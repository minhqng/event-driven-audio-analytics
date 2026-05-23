# M001 Context Draft

## Vision
Nâng cấp phần giao diện của project event-driven audio analytics đồ án để khi mở demo, giảng viên thấy được luồng dữ liệu, kết quả phân tích, trạng thái hệ thống, và bằng chứng hoạt động một cách trực quan hơn hiện tại.

## Primary Work Type
UI/frontend plus demo storytelling over an existing data pipeline.

## Approved Scope
- Primary demo surface: existing FastAPI review console at `http://localhost:8080/?demo=1`.
- Supporting surface: Grafana dashboards at `http://localhost:3000`, used as corroboration after the review story is clear.
- Demo narrative order: “pipeline chạy ra sao” → “run nào thành công/thất bại” → “audio được phân tích thế nào” → “bằng chứng hệ thống”.
- Pain points: current UI is hard to understand and lacks live status.
- Language: bilingual Vietnamese/English.
- Keep the review layer read-only and demo-oriented.

## Architecture Direction
- Enhance the existing static review console: `src/event_driven_audio_analytics/review/static/index.html`, `styles.css`, and `app.js`.
- Do not introduce React, Vite, Node, or a new frontend build pipeline.
- Keep FastAPI as the serving/API layer.
- Add small read-only API fields/endpoints only where existing responses cannot express live/system status.
- Use FastAPI static asset serving already present in `review.app:create_app`.
- Preserve package-data static asset packaging in `pyproject.toml`.

## Presentation Architecture
- Pipeline visualization should be a stage diagram whose stage status changes based on data/API state, not just a static illustration.
- Live status should include all three meanings requested by the user:
  1. service/API is alive,
  2. data auto-refreshes,
  3. individual service/pipeline stages show status.
- Visual tone: academic/professional, appropriate for a thesis/project defense, not flashy consumer-app styling.

## Evidence From Codebase
- `src/event_driven_audio_analytics/review/app.py` serves a read-only FastAPI review UI and APIs: `/`, `/healthz`, `/api/runs`, `/api/runs/{run_id}`, `/api/runs/{run_id}/tracks`, track detail, and media segment routes.
- `src/event_driven_audio_analytics/review/static/index.html`, `app.js`, and `styles.css` implement the current review console.
- `docs/runbooks/demo.md` says to open the review console first and use Grafana only after the review story is clear.
- `pyproject.toml` has no frontend build toolchain and packages `event_driven_audio_analytics.review` static assets.
- `tests/unit/test_review_app.py`, `tests/unit/test_review_queries.py`, and `tests/unit/test_review_runtime.py` already cover review API/query/runtime behavior.

## Scope Draft
### In Scope
- Improve review console as the first surface seen by the instructor.
- Make the pipeline flow understandable visually and narratively.
- Surface run success/failure status clearly.
- Explain audio analytics results in bilingual labels/copy.
- Add live/system status: API health, auto-refresh, and stage-level status.
- Keep Grafana as supporting evidence rather than replacing the review console.

### Out of Scope
- Rebuilding the audio analytics pipeline.
- Changing Kafka/TimescaleDB/MinIO architecture unless required to expose read-only status.
- New model training or model serving.
- Turning Grafana into the primary product UI.
- Authentication/user roles unless requested later.

## Open Questions
- Exact derivation rules for each pipeline stage status.
- Error/fallback behavior when health/status APIs fail during a live demo.
- Quality bar for browser/manual verification and screenshot evidence.
