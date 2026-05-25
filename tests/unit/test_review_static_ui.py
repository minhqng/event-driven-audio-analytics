from __future__ import annotations

from pathlib import Path


STATIC_ROOT = Path("src/event_driven_audio_analytics/review/static")


def test_demo_mode_uses_client_side_toggle_instead_of_hard_reload() -> None:
    index_html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'href="/?demo=1"' not in index_html
    assert 'id="demo-mode-toggle"' in index_html
    assert "/static/app.js?v=" in index_html
    assert 'document.getElementById("demo-mode-toggle")' in app_js
    assert "state.demoMode = !state.demoMode" in app_js


def test_review_console_guards_stale_async_responses() -> None:
    app_js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "activeRequestId" in app_js
    assert "function startViewRequest()" in app_js
    assert "function isCurrentRequest(requestId)" in app_js
    assert "if (!isCurrentRequest(requestId))" in app_js


def test_selected_run_is_not_overwritten_by_filtered_run_list() -> None:
    app_js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "payload.items[0].run_id" in app_js
    assert "state.selectedRunId && !payload.items.some" not in app_js
