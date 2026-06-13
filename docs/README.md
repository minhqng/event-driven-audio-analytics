# Documentation Guide

This documentation is the final reader path for the bounded FMA-Small research system. It keeps the operator story centered on persisted truth and the thesis topic: event-driven microservices for near-real-time audio analytics on a private-cloud-style platform.

## Start Here

0. `docs/bao-cao-de-tai-event-driven-audio-analytics.md` for the thesis report draft and its evidence manifest pointer.
1. `docs/architecture/system-overview.md` for system boundaries and data flow.
2. `docs/runbooks/demo.md` for the final demo and evidence command.
3. `docs/runbooks/validation.md` for smoke checks and the official containerized test path.
4. `docs/runbooks/final-release-validation-scenarios.md` for the high-value final release scenario scan.
5. `docs/runbooks/k3s.md` for the bounded private-cloud deployment variant.
6. `artifacts/README.md` for generated output boundaries.
7. `data/README.md` for local dataset placement.

## Product Story

- The review console is the primary front door for run, track, and segment inspection.
- Grafana is supporting corroboration over the same persisted TimescaleDB truth.
- Kafka carries small events only; audio artifacts stay behind the claim-check boundary.
- Dataset exports and evaluation artifacts are generated from persisted FMA-Small truth.
- Evidence is bounded to deterministic demo, smoke, MinIO, K3s, and evaluation flows, not production readiness.
- Final release validation is scenario-driven and prioritizes dataset correctness,
  claim-check safety, review/export consistency, evaluation evidence, and K3s
  operator mistakes.
