"""Shared event-envelope model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from typing import Generic, TypeVar

from event_driven_audio_analytics.shared.ids import generate_event_id


PayloadT = TypeVar("PayloadT")


@dataclass(slots=True)
class EventEnvelope(Generic[PayloadT]):
    """Generic event envelope for topic payloads."""

    event_id: str
    event_type: str
    schema_version: str
    occurred_at: str
    produced_by: str
    payload: PayloadT

    def to_dict(self) -> dict[str, object]:
        payload: object = self.payload
        if is_dataclass(self.payload):
            payload = asdict(self.payload)

        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at,
            "produced_by": self.produced_by,
            "payload": payload,
        }


def build_envelope(event_type: str, produced_by: str, payload: PayloadT) -> EventEnvelope[PayloadT]:
    """Build a versioned event envelope with a generated identifier."""

    return EventEnvelope(
        event_id=generate_event_id(),
        event_type=event_type,
        schema_version="v1",
        occurred_at=datetime.now(UTC).isoformat(),
        produced_by=produced_by,
        payload=payload,
    )
