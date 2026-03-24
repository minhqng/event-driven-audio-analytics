"""Shared logging helpers."""

from __future__ import annotations

import logging


def configure_logging(service_name: str) -> logging.Logger:
    """Configure a minimal structured logger for a service."""

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s %(levelname)s [{service_name}] %(message)s",
    )
    return logging.getLogger(service_name)
