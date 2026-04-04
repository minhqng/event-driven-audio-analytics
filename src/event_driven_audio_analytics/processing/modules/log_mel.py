"""Log-mel computation with the locked legacy parameter set."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch
import torchaudio


@dataclass(slots=True)
class LogMelExtractor:
    """Compute the exact legacy log-mel representation for one segment."""

    sample_rate_hz: int
    n_mels: int
    n_fft: int
    hop_length: int
    target_frames: int
    f_min: int = 0
    f_max: int | None = None
    log_epsilon: float = 1e-9
    device: str = "cpu"
    _device: torch.device = field(init=False, repr=False)
    _transform: torchaudio.transforms.MelSpectrogram = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._device = torch.device(self.device)
        self._transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=self.sample_rate_hz,
            n_mels=self.n_mels,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            f_min=self.f_min,
            f_max=self.f_max,
            norm="slaney",
            mel_scale="slaney",
        ).to(self._device)

    @property
    def expected_shape(self) -> tuple[int, int, int]:
        return (1, self.n_mels, self.target_frames)

    def compute(self, waveform: np.ndarray) -> torch.Tensor:
        """Convert a mono waveform into a log-mel tensor with exact target shape."""

        if waveform.ndim != 2 or waveform.shape[0] != 1:
            raise ValueError("Log-mel extraction expects a mono waveform shaped as (1, samples).")

        segment = torch.from_numpy(waveform.copy()).float().to(self._device)
        mel = self._transform(segment)
        mel = torch.log(mel + self.log_epsilon)

        if mel.shape[-1] > self.target_frames:
            mel = mel[:, :, : self.target_frames]
        elif mel.shape[-1] < self.target_frames:
            pad_width = self.target_frames - mel.shape[-1]
            mel = torch.nn.functional.pad(mel, (0, pad_width))

        mel = mel.cpu()
        if tuple(int(dimension) for dimension in mel.shape) != self.expected_shape:
            raise ValueError(
                "Log-mel extractor failed to produce the locked shape "
                f"expected={self.expected_shape} actual={tuple(int(d) for d in mel.shape)}"
            )
        return mel


def compute_log_mel_shape(waveform: np.ndarray, extractor: LogMelExtractor) -> tuple[int, int]:
    """Return the `(mel_bins, mel_frames)` summary for a computed log-mel tensor."""

    mel = extractor.compute(waveform)
    return (int(mel.shape[-2]), int(mel.shape[-1]))
