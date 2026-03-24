"""Identifier helpers."""

from __future__ import annotations

from uuid import uuid4


def generate_event_id() -> str:
    """Return a UUID4 event identifier."""

    return str(uuid4())
