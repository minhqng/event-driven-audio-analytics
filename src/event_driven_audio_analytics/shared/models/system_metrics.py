"""Payload model for the system.metrics topic."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SystemMetricsPayload:
    """Operational metric emitted by any service."""

    ts: str
    run_id: str
    service_name: str
    metric_name: str
    metric_value: float
    labels_json: dict[str, object] = field(default_factory=dict)
    unit: str | None = None
