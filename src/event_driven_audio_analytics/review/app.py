"""Entrypoint and HTTP app for the read-only review service."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from event_driven_audio_analytics.review.config import ReviewSettings
from event_driven_audio_analytics.review.queries import (
    get_run_detail,
    get_track_detail,
    list_runs,
    list_tracks_for_run,
    lookup_segment_artifact_ref,
)
from event_driven_audio_analytics.review.runtime import check_runtime_dependencies
from event_driven_audio_analytics.review.schemas import normalize_limit, normalize_offset, validate_run_id
from event_driven_audio_analytics.shared.logging import configure_logging
from event_driven_audio_analytics.shared.models.envelope import build_trace_id
from event_driven_audio_analytics.shared.storage import build_claim_check_store_for_uri


STATIC_ROOT = Path(__file__).with_name("static")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        choices=("run", "preflight"),
        default="run",
    )
    return parser.parse_args(argv)


def create_app(settings: ReviewSettings | None = None) -> FastAPI:
    active_settings = settings or ReviewSettings.from_env()
    app = FastAPI(
        title="Event-Driven Audio Analytics Review",
        version="0.1.0",
    )
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @app.get("/", response_class=HTMLResponse)
    def review_index() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "service": active_settings.base.service_name,
            "authoritative_truth": "db_views_and_artifacts",
            "provenance": {"source": "derived"},
        }

    @app.get("/api/runs")
    def api_runs(
        limit: int | None = Query(default=None),
        offset: int | None = Query(default=None),
        demo_mode: bool = Query(default=False),
    ) -> dict[str, object]:
        try:
            resolved_limit = normalize_limit(
                limit,
                default_limit=active_settings.default_limit,
                max_limit=active_settings.max_limit,
            )
            resolved_offset = normalize_offset(offset)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return list_runs(
            active_settings,
            limit=resolved_limit,
            offset=resolved_offset,
            demo_mode=demo_mode,
        )

    @app.get("/api/runs/{run_id}")
    def api_run_detail(run_id: str) -> dict[str, object]:
        try:
            payload = get_run_detail(active_settings, validate_run_id(run_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}.")
        return payload

    @app.get("/api/runs/{run_id}/tracks")
    def api_run_tracks(
        run_id: str,
        limit: int | None = Query(default=None),
        offset: int | None = Query(default=None),
    ) -> dict[str, object]:
        try:
            validated_run_id = validate_run_id(run_id)
            resolved_limit = normalize_limit(
                limit,
                default_limit=active_settings.default_limit,
                max_limit=active_settings.max_limit,
            )
            resolved_offset = normalize_offset(offset)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return list_tracks_for_run(
            active_settings,
            run_id=validated_run_id,
            limit=resolved_limit,
            offset=resolved_offset,
        )

    @app.get("/api/runs/{run_id}/tracks/{track_id}")
    def api_track_detail(
        run_id: str,
        track_id: int,
        segments_limit: int | None = Query(default=None),
        segments_offset: int | None = Query(default=None),
    ) -> dict[str, object]:
        try:
            validated_run_id = validate_run_id(run_id)
            resolved_limit = normalize_limit(
                segments_limit,
                default_limit=active_settings.default_limit,
                max_limit=active_settings.max_limit,
            )
            resolved_offset = normalize_offset(segments_offset)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload = get_track_detail(
            active_settings,
            run_id=validated_run_id,
            track_id=track_id,
            segments_limit=resolved_limit,
            segments_offset=resolved_offset,
        )
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail=f"Track not found for run_id={run_id} track_id={track_id}.",
            )
        return payload

    @app.get("/media/runs/{run_id}/segments/{track_id}/{segment_idx}.wav")
    def media_segment(
        run_id: str,
        track_id: int,
        segment_idx: int,
    ) -> Response:
        try:
            validated_run_id = validate_run_id(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        artifact_ref = lookup_segment_artifact_ref(
            active_settings,
            run_id=validated_run_id,
            track_id=track_id,
            segment_idx=segment_idx,
        )
        if artifact_ref is None or not artifact_ref.exists:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Segment artifact not found for "
                    f"run_id={validated_run_id} track_id={track_id} segment_idx={segment_idx}."
                ),
            )
        store = build_claim_check_store_for_uri(active_settings.base.storage, artifact_ref.uri)
        try:
            actual_checksum = store.checksum(artifact_ref.uri)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Segment artifact not found for "
                    f"run_id={validated_run_id} track_id={track_id} segment_idx={segment_idx}."
                ),
            ) from exc
        if actual_checksum != artifact_ref.checksum:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Segment artifact checksum mismatch for "
                    f"run_id={validated_run_id} track_id={track_id} segment_idx={segment_idx}."
                ),
            )
        if artifact_ref.local_path is not None:
            return FileResponse(
                artifact_ref.local_path,
                media_type="audio/wav",
                filename=artifact_ref.local_path.name,
            )

        return StreamingResponse(
            store.read_bytes_chunked(artifact_ref.uri),
            media_type="audio/wav",
            headers={"Content-Disposition": f'inline; filename="{segment_idx}.wav"'},
        )

    return app


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = ReviewSettings.from_env()
    logger = configure_logging(
        settings.base.service_name,
        run_id=settings.base.run_id,
    ).bind(
        trace_id=build_trace_id(
            {
                "run_id": settings.base.run_id,
                "service_name": settings.base.service_name,
            },
            source_service=settings.base.service_name,
        )
    )

    if args.command == "preflight":
        logger.info("Running review preflight.")
        try:
            check_runtime_dependencies(settings)
        except Exception:
            logger.bind(failure_class="startup_dependency").exception(
                "Review preflight failed."
            )
            raise
        logger.info("Review preflight passed.")
        return

    logger.info(
        "Starting review service host=%s port=%s artifacts_root=%s",
        settings.host,
        settings.port,
        settings.base.artifacts_root,
    )

    import uvicorn

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
