"""Shared logging helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import os
import sys
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Render one JSON log line per record for container-friendly logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace(
                "+00:00",
                "Z",
            ),
            "level": record.levelname,
            "service": getattr(record, "service_name", record.name),
            "logger": record.name,
            "message": record.getMessage(),
        }
        run_id = getattr(record, "run_id", None)
        if isinstance(run_id, str) and run_id:
            payload["run_id"] = run_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class ServiceLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    """Attach stable service metadata to every emitted record."""

    def process(self, msg: object, kwargs: dict[str, object]) -> tuple[object, dict[str, object]]:
        extra = dict(kwargs.get("extra", {}))
        extra.setdefault("service_name", self.extra["service_name"])
        run_id = self.extra.get("run_id")
        if run_id:
            extra.setdefault("run_id", run_id)
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(
    service_name: str,
    *,
    run_id: str | None = None,
    level: str | None = None,
) -> ServiceLoggerAdapter:
    """Configure structured logging for one service."""

    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(resolved_level)

    logger = logging.getLogger(service_name)
    logger.setLevel(resolved_level)
    logger.propagate = True
    return ServiceLoggerAdapter(
        logger,
        {
            "service_name": service_name,
            "run_id": run_id,
        },
    )
