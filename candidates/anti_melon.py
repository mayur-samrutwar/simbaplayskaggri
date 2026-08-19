"""Adversarial crop portfolio for the incumbent melon opening.

The incumbent commits all 25 opening tiles to melons.  This candidate plants
only enough melons to share the valuable early quotes and push the incumbent's
unmatched tail through the market's quadratic glut curve.  The other opening
tiles remain productive in faster, more resilient crops.  After the opening,
the incumbent's observation-driven crop valuation and field routing are reused
unchanged.

This file intentionally keeps no episode state.  The temporary function swap
is scoped to one synchronous agent call and restored even if the base policy
raises, so loading this candidate beside ``candidates.crop`` cannot alter the
opponent's policy.
"""

from __future__ import annotations

from candidates import crop as _crop


_BASE_PLAN_CROPS = _crop._plan_crops


def _opening_portfolio(count):
    """Allocate up to one NW field, preserving the preferred planting order."""
    remaining = max(0, min(25, int(count)))
    planned = {}
    # Fourteen melon tiles yield 84 units.  Paired with the incumbent's first
    # 84 units, this crosses the roughly 158-unit price-floor threshold; the
    # incumbent's remaining melons therefore earn almost nothing.
    for crop, target in (
        ("MELON", 14),
        ("TOMATO", 2),
        ("CARROT", 4),
        ("WHEAT", 5),
    ):
        quantity = min(target, remaining)
        if quantity:
            planned[crop] = quantity
            remaining -= quantity
    return planned


def _anti_melon_plan(obs, count):
    day = int(obs.get("day", 0))
    inventory = ((obs.get("market", {}) or {}).get("inventory", {}) or {})
    # Restrict the fixed allocation to seed shopping on the opening day.  The
    # full 25-seed buffer is bought then, so subsequent planting can consume it
    # without repeating the opening after early carrot vacancies appear.
    if day == 0 and float(inventory.get("MELON", 10000)) < 10040:
        return _opening_portfolio(count)
    return _BASE_PLAN_CROPS(obs, count)


def agent(obs):
    """Kaggle entry point using the bounded anti-melon opening."""
    previous = _crop._plan_crops
    _crop._plan_crops = _anti_melon_plan
    try:
        return _crop.agent(obs)
    finally:
        _crop._plan_crops = previous
