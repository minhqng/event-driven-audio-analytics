"""Pipeline outline for the writer service."""

from __future__ import annotations

from dataclasses import dataclass

from .config import WriterSettings


@dataclass(slots=True)
class WriterPipeline:
    """Describe the writer workflow without implementing database I/O."""

    settings: WriterSettings

    def describe(self) -> list[str]:
        return [
            "consume audio.metadata, audio.features, and system.metrics events",
            "persist track metadata, feature summaries, and system metrics",
            "upsert feature summaries using the logical key (run_id, track_id, segment_idx)",
            "update run checkpoints after successful persistence",
            "commit Kafka offsets only after persistence and checkpoint update",
        ]

    def run(self) -> None:
        # TODO: connect Kafka consumption, TimescaleDB persistence, checkpoint storage, and offset commits.
        return None
