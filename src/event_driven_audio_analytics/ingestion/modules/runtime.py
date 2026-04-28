"""Runtime readiness checks for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass
from os import R_OK, W_OK, X_OK, access
from pathlib import Path
from time import monotonic, sleep
from typing import TYPE_CHECKING
from uuid import uuid4

from event_driven_audio_analytics.ingestion.modules.metadata_loader import load_small_subset_metadata
from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.shared.models.envelope import build_trace_id
from event_driven_audio_analytics.shared.storage import (
    manifest_uri,
    resolve_artifact_uri,
    run_root,
)

if TYPE_CHECKING:
    from confluent_kafka.admin import ClusterMetadata

    from event_driven_audio_analytics.ingestion.config import IngestionSettings
    from event_driven_audio_analytics.shared.logging import ServiceLoggerAdapter


REQUIRED_INGESTION_TOPICS = (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    SYSTEM_METRICS,
)
KAFKA_METADATA_TIMEOUT_S = 5.0


@dataclass(slots=True)
class IngestionReadinessError(RuntimeError):
    """Raised when ingestion runtime dependencies are not ready."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _service_trace_id(settings: "IngestionSettings") -> str:
    """Return the service-scoped trace id for startup logging."""

    return build_trace_id(
        {
            "run_id": settings.base.run_id,
            "service_name": settings.base.service_name,
        },
        source_service=settings.base.service_name,
    )


def _list_kafka_topics(bootstrap_servers: str) -> set[str]:
    """Return the currently visible Kafka topics."""

    from confluent_kafka.admin import AdminClient

    admin_client = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata: ClusterMetadata = admin_client.list_topics(timeout=KAFKA_METADATA_TIMEOUT_S)
    return set(metadata.topics)


def _assert_readable_file(path: Path, *, label: str) -> None:
    """Ensure one runtime file dependency exists and is readable."""

    if not path.exists():
        raise IngestionReadinessError(f"{label} does not exist: {path.as_posix()}")
    if not path.is_file():
        raise IngestionReadinessError(f"{label} is not a file: {path.as_posix()}")
    if not access(path, R_OK):
        raise IngestionReadinessError(f"{label} is not readable: {path.as_posix()}")


def _assert_readable_directory(path: Path, *, label: str) -> None:
    """Ensure one runtime directory dependency exists and is readable."""

    if not path.exists():
        raise IngestionReadinessError(f"{label} does not exist: {path.as_posix()}")
    if not path.is_dir():
        raise IngestionReadinessError(f"{label} is not a directory: {path.as_posix()}")
    if not access(path, R_OK | X_OK):
        raise IngestionReadinessError(f"{label} is not readable: {path.as_posix()}")


def _assert_writable_directory(path: Path, *, label: str) -> None:
    """Ensure one runtime directory dependency exists and is writable."""

    if not path.exists():
        raise IngestionReadinessError(f"{label} does not exist: {path.as_posix()}")
    if not path.is_dir():
        raise IngestionReadinessError(f"{label} is not a directory: {path.as_posix()}")
    if not access(path, W_OK | X_OK):
        raise IngestionReadinessError(f"{label} is not writable: {path.as_posix()}")


def _ensure_runtime_directory(path: Path, *, label: str) -> None:
    """Ensure one run-scoped runtime directory exists and is writable."""

    if path.exists():
        if not path.is_dir():
            raise IngestionReadinessError(f"{label} is not a directory: {path.as_posix()}")
    else:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise IngestionReadinessError(
                f"{label} could not be created: {path.as_posix()} ({exc})"
            ) from exc

    if not access(path, W_OK | X_OK):
        raise IngestionReadinessError(f"{label} is not writable: {path.as_posix()}")


def _probe_directory_write(path: Path, *, label: str) -> None:
    """Ensure one runtime directory accepts a short-lived write probe."""

    probe_path = path / f".ingestion-write-probe-{uuid4().hex}"
    try:
        probe_path.write_bytes(b"")
    except OSError as exc:
        raise IngestionReadinessError(
            f"{label} is not writable: {path.as_posix()} ({exc})"
        ) from exc

    try:
        probe_path.unlink()
    except OSError as exc:
        raise IngestionReadinessError(
            f"{label} probe cleanup failed: {probe_path.as_posix()} ({exc})"
        ) from exc


