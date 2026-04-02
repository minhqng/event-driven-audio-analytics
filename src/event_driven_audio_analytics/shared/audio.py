"""Shared audio loading and validation helpers derived from the legacy pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import av
import numpy as np


@dataclass(slots=True)
class AudioProbe:
    """Cheap stream metadata gathered before full decode."""

    duration_s: float
    sample_rate_hz: int


@dataclass(slots=True)
class DecodedAudio:
    """Decoded mono waveform normalized to the target sample rate."""

    waveform: np.ndarray
    sample_rate_hz: int
    duration_s: float
    original_sample_rate_hz: int


def _open_audio(path: str | Path) -> av.container.input.InputContainer:
    """Open an audio container via PyAV."""

    return av.open(str(Path(path)))


def probe_audio(path: str | Path) -> AudioProbe:
    """Probe duration and sample rate for an audio file."""

    container = _open_audio(path)
    try:
        stream = container.streams.audio[0]
        if stream.rate is None:
            raise RuntimeError(f"Audio sample rate is unavailable for {path}.")

        duration_s: float | None = None
        if stream.duration is not None and stream.time_base is not None:
            duration_s = float(stream.duration * stream.time_base)
        elif container.duration is not None:
            duration_s = float(container.duration / av.time_base)

        if duration_s is None:
            raise RuntimeError(f"Audio duration is unavailable for {path}.")

        return AudioProbe(duration_s=duration_s, sample_rate_hz=int(stream.rate))
    finally:
        container.close()


def decode_audio_pyav(path: str | Path, *, target_sample_rate_hz: int) -> DecodedAudio:
    """Decode audio via PyAV, convert to mono, and resample to the target rate."""

    container = _open_audio(path)
    try:
        stream = container.streams.audio[0]
        if stream.rate is None:
            raise RuntimeError(f"Audio sample rate is unavailable for {path}.")

        original_sample_rate_hz = int(stream.rate)
        resampler = av.audio.resampler.AudioResampler(
            format="flt",
            layout="mono",
            rate=target_sample_rate_hz,
        )

        frames: list[np.ndarray] = []
        for frame in container.decode(audio=0):
            for output_frame in resampler.resample(frame):
                frames.append(output_frame.to_ndarray().astype(np.float32, copy=False))

        for output_frame in resampler.resample(None):
            frames.append(output_frame.to_ndarray().astype(np.float32, copy=False))

        if not frames:
            raise RuntimeError(f"No audio frames decoded from {path}.")

        waveform = np.concatenate(frames, axis=1)
        if waveform.ndim == 1:
            waveform = waveform[np.newaxis, :]

        duration_s = waveform.shape[-1] / float(target_sample_rate_hz)
        return DecodedAudio(
            waveform=waveform,
            sample_rate_hz=target_sample_rate_hz,
            duration_s=duration_s,
            original_sample_rate_hz=original_sample_rate_hz,
        )
    finally:
        container.close()


def compute_rms_db(waveform: np.ndarray) -> float:
    """Compute waveform RMS in dBFS, matching the legacy silence policy."""

    if waveform.size == 0:
        return -math.inf

    mono_waveform = waveform.astype(np.float32, copy=False)
    rms = float(np.sqrt(np.mean(np.square(mono_waveform), dtype=np.float64)))
    if rms < 1e-10:
        return -math.inf

    return 20.0 * math.log10(rms)
