"""Verify the bounded ingestion smoke flow against Kafka and the run manifest."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.ingestion.modules.artifact_writer import read_manifest_frame
from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_NO_SEGMENTS,
    VALIDATION_STATUS_VALIDATED,
    validate_audio_record,
)
from event_driven_audio_analytics.ingestion.modules.metadata_loader import (
    load_small_subset_metadata,
)
from event_driven_audio_analytics.ingestion.modules.segmenter import segment_audio
from event_driven_audio_analytics.shared.checksum import sha256_file
from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.shared.kafka import build_consumer, deserialize_envelope
from event_driven_audio_analytics.shared.storage import manifest_uri, resolve_artifact_uri


EXPECTED_RUN_TOTAL_METRICS = {
    "tracks_total",
    "segments_total",
    "validation_failures",
    "artifact_write_ms",
}


@dataclass(slots=True)
class TrackExpectation:
    """Expected smoke outcome for one selected metadata record."""

    track_id: int
    validation_status: str
    segment_indices: tuple[int, ...]

    @property
    def expects_manifest(self) -> bool:
        """Return whether this track should publish the run manifest URI."""

        return bool(self.segment_indices)


@dataclass(slots=True)
class SmokeExpectation:
    """Expected smoke outcome for the configured bounded ingestion run."""

    track_expectations: dict[int, TrackExpectation]

    @property
    def metadata_track_ids(self) -> tuple[int, ...]:
        """Return the selected metadata track ids in stable order."""

        return tuple(sorted(self.track_expectations))

    @property
    def validated_track_ids(self) -> tuple[int, ...]:
        """Return the track ids that should emit segment-ready events."""

        return tuple(
            sorted(
                track_id
                for track_id, expectation in self.track_expectations.items()
                if expectation.expects_manifest
            )
        )

    @property
    def rejected_track_ids(self) -> tuple[int, ...]:
        """Return the track ids that stay metadata-only in this run."""

        return tuple(
            sorted(
                track_id
                for track_id, expectation in self.track_expectations.items()
                if not expectation.expects_manifest
            )
        )

    @property
    def segment_pairs(self) -> tuple[tuple[int, int], ...]:
        """Return the expected logical segment identities."""

        return tuple(
            sorted(
                (track_id, segment_idx)
                for track_id, expectation in self.track_expectations.items()
                for segment_idx in expectation.segment_indices
            )
        )

    @property
    def expected_topic_counts(self) -> dict[str, int]:
        """Return the exact current-run message counts per smoke topic."""

        return {
            AUDIO_METADATA: len(self.track_expectations),
            AUDIO_SEGMENT_READY: len(self.segment_pairs),
            SYSTEM_METRICS: len(EXPECTED_RUN_TOTAL_METRICS),
        }

    @property
    def validation_failures(self) -> int:
        """Return the expected number of metadata-only validation outcomes."""

        return sum(
            1
            for expectation in self.track_expectations.values()
            if expectation.validation_status != VALIDATION_STATUS_VALIDATED
        )


def _derive_smoke_expectation(settings: IngestionSettings) -> SmokeExpectation:
    """Derive expected smoke outputs from the currently selected input set."""

    records = load_small_subset_metadata(
        settings.metadata_csv_path,
        audio_root_path=settings.audio_root_path,
        subset=settings.subset,
        track_id_allowlist=settings.track_id_allowlist,
        max_tracks=settings.max_tracks,
    )

    expectations: dict[int, TrackExpectation] = {}
    for record in records:
        validation = validate_audio_record(
            record,
            target_sample_rate_hz=settings.target_sample_rate_hz,
            min_duration_s=settings.min_duration_s,
            silence_threshold_db=settings.silence_threshold_db,
        )
        segment_indices: tuple[int, ...] = ()
        validation_status = validation.validation_status
        if (
            validation.validation_status == VALIDATION_STATUS_VALIDATED
            and validation.decoded_audio is not None
        ):
            segments = segment_audio(
                run_id=settings.base.run_id,
                track_id=record.track_id,
                waveform=validation.decoded_audio.waveform,
                sample_rate_hz=validation.decoded_audio.sample_rate_hz,
                segment_duration_s=settings.segment_duration_s,
                segment_overlap_s=settings.segment_overlap_s,
            )
            if segments:
                segment_indices = tuple(segment.segment_idx for segment in segments)
            else:
                validation_status = VALIDATION_STATUS_NO_SEGMENTS

        expectations[record.track_id] = TrackExpectation(
            track_id=record.track_id,
            validation_status=validation_status,
            segment_indices=segment_indices,
        )

    return SmokeExpectation(track_expectations=expectations)


def _consume_topic(
    topic: str,
    *,
    timeout_s: float = 20.0,
    idle_timeout_s: float = 3.0,
) -> list[dict[str, object]]:
    """Consume all currently visible messages from one topic until the topic goes idle."""

    from confluent_kafka import KafkaError, KafkaException

    settings = IngestionSettings.from_env()
    consumer = build_consumer(
        bootstrap_servers=settings.base.kafka_bootstrap_servers,
        group_id=f"ingestion-smoke-{topic}-{uuid4().hex}",
        client_id=f"ingestion-smoke-{topic}",
        topics=(topic,),
        auto_offset_reset="earliest",
    )

    try:
        messages: list[dict[str, object]] = []
        deadline = monotonic() + timeout_s
        last_message_at: float | None = None
        while monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is None:
                if (
                    last_message_at is not None
                    and monotonic() - last_message_at >= idle_timeout_s
                ):
                    break
                continue
            if message.error() is not None:
                if message.error().code() in (
                    KafkaError._PARTITION_EOF,
                    KafkaError.UNKNOWN_TOPIC_OR_PART,
                ):
                    if (
                        last_message_at is not None
                        and monotonic() - last_message_at >= idle_timeout_s
                    ):
                        break
                    continue
                raise KafkaException(message.error())

            last_message_at = monotonic()
            messages.append(
                {
                    "key": (
                        message.key().decode("utf-8")
                        if message.key() is not None
                        else None
                    ),
                    "envelope": deserialize_envelope(message.value() or b""),
                }
            )
        return messages
    finally:
        consumer.close()


def _filter_messages_for_run(
    messages: list[dict[str, object]],
    *,
    run_id: str,
) -> list[dict[str, object]]:
    """Return only the messages that belong to the active smoke run."""

    return [
        message for message in messages if message.get("envelope", {}).get("run_id") == run_id
    ]


def _assert_expected_count(
    topic: str,
    messages: list[dict[str, object]],
    *,
    expected_count: int,
    run_id: str,
) -> None:
    """Ensure one topic produced the exact number of messages for the active run."""

    if len(messages) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} messages on {topic} for run_id={run_id}, "
            f"but observed {len(messages)}."
        )


def _assert_metadata_messages(
    messages: list[dict[str, object]],
    *,
    expectation: SmokeExpectation,
    artifacts_root: Path,
    run_id: str,
) -> str | None:
    """Validate metadata events for the currently configured smoke run."""

    payload_by_track_id = {
        int(message["envelope"]["payload"]["track_id"]): message["envelope"]["payload"]
        for message in messages
    }
    expected_track_ids = set(expectation.metadata_track_ids)
    if set(payload_by_track_id) != expected_track_ids:
        raise RuntimeError(
            "Smoke metadata events did not contain the expected track ids. "
            f"Observed: {sorted(payload_by_track_id)}."
        )

    expected_manifest_uri = (
        manifest_uri(artifacts_root, run_id) if expectation.validated_track_ids else None
    )

    for message in messages:
        payload = message["envelope"]["payload"]
        track_id = int(payload["track_id"])
        if message["key"] != str(track_id):
            raise RuntimeError("Smoke audio.metadata events must stay keyed by track_id.")

        track_expectation = expectation.track_expectations[track_id]
        if payload["validation_status"] != track_expectation.validation_status:
            raise RuntimeError(
                "Smoke audio.metadata validation_status drifted from the selected input outcome "
                f"for track_id={track_id}."
            )

        manifest_uri_value = payload.get("manifest_uri")
        if track_expectation.expects_manifest:
            if manifest_uri_value != expected_manifest_uri:
                raise RuntimeError(
                    "Validated smoke metadata must expose the canonical run manifest URI."
                )
        elif "manifest_uri" in payload:
            raise RuntimeError("Metadata-only smoke outcomes must not advertise manifest_uri.")

    return expected_manifest_uri


def _assert_segment_messages(
    messages: list[dict[str, object]],
    *,
    expectation: SmokeExpectation,
    manifest_uri_value: str | None,
) -> None:
    """Validate segment-ready events for the currently configured smoke run."""

    expected_segment_pairs = set(expectation.segment_pairs)
    observed_segment_pairs = {
        (
            int(message["envelope"]["payload"]["track_id"]),
            int(message["envelope"]["payload"]["segment_idx"]),
        )
        for message in messages
    }
    if observed_segment_pairs != expected_segment_pairs:
        raise RuntimeError(
            "Smoke segment-ready events did not contain the expected logical segments. "
            f"Observed: {sorted(observed_segment_pairs)}."
        )

    if expected_segment_pairs and manifest_uri_value is None:
        raise RuntimeError("Validated smoke segment-ready events require a manifest_uri.")

    for message in messages:
        payload = message["envelope"]["payload"]
        track_id = int(payload["track_id"])
        if message["key"] != str(track_id):
            raise RuntimeError("Smoke audio.segment.ready events must stay keyed by track_id.")
        if payload["manifest_uri"] != manifest_uri_value:
            raise RuntimeError("Segment-ready manifest_uri did not match validated metadata.")


def _assert_metric_messages(
    messages: list[dict[str, object]],
    *,
    expectation: SmokeExpectation,
) -> None:
    """Validate the bounded run-level system.metrics output."""

    metric_payloads = {
        str(message["envelope"]["payload"]["metric_name"]): message["envelope"]["payload"]
        for message in messages
    }
    if set(metric_payloads) != EXPECTED_RUN_TOTAL_METRICS:
        raise RuntimeError(
            "Smoke system.metrics events did not contain the expected metric names. "
            f"Observed: {sorted(metric_payloads)}."
        )

    expected_metric_values = {
        "tracks_total": float(len(expectation.metadata_track_ids)),
        "segments_total": float(len(expectation.segment_pairs)),
        "validation_failures": float(expectation.validation_failures),
    }

    for message in messages:
        payload = message["envelope"]["payload"]
        metric_name = str(payload["metric_name"])
        if message["key"] != "ingestion":
            raise RuntimeError(
                "Smoke system.metrics events must stay keyed by service_name=ingestion."
            )
        if payload["service_name"] != "ingestion":
            raise RuntimeError(
                "Smoke system.metrics payloads must expose service_name=ingestion."
            )
        labels_json = payload.get("labels_json")
        if not isinstance(labels_json, dict) or labels_json.get("scope") != "run_total":
            raise RuntimeError(
                "Smoke system.metrics payloads must stay scoped as run_total snapshots."
            )
        if metric_name in expected_metric_values:
            if float(payload["metric_value"]) != expected_metric_values[metric_name]:
                raise RuntimeError(
                    "Smoke system.metrics metric_value drifted from the selected input outcome "
                    f"for metric_name={metric_name}."
                )
        elif float(payload["metric_value"]) < 0.0:
            raise RuntimeError("Smoke artifact_write_ms must stay non-negative.")


def _assert_manifest(
    manifest_uri_value: str | None,
    segment_messages: list[dict[str, object]],
    *,
    expectation: SmokeExpectation,
    artifacts_root: Path,
    run_id: str,
) -> dict[str, object]:
    """Validate the run manifest and its checksum linkage."""

    expected_manifest_uri = manifest_uri(artifacts_root, run_id)
    if not expectation.segment_pairs:
        if manifest_uri_value is not None:
            raise RuntimeError("Metadata-only smoke runs must not surface a manifest URI.")
        manifest_path = resolve_artifact_uri(artifacts_root, expected_manifest_uri)
        if manifest_path.exists():
            raise RuntimeError(
                "Metadata-only smoke runs must not leave behind a run manifest file."
            )
        return {
            "manifest_uri": expected_manifest_uri,
            "manifest_rows": 0,
            "track_ids": [],
            "segment_pairs": [],
        }

    if manifest_uri_value != expected_manifest_uri:
        raise RuntimeError(
            "Smoke metadata manifest_uri did not match the canonical run manifest location."
        )

    manifest_path = resolve_artifact_uri(artifacts_root, manifest_uri_value)
    if not manifest_path.exists():
        raise RuntimeError(f"Run manifest does not exist: {manifest_path.as_posix()}")

    manifest_frame = read_manifest_frame(manifest_path)
    track_ids = sorted({int(value) for value in manifest_frame["track_id"].to_list()})
    if track_ids != list(expectation.validated_track_ids):
        raise RuntimeError(
            "Run manifest track ids drifted from the selected validated smoke tracks. "
            f"Observed: {track_ids}."
        )
    if manifest_frame.height != len(expectation.segment_pairs):
        raise RuntimeError(
            "Run manifest row count drifted from the selected smoke segment count. "
            f"Observed: {manifest_frame.height}."
        )

    manifest_rows = {
        (int(row["track_id"]), int(row["segment_idx"])): row
        for row in manifest_frame.to_dicts()
    }
    if set(manifest_rows) != set(expectation.segment_pairs):
        raise RuntimeError(
            "Run manifest logical segments drifted from the selected smoke segment identities. "
            f"Observed: {sorted(manifest_rows)}."
        )

    for message in segment_messages:
        payload = message["envelope"]["payload"]
        segment_key = (int(payload["track_id"]), int(payload["segment_idx"]))
        manifest_row = manifest_rows.get(segment_key)
        if manifest_row is None:
            raise RuntimeError(
                "Run manifest is missing one logical segment from the emitted segment-ready events "
                f"for track_id={segment_key[0]} segment_idx={segment_key[1]}."
            )
        if manifest_row["artifact_uri"] != payload["artifact_uri"]:
            raise RuntimeError("Run manifest artifact_uri did not match segment-ready payload.")
        if manifest_row["checksum"] != payload["checksum"]:
            raise RuntimeError("Run manifest checksum did not match segment-ready payload.")
        artifact_path = resolve_artifact_uri(artifacts_root, str(payload["artifact_uri"]))
        if sha256_file(artifact_path) != payload["checksum"]:
            raise RuntimeError("Segment artifact checksum did not match the smoke payload.")

    return {
        "manifest_uri": manifest_uri_value,
        "manifest_rows": manifest_frame.height,
        "track_ids": track_ids,
        "segment_pairs": [list(segment_key) for segment_key in sorted(manifest_rows)],
    }


def main() -> None:
    """Verify the bounded ingestion smoke path and print a compact summary."""

    settings = IngestionSettings.from_env()
    expectation = _derive_smoke_expectation(settings)
    metadata_messages = _filter_messages_for_run(
        _consume_topic(AUDIO_METADATA),
        run_id=settings.base.run_id,
    )
    segment_messages = _filter_messages_for_run(
        _consume_topic(AUDIO_SEGMENT_READY),
        run_id=settings.base.run_id,
    )
    metric_messages = _filter_messages_for_run(
        _consume_topic(SYSTEM_METRICS),
        run_id=settings.base.run_id,
    )

    _assert_expected_count(
        AUDIO_METADATA,
        metadata_messages,
        expected_count=expectation.expected_topic_counts[AUDIO_METADATA],
        run_id=settings.base.run_id,
    )
    _assert_expected_count(
        AUDIO_SEGMENT_READY,
        segment_messages,
        expected_count=expectation.expected_topic_counts[AUDIO_SEGMENT_READY],
        run_id=settings.base.run_id,
    )
    _assert_expected_count(
        SYSTEM_METRICS,
        metric_messages,
        expected_count=expectation.expected_topic_counts[SYSTEM_METRICS],
        run_id=settings.base.run_id,
    )

    manifest_uri_value = _assert_metadata_messages(
        metadata_messages,
        expectation=expectation,
        artifacts_root=settings.base.artifacts_root,
        run_id=settings.base.run_id,
    )
    _assert_segment_messages(
        segment_messages,
        expectation=expectation,
        manifest_uri_value=manifest_uri_value,
    )
    _assert_metric_messages(metric_messages, expectation=expectation)
    manifest_summary = _assert_manifest(
        manifest_uri_value,
        segment_messages,
        expectation=expectation,
        artifacts_root=settings.base.artifacts_root,
        run_id=settings.base.run_id,
    )

    print(
        json.dumps(
            {
                "run_id": settings.base.run_id,
                "metadata_tracks": list(expectation.metadata_track_ids),
                "validated_track_ids": list(expectation.validated_track_ids),
                "rejected_track_ids": list(expectation.rejected_track_ids),
                "segment_count": len(expectation.segment_pairs),
                "metrics": sorted(EXPECTED_RUN_TOTAL_METRICS),
                **manifest_summary,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
