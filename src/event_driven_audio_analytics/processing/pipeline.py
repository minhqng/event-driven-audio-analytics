"""Pipeline outline for the processing service."""

from __future__ import annotations

from dataclasses import dataclass

from .config import ProcessingSettings


@dataclass(slots=True)
class ProcessingPipeline:
    """Describe the processing workflow without implementing DSP internals."""

    settings: ProcessingSettings

    def describe(self) -> list[str]:
        return [
            "consume audio.segment.ready events",
            "load artifacts using artifact_uri and checksum",
            "compute RMS, silence-gate decisions, and log-mel summary shape",
            "update Welford-style monitoring statistics",
            "publish audio.features and system.metrics events",
        ]

    def run(self) -> None:
        # TODO: connect Kafka consumption, artifact loading, DSP steps, and event publishing.
        return None
