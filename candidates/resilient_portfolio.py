"""Replay-audited resilient portfolio candidate.

This candidate keeps the reliable, stateless mechanics of
``live_archetypes`` and the occupied-position-stable animal layout, while
overriding the failure modes observed in submission 55631403:

* a demand- and opponent-aware crop/animal portfolio;
* viable late livestock responses to shops unlocked after day 17;
* bounded strawberry cohorts and preventive afternoon watering;
* capacity-aware banking before the shed's end-of-day drop; and
* fertilizer use only when it beats selling the fertilizer itself.

The implementation is observation-only and deterministic.  The scheduler is
cloned into a private function namespace so none of these overrides mutate the
incumbent or a concurrently running opponent.
"""

from __future__ import annotations

import collections
import inspect
import math
import types

from candidates import live_archetypes as live


ANIMALS = live.ANIMALS
ANIMAL_COST = live.ANIMAL_COST
ANIMAL_PRODUCT = live.ANIMAL_PRODUCT
CROPS = live.CROPS
PRODUCTS = live.PRODUCTS

OUTPUT_RATE = {"GOOSE": 2.0, "COW": 1.5, "SHEEP": 4.0 / 3.0}
ANIMAL_CAPS = {"GOOSE": 9, "COW": 12, "SHEEP": 14}
ANIMAL_CUTOFFS = {"GOOSE": 18, "COW": 18, "SHEEP": 18}
BASELINE_ANIMALS = {"GOOSE": 1, "COW": 2, "SHEEP": 2}

POLICY = {
    **live.POLICIES["strawberry"],
    "opening_animals": {"GOOSE": 1, "COW": 2, "SHEEP": 2},
    "animal_targets": dict(BASELINE_ANIMALS),
    "opening_seeds": {"MELON": 8, "WHEAT": 7},
    "strawberries": 28,
    "tomatoes": 4,
    "hands": 9,
    "land": 3,
    "slot_order": ("SHEEP", "COW", "GOOSE"),
}
POLICIES = {**live.POLICIES, "resilient": POLICY}


def _opponent_animals(obs):
    try:
        me = int(obs.get("player", 0))
    except (TypeError, ValueError):
        me = 0
    counts = collections.Counter()
    for player, farm in enumerate(obs.get("farms", []) or []):
        if player == me:
            continue
        counts.update(tile.get("animal") for _pos, tile in live._animal_tiles(farm))
    return counts


def _opponent_crops(obs):
    try:
        me = int(obs.get("player", 0))
    except (TypeError, ValueError):
        me = 0
    counts = collections.Counter()
    for player, farm in enumerate(obs.get("farms", []) or []):
        if player == me:
            continue
        counts.update(tile.get("crop") for _pos, tile in live._plant_tiles(farm))
    return counts


def _owned(obs):
    farms = obs.get("farms", []) or []
    try:
        player = int(obs.get("player", 0))
    except (TypeError, ValueError):
        player = 0
    if not 0 <= player < len(farms):
        return collections.Counter()
    return live._owned_animals(farms[player], obs.get("private", {}) or {})


