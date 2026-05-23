# M001: Review console demo UI upgrade

**Vision:** Nâng cấp phần giao diện của project event-driven audio analytics đồ án để khi mở demo, giảng viên thấy được luồng dữ liệu, kết quả phân tích, trạng thái hệ thống, và bằng chứng hoạt động một cách trực quan hơn hiện tại.

## Success Criteria

- The review console opens at the demo entrypoint and presents the narrative order: pipeline flow, run outcome, audio analysis, and system or evidence corroboration.
- A pipeline stage diagram is visible and each stage has an honest status derived from observable review API or persisted evidence data.
- API health and auto-refresh freshness are visible, including stale and error states.
- Deterministic demo runs are easy to distinguish by success, validation failure, and evidence availability.
- Audio analytics results use concise Vietnamese-first copy with English technical terms where useful.
- Grafana remains a supporting evidence path rather than the first required surface.
- Missing data, failed API calls, and media or segment gaps produce clear localized fallback messages.
- No React, Vite, Node, or new frontend build pipeline is introduced.
- Existing tests pass, new status behavior is tested, and browser verification evidence is produced.

## Slices

- [ ] **S01: Honest pipeline status contract** `risk:high` `depends:[]`
  > After this: Run detail or derived review payloads have a tested, honest pipeline-stage status contract for deterministic demo states without claiming unobserved infrastructure health.

- [ ] **S02: Data driven pipeline diagram** `risk:high` `depends:[S01]`
  > After this: Selecting a demo run in the review console updates a data-driven pipeline diagram with stage status labels, reasons, and accessible visual states from real review data.

- [ ] **S03: Refresh and fallback states** `risk:medium` `depends:[S02]`
  > After this: The review console visibly reports API health, last successful refresh, stale or failed refresh state, empty runs, failed run loads, and localized media or segment gaps without breaking the page.

- [ ] **S04: Bilingual demo narrative polish** `risk:medium` `depends:[S02]`
  > After this: The review console presents a Vietnamese-first demo story with professional academic styling, clear deterministic run cards, audio result explanations, and Grafana as supporting evidence.

- [ ] **S05: Final browser evidence integration** `risk:medium` `depends:[S03,S04]`
  > After this: The local demo entrypoint is verified end to end with tests and browser evidence showing the final review console story, status indicators, run outcomes, and no regressions to evidence-script readiness markers.

## Boundary Map

### S01 → S02

Produces:
- Stable pipeline stage status contract for selected runs, including stage id, label, value, reason, and provenance.
- Tests proving status derivation for persisted, metadata-only, error, empty, and partial evidence states.

Consumes:
- Existing review run summaries, run detail payloads, validation outcomes, runtime proof, and artifact evidence.

### S02 → S03

Produces:
- Data-driven pipeline diagram in the static review console.
- Preserved body readiness markers: `data-review-ready`, `data-selected-run-id`, `data-selected-track-id`, and error marker behavior.

Consumes:
- S01 status contract and existing review API loading flow.

### S02 → S04

Produces:
- Stable selected-run UI structure and stage rendering areas for narrative copy and visual polish.

Consumes:
- S01 status contract and existing review console layout.

### S03 and S04 → S05

Produces:
- Health, refresh, stale/error, empty, and localized fallback surfaces.
- Vietnamese-first narrative, run outcome cards, audio explanation surfaces, and Grafana support path.

Consumes:
- Final assembled FastAPI-served review console at the local demo entrypoint.