def _prepare_run_artifact_targets(artifacts_root: Path, run_id: str) -> tuple[Path, Path]:
    """Ensure the run-scoped artifact directories exist and are writable."""

    artifact_run_root = run_root(artifacts_root, run_id)
    segments_dir = artifact_run_root / "segments"
    manifests_dir = artifact_run_root / "manifests"

    _ensure_runtime_directory(
        artifact_run_root,
        label=f"ARTIFACT_RUN_ROOT[{run_id}]",
    )
    _ensure_runtime_directory(
        segments_dir,
        label=f"ARTIFACT_SEGMENTS_DIR[{run_id}]",
    )
    _ensure_runtime_directory(
        manifests_dir,
        label=f"ARTIFACT_MANIFESTS_DIR[{run_id}]",
    )
    _probe_directory_write(
        segments_dir,
        label=f"ARTIFACT_SEGMENTS_DIR[{run_id}]",
    )
    _probe_directory_write(
        manifests_dir,
        label=f"ARTIFACT_MANIFESTS_DIR[{run_id}]",
    )
    return segments_dir, manifests_dir


def _assert_manifest_target_ready(artifacts_root: Path, run_id: str) -> None:
    """Ensure the deterministic run manifest target is safe to overwrite."""

    manifest_path = resolve_artifact_uri(
        artifacts_root,
        manifest_uri(artifacts_root, run_id),
    )
    if not manifest_path.exists():
        return
    if not manifest_path.is_file():
        raise IngestionReadinessError(
            f"ARTIFACT_MANIFEST_PATH[{run_id}] is not a file: {manifest_path.as_posix()}"
        )
    if not access(manifest_path, W_OK):
        raise IngestionReadinessError(
            f"ARTIFACT_MANIFEST_PATH[{run_id}] is not writable: {manifest_path.as_posix()}"
        )


def _selected_track_ids(settings: "IngestionSettings") -> tuple[int, ...]:
    """Resolve the logical track ids that can write under the current run."""

    records = load_small_subset_metadata(
        settings.metadata_csv_path,
        audio_root_path=settings.audio_root_path,
        subset=settings.subset,
        track_id_allowlist=settings.track_id_allowlist,
        max_tracks=settings.max_tracks,
    )
    return tuple(sorted({record.track_id for record in records}))


def _prepare_track_segment_targets(segments_dir: Path, track_ids: tuple[int, ...], *, run_id: str) -> None:
    """Ensure the selected track-scoped segment directories are writable."""

    for track_id in track_ids:
        track_segments_dir = segments_dir / str(track_id)
        _ensure_runtime_directory(
            track_segments_dir,
            label=f"ARTIFACT_TRACK_SEGMENTS_DIR[{run_id}:{track_id}]",
        )
        _probe_directory_write(
            track_segments_dir,
            label=f"ARTIFACT_TRACK_SEGMENTS_DIR[{run_id}:{track_id}]",
        )


def check_runtime_dependencies(settings: "IngestionSettings") -> None:
    """Validate the current ingestion runtime dependencies once."""

    visible_topics = _list_kafka_topics(settings.base.kafka_bootstrap_servers)
    missing_topics = sorted(set(REQUIRED_INGESTION_TOPICS) - visible_topics)
    if missing_topics:
        raise IngestionReadinessError(
            "Kafka is reachable but missing required ingestion topics: "
            f"{', '.join(missing_topics)}."
        )

    _assert_writable_directory(settings.base.artifacts_root, label="ARTIFACTS_ROOT")
    _assert_readable_file(Path(settings.metadata_csv_path), label="METADATA_CSV_PATH")
    _assert_readable_directory(Path(settings.audio_root_path), label="AUDIO_ROOT_PATH")
    segments_dir, _ = _prepare_run_artifact_targets(settings.base.artifacts_root, settings.base.run_id)
    _assert_manifest_target_ready(settings.base.artifacts_root, settings.base.run_id)
    _prepare_track_segment_targets(
        segments_dir,
        _selected_track_ids(settings),
        run_id=settings.base.run_id,
    )


def wait_for_runtime_dependencies(
    settings: "IngestionSettings",
    logger: "ServiceLoggerAdapter",
) -> None:
    """Retry ingestion runtime readiness checks until the configured timeout."""

    deadline = monotonic() + settings.startup_timeout_s
    attempt = 0
    service_logger = logger.bind(trace_id=_service_trace_id(settings))
    failure_logger = service_logger.bind(failure_class="startup_dependency")

    while True:
        attempt += 1
        try:
            check_runtime_dependencies(settings)
            service_logger.info("Ingestion startup dependencies are ready.")
            return
        except Exception as exc:
            if monotonic() >= deadline:
                failure_logger.error("Ingestion startup dependency check failed: %s", exc)
                raise
            failure_logger.warning(
                "Waiting for ingestion startup dependencies attempt=%s reason=%s",
                attempt,
                exc,
            )
            sleep(settings.startup_retry_interval_s)
