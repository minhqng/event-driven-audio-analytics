# S01: Grafana presentation contract

**Goal:** Define the Grafana demo story and panel-level contract so dashboard improvements remain honest, presentation-friendly, and grounded in observable persisted data.
**Demo:** After this: The milestone has a written panel narrative that explains what each dashboard should prove, what it must not claim, and how a presenter should read it.

## Must-Haves

- A slice context or research artifact documents the Grafana presentation narrative.
- Existing Audio Quality and System Health panels are inventoried with their data source, presentation purpose, and no-overclaim boundary.
- The contract identifies concrete downstream edits for titles, descriptions, units, legends, thresholds, layout, and tests.
- Verification confirms the contract references real dashboard files, SQL views, and demo evidence scripts.

## Proof Level

- This slice proves: documentation plus static contract inspection

## Integration Closure

S01 produces the written contract consumed by S02 and S03. It does not edit dashboard JSON yet; it defines what the dashboard JSON must communicate and how future tests should lock that presentation contract.

## Verification

- Makes dashboard observability explicit by documenting what each panel proves, where the data comes from, and what the presenter must not claim from Grafana alone.

## Tasks

- [x] **T01: Inventory current Grafana evidence surface** `est:45m`
  Inspect existing Grafana dashboard JSON, provisioning YAML, operational SQL views, and demo evidence scripts. Produce a compact inventory of current dashboard panels, UIDs, queries/views used, screenshot URLs, and existing tests that can guard presentation changes.
  - Files: `infra/grafana/dashboards/audio_quality.json`, `infra/grafana/dashboards/system_health.json`, `infra/grafana/provisioning/dashboards/dashboards.yaml`, `infra/grafana/provisioning/datasources/timescaledb.yaml`, `infra/sql/003_operational_views.sql`, `scripts/demo/generate-dashboard-evidence.sh`, `scripts/demo/generate-dashboard-evidence.ps1`, `tests/unit/test_grafana_provisioning.py`
  - Verify: Confirm `S01-RESEARCH.md` lists both dashboard UIDs, panel titles, primary SQL views, evidence script screenshot URLs, and existing/proposed test files.

- [ ] **T02: Write Grafana presentation contract** `est:60m`
  Write the presentation contract for Grafana: intended reading order, presenter script bullets, panel-by-panel purpose, allowed claims, forbidden overclaims, label/unit/threshold guidance, and downstream acceptance checklist for S02/S03/S04.
  - Files: `.gsd/milestones/M002/slices/S01/S01-CONTEXT.md`
  - Verify: Review `S01-CONTEXT.md` for required sections: narrative order, dashboard purposes, panel contract, no-overclaim rules, visual guidance, and downstream test targets.

- [ ] **T03: Verify contract references and downstream readiness** `est:30m`
  Validate the S01 contract against the repository reality. Check that referenced files exist, dashboard UIDs and titles match JSON, SQL view names exist, evidence script URLs match dashboard UIDs, and the downstream task checklist is actionable for S02 through S04.
  - Files: `.gsd/milestones/M002/slices/S01/S01-CONTEXT.md`, `.gsd/milestones/M002/slices/S01/S01-RESEARCH.md`
  - Verify: Run a small static verification command or script that checks referenced dashboard files, UIDs, SQL view names, and evidence URLs; record pass/fail evidence in the task summary.

## Files Likely Touched

- infra/grafana/dashboards/audio_quality.json
- infra/grafana/dashboards/system_health.json
- infra/grafana/provisioning/dashboards/dashboards.yaml
- infra/grafana/provisioning/datasources/timescaledb.yaml
- infra/sql/003_operational_views.sql
- scripts/demo/generate-dashboard-evidence.sh
- scripts/demo/generate-dashboard-evidence.ps1
- tests/unit/test_grafana_provisioning.py
- .gsd/milestones/M002/slices/S01/S01-CONTEXT.md
- .gsd/milestones/M002/slices/S01/S01-RESEARCH.md
