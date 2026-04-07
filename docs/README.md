# Documentation Guide

Use this file as the entrypoint for the repo documentation.

## Start Here

- `docs/architecture/system-overview.md`: concise system boundary and service responsibilities
- `docs/runbooks/demo.md`: primary final demo and evidence path
- `docs/runbooks/validation.md`: smoke checks, test entrypoints, and validation scope
- `correctness-against-reference.md`: audio/DSP parity and correctness position against the legacy FMA-small pipeline

## Demo And Validation

- `docs/runbooks/demo.md`: full bounded demo path, including restart/replay evidence and dashboard artifacts
- `docs/runbooks/dashboard-demo.md`: dashboard-only evidence path and live presentation flow
- `docs/runbooks/validation.md`: targeted smoke scripts, containerized `pytest`, restart/replay validation, and repo-local FMA burst guidance

## Architecture And Contracts

- `docs/architecture/system-overview.md`: runtime architecture in one page
- `ARCHITECTURE_CONTRACTS.md`: locked service boundaries, event-flow rules, idempotency, and checkpoint semantics
- `event-contracts.md`: canonical event contract v1
- `docs/architecture/dashboard-interpretation.md`: what each Grafana panel proves
- `docs/architecture/ingestion-flow.md`: ingestion-owned metadata, validation, segmentation, and manifest behavior

## Status And Project Truth

- `IMPLEMENTATION_STATUS.md`: final implementation summary, verified paths, and remaining limitations
- `TASK_BOARD.md`: accepted follow-up items after the final polish pass
- `PROJECT_CONTEXT.md`: stable project framing and scope boundaries
- `REUSE_MAP.md`: legacy-pipeline reuse and refactor map

## Archive

- `docs/archive/week1-bootstrap-status.md`: retained only as delivery history; not part of the current reader path
