"""Entrypoint for the ingestion service."""

from __future__ import annotations

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.ingestion.pipeline import IngestionPipeline
from event_driven_audio_analytics.shared.logging import configure_logging


def main() -> None:
    settings = IngestionSettings.from_env()
    logger = configure_logging(settings.base.service_name, run_id=settings.base.run_id)
    pipeline = IngestionPipeline(settings=settings)
    logger.info(
        "Starting ingestion pipeline steps=%s metadata_csv=%s audio_root=%s bootstrap_servers=%s",
        pipeline.describe(),
        settings.metadata_csv_path,
        settings.audio_root_path,
        settings.base.kafka_bootstrap_servers,
    )
    pipeline.run()


if __name__ == "__main__":
    main()
