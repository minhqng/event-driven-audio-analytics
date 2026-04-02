"""Publish fake metadata and feature events for smoke validation."""

from __future__ import annotations

import json
from pathlib import Path

from event_driven_audio_analytics.shared.contracts.topics import AUDIO_FEATURES, AUDIO_METADATA
from event_driven_audio_analytics.shared.kafka import build_producer, serialize_envelope
from event_driven_audio_analytics.shared.settings import load_base_service_settings


REPO_ROOT = Path("/app")
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "events" / "v1"


def load_fixture(name: str) -> dict[str, object]:
    """Load one JSON fixture from the copied tests fixtures directory."""

    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def main() -> None:
    settings = load_base_service_settings("smoke-publisher")
    producer = build_producer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id="smoke-publisher",
    )

    fixture_by_topic = (
        (AUDIO_METADATA, load_fixture("audio.metadata.valid.json")),
        (AUDIO_FEATURES, load_fixture("audio.features.valid.json")),
    )

    for topic, envelope in fixture_by_topic:
        producer.produce(topic=topic, value=serialize_envelope(envelope))

    producer.flush()
    print("Published fake events: audio.metadata, audio.features")


if __name__ == "__main__":
    main()
