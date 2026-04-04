"""Shared logging helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import os
import sys
from typing import Any


OPTIONAL_LOG_CONTEXT_FIELDS = (
    "run_id",
    "trace_id",
    "track_id",
    "segment_idx",
    "validation_status",
    "failure_class",
    "topic",
    "partition",
    "offset",
    "attempt",
    "metric_name",
    "metric_value",
    "silent_flag",
)
BOOLEAN_LOG_CONTEXT_FIELDS = {
    "silent_flag",
}


def _should_include_log_value(field_name: str, value: object) -> bool:
    """Return whether an optional structured-log field should be emitted."""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, bool):
        return field_name in BOOLEAN_LOG_CONTEXT_FIELDS
    return isinstance(value, (int, float))


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
        for field_name in OPTIONAL_LOG_CONTEXT_FIELDS:
            value = getattr(record, field_name, None)
            if _should_include_log_value(field_name, value):
                payload[field_name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class ServiceLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    """Attach stable service metadata to every emitted record."""

    def process(self, msg: object, kwargs: dict[str, object]) -> tuple[object, dict[str, object]]:
        extra = {
            key: value
            for key, value in dict(self.extra).items()
            if key == "service_name" or _should_include_log_value(key, value)
        }
        extra.update(
            {
                key: value
                for key, value in dict(kwargs.get("extra", {})).items()
                if key == "service_name" or _should_include_log_value(key, value)
            }
        )
        extra.setdefault("service_name", self.extra["service_name"])
        kwargs["extra"] = extra
        return msg, kwargs

    def bind(self, **context: object) -> "ServiceLoggerAdapter":
        """Return a new adapter with additional structured-log context."""

        merged = dict(self.extra)
        for key, value in context.items():
            if key == "service_name":
                merged[key] = value
            elif _should_include_log_value(key, value):
                merged[key] = value
            else:
                merged.pop(key, None)
        return ServiceLoggerAdapter(self.logger, merged)


def get_service_logger(
    service_name: str,
    *,
    run_id: str | None = None,
) -> ServiceLoggerAdapter:
    """Return a structured logger adapter for a configured service logger."""

    return ServiceLoggerAdapter(
        logging.getLogger(service_name),
        {
            "service_name": service_name,
            "run_id": run_id,
        },
    )


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
    return get_service_logger(service_name, run_id=run_id)
