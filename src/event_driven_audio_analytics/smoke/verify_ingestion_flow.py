"""Verify the bounded ingestion smoke flow against Kafka and the run manifest."""

from __future__ import annotations

import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from event_driven_audio_analytics.ingestion.modules.artifact_writer import read_manifest_frame
from event_driven_audio_analytics.shared.checksum import sha256_file
from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.shared.kafka import build_consumer, deserialize_envelope
from event_driven_audio_analytics.shared.settings import load_base_service_settings
from event_driven_audio_analytics.shared.storage import manifest_uri


EXPECTED_SEGMENT_COUNT = 3
EXPECTED_METADATA_TRACK_IDS = {2, 666}
EXPECTED_RUN_TOTAL_METRICS = {
    "tracks_total",
    "segments_total",
    "validation_failures",
    "artifact_write_ms",
}
EXPECTED_TOPIC_COUNTS = {
    AUDIO_METADATA: 2,
    AUDIO_SEGMENT_READY: EXPECTED_SEGMENT_COUNT,
    SYSTEM_METRICS: 4,
}


def _consume_topic(
    topic: str,
    *,
    timeout_s: float = 20.0,
    idle_timeout_s: float = 3.0,
) -> list[dict[str, object]]:
    """Consume all currently visible messages from one topic until the topic goes idle."""

    from confluent_kafka import KafkaError, KafkaException

    settings = load_base_service_settings("ingestion-smoke-verifier")
    consumer = build_consumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
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
                if last_message_at is not None and monotonic() - last_message_at >= idle_timeout_s:
                    break
                continue
            if message.error() is not None:
                if message.error().code() in (
                    KafkaError._PARTITION_EOF,
                    KafkaError.UNKNOWN_TOPIC_OR_PART,
                ):
                    if last_message_at is not None and monotonic() - last_message_at >= idle_timeout_s:
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


