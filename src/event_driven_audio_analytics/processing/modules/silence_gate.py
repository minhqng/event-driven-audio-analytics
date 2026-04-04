"""Silence-gating helpers derived from the legacy pipeline."""

from __future__ import annotations

import torch


def is_silent_segment(mel: torch.Tensor, *, std_floor: float = 1e-7) -> bool:
    """Apply the inherited post-log-mel silence gate."""

    if mel.ndim != 3 or mel.shape[0] != 1:
        raise ValueError("Silence gate expects a log-mel tensor shaped as (1, n_mels, frames).")

    return bool(mel.std().item() < std_floor)
