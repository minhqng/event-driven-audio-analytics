"""Entrypoint for the ingestion service."""

from __future__ import annotations

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.ingestion.pipeline import IngestionPipeline
from event_driven_audio_analytics.shared.logging import configure_logging


def main() -> None:
    settings = IngestionSettings.from_env()
    logger = configure_logging(settings.base.service_name)
    pipeline = IngestionPipeline(settings=settings)
    logger.info("Starting ingestion scaffold with steps: %s", pipeline.describe())
    pipeline.run()


if __name__ == "__main__":
    main()