def _filter_messages_for_run(messages: list[dict[str, object]], *, run_id: str) -> list[dict[str, object]]:
    """Return only the messages that belong to the active smoke run."""

    return [
        message
        for message in messages
        if message.get("envelope", {}).get("run_id") == run_id
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


def _assert_metadata_messages(messages: list[dict[str, object]]) -> str:
    """Validate the bounded metadata outcomes for the smoke fixture set."""

    payload_by_track_id = {
        int(message["envelope"]["payload"]["track_id"]): message["envelope"]["payload"]
        for message in messages
    }
    if set(payload_by_track_id) != EXPECTED_METADATA_TRACK_IDS:
        raise RuntimeError(
            "Smoke metadata events did not contain the expected track ids. "
            f"Observed: {sorted(payload_by_track_id)}."
        )

    validated_payload = payload_by_track_id[2]
    rejected_payload = payload_by_track_id[666]
    if validated_payload["validation_status"] != "validated":
        raise RuntimeError("Track 2 must publish validated metadata in the smoke flow.")
    if rejected_payload["validation_status"] != "probe_failed":
        raise RuntimeError("Track 666 must publish probe_failed metadata in the smoke flow.")
    if "manifest_uri" in rejected_payload:
        raise RuntimeError("Reject-path metadata must not advertise manifest_uri.")

    manifest_uri_value = validated_payload.get("manifest_uri")
    if not isinstance(manifest_uri_value, str) or not manifest_uri_value:
        raise RuntimeError("Validated smoke metadata must expose manifest_uri.")
    return manifest_uri_value


def _assert_segment_messages(messages: list[dict[str, object]], *, manifest_uri_value: str) -> None:
    """Validate the bounded segment-ready messages for the smoke fixture set."""

    track_ids = {int(message["envelope"]["payload"]["track_id"]) for message in messages}
    if track_ids != {2}:
        raise RuntimeError(
            f"Smoke segment-ready events must contain only track_id=2, observed {sorted(track_ids)}."
        )

    segment_indices = {
        int(message["envelope"]["payload"]["segment_idx"])
        for message in messages
    }
    if segment_indices != {0, 1, 2}:
        raise RuntimeError(
            "Smoke segment-ready events must contain segment_idx values 0, 1, and 2."
        )

    for message in messages:
        payload = message["envelope"]["payload"]
        if message["key"] != "2":
            raise RuntimeError("Smoke segment-ready events must stay keyed by track_id=2.")
        if payload["manifest_uri"] != manifest_uri_value:
            raise RuntimeError("Segment-ready manifest_uri did not match validated metadata.")


def _assert_metric_messages(messages: list[dict[str, object]]) -> None:
    """Validate the bounded run-level system.metrics output."""

    metric_names = {
        str(message["envelope"]["payload"]["metric_name"])
        for message in messages
    }
    if metric_names != EXPECTED_RUN_TOTAL_METRICS:
        raise RuntimeError(
            "Smoke system.metrics events did not contain the expected metric names. "
            f"Observed: {sorted(metric_names)}."
        )

    for message in messages:
        payload = message["envelope"]["payload"]
        if message["key"] != "ingestion":
            raise RuntimeError("Smoke system.metrics events must stay keyed by service_name=ingestion.")
        if payload["service_name"] != "ingestion":
            raise RuntimeError("Smoke system.metrics payloads must expose service_name=ingestion.")
        labels_json = payload.get("labels_json")
        if not isinstance(labels_json, dict) or labels_json.get("scope") != "run_total":
            raise RuntimeError("Smoke system.metrics payloads must stay scoped as run_total snapshots.")


def _assert_manifest(
    manifest_uri_value: str,
    segment_messages: list[dict[str, object]],
    *,
    artifacts_root: Path,
    run_id: str,
) -> dict[str, object]:
    """Validate the run manifest and its checksum linkage."""

    expected_manifest_uri = manifest_uri(artifacts_root, run_id)
    if manifest_uri_value != expected_manifest_uri:
        raise RuntimeError(
            "Smoke metadata manifest_uri did not match the canonical run manifest location."
        )

    manifest_path = Path(manifest_uri_value)
    if not manifest_path.exists():
        raise RuntimeError(f"Run manifest does not exist: {manifest_path.as_posix()}")

    manifest_frame = read_manifest_frame(manifest_path)
    track_ids = sorted({int(value) for value in manifest_frame["track_id"].to_list()})
    if track_ids != [2]:
        raise RuntimeError(f"Run manifest must contain only track_id=2 rows, observed {track_ids}.")
    if manifest_frame.height != EXPECTED_SEGMENT_COUNT:
        raise RuntimeError(
            f"Run manifest must contain {EXPECTED_SEGMENT_COUNT} rows, observed {manifest_frame.height}."
        )

    manifest_rows = {
        int(row["segment_idx"]): row
        for row in manifest_frame.to_dicts()
    }
    for message in segment_messages:
        payload = message["envelope"]["payload"]
        segment_idx = int(payload["segment_idx"])
        manifest_row = manifest_rows.get(segment_idx)
        if manifest_row is None:
            raise RuntimeError(
                f"Run manifest is missing segment_idx={segment_idx} from segment-ready events."
            )
        if manifest_row["artifact_uri"] != payload["artifact_uri"]:
            raise RuntimeError("Run manifest artifact_uri did not match segment-ready payload.")
        if manifest_row["checksum"] != payload["checksum"]:
            raise RuntimeError("Run manifest checksum did not match segment-ready payload.")
        if sha256_file(payload["artifact_uri"]) != payload["checksum"]:
            raise RuntimeError("Segment artifact checksum did not match the smoke payload.")

    return {
        "manifest_uri": manifest_uri_value,
        "manifest_rows": manifest_frame.height,
        "track_ids": track_ids,
        "segment_indices": sorted(manifest_rows),
    }


def main() -> None:
    """Verify the bounded ingestion smoke path and print a compact summary."""

    settings = load_base_service_settings("ingestion-smoke-verifier")
    metadata_messages = _filter_messages_for_run(
        _consume_topic(AUDIO_METADATA),
        run_id=settings.run_id,
    )
    segment_messages = _filter_messages_for_run(
        _consume_topic(AUDIO_SEGMENT_READY),
        run_id=settings.run_id,
    )
    metric_messages = _filter_messages_for_run(
        _consume_topic(SYSTEM_METRICS),
        run_id=settings.run_id,
    )

    _assert_expected_count(
        AUDIO_METADATA,
        metadata_messages,
        expected_count=EXPECTED_TOPIC_COUNTS[AUDIO_METADATA],
        run_id=settings.run_id,
    )
    _assert_expected_count(
        AUDIO_SEGMENT_READY,
        segment_messages,
        expected_count=EXPECTED_TOPIC_COUNTS[AUDIO_SEGMENT_READY],
        run_id=settings.run_id,
    )
    _assert_expected_count(
        SYSTEM_METRICS,
        metric_messages,
        expected_count=EXPECTED_TOPIC_COUNTS[SYSTEM_METRICS],
        run_id=settings.run_id,
    )

    manifest_uri_value = _assert_metadata_messages(metadata_messages)
    _assert_segment_messages(segment_messages, manifest_uri_value=manifest_uri_value)
    _assert_metric_messages(metric_messages)
    manifest_summary = _assert_manifest(
        manifest_uri_value,
        segment_messages,
        artifacts_root=settings.artifacts_root,
        run_id=settings.run_id,
    )

    print(
        json.dumps(
            {
                "run_id": settings.run_id,
                "metadata_tracks": sorted(EXPECTED_METADATA_TRACK_IDS),
                "segment_count": EXPECTED_SEGMENT_COUNT,
                "metrics": sorted(EXPECTED_RUN_TOTAL_METRICS),
                **manifest_summary,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
