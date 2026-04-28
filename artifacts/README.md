# Runtime Artifacts

This directory is the local claim-check and evidence output root.

## Tracked

- `runs/.gitkeep`
- `shared/.gitkeep`

## Generated

- `artifacts/runs/`: claim-check segments, manifests, and processing state
- `artifacts/evidence/`: generated evidence output
- `artifacts/demo-inputs/`: generated deterministic review-demo inputs

Generated content is ignored by git. Recreate final evidence with `scripts/demo/generate-demo-evidence.*`.
