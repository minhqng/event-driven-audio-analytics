# S03 Summary: Refresh and fallback states

## Outcome

Completed. The console now has lightweight auto-refresh, visible freshness state, stale/error handling that preserves the last successful payload, contextual empty states, and row-local audio artifact error messages.

## Evidence

- Auto-refresh interval: 25 seconds.
- Freshness states are exposed through `body[data-refresh-state]`: `loading`, `fresh`, `stale`, `error`.
- Fallback copy is contextual for no runs, validation outcomes, tracks, segments, failed run load, and unavailable review API.
- Media errors are scoped to the segment artifact cell.
- Browser evidence: `artifacts/review-console-m001-desktop.png`, `artifacts/review-console-m001-mobile.png`.

