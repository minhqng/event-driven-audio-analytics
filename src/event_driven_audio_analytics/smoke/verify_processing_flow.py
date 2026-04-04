"""Verify the bounded processing smoke flow against Kafka outputs for one run."""

from __future__ import annotations

from dataclasses import dataclass
import json
from time import monotonic
from uuid import uuid4

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.shared.contracts.topics import AUDIO_FEATURES, SYSTEM_METRICS
from event_driven_audio_analytics.shared.kafka import build_consumer, deserialize_envelope
from event_driven_audio_analytics.shared.models.envelope import validate_envelope_dict
from event_driven_audio_analytics.smoke.verify_ingestion_flow import _derive_smoke_expectation


EXPECTED_PROCESSING_EVENT_METRICS = {
    "processing_ms",
    "silent_ratio",
}


@dataclass(slots=True)
class ProcessingSmokeSummary:
    """Compact verification summary for the processing smoke path."""

    run_id: str
    expected_segment_count: int
    feature_count: int
    processing_ms_count: int
    silent_ratio_count: int
    final_silent_ratio: float
    silent_segments: int

    def to_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "expected_segment_count": self.expected_segment_count,
                "feature_count": self.feature_count,
                "processing_ms_count": self.processing_ms_count,
                "silent_ratio_count": self.silent_ratio_count,
                "final_silent_ratio": self.final_silent_ratio,
                "silent_segments": self.silent_segments,
            },
            separators=(",", ":"),
            sort_keys=True,
        )


