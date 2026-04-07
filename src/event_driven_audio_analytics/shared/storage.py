"""Shared claim-check storage helpers."""

from __future__ import annotations

from pathlib import Path


def _as_uri(path: Path) -> str:
    """Normalize a filesystem path into a portable path-like URI string."""

    return path.as_posix()


def run_root(artifacts_root: Path, run_id: str) -> Path:
    """Return the shared storage root for a run."""

    return artifacts_root / "runs" / run_id


def segment_artifact_uri(artifacts_root: Path, run_id: str, track_id: int, segment_idx: int) -> str:
    """Build the canonical artifact URI for a segment."""

    return _as_uri(
        run_root(artifacts_root, run_id) / "segments" / str(track_id) / f"{segment_idx}.wav"
    )


def manifest_uri(artifacts_root: Path, run_id: str) -> str:
    """Build the canonical manifest URI for a run."""

    return _as_uri(run_root(artifacts_root, run_id) / "manifests" / "segments.parquet")
