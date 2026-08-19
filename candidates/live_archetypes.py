"""Independent replay-calibrated opponents for live-strength regression tests.

These agents intentionally do *not* use :mod:`candidates.hybrid_core`.  The
four policies share this separate scheduler so that its routing, batching,
hiring, feed, crop-calendar, and liquidation mistakes do not cancel those of
the submitted agent during local tournaments.

The policies model four patterns seen in public 90k+ games:

* an opening melon wave followed by a large day-8--12 strawberry cohort;
* a lower-labor strawberry specialist;
* a cow-heavy milk branch;
* a goose/tomato residual-demand branch.

The implementation is observation-only and deterministic.  It is suitable for
loading repeatedly by ``eval.tournament`` and does not retain episode state.
"""

from __future__ import annotations

import collections
import math


ANIMALS = ("GOOSE", "COW", "SHEEP")
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
ANIMAL_STRUCTURE = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}

CROPS = {
    "WHEAT": {"seed": 10, "first": 2, "peak": 4, "last": 4, "yield": 4, "ongoing": False},
    "CARROT": {"seed": 20, "first": 2, "peak": 3, "last": 3, "yield": 3, "ongoing": False},
    "TOMATO": {"seed": 50, "first": 8, "peak": 11, "last": 11, "yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first": 10, "peak": 16, "last": 16, "yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first": 10, "peak": 10, "last": 12, "yield": 6, "ongoing": False},
}

PRODUCTS = (
    "WHEAT",
    "CARROT",
    "TOMATO",
    "STRAWBERRY",
    "MELON",
    "EGG",
    "MILK",
    "WOOL",
    "FERTILIZER",
)

PREMIUM_HOLD_PRICE = {"STRAWBERRY": 105, "MELON": 130, "MILK": 105, "WOOL": 130}


POLICIES = {
    "melon_strawberry": {
        "opening_animals": {"GOOSE": 0, "COW": 2, "SHEEP": 1},
        "animal_targets": {"GOOSE": 1, "COW": 7, "SHEEP": 5},
        "opening_seeds": {"MELON": 12, "WHEAT": 8},
        "strawberries": 32,
        "tomatoes": 4,
        "hands": 8,
        "land": 3,
        "slot_order": ("COW", "SHEEP", "GOOSE"),
    },
    "strawberry": {
        "opening_animals": {"GOOSE": 0, "COW": 1, "SHEEP": 2},
        "animal_targets": {"GOOSE": 0, "COW": 4, "SHEEP": 3},
        "opening_seeds": {"MELON": 8, "WHEAT": 8},
        "strawberries": 40,
        "tomatoes": 4,
        "hands": 8,
        "land": 3,
        "slot_order": ("SHEEP", "COW", "GOOSE"),
    },
    "milk": {
        "opening_animals": {"GOOSE": 0, "COW": 3, "SHEEP": 0},
        "animal_targets": {"GOOSE": 0, "COW": 14, "SHEEP": 2},
        "opening_seeds": {"MELON": 10, "WHEAT": 8},
        "strawberries": 28,
        "tomatoes": 8,
        "hands": 9,
        "land": 3,
        "slot_order": ("COW", "SHEEP", "GOOSE"),
    },
    "tomato_goose": {
        "opening_animals": {"GOOSE": 3, "COW": 1, "SHEEP": 0},
        "animal_targets": {"GOOSE": 6, "COW": 7, "SHEEP": 2},
        "opening_seeds": {"MELON": 8, "WHEAT": 8},
        "strawberries": 20,
        "tomatoes": 8,
        "hands": 9,
        "land": 3,
        "slot_order": ("GOOSE", "COW", "SHEEP"),
    },
}


def _shop_counts(obs):
    return collections.Counter((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])


