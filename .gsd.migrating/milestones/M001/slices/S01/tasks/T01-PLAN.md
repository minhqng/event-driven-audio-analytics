---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T01: Pin pipeline stage contract tests

Create or extend focused tests for the pipeline-stage contract before implementation. Define the expected stage item shape and cover representative run states: persisted success, metadata-only validation failure, processing/writer error, empty/no evidence, and partial runtime or artifact proof. Keep these tests at the pure schema/query boundary so they do not require Docker or a live database.

## Inputs

- `.gsd/milestones/M001/M001-CONTEXT.md`
- `.gsd/milestones/M001/M001-ROADMAP.md`
- `src/event_driven_audio_analytics/review/schemas.py`
- `src/event_driven_audio_analytics/review/queries.py`
- `tests/unit/test_review_queries.py`
- `tests/unit/test_review_app.py`

## Expected Output

- `tests/unit/test_review_queries.py`
- `tests/unit/test_review_app.py`

## Verification

pytest tests/unit/test_review_queries.py tests/unit/test_review_app.py

## Observability Impact

Tests pin the diagnostic shape of derived status reasons and provenance, making future status regressions visible before UI work starts.
