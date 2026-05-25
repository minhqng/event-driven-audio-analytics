# S02 Summary: Data-driven pipeline diagram

## Outcome

Completed. The static review console now renders the pipeline diagram from `payload.pipeline_stages.items` instead of hard-coded stage cards. The browser consumes the API contract directly and does not re-derive pipeline business logic.

## Evidence

- Updated files: `src/event_driven_audio_analytics/review/static/index.html`, `app.js`, `styles.css`.
- Stage visual states map from API values: `ready`, `degraded`, `failed`, `empty`, `unknown`.
- Each stage shows short label, status badge, reason text/title, and provenance badge.
- Body markers remain in use: `data-review-ready`, `data-selected-run-id`, `data-selected-track-id`, `data-review-error`.
- Browser evidence: `artifacts/review-console-m001-desktop.png`, `artifacts/review-console-m001-mobile.png`.

