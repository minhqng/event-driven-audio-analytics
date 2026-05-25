# T02 Summary: Honest stage derivation

## Outcome

Completed. `/api/runs/{run_id}` now includes `pipeline_stages` with stable `id`, `label`, `value`, `reason`, and `provenance` fields. The derivation remains server-side in the review schema/query layer and uses only observable review payload evidence.

## Evidence

- Contract values: `ready`, `degraded`, `failed`, `empty`, `unknown`.
- Stage ids: `metadata`, `validation`, `features`, `artifacts`, `review`.
- Official container test pass: `tests/unit/test_review_queries.py`, `tests/unit/test_review_app.py`, `tests/unit/test_verify_review_api.py` -> `31 passed`.

