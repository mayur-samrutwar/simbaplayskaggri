"""Preserved 25-melon opening used as an adversarial regression opponent."""

from __future__ import annotations

from candidates import crop as _crop


_BASE_PLAN_CROPS = _crop._plan_crops


def _monoculture_plan(obs, count):
    if count <= 0:
        return {}
    day = int(obs.get("day", 0))
    inventory = ((obs.get("market", {}) or {}).get("inventory", {}) or {})
    if day <= 3 and float(inventory.get("MELON", 10000)) < 10040:
        return {"MELON": count}
    return _BASE_PLAN_CROPS(obs, count)


def agent(obs):
    previous = _crop._plan_crops
    _crop._plan_crops = _monoculture_plan
    try:
        return _crop.agent(obs)
    finally:
        _crop._plan_crops = previous
