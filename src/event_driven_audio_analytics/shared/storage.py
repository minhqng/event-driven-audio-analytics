"""Shared claim-check storage helpers."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


LOGICAL_ARTIFACTS_ROOT = PurePosixPath("/artifacts")


def validate_run_id(run_id: str) -> str:
    """Validate a run id before using it in events, DB rows, or artifact paths."""

    normalized = run_id.strip()
    if normalized == "":
        raise ValueError("run_id must not be empty or whitespace.")
    if normalized in {".", ".."} or any(
        character in normalized for character in ("/", "\\", ":", ".")
    ) or any(
        character.isspace() for character in run_id
    ):
        raise ValueError(
            "run_id must be a single relative path segment without whitespace "
            "or reserved path characters."
        )
    return normalized


def _as_logical_uri(*parts: object) -> str:
    """Build a service-mount-independent claim-check URI."""

    return str(LOGICAL_ARTIFACTS_ROOT.joinpath(*(str(part) for part in parts)))


def _logical_relative_path(artifact_uri: str) -> Path | None:
    normalized_uri = artifact_uri.strip().replace("\\", "/")
    logical_root = str(LOGICAL_ARTIFACTS_ROOT)
    if normalized_uri == logical_root:
        raise ValueError("artifact_uri must point below /artifacts.")

    logical_prefix = f"{logical_root}/"
    if not normalized_uri.startswith(logical_prefix):
        return None

    logical_path = PurePosixPath(normalized_uri.removeprefix(logical_prefix))
    if any(part in {"", ".", ".."} for part in logical_path.parts):
        raise ValueError(f"artifact_uri '{artifact_uri}' escapes artifacts_root.")
    return Path(*logical_path.parts)


def run_root(artifacts_root: Path, run_id: str) -> Path:
    """Return the shared storage root for a run."""

    return artifacts_root / "runs" / validate_run_id(run_id)


def resolve_artifact_uri(artifacts_root: Path, artifact_uri: str) -> Path:
    """Resolve a claim-check URI while enforcing the configured artifacts boundary."""

    if not artifact_uri.strip():
        raise ValueError("artifact_uri must not be empty or whitespace.")

    root = artifacts_root.resolve()
    logical_relative = _logical_relative_path(artifact_uri)
    if logical_relative is not None:
        candidates = [root / logical_relative]
    else:
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


def segment_artifact_uri(
    artifacts_root: Path,
    run_id: str,
    track_id: int,
    segment_idx: int,
) -> str:
    """Build the canonical artifact URI for a segment."""

    validate_run_id(run_id)
    return _as_logical_uri("runs", run_id, "segments", track_id, f"{segment_idx}.wav")


def manifest_uri(artifacts_root: Path, run_id: str) -> str:
    """Build the canonical manifest URI for a run."""

    validate_run_id(run_id)
    return _as_logical_uri("runs", run_id, "manifests", "segments.parquet")
