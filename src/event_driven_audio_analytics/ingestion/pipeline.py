"""Week 3 ingestion pipeline from real audio input to claim-check events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from event_driven_audio_analytics.ingestion.modules.artifact_writer import SegmentDescriptor, write_segment_artifacts
from event_driven_audio_analytics.ingestion.modules.audio_validator import (
    VALIDATION_STATUS_VALIDATED,
    ValidationResult,
    validate_audio_record,
)
from event_driven_audio_analytics.ingestion.modules.metadata_loader import MetadataRecord, load_small_subset_metadata
from event_driven_audio_analytics.ingestion.modules.publisher import (
    ProducerLike,
    publish_metadata_event,
    publish_segment_ready_event,
)
from event_driven_audio_analytics.ingestion.modules.segmenter import segment_audio
from .config import IngestionSettings
from event_driven_audio_analytics.shared.kafka import build_producer
from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload
from event_driven_audio_analytics.shared.models.audio_segment_ready import AudioSegmentReadyPayload
from event_driven_audio_analytics.shared.models.envelope import EventEnvelope
from event_driven_audio_analytics.shared.storage import manifest_uri


@dataclass(slots=True)
class TrackIngestionResult:
    """Materialized output for one ingested track."""

    record: MetadataRecord
    validation: ValidationResult
    metadata_event: EventEnvelope[AudioMetadataPayload]
    segment_descriptors: list[SegmentDescriptor]
    segment_events: list[EventEnvelope[AudioSegmentReadyPayload]]


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
    ) -> AudioMetadataPayload:
        """Build the canonical audio.metadata payload for one track."""

        payload_kwargs: dict[str, Any] = {
            "run_id": self.settings.base.run_id,
            "track_id": record.track_id,
            "artist_id": record.artist_id,
            "genre": record.genre_label,
            "source_audio_uri": record.source_audio_uri,
            "validation_status": validation.validation_status,
            "duration_s": validation.duration_s or 0.0,
            "subset": record.subset,
            "checksum": validation.checksum,
        }
        if validation.validation_status == VALIDATION_STATUS_VALIDATED:
            payload_kwargs["manifest_uri"] = manifest_uri(
                self.settings.base.artifacts_root,
                self.settings.base.run_id,
            )
        return AudioMetadataPayload(**payload_kwargs)

    def process_record(
        self,
        producer: ProducerLike,
        record: MetadataRecord,
    ) -> TrackIngestionResult:
        """Validate, segment, persist, and publish one track."""

        validation = validate_audio_record(
            record,
            target_sample_rate_hz=self.settings.target_sample_rate_hz,
            min_duration_s=self.settings.min_duration_s,
            silence_threshold_db=self.settings.silence_threshold_db,
        )
        metadata_event = publish_metadata_event(
            producer,
            self._build_metadata_payload(record, validation),
        )

        if validation.validation_status != VALIDATION_STATUS_VALIDATED or validation.decoded_audio is None:
            return TrackIngestionResult(
                record=record,
                validation=validation,
                metadata_event=metadata_event,
                segment_descriptors=[],
                segment_events=[],
            )

        segments = segment_audio(
            run_id=self.settings.base.run_id,
            track_id=record.track_id,
            waveform=validation.decoded_audio.waveform,
            sample_rate_hz=validation.decoded_audio.sample_rate_hz,
            segment_duration_s=self.settings.segment_duration_s,
            segment_overlap_s=self.settings.segment_overlap_s,
        )
        segment_descriptors = write_segment_artifacts(
            self.settings.base.artifacts_root,
            segments,
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
            )
            for descriptor in segment_descriptors
        ]

        return TrackIngestionResult(
            record=record,
            validation=validation,
            metadata_event=metadata_event,
            segment_descriptors=segment_descriptors,
            segment_events=segment_events,
        )

    def run(self, producer: ProducerLike | None = None) -> list[TrackIngestionResult]:
        """Execute the Week 3 ingestion path for the configured sample set."""

        own_producer = producer is None
        active_producer = producer or build_producer(
            bootstrap_servers=self.settings.base.kafka_bootstrap_servers,
            client_id=f"{self.settings.base.service_name}-producer",
        )

        try:
            results = [
                self.process_record(active_producer, record)
                for record in self.load_metadata_records()
            ]
            active_producer.flush()
            return results
        finally:
            if own_producer:
                active_producer.flush()
