"""Kafka client configuration helpers."""

from __future__ import annotations

from event_driven_audio_analytics.shared.contracts.topics import ALL_TOPICS


def producer_config(bootstrap_servers: str, client_id: str) -> dict[str, object]:
    """Return placeholder producer configuration."""

    return {
        "bootstrap.servers": bootstrap_servers,
        "client.id": client_id,
        "enable.idempotence": True,
        "acks": "all",
    }


def consumer_config(
    bootstrap_servers: str,
    group_id: str,
    auto_offset_reset: str = "earliest",
) -> dict[str, object]:
    """Return placeholder consumer configuration."""

    return {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "auto.offset.reset": auto_offset_reset,
        "enable.auto.commit": False,
        "topics": list(ALL_TOPICS),
    }
