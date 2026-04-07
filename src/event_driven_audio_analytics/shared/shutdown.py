"""Signal helpers for graceful shutdown of long-lived service loops."""

from __future__ import annotations

from collections.abc import Callable
import signal
from threading import Event
from types import FrameType


def install_shutdown_event() -> tuple[Event, Callable[[], None]]:
    """Install SIGINT/SIGTERM handlers that flip a shared stop event."""

    stop_requested = Event()
    previous_handlers = {
        current_signal: signal.getsignal(current_signal)
        for current_signal in (signal.SIGINT, signal.SIGTERM)
    }

    def _request_shutdown(signum: int, _frame: FrameType | None) -> None:
        del signum
        stop_requested.set()

    for current_signal in previous_handlers:
        signal.signal(current_signal, _request_shutdown)

    def _restore_handlers() -> None:
        for current_signal, previous_handler in previous_handlers.items():
            signal.signal(current_signal, previous_handler)

    return stop_requested, _restore_handlers
