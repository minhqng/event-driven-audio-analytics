"""Persistence placeholders for idempotent writer behavior."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from psycopg import Cursor
from psycopg.types.json import Jsonb

from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_FEATURES,
    AUDIO_METADATA,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.shared.db import acquire_transaction_advisory_lock
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload
from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload
from event_driven_audio_analytics.shared.models.system_metrics import SystemMetricsPayload


AUDIO_FEATURES_LOGICAL_KEY = ("run_id", "track_id", "segment_idx")


@dataclass(slots=True)
class PersistenceResult:
    """Summarize placeholder persistence work."""

    rows_written: int
    checkpoints_ready: bool


TRACK_METADATA_UPSERT = """
INSERT INTO track_metadata (
    run_id,
    track_id,
    artist_id,
    genre,
    subset,
    source_audio_uri,
    validation_status,
    manifest_uri,
    checksum
)
VALUES (
    %(run_id)s,
    %(track_id)s,
    %(artist_id)s,
    %(genre)s,
    %(subset)s,
    %(source_audio_uri)s,
    %(validation_status)s,
    %(manifest_uri)s,
    %(checksum)s
)
ON CONFLICT (run_id, track_id) DO UPDATE SET
    artist_id = EXCLUDED.artist_id,
    genre = EXCLUDED.genre,
    subset = EXCLUDED.subset,
    source_audio_uri = EXCLUDED.source_audio_uri,
    validation_status = EXCLUDED.validation_status,
    manifest_uri = EXCLUDED.manifest_uri,
    checksum = EXCLUDED.checksum;
""".strip()


AUDIO_FEATURES_UPSERT = """
UPDATE audio_features
SET
    artifact_uri = %(artifact_uri)s,
    checksum = %(checksum)s,
    manifest_uri = %(manifest_uri)s,
    rms = %(rms)s,
    silent_flag = %(silent_flag)s,
    mel_bins = %(mel_bins)s,
    mel_frames = %(mel_frames)s,
    processing_ms = %(processing_ms)s
WHERE run_id = %(run_id)s
  AND track_id = %(track_id)s
  AND segment_idx = %(segment_idx)s
RETURNING 1;
""".strip()


AUDIO_FEATURES_INSERT = """
INSERT INTO audio_features (
    ts,
    run_id,
    track_id,
    segment_idx,
    artifact_uri,
    checksum,
    manifest_uri,
    rms,
    silent_flag,
    mel_bins,
    mel_frames,
    processing_ms
)
VALUES (
    %(ts)s,
    %(run_id)s,
    %(track_id)s,
    %(segment_idx)s,
    %(artifact_uri)s,
    %(checksum)s,
    %(manifest_uri)s,
    %(rms)s,
    %(silent_flag)s,
    %(mel_bins)s,
    %(mel_frames)s,
    %(processing_ms)s
);
""".strip()


SYSTEM_METRICS_INSERT = """
INSERT INTO system_metrics (
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    labels_json
)
VALUES (
    %(ts)s,
    %(run_id)s,
    %(service_name)s,
    %(metric_name)s,
    %(metric_value)s,
    %(labels_json)s
);
""".strip()


def persist_track_metadata(cursor: Cursor, payload: AudioMetadataPayload) -> int:
    """Upsert one track metadata record."""

    cursor.execute(TRACK_METADATA_UPSERT, asdict(payload))
    return cursor.rowcount


def persist_audio_features(cursor: Cursor, payload: AudioFeaturesPayload) -> int:
    """Update or insert one feature record using the natural key under advisory lock."""

    params = asdict(payload)
    acquire_transaction_advisory_lock(
        cursor,
        payload.run_id,
        payload.track_id,
        payload.segment_idx,
    )
    cursor.execute(AUDIO_FEATURES_UPSERT, params)
    matches = cursor.fetchall()
    if len(matches) > 1:
        raise ValueError(
            "audio_features natural key lookup matched multiple rows for "
            f"({payload.run_id}, {payload.track_id}, {payload.segment_idx})."
        )
    if len(matches) == 1:
        return 1

    cursor.execute(AUDIO_FEATURES_INSERT, params)
    return cursor.rowcount


def persist_system_metrics(cursor: Cursor, payload: SystemMetricsPayload) -> int:
    """Append one operational metrics record."""

    params = asdict(payload)
    params["labels_json"] = Jsonb(payload.labels_json)
    cursor.execute(SYSTEM_METRICS_INSERT, params)
    return cursor.rowcount


def persist_envelope_payload(
    cursor: Cursor,
    topic: str,
    payload_data: dict[str, object],
) -> int:
    """Persist one decoded envelope payload based on the Kafka topic."""

    if topic == AUDIO_METADATA:
        return persist_track_metadata(cursor, AudioMetadataPayload(**payload_data))
    if topic == AUDIO_FEATURES:
        return persist_audio_features(cursor, AudioFeaturesPayload(**payload_data))
    if topic == SYSTEM_METRICS:
        return persist_system_metrics(cursor, SystemMetricsPayload(**payload_data))

    raise ValueError(f"Writer does not persist topic {topic}.")
