# M002: Grafana presentation upgrade

**Vision:** Nâng cấp Grafana để phục vụ phần trình bày đồ án: người xem có thể mở dashboard, thấy ngay chất lượng âm thanh, trạng thái pipeline, bằng chứng persisted TimescaleDB, và hiểu các chỉ số chính mà không cần giải thích dài dòng hoặc click thủ công nhiều bước.

## Success Criteria

- Grafana dashboards have a clear presentation order: audio quality evidence first, then system health and pipeline corroboration.
- Panel titles, descriptions, units, thresholds, legends, and layout are readable in kiosk or screenshot mode for a thesis demo audience.
- Dashboards remain file-provisioned and read-only over TimescaleDB persisted truth; no click-ops or new frontend stack is introduced.
- Docker Compose and K3s dashboard copies stay aligned or have an explicit sync mechanism verified by tests.
- Dashboard evidence scripts produce API snapshots, screenshots, and notes that explain how to present Grafana as supporting evidence.
- Verification includes JSON/provisioning tests and, where environment permits, local browser or evidence-script confirmation.

## Slices

- [ ] **S01: S01** `risk:high` `depends:[]`
  > After this: After this: The milestone has a written panel narrative that explains what each dashboard should prove, what it must not claim, and how a presenter should read it.

- [ ] **S02: Audio quality dashboard polish** `risk:medium` `depends:[S01]`
  > After this: After this: The Audio Quality dashboard is easier to explain in kiosk or screenshot mode, with clearer titles, descriptions, units, and ordering.

- [ ] **S03: System health dashboard polish** `risk:medium` `depends:[S01]`
  > After this: After this: The System Health dashboard tells a clear operational corroboration story from persisted metrics and run summaries.

- [ ] **S04: Provisioning parity and evidence script alignment** `risk:high` `depends:[S02,S03]`
  > After this: After this: Dashboard JSON parity, provisioning paths, UIDs, screenshot URLs, and artifact notes agree across local and K3s-facing assets.

- [ ] **S05: Final Grafana presentation verification** `risk:medium` `depends:[S04]`
  > After this: After this: The local evidence path or browser verification proves the upgraded Grafana dashboards load and can support the intended presentation story.

## Boundary Map

### S01 → S02 and S03

Produces:
- Presentation narrative and panel contract for Grafana.
- Constraints for labels, units, thresholds, and no-overclaim wording.

Consumes:
- Existing Audio Quality and System Health dashboard JSON.
- Existing operational SQL views and demo evidence flow.

### S02 and S03 → S04

Produces:
- Updated dashboard JSON content for Compose provisioning.
- Expected panel UIDs, titles, and layout structure.

Consumes:
- S01 narrative contract.

### S04 → S05

Produces:
- K3s and Compose parity checks plus evidence script expectations.
- Updated runbook or artifact-note wording for presentation.

Consumes:
- Final dashboard files from S02 and S03.
