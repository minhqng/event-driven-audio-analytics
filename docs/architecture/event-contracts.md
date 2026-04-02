# Event Contracts

The canonical v1 contract now lives at [event-contracts.md](../../event-contracts.md).

This file intentionally stays short to avoid duplicate field tables drifting again.

Current status:

- `event-contracts.md` is the contract source of truth for the 4 primary topics.
- `schemas/`, shared models, contract fixtures, and contract tests are aligned to that v1 definition.
- The fake-event smoke publisher now uses the canonical valid fixtures under `tests/fixtures/events/v1/`.
