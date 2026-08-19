"""Opponent-aware crop opener built on the promoted crop engine.

Seed shopping waits until day 0 hour 2.  By then an ordinary crop rush has
placed public tiles and an animal rush has built public structures.  The agent
uses a 16-melon/9-wheat hedge against visible premium-crop competition and the
full 25-melon opening when the premium market appears uncontested.
"""

from __future__ import annotations

from candidates import crop as _crop


_BASE_PLAN_CROPS = _crop._plan_crops
_BASE_DESIRED_HANDS = _crop._desired_hands


def _opening_is_contested(obs):
    farms = obs.get("farms", []) or []
    me = int(obs.get("player", 0))
    opponent = 1 - me
    if opponent >= len(farms):
        return False
    farm = farms[opponent]
    melon_tiles = 0
    animal_structures = 0
    for row in farm.get("tiles", []):
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "PLANT" and tile.get("crop") == "MELON":
                melon_tiles += 1
            if tile.get("kind") in ("COOP", "PASTURE"):
                animal_structures += 1
    if melon_tiles:
        return True
    # A large invisible purchase without any livestock structures is most
    # plausibly a seed commitment whose first plant was delayed by routing.
    return animal_structures == 0 and float(farm.get("money", 3000)) < 1800


def _adaptive_plan(obs, count):
    if count <= 0:
        return {}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    market_inv = (obs.get("market", {}) or {}).get("inventory", {}) or {}
    if day == 0 and hour < 2:
        return {}
    if day <= 3 and float(market_inv.get("MELON", 10000)) < 10040:
        if _opening_is_contested(obs):
            melons = min(16, count)
            plan = {"MELON": melons}
            if count > melons:
                plan["WHEAT"] = count - melons
            return plan
        return {"MELON": count}
    return _BASE_PLAN_CROPS(obs, count)


def _adaptive_hands(farm):
    owned = sum(1 for _ in _crop._owned_cells(farm))
    return 7 if owned <= 25 else _BASE_DESIRED_HANDS(farm)


def agent(obs):
    previous_plan = _crop._plan_crops
    previous_hands = _crop._desired_hands
    _crop._plan_crops = _adaptive_plan
    _crop._desired_hands = _adaptive_hands
    try:
        return _crop.agent(obs)
    finally:
        _crop._plan_crops = previous_plan
        _crop._desired_hands = previous_hands
