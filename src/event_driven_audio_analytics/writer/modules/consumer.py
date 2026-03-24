"""Kafka-consumption placeholders for the writer service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConsumedRecord:
    """A minimal consumed Kafka record placeholder."""

    topic: str
    partition: int
    offset: int
    payload: dict[str, object]


def poll_batch() -> list[ConsumedRecord]:
    """Return an empty batch until Kafka consumption is implemented."""

    # TODO: implement batch polling for audio.metadata, audio.features, and system.metrics.
    return []