def _consume_topic(
    topic: str,
    *,
    timeout_s: float = 30.0,
    idle_timeout_s: float = 3.0,
) -> list[dict[str, object]]:
    """Consume all currently visible messages from one topic until the topic goes idle."""

    from confluent_kafka import KafkaError, KafkaException

    settings = IngestionSettings.from_env()
    consumer = build_consumer(
        bootstrap_servers=settings.base.kafka_bootstrap_servers,
        group_id=f"processing-smoke-{topic}-{uuid4().hex}",
        client_id=f"processing-smoke-{topic}",
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


def _filter_processing_metric_messages(
    messages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return only the processing-owned metrics for the active run."""

    return [
        message
        for message in messages
        if message.get("envelope", {}).get("payload", {}).get("service_name") == "processing"
    ]


def _assert_feature_messages(
    messages: list[dict[str, object]],
    *,
    expected_segment_pairs: tuple[tuple[int, int], ...],
) -> list[dict[str, object]]:
    """Validate the emitted audio.features messages for the current run."""

    if len(messages) != len(expected_segment_pairs):
        raise RuntimeError(
            "Smoke audio.features count drifted from the selected segment-ready input count. "
            f"Expected {len(expected_segment_pairs)} observed {len(messages)}."
        )

    observed_segment_pairs = {
        (
            int(message["envelope"]["payload"]["track_id"]),
            int(message["envelope"]["payload"]["segment_idx"]),
        )
        for message in messages
    }
    if observed_segment_pairs != set(expected_segment_pairs):
        raise RuntimeError(
            "Smoke audio.features messages did not contain the expected logical segments. "
            f"Observed: {sorted(observed_segment_pairs)}."
        )

    for message in messages:
        envelope = message["envelope"]
        payload = validate_envelope_dict(envelope, expected_event_type=AUDIO_FEATURES)
        track_id = int(payload["track_id"])
        if message["key"] != str(track_id):
            raise RuntimeError("Smoke audio.features events must stay keyed by track_id.")
        if int(payload["mel_bins"]) != 128 or int(payload["mel_frames"]) != 300:
            raise RuntimeError("Smoke audio.features messages drifted from the locked log-mel shape.")
        if float(payload["processing_ms"]) < 0.0:
            raise RuntimeError("Smoke audio.features processing_ms must stay non-negative.")

    return messages


def _assert_processing_metrics(
    messages: list[dict[str, object]],
    *,
    feature_messages: list[dict[str, object]],
) -> tuple[int, int, float, int]:
    """Validate the processing-owned system.metrics envelopes for the current run."""

    expected_segment_count = len(feature_messages)
    processing_ms_messages = [
        message
        for message in messages
        if message["envelope"]["payload"]["metric_name"] == "processing_ms"
    ]
    silent_ratio_messages = [
        message
        for message in messages
        if message["envelope"]["payload"]["metric_name"] == "silent_ratio"
    ]
    feature_error_messages = [
        message
        for message in messages
        if message["envelope"]["payload"]["metric_name"] == "feature_errors"
    ]

    metric_names = {
        str(message["envelope"]["payload"]["metric_name"])
        for message in messages
    }
    if metric_names - (EXPECTED_PROCESSING_EVENT_METRICS | {"feature_errors"}):
        raise RuntimeError(
            "Smoke processing metrics contained unexpected metric names. "
            f"Observed: {sorted(metric_names)}."
        )
    if feature_error_messages:
        raise RuntimeError("Healthy processing smoke runs must not emit feature_errors metrics.")
    if len(processing_ms_messages) != expected_segment_count:
        raise RuntimeError(
            "Smoke processing_ms metric count drifted from audio.features count. "
            f"Expected {expected_segment_count} observed {len(processing_ms_messages)}."
        )
    if len(silent_ratio_messages) != expected_segment_count:
        raise RuntimeError(
            "Smoke silent_ratio metric count drifted from audio.features count. "
            f"Expected {expected_segment_count} observed {len(silent_ratio_messages)}."
        )
    if expected_segment_count == 0:
        return (0, 0, 0.0, 0)

    feature_processing_ms = sorted(
        round(float(message["envelope"]["payload"]["processing_ms"]), 6)
        for message in feature_messages
    )
    metric_processing_ms = sorted(
        round(float(message["envelope"]["payload"]["metric_value"]), 6)
        for message in processing_ms_messages
    )
    if feature_processing_ms != metric_processing_ms:
        raise RuntimeError(
            "Smoke processing_ms metrics drifted from the emitted audio.features summaries."
        )

    silent_segments = 0
    for message in feature_messages:
        payload = message["envelope"]["payload"]
        if bool(payload["silent_flag"]):
            silent_segments += 1

    expected_final_silent_ratio = (
        silent_segments / float(expected_segment_count)
        if expected_segment_count
        else 0.0
    )
    latest_silent_ratio_message = max(
        silent_ratio_messages,
        key=lambda message: str(message["envelope"]["payload"]["ts"]),
    )
    latest_silent_ratio = float(latest_silent_ratio_message["envelope"]["payload"]["metric_value"])

    for message in processing_ms_messages:
        payload = validate_envelope_dict(message["envelope"], expected_event_type=SYSTEM_METRICS)
        if message["key"] != "processing":
            raise RuntimeError("Smoke processing metrics must stay keyed by service_name=processing.")
        if payload["service_name"] != "processing":
            raise RuntimeError("Smoke processing metrics must expose service_name=processing.")
        labels_json = payload.get("labels_json", {})
        if labels_json != {"topic": "audio.features", "status": "ok"}:
            raise RuntimeError("Smoke processing_ms metrics drifted from the locked labels_json.")
        if payload.get("unit") != "ms":
            raise RuntimeError("Smoke processing_ms metrics must expose unit=ms.")

    for message in silent_ratio_messages:
        payload = validate_envelope_dict(message["envelope"], expected_event_type=SYSTEM_METRICS)
        if message["key"] != "processing":
            raise RuntimeError("Smoke processing metrics must stay keyed by service_name=processing.")
        if payload["service_name"] != "processing":
            raise RuntimeError("Smoke processing metrics must expose service_name=processing.")
        labels_json = payload.get("labels_json", {})
        if labels_json != {"scope": "run_total"}:
            raise RuntimeError("Smoke silent_ratio metrics must stay scoped as run_total snapshots.")
        if payload.get("unit") != "ratio":
            raise RuntimeError("Smoke silent_ratio metrics must expose unit=ratio.")

    if round(latest_silent_ratio, 6) != round(expected_final_silent_ratio, 6):
        raise RuntimeError(
            "Smoke silent_ratio final snapshot drifted from the emitted audio.features silent flags."
        )

    return (
        len(processing_ms_messages),
        len(silent_ratio_messages),
        latest_silent_ratio,
        silent_segments,
    )


def main() -> None:
    """Verify the bounded processing smoke path and print a compact summary."""

    settings = IngestionSettings.from_env()
    expectation = _derive_smoke_expectation(settings)
    feature_messages = _filter_messages_for_run(
        _consume_topic(AUDIO_FEATURES),
        run_id=settings.base.run_id,
    )
    processing_metric_messages = _filter_processing_metric_messages(
        _filter_messages_for_run(
            _consume_topic(SYSTEM_METRICS),
            run_id=settings.base.run_id,
        )
    )

    validated_feature_messages = _assert_feature_messages(
        feature_messages,
        expected_segment_pairs=expectation.segment_pairs,
    )
    processing_ms_count, silent_ratio_count, final_silent_ratio, silent_segments = (
        _assert_processing_metrics(
            processing_metric_messages,
            feature_messages=validated_feature_messages,
        )
    )

    print(
        ProcessingSmokeSummary(
            run_id=settings.base.run_id,
            expected_segment_count=len(expectation.segment_pairs),
            feature_count=len(validated_feature_messages),
            processing_ms_count=processing_ms_count,
            silent_ratio_count=silent_ratio_count,
            final_silent_ratio=final_silent_ratio,
            silent_segments=silent_segments,
        ).to_json()
    )


if __name__ == "__main__":
    main()
