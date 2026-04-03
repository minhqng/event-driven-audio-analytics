"""Week 3 ingestion pipeline from real audio input to claim-check events."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from time import perf_counter
from typing import Any

from event_driven_audio_analytics.ingestion.modules.artifact_writer import SegmentDescriptor, write_segment_artifacts
from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_NO_SEGMENTS,
    VALIDATION_STATUS_VALIDATED,
    ValidationResult,
    validate_audio_record,
)
from event_driven_audio_analytics.ingestion.modules.metadata_loader import MetadataRecord, load_small_subset_metadata
from event_driven_audio_analytics.ingestion.modules.metrics import IngestionRunMetrics
from event_driven_audio_analytics.ingestion.modules.publisher import (
    ProducerLike,
    publish_metadata_event,
    publish_segment_ready_event,
    publish_system_metric_event,
)
from event_driven_audio_analytics.ingestion.modules.segmenter import segment_audio
from .config import IngestionSettings
from event_driven_audio_analytics.shared.kafka import build_producer
from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.models.envelope import EventEnvelope


@dataclass(slots=True)
class TrackIngestionResult:
    """Materialized output for one ingested track."""

    record: MetadataRecord
    validation: ValidationResult
    metadata_event: EventEnvelope[AudioMetadataPayload]
    segment_descriptors: list[SegmentDescriptor]
    segment_events: list[EventEnvelope[AudioSegmentReadyPayload]]
    artifact_write_ms: float


@dataclass(slots=True)
class IngestionPipeline:
    """Run the Week 3 ingestion path from metadata ETL to event emission."""

    settings: IngestionSettings

    def describe(self) -> list[str]:
        return [
            "load metadata for subset=small",
            "validate audio paths and decode readiness",
            "segment audio into 3.0-second windows with 1.5-second overlap",
            "write artifacts and manifests to shared storage",
            "publish audio.metadata and audio.segment.ready events",
        ]

    def load_metadata_records(self) -> list[MetadataRecord]:
        """Load normalized metadata rows for the configured sample set."""

        return load_small_subset_metadata(
            self.settings.metadata_csv_path,
            audio_root_path=self.settings.audio_root_path,
            subset=self.settings.subset,
            track_id_allowlist=self.settings.track_id_allowlist,
            max_tracks=self.settings.max_tracks,
        )

    def _build_metadata_payload(
        self,
        record: MetadataRecord,
        validation: ValidationResult,
        *,
        manifest_uri_value: str | None = None,
    ) -> AudioMetadataPayload:
        """Build the canonical audio.metadata payload for one track."""

        duration_s = validation.duration_s
        if duration_s is None or duration_s <= 0.0:
            duration_s = record.declared_duration_s
        if duration_s is None or duration_s <= 0.0:
            raise ValueError(
                "audio.metadata requires a positive duration_s for "
                f"track_id={record.track_id}, but neither validation nor metadata ETL "
                "produced one."
            )

        payload_kwargs: dict[str, Any] = {
            "run_id": self.settings.base.run_id,
            "track_id": record.track_id,
            "artist_id": record.artist_id,
            "genre": record.genre_label,
            "source_audio_uri": record.source_audio_uri,
            "validation_status": validation.validation_status,
            "duration_s": duration_s,
            "subset": record.subset,
            "checksum": validation.checksum,
        }
        if manifest_uri_value is not None:
            payload_kwargs["manifest_uri"] = manifest_uri_value
        return AudioMetadataPayload(**payload_kwargs)

    def process_record(
        self,
        producer: ProducerLike,
        record: MetadataRecord,
    ) -> TrackIngestionResult:
        """Validate, segment, persist, and publish one track."""

        logger = logging.getLogger(self.settings.base.service_name)
        validation = validate_audio_record(
            record,
            target_sample_rate_hz=self.settings.target_sample_rate_hz,
            min_duration_s=self.settings.min_duration_s,
            silence_threshold_db=self.settings.silence_threshold_db,
        )
        if validation.validation_status != VALIDATION_STATUS_VALIDATED or validation.decoded_audio is None:
            metadata_event = publish_metadata_event(
                producer,
                self._build_metadata_payload(record, validation),
                delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
            )
            logger.info(
                "Published metadata only track_id=%s metadata_topic=audio.metadata validation_status=%s",
                record.track_id,
                validation.validation_status,
            )
            return TrackIngestionResult(
                record=record,
                validation=validation,
                metadata_event=metadata_event,
                segment_descriptors=[],
                segment_events=[],
                artifact_write_ms=0.0,
            )

        segments = segment_audio(
            run_id=self.settings.base.run_id,
            track_id=record.track_id,
            waveform=validation.decoded_audio.waveform,
            sample_rate_hz=validation.decoded_audio.sample_rate_hz,
            segment_duration_s=self.settings.segment_duration_s,
            segment_overlap_s=self.settings.segment_overlap_s,
        )
        if not segments:
            validation = replace(
                validation,
                validation_status=VALIDATION_STATUS_NO_SEGMENTS,
                validation_error=(
                    "Decoded audio passed validation but did not yield any legal "
                    "3.0-second segments under the legacy tail-padding rule."
                ),
            )
            metadata_event = publish_metadata_event(
                producer,
                self._build_metadata_payload(record, validation),
                delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
            )
            logger.info(
                "Published metadata only track_id=%s metadata_topic=audio.metadata validation_status=%s",
                record.track_id,
                validation.validation_status,
            )
            return TrackIngestionResult(
                record=record,
                validation=validation,
                metadata_event=metadata_event,
                segment_descriptors=[],
                segment_events=[],
                artifact_write_ms=0.0,
            )

        artifact_write_started = perf_counter()
        segment_descriptors = write_segment_artifacts(
            self.settings.base.artifacts_root,
            segments,
        )
        artifact_write_ms = (perf_counter() - artifact_write_started) * 1000.0
        if not segment_descriptors:
            raise RuntimeError("Artifact writer returned no descriptors for a non-empty segment batch.")

        metadata_event = publish_metadata_event(
            producer,
            self._build_metadata_payload(
                record,
                validation,
                manifest_uri_value=segment_descriptors[0].manifest_uri,
            ),
            delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
        )
        segment_events = [
            publish_segment_ready_event(
                producer,
                AudioSegmentReadyPayload(
                    run_id=descriptor.run_id,
                    track_id=descriptor.track_id,
                    segment_idx=descriptor.segment_idx,
                    artifact_uri=descriptor.artifact_uri,
                    checksum=descriptor.checksum,
                    sample_rate=descriptor.sample_rate,
                    duration_s=descriptor.duration_s,
                    is_last_segment=descriptor.is_last_segment,
                    manifest_uri=descriptor.manifest_uri,
                ),
                delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
            )
            for descriptor in segment_descriptors
        ]
        logger.info(
            "Published track events track_id=%s metadata_topic=audio.metadata segment_topic=audio.segment.ready segments=%s artifact_write_ms=%.3f",
            record.track_id,
            len(segment_events),
            artifact_write_ms,
        )

        return TrackIngestionResult(
            record=record,
            validation=validation,
            metadata_event=metadata_event,
            segment_descriptors=segment_descriptors,
            segment_events=segment_events,
            artifact_write_ms=artifact_write_ms,
        )

    def run(self, producer: ProducerLike | None = None) -> list[TrackIngestionResult]:
        """Execute the Week 3 ingestion path for the configured sample set."""

        own_producer = producer is None
        logger = logging.getLogger(self.settings.base.service_name)
        active_producer = producer or build_producer(
            bootstrap_servers=self.settings.base.kafka_bootstrap_servers,
            client_id=f"{self.settings.base.service_name}-producer",
            retries=self.settings.producer_retries,
            retry_backoff_ms=self.settings.producer_retry_backoff_ms,
            retry_backoff_max_ms=self.settings.producer_retry_backoff_max_ms,
            delivery_timeout_ms=self.settings.producer_delivery_timeout_ms,
        )

        try:
            metrics = IngestionRunMetrics()
            results: list[TrackIngestionResult] = []
            for record in self.load_metadata_records():
                result = self.process_record(active_producer, record)
                metrics.record_track(
                    segment_count=len(result.segment_events),
                    validation_failed=result.validation.validation_status != VALIDATION_STATUS_VALIDATED,
                    artifact_write_ms=result.artifact_write_ms,
                )
                results.append(result)

            for payload in metrics.as_payloads(
                run_id=self.settings.base.run_id,
                service_name=self.settings.base.service_name,
            ):
                publish_system_metric_event(
                    active_producer,
                    payload,
                    delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
                )

            remaining_messages = active_producer.flush()
            if remaining_messages not in (0, None):
                raise RuntimeError(
                    "Ingestion finished with undelivered Kafka messages still queued."
                )
            logger.info(
                "Ingestion run complete tracks_total=%s segments_total=%s validation_failures=%s artifact_write_ms=%.3f",
                metrics.tracks_total,
                metrics.segments_total,
                metrics.validation_failures,
                metrics.artifact_write_ms,
            )
            return results
        finally:
            if own_producer:
                active_producer.flush()
