# M001: Review console demo UI upgrade

**Gathered:** 2026-05-23
**Status:** Ready for planning

## Project Description

This milestone improves the demo-facing review console for the event-driven audio analytics project so a thesis/demo audience can understand the pipeline flow, run outcomes, audio analysis results, system status, and supporting evidence from one clear browser-first story. The work builds on the existing FastAPI-served static review UI and keeps Grafana as corroborating evidence, not the primary product surface.

## Why This Milestone

The current demo has working backend evidence, deterministic runs, and Grafana dashboards, but the first screen is not yet clear enough for an instructor or reviewer to quickly understand what happened in the pipeline. The milestone exists to turn existing persisted analytics and evidence into an understandable demo narrative without rebuilding the data pipeline or introducing a new frontend stack.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Open the review console in a browser and explain the demo in this order: pipeline flow, run success/failure, audio analysis results, and system/evidence corroboration.
- See a read-only pipeline stage diagram whose statuses are derived from review API health, auto-refresh state, and persisted run/track/segment data.
- Select deterministic demo runs and immediately understand whether each run succeeded, failed validation, or has partial/missing evidence.
- Explain key audio analytics results using bilingual Vietnamese-first labels with English technical terms where useful.
- Use Grafana dashboards as a secondary evidence surface after the review console story is clear.

### Entry point / environment

- Entry point: `http://localhost:8080/?demo=1`
- Environment: local browser against the project demo stack
- Live dependencies involved: FastAPI review service, persisted analytics database state, media segment artifacts, Grafana dashboards as supporting evidence

## Completion Class

- Contract complete means: review API/status derivation behavior is covered by unit tests or existing API tests, including healthy, empty, failed, and partial-data cases where practical.
- Integration complete means: the browser review console renders deterministic demo runs and uses real review APIs rather than static mock data.
- Operational complete means: during a local demo run, the UI visibly communicates API health, auto-refresh freshness, data availability, and fallback/error states without requiring code inspection.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A user can open the local review console, follow the pipeline story, select deterministic demo runs, and explain run outcomes without needing Grafana first.
- The review console shows stage-level status from persisted review data and API health without claiming deeper real-time infrastructure health that is not actually exposed.
- The UI handles missing/empty/failing review data with clear read-only fallback messages that are safe for a live demo.
- Existing review API/runtime tests still pass, and any new status derivation logic has focused test coverage.
- Browser verification captures the final review console state at the demo entry point; this cannot be considered done from unit tests alone.

## Architectural Decisions

### Keep the existing static review console

**Decision:** Enhance the existing FastAPI-served static HTML/CSS/JavaScript review console instead of introducing React, Vite, Node, or another frontend build pipeline.

**Rationale:** The review console is already the demo front door, the project packages static review assets through the Python application, and the milestone is presentation/storytelling over existing data rather than a new frontend product. Avoiding a new toolchain lowers demo risk and keeps deployment aligned with the current Python services.

**Alternatives Considered:**
- Add a frontend framework — richer component model, but unnecessary build/deploy complexity for this milestone.
- Make Grafana the primary interface — strong for operations evidence, but weaker for the review-first narrative and conflicts with the established demo flow.

---

### Treat live status as demo-live, not full infrastructure observability

**Decision:** The review console should show status derived from review API health, auto-refresh freshness, and persisted run/track/segment evidence. It should not imply full real-time Kafka, TimescaleDB, MinIO, or container orchestration health unless that data is explicitly exposed through existing or newly added read-only endpoints.

**Rationale:** The user asked for live status in three senses: API alive, data auto-refreshing, and pipeline/service stages showing state. The safest implementation is honest status tied to data the review layer can actually observe, avoiding misleading green checks for infrastructure internals.

**Alternatives Considered:**
- Full distributed health dashboard — potentially useful, but outside the review-console demo scope and overlaps with Grafana.
- Static pipeline illustration — simpler, but does not satisfy the live/status requirement.

---

### Use Vietnamese-first demo copy with English technical terms

**Decision:** UI headings and explanations should prioritize Vietnamese-friendly demo narration while preserving English technical terms in parentheses or short labels where they help map to the project architecture.

**Rationale:** The demo audience needs quick comprehension, while the project domain and codebase use English terms such as pipeline, run, features, segments, and validation. Vietnamese-first copy supports presentation clarity without hiding technical vocabulary.

**Alternatives Considered:**
- English-only labels — consistent with code, but less effective for a Vietnamese thesis/demo presentation.
- Fully duplicated bilingual text everywhere — comprehensive, but likely noisy and harder to scan during a live demo.

## Error Handling Strategy

The review layer remains read-only and demo-oriented. Failures should be visible, calm, and specific rather than hidden behind generic loading states. If API health fails, the UI should show the review service as unavailable or degraded and avoid pretending that data is fresh. If runs cannot be loaded, the user should see a clear message explaining that run data is unavailable and suggesting the demo evidence generation path or stack state as the likely cause. If there are no runs, the empty state should explain what the deterministic demo runs normally represent. If a selected run has no tracks, features, or segments, the UI should distinguish validation failure from missing evidence where the available data allows it. Auto-refresh should expose last refresh time and stale/paused/error state. Media segment failures should not break the whole page; they should be localized to the relevant track or segment display.

