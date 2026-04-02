"""Segmentation helpers for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(slots=True)
class AudioSegment:
    """Represents one in-memory audio segment prior to claim-check writing."""

    run_id: str
    track_id: int
    segment_idx: int
    waveform: np.ndarray
    sample_rate: int
    duration_s: float
    is_last_segment: bool


def segment_audio(
    *,
    run_id: str,
    track_id: int,
    waveform: np.ndarray,
    sample_rate_hz: int,
    segment_duration_s: float = 3.0,
    segment_overlap_s: float = 1.5,
    tail_pad_threshold_s: float = 1.0,
) -> list[AudioSegment]:
    """Slice decoded audio into the legacy 3.0s / 1.5s-overlap segments."""

    if waveform.ndim != 2 or waveform.shape[0] != 1:
        raise ValueError("Segmenter expects a mono waveform shaped as (1, samples).")

    segment_samples = int(round(sample_rate_hz * segment_duration_s))
    hop_samples = int(round(sample_rate_hz * (segment_duration_s - segment_overlap_s)))
    tail_pad_threshold_samples = int(math.floor(sample_rate_hz * tail_pad_threshold_s))
    if hop_samples <= 0:
        raise ValueError("segment_overlap_s must be smaller than segment_duration_s.")

    total_samples = waveform.shape[-1]
    segments: list[AudioSegment] = []
    start = 0
    segment_idx = 0
    while start + segment_samples <= total_samples:
        segments.append(
            AudioSegment(
                run_id=run_id,
                track_id=track_id,
                segment_idx=segment_idx,
                waveform=waveform[:, start : start + segment_samples].copy(),
                sample_rate=sample_rate_hz,
                duration_s=segment_duration_s,
                is_last_segment=False,
            )
        )
        start += hop_samples
        segment_idx += 1

    remaining_samples = total_samples - start
    if remaining_samples > tail_pad_threshold_samples:
        tail_segment = waveform[:, start:].copy()
        pad_width = segment_samples - tail_segment.shape[-1]
        if pad_width > 0:
            tail_segment = np.pad(tail_segment, ((0, 0), (0, pad_width)))

        segments.append(
            AudioSegment(
                run_id=run_id,
                track_id=track_id,
                segment_idx=segment_idx,
                waveform=tail_segment,
                sample_rate=sample_rate_hz,
                duration_s=segment_duration_s,
                is_last_segment=False,
            )
        )

    if segments:
        segments[-1].is_last_segment = True

    return segments
