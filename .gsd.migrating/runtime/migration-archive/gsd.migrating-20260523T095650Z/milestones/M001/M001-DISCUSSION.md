# M001 Discussion Log

## Exchange — 2026-05-23T09:35:55.606Z

### Arch

For the implementation architecture, which path should we plan around?

- **Enhance static UI (Recommended)** — Use existing FastAPI static HTML/CSS/JS and add only small read-only API fields for live status.
- **Add frontend framework** — Introduce React/Vite or similar for richer components, but adds build/deploy complexity to a Python demo project.
- **Grafana-first integration** — Keep review console simpler and embed/link Grafana heavily, but this conflicts with review-console-as-front-door.

**Selected:** Enhance static UI (Recommended)

---
