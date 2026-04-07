"""Unit coverage for graceful shutdown signal helpers."""

from __future__ import annotations

import signal

from event_driven_audio_analytics.shared.shutdown import install_shutdown_event


def test_install_shutdown_event_sets_stop_flag_and_restores_handlers() -> None:
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    stop_requested, restore_handlers = install_shutdown_event()
    try:
        assert not stop_requested.is_set()

        sigint_handler = signal.getsignal(signal.SIGINT)
        assert callable(sigint_handler)
        sigint_handler(signal.SIGINT, None)
        assert stop_requested.is_set()

        stop_requested.clear()
        sigterm_handler = signal.getsignal(signal.SIGTERM)
        assert callable(sigterm_handler)
        sigterm_handler(signal.SIGTERM, None)
        assert stop_requested.is_set()
    finally:
        restore_handlers()

    assert signal.getsignal(signal.SIGINT) is previous_sigint
    assert signal.getsignal(signal.SIGTERM) is previous_sigterm
