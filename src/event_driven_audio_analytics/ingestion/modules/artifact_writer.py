"""Claim-check artifact writing placeholders."""

from __future__ import annotations

from pathlib import Path

from .segmenter import SegmentDescriptor


def ensure_artifact_layout(artifacts_root: Path, run_id: str) -> tuple[Path, Path]:
    """Return segment and manifest directories for a run."""

    segments_dir = artifacts_root / "runs" / run_id / "segments"
    manifests_dir = artifacts_root / "runs" / run_id / "manifests"
    return segments_dir, manifests_dir


def write_segment_artifact(segment: SegmentDescriptor) -> SegmentDescriptor:
    """Return the descriptor unchanged until artifact persistence is implemented."""

    # TODO: write segment artifacts and manifests to shared storage.
    return segment
