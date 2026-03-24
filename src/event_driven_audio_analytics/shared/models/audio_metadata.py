"""Payload model for the audio.metadata topic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AudioMetadataPayload:
    """Metadata needed by downstream persistence and dashboards."""

    run_id: str
    track_id: int
    artist_id: int
    genre: str
    subset: str
    source_audio_uri: str
    validation_status: str
    manifest_uri: str | None = None
    checksum: str | None = None
