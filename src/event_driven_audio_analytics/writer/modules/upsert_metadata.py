"""Track-metadata persistence helpers for the writer service."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from event_driven_audio_analytics.shared.models.audio_metadata import AudioMetadataPayload

if TYPE_CHECKING:
    from psycopg import Cursor
else:
    Cursor = Any


TRACK_METADATA_UPSERT = """
INSERT INTO track_metadata (
    run_id,
    track_id,
    artist_id,
    genre,
    subset,
    source_audio_uri,
    validation_status,
    duration_s,
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
    %(duration_s)s,
    %(manifest_uri)s,
    %(checksum)s
)
ON CONFLICT (run_id, track_id) DO UPDATE SET
    artist_id = EXCLUDED.artist_id,
    genre = EXCLUDED.genre,
    subset = EXCLUDED.subset,
    source_audio_uri = EXCLUDED.source_audio_uri,
    validation_status = EXCLUDED.validation_status,
    duration_s = EXCLUDED.duration_s,
    manifest_uri = EXCLUDED.manifest_uri,
    checksum = EXCLUDED.checksum;
""".strip()


def persist_track_metadata(cursor: Cursor, payload: AudioMetadataPayload) -> int:
    """Upsert one track metadata record."""

    cursor.execute(TRACK_METADATA_UPSERT, asdict(payload))
    return cursor.rowcount
