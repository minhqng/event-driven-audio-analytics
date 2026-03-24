"""Entrypoint for the writer service."""

from __future__ import annotations

from event_driven_audio_analytics.shared.logging import configure_logging
from event_driven_audio_analytics.writer.config import WriterSettings
from event_driven_audio_analytics.writer.pipeline import WriterPipeline


def main() -> None:
    settings = WriterSettings.from_env()
    logger = configure_logging(settings.base.service_name)
    pipeline = WriterPipeline(settings=settings)
    logger.info("Starting writer scaffold with steps: %s", pipeline.describe())
    pipeline.run()


if __name__ == "__main__":
    main()
