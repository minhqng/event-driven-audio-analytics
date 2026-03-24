"""Shared claim-check storage helpers."""

from __future__ import annotations

from pathlib import Path


def run_root(artifacts_root: Path, run_id: str) -> Path:
    """Return the shared storage root for a run."""

    return artifacts_root / "runs" / run_id


def segment_artifact_uri(artifacts_root: Path, run_id: str, track_id: int, segment_idx: int) -> str:
    """Build a placeholder artifact URI for a segment."""

    return str(run_root(artifacts_root, run_id) / "segments" / str(track_id) / f"{segment_idx}.wav")


def manifest_uri(artifacts_root: Path, run_id: str) -> str:
    """Build a placeholder manifest URI for a run."""

    return str(run_root(artifacts_root, run_id) / "manifests" / "segments.parquet")
