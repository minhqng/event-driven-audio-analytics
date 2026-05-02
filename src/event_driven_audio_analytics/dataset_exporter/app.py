"""CLI entrypoint for deterministic FMA-Small dataset exports."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
import json
from pathlib import Path

from event_driven_audio_analytics.dataset_exporter.config import DatasetExporterSettings
from event_driven_audio_analytics.dataset_exporter.exporter import export_dataset_bundle
from event_driven_audio_analytics.shared.storage import validate_run_id


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a completed FMA-Small run into a deterministic dataset bundle.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--run-id", required=True)
    export_parser.add_argument(
        "--artifacts-root",
        type=Path,
        help="Override ARTIFACTS_ROOT for claim-check artifact lookup.",
    )
    export_parser.add_argument(
        "--datasets-root",
        type=Path,
        help="Override DATASET_EXPORT_ROOT for bundle output.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = DatasetExporterSettings.from_env()

    if args.command == "export":
        artifacts_root = args.artifacts_root or settings.artifacts_root
        storage = replace(settings.storage, artifacts_root=artifacts_root)
        datasets_root = args.datasets_root or settings.datasets_root
        result = export_dataset_bundle(
            database=settings.database,
            artifacts_root=artifacts_root,
            datasets_root=datasets_root,
            storage_settings=storage,
            run_id=validate_run_id(args.run_id),
        )
        print(json.dumps(  # noqa: T201 - CLI result payload
            {
                "run_id": result.run_id,
                "output_dir": result.output_dir.as_posix(),
                "file_count": result.file_count,
                "quality_verdict": result.quality_verdict,
                "accepted_tracks": result.accepted_tracks,
                "rejected_tracks": result.rejected_tracks,
                "accepted_segments": result.accepted_segments,
                "rejected_segments": result.rejected_segments,
            },
            indent=2,
            sort_keys=True,
        ))
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
