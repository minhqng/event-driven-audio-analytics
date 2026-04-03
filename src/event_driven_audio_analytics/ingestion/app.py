"""Entrypoint for the ingestion service."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from event_driven_audio_analytics.ingestion.config import IngestionSettings
from event_driven_audio_analytics.ingestion.modules.runtime import check_runtime_dependencies
from event_driven_audio_analytics.ingestion.pipeline import IngestionPipeline
from event_driven_audio_analytics.shared.logging import configure_logging
from event_driven_audio_analytics.shared.models.envelope import build_trace_id


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the ingestion CLI command."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "preflight"),
        default="run",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = IngestionSettings.from_env()
    logger = configure_logging(settings.base.service_name, run_id=settings.base.run_id).bind(
        trace_id=build_trace_id(
            {
                "run_id": settings.base.run_id,
                "service_name": settings.base.service_name,
            },
            source_service=settings.base.service_name,
        )
    )

    if args.command == "preflight":
        logger.info("Running ingestion preflight.")
        try:
            check_runtime_dependencies(settings)
        except Exception:
            logger.bind(failure_class="startup_dependency").exception(
                "Ingestion preflight failed."
            )
            raise
        logger.info("Ingestion preflight passed.")
        return

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