def _animal_demand(obs):
    shops = live._shop_counts(obs)
    return {
        "GOOSE": 1 + 6 * (shops["BAKERY"] + shops["BRUNCH_SPOT"]),
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
    """Scale for animal demand without crowding crop-only town economies."""

    day = int(obs.get("day", 0))
    owned = _owned(obs)
    opening = collections.Counter(policy["opening_animals"])
    if day <= 2:
        return {
            kind: max(int(opening[kind]), int(owned[kind])) for kind in ANIMALS
        }

    shops = live._shop_counts(obs)
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
    calendar_capacity = 8 if day <= 5 else 11 if day <= 8 else 14 if day <= 11 else 16
    capacity = min(calendar_capacity, 8 + animal_shop_count)
    floors = {
        kind: max(int(opening[kind]), int(BASELINE_ANIMALS[kind]))
        for kind in ANIMALS
    }

    # Rival supply is credited conservatively. It may reduce an optional
    # sleeve, but never an animal already bought or the compact five-animal
    # fertilizer engine. Pet Cafe and Farmers Market towns therefore keep
    # their cells and labor for crops instead of blindly forcing 16 animals.
    opponent = _opponent_animals(obs)
    demand = _animal_demand(obs)
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    residual = {}
    goals = {}
    for kind in ANIMALS:
        residual[kind] = max(
            0.0,
            float(demand[kind])
            - 0.78 * float(opponent[kind]) * OUTPUT_RATE[kind],
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

    # Eight animals are a compact generic fertilizer/output engine. Beyond
    # that base, expansion is earned by an animal-consuming shop rather than
    # by the date alone.
    engine_floor = min(capacity, 8)
    while sum(goals.values()) < engine_floor:
        choices = [kind for kind in ANIMALS if goals[kind] < int(ANIMAL_CAPS[kind])]
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

    # A goal that can no longer be purchased must not reserve empty crop cells.
    for kind, cutoff in ANIMAL_CUTOFFS.items():
        if day > cutoff:
            goals[kind] = int(owned[kind])
    return {kind: max(int(goals[kind]), int(owned[kind])) for kind in ANIMALS}


def _stable_layout(farm, animal_goals, policy=POLICY):
    """Keep occupied anchors and consume empty cells before productive crops."""

    occupied = sorted(
        ((pos, tile["animal"]) for pos, tile in live._animal_tiles(farm)),
        key=lambda item: (item[0][1], item[0][0], item[1]),
    )
    occupied_positions = {pos for pos, _kind in occupied}
    visible = collections.Counter(kind for _pos, kind in occupied)
    size = len(farm.get("tiles", [])) or 10
    half = size // 2

    def quadrant(pos):
        x, y = pos
        return 0 if x < half and y < half else 1 if y < half else 2 if x < half else 3

    def tile_cost(pos, kind):
        tile = farm["tiles"][pos[1]][pos[0]]
        structure = live.ANIMAL_STRUCTURE[kind]
        if isinstance(tile, dict) and tile.get("kind") == structure and not tile.get("animal"):
            return 0
        if tile is None:
            return 1
        if isinstance(tile, dict) and tile.get("kind") == "WEED":
            return 2
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            crop = tile.get("crop")
            return 5 if crop == "STRAWBERRY" else 4 if crop == "TOMATO" else 3
        return 3

    available = {
        (x, y)
        for x, y, _tile in live._owned_cells(farm)
        if (x, y) not in occupied_positions
    }
    visible_nw = collections.Counter(kind for pos, kind in occupied if quadrant(pos) == 0)
    result = list(occupied)
    opening = collections.Counter(policy["opening_animals"])

    def take(kind, pool, count):
        chosen = sorted(
            pool,
            key=lambda pos: (
                tile_cost(pos, kind),
                live._distance(pos, live._nearest_shed(pos, size)),
                pos[1],
                pos[0],
            ),
        )[:count]
        for pos in chosen:
            available.remove(pos)
            result.append((pos, kind))
        return len(chosen)

    for kind in policy["slot_order"]:
        remaining = max(0, int(animal_goals.get(kind, 0)) - int(visible[kind]))
        opening_missing = max(
            0,
            min(int(animal_goals.get(kind, 0)), int(opening[kind])) - int(visible_nw[kind]),
        )
        nw_pool = {pos for pos in available if quadrant(pos) == 0}
        used = take(kind, nw_pool, min(remaining, opening_missing))
        remaining -= used
        expansion_pool = {pos for pos in available if quadrant(pos) != 0}
        take(kind, expansion_pool, remaining)
    return result


def _crop_targets(obs, farm, policy, animal_goals):
    """Allocate cells across feed and the town's actual crop demand."""

    day = int(obs.get("day", 0))
    if day <= 2:
        return collections.Counter(policy["opening_seeds"])

    shops = live._shop_counts(obs)
    opponent = _opponent_crops(obs)
    animal_count = sum(int(value) for value in animal_goals.values())
    capacity = max(0, 25 * int(policy["land"]) - animal_count)

    berry_shops = sum(
        shops[name]
        for name in (
            "BRUNCH_SPOT",
            "ICE_CREAM_SHOP",
            "SMOOTHIE_SHOP",
            "FARMERS_MARKET",
        )
    )
    wheat_shops = sum(
        shops[name]
        for name in ("PIZZA_SHOP", "BAKERY", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET")
    )
    tomato_shops = shops["PIZZA_SHOP"] + shops["FARMERS_MARKET"]
    carrot_weight = 2 * shops["PET_CAFE"] + shops["FARMERS_MARKET"]

    feed_floor = max(12, int(math.ceil(animal_count * 1.10)) + 3)
    desired = collections.Counter(
        {
            "WHEAT": min(40, max(16, feed_floor + 2 * wheat_shops)),
            "STRAWBERRY": (
                min(40, max(18, 18 + 4 * berry_shops - int(opponent["STRAWBERRY"] * 0.20)))
                if day >= 6
                else 0
            ),
            "TOMATO": (
                min(24, max(4, 4 + 5 * tomato_shops - int(opponent["TOMATO"] * 0.25)))
                if day >= 5 and tomato_shops
                else 0
            ),
            "CARROT": (
                min(40, max(4, 4 + 5 * carrot_weight - int(opponent["CARROT"] * 0.25)))
                if day <= 25 and carrot_weight
                else 0
            ),
        }
    )
    targets = collections.Counter()
    targets["WHEAT"] = min(capacity, feed_floor, desired["WHEAT"])
    if day >= 6:
        targets["STRAWBERRY"] = min(12, desired["STRAWBERRY"], max(0, capacity - sum(targets.values())))
    for crop in ("TOMATO", "CARROT"):
        if desired[crop]:
            targets[crop] = min(3, desired[crop], max(0, capacity - sum(targets.values())))

    scores = {
        "WHEAT": 3 + wheat_shops,
        "STRAWBERRY": 4 + berry_shops,
        "TOMATO": 3 + 2 * tomato_shops,
        "CARROT": 3 + 2 * carrot_weight,
    }
    extras = collections.Counter()
    while sum(targets.values()) < capacity:
        choices = [crop for crop in scores if targets[crop] < desired[crop]]
        if not choices:
            break
        crop = max(
            choices,
            key=lambda name: (scores[name] / (1 + extras[name]), scores[name], name),
        )
        targets[crop] += 1
        extras[crop] += 1
    # A seed already bought is a sunk commitment.  Keep enough target room to
    # plant it, taking only uncommitted slots from another crop.
    active = live._crop_counts(farm)
    seeds = collections.Counter((obs.get("private", {}) or {}).get("seeds", {}) or {})
    for crop in CROPS:
        missing_commitment = max(0, int(active[crop]) + int(seeds[crop]) - int(targets[crop]))
        while missing_commitment > 0:
            donors = [
                name
                for name in CROPS
                if name != crop
                and targets[name] > int(active[name]) + int(seeds[name])
            ]
            if not donors:
                break
            donor = min(donors, key=lambda name: (scores.get(name, 0), -targets[name], name))
            targets[donor] -= 1
            targets[crop] += 1
            missing_commitment -= 1
    return targets


def _fertilizer_targets(obs, farm, reserved):
    """Apply fertilizer only when its incremental crop value wins."""

    day = int(obs.get("day", 0))
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    fertilizer_price = max(1, int(prices.get("FERTILIZER", 100)))
    result = []
    for pos, tile in live._plant_tiles(farm):
        if pos in reserved:
            continue
        crop = tile.get("crop")
        age = live._tile_age(tile, day)
        until = int(tile.get("fertilized_until_day", -1))
        production_ages = (
            {9, 11, 13, 15} if crop == "STRAWBERRY" else set(range(7, 11)) if crop == "TOMATO" else set()
        )
        if not production_ages:
            # In particular, fertilizing a maintained melon only reaches the
            # same six-unit cap sooner; it does not increase final yield.
            continue
        uncovered_events = sum(
            age + offset in production_ages and until < day + offset
            for offset in range(3)
        )
        headroom = max(0, 4 - int(tile.get("yield_units", 0)))
        added_units = min(uncovered_events, headroom)
        if added_units <= 0:
            continue
        value = added_units * max(1, int(prices.get(crop, 1)))
        if value >= int(math.ceil(fertilizer_price * 1.10)):
            result.append((value, pos))
    return [pos for _value, pos in sorted(result, key=lambda row: (-row[0], row[1][1], row[1][0]))]


# The three wrappers below are cloned with private base functions by
# ``_clone_scheduler``.  Module-level placeholders keep their globals valid for
# introspection; calls used by the agent resolve the private namespace values.
_BASE_CROP_TASKS = live._crop_tasks
_BASE_UNIT_ACTIONS = live._unit_actions
_BASE_LIQUIDATION = live._liquidation
_BASE_SEED_NEEDS = live._seed_needs


def _seed_needs(obs, farm, policy, animal_goals, reserved):
    """Keep at most one immediately plantable seed wave in inventory."""

    needs = collections.Counter(
        _BASE_SEED_NEEDS(obs, farm, policy, animal_goals, reserved)
    )
    day = int(obs.get("day", 0))
    seeds = collections.Counter((obs.get("private", {}) or {}).get("seeds", {}) or {})
    buffers = {"MELON": 8, "WHEAT": 10, "STRAWBERRY": 8, "TOMATO": 8, "CARROT": 10}
    purchase_deadlines = {"MELON": 2, "WHEAT": 20, "STRAWBERRY": 12, "TOMATO": 16, "CARROT": 25}
    for crop, buffer in buffers.items():
        if day > purchase_deadlines[crop]:
            needs[crop] = 0
        else:
            needs[crop] = min(int(needs[crop]), max(0, int(buffer) - int(seeds[crop])))
    return needs


def _crop_tasks(obs, farm, policy, animal_goals, reserved):
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
        tasks.append((priority, target, operation))

    # Afternoon preventive watering de-synchronizes the next day's survival
    # backlog.  A harvest on that tile waits one turn rather than competing
    # with a second worker for the same coordinate.
    if day < 29 and hour >= 12:
        for pos, tile in live._plant_tiles(farm):
            if pos in reserved or tile.get("crop") not in ("TOMATO", "STRAWBERRY"):
                continue
            crop = tile.get("crop")
            if live._tile_age(tile, day) >= int(CROPS[crop]["last"]):
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


def _storage_units(private):
    shed = private.get("shed", {}) or {}
    inventories = private.get("inventories", []) or []
    return sum(int(value) for value in shed.values()) + sum(
        int(value) for inventory in inventories for value in (inventory or {}).values()
    )


def _unit_actions(obs, farm, policy, animal_goals):
    actions = list(_BASE_UNIT_ACTIONS(obs, farm, policy, animal_goals))
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}

    # The base scheduler begins its bank run at hour 14.  A larger resilient
    # portfolio can still have one or two held products then, so empty workers
    # may take only harvests whose complete harvest-return-drop path fits by
    # the final actionable turn.  Loaded workers keep the base return action.
    if day >= 29:
        if 14 <= hour <= 17:
            positions = [tuple(farm.get("farmer", (0, 0)))] + [
                tuple(pos) for pos in farm.get("hands", []) or []
            ]
            inventories = list(private.get("inventories", []) or [])
            inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
            size = len(farm.get("tiles", [])) or 10
            targets = [
                pos
                for x, y, tile in live._owned_cells(farm)
                for pos in [(x, y)]
                if isinstance(tile, dict) and int(tile.get("yield_units", 0)) > 0
            ]
            claimed = set()
            for unit in range(len(positions)):
                if unit >= len(actions) or any(
                    int((inventories[unit] or {}).get(kind, 0)) > 0
                    for kind in ANIMALS
                ):
                    continue
                choices = []
                for target in targets:
                    if target in claimed:
                        continue
                    travel = live._distance(positions[unit], target)
                    return_trip = live._distance(target, live._nearest_shed(target, size))
                    required_actions = travel + 1 + return_trip + 1
                    if required_actions <= 23 - hour:
                        choices.append((travel, return_trip, target[1], target[0], target))
                if not choices:
                    continue
                target = min(choices)[-1]
                claimed.add(target)
                actions[unit] = (
                    ["HARVEST"]
                    if positions[unit] == target
                    else live._move(positions[unit], target, unit)
                )
        return actions

    pressure = _storage_units(private)
    if pressure < 90 or (hour < 16 and pressure < 105):
        return actions

    positions = [tuple(farm.get("farmer", (0, 0)))] + [
        tuple(pos) for pos in farm.get("hands", []) or []
    ]
    inventories = list(private.get("inventories", []) or [])
    inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
    size = len(farm.get("tiles", [])) or 10
    candidates = sorted(
        range(len(positions)),
        key=lambda unit: (
            -sum(int(value) for value in (inventories[unit] or {}).values()),
            unit,
        ),
    )
    couriers = 0
    for unit in candidates:
        inventory = inventories[unit] or {}
        if not any(int(inventory.get(item, 0)) > 0 for item in PRODUCTS):
            continue
        if any(int(inventory.get(kind, 0)) > 0 for kind in ANIMALS):
            continue
        op = actions[unit][0] if unit < len(actions) and actions[unit] else "PASS"
        if op in ("FEED", "WATER", "PLACE"):
            continue
        target = live._nearest_shed(positions[unit], size)
        actions[unit] = (
            ["DROP"]
            if live._at_shed(positions[unit], size)
            else live._move(positions[unit], target, unit)
        )
        couriers += 1
        if couriers >= 2:
            break
    return actions


def _liquidation(obs, actions, animal_count):
    amounts = dict(_BASE_LIQUIDATION(obs, actions, animal_count))
    private = obs.get("private", {}) or {}
    total = _storage_units(private)
    if int(obs.get("day", 0)) >= 29 or total < 90:
        return amounts

    shed = private.get("shed", {}) or {}
    inventories = private.get("inventories", []) or []
    available = {item: int(shed.get(item, 0)) for item in PRODUCTS}
    for unit, action in enumerate(actions):
        if unit >= len(inventories) or not action or action[0] != "DROP":
            continue
        for item in PRODUCTS:
            available[item] += int((inventories[unit] or {}).get(item, 0))

    feed_reserve = max(8, int(math.ceil(animal_count * 2.0)))
    available["WHEAT"] = max(0, available["WHEAT"] - feed_reserve)
    needed = max(0, total - 80 - sum(min(available[item], int(amounts.get(item, 0))) for item in PRODUCTS))
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    for item in sorted(PRODUCTS, key=lambda name: (-int(prices.get(name, 1)), name)):
        if needed <= 0:
            break
        extra_room = max(0, available[item] - int(amounts.get(item, 0)))
        extra = min(extra_room, needed)
        if extra:
            amounts[item] = int(amounts.get(item, 0)) + extra
            needed -= extra
    return amounts


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
    productive_tiles = len(live._plant_tiles(farm)) + len(live._animal_tiles(farm))
    if urgent >= 4:
        return 11
    return 10 if productive_tiles >= 42 else 9


def _animal_roi(obs, kind):
    day = int(obs.get("day", 0))
    placement_day = day + 2
    first, interval = {"GOOSE": (4, 1), "COW": (8, 2), "SHEEP": (6, 3)}[kind]
    first_production = placement_day + first
    cycles = (
        0
        if first_production > 29
        else 1 + max(0, (29 - first_production) // interval)
    )
    product_units = cycles * 1.5
    service_days = max(0, 29 - placement_day + 1)
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    product_price = max(1, int(prices.get(ANIMAL_PRODUCT[kind], 1)))
    fertilizer_price = max(1, int(prices.get("FERTILIZER", 100)))
    wheat_price = max(1, int(prices.get("WHEAT", 25)))
    return (
        0.70 * product_units * product_price
        + 0.65 * service_days * fertilizer_price
        - ANIMAL_COST[kind]
        - service_days * wheat_price
        - 200.0
    )


def _market_actions(obs, farm, actions, policy, animal_goals, reserved):
    """Live market discipline with dynamic labor and late viable animals."""

    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    owned = live._owned_animals(farm, private)
    animal_count = sum(int(value) for value in owned.values())
    feed_projection_count = max(
        animal_count,
        sum(int(value) for value in animal_goals.values()),
    )
    amounts = _liquidation(obs, actions, feed_projection_count)
    orders = []

    sales = [item for item, quantity in amounts.items() if quantity > 0]
    sales.sort(key=lambda item: (-amounts[item] * int(prices.get(item, 1)), item))

    desired_hires = _desired_hands(obs, farm) if hour <= 1 else 0
    if day >= 29:
        desired_hires = min(desired_hires, 9)
    existing_hires = int(farm.get("hires_today", 0))
    missing_hires = max(0, desired_hires - existing_hires)
    sale_limit = max(0, 10 - min(missing_hires, 6))
    for item in sales[:sale_limit]:
        orders.append(["SELL", item, amounts[item]])
    hire_now = min(missing_hires, 10 - len(orders))
    orders.extend([["HIRE"] for _ in range(hire_now)])

    liquid = float(farm.get("money", 0))
    liquid += sum(
        amounts[item] * int(prices.get(item, 1)) * 0.72
        for item in sales[:sale_limit]
    )
    liquid -= live._fib_cost(existing_hires, hire_now)
    if day >= 29:
        return orders[:10]

    reserve = max(300.0, feed_projection_count * int(prices.get("WHEAT", 25)) * 1.5)
    quadrants = len(farm.get("unlocked_quadrants", []))
    # The first expansion is required before the day-6 herd wave.  The third
    # quadrant waits until the two-quadrant farm has compounded ten animals.
    if 3 <= day <= 8 and quadrants < 2 and len(orders) < 10:
        land_cost = 1000
        if liquid >= reserve + land_cost:
            orders.append(["BUY_LAND"])
            liquid -= land_cost

    slot_capacity = collections.Counter(
        kind for _pos, kind in _stable_layout(farm, animal_goals, policy)
    )
    candidates = sorted(
        (
            (_animal_roi(obs, kind), kind)
            for kind in ANIMALS
            if day <= ANIMAL_CUTOFFS[kind]
            and int(owned[kind]) < min(int(animal_goals[kind]), int(slot_capacity[kind]))
        ),
        reverse=True,
    )
    for roi, kind in candidates:
        if len(orders) >= 10:
            break
        if day > 12 and roi <= 0:
            continue
        missing = max(
            0,
            min(int(animal_goals[kind]), int(slot_capacity[kind])) - int(owned[kind]),
        )
        affordable = max(0, int((liquid - reserve) // ANIMAL_COST[kind]))
        quantity = min(3, missing, affordable)
        if quantity:
            orders.append(["BUY_ANIMAL", kind, quantity])
            owned[kind] += quantity
            liquid -= quantity * ANIMAL_COST[kind]

    committed_animals = sum(int(value) for value in owned.values())
    crop_capacity_needed = sum(
        int(value)
        for value in _crop_targets(obs, farm, policy, animal_goals).values()
    )
    if (
        9 <= day <= 13
        and quadrants == 2
        and (committed_animals >= 10 or committed_animals + crop_capacity_needed > 46)
        and int(policy["land"]) >= 3
        and len(orders) < 10
    ):
        land_cost = 2000
        if liquid >= reserve + land_cost:
            orders.append(["BUY_LAND"])
            liquid -= land_cost

    needs = _seed_needs(obs, farm, policy, animal_goals, reserved)
    if day <= 2:
        for crop in ("MELON", "WHEAT"):
            if len(orders) >= 10:
                break
            quantity = int(needs[crop])
            affordable = max(0, int((liquid - reserve) // int(CROPS[crop]["seed"])))
            quantity = min(quantity, affordable)
            if quantity:
                orders.append(["BUY_SEED", crop, quantity])
                liquid -= quantity * int(CROPS[crop]["seed"])

    total_wheat = int(shed.get("WHEAT", 0)) + live._carried(private, "WHEAT")
    projected_wheat = max(0, total_wheat - int(amounts.get("WHEAT", 0)))
    target_wheat = max(8, int(math.ceil(sum(int(value) for value in owned.values()) * 2.0)))
    shortage = max(0, target_wheat - projected_wheat)
    if shortage and day < 29 and len(orders) < 10:
        wheat_price = max(1, int(prices.get("WHEAT", 25)))
        affordable = max(0, int((liquid - reserve * 0.35) // wheat_price))
        quantity = min(shortage, affordable)
        if quantity:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            liquid -= quantity * wheat_price

    if day > 2:
        planting_deadline = {"WHEAT": 24, "STRAWBERRY": 13, "TOMATO": 17, "CARROT": 26}
        crop_order = sorted(
            ("WHEAT", "STRAWBERRY", "TOMATO", "CARROT"),
            key=lambda crop: (
                planting_deadline[crop] - day,
                -int(prices.get(crop, 1)) / max(1, int(CROPS[crop]["seed"])),
                crop,
            ),
        )
        for crop in crop_order:
            if len(orders) >= 10:
                break
            quantity = int(needs[crop])
            if quantity <= 0:
                continue
            affordable = max(0, int((liquid - reserve) // int(CROPS[crop]["seed"])))
            quantity = min(quantity, affordable)
            if quantity:
                orders.append(["BUY_SEED", crop, quantity])
                liquid -= quantity * int(CROPS[crop]["seed"])
    return orders[:10]


def _clone(function, namespace):
    cloned = types.FunctionType(
        function.__code__,
        namespace,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    cloned.__kwdefaults__ = function.__kwdefaults__
    cloned.__annotations__ = dict(getattr(function, "__annotations__", {}))
    cloned.__dict__.update(getattr(function, "__dict__", {}))
    return cloned


def _clone_scheduler():
    namespace = dict(vars(live))
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
    namespace["_layout"] = _stable_layout
    for name, value in vars(live).items():
        if name in overrides:
            continue
        if inspect.isfunction(value) and value.__module__ == live.__name__:
            namespace[name] = _clone(value, namespace)

    namespace["_BASE_SEED_NEEDS"] = _clone(live._seed_needs, namespace)
    namespace["_seed_needs"] = _clone(_seed_needs, namespace)
    namespace["_BASE_CROP_TASKS"] = _clone(live._crop_tasks, namespace)
    namespace["_crop_tasks"] = _clone(_crop_tasks, namespace)
    namespace["_BASE_LIQUIDATION"] = _clone(live._liquidation, namespace)
    namespace["_liquidation"] = _clone(_liquidation, namespace)
    namespace["_BASE_UNIT_ACTIONS"] = _clone(live._unit_actions, namespace)
    namespace["_unit_actions"] = _clone(_unit_actions, namespace)
    namespace["_market_actions"] = _clone(_market_actions, namespace)
    namespace["agent_for"] = _clone(live.agent_for, namespace)
    return namespace


_SCHEDULER = _clone_scheduler()

# Expose the exact functions used by the candidate for focused unit tests.
_crop_tasks = _SCHEDULER["_crop_tasks"]
_seed_needs = _SCHEDULER["_seed_needs"]
_unit_actions = _SCHEDULER["_unit_actions"]
_liquidation = _SCHEDULER["_liquidation"]
_market_actions = _SCHEDULER["_market_actions"]


def agent(obs):
    return _SCHEDULER["agent_for"](obs, "resilient")


__all__ = ["POLICY", "agent"]
