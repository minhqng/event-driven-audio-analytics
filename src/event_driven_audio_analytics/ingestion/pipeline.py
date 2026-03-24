"""Pipeline outline for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass

from .config import IngestionSettings


@dataclass(slots=True)
class IngestionPipeline:
    """Describe the ingestion workflow without implementing full DSP behavior."""

    settings: IngestionSettings

    def describe(self) -> list[str]:
        return [
            "load metadata for subset=small",
            "validate audio paths and decode readiness",
            "segment audio into 3.0-second windows with 1.5-second overlap",
            "write artifacts and manifests to shared storage",
            "publish audio.metadata and audio.segment.ready events",
        ]

    def run(self) -> None:
        # TODO: connect metadata loading, validation, segmentation, artifact writing, and publishing.
        return None
