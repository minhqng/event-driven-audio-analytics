"""Verify the broker-backed processing -> writer -> TimescaleDB flow for one run."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from time import monotonic, sleep

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.settings import load_database_settings
from event_driven_audio_analytics.smoke.verify_ingestion_flow import (
    EXPECTED_RUN_TOTAL_METRICS,
    SmokeExpectation,
    _derive_smoke_expectation,
)
from event_driven_audio_analytics.writer.config import WriterSettings


DEFAULT_VERIFY_TIMEOUT_S = 30.0
DEFAULT_VERIFY_POLL_INTERVAL_S = 1.0


@dataclass(slots=True)
class WriterDatabaseSnapshot:
    """Observed TimescaleDB state for one verified smoke run."""

    track_metadata_count: int
    audio_features_count: int
    ingestion_metric_counts: dict[str, int]
    processing_metric_counts: dict[str, int]
    writer_metric_counts: dict[str, int]
    writer_metric_shapes: dict["WriterMetricShape", int]
    writer_rows_upserted_values: tuple[float, ...]
    checkpoint_topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WriterMetricShape:
    """Normalized metric contract shape for one writer-owned metric bucket."""

    metric_name: str
    unit: str | None
    topic: str | None
    status: str | None
    has_failure_class: bool


@dataclass(slots=True)
class WriterSmokeSummary:
    """Compact verification summary for the writer-backed smoke path."""

    run_id: str
    metadata_count: int
    feature_count: int
    ingestion_metric_count: int
    processing_metric_count: int
    writer_record_count: int
    checkpoint_topics: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "metadata_count": self.metadata_count,
                "feature_count": self.feature_count,
                "ingestion_metric_count": self.ingestion_metric_count,
                "processing_metric_count": self.processing_metric_count,
                "writer_record_count": self.writer_record_count,
                "checkpoint_topics": self.checkpoint_topics,
            },
            separators=(",", ":"),
            sort_keys=True,
        )


def _query_scalar(cursor: object, sql: str, params: tuple[object, ...]) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


def _query_metric_counts(
    cursor: object,
    *,
    run_id: str,
    service_name: str,
) -> dict[str, int]:
    cursor.execute(
        """
        SELECT metric_name, COUNT(*)::int
        FROM system_metrics
        WHERE run_id = %s
          AND service_name = %s
        GROUP BY metric_name
        ORDER BY metric_name;
        """,
        (run_id, service_name),
    )
    return {
        str(metric_name): int(count)
        for metric_name, count in cursor.fetchall()
    }


def _query_writer_rows_upserted_values(cursor: object, *, run_id: str) -> tuple[float, ...]:
    cursor.execute(
        """
        SELECT metric_value
        FROM system_metrics
        WHERE run_id = %s
          AND service_name = 'writer'
          AND metric_name = 'rows_upserted'
        ORDER BY ts ASC;
        """,
        (run_id,),
    )
    return tuple(float(row[0]) for row in cursor.fetchall())


def _query_writer_metric_shapes(cursor: object, *, run_id: str) -> dict[WriterMetricShape, int]:
    cursor.execute(
        """
        SELECT
            metric_name,
            unit,
            labels_json ->> 'topic' AS topic,
            labels_json ->> 'status' AS status,
            labels_json ? 'failure_class' AS has_failure_class,
            COUNT(*)::int
        FROM system_metrics
        WHERE run_id = %s
          AND service_name = 'writer'
        GROUP BY metric_name, unit, topic, status, has_failure_class
        ORDER BY metric_name, unit, topic, status, has_failure_class;
        """,
        (run_id,),
    )
    return {
        WriterMetricShape(
            metric_name=str(metric_name),
            unit=str(unit) if unit is not None else None,
            topic=str(topic) if topic is not None else None,
            status=str(status) if status is not None else None,
            has_failure_class=bool(has_failure_class),
        ): int(count)
        for metric_name, unit, topic, status, has_failure_class, count in cursor.fetchall()
    }


def _query_checkpoint_topics(
    cursor: object,
    *,
    run_id: str,
    consumer_group: str,
) -> tuple[str, ...]:
    cursor.execute(
        """
        SELECT DISTINCT topic_name
        FROM run_checkpoints
        WHERE run_id = %s
          AND consumer_group = %s
        ORDER BY topic_name;
        """,
        (run_id, consumer_group),
    )
    return tuple(str(row[0]) for row in cursor.fetchall())


def _query_writer_snapshot(
    *,
    run_id: str,
    consumer_group: str,
) -> WriterDatabaseSnapshot:
    database_settings = load_database_settings()
    with open_database_connection(database_settings) as connection:
        with connection.cursor() as cursor:
            return WriterDatabaseSnapshot(
                track_metadata_count=_query_scalar(
                    cursor,
                    "SELECT COUNT(*) FROM track_metadata WHERE run_id = %s;",
                    (run_id,),
                ),
                audio_features_count=_query_scalar(
                    cursor,
                    "SELECT COUNT(*) FROM audio_features WHERE run_id = %s;",
                    (run_id,),
                ),
                ingestion_metric_counts=_query_metric_counts(
                    cursor,
                    run_id=run_id,
                    service_name="ingestion",
                ),
                processing_metric_counts=_query_metric_counts(
                    cursor,
                    run_id=run_id,
                    service_name="processing",
                ),
                writer_metric_counts=_query_metric_counts(
                    cursor,
                    run_id=run_id,
                    service_name="writer",
                ),
                writer_metric_shapes=_query_writer_metric_shapes(
                    cursor,
                    run_id=run_id,
                ),
                writer_rows_upserted_values=_query_writer_rows_upserted_values(
                    cursor,
                    run_id=run_id,
                ),
                checkpoint_topics=_query_checkpoint_topics(
                    cursor,
                    run_id=run_id,
                    consumer_group=consumer_group,
                ),
            )


def _assert_writer_snapshot(
    snapshot: WriterDatabaseSnapshot,
    *,
    run_id: str,
    expectation: SmokeExpectation,
    consumer_group: str,
) -> WriterSmokeSummary:
    expected_metadata_count = len(expectation.track_expectations)
    expected_feature_count = len(expectation.segment_pairs)
    expected_processing_metric_count = (2 * expected_feature_count)
    expected_writer_record_count = (
        expected_metadata_count
        + expected_feature_count
        + len(EXPECTED_RUN_TOTAL_METRICS)
        + expected_processing_metric_count
    )
    expected_writer_topic_counts = {
        "audio.metadata": expected_metadata_count,
        "audio.features": expected_feature_count,
        "system.metrics": len(EXPECTED_RUN_TOTAL_METRICS) + expected_processing_metric_count,
    }

    if snapshot.track_metadata_count != expected_metadata_count:
        raise RuntimeError(
            "Writer smoke track_metadata count drifted from the selected input count. "
            f"Expected {expected_metadata_count} observed {snapshot.track_metadata_count}."
        )
    if snapshot.audio_features_count != expected_feature_count:
        raise RuntimeError(
            "Writer smoke audio_features count drifted from the selected segment count. "
            f"Expected {expected_feature_count} observed {snapshot.audio_features_count}."
        )

    if set(snapshot.ingestion_metric_counts) != EXPECTED_RUN_TOTAL_METRICS:
        raise RuntimeError(
            "Writer smoke ingestion metric set drifted from the bounded run_total contract. "
            f"Observed {sorted(snapshot.ingestion_metric_counts)}."
        )
    if any(count != 1 for count in snapshot.ingestion_metric_counts.values()):
        raise RuntimeError("Writer smoke ingestion run_total metrics must persist as one snapshot row each.")

    if snapshot.processing_metric_counts.get("processing_ms", 0) != expected_feature_count:
        raise RuntimeError(
            "Writer smoke processing_ms DB count drifted from the selected segment count. "
            f"Expected {expected_feature_count} observed {snapshot.processing_metric_counts.get('processing_ms', 0)}."
        )

    expected_silent_ratio_count = 1 if expected_feature_count > 0 else 0
    if snapshot.processing_metric_counts.get("silent_ratio", 0) != expected_silent_ratio_count:
        raise RuntimeError(
            "Writer smoke silent_ratio DB count drifted from the replay-safe run_total rule. "
            f"Expected {expected_silent_ratio_count} observed {snapshot.processing_metric_counts.get('silent_ratio', 0)}."
        )

    if snapshot.processing_metric_counts.get("feature_errors", 0) != 0:
        raise RuntimeError("Healthy writer smoke runs must not persist processing feature_errors.")

    if snapshot.writer_metric_counts.get("write_ms", 0) != expected_writer_record_count:
        raise RuntimeError(
            "Writer smoke write_ms count drifted from the consumed writer record count. "
            f"Expected {expected_writer_record_count} observed {snapshot.writer_metric_counts.get('write_ms', 0)}."
        )

    if snapshot.writer_metric_counts.get("rows_upserted", 0) != expected_writer_record_count:
        raise RuntimeError(
            "Writer smoke rows_upserted count drifted from the consumed writer record count. "
            f"Expected {expected_writer_record_count} observed {snapshot.writer_metric_counts.get('rows_upserted', 0)}."
        )

    if snapshot.writer_metric_counts.get("write_failures", 0) != 0:
        raise RuntimeError("Healthy writer smoke runs must not persist writer write_failures.")

    expected_writer_metric_shapes = {}
    for topic_name, topic_count in expected_writer_topic_counts.items():
        if topic_count <= 0:
            continue
        expected_writer_metric_shapes[
            WriterMetricShape(
                metric_name="write_ms",
                unit="ms",
                topic=topic_name,
                status="ok",
                has_failure_class=False,
            )
        ] = topic_count
        expected_writer_metric_shapes[
            WriterMetricShape(
                metric_name="rows_upserted",
                unit="count",
                topic=topic_name,
                status="ok",
                has_failure_class=False,
            )
        ] = topic_count

    if snapshot.writer_metric_shapes != expected_writer_metric_shapes:
        raise RuntimeError(
            "Writer smoke writer metric contract drifted from the locked labels/unit semantics. "
            f"Expected {expected_writer_metric_shapes} observed {snapshot.writer_metric_shapes}."
        )

    if snapshot.writer_rows_upserted_values and any(
        abs(value - 1.0) > 1e-9 for value in snapshot.writer_rows_upserted_values
    ):
        raise RuntimeError("Writer smoke rows_upserted metric_value must stay 1.0 per consumed record.")

    expected_checkpoint_topics = {"audio.metadata", "system.metrics"}
    if expected_feature_count > 0:
        expected_checkpoint_topics.add("audio.features")
    if set(snapshot.checkpoint_topics) != expected_checkpoint_topics:
        raise RuntimeError(
            "Writer smoke checkpoint topics drifted from the exercised writer inputs. "
            f"Expected {sorted(expected_checkpoint_topics)} observed {list(snapshot.checkpoint_topics)}."
        )

    return WriterSmokeSummary(
        run_id=run_id,
        metadata_count=snapshot.track_metadata_count,
        feature_count=snapshot.audio_features_count,
        ingestion_metric_count=sum(snapshot.ingestion_metric_counts.values()),
        processing_metric_count=sum(snapshot.processing_metric_counts.values()),
        writer_record_count=expected_writer_record_count,
        checkpoint_topics=snapshot.checkpoint_topics,
    )


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = float(raw_value)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive when set.")
    return value


def verify_writer_snapshot_with_retries(
    *,
    run_id: str,
    consumer_group: str,
    expectation: SmokeExpectation,
    timeout_s: float,
    poll_interval_s: float,
) -> WriterSmokeSummary:
    """Poll TimescaleDB until the current-run writer snapshot satisfies the smoke contract."""

    deadline = monotonic() + timeout_s
    last_error: RuntimeError | None = None

    while monotonic() <= deadline:
        snapshot = _query_writer_snapshot(
            run_id=run_id,
            consumer_group=consumer_group,
        )
        try:
            return _assert_writer_snapshot(
                snapshot,
                run_id=run_id,
                expectation=expectation,
                consumer_group=consumer_group,
            )
        except RuntimeError as exc:
            last_error = exc
            if monotonic() >= deadline:
                raise
            sleep(poll_interval_s)
            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError("Writer smoke verification timed out without producing a summary.")


def main() -> None:
    ingestion_settings = IngestionSettings.from_env()
    writer_settings = WriterSettings.from_env()
    expectation = _derive_smoke_expectation(ingestion_settings)
    timeout_s = _env_float("WRITER_SMOKE_VERIFY_TIMEOUT_S", DEFAULT_VERIFY_TIMEOUT_S)
    poll_interval_s = _env_float(
        "WRITER_SMOKE_VERIFY_POLL_INTERVAL_S",
        DEFAULT_VERIFY_POLL_INTERVAL_S,
    )
    summary = verify_writer_snapshot_with_retries(
        run_id=ingestion_settings.base.run_id,
        consumer_group=writer_settings.consumer_group,
        expectation=expectation,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    )
    print(summary.to_json())


if __name__ == "__main__":
    main()
