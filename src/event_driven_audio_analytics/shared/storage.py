"""Shared claim-check storage helpers."""

from __future__ import annotations

from pathlib import Path


def validate_run_id(run_id: str) -> str:
    """Validate a run id before using it in events, DB rows, or artifact paths."""

    normalized = run_id.strip()
    if normalized == "":
        raise ValueError("run_id must not be empty or whitespace.")
    if normalized in {".", ".."} or any(
        character in normalized for character in ("/", "\\", ":")
    ) or any(
        character.isspace() for character in run_id
    ):
        raise ValueError("run_id must be a single relative path segment without whitespace.")
    return normalized


def _as_uri(path: Path) -> str:
    """Normalize a filesystem path into a portable path-like URI string."""

    return path.as_posix()


def run_root(artifacts_root: Path, run_id: str) -> Path:
    """Return the shared storage root for a run."""

    return artifacts_root / "runs" / validate_run_id(run_id)


def resolve_artifact_uri(artifacts_root: Path, artifact_uri: str) -> Path:
    """Resolve a claim-check URI while enforcing the configured artifacts boundary."""

    if not artifact_uri.strip():
        raise ValueError("artifact_uri must not be empty or whitespace.")

    root = artifacts_root.resolve()
    candidate = Path(artifact_uri)
    candidates = [candidate] if candidate.is_absolute() else [candidate, root / candidate]
    resolved_candidates: list[Path] = []
    for candidate_path in candidates:
        resolved = candidate_path.resolve()
        resolved_candidates.append(resolved)
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved

    rendered_candidates = ", ".join(path.as_posix() for path in resolved_candidates)
    raise ValueError(
        "artifact_uri must resolve within the configured artifacts_root "
        f"root={root.as_posix()} candidates={rendered_candidates}."
    )


def segment_artifact_uri(artifacts_root: Path, run_id: str, track_id: int, segment_idx: int) -> str:
    """Build the canonical artifact URI for a segment."""

    return _as_uri(
        run_root(artifacts_root, run_id) / "segments" / str(track_id) / f"{segment_idx}.wav"
    )


def manifest_uri(artifacts_root: Path, run_id: str) -> str:
    """Build the canonical manifest URI for a run."""

    return _as_uri(run_root(artifacts_root, run_id) / "manifests" / "segments.parquet")
