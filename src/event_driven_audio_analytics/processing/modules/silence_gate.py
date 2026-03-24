"""Silence-gating placeholders."""

from __future__ import annotations


def is_silent_segment(rms_value: float, threshold_db: float) -> bool:
    """Return a placeholder silence decision."""

    return rms_value <= threshold_db
