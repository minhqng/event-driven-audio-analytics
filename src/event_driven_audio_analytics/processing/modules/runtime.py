"""Runtime readiness checks for the processing service."""

from __future__ import annotations

from dataclasses import dataclass
from os import R_OK, X_OK, access
from pathlib import Path
from typing import TYPE_CHECKING

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


def check_runtime_dependencies(settings: "ProcessingSettings") -> None:
    """Validate the current processing runtime dependencies once."""

    visible_topics = _list_kafka_topics(settings.base.kafka_bootstrap_servers)
    missing_topics = sorted(set(REQUIRED_PROCESSING_TOPICS) - visible_topics)
    if missing_topics:
        raise ProcessingReadinessError(
            "Kafka is reachable but missing required processing topics: "
            f"{', '.join(missing_topics)}."
        )

    _assert_readable_directory(settings.base.artifacts_root, label="ARTIFACTS_ROOT")
