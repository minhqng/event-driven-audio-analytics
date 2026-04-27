# TASK_BOARD.md

Post-freeze follow-up list for the current final PoC state.

This file is no longer a sprint board. It captures only the remaining work that is still acceptable to discuss after the repository has been cleaned up into its final presentation shape.

## Closed In The Current Repo

- Final reader path is in place through `README.md`, `docs/README.md`, and the runbooks under `docs/runbooks/`.
- Final demo evidence command is `scripts/demo/generate-demo-evidence.*`.
- Dashboard-only evidence command is `scripts/demo/generate-dashboard-evidence.*`.
- A read-only `review` surface is now wired into the repo as the primary run/track/segment demo layer over existing persisted truth.
- Demo bootstrap and evidence scripts now gate on review preflight plus `vw_review_tracks` readiness before declaring the stack usable.
- PowerShell demo wrappers are aligned with the bash review-first evidence path.
- Review media playback is now anchored to persisted `artifact_uri`, and review screenshot capture waits for a DOM-ready marker instead of trusting file existence alone.
- Review-finding hardening now covers path-safe `run_id` validation, artifacts-root enforcement for consumed `artifact_uri` values, non-finite JSON rejection, replay-safe processing failure metrics, and exact Python dependency pins.
- Official repo test path is `scripts/smoke/check-pytest.*`.
- Bounded restart/replay evidence exists and is documented.
- Grafana dashboards are provisioned from files and backed by real TimescaleDB queries.
- Contract, schema, model, fixture, and writer-path alignment is in place for Event Contract v1.

## Verified Entry Points

- `docker compose config`
- `run-demo.ps1` and `run-demo.sh`
- `scripts/smoke/check-pytest.ps1` and `scripts/smoke/check-pytest.sh`
- `docs/runbooks/demo.md`
- `docs/runbooks/dashboard-demo.md`
- `docs/runbooks/validation.md`

Current test baseline:

- `176 passed, 5 skipped` on the official containerized `pytest` path
- The 5 skips are the optional legacy-reference parity tests when local reference data or extra reference dependencies are unavailable
- `60 passed` on 2026-04-27 for the targeted containerized `pytest` slice covering contract/path/metric hardening

## Accepted Unfinished Items

- 100-track burst and benchmark-scale evidence are still absent from the default repo story.
- `audio.dlq` remains reserved only.
- `welford_snapshots` remains defined in SQL but not produced by the current processing runtime.
- Larger-scale replay/restart behavior beyond the bounded same-`run_id` smoke path remains unverified.

These items should stay documented honestly rather than being hidden or polished away.

## If Future Work Is Requested

1. Preserve Event Contract v1 unless an intentional coordinated version change is approved.
2. Prefer thin read-only demo surfaces backed by current persisted truth before adding new backend semantics.
3. Treat benchmark work, DLQ work, and persisted Welford work as the only meaningful follow-up items still inside the PoC narrative.
4. Keep docs honest: separate verified bounded evidence from planned or deferred work.

## A/B Synchronization Required

- Activating `audio.dlq` as a real contract and runtime flow
- Changing natural-key or checkpoint semantics
- Expanding manifest fields across service boundaries
- Changing dashboard metric names, labels, or SQL surfaces
- Any contract or schema change that crosses ingestion, processing, and writer ownership

## Do Not Start

- Kubernetes or production HA work
- Full OpenTelemetry collector/backend work
- Model serving or inference services
- Exactly-once experiments before the current at-least-once plus idempotent sink story is explicitly re-scoped
- Dashboard expansion that outruns the actual persisted data model
