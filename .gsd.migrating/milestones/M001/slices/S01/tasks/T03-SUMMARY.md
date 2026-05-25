# T03 Summary: Demo API compatibility

## Outcome

Completed. The review API verifier now validates `pipeline_stages` for the deterministic demo payload and still checks run ordering, persisted segment evidence, silent segment evidence, validation-failure behavior, track detail, and media paths.

## Evidence

- Live verifier pass: `docker compose exec -T review python -m event_driven_audio_analytics.smoke.verify_review_api --base-url "http://127.0.0.1:8080"`.
- `demo-high-energy`: ready metadata/validation/features/artifacts/review.
- `demo-silent-oriented`: persisted with `silent_ratio=0.25` and one silent segment.
- `demo-validation-failure`: validation degraded, features empty, artifacts empty, review degraded.
- Official container test pass: `31 passed`.

