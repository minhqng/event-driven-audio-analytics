"""Publish fake writer-topic events for smoke validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_FEATURES,
    AUDIO_METADATA,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.shared.kafka import build_producer, serialize_envelope
from event_driven_audio_analytics.shared.settings import load_base_service_settings


REPO_ROOT = Path("/app")
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "events" / "v1"


def load_fixture(name: str) -> dict[str, object]:
    """Load one JSON fixture from the copied tests fixtures directory."""

    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    """Parse smoke publisher runtime options."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only-run-total-metric",
        action="store_true",
        help="publish only the dedicated run_total system.metrics fixture",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_base_service_settings("smoke-publisher")
    producer = build_producer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id="smoke-publisher",
    )

    if args.only_run_total_metric:
        fixture_by_topic = (
            (SYSTEM_METRICS, load_fixture("system.metrics.run_total.valid.json")),
        )
    else:
        fixture_by_topic = (
            (AUDIO_METADATA, load_fixture("audio.metadata.valid.json")),
            (AUDIO_FEATURES, load_fixture("audio.features.valid.json")),
        )

    for topic, envelope in fixture_by_topic:
        producer.produce(topic=topic, value=serialize_envelope(envelope))

    producer.flush()
    print(
        "Published fake events: "
        + ", ".join(topic for topic, _ in fixture_by_topic)
    )


if __name__ == "__main__":
    main()
