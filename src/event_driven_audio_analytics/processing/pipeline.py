"""Week 5 processing pipeline from claim-check artifacts to audio.features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING, Any

import torch

from event_driven_audio_analytics.processing.modules.artifact_loader import (
    LoadedSegmentArtifact,
    load_segment_artifact,
)
from event_driven_audio_analytics.processing.modules.log_mel import LogMelExtractor
from event_driven_audio_analytics.processing.modules.publisher import (
    ProducerLike,
    publish_audio_features_event,
)
from event_driven_audio_analytics.processing.modules.rms import (
    RmsSummary,
    encode_rms_db_for_event,
    summarize_rms,
)
from event_driven_audio_analytics.processing.modules.silence_gate import is_silent_segment
from event_driven_audio_analytics.processing.modules.welford import (
    WelfordState,
    build_welford_state_ref,
    update_welford,
)
from .config import ProcessingSettings
from event_driven_audio_analytics.shared.contracts.topics import AUDIO_DLQ, AUDIO_FEATURES, AUDIO_SEGMENT_READY
from event_driven_audio_analytics.shared.kafka import (
    build_consumer,
    build_producer,
    deserialize_envelope,
)
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.models.envelope import EventEnvelope, validate_envelope_dict

if TYPE_CHECKING:
    from confluent_kafka import Consumer, Message
else:
    Consumer = Any
    Message = Any


def _utc_now_iso() -> str:
    """Return a compact UTC timestamp in RFC 3339 form."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class ConsumedRecord:
    """Minimal decoded Kafka metadata for the processing consumer loop."""

    topic: str
    partition: int
    offset: int
    value: bytes
    message: Message


def poll_record(consumer: Consumer, timeout_s: float = 1.0) -> ConsumedRecord | None:
    """Poll one Kafka record from the processing input topic."""

    from confluent_kafka import KafkaError, KafkaException

    message = consumer.poll(timeout_s)
    if message is None:
        return None

    if message.error() is not None:
        if message.error().code() in (
            KafkaError._PARTITION_EOF,
            KafkaError.UNKNOWN_TOPIC_OR_PART,
        ):
            return None
        raise KafkaException(message.error())

    return ConsumedRecord(
        topic=message.topic(),
        partition=message.partition(),
        offset=message.offset(),
        value=message.value() or b"",
        message=message,
    )


@dataclass(slots=True)
class ProcessingResult:
    """Materialized output for one processed segment event."""

    segment_ready: AudioSegmentReadyPayload
    loaded_artifact: LoadedSegmentArtifact
    rms_summary: RmsSummary
    mel: torch.Tensor
    silent_flag: bool
    processing_ms: float
    welford_state: WelfordState
    welford_state_ref: str | None
    features_event: EventEnvelope[AudioFeaturesPayload]


