# Documentation Guide

This documentation is the final reader path for the bounded product release. It keeps the operator story centered on persisted truth.

## Start Here

1. `docs/architecture/system-overview.md` for system boundaries and data flow.
2. `docs/runbooks/demo.md` for the final demo and evidence command.
3. `docs/runbooks/validation.md` for smoke checks and the official containerized test path.
4. `artifacts/README.md` for generated output boundaries.
5. `data/README.md` for local dataset placement.

## Product Story

- The review console is the primary front door for run, track, and segment inspection.
- Grafana is supporting corroboration over the same persisted TimescaleDB truth.
- Kafka carries small events only; audio artifacts stay behind the claim-check boundary.
- Evidence is bounded to deterministic demo and smoke flows, not production readiness.