def _animal_goals(obs, policy):
    goals = dict(policy["animal_targets"])
    shops = _shop_counts(obs)
    milk_demand = shops["PIZZA_SHOP"] + shops["ICE_CREAM_SHOP"] + shops["SMOOTHIE_SHOP"]
    egg_demand = shops["BAKERY"] + shops["BRUNCH_SPOT"]
    yarn = shops["YARN_STORE"]

    # Each archetype stays recognisable while reacting to an unusually strong
    # residual signal.  Caps match allocations observed in public games.
    if policy is POLICIES["milk"]:
        me = int(obs.get("player", 0))
        own_cows = opponent_cows = opponent_geese = 0
        for player, farm in enumerate(obs.get("farms", []) or []):
            cows = sum(tile.get("animal") == "COW" for _pos, tile in _animal_tiles(farm))
            geese = sum(tile.get("animal") == "GOOSE" for _pos, tile in _animal_tiles(farm))
            if player == me:
                own_cows += cows
            else:
                opponent_cows += cows
                opponent_geese += geese
        daily_demand = 1 + 6 * milk_demand
        residual = max(0.0, daily_demand - 1.2 * opponent_cows)
        residual_goal = 3 + int(math.ceil(residual / 1.4))
        if milk_demand >= 4:
            residual_goal = max(residual_goal, 10)
        goals["COW"] = min(15, max(int(policy["opening_animals"]["COW"]), own_cows, residual_goal))
        goals["SHEEP"] = min(8, max(goals["SHEEP"], 2 + 2 * yarn))
        goals["GOOSE"] = min(5, max(0, egg_demand - opponent_geese // 2))
    elif policy is POLICIES["tomato_goose"]:
        goals["GOOSE"] = min(7, max(goals["GOOSE"], 2 + egg_demand))
        goals["COW"] = min(8, max(goals["COW"], 3 + milk_demand))
    else:
        goals["COW"] = min(9, max(goals["COW"], 3 + milk_demand))
        goals["SHEEP"] = min(8, max(goals["SHEEP"], 2 + 2 * yarn))

    cap = 16 if policy is POLICIES["milk"] else 15
    while sum(goals.values()) > cap:
        # Preserve each archetype's defining product and trim the least demanded
        # non-opening sleeve first.
        if policy is POLICIES["milk"]:
            order = ("SHEEP", "GOOSE", "COW")
        elif policy is POLICIES["tomato_goose"]:
            order = ("SHEEP", "COW", "GOOSE")
        else:
            order = ("GOOSE", "COW", "SHEEP")
        changed = False
        for kind in order:
            floor = int(policy["opening_animals"].get(kind, 0))
            if goals[kind] > floor:
                goals[kind] -= 1
                changed = True
                break
        if not changed:
            break
    return goals


def _shed_tiles(size):
    half = size // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _at_shed(pos, size):
    return tuple(pos) in _shed_tiles(size)


def _nearest_shed(pos, size):
    return min(_shed_tiles(size), key=lambda target: (_distance(pos, target), target[1], target[0]))


def _move(source, target, unit):
    x, y = source
    tx, ty = target
    # Alternating axis preference separates workers that spawn together.
    if unit % 2 == 0 and x != tx:
        return ["EAST" if tx > x else "WEST"]
    if y != ty:
        return ["SOUTH" if ty > y else "NORTH"]
    if x != tx:
        return ["EAST" if tx > x else "WEST"]
    return ["PASS"]


def _owned_cells(farm):
    for y, row in enumerate(farm.get("tiles", []) or []):
        for x, tile in enumerate(row):
            if tile != "LOCKED":
                yield x, y, tile


def _animal_tiles(farm):
    return [
        ((x, y), tile)
        for x, y, tile in _owned_cells(farm)
        if isinstance(tile, dict) and tile.get("animal")
    ]


def _plant_tiles(farm):
    return [
        ((x, y), tile)
        for x, y, tile in _owned_cells(farm)
        if isinstance(tile, dict) and tile.get("kind") == "PLANT"
    ]


def _carried(private, item):
    return sum(int((inventory or {}).get(item, 0)) for inventory in private.get("inventories", []) or [])


def _owned_animals(farm, private):
    answer = collections.Counter(tile["animal"] for _pos, tile in _animal_tiles(farm))
    shed = private.get("shed", {}) or {}
    for kind in ANIMALS:
        answer[kind] += int(shed.get(kind, 0)) + _carried(private, kind)
    return answer


def _layout(farm, animal_goals, policy):
    size = len(farm.get("tiles", [])) or 10
    half = size // 2

    def quadrant(pos):
        x, y = pos
        return 0 if x < half and y < half else 1 if y < half else 2 if x < half else 3

    cells = [(x, y) for x, y, _tile in _owned_cells(farm)]
    nw = sorted(
        (pos for pos in cells if quadrant(pos) == 0),
        key=lambda pos: (_distance(pos, _nearest_shed(pos, size)), pos[1], -pos[0]),
    )
    expansion = sorted(
        (pos for pos in cells if quadrant(pos) != 0),
        key=lambda pos: (quadrant(pos), _distance(pos, _nearest_shed(pos, size)), pos[1], pos[0]),
    )

    opening = policy["opening_animals"]
    result = []
    nw_cursor = expansion_cursor = 0
    for kind in policy["slot_order"]:
        opening_count = min(int(opening.get(kind, 0)), int(animal_goals[kind]))
        for _ in range(opening_count):
            if nw_cursor < len(nw):
                result.append((nw[nw_cursor], kind))
                nw_cursor += 1
        for _ in range(max(0, int(animal_goals[kind]) - opening_count)):
            if expansion_cursor < len(expansion):
                result.append((expansion[expansion_cursor], kind))
                expansion_cursor += 1
    return result


def _tile_age(tile, day):
    return day - int(tile.get("planted_day", day))


def _crop_counts(farm):
    return collections.Counter(tile.get("crop") for _pos, tile in _plant_tiles(farm))


def _crop_targets(obs, farm, policy, animal_goals):
    day = int(obs.get("day", 0))
    shops = _shop_counts(obs)
    targets = collections.Counter()

    # The first melon cohort must mature before the common day-15 collapse.
    if day <= 2:
        targets.update(policy["opening_seeds"])
        return targets

    # Recurring feed base.  One well-watered wheat tile produces about one unit
    # per day over repeated four-day cycles.
    targets["WHEAT"] = max(
        int(policy["opening_seeds"].get("WHEAT", 0)),
        int(math.ceil(sum(animal_goals.values()) * 1.25)),
    )

    # Live high scorers planted the bulk of strawberries on days 9--13.  Start
    # one day earlier locally so the field can be serviced before its first
    # required watering, but never create a cohort that cannot finish by d29.
    if day >= 6:
        demand = shops["BRUNCH_SPOT"] + shops["ICE_CREAM_SHOP"] + shops["SMOOTHIE_SHOP"] + shops["FARMERS_MARKET"]
        targets["STRAWBERRY"] = min(44, int(policy["strawberries"]) + 2 * max(0, demand - 3))

    tomato_demand = shops["PIZZA_SHOP"] + shops["FARMERS_MARKET"]
    if day >= 5:
        base = int(policy["tomatoes"])
        if policy is POLICIES["tomato_goose"]:
            targets["TOMATO"] = min(24, max(base, 5 * tomato_demand))
        elif tomato_demand >= 2:
            targets["TOMATO"] = min(12, max(base, 3 * tomato_demand))

    carrot_demand = 2 * shops["PET_CAFE"] + shops["FARMERS_MARKET"]
    if day <= 25 and carrot_demand:
        targets["CARROT"] = min(18, 3 * carrot_demand)

    # Never reserve more crops than the policy's normal 75-tile farm can hold.
    capacity = max(0, 25 * int(policy["land"]) - sum(animal_goals.values()))
    priority = ("STRAWBERRY", "TOMATO", "WHEAT", "CARROT", "MELON")
    trimmed = collections.Counter()
    for crop in priority:
        add = min(targets[crop], max(0, capacity - sum(trimmed.values())))
        if add:
            trimmed[crop] = add
    return trimmed


def _soon_vacancies(farm, day):
    count = 0
    for _pos, tile in _plant_tiles(farm):
        crop = tile.get("crop")
        data = CROPS.get(crop)
        if not data:
            continue
        age = _tile_age(tile, day)
        if (data["ongoing"] and age >= data["last"]) or (not data["ongoing"] and age >= data["peak"]):
            count += 1
    return count


def _seed_needs(obs, farm, policy, animal_goals, reserved):
    day = int(obs.get("day", 0))
    if day >= 26:
        return collections.Counter()
    private = obs.get("private", {}) or {}
    seeds = collections.Counter(private.get("seeds", {}) or {})
    active = _crop_counts(farm)
    targets = _crop_targets(obs, farm, policy, animal_goals)
    empty = sum(
        pos not in reserved and (tile is None or (isinstance(tile, dict) and tile.get("kind") == "WEED"))
        for x, y, tile in _owned_cells(farm)
        for pos in [(x, y)]
    )
    # Buy only for cells that exist now.  A one-turn delay after a harvest is
    # cheaper than ending every game with seeds purchased for speculative
    # vacancies that the service crew never reaches.
    capacity = empty
    needs = collections.Counter()
    order = ("MELON", "WHEAT") if day <= 2 else ("STRAWBERRY", "TOMATO", "WHEAT", "CARROT")
    for crop in order:
        deadline = {"MELON": 2, "STRAWBERRY": 13, "TOMATO": 18, "WHEAT": 25, "CARROT": 26}[crop]
        if day > deadline:
            continue
        missing = max(0, targets[crop] - active[crop] - seeds[crop])
        missing = min(missing, max(0, capacity - sum(needs.values())))
        if missing:
            needs[crop] = missing
    return needs


def _crop_tasks(obs, farm, policy, animal_goals, reserved):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}
    seeds = collections.Counter(private.get("seeds", {}) or {})
    active = _crop_counts(farm)
    targets = _crop_targets(obs, farm, policy, animal_goals)
    tasks = []
    empties = []

    for x, y, tile in _owned_cells(farm):
        pos = (x, y)
        if pos in reserved:
            continue
        if tile is None:
            empties.append(pos)
            continue
        if not isinstance(tile, dict):
            continue
        if tile.get("kind") == "WEED":
            if day < 29:
                tasks.append((5, pos, ["DIG"]))
            continue
        if tile.get("kind") != "PLANT":
            continue

        crop = tile.get("crop")
        data = CROPS.get(crop)
        if not data:
            continue
        age = _tile_age(tile, day)
        units = int(tile.get("yield_units", 0))
        watered = bool(tile.get("watered_today", False))
        consecutive = int(tile.get("consecutive_unwatered", 0))

        if day >= 29:
            if hour <= 13 and units > 0 and age >= data["first"]:
                tasks.append((0, pos, ["HARVEST"]))
            continue

        if data["ongoing"]:
            production_tomorrow = (
                (crop == "TOMATO" and 7 <= age <= 10)
                or (crop == "STRAWBERRY" and age in (9, 11, 13, 15))
            )
            fertilized = int(tile.get("fertilized_until_day", -1)) >= day
            must_water = not watered and (consecutive >= 1 or (fertilized and production_tomorrow))
            final_cycle = age >= data["last"]
            if must_water:
                tasks.append((0, pos, ["WATER"]))
            elif units >= 2 or (units > 0 and final_cycle):
                tasks.append((3, pos, ["HARVEST"]))
            continue

        bonus_start = (int(data["last"]) + 1) // 2
        bonus_active = bonus_start <= age <= int(data["last"]) and units < int(data["yield"])
        must_water = not watered and (consecutive >= 1 or bonus_active)
        ready = age >= int(data["peak"]) and units >= int(data["yield"])
        if must_water:
            tasks.append((0, pos, ["WATER"]))
        elif ready or (age > int(data["last"]) and units > 0):
            tasks.append((3, pos, ["HARVEST"]))

    if day < 29 and hour <= 20:
        shortages = collections.Counter(
            {crop: max(0, targets[crop] - active[crop]) for crop in CROPS}
        )
        available_seeds = collections.Counter(seeds)
        order = ("MELON", "WHEAT") if day <= 2 else ("STRAWBERRY", "TOMATO", "WHEAT", "CARROT")
        for pos in sorted(empties, key=lambda value: (_distance(value, _nearest_shed(value, len(farm["tiles"]))), value[1], value[0])):
            crop = next(
                (
                    name
                    for name in order
                    if shortages[name] > 0
                    and available_seeds[name] > 0
                    and day <= {"MELON": 2, "STRAWBERRY": 15, "TOMATO": 18, "WHEAT": 25, "CARROT": 26}[name]
                ),
                None,
            )
            if crop is None:
                break
            # Planting a finite premium cohort outranks routine care/collection;
            # the resulting fresh tile receives priority-zero watering next.
            tasks.append((1, pos, ["PLANT", crop]))
            shortages[crop] -= 1
            available_seeds[crop] -= 1
    return tasks


def _fertilizer_targets(obs, farm, reserved):
    day = int(obs.get("day", 0))
    result = []
    for pos, tile in _plant_tiles(farm):
        if pos in reserved:
            continue
        crop = tile.get("crop")
        age = _tile_age(tile, day)
        until = int(tile.get("fertilized_until_day", -1))
        if until >= day + 1:
            continue
        useful = (
            (crop == "MELON" and 6 <= age <= 8)
            or (crop == "TOMATO" and 7 <= age <= 10)
            or (crop == "STRAWBERRY" and 9 <= age <= 15)
        )
        if useful:
            result.append(pos)
    return result


def _inventory_units(inventory):
    return sum(int((inventory or {}).get(item, 0)) for item in PRODUCTS)


def _assign_tasks(positions, free, tasks, actions):
    tasks = list(tasks)
    # Finish work already under a unit's feet before considering another route.
    # This turns CARE -> COLLECT -> HARVEST and WATER -> HARVEST into short local
    # sequences instead of sending the same worker across the farm whenever a
    # nominally higher-priority task appears elsewhere.
    for unit in sorted(tuple(free)):
        local = [
            (priority, operation[0], index, operation)
            for index, (priority, target, operation) in enumerate(tasks)
            if positions[unit] == target
        ]
        if not local:
            continue
        _priority, _name, index, operation = min(local)
        actions[unit] = operation
        free.remove(unit)
        tasks.pop(index)

    while free and tasks:
        best = None
        for unit in sorted(free):
            for index, (priority, target, operation) in enumerate(tasks):
                candidate = (
                    priority,
                    _distance(positions[unit], target),
                    target[1],
                    target[0],
                    operation[0],
                    unit,
                    index,
                )
                if best is None or candidate < best[0]:
                    best = (candidate, unit, index, target, operation)
        _key, unit, index, target, operation = best
        actions[unit] = operation if positions[unit] == target else _move(positions[unit], target, unit)
        free.remove(unit)
        tasks.pop(index)


def _unit_actions(obs, farm, policy, animal_goals):
    private = obs.get("private", {}) or {}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    size = len(farm.get("tiles", [])) or 10
    positions = [tuple(farm.get("farmer", (0, 0)))] + [tuple(pos) for pos in farm.get("hands", [])]
    inventories = list(private.get("inventories", []) or [])
    inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
    actions = [["PASS"] for _ in positions]
    free = set(range(len(positions)))
    shed = private.get("shed", {}) or {}
    animals = _animal_tiles(farm)
    layout = _layout(farm, animal_goals, policy)
    reserved = {pos for pos, _kind in layout}
    desired_kind = {pos: kind for pos, kind in layout}

    # The final afternoon is a dedicated bank run.  This is the only period in
    # which ordinary inventories are forced home; on normal days free end-day
    # auto-drop avoids hundreds of short DROP trips.
    if day >= 29 and hour >= 14:
        for unit in sorted(free):
            if _inventory_units(inventories[unit]):
                target = _nearest_shed(positions[unit], size)
                actions[unit] = ["DROP"] if _at_shed(positions[unit], size) else _move(positions[unit], target, unit)
        return actions

    # During a very large harvest wave, bank only the two fullest workers.  The
    # market layer can sell their predicted drops on this same turn.
    total_carried = sum(_inventory_units(inventory) for inventory in inventories)
    if day < 29 and total_carried >= 78:
        loaded = sorted(
            (unit for unit in free if _inventory_units(inventories[unit]) >= 18),
            key=lambda unit: (-_inventory_units(inventories[unit]), unit),
        )[:2]
        for unit in loaded:
            target = _nearest_shed(positions[unit], size)
            actions[unit] = ["DROP"] if _at_shed(positions[unit], size) else _move(positions[unit], target, unit)
            free.remove(unit)

    occupied = {pos for pos, _tile in animals}
    empty_slots = [pos for pos, _kind in layout if pos not in occupied]

    # Deliver already-carried animals, retaining the same target across turns
    # through deterministic nearest matching.
    claimed = set()
    for unit in sorted(tuple(free)):
        kind = next((name for name in ANIMALS if int(inventories[unit].get(name, 0)) > 0), None)
        if kind is None:
            continue
        choices = [pos for pos in empty_slots if desired_kind[pos] == kind and pos not in claimed]
        if not choices:
            continue
        target = min(choices, key=lambda pos: (_distance(positions[unit], pos), pos[1], pos[0]))
        claimed.add(target)
        tile = farm["tiles"][target[1]][target[0]]
        if positions[unit] != target:
            actions[unit] = _move(positions[unit], target, unit)
        elif tile is None:
            actions[unit] = ["BUILD_COOP" if kind == "GOOSE" else "BUILD_PASTURE"]
        elif isinstance(tile, dict) and tile.get("kind") == ANIMAL_STRUCTURE[kind] and not tile.get("animal"):
            actions[unit] = ["PLACE", kind]
        elif isinstance(tile, dict) and not tile.get("animal"):
            actions[unit] = ["DIG"]
        free.remove(unit)

    # Workers carrying feed keep servicing a compact nearest-neighbour tour.
    unfed = {pos for pos, tile in animals if not tile.get("fed_today", False)}
    for unit in sorted(tuple(free)):
        if int(inventories[unit].get("WHEAT", 0)) <= 0 or not unfed:
            continue
        target = min(unfed, key=lambda pos: (_distance(positions[unit], pos), pos[1], pos[0]))
        unfed.remove(target)
        actions[unit] = ["FEED"] if positions[unit] == target else _move(positions[unit], target, unit)
        free.remove(unit)

    # Fertilizer is applied directly from the carrier instead of taking a shed
    # round trip.  Targets are spaced around imminent premium production days.
    fertilizer_targets = _fertilizer_targets(obs, farm, reserved)
    claimed_fertilizer = set()
    for unit in sorted(tuple(free)):
        if int(inventories[unit].get("FERTILIZER", 0)) <= 0:
            continue
        choices = [pos for pos in fertilizer_targets if pos not in claimed_fertilizer]
        if not choices:
            continue
        target = min(choices, key=lambda pos: (_distance(positions[unit], pos), pos[1], pos[0]))
        claimed_fertilizer.add(target)
        actions[unit] = ["FERTILIZE"] if positions[unit] == target else _move(positions[unit], target, unit)
        free.remove(unit)

    # At the shed, create animal and feed carriers.  Player actions precede the
    # market, so wheat/animals bought this turn naturally become available on
    # the following observation.
    # Feed pickups precede animal pickups: an extra day in the shed is cheaper
    # than allowing an existing animal to escape.
    serviceable = sum(min(6, int(inventory.get("WHEAT", 0))) for inventory in inventories)
    feed_shortage = max(0, len(unfed))
    available_feed = min(feed_shortage, int(shed.get("WHEAT", 0)))
    for unit in sorted(tuple(free)):
        if available_feed <= 0 or not _at_shed(positions[unit], size):
            continue
        share = min(6, available_feed)
        actions[unit] = ["PICKUP", "WHEAT", share]
        available_feed -= share
        free.remove(unit)

    waiting = collections.Counter({kind: int(shed.get(kind, 0)) for kind in ANIMALS})
    for unit in sorted(tuple(free)):
        if not _at_shed(positions[unit], size):
            continue
        kind = next(
            (
                name
                for name in ("SHEEP", "COW", "GOOSE")
                if waiting[name] > 0
                and any(desired_kind[pos] == name and pos not in claimed for pos in empty_slots)
            ),
            None,
        )
        if kind is None:
            continue
        actions[unit] = ["PICKUP", kind, 1]
        waiting[kind] -= 1
        free.remove(unit)

    # If feed is waiting but every idle unit is in the field, send only enough
    # workers home to cover the unresolved animals in six-unit tours.
    unresolved = max(0, len(unfed) - int(shed.get("WHEAT", 0) > 0) * 6)
    if unresolved and int(shed.get("WHEAT", 0)) > 0:
        fetchers = min(len(free), max(1, math.ceil(unresolved / 6)))
        choices = sorted(free, key=lambda unit: (_distance(positions[unit], _nearest_shed(positions[unit], size)), unit))
        for unit in choices[:fetchers]:
            target = _nearest_shed(positions[unit], size)
            actions[unit] = ["PICKUP", "WHEAT", min(6, unresolved)] if _at_shed(positions[unit], size) else _move(positions[unit], target, unit)
            unresolved -= 6
            free.remove(unit)

    tasks = []
    if day < 29:
        for pos, tile in animals:
            operation = None
            if not tile.get("cared_today", False):
                operation = (1, pos, ["CARE"])
            elif tile.get("fertilizer_available", False):
                operation = (2, pos, ["COLLECT_FERTILIZER"])
            held = int(tile.get("yield_units", 0))
            if operation is None and (held >= 3 or (held > 0 and day >= 27)):
                operation = (3, pos, ["HARVEST"])
            # One worker visits a tile and performs its operations on successive
            # turns.  Sending three workers to CARE/COLLECT/HARVEST in parallel
            # was fast but reproduced the incumbent's excessive movement.
            if operation is not None:
                tasks.append(operation)
    else:
        prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
        for pos, tile in animals:
            held = int(tile.get("yield_units", 0))
            if held:
                tasks.append((0, pos, ["HARVEST"]))
            if tile.get("fertilizer_available", False):
                tasks.append((1, pos, ["COLLECT_FERTILIZER"]))

    tasks.extend(_crop_tasks(obs, farm, policy, animal_goals, reserved))

    # Prepare compact animal slots only after survival and harvest work.
    if day < 20:
        owned_for_build = _owned_animals(farm, private)
        seen_kind = collections.Counter()
        for pos, kind in layout:
            seen_kind[kind] += 1
            if seen_kind[kind] > int(owned_for_build[kind]):
                continue
            if pos in occupied or pos in claimed:
                continue
            tile = farm["tiles"][pos[1]][pos[0]]
            structure = ANIMAL_STRUCTURE[kind]
            if tile is None:
                tasks.append((5, pos, ["BUILD_COOP" if structure == "COOP" else "BUILD_PASTURE"]))
            elif isinstance(tile, dict) and tile.get("kind") != structure and not tile.get("animal"):
                tasks.append((5, pos, ["DIG"]))

    _assign_tasks(positions, free, tasks, actions)
    return actions


def _fib_cost(existing, additional):
    a, b = 1, 1
    costs = []
    for _ in range(existing + additional):
        costs.append(a)
        a, b = b, a + b
    return sum(costs[existing : existing + additional])


def _liquidation(obs, actions, animal_count):
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    day = int(obs.get("day", 0))
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    hour = int(obs.get("hour", 0))
    amounts = {item: int(shed.get(item, 0)) for item in PRODUCTS}
    inventories = private.get("inventories", []) or []
    for unit, action in enumerate(actions):
        if action and action[0] == "DROP" and unit < len(inventories):
            for item in PRODUCTS:
                amounts[item] += int((inventories[unit] or {}).get(item, 0))

    feed_reserve = 0 if day >= 29 else max(8, int(math.ceil(animal_count * 2.0)))
    amounts["WHEAT"] = max(0, amounts["WHEAT"] - feed_reserve)
    total_shed = sum(int(value) for value in shed.values())
    for item, floor in PREMIUM_HOLD_PRICE.items():
        if day < 26 and total_shed < 72 and int(prices.get(item, 1)) < floor:
            amounts[item] = 0

    # Recurring premium curves collapse when a multi-day stockpile is dumped
    # in one order.  Sell approximately one day of town demand over hours 0--1
    # and let consumption rebuild the scarcity tail before the next batch.
    # Melons are deliberately excluded: the opening cohort should front-run
    # the common day-10 wave in one sale.
    if day < 29:
        shops = _shop_counts(obs)
        daily_demand = {
            "STRAWBERRY": 1 + 6 * (
                shops["BRUNCH_SPOT"]
                + shops["ICE_CREAM_SHOP"]
                + shops["SMOOTHIE_SHOP"]
                + shops["FARMERS_MARKET"]
            ),
            "MILK": 1 + 6 * (shops["PIZZA_SHOP"] + shops["ICE_CREAM_SHOP"] + shops["SMOOTHIE_SHOP"]),
            "WOOL": 1 + 12 * shops["YARN_STORE"],
        }
        for item, demand in daily_demand.items():
            quantity = int(amounts[item])
            if quantity <= 0:
                continue
            if hour > 1 and total_shed < 80:
                amounts[item] = 0
                continue
            cap = max(6, int(math.ceil(demand / 2)))
            if day >= 26:
                cap = max(cap, int(math.ceil(quantity / max(1, 29 - day))))
            amounts[item] = min(quantity, cap)
    return amounts


def _market_actions(obs, farm, actions, policy, animal_goals, reserved):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    animals = _animal_tiles(farm)
    animal_count = len(animals)
    amounts = _liquidation(obs, actions, animal_count)
    orders = []

    sales = [item for item, quantity in amounts.items() if quantity > 0]
    sales.sort(key=lambda item: (-amounts[item] * int(prices.get(item, 1)), item))

    desired_hires = int(policy["hands"]) if hour <= 1 else 0
    # The final day still needs a complete harvest and return crew.
    if day >= 29:
        desired_hires = min(desired_hires, 8)
    existing_hires = int(farm.get("hires_today", 0))
    missing_hires = max(0, desired_hires - existing_hires)

    # Sell first to fund the day's crew, but reserve enough slots to finish
    # hiring over hours zero and one.
    sale_limit = max(0, 10 - min(missing_hires, 6))
    for item in sales[:sale_limit]:
        orders.append(["SELL", item, amounts[item]])
    hire_now = min(missing_hires, 10 - len(orders))
    for _ in range(hire_now):
        orders.append(["HIRE"])

    liquid = float(farm.get("money", 0))
    liquid += sum(amounts[item] * int(prices.get(item, 1)) * 0.72 for item in sales[:sale_limit])
    liquid -= _fib_cost(existing_hires, hire_now)
    if day >= 29:
        return orders[:10]

    reserve = max(300.0, animal_count * int(prices.get("WHEAT", 25)) * 1.25)

    quadrants = len(farm.get("unlocked_quadrants", []))
    if 3 <= day <= 11 and quadrants < int(policy["land"]) and len(orders) < 10:
        land_cost = (1000, 2000, 4000)[min(2, max(0, quadrants - 1))]
        if liquid >= reserve + land_cost:
            orders.append(["BUY_LAND"])
            liquid -= land_cost

    owned = _owned_animals(farm, private)
    slot_capacity = collections.Counter(kind for _pos, kind in _layout(farm, animal_goals, policy))
    if day <= 17:
        # Purchase small waves so placement keeps up and money is not trapped in
        # the shed.  Each policy's defining animal receives first priority.
        if policy is POLICIES["milk"]:
            order = ("COW", "SHEEP", "GOOSE")
        elif policy is POLICIES["tomato_goose"]:
            order = ("GOOSE", "COW", "SHEEP")
        else:
            order = ("SHEEP", "COW", "GOOSE")
        for kind in order:
            if len(orders) >= 10:
                break
            missing = max(0, min(int(animal_goals[kind]), int(slot_capacity[kind])) - int(owned[kind]))
            affordable = max(0, int((liquid - reserve) // ANIMAL_COST[kind]))
            quantity = min(3, missing, affordable)
            if quantity:
                orders.append(["BUY_ANIMAL", kind, quantity])
                owned[kind] += quantity
                liquid -= quantity * ANIMAL_COST[kind]

    needs = _seed_needs(obs, farm, policy, animal_goals, reserved)
    if day <= 2:
        # Opening crop timing is non-recoverable: fund the day-10 melon wave
        # before buying feed that can safely wait until the following hour.
        for crop in ("MELON", "WHEAT"):
            if len(orders) >= 10:
                break
            quantity = int(needs[crop])
            affordable = max(0, int((liquid - reserve) // int(CROPS[crop]["seed"])))
            quantity = min(quantity, affordable)
            if quantity:
                orders.append(["BUY_SEED", crop, quantity])
                liquid -= quantity * int(CROPS[crop]["seed"])

    # Farm wheat is retained as feed.  Market wheat is only the two-day reserve
    # shortfall, preventing the buy-306/sell-140 pattern in the submitted bot.
    total_wheat = int(shed.get("WHEAT", 0)) + _carried(private, "WHEAT")
    target_wheat = max(8, int(math.ceil((animal_count + sum(int(shed.get(k, 0)) for k in ANIMALS)) * 2.0)))
    shortage = max(0, target_wheat - total_wheat)
    if shortage and day < 29 and len(orders) < 10:
        wheat_price = max(1, int(prices.get("WHEAT", 25)))
        affordable = max(0, int((liquid - reserve * 0.35) // wheat_price))
        quantity = min(shortage, affordable)
        if quantity:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            liquid -= quantity * wheat_price

    if day > 2:
        for crop in ("STRAWBERRY", "TOMATO", "WHEAT", "CARROT"):
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


def agent_for(obs, archetype="melon_strawberry"):
    """Return an action for one named live archetype."""
    policy = POLICIES.get(archetype)
    if policy is None:
        raise ValueError(f"unknown live archetype: {archetype}")
    farms = obs.get("farms", []) or []
    try:
        player = int(obs.get("player", 0))
    except (TypeError, ValueError):
        player = 0
    if player < 0 or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    goals = _animal_goals(obs, policy)
    layout = _layout(farm, goals, policy)
    reserved = {pos for pos, _kind in layout}
    actions = _unit_actions(obs, farm, policy, goals)
    market = _market_actions(obs, farm, actions, policy, goals, reserved)
    return {
        "farmer": actions[0] if actions else ["PASS"],
        "hands": actions[1:],
        "market": market,
    }


def agent(obs):
    """Default to the balanced melon/strawberry live archetype."""
    return agent_for(obs, "melon_strawberry")
