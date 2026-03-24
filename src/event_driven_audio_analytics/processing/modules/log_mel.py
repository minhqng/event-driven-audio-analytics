"""Log-mel placeholder computations."""

from __future__ import annotations


def compute_log_mel_shape(_: bytes) -> tuple[int, int]:
    """Return the expected log-mel shape without computing the transform."""

    # TODO: implement log-mel spectrogram generation with target shape (128, 300).
    return (128, 300)
