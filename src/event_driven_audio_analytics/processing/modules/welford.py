"""Welford statistics placeholders."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class WelfordState:
    """Minimal state holder for online monitoring statistics."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0


def update_welford(state: WelfordState, value: float) -> WelfordState:
    """Update a scalar Welford accumulator."""

    count = state.count + 1
    delta = value - state.mean
    mean = state.mean + (delta / count)
    delta2 = value - mean
    m2 = state.m2 + (delta * delta2)
    return WelfordState(count=count, mean=mean, m2=m2)
