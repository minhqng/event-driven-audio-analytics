"""Feature-row upsert helpers for the writer service."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from event_driven_audio_analytics.shared.db import acquire_transaction_advisory_lock
from event_driven_audio_analytics.shared.models.audio_features import AudioFeaturesPayload

if TYPE_CHECKING:
    from psycopg import Cursor
else:
    Cursor = Any


class AudioFeaturesNaturalKeyError(RuntimeError):
    """Raised when the logical feature identity resolves ambiguously in the sink."""

    pass


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


def persist_audio_features(cursor: Cursor, payload: AudioFeaturesPayload) -> int:
    """Update or insert one feature row using the natural key under advisory lock."""

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
        raise AudioFeaturesNaturalKeyError(
            "audio_features natural key lookup matched multiple rows for "
            f"({payload.run_id}, {payload.track_id}, {payload.segment_idx})."
        )
    if len(matches) == 1:
        return 1

    cursor.execute(AUDIO_FEATURES_INSERT, params)
    return cursor.rowcount
