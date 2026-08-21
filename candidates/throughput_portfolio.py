"""Replay-refined high-throughput portfolio.

This candidate keeps v7's replay-tested routing, storage, ROI, and liquidation
mechanics while changing only policies supported by the latest live losses:

* geese are shop-gated instead of consuming opening cash by default; and
* the herd scales by two animals per relevant shop, up to the proven calendar;
* paid premium seeds receive urgent planting priority before they expire;
* up to six uncommitted tomato/carrot cells rotate into demanded berries; and
* a twelfth worker is hired only for real backlog in a diverse town.

The scheduler is cloned into a private namespace, so benchmarking this module
beside v7 cannot mutate either agent's globals.
"""

from __future__ import annotations

import collections
import inspect
import math

from candidates import live_archetypes as live
from candidates import resilient_portfolio as v7


ANIMALS = live.ANIMALS
ANIMAL_COST = live.ANIMAL_COST
ANIMAL_PRODUCT = live.ANIMAL_PRODUCT
OUTPUT_RATE = v7.OUTPUT_RATE
ANIMAL_CAPS = v7.ANIMAL_CAPS
ANIMAL_CUTOFFS = v7.ANIMAL_CUTOFFS
BASELINE_ANIMALS = {"GOOSE": 0, "COW": 2, "SHEEP": 2}

POLICY = {
    **v7.POLICY,
    "opening_animals": {"GOOSE": 0, "COW": 2, "SHEEP": 2},
    "animal_targets": dict(BASELINE_ANIMALS),
    "opening_seeds": {"MELON": 8, "WHEAT": 7},
}
POLICIES = {**live.POLICIES, "throughput": POLICY}


def _animal_demand(obs):
    shops = live._shop_counts(obs)
    egg_shops = shops["BAKERY"] + shops["BRUNCH_SPOT"]
    return {
        # A goose is useful only after an egg-consuming shop exists.  The old
        # unconditional +1 forced one into every opening and displaced crops
        # and feed before the town was known.
        "GOOSE": 6 * egg_shops,
        "COW": 1
        + 6
        * (
            shops["PIZZA_SHOP"]
            + shops["ICE_CREAM_SHOP"]
            + shops["SMOOTHIE_SHOP"]
        ),
        "SHEEP": 1 + 12 * shops["YARN_STORE"],
    }


