"""Entrypoint for the processing service."""

from __future__ import annotations

from event_driven_audio_analytics.processing.config import ProcessingSettings
from event_driven_audio_analytics.processing.pipeline import ProcessingPipeline
from event_driven_audio_analytics.shared.logging import configure_logging


def main() -> None:
    settings = ProcessingSettings.from_env()
    logger = configure_logging(settings.base.service_name)
    pipeline = ProcessingPipeline(settings=settings)
    logger.info("Starting processing scaffold with steps: %s", pipeline.describe())
    pipeline.run()


if __name__ == "__main__":
    main()
