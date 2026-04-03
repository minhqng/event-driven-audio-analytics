"""Runtime readiness checks for the processing service."""

from __future__ import annotations

from dataclasses import dataclass
from os import R_OK, W_OK, X_OK, access
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from event_driven_audio_analytics.processing.modules.metrics import processing_metrics_state_path
from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_FEATURES,
    AUDIO_SEGMENT_READY,
    SYSTEM_METRICS,
)

if TYPE_CHECKING:
    from confluent_kafka.admin import ClusterMetadata

    from event_driven_audio_analytics.processing.config import ProcessingSettings


REQUIRED_PROCESSING_TOPICS = (
    AUDIO_SEGMENT_READY,
    AUDIO_FEATURES,
    SYSTEM_METRICS,
)
KAFKA_METADATA_TIMEOUT_S = 5.0


@dataclass(slots=True)
class ProcessingReadinessError(RuntimeError):
    """Raised when processing runtime dependencies are not ready."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _list_kafka_topics(bootstrap_servers: str) -> set[str]:
    """Return the currently visible Kafka topics."""

    from confluent_kafka.admin import AdminClient

    admin_client = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata: ClusterMetadata = admin_client.list_topics(timeout=KAFKA_METADATA_TIMEOUT_S)
    return set(metadata.topics)


def _assert_readable_directory(path: Path, *, label: str) -> None:
    """Ensure one runtime directory dependency exists and is readable."""

    if not path.exists():
        raise ProcessingReadinessError(f"{label} does not exist: {path.as_posix()}")
    if not path.is_dir():
        raise ProcessingReadinessError(f"{label} is not a directory: {path.as_posix()}")
    if not access(path, R_OK | X_OK):
        raise ProcessingReadinessError(f"{label} is not readable: {path.as_posix()}")


def _assert_writable_directory(path: Path, *, label: str) -> None:
    """Ensure one runtime directory dependency exists and is writable."""

    if not path.exists():
        raise ProcessingReadinessError(f"{label} does not exist: {path.as_posix()}")
    if not path.is_dir():
        raise ProcessingReadinessError(f"{label} is not a directory: {path.as_posix()}")
    if not access(path, W_OK | X_OK):
        raise ProcessingReadinessError(f"{label} is not writable: {path.as_posix()}")


def _ensure_runtime_directory(path: Path, *, label: str) -> None:
    """Ensure one run-scoped runtime directory exists and is writable."""

    if path.exists():
        if not path.is_dir():
            raise ProcessingReadinessError(f"{label} is not a directory: {path.as_posix()}")
    else:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProcessingReadinessError(
                f"{label} could not be created: {path.as_posix()} ({exc})"
            ) from exc

    if not access(path, W_OK | X_OK):
        raise ProcessingReadinessError(f"{label} is not writable: {path.as_posix()}")


def _probe_directory_write(path: Path, *, label: str) -> None:
    """Ensure one runtime directory accepts a short-lived write probe."""

    probe_path = path / f".processing-write-probe-{uuid4().hex}"
    try:
        probe_path.write_bytes(b"")
    except OSError as exc:
        raise ProcessingReadinessError(
            f"{label} is not writable: {path.as_posix()} ({exc})"
        ) from exc

    try:
        probe_path.unlink()
    except OSError as exc:
        raise ProcessingReadinessError(
            f"{label} probe cleanup failed: {probe_path.as_posix()} ({exc})"
        ) from exc


def _prepare_processing_state_target(artifacts_root: Path, run_id: str) -> None:
    """Ensure the processing state directory exists and is writable."""

    state_path = processing_metrics_state_path(artifacts_root, run_id)
    state_dir = state_path.parent
    _ensure_runtime_directory(
        state_dir,
        label=f"ARTIFACT_PROCESSING_STATE_DIR[{run_id}]",
    )
    _probe_directory_write(
        state_dir,
        label=f"ARTIFACT_PROCESSING_STATE_DIR[{run_id}]",
    )
    if state_path.exists() and (not state_path.is_file() or not access(state_path, W_OK)):
        raise ProcessingReadinessError(
            f"ARTIFACT_PROCESSING_STATE_PATH[{run_id}] is not writable: {state_path.as_posix()}"
        )


def check_runtime_dependencies(settings: "ProcessingSettings") -> None:
    """Validate the current processing runtime dependencies once."""

    visible_topics = _list_kafka_topics(settings.base.kafka_bootstrap_servers)
    missing_topics = sorted(set(REQUIRED_PROCESSING_TOPICS) - visible_topics)
    if missing_topics:
        raise ProcessingReadinessError(
            "Kafka is reachable but missing required processing topics: "
            f"{', '.join(missing_topics)}."
        )

    _assert_writable_directory(settings.base.artifacts_root, label="ARTIFACTS_ROOT")
    _assert_readable_directory(settings.base.artifacts_root, label="ARTIFACTS_ROOT")
    _prepare_processing_state_target(settings.base.artifacts_root, settings.base.run_id)