## Risks and Unknowns

- Stage status derivation can overclaim system health — the implementation must map each stage to observable review data and label unknown states honestly.
- Browser demo quality depends on real local demo data — verification must use the demo entry point, not just static file inspection.
- Bilingual copy can become visually noisy — copy should be concise, Vietnamese-first, and focused on presentation clarity.
- Existing static JavaScript may become hard to maintain if the UI grows too much — slices should prefer small data/view helpers over a monolithic script rewrite.

## Existing Codebase / Prior Art

- Review FastAPI application — serves the read-only review console, health endpoint, run APIs, track detail APIs, and media segment routes.
- Review static assets — existing HTML, CSS, and JavaScript for the browser console that should be enhanced in place.
- Review query/runtime tests — existing unit coverage around review behavior that should remain green and guide API/status changes.
- Demo runbook — establishes the review console as the first demo surface and Grafana as corroborating evidence.
- Grafana dashboards — supporting evidence for audio quality and system health after the review story is clear.
- Python packaging configuration — already packages review static assets without a separate frontend build step.

## Relevant Requirements

- No formal GSD requirement IDs exist yet. This milestone should create or validate requirements for review-console clarity, read-only demo status, bilingual presentation, and browser-verifiable demo evidence before implementation is marked complete.

## Scope

### In Scope

- Improve the review console as the first surface seen by the instructor or reviewer.
- Add a pipeline visualization with stage status derived from observable review/API state.
- Surface run success, validation failure, partial evidence, and missing-data states clearly.
- Explain audio analytics results with concise Vietnamese-first copy and English technical terms where helpful.
- Add visible API health, auto-refresh freshness, and stage-level/demo-live status indicators.
- Add or extend small read-only API fields/endpoints only where the current review responses cannot express required status.
- Keep Grafana links or references as supporting evidence after the review console narrative.
- Preserve static asset packaging and the current Python service deployment model.

### Out of Scope / Non-Goals

- Rebuilding the audio analytics pipeline.
- Replacing the static review console with React, Vite, Node, or another frontend build pipeline.
- Making Grafana the primary product UI.
- Adding authentication, user roles, write actions, or mutable review workflows.
- Training or serving new machine learning models.
- Changing Kafka, TimescaleDB, MinIO, or container architecture except for minimal read-only status exposure if strictly necessary.
- Claiming real-time distributed infrastructure health that the review layer cannot observe.

## Technical Constraints

- The review console must remain served by FastAPI with static HTML/CSS/JavaScript assets.
- The review layer must remain read-only and safe for demo use.
- New status data must be derived from existing persisted review data or small read-only API additions.
- The UI must work at the established local demo entry point.
- Static assets must remain packageable through the existing Python packaging configuration.
- Styling should be academic/professional, not flashy consumer-app styling.
- Any auto-refresh behavior must avoid noisy polling failures and must surface stale/error state clearly.

## Integration Points

- FastAPI review service — serves the browser UI and provides health/run/track/media APIs.
- Persisted analytics database state — source of run, track, feature, validation, and segment availability signals.
- Media segment artifact storage — source for playable or downloadable segment evidence when available through review routes.
- Grafana dashboards — secondary evidence surface linked or referenced after the review narrative.
- Demo evidence/runbook flow — supplies deterministic runs and screenshot/evidence expectations for validation.

## Testing Requirements

Testing should combine contract, integration, and browser evidence. Unit/API tests should cover any new status derivation rules, especially healthy data, validation-failure data, empty data, and partial evidence. Existing review API/runtime tests must continue to pass. Static UI changes should be verified in a browser against the local demo entry point, with console/network checks where practical. Final verification should include screenshot or browser evidence showing the pipeline story, status indicators, run outcomes, and fallback behavior if feasible. The milestone should not be considered complete from code inspection alone.

## Acceptance Criteria

- The review console opens at the demo entry point and presents the narrative order: pipeline flow, run outcome, audio analysis, and system/evidence corroboration.
- A pipeline stage diagram is visible and each stage has an honest status derived from observable review/API data.
- API health and auto-refresh freshness are visible, including stale/error states.
- Deterministic demo runs are easy to distinguish by success, validation failure, and evidence availability.
- Audio analytics results are explained with concise Vietnamese-first copy and English technical terms where useful.
- Grafana remains a supporting evidence path rather than the first required surface.
- Missing data, failed API calls, and media/segment gaps produce clear localized fallback messages.
- No new frontend build pipeline is introduced.
- Existing tests pass, new status behavior is tested, and browser verification evidence is produced.

## Open Questions

- Exact stage names and derivation rules — current recommendation is to define stages only from observable review data: API health, run metadata, validation status, feature availability, segment availability, persistence/review availability, and Grafana/evidence links.
- Whether a new read-only status endpoint is needed — current recommendation is to avoid one unless existing run/track responses cannot express stage status without fragile client-side inference.
- How much fallback behavior can be browser-tested automatically — current recommendation is to at least test API/status contracts and manually or browser-verify one degraded/empty state if the demo fixtures make it practical.
