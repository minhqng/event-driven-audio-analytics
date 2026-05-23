---
id: T01
parent: S01
milestone: M001
key_files:
  - tests/unit/test_review_queries.py
  - tests/unit/test_review_app.py
key_decisions:
  - Keep T01 as a red-contract test task and do not implement pipeline-stage derivation until T02.
duration: 
verification_result: mixed
completed_at: 2026-05-23T10:29:02.937Z
blocker_discovered: false
---

# T01: Pinned the review pipeline-stage contract with query-level fixtures and a public API shape assertion.

**Pinned the review pipeline-stage contract with query-level fixtures and a public API shape assertion.**

## What Happened

Inspected the milestone/slice context plus existing review schemas, queries, and app tests. The query tests already define the intended red contract for `pipeline_stages`: stable stage ids, labels, constrained status values, non-empty reasons, and derived provenance, covering persisted success, metadata-only validation failure, downstream processing/writer error, empty/no-evidence, and partial runtime/artifact proof cases. I extended `tests/unit/test_review_app.py` with an API-boundary assertion that `/api/runs/{run_id}` responses preserve the same stage item shape when the query layer returns it, keeping the contract visible at the public review route without requiring Docker or a live database.

## Verification

Verified the modified test files parse successfully. Ran the query test subset through the local venv with a workspace basetemp; it produced the expected red state for this test-pinning task: 14 passing tests and 5 failing pipeline-stage tests, all failing with `KeyError: 'pipeline_stages'` because T02 has not implemented the contract yet. The full specified test command could not complete in the local venv because FastAPI is not installed there; this environment limitation was captured as durable project knowledge.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/unit/test_review_queries.py tests/unit/test_review_app.py via gsd_exec bash runtime` | 1 | ❌ environment: /bin/bash unavailable in gsd_exec runtime | 156ms |
| 2 | `./.venv/Scripts/python.exe -m pytest --basetemp=.pytest-tmp tests/unit/test_review_queries.py` | 1 | ✅ expected red contract: 14 passed, 5 failed on missing pipeline_stages | 190ms |
| 3 | `./.venv/Scripts/python.exe -m pytest --basetemp=.pytest-tmp tests/unit/test_review_queries.py tests/unit/test_review_app.py` | 2 | ❌ environment: local venv missing fastapi for test_review_app collection | 190ms |
| 4 | `./.venv/Scripts/python.exe AST parse for tests/unit/test_review_queries.py and tests/unit/test_review_app.py` | 0 | ✅ pass: modified tests parse successfully | 300ms |

## Deviations

Added an app-level route contract assertion in addition to the query-boundary tests so the public run-detail API shape is pinned before implementation.

## Known Issues

The pinned query tests intentionally fail until T02 implements `pipeline_stages`. The local venv also lacks FastAPI, so app tests require the official containerized pytest path or review/dev extras installed.

## Files Created/Modified

- `tests/unit/test_review_queries.py`
- `tests/unit/test_review_app.py`
