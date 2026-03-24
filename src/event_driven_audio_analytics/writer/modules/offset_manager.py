"""Offset-commit coordination placeholders for the writer service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OffsetCommitDecision:
    """Represent whether offsets are safe to commit."""

    commit_allowed: bool
    reason: str


def build_commit_decision(rows_written: int, checkpoints_ready: bool) -> OffsetCommitDecision:
    """Commit offsets only when persistence and checkpoints both succeed."""

    if not checkpoints_ready:
        return OffsetCommitDecision(commit_allowed=False, reason="checkpoint update not complete")
    if rows_written < 0:
        return OffsetCommitDecision(commit_allowed=False, reason="invalid persistence result")
    return OffsetCommitDecision(commit_allowed=True, reason="persistence and checkpoints complete")
