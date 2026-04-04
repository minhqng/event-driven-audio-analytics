"""Vector-valued Welford statistics for mel-bin monitoring."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch


@dataclass(slots=True)
class WelfordState:
    """Streaming statistics over per-mel-bin means."""

    count: int = 0
    mean: np.ndarray | None = None
    m2: np.ndarray | None = None
    ref: str | None = None

    @property
    def variance(self) -> np.ndarray | None:
        if self.mean is None or self.m2 is None or self.count < 2:
            return None
        return self.m2 / float(self.count - 1)

    @property
    def std(self) -> np.ndarray | None:
        variance = self.variance
        if variance is None:
            return None
        return np.sqrt(variance)


def build_welford_state_ref(run_id: str) -> str:
    """Build a deterministic reference for the current in-memory Welford state."""

    return f"welford:processing:v1:{run_id}:mel-bin-mean"


def mel_bin_means(mel: torch.Tensor | np.ndarray) -> np.ndarray:
    """Collapse a log-mel tensor into one mean value per mel bin."""

    if isinstance(mel, torch.Tensor):
        mel_tensor = mel.detach().cpu()
        if mel_tensor.ndim != 3 or mel_tensor.shape[0] != 1:
            raise ValueError("Welford updates expect a log-mel tensor shaped as (1, n_mels, frames).")
        return mel_tensor.squeeze(0).mean(dim=1).numpy().astype(np.float64, copy=False)

    mel_array = np.asarray(mel, dtype=np.float64)
    if mel_array.ndim != 3 or mel_array.shape[0] != 1:
        raise ValueError("Welford updates expect a log-mel tensor shaped as (1, n_mels, frames).")
    return mel_array[0].mean(axis=1)


def update_welford(state: WelfordState, mel: torch.Tensor | np.ndarray) -> WelfordState:
    """Update vector-valued Welford statistics using one log-mel sample."""

    sample_mean = mel_bin_means(mel)
    if state.mean is None or state.m2 is None:
        mean = np.zeros_like(sample_mean, dtype=np.float64)
        m2 = np.zeros_like(sample_mean, dtype=np.float64)
        count = 0
    else:
        mean = state.mean.copy()
        m2 = state.m2.copy()
        count = state.count

    count += 1
    delta = sample_mean - mean
    mean = mean + (delta / float(count))
    delta2 = sample_mean - mean
    m2 = m2 + (delta * delta2)
    return WelfordState(count=count, mean=mean, m2=m2, ref=state.ref)
