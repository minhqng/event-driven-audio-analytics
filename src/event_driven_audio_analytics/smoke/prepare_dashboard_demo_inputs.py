"""Prepare deterministic dashboard demo inputs under the shared artifacts mount."""

from __future__ import annotations

import argparse
from array import array
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import sys
import wave


SAMPLE_RATE_HZ = 32000
PCM_MAX_AMPLITUDE = 32767


@dataclass(frozen=True, slots=True)
class DemoTrack:
    track_id: int
    artist_id: int
    genre: str
    duration_s: float
    description: str


HIGH_ENERGY_TRACK = DemoTrack(
    track_id=910001,
    artist_id=9101,
    genre="Synthetic-High-Energy",
    duration_s=6.0,
    description="Continuous high-energy tone for the baseline run.",
)
SILENT_ORIENTED_TRACK = DemoTrack(
    track_id=910002,
    artist_id=9102,
    genre="Synthetic-Silent-Oriented",
    duration_s=6.0,
    description="First segment silent, later segments energetic, so processing emits a non-zero silent_ratio.",
)
VALIDATION_FAILURE_TRACK = DemoTrack(
    track_id=910003,
    artist_id=9103,
    genre="Synthetic-Validation-Failure",
    duration_s=3.0,
    description="Fully silent track that fails ingestion validation and drives the error-rate panel.",
)


def _canonical_track_path(output_root: Path, track_id: int) -> Path:
    track_id_str = f"{track_id:06d}"
    return output_root / "fma_small" / track_id_str[:3] / f"{track_id_str}.mp3"


def _clamp_pcm_sample(value: float) -> int:
    limited = max(-1.0, min(1.0, value))
    return int(round(limited * PCM_MAX_AMPLITUDE))


def _wave_bytes(samples: list[int]) -> bytes:
    pcm = array("h", samples)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def _write_waveform(path: Path, samples: list[int], *, sample_rate_hz: int = SAMPLE_RATE_HZ) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(_wave_bytes(samples))


def _tone_samples(
    *,
    duration_s: float,
    amplitude: float,
    frequency_hz: float,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
) -> list[int]:
    sample_count = int(round(duration_s * sample_rate_hz))
    return [
        _clamp_pcm_sample(
            amplitude * math.sin((2.0 * math.pi * frequency_hz * sample_idx) / float(sample_rate_hz))
        )
        for sample_idx in range(sample_count)
    ]


def _silence_samples(*, duration_s: float, sample_rate_hz: int = SAMPLE_RATE_HZ) -> list[int]:
    return [0] * int(round(duration_s * sample_rate_hz))


def _high_energy_waveform() -> list[int]:
    return _tone_samples(duration_s=HIGH_ENERGY_TRACK.duration_s, amplitude=0.55, frequency_hz=440.0)


def _silent_oriented_waveform() -> list[int]:
    return _silence_samples(duration_s=3.0) + _tone_samples(duration_s=3.0, amplitude=0.35, frequency_hz=660.0)


def _validation_failure_waveform() -> list[int]:
    return _silence_samples(duration_s=VALIDATION_FAILURE_TRACK.duration_s)


def _write_metadata_csv(output_root: Path, tracks: list[DemoTrack]) -> Path:
    csv_path = output_root / "metadata.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["", "artist", "set", "track", "track"])
        writer.writerow(["", "id", "subset", "genre_top", "duration"])
        writer.writerow(["track_id", "", "", "", ""])
        for track in tracks:
            writer.writerow(
                [
                    track.track_id,
                    track.artist_id,
                    "small",
                    track.genre,
                    f"{track.duration_s:.2f}",
                ]
            )
    return csv_path


def prepare_dashboard_demo_inputs(output_root: Path) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)

    tracks = [
        HIGH_ENERGY_TRACK,
        SILENT_ORIENTED_TRACK,
        VALIDATION_FAILURE_TRACK,
    ]
    _write_waveform(_canonical_track_path(output_root, HIGH_ENERGY_TRACK.track_id), _high_energy_waveform())
    _write_waveform(_canonical_track_path(output_root, SILENT_ORIENTED_TRACK.track_id), _silent_oriented_waveform())
    _write_waveform(
        _canonical_track_path(output_root, VALIDATION_FAILURE_TRACK.track_id),
        _validation_failure_waveform(),
    )
    metadata_csv = _write_metadata_csv(output_root, tracks)
    return {
        "output_root": output_root.as_posix(),
        "metadata_csv": metadata_csv.as_posix(),
        "audio_root": (output_root / "fma_small").as_posix(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/demo_inputs/dashboard-demo"),
        help="Directory used to stage the dashboard demo inputs.",
    )
    args = parser.parse_args()
    paths = prepare_dashboard_demo_inputs(args.output_root.resolve())
    for key, value in paths.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
