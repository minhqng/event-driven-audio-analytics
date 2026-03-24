"""Metadata loading placeholders for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MetadataRecord:
    """Minimal metadata record carried into the replay pipeline."""

    track_id: int
    artist_id: int
    genre: str
    subset: str
    source_audio_uri: str


def load_small_subset_metadata(metadata_csv_path: str) -> list[MetadataRecord]:
    """Return placeholder metadata records for the FMA-small subset."""

    if not metadata_csv_path:
        raise ValueError("metadata_csv_path must not be empty")

    # TODO: implement flattened-header parsing and subset=small filtering.
    return []
