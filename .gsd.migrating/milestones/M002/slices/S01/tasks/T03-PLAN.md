---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T03: Verify contract references and downstream readiness

Validate the S01 contract against the repository reality. Check that referenced files exist, dashboard UIDs and titles match JSON, SQL view names exist, evidence script URLs match dashboard UIDs, and the downstream task checklist is actionable for S02 through S04.

## Inputs

- `infra/grafana/dashboards/audio_quality.json`
- `infra/grafana/dashboards/system_health.json`
- `infra/sql/003_operational_views.sql`
- `scripts/demo/generate-dashboard-evidence.sh`
- `scripts/demo/generate-dashboard-evidence.ps1`

## Expected Output

- `.gsd/milestones/M002/slices/S01/tasks/T03-SUMMARY.md`

## Verification

Run a small static verification command or script that checks referenced dashboard files, UIDs, SQL view names, and evidence URLs; record pass/fail evidence in the task summary.

## Observability Impact

Prevents stale or fictional presentation guidance by verifying contract references against actual dashboard and evidence files.
