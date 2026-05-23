---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T02: Implement honest stage derivation

Implement the pure stage derivation helper and wire it into the review query/API payload. Prefer `review/schemas.py` for deterministic derivation and `review/queries.py` for payload assembly. Each stage item should include stable ids and human-readable labels, a constrained status value, reason text, and provenance. Rules must avoid claims about Kafka, MinIO, TimescaleDB, containers, or Grafana live health unless those signals are actually present in the review payload.

## Inputs

- `src/event_driven_audio_analytics/review/schemas.py`
- `src/event_driven_audio_analytics/review/queries.py`
- `tests/unit/test_review_queries.py`
- `tests/unit/test_review_app.py`

## Expected Output

- `src/event_driven_audio_analytics/review/schemas.py`
- `src/event_driven_audio_analytics/review/queries.py`
- `tests/unit/test_review_queries.py`
- `tests/unit/test_review_app.py`

## Verification

pytest tests/unit/test_review_queries.py tests/unit/test_review_app.py

## Observability Impact

Review API JSON gains derived status reasons and provenance for each stage, creating an inspectable contract for future UI and demo failures.