def _animal_goals(obs, policy=POLICY):
    """Use the v7 residual allocator without a speculative opening goose."""

    day = int(obs.get("day", 0))
    owned = v7._owned(obs)
    opening = collections.Counter(policy["opening_animals"])
    if day <= 2:
        return {
            kind: max(int(opening[kind]), int(owned[kind])) for kind in ANIMALS
        }

    shops = live._shop_counts(obs)
    egg_shops = shops["BAKERY"] + shops["BRUNCH_SPOT"]
    animal_shop_count = sum(
        shops[name]
        for name in (
            "BAKERY",
            "BRUNCH_SPOT",
            "PIZZA_SHOP",
            "ICE_CREAM_SHOP",
            "SMOOTHIE_SHOP",
            "YARN_STORE",
        )
    )
    calendar_capacity = (
        10 if day <= 5 else 14 if day <= 8 else 18 if day <= 11 else 20
    )
    capacity = min(calendar_capacity, 8 + 2 * animal_shop_count)
    floors = {
        kind: max(int(opening[kind]), int(BASELINE_ANIMALS[kind]))
        for kind in ANIMALS
    }

    opponent = v7._opponent_animals(obs)
    demand = _animal_demand(obs)
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    residual = {}
    goals = {}
    for kind in ANIMALS:
        residual[kind] = max(
            0.0,
            float(demand[kind])
            - 0.25 * float(opponent[kind]) * OUTPUT_RATE[kind],
        )
        requested = int(math.ceil(residual[kind] / OUTPUT_RATE[kind]))
        goals[kind] = min(
            int(ANIMAL_CAPS[kind]),
            max(int(floors[kind]), int(owned[kind]), requested),
        )

    capacity = max(capacity, sum(int(owned[kind]) for kind in ANIMALS))
    while sum(goals.values()) > capacity:
        choices = [
            kind
            for kind in ANIMALS
            if goals[kind] > max(int(floors[kind]), int(owned[kind]))
        ]
        if not choices:
            break

        def trim_key(kind):
            covered = goals[kind] * OUTPUT_RATE[kind]
            oversupply = max(0.0, covered - residual[kind])
            product_price = max(1, int(prices.get(ANIMAL_PRODUCT[kind], 1)))
            revenue = OUTPUT_RATE[kind] * product_price
            return oversupply, -revenue, kind

        goals[max(choices, key=trim_key)] -= 1

    engine_floor = capacity
    while sum(goals.values()) < engine_floor:
        choices = [
            kind
            for kind in ANIMALS
            if goals[kind] < int(ANIMAL_CAPS[kind])
            and (kind != "GOOSE" or egg_shops > 0 or int(owned[kind]) > 0)
        ]
        if not choices:
            break

        def engine_value(kind):
            product_price = max(1, int(prices.get(ANIMAL_PRODUCT[kind], 1)))
            fertilizer_price = max(1, int(prices.get("FERTILIZER", 100)))
            wheat_price = max(1, int(prices.get("WHEAT", 25)))
            remaining_days = max(6, 24 - day)
            return (
                OUTPUT_RATE[kind] * product_price
                + fertilizer_price
                - wheat_price
                - ANIMAL_COST[kind] / remaining_days,
                kind,
            )

        goals[max(choices, key=engine_value)] += 1

    for kind, cutoff in ANIMAL_CUTOFFS.items():
        if day > cutoff:
            goals[kind] = int(owned[kind])
    return {kind: max(int(goals[kind]), int(owned[kind])) for kind in ANIMALS}


def _crop_targets(obs, farm, policy, animal_goals):
    """Shift a small uncommitted sleeve toward berries before seed cutoff."""

    targets = collections.Counter(v7._crop_targets(obs, farm, policy, animal_goals))
    day = int(obs.get("day", 0))
    shops = live._shop_counts(obs)
    berry_shops = sum(
        shops[name]
        for name in (
            "BRUNCH_SPOT",
            "ICE_CREAM_SHOP",
            "SMOOTHIE_SHOP",
            "FARMERS_MARKET",
        )
    )
    if not 6 <= day <= 13 or berry_shops < 2:
        return targets

    active = live._crop_counts(farm)
    seeds = collections.Counter((obs.get("private", {}) or {}).get("seeds", {}) or {})
    berry_goal = min(34, 24 + 2 * berry_shops)
    extra = min(6, max(0, berry_goal - int(targets["STRAWBERRY"])))
    for donor in ("CARROT", "TOMATO"):
        committed = int(active[donor]) + int(seeds[donor])
        available = max(0, int(targets[donor]) - committed)
        moved = min(extra, available)
        targets[donor] -= moved
        targets["STRAWBERRY"] += moved
        extra -= moved
        if extra <= 0:
            break
    return targets


def _desired_hands(obs, farm):
    urgent = 0
    for _pos, tile in live._plant_tiles(farm):
        urgent += int(
            not tile.get("watered_today", False)
            and int(tile.get("consecutive_unwatered", 0)) >= 1
        )
    for _pos, tile in live._animal_tiles(farm):
        urgent += int(
            not tile.get("fed_today", False)
            and int(tile.get("consecutive_unfed", 0)) >= 1
        )
    distinct_shops = len(
        set((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])
    )
    if urgent >= 4 and distinct_shops >= 3:
        return 12
    return v7._desired_hands(obs, farm)


