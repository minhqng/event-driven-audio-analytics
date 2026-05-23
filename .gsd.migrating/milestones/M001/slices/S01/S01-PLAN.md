# S01: Honest pipeline status contract

**Goal:** Define and expose a tested, honest pipeline-stage status contract for selected review runs using only observable review API and persisted evidence data. This slice should leave downstream UI slices with a stable stage shape: stage id, label, status value, reason, and provenance, without claiming unobserved infrastructure health.
**Demo:** Run detail or derived review payloads have a tested, honest pipeline-stage status contract for deterministic demo states without claiming unobserved infrastructure health.

## Must-Haves

- Stage ids, labels, status values, reason text, and provenance shape are defined and stable.
- Status rules only use observable review data: run summary, validation outcomes, track/segment evidence, runtime proof, artifact existence, and `/healthz` where relevant.
- Deterministic demo states map clearly: persisted high-energy and silent-oriented runs are successful/available; validation-failure run is metadata-only or validation-degraded without fake downstream health.
- Unit/API tests cover persisted, metadata-only, error, empty, and partial evidence cases.
- Existing review API/query/runtime tests still pass.
- The review API payload is ready for S02 to render without duplicating complex derivation logic in static JavaScript.

## Proof Level

- This slice proves: Contract proof through focused unit/API tests over persisted, metadata-only validation failure, processing or writer errors, empty runs, and partial evidence/runtime proof states.

## Integration Closure

The status contract is available through the existing review API path used by the console, preferably `/api/runs/{run_id}` via query-layer enrichment. No new frontend build pipeline or runtime service is introduced. Downstream S02 can consume this contract directly from selected-run detail without duplicating status business rules in JavaScript.

## Verification

- Adds explicit derived stage reason and provenance fields so future agents can inspect why each stage is ready, degraded, failed, empty, or unknown. Failure diagnosis should be possible from API JSON and unit test fixtures without needing to infer hidden state from the UI.

## Tasks

- [ ] **T01: Pin pipeline stage contract tests** `est:45m`
  Create or extend focused tests for the pipeline-stage contract before implementation. Define the expected stage item shape and cover representative run states: persisted success, metadata-only validation failure, processing/writer error, empty/no evidence, and partial runtime or artifact proof. Keep these tests at the pure schema/query boundary so they do not require Docker or a live database.
  - Files: `tests/unit/test_review_queries.py`, `tests/unit/test_review_app.py`, `src/event_driven_audio_analytics/review/schemas.py`, `src/event_driven_audio_analytics/review/queries.py`
  - Verify: pytest tests/unit/test_review_queries.py tests/unit/test_review_app.py

- [ ] **T02: Implement honest stage derivation** `est:1h`
  Implement the pure stage derivation helper and wire it into the review query/API payload. Prefer `review/schemas.py` for deterministic derivation and `review/queries.py` for payload assembly. Each stage item should include stable ids and human-readable labels, a constrained status value, reason text, and provenance. Rules must avoid claims about Kafka, MinIO, TimescaleDB, containers, or Grafana live health unless those signals are actually present in the review payload.
  - Files: `src/event_driven_audio_analytics/review/schemas.py`, `src/event_driven_audio_analytics/review/queries.py`, `tests/unit/test_review_queries.py`, `tests/unit/test_review_app.py`
  - Verify: pytest tests/unit/test_review_queries.py tests/unit/test_review_app.py

- [ ] **T03: Verify demo API compatibility** `est:45m`
  Extend deterministic review API verification only if the new stage contract is part of the public demo payload, then run the existing review-focused test set. Confirm pinned demo ordering and existing media/runtime behavior still work. This task closes S01 by proving the status contract did not regress existing review API consumers and is ready for S02 UI rendering.
  - Files: `src/event_driven_audio_analytics/smoke/verify_review_api.py`, `tests/unit/test_verify_review_api.py`, `tests/unit/test_review_queries.py`, `tests/unit/test_review_app.py`
  - Verify: pytest tests/unit/test_review_queries.py tests/unit/test_review_app.py tests/unit/test_verify_review_api.py

## Files Likely Touched

- tests/unit/test_review_queries.py
- tests/unit/test_review_app.py
- src/event_driven_audio_analytics/review/schemas.py
- src/event_driven_audio_analytics/review/queries.py
- src/event_driven_audio_analytics/smoke/verify_review_api.py
- tests/unit/test_verify_review_api.py
