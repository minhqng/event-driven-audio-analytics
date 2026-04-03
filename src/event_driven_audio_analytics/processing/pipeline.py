"""Week 5 processing pipeline from claim-check artifacts to audio.features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter, sleep
from typing import TYPE_CHECKING, Any

import torch

from event_driven_audio_analytics.processing.modules.artifact_loader import (
    ArtifactChecksumMismatch,
    ArtifactLoadError,
    LoadedSegmentArtifact,
    load_segment_artifact,
)
from event_driven_audio_analytics.processing.modules.log_mel import LogMelExtractor
from event_driven_audio_analytics.processing.modules.metrics import (
    ProcessingMetricsStateError,
    ProcessingRunMetrics,
    processing_metrics_state_path,
)
from event_driven_audio_analytics.processing.modules.publisher import (
    ProducerLike,
    publish_audio_features_event,
    publish_system_metric_event,
)
from event_driven_audio_analytics.processing.modules.rms import (
    RmsSummary,
    encode_rms_db_for_event,
    summarize_rms,
)
from event_driven_audio_analytics.processing.modules.runtime import check_runtime_dependencies
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
from event_driven_audio_analytics.shared.logging import ServiceLoggerAdapter, get_service_logger
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.models.envelope import (
    EventEnvelope,
    build_trace_id,
    validate_envelope_dict,
)
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload

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


@dataclass(slots=True)
class ProcessingFailureDecision:
    """Describe whether the current processing error can be retried safely."""

    failure_class: str
    retryable: bool


@dataclass(slots=True)
class ProcessingStageError(RuntimeError):
    """Describe one terminal processing-stage failure with a stable failure class."""

    failure_class: str
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(slots=True)
class FailureContext:
    """Structured context extracted from one consumed processing record."""

    run_id: str | None = None
    trace_id: str | None = None
    track_id: int | None = None
    segment_idx: int | None = None


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
    silent_ratio: float
    processing_ms: float
    welford_state: WelfordState
    welford_state_ref: str | None
    features_event: EventEnvelope[AudioFeaturesPayload]
    metric_events: tuple[EventEnvelope[SystemMetricsPayload], ...]


@dataclass(slots=True)
class ProcessingPipeline:
    """Run the Week 5 processing path from segment-ready events to feature summaries."""

    settings: ProcessingSettings
    _mel_extractor: LogMelExtractor = field(init=False, repr=False)
    _welford_state_by_run_id: dict[str, WelfordState] = field(init=False, repr=False)
    _run_metrics_by_run_id: dict[str, ProcessingRunMetrics] = field(init=False, repr=False)

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
        self._welford_state_by_run_id = {}
        self._run_metrics_by_run_id = {}

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

        return self.welford_state_for(self.settings.base.run_id)

    def welford_state_for(self, run_id: str) -> WelfordState:
        """Return the in-memory Welford tracker for one logical run."""

        return self._welford_state_by_run_id.setdefault(
            run_id,
            WelfordState(ref=build_welford_state_ref(run_id)),
        )

    @property
    def run_metrics(self) -> ProcessingRunMetrics:
        """Expose the current in-memory run metrics for tests and diagnostics."""

        return self.run_metrics_for(self.settings.base.run_id)

    def run_metrics_for(self, run_id: str) -> ProcessingRunMetrics:
        """Return the in-memory run metrics tracker for one logical run."""

        current_metrics = self._run_metrics_by_run_id.get(run_id)
        if current_metrics is not None:
            return current_metrics

        state_path = processing_metrics_state_path(self.settings.base.artifacts_root, run_id)
        recovered_metrics = ProcessingRunMetrics.from_state_file(state_path, run_id=run_id)
        self._run_metrics_by_run_id[run_id] = recovered_metrics
        return recovered_metrics

    def _service_trace_id(self) -> str:
        """Return the stable service-scoped trace id for processing logs and metrics."""

        return build_trace_id(
            {
                "run_id": self.settings.base.run_id,
                "service_name": self.settings.base.service_name,
            },
            source_service=self.settings.base.service_name,
        )

    def _validate_loaded_artifact(self, payload: AudioSegmentReadyPayload, artifact: LoadedSegmentArtifact) -> None:
        """Cross-check event metadata against the loaded claim-check artifact."""

        if artifact.sample_rate_hz != payload.sample_rate:
            raise ArtifactLoadError(
                "audio.segment.ready sample_rate does not match the claim-check artifact "
                f"expected={payload.sample_rate} actual={artifact.sample_rate_hz}"
            )

        max_duration_delta_s = 1.0 / float(payload.sample_rate)
        if abs(artifact.duration_s - payload.duration_s) > max_duration_delta_s:
            raise ArtifactLoadError(
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

    def _processing_delivery_timeout_s(self) -> float:
        """Return the shared producer delivery timeout in seconds."""

        return self.settings.producer_delivery_timeout_ms / 1000.0

    def _build_success_metric_payloads(
        self,
        *,
        run_id: str,
        processing_ms: float,
        run_metrics: ProcessingRunMetrics,
    ) -> tuple[SystemMetricsPayload, SystemMetricsPayload]:
        """Build the success-path processing metrics for one segment."""

        return run_metrics.build_success_payloads(
            run_id=run_id,
            service_name=self.settings.base.service_name,
            processing_ms=processing_ms,
        )

    def _publish_success_metrics(
        self,
        producer: ProducerLike,
        *,
        trace_id: str | None,
        metric_payloads: tuple[SystemMetricsPayload, SystemMetricsPayload],
    ) -> tuple[EventEnvelope[SystemMetricsPayload], ...]:
        """Publish the canonical success-path processing metrics."""

        try:
            return tuple(
                publish_system_metric_event(
                    producer,
                    payload,
                    trace_id=trace_id,
                    delivery_timeout_s=self._processing_delivery_timeout_s(),
                )
                for payload in metric_payloads
            )
        except Exception as exc:
            raise ProcessingStageError(
                failure_class="metric_publish_failed",
                reason="Processing failed while publishing system.metrics.",
            ) from exc

    def _build_failure_metric_payload(
        self,
        *,
        run_id: str,
        failure_class: str,
    ) -> SystemMetricsPayload:
        """Build the canonical terminal-failure metric."""

        return self.run_metrics_for(run_id).build_feature_error_payload(
            run_id=run_id,
            service_name=self.settings.base.service_name,
            failure_class=failure_class,
        )

    def _persist_run_metrics(
        self,
        *,
        run_id: str,
        run_metrics: ProcessingRunMetrics,
    ) -> None:
        """Persist replay-stable processing run metrics for restart recovery."""

        run_metrics.persist(
            state_path=processing_metrics_state_path(self.settings.base.artifacts_root, run_id),
            run_id=run_id,
        )

    def _emit_failure_metric(
        self,
        producer: ProducerLike,
        *,
        failure_context: FailureContext,
        failure_class: str,
        logger: ServiceLoggerAdapter,
    ) -> None:
        """Attempt to publish the canonical terminal-failure metric."""

        failure_run_id = failure_context.run_id or self.settings.base.run_id
        failure_trace_id = failure_context.trace_id or self._service_trace_id()
        try:
            publish_system_metric_event(
                producer,
                self._build_failure_metric_payload(
                    run_id=failure_run_id,
                    failure_class=failure_class,
                ),
                trace_id=failure_trace_id,
                delivery_timeout_s=self._processing_delivery_timeout_s(),
            )
        except Exception:
            logger.bind(
                metric_name="feature_errors",
                metric_value=1.0,
                failure_class=failure_class,
            ).exception("Processing failed to publish terminal failure metrics.")

    def _artifact_retry_backoff_s(self, attempt: int) -> float:
        """Return the bounded exponential backoff for retryable artifact failures."""

        delay_ms = min(
            self.settings.artifact_retry_backoff_ms * (2 ** max(attempt - 1, 0)),
            self.settings.artifact_retry_backoff_max_ms,
        )
        return delay_ms / 1000.0

    def _extract_failure_context(self, envelope: dict[str, object] | None) -> FailureContext:
        """Extract stable structured logging context from one decoded envelope."""

        context = FailureContext()
        if envelope is None:
            return context

        run_id = envelope.get("run_id")
        trace_id = envelope.get("trace_id")
        if isinstance(run_id, str) and run_id:
            context.run_id = run_id
        if isinstance(trace_id, str) and trace_id:
            context.trace_id = trace_id

        payload = envelope.get("payload")
        if isinstance(payload, dict):
            payload_run_id = payload.get("run_id")
            track_id = payload.get("track_id")
            segment_idx = payload.get("segment_idx")
            if context.run_id is None and isinstance(payload_run_id, str) and payload_run_id:
                context.run_id = payload_run_id
            if isinstance(track_id, int) and not isinstance(track_id, bool):
                context.track_id = track_id
            if isinstance(segment_idx, int) and not isinstance(segment_idx, bool):
                context.segment_idx = segment_idx
        return context

    def _bind_failure_context(
        self,
        logger: ServiceLoggerAdapter,
        failure_context: FailureContext,
    ) -> ServiceLoggerAdapter:
        """Attach run/trace/track/segment context to one service logger."""

        return logger.bind(
            run_id=failure_context.run_id,
            trace_id=failure_context.trace_id,
            track_id=failure_context.track_id,
            segment_idx=failure_context.segment_idx,
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
        try:
            artifact = load_segment_artifact(
                payload.artifact_uri,
                payload.checksum,
                expected_sample_rate_hz=self.settings.target_sample_rate_hz,
            )
            self._validate_loaded_artifact(payload, artifact)
        except (FileNotFoundError, ArtifactChecksumMismatch):
            raise
        except ArtifactLoadError:
            raise
        except Exception as exc:
            raise ProcessingStageError(
                failure_class="artifact_load_failed",
                reason="Processing failed while validating the claim-check artifact.",
            ) from exc

        try:
            rms_summary = summarize_rms(artifact.waveform)
            mel = self._mel_extractor.compute(artifact.waveform)
            silent_flag = is_silent_segment(
                mel,
                std_floor=self.settings.segment_silence_floor,
            )
            next_welford_state = update_welford(
                self.welford_state_for(payload.run_id),
                mel,
            )
        except Exception as exc:
            raise ProcessingStageError(
                failure_class="processing_failed",
                reason="Processing failed while computing feature summaries.",
            ) from exc

        processing_ms = (perf_counter() - started_at) * 1000.0
        try:
            current_run_metrics = self.run_metrics_for(payload.run_id)
            next_run_metrics = current_run_metrics.with_recorded_success(
                track_id=payload.track_id,
                segment_idx=payload.segment_idx,
                silent_flag=silent_flag,
            )
        except ProcessingMetricsStateError as exc:
            raise ProcessingStageError(
                failure_class="metrics_state_failed",
                reason="Processing failed while recovering replay-stable run metrics.",
            ) from exc

        metric_payloads = self._build_success_metric_payloads(
            run_id=payload.run_id,
            processing_ms=processing_ms,
            run_metrics=next_run_metrics,
        )
        silent_ratio = metric_payloads[1].metric_value

        try:
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
                delivery_timeout_s=self._processing_delivery_timeout_s(),
            )
        except Exception as exc:
            raise ProcessingStageError(
                failure_class="feature_publish_failed",
                reason="Processing failed while publishing audio.features.",
            ) from exc

        metric_events = self._publish_success_metrics(
            producer,
            trace_id=trace_id,
            metric_payloads=metric_payloads,
        )
        try:
            if next_run_metrics is not current_run_metrics:
                self._persist_run_metrics(
                    run_id=payload.run_id,
                    run_metrics=next_run_metrics,
                )
        except ProcessingMetricsStateError as exc:
            raise ProcessingStageError(
                failure_class="metrics_state_failed",
                reason="Processing failed while persisting replay-stable run metrics.",
            ) from exc

        self._welford_state_by_run_id[payload.run_id] = next_welford_state
        self._run_metrics_by_run_id[payload.run_id] = next_run_metrics
        return ProcessingResult(
            segment_ready=payload,
            loaded_artifact=artifact,
            rms_summary=rms_summary,
            mel=mel,
            silent_flag=silent_flag,
            silent_ratio=silent_ratio,
            processing_ms=processing_ms,
            welford_state=next_welford_state,
            welford_state_ref=next_welford_state.ref,
            features_event=features_event,
            metric_events=metric_events,
        )

    def process_event(
        self,
        producer: ProducerLike,
        envelope: dict[str, object],
    ) -> ProcessingResult:
        """Validate and process one decoded audio.segment.ready envelope."""

        try:
            payload_data = validate_envelope_dict(
                envelope,
                expected_event_type=AUDIO_SEGMENT_READY,
            )
            payload = AudioSegmentReadyPayload(**payload_data)
        except Exception as exc:
            raise ProcessingStageError(
                failure_class="envelope_invalid",
                reason="Processing failed while validating the audio.segment.ready envelope.",
            ) from exc
        return self.process_payload(
            producer,
            payload,
            trace_id=str(envelope["trace_id"]),
        )

    def _process_with_retry(
        self,
        producer: ProducerLike,
        envelope: dict[str, object],
        *,
        logger: ServiceLoggerAdapter,
    ) -> ProcessingResult:
        """Process one envelope with bounded retry for artifact readiness failures."""

        max_attempts = max(1, self.settings.artifact_retry_attempts)
        for attempt in range(1, max_attempts + 1):
            try:
                return self.process_event(producer, envelope)
            except Exception as exc:
                decision = classify_processing_failure(exc)
                if not decision.retryable or attempt >= max_attempts:
                    raise

                retry_delay_s = self._artifact_retry_backoff_s(attempt)
                logger.bind(
                    failure_class=decision.failure_class,
                    attempt=attempt,
                ).warning(
                    "Retrying processing after retryable artifact failure delay_s=%.3f reason=%s",
                    retry_delay_s,
                    exc,
                )
                sleep(retry_delay_s)

        raise RuntimeError("Processing retry loop exited without returning or raising.")

    def run(self, *, logger: ServiceLoggerAdapter | None = None) -> None:
        """Consume audio.segment.ready and publish audio.features until interrupted."""

        service_logger = logger or get_service_logger(
            self.settings.base.service_name,
            run_id=self.settings.base.run_id,
        )
        check_runtime_dependencies(self.settings)
        consumer = build_consumer(
            bootstrap_servers=self.settings.base.kafka_bootstrap_servers,
            group_id=self.settings.consumer_group,
            client_id=self.settings.base.service_name,
            topics=(AUDIO_SEGMENT_READY,),
            auto_offset_reset=self.settings.auto_offset_reset,
            enable_auto_commit=False,
            enable_auto_offset_store=False,
            session_timeout_ms=self.settings.session_timeout_ms,
            max_poll_interval_ms=self.settings.max_poll_interval_ms,
            retry_backoff_ms=self.settings.consumer_retry_backoff_ms,
            retry_backoff_max_ms=self.settings.consumer_retry_backoff_max_ms,
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
                    record = poll_record(consumer, timeout_s=self.settings.poll_timeout_s)
                except Exception:
                    service_logger.bind(failure_class="poll_failed").exception(
                        "Processing failed while polling Kafka."
                    )
                    continue

                if record is None:
                    continue

                raw_envelope: dict[str, object] | None = None
                record_logger = service_logger.bind(
                    topic=record.topic,
                    partition=record.partition,
                    offset=record.offset,
                )
                try:
                    raw_envelope = deserialize_envelope(record.value)
                    failure_context = self._extract_failure_context(raw_envelope)
                    record_logger = self._bind_failure_context(record_logger, failure_context)
                    result = self._process_with_retry(
                        producer,
                        raw_envelope,
                        logger=record_logger,
                    )
                except Exception as exc:
                    decision = classify_processing_failure(exc)
                    failure_context = self._extract_failure_context(raw_envelope)
                    failure_logger = self._bind_failure_context(record_logger, failure_context).bind(
                        failure_class=decision.failure_class,
                    )
                    self._emit_failure_metric(
                        producer,
                        failure_context=failure_context,
                        failure_class=decision.failure_class,
                        logger=failure_logger,
                    )
                    failure_logger.exception(
                        "Processing failed for the current record. "
                        "Leaving the record uncommitted and exiting because %s is reserved but not implemented yet.",
                        AUDIO_DLQ,
                    )
                    raise

                try:
                    consumer.commit(message=record.message, asynchronous=False)
                except Exception:
                    record_logger.bind(failure_class="offset_commit_failed").exception(
                        "Processing published outputs but failed to commit the Kafka offset. "
                        "Leaving the record uncommitted so the next restart can replay it safely."
                    )
                    raise

                record_logger.bind(
                    silent_flag=result.silent_flag,
                    metric_name="processing_ms",
                    metric_value=result.processing_ms,
                ).info(
                    "Published processing outputs topic=%s metrics=%s processing_ms=%.3f mel_shape=%s",
                    AUDIO_FEATURES,
                    ("processing_ms", "silent_ratio"),
                    result.processing_ms,
                    tuple(int(dimension) for dimension in result.mel.shape),
                )
        finally:
            producer.flush()
            consumer.close()


def classify_processing_failure(error: Exception) -> ProcessingFailureDecision:
    """Return the stable failure class and retry policy for one processing error."""

    if isinstance(error, ProcessingStageError):
        return ProcessingFailureDecision(
            failure_class=error.failure_class,
            retryable=False,
        )
    if isinstance(error, FileNotFoundError):
        return ProcessingFailureDecision(
            failure_class="artifact_not_ready",
            retryable=True,
        )
    if isinstance(error, ArtifactChecksumMismatch):
        return ProcessingFailureDecision(
            failure_class="checksum_mismatch",
            retryable=True,
        )
    if isinstance(error, ArtifactLoadError):
        return ProcessingFailureDecision(
            failure_class="artifact_load_failed",
            retryable=False,
        )
    if isinstance(error, ProcessingMetricsStateError):
        return ProcessingFailureDecision(
            failure_class="metrics_state_failed",
            retryable=False,
        )
    return ProcessingFailureDecision(
        failure_class="processing_failed",
        retryable=False,
    )