@dataclass(slots=True)
class ProcessingPipeline:
    """Run the Week 5 processing path from segment-ready events to feature summaries."""

    settings: ProcessingSettings
    _mel_extractor: LogMelExtractor = field(init=False, repr=False)
    _welford_state: WelfordState = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._mel_extractor = LogMelExtractor(
            sample_rate_hz=self.settings.target_sample_rate_hz,
            n_mels=self.settings.n_mels,
            n_fft=self.settings.n_fft,
            hop_length=self.settings.hop_length,
            target_frames=self.settings.target_frames,
            f_min=self.settings.f_min,
            f_max=self.settings.f_max,
            log_epsilon=self.settings.log_epsilon,
        )
        self._welford_state = WelfordState(ref=build_welford_state_ref(self.settings.base.run_id))

    def describe(self) -> list[str]:
        return [
            "consume audio.segment.ready events",
            "load artifacts using artifact_uri and checksum",
            "compute RMS, silence-gate decisions, and exact log-mel summaries",
            "update Welford-style monitoring statistics",
            "publish audio.features events from claim-check artifacts",
        ]

    @property
    def welford_state(self) -> WelfordState:
        """Expose the current in-memory Welford state for tests and diagnostics."""

        return self._welford_state

    def _validate_loaded_artifact(self, payload: AudioSegmentReadyPayload, artifact: LoadedSegmentArtifact) -> None:
        """Cross-check event metadata against the loaded claim-check artifact."""

        if artifact.sample_rate_hz != payload.sample_rate:
            raise ValueError(
                "audio.segment.ready sample_rate does not match the claim-check artifact "
                f"expected={payload.sample_rate} actual={artifact.sample_rate_hz}"
            )

        max_duration_delta_s = 1.0 / float(payload.sample_rate)
        if abs(artifact.duration_s - payload.duration_s) > max_duration_delta_s:
            raise ValueError(
                "audio.segment.ready duration_s does not match the claim-check artifact "
                f"expected={payload.duration_s} actual={artifact.duration_s}"
            )

    def _build_audio_features_payload(
        self,
        payload: AudioSegmentReadyPayload,
        *,
        rms_summary: RmsSummary,
        silent_flag: bool,
        mel: torch.Tensor,
        processing_ms: float,
    ) -> AudioFeaturesPayload:
        """Build the canonical audio.features payload for one segment."""

        return AudioFeaturesPayload(
            ts=_utc_now_iso(),
            run_id=payload.run_id,
            track_id=payload.track_id,
            segment_idx=payload.segment_idx,
            artifact_uri=payload.artifact_uri,
            checksum=payload.checksum,
            rms=encode_rms_db_for_event(
                rms_summary.rms_dbfs,
                floor_db=self.settings.silence_threshold_db,
            ),
            silent_flag=silent_flag,
            mel_bins=int(mel.shape[-2]),
            mel_frames=int(mel.shape[-1]),
            processing_ms=processing_ms,
            manifest_uri=payload.manifest_uri,
        )

    def process_payload(
        self,
        producer: ProducerLike,
        payload: AudioSegmentReadyPayload,
        *,
        trace_id: str | None = None,
    ) -> ProcessingResult:
        """Process one validated audio.segment.ready payload and publish audio.features."""

        if payload.sample_rate != self.settings.target_sample_rate_hz:
            raise ValueError(
                "audio.segment.ready sample_rate must match the locked processing target "
                f"expected={self.settings.target_sample_rate_hz} actual={payload.sample_rate}"
            )

        started_at = perf_counter()
        artifact = load_segment_artifact(
            payload.artifact_uri,
            payload.checksum,
            expected_sample_rate_hz=self.settings.target_sample_rate_hz,
        )
        self._validate_loaded_artifact(payload, artifact)
        rms_summary = summarize_rms(artifact.waveform)
        mel = self._mel_extractor.compute(artifact.waveform)
        silent_flag = is_silent_segment(
            mel,
            std_floor=self.settings.segment_silence_floor,
        )
        next_welford_state = update_welford(self._welford_state, mel)
        processing_ms = (perf_counter() - started_at) * 1000.0

        features_event = publish_audio_features_event(
            producer,
            self._build_audio_features_payload(
                payload,
                rms_summary=rms_summary,
                silent_flag=silent_flag,
                mel=mel,
                processing_ms=processing_ms,
            ),
            trace_id=trace_id,
            delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
        )
        self._welford_state = next_welford_state
        return ProcessingResult(
            segment_ready=payload,
            loaded_artifact=artifact,
            rms_summary=rms_summary,
            mel=mel,
            silent_flag=silent_flag,
            processing_ms=processing_ms,
            welford_state=next_welford_state,
            welford_state_ref=next_welford_state.ref,
            features_event=features_event,
        )

    def process_event(
        self,
        producer: ProducerLike,
        envelope: dict[str, object],
    ) -> ProcessingResult:
        """Validate and process one decoded audio.segment.ready envelope."""

        payload_data = validate_envelope_dict(
            envelope,
            expected_event_type=AUDIO_SEGMENT_READY,
        )
        payload = AudioSegmentReadyPayload(**payload_data)
        return self.process_payload(
            producer,
            payload,
            trace_id=str(envelope["trace_id"]),
        )

    def run(self) -> None:
        """Consume audio.segment.ready and publish audio.features until interrupted."""

        import logging

        logger = logging.getLogger(self.settings.base.service_name)
        consumer = build_consumer(
            bootstrap_servers=self.settings.base.kafka_bootstrap_servers,
            group_id=self.settings.consumer_group,
            client_id=self.settings.base.service_name,
            topics=(AUDIO_SEGMENT_READY,),
        )
        producer = build_producer(
            bootstrap_servers=self.settings.base.kafka_bootstrap_servers,
            client_id=f"{self.settings.base.service_name}-producer",
            retries=self.settings.producer_retries,
            retry_backoff_ms=self.settings.producer_retry_backoff_ms,
            retry_backoff_max_ms=self.settings.producer_retry_backoff_max_ms,
            delivery_timeout_ms=self.settings.producer_delivery_timeout_ms,
        )

        try:
            while True:
                try:
                    record = poll_record(consumer)
                except Exception:
                    logger.exception("Processing failed while polling Kafka.")
                    continue

                if record is None:
                    continue

                try:
                    result = self.process_event(producer, deserialize_envelope(record.value))
                    consumer.commit(message=record.message, asynchronous=False)
                    logger.info(
                        "Published %s for track_id=%s segment_idx=%s silent_flag=%s processing_ms=%.3f mel_shape=%s",
                        AUDIO_FEATURES,
                        result.segment_ready.track_id,
                        result.segment_ready.segment_idx,
                        result.silent_flag,
                        result.processing_ms,
                        tuple(int(dimension) for dimension in result.mel.shape),
                    )
                except Exception:
                    logger.exception(
                        "Processing failed for topic=%s partition=%s offset=%s. "
                        "Leaving the record uncommitted because %s is reserved but not implemented yet.",
                        record.topic,
                        record.partition,
                        record.offset,
                        AUDIO_DLQ,
                    )
        finally:
            producer.flush()
            consumer.close()
