---
estimated_steps: 1
estimated_files: 8
skills_used: []
---

# T01: Inventory current Grafana evidence surface

Inspect existing Grafana dashboard JSON, provisioning YAML, operational SQL views, and demo evidence scripts. Produce a compact inventory of current dashboard panels, UIDs, queries/views used, screenshot URLs, and existing tests that can guard presentation changes.

## Inputs

- `.gsd/milestones/M002/M002-ROADMAP.md`
- `README.md`
- `docs/runbooks/demo.md`
- `docs/architecture/system-overview.md`

## Expected Output

- `.gsd/milestones/M002/slices/S01/S01-RESEARCH.md`

## Verification

Confirm `S01-RESEARCH.md` lists both dashboard UIDs, panel titles, primary SQL views, evidence script screenshot URLs, and existing/proposed test files.

## Observability Impact

Creates an inspectable map from Grafana panels to persisted evidence sources and existing verification hooks.