def _crop_tasks(obs, farm, policy, animal_goals, reserved):
    """Retain v7 task shaping and protect already-paid premium commitments."""

    tasks = list(_BASE_CROP_TASKS(obs, farm, policy, animal_goals, reserved))
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))

    planted_today = sum(
        tile.get("crop") == "STRAWBERRY"
        and int(tile.get("planted_day", -1)) == day
        for _pos, tile in live._plant_tiles(farm)
    )
    allowance = max(0, 6 - planted_today)
    bounded = []
    for task in tasks:
        operation = task[2]
        if operation[:2] == ["PLANT", "STRAWBERRY"]:
            if allowance <= 0:
                continue
            allowance -= 1
        bounded.append(task)

    tasks = []
    plant_deadlines = {"WHEAT": 24, "STRAWBERRY": 13, "TOMATO": 17, "CARROT": 26}
    for priority, target, operation in bounded:
        if day > 2 and operation and operation[0] == "PLANT":
            crop = operation[1]
            priority = 1 if day + 1 >= plant_deadlines.get(crop, 99) else 2
            # These tasks exist only because the seed is already in private
            # inventory.  Planting it is better than carrying a sunk purchase
            # through the end of the episode.
            if crop == "STRAWBERRY" and 13 <= day <= 15:
                priority = -1
            elif crop == "TOMATO" and 16 <= day <= 18:
                priority = 0
        tasks.append((priority, target, operation))

    if day < 29 and hour >= 12:
        for pos, tile in live._plant_tiles(farm):
            if pos in reserved or tile.get("crop") not in ("TOMATO", "STRAWBERRY"):
                continue
            crop = tile.get("crop")
            if live._tile_age(tile, day) >= int(live.CROPS[crop]["last"]):
                continue
            if tile.get("watered_today", False):
                continue
            if any(target == pos and operation[0] == "WATER" for _p, target, operation in tasks):
                continue
            tasks = [
                task
                for task in tasks
                if not (task[1] == pos and task[2][0] == "HARVEST")
            ]
            tasks.append((1, pos, ["WATER"]))
    return tasks


def _clone_scheduler():
    namespace = dict(vars(live))
    namespace.update(vars(v7))
    namespace.update(globals())
    overrides = {
        "_animal_goals",
        "_layout",
        "_crop_targets",
        "_seed_needs",
        "_fertilizer_targets",
        "_crop_tasks",
        "_unit_actions",
        "_liquidation",
        "_market_actions",
        "agent_for",
        "agent",
    }
    namespace["_layout"] = v7._stable_layout
    for name, value in vars(live).items():
        if name in overrides:
            continue
        if inspect.isfunction(value) and value.__module__ == live.__name__:
            namespace[name] = v7._clone(value, namespace)

    namespace["_BASE_SEED_NEEDS"] = v7._clone(live._seed_needs, namespace)
    namespace["_seed_needs"] = v7._clone(v7._seed_needs, namespace)
    namespace["_BASE_CROP_TASKS"] = v7._clone(live._crop_tasks, namespace)
    namespace["_crop_tasks"] = v7._clone(_crop_tasks, namespace)
    namespace["_BASE_LIQUIDATION"] = v7._clone(live._liquidation, namespace)
    namespace["_liquidation"] = v7._clone(v7._liquidation, namespace)
    namespace["_BASE_UNIT_ACTIONS"] = v7._clone(live._unit_actions, namespace)
    namespace["_unit_actions"] = v7._clone(v7._unit_actions, namespace)
    namespace["_market_actions"] = v7._clone(v7._market_actions, namespace)
    namespace["agent_for"] = v7._clone(live.agent_for, namespace)
    return namespace


_SCHEDULER = _clone_scheduler()

_crop_tasks = _SCHEDULER["_crop_tasks"]
_seed_needs = _SCHEDULER["_seed_needs"]
_unit_actions = _SCHEDULER["_unit_actions"]
_liquidation = _SCHEDULER["_liquidation"]
_market_actions = _SCHEDULER["_market_actions"]


def agent(obs):
    return _SCHEDULER["agent_for"](obs, "throughput")


__all__ = ["POLICY", "agent"]
