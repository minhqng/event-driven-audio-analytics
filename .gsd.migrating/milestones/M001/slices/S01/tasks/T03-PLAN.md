---
estimated_steps: 1
estimated_files: 4
skills_used: []
---

# T03: Verify demo API compatibility

Extend deterministic review API verification only if the new stage contract is part of the public demo payload, then run the existing review-focused test set. Confirm pinned demo ordering and existing media/runtime behavior still work. This task closes S01 by proving the status contract did not regress existing review API consumers and is ready for S02 UI rendering.

## Inputs

- `src/event_driven_audio_analytics/review/schemas.py`
- `src/event_driven_audio_analytics/review/queries.py`
- `src/event_driven_audio_analytics/smoke/verify_review_api.py`
- `tests/unit/test_verify_review_api.py`
- `tests/unit/test_review_queries.py`
- `tests/unit/test_review_app.py`

## Expected Output

- `src/event_driven_audio_analytics/smoke/verify_review_api.py`
- `tests/unit/test_verify_review_api.py`
- `tests/unit/test_review_queries.py`
- `tests/unit/test_review_app.py`

## Verification

pytest tests/unit/test_review_queries.py tests/unit/test_review_app.py tests/unit/test_verify_review_api.py

## Observability Impact

Smoke-verifier expectations document which stage-status fields are part of the deterministic demo API contract, making missing or malformed status evidence easy to detect.
