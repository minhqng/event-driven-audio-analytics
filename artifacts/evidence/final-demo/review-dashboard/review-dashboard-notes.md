# Demo Artifact Notes

This review/Grafana artifact pack supports the thesis evidence story for a bounded FMA-Small event-driven microservices system. The review console is the primary inspection surface; Grafana corroborates persisted TimescaleDB truth.

## Run Review Console

- `review-console.png` captures the read-only `Run Review Console` in demo mode, pinned to `demo-high-energy`.
- The review console is the primary demo surface: it shows run state, validation outcomes, track summaries, segment artifacts, and secondary runtime proof without forcing the audience into Grafana first.
- `review-api.json` is the authoritative machine-readable verification output from `verify_review_api` for the review surface.

## Audio Quality Dashboard

- `audio-quality-dashboard.png` captures the `Audio Quality` dashboard with the recent-demo `now-6h` time window.
- `Segment RMS Over Time` proves the high-energy run stays closer to `0 dB` than the silent-oriented run.
- `Silent Segment Ratio By Run` proves the silent-oriented run contains silent segments while the high-energy run does not.
- `Persisted Segment Count By Run` proves validated runs reached `audio_features` persistence and the validation-failure run did not.
- `Validation Outcomes By Run` proves the validation-failure case is an ingestion-side `silent` rejection, not a hidden downstream failure.
- `Run Quality Summary Table` is the compact reporting table for slide and report handoff.

## System Health Dashboard

- `system-health-dashboard.png` captures the `System Health` dashboard with the same recent-demo time window.
- `Persisted Segment Throughput` proves the bounded demo produced real sink-side throughput.
- `Processing Latency Over Time` and `Writer DB Latency By Topic` prove processing and persistence latency stayed observable on real data.
- `Claim-Check Artifact Write Latency` proves the claim-check boundary has measurable artifact-write cost.
- `Track Validation Error Rate By Run` and `Operational Summary Table` prove the validation-failure run is visible as an operational signal instead of disappearing silently.

## Supporting Files

- `review-dashboard-summary.json` is the machine-readable verification output from `verify_dashboard_demo`.
- `grafana-api.json` proves the dashboards were auto-loaded through Grafana provisioning rather than click-ops.
- `review-api.json` proves the new review surface is reachable and exposes the deterministic demo runs with track/segment detail.
