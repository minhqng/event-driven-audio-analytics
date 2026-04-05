"""Entrypoint for the writer service."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from event_driven_audio_analytics.shared.logging import configure_logging
from event_driven_audio_analytics.shared.models.envelope import build_trace_id
from event_driven_audio_analytics.writer.config import WriterSettings
from event_driven_audio_analytics.writer.modules.runtime import check_runtime_dependencies
from event_driven_audio_analytics.writer.pipeline import WriterPipeline


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the writer CLI command."""

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
    settings = WriterSettings.from_env()
    logger = configure_logging(
        settings.base.service_name,
        run_id=settings.base.run_id,
    ).bind(
        trace_id=build_trace_id(
            {
                "run_id": settings.base.run_id,
                "service_name": settings.base.service_name,
            },
            source_service=settings.base.service_name,
        )
    )

    if args.command == "preflight":
        logger.info("Running writer preflight.")
        try:
            check_runtime_dependencies(settings)
        except Exception:
            logger.bind(failure_class="startup_dependency").exception(
                "Writer preflight failed."
            )
            raise
        logger.info("Writer preflight passed.")
        return

    pipeline = WriterPipeline(settings=settings)
    logger.info(
        "Starting writer pipeline steps=%s bootstrap_servers=%s consumer_group=%s",
        pipeline.describe(),
        settings.base.kafka_bootstrap_servers,
        settings.consumer_group,
    )
    pipeline.run(logger=logger)


if __name__ == "__main__":
    main()
