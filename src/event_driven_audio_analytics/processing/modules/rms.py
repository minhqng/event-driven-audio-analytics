"""RMS computations for processing summaries."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from event_driven_audio_analytics.shared.audio import compute_rms_db


@dataclass(slots=True)
class RmsSummary:
    """Segment RMS summary in linear and dBFS forms."""

    rms_linear: float
    rms_dbfs: float


def summarize_rms(waveform: np.ndarray) -> RmsSummary:
    """Compute the legacy RMS summary for one mono segment."""

    mono_waveform = waveform.astype(np.float32, copy=False)
    if mono_waveform.size == 0:
        return RmsSummary(rms_linear=0.0, rms_dbfs=-math.inf)

    rms_linear = float(np.sqrt(np.mean(np.square(mono_waveform), dtype=np.float64)))
    return RmsSummary(rms_linear=rms_linear, rms_dbfs=compute_rms_db(mono_waveform))


def encode_rms_db_for_event(rms_dbfs: float, *, floor_db: float) -> float:
    """Clamp non-finite RMS values so the summary event stays JSON-safe."""

    if math.isfinite(rms_dbfs):
        return rms_dbfs
    return floor_db
