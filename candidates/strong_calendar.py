"""Calendar-aware hybrid built from the public Kaggriculture contract.

This candidate is intentionally separate from :mod:`candidates.hybrid_core`.
It keeps the live bot's useful livestock economics, but uses a smaller opening,
an early melon liquidity wave, explicit recurring-crop calendars, compact
quadrant layouts, task-sized labor, and large carrier batches.

All decisions are reconstructed from the observation.  There is no episode
state, so the same module is safe in either seat and in concurrent games.
"""

from __future__ import annotations

import math
from collections import Counter

from candidates.crop import CROPS, MARKET, PRODUCTS, _average_sale
from candidates.livestock import ANIMAL_COST, ANIMAL_PRODUCT, ANIMAL_STRUCTURE


ANIMALS = tuple(ANIMAL_PRODUCT)
SELLABLE = tuple(PRODUCTS)
BASE_PRICE = {
    "WHEAT": 25,
    "CARROT": 35,
    "TOMATO": 60,
    "STRAWBERRY": 120,
    "MELON": 250,
    "EGG": 50,
    "MILK": 160,
    "WOOL": 200,
    "FERTILIZER": 100,
}
SHOP_DEMAND = {
    "BAKERY": {"EGG": 6, "WHEAT": 6},
    "PIZZA_SHOP": {"MILK": 6, "TOMATO": 6, "WHEAT": 6},
    "BRUNCH_SPOT": {"EGG": 6, "WHEAT": 6, "STRAWBERRY": 6},
    "YARN_STORE": {"WOOL": 12},
    "ICE_CREAM_SHOP": {"STRAWBERRY": 6, "MILK": 6, "WHEAT": 6},
    "PET_CAFE": {"CARROT": 12},
    "SMOOTHIE_SHOP": {"STRAWBERRY": 6, "MILK": 6},
    "FARMERS_MARKET": {
        "WHEAT": 6,
        "CARROT": 6,
        "TOMATO": 6,
        "STRAWBERRY": 6,
    },
}
OUTPUT_RATE = {"GOOSE": 2.0, "COW": 1.5, "SHEEP": 4.0 / 3.0}
PRODUCT_ANIMAL = {product: kind for kind, product in ANIMAL_PRODUCT.items()}


POLICY = {
    "opening_animals": {"GOOSE": 0, "COW": 1, "SHEEP": 1},
    "opening_melons": 9,
    "opening_wheat": 6,
    "opening_feed": 4,
    "opening_hands": 5,
    "routine_hands": 9,
    "peak_hands": 10,
    "animal_cap": 15,
    "animal_caps": {"GOOSE": 6, "COW": 10, "SHEEP": 10},
    "strawberry_floor": 30,
    "strawberry_target": 34,
    "strawberry_cap": 38,
    "daily_plant_cap": 12,
    "land_goal": 3,
    "carrier_batch": 18,
    "feed_batch": 6,
}


def _owned_cells(farm):
    for y, row in enumerate(farm.get("tiles", []) or []):
        for x, tile in enumerate(row):
            if tile != "LOCKED":
                yield x, y, tile


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _shed_tiles(size):
    half = size // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _at_shed(pos, size):
    return tuple(pos) in _shed_tiles(size)


def _nearest_shed(pos, size):
    return min(_shed_tiles(size), key=lambda target: (_distance(pos, target), target[1], target[0]))


def _step_toward(source, target, unit=0):
    x, y = source
    tx, ty = target
    # Alternating the first axis prevents co-located hands from convoying.
    if unit % 2 == 0 and x != tx:
        return ["EAST" if tx > x else "WEST"]
    if y != ty:
        return ["SOUTH" if ty > y else "NORTH"]
    if x != tx:
        return ["EAST" if tx > x else "WEST"]
    return ["PASS"]


def _quadrant(pos, size):
    x, y = pos
    half = size // 2
    return ("S" if y >= half else "N") + ("E" if x >= half else "W")


def _quadrant_slots(size, unlocked):
    """Return shed-facing snakes for every owned quadrant."""
    half = size // 2
    result = []

    def add(name, xs, ys):
        if name not in unlocked:
            return
        for row_number, y in enumerate(ys):
            row = list(xs)
            if row_number % 2:
                row.reverse()
            result.extend((x, y) for x in row)

    add("NW", range(half - 1, -1, -1), range(half - 1, -1, -1))
    add("NE", range(half, size), range(half - 1, -1, -1))
    add("SW", range(half - 1, -1, -1), range(half, size))
    add("SE", range(half, size), range(half, size))
    return result


def _all_animal_slots(size):
    """Permanent compact animal strips; crops never occupy these cells."""
    half = size // 2
    rings = []
    for radius in range(size):
        ring = []
        for y in range(size):
            for x in range(size):
                if max(abs(x - (half - 0.5)), abs(y - (half - 0.5))) != radius + 0.5:
                    continue
                if _quadrant((x, y), size) == "SE":
                    continue
                ring.append((x, y))
        ring.sort(key=lambda p: (_distance(p, _nearest_shed(p, size)), p[1], p[0]))
        rings.extend(ring)
    # Balance the first positions across the three intended quadrants.
    by_quadrant = {
        name: [p for p in rings if _quadrant(p, size) == name]
        for name in ("NW", "NE", "SW")
    }
    answer = []
    while any(by_quadrant.values()):
        for name in ("NW", "NE", "SW"):
            if by_quadrant[name]:
                answer.append(by_quadrant[name].pop(0))
    return answer[: int(POLICY["animal_cap"])]


def _animal_tiles(farm):
    result = []
    for x, y, tile in _owned_cells(farm):
        if isinstance(tile, dict) and tile.get("animal"):
            result.append(((x, y), tile))
    return result


def _active_crops(farm):
    counts = Counter()
    for _x, _y, tile in _owned_cells(farm):
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            counts[tile.get("crop")] += 1
    return counts


def _pending(private, item):
    return int((private.get("shed", {}) or {}).get(item, 0)) + sum(
        int((inventory or {}).get(item, 0))
        for inventory in private.get("inventories", []) or []
    )


def _owned_animals(farm, private):
    counts = Counter(tile["animal"] for _pos, tile in _animal_tiles(farm))
    for kind in ANIMALS:
        counts[kind] += _pending(private, kind)
    return counts


def _opponent_counts(obs):
    player = int(obs.get("player", 0))
    crops = Counter()
    animals = Counter()
    for index, farm in enumerate(obs.get("farms", []) or []):
        if index == player:
            continue
        crops.update(_active_crops(farm))
        animals.update(tile["animal"] for _pos, tile in _animal_tiles(farm))
    return crops, animals


def _shop_counts(obs):
    return Counter((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])


def _town_rates(obs):
    rates = {item: 1.0 for item in BASE_PRICE if item != "FERTILIZER"}
    for shop in (obs.get("town", {}) or {}).get("unlocked_shops", []) or []:
        for item, amount in SHOP_DEMAND.get(shop, {}).items():
            rates[item] += amount
    return rates


def _animal_goals(obs):
    day = int(obs.get("day", 0))
    opening = Counter(POLICY["opening_animals"])
    if day < 3:
        return {kind: opening[kind] for kind in ANIMALS}

    rates = _town_rates(obs)
    _crops, opponent = _opponent_counts(obs)
    floors = {"GOOSE": 0, "COW": 2, "SHEEP": 2}
    goals = {}
    for product, kind in PRODUCT_ANIMAL.items():
        residual = max(0.0, rates[product] - opponent[kind] * OUTPUT_RATE[kind] * 0.80)
        goals[kind] = max(floors[kind], int(math.ceil(residual / OUTPUT_RATE[kind])))

    shops = _shop_counts(obs)
    if shops["BAKERY"] or shops["BRUNCH_SPOT"]:
        goals["GOOSE"] = max(1, goals["GOOSE"])
    caps = POLICY["animal_caps"]
    goals = {kind: min(int(caps[kind]), max(opening[kind], goals[kind])) for kind in ANIMALS}

    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    while sum(goals.values()) > int(POLICY["animal_cap"]):
        removable = [kind for kind in ANIMALS if goals[kind] > max(opening[kind], floors[kind])]
        if not removable:
            break
        # Trim the least profitable marginal capacity first.
        kind = min(
            removable,
            key=lambda item: (
                OUTPUT_RATE[item] * int(prices.get(ANIMAL_PRODUCT[item], BASE_PRICE[ANIMAL_PRODUCT[item]]))
                + int(prices.get("FERTILIZER", 100))
                - int(prices.get("WHEAT", 25)),
                goals[item],
                item,
            ),
        )
        goals[kind] -= 1
    return goals


def _strawberry_goal(obs, opponent_crops):
    shops = _shop_counts(obs)
    strawberry_shops = sum(
        shops[name]
        for name in ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET")
    )
    opponent_strawberries = int(opponent_crops["STRAWBERRY"])
    target = int(POLICY["strawberry_target"]) + 2 * strawberry_shops
    # A visible leaderboard-sized block is real residual supply, not a reason
    # to mirror into the $1 floor.  Normal games still maintain a 30-38 cohort;
    # the counter branch reallocates only after the opponent exposes 28 tiles.
    counter_floor = int(POLICY["strawberry_floor"])
    subtraction = 0.25
    if opponent_strawberries >= 28:
        counter_floor = 18
        subtraction = 0.60
    target -= int(round(opponent_strawberries * subtraction))
    return max(
        counter_floor,
        min(int(POLICY["strawberry_cap"]), target),
    )


def _crop_goals(obs, farm, animal_count):
    day = int(obs.get("day", 0))
    rates = _town_rates(obs)
    opponent, _animals = _opponent_counts(obs)
    goals = Counter()

    # The day-zero wave is a liquidity instrument, not a repeating monoculture.
    if day == 0:
        goals["MELON"] = int(POLICY["opening_melons"])
        goals["WHEAT"] = int(POLICY["opening_wheat"])
        return goals

    goals["WHEAT"] = max(6, int(math.ceil(animal_count * 1.15)))

    if day <= 13:
        final_strawberries = _strawberry_goal(obs, opponent)
        if day < 3:
            goals["STRAWBERRY"] = 0
        elif day <= 5:
            goals["STRAWBERRY"] = min(12, final_strawberries)
        elif day <= 8:
            goals["STRAWBERRY"] = min(24, final_strawberries)
        else:
            goals["STRAWBERRY"] = final_strawberries

    shops = _shop_counts(obs)
    if day <= 17 and (shops["PIZZA_SHOP"] or shops["FARMERS_MARKET"]):
        residual = max(0.0, rates["TOMATO"] - opponent["TOMATO"] * 0.50)
        goals["TOMATO"] = min(14, max(3, int(math.ceil(residual / 0.65))))
    if day <= 25 and (shops["PET_CAFE"] or shops["FARMERS_MARKET"]):
        residual = max(0.0, rates["CARROT"] - opponent["CARROT"] * 0.90)
        goals["CARROT"] = min(16, max(3, int(math.ceil(residual / 1.0))))

    # A small second melon sleeve is permitted only in a visibly unglutted
    # market after the opening crop has paid, never into a large opposing wave.
    market = obs.get("market", {}) or {}
    price = int((market.get("prices", {}) or {}).get("MELON", 250))
    if 10 <= day <= 17 and opponent["MELON"] <= 5 and price >= 210:
        goals["MELON"] = 4
    return goals


def _crop_priority(day, crop):
    if day == 0:
        return {"MELON": 0, "WHEAT": 1}.get(crop, 9)
    if day <= 13:
        return {"STRAWBERRY": 0, "WHEAT": 1, "TOMATO": 2, "CARROT": 3, "MELON": 4}.get(crop, 9)
    return {"WHEAT": 0, "CARROT": 1, "TOMATO": 2, "MELON": 3}.get(crop, 9)


def _soon_vacancies(farm, day):
    counts = Counter()
    for _x, _y, tile in _owned_cells(farm):
        if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        data = CROPS.get(crop)
        if not data:
            continue
        age = day - int(tile.get("planted_day", day))
        if (data["ongoing"] and age >= data["last"]) or (not data["ongoing"] and age >= data["peak"]):
            counts[crop] += 1
    return counts


def _seed_plan(obs, farm, reserved):
    day = int(obs.get("day", 0))
    if day >= 28:
        return {}
    private = obs.get("private", {}) or {}
    active = _active_crops(farm)
    goals = _crop_goals(obs, farm, len(_animal_tiles(farm)))
    soon = _soon_vacancies(farm, day)
    empty = sum(tile is None and (x, y) not in reserved for x, y, tile in _owned_cells(farm))
    planted_today = sum(
        isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and int(tile.get("planted_day", -1)) == day
        for _x, _y, tile in _owned_cells(farm)
    )
    capacity = min(empty + sum(soon.values()), max(0, int(POLICY["daily_plant_cap"]) - planted_today))
    seeds = private.get("seeds", {}) or {}
    # Existing seed stock already consumes near-term planting capacity.  This
    # prevents the market layer from buying a fresh twelve-pack every morning
    # while the service crew is still placing yesterday's cohort.
    usable_stock = sum(
        max(0, int(quantity))
        for crop, quantity in seeds.items()
        if crop in CROPS and CROPS[crop]["peak"] <= 29 - day
    )
    capacity = max(0, capacity - usable_stock)
    deficits = {}
    for crop, goal in goals.items():
        if CROPS[crop]["peak"] > 29 - day:
            continue
        keep = soon[crop] if crop in ("WHEAT", "CARROT") else 0
        deficits[crop] = max(0, int(goal) - active[crop] + keep - int(seeds.get(crop, 0)))

    result = {}
    for crop in sorted(deficits, key=lambda item: (_crop_priority(day, item), item)):
        quantity = min(deficits[crop], capacity)
        if quantity > 0:
            result[crop] = quantity
            capacity -= quantity
        if capacity <= 0:
            break
    return result


def _crop_assignments(obs, farm, reserved):
    day = int(obs.get("day", 0))
    private = obs.get("private", {}) or {}
    pool = Counter({crop: int(value) for crop, value in (private.get("seeds", {}) or {}).items()})
    if not any(pool.values()):
        return {}
    active = _active_crops(farm)
    goals = _crop_goals(obs, farm, len(_animal_tiles(farm)))
    planted_today = sum(
        isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and int(tile.get("planted_day", -1)) == day
        for _x, _y, tile in _owned_cells(farm)
    )
    room = max(0, int(POLICY["daily_plant_cap"]) - planted_today)
    wanted = []
    for crop in sorted(goals, key=lambda item: (_crop_priority(day, item), item)):
        quantity = min(pool[crop], max(0, int(goals[crop]) - active[crop]))
        wanted.extend([crop] * quantity)
    # Sunk seeds with time to mature fill unused capacity after target seeds.
    for crop in sorted(CROPS, key=lambda item: (_crop_priority(day, item), item)):
        if CROPS[crop]["peak"] <= 29 - day:
            wanted.extend([crop] * max(0, pool[crop] - wanted.count(crop)))
    wanted = wanted[:room]

    size = len(farm.get("tiles", []) or []) or 10
    unlocked = set(farm.get("unlocked_quadrants", []) or [])
    empties = [
        pos
        for pos in _quadrant_slots(size, unlocked)
        if pos not in reserved and farm["tiles"][pos[1]][pos[0]] is None
    ]
    assignments = {}
    for pos, crop in zip(empties, wanted):
        if pool[crop] <= 0:
            continue
        assignments[pos] = crop
        pool[crop] -= 1
    return assignments


def _animal_assignments(farm, private, goals):
    size = len(farm.get("tiles", []) or []) or 10
    slots = [
        pos
        for pos in _all_animal_slots(size)
        if farm["tiles"][pos[1]][pos[0]] != "LOCKED"
    ]
    occupied = {pos for pos, _tile in _animal_tiles(farm)}
    kinds = []
    for kind in ("SHEEP", "COW", "GOOSE"):
        kinds.extend([kind] * _pending(private, kind))
    owned = _owned_animals(farm, private)
    for kind in ("SHEEP", "COW", "GOOSE"):
        kinds.extend([kind] * min(2, max(0, int(goals[kind]) - int(owned[kind]))))
    result = []
    available = [pos for pos in slots if pos not in occupied]
    for kind in kinds:
        matching = [
            pos
            for pos in available
            if isinstance(farm["tiles"][pos[1]][pos[0]], dict)
            and farm["tiles"][pos[1]][pos[0]].get("kind") == ANIMAL_STRUCTURE[kind]
            and not farm["tiles"][pos[1]][pos[0]].get("animal")
        ]
        if not available:
            break
        pos = matching[0] if matching else available[0]
        available.remove(pos)
        result.append((pos, kind))
    return result


def _fertilizer_targets(obs, farm):
    day = int(obs.get("day", 0))
    if day >= 29:
        return []
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    fertilizer_value = max(1, int(prices.get("FERTILIZER", 100)))
    result = []
    # Production is posted at the day refresh.  Therefore a crop whose first
    # documented yield age is 10 must be watered/fertilized on current age 9.
    # One three-day application at strawberry ages 9 and 13 covers all four
    # outputs; the former rolling-window code spent roughly three applications
    # per plant while capturing almost no doubled yield.
    schedules = {"TOMATO": (7, 8, 9, 10), "STRAWBERRY": (9, 11, 13, 15)}
    for x, y, tile in _owned_cells(farm):
        if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        if crop not in schedules:
            continue
        planted = int(tile.get("planted_day", day))
        age = day - planted
        future = [value for value in schedules[crop] if value >= age]
        if not future or future[0] != age:
            continue
        until = int(tile.get("fertilized_until_day", -1))
        # Never roll a still-active window forward one day at a time.  Wait for
        # it to expire, then place the next application beside an actual yield.
        if until >= day:
            continue
        covered = [value for value in future if value <= age + 2]
        uncovered = [value for value in covered if planted + value > until]
        value = len(uncovered) * int(prices.get(crop, BASE_PRICE[crop]))
        if uncovered and value >= fertilizer_value * 1.05:
            result.append((value, (x, y)))
    return [pos for _value, pos in sorted(result, key=lambda row: (-row[0], row[1][1], row[1][0]))]


def _fertilizer_reserve_need(obs, farm):
    """Fertilizer to retain for applications due today or tomorrow."""
    day = int(obs.get("day", 0))
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    fertilizer_value = max(1, int(prices.get("FERTILIZER", 100)))
    application_days = {"TOMATO": (7, 10), "STRAWBERRY": (9, 13)}
    need = 0
    for _x, _y, tile in _owned_cells(farm):
        if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        if crop not in application_days:
            continue
        planted = int(tile.get("planted_day", day))
        age = day - planted
        until = int(tile.get("fertilized_until_day", -1))
        for offset in (0, 1):
            target_age = age + offset
            if target_age not in application_days[crop] or until >= day + offset:
                continue
            extra_units = 3 if crop == "TOMATO" and target_age == 7 else 1 if crop == "TOMATO" else 2
            if extra_units * int(prices.get(crop, BASE_PRICE[crop])) >= fertilizer_value * 1.05:
                need += 1
            break
    return need


def _field_jobs(obs, farm, reserved):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    jobs = []
    for x, y, tile in _owned_cells(farm):
        pos = (x, y)
        if not isinstance(tile, dict):
            continue
        if tile.get("kind") == "WEED":
            if day < 29 and pos not in reserved:
                jobs.append((7, pos, ["DIG"], "CROP"))
            continue
        if tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        data = CROPS.get(crop)
        if not data:
            continue
        age = day - int(tile.get("planted_day", day))
        units = int(tile.get("yield_units", 0))
        watered = bool(tile.get("watered_today", False))
        missed = int(tile.get("consecutive_unwatered", 0))

        if day >= 29:
            travel = _distance(pos, _nearest_shed(pos, len(farm.get("tiles", [])) or 10))
            if units > 0 and hour + travel + 2 <= 22:
                jobs.append((0, pos, ["HARVEST"], "CROP"))
            continue

        if data["ongoing"]:
            expiring = age >= data["last"]
            if units >= 2 or (units > 0 and expiring):
                jobs.append((1 if expiring else 3, pos, ["HARVEST"], "CROP"))
            if not watered:
                jobs.append((0 if missed >= 1 else 5, pos, ["WATER"], "CROP"))
        else:
            bonus_start = (data["last"] + 1) // 2
            bonus = bonus_start <= age <= data["last"] and units < data["yield"]
            if not watered and (missed >= 1 or bonus):
                jobs.append((0 if missed >= 1 else 2, pos, ["WATER"], "CROP"))
            if age >= data["peak"] and units > 0 and (watered or not bonus):
                jobs.append((2, pos, ["HARVEST"], "CROP"))
            elif age > data["last"] and units > 0:
                jobs.append((1, pos, ["HARVEST"], "CROP"))

    if day < 28 and hour <= 19:
        for pos, crop in _crop_assignments(obs, farm, reserved).items():
            jobs.append((2, pos, ["PLANT", crop], "CROP"))
    return jobs


def _inventory_units(inventory, include_wheat=False):
    ignored = {"FERTILIZER"}
    if not include_wheat:
        ignored.add("WHEAT")
    return sum(
        int(quantity)
        for item, quantity in (inventory or {}).items()
        if item in SELLABLE and item not in ignored
    )


def _home_zone(unit, unlocked):
    zones = [name for name in ("NW", "NE", "SW", "SE") if name in unlocked]
    if not zones:
        return "NW"
    # Six workers anchor the central animal/feed crew; the last two are flex
    # hands shared with the crop strips.
    if unit < 6:
        return "CENTER"
    return zones[(unit - 6) % len(zones)]


def _assign_jobs(positions, free, jobs, size, unlocked, actions):
    jobs = list(jobs)
    while free and jobs:
        best = None
        for unit in sorted(free):
            home = _home_zone(unit, unlocked)
            for index, (priority, target, action, category) in enumerate(jobs):
                # Persistent crews eliminate the daily all-hands commute from
                # outer crop strips to the central herd.  Unit three is the
                # flex worker and can serve either side when deadlines collide.
                if category == "ANIMAL" and unit >= 6:
                    continue
                if category == "CROP" and unit < 4:
                    continue
                target_zone = _quadrant(target, size)
                mismatch = 0
                if home == "CENTER":
                    mismatch = 0 if category == "ANIMAL" else 3
                elif target_zone != home:
                    mismatch = 12
                key = (priority, _distance(positions[unit], target) + mismatch, target[1], target[0], action[0], unit)
                if best is None or key < best[0]:
                    best = (key, unit, index, target, action)
        if best is None:
            break
        _key, unit, index, target, action = best
        free.remove(unit)
        jobs.pop(index)
        actions[unit] = action if positions[unit] == target else _step_toward(positions[unit], target, unit)


def _unit_actions(obs, farm, goals):
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    size = len(farm.get("tiles", []) or []) or 10
    positions = [tuple(farm.get("farmer", (0, 0))), *[tuple(pos) for pos in farm.get("hands", []) or []]]
    inventories = list(private.get("inventories", []) or [])
    inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
    actions = [["PASS"] for _ in positions]
    free = set(range(len(positions)))
    animals = _animal_tiles(farm)
    unlocked = set(farm.get("unlocked_quadrants", []) or [])
    reserved = set(_all_animal_slots(size))
    assignments = _animal_assignments(farm, private, goals)

    if day >= 29 and hour >= 14:
        for unit in sorted(free):
            if inventories[unit]:
                target = _nearest_shed(positions[unit], size)
                actions[unit] = ["DROP"] if _at_shed(positions[unit], size) else _step_toward(positions[unit], target, unit)
        return actions

    # Place purchased livestock in the compact central strips.
    used = set()
    for unit in sorted(tuple(free)):
        kind = next((item for item in ANIMALS if inventories[unit].get(item, 0) > 0), None)
        if kind is None:
            continue
        choices = [pos for pos, wanted in assignments if wanted == kind and pos not in used]
        if not choices:
            continue
        target = min(choices, key=lambda pos: (_distance(positions[unit], pos), pos[1], pos[0]))
        used.add(target)
        tile = farm["tiles"][target[1]][target[0]]
        if positions[unit] != target:
            actions[unit] = _step_toward(positions[unit], target, unit)
        elif tile is None:
            actions[unit] = ["BUILD_COOP" if kind == "GOOSE" else "BUILD_PASTURE"]
        elif isinstance(tile, dict) and tile.get("kind") == ANIMAL_STRUCTURE[kind] and not tile.get("animal"):
            actions[unit] = ["PLACE", kind]
        elif isinstance(tile, dict) and not tile.get("animal"):
            actions[unit] = ["DIG"]
        free.remove(unit)

    waiting = Counter({kind: int(shed.get(kind, 0)) for kind in ANIMALS})
    for unit in sorted(tuple(free)):
        if not _at_shed(positions[unit], size):
            continue
        kind = next(
            (
                item
                for item in ("SHEEP", "COW", "GOOSE")
                if waiting[item] > 0 and any(wanted == item and pos not in used for pos, wanted in assignments)
            ),
            None,
        )
        if kind is not None:
            actions[unit] = ["PICKUP", kind, 1]
            waiting[kind] -= 1
            free.remove(unit)

    unfed = [] if day >= 29 else [(pos, tile) for pos, tile in animals if not tile.get("fed_today", False)]
    remaining_feed_targets = {pos for pos, _tile in unfed}
    for unit in sorted(tuple(free)):
        if int(inventories[unit].get("WHEAT", 0)) <= 0 or not remaining_feed_targets:
            continue
        target = min(remaining_feed_targets, key=lambda pos: (_distance(positions[unit], pos), pos[1], pos[0]))
        remaining_feed_targets.remove(target)
        actions[unit] = ["FEED"] if positions[unit] == target else _step_toward(positions[unit], target, unit)
        free.remove(unit)

    wheat_in_field = sum(int(inventory.get("WHEAT", 0)) for inventory in inventories)
    uncovered = max(0, len(unfed) - wheat_in_field)
    carriers_needed = int(math.ceil(uncovered / int(POLICY["feed_batch"])))
    for unit in sorted(tuple(free)):
        if carriers_needed <= 0 or int(shed.get("WHEAT", 0)) <= 0:
            break
        if _at_shed(positions[unit], size):
            amount = min(int(POLICY["feed_batch"]), int(shed.get("WHEAT", 0)))
            actions[unit] = ["PICKUP", "WHEAT", amount]
            carriers_needed -= 1
            free.remove(unit)
    while carriers_needed > 0 and free and int(shed.get("WHEAT", 0)) > 0:
        unit = min(free, key=lambda index: (_distance(positions[index], _nearest_shed(positions[index], size)), index))
        target = _nearest_shed(positions[unit], size)
        actions[unit] = _step_toward(positions[unit], target, unit)
        free.remove(unit)
        carriers_needed -= 1

    fertilizer_targets = _fertilizer_targets(obs, farm)
    used_fertilizer = set()
    for unit in sorted(tuple(free)):
        # Pure crop workers apply fertilizer picked up in batches at the shed.
        # Animal workers retain collected units until a batched return below.
        if unit < 4 or int(inventories[unit].get("FERTILIZER", 0)) <= 0:
            continue
        choices = [pos for pos in fertilizer_targets if pos not in used_fertilizer]
        if not choices:
            continue
        target = min(choices, key=lambda pos: (_distance(positions[unit], pos), pos[1], pos[0]))
        used_fertilizer.add(target)
        actions[unit] = ["FERTILIZE"] if positions[unit] == target else _step_toward(positions[unit], target, unit)
        free.remove(unit)

    uncovered_fertilizer = max(0, len(fertilizer_targets) - len(used_fertilizer))
    if uncovered_fertilizer and int(shed.get("FERTILIZER", 0)) > 0:
        available_fertilizer = int(shed.get("FERTILIZER", 0))
        carriers_needed = int(math.ceil(uncovered_fertilizer / 4))
        for unit in sorted(tuple(free)):
            if carriers_needed <= 0 or available_fertilizer <= 0:
                break
            if unit < 4 or not _at_shed(positions[unit], size):
                continue
            amount = min(4, uncovered_fertilizer, available_fertilizer)
            actions[unit] = ["PICKUP", "FERTILIZER", amount]
            free.remove(unit)
            uncovered_fertilizer -= amount
            available_fertilizer -= amount
            carriers_needed -= 1
        # Pull the nearest crop crew members back for reserved fertilizer.  The
        # old at-shed-only rule left nearly every strawberry application
        # unserved because crop workers correctly stayed in their field zones.
        while carriers_needed > 0:
            candidates = [unit for unit in free if unit >= 4]
            if not candidates:
                break
            unit = min(
                candidates,
                key=lambda index: (
                    _distance(positions[index], _nearest_shed(positions[index], size)),
                    index,
                ),
            )
            target = _nearest_shed(positions[unit], size)
            actions[unit] = _step_toward(positions[unit], target, unit)
            free.remove(unit)
            carriers_needed -= 1

    # Return only substantial batches.  Late-day idle carriers are handled
    # below, avoiding the old bot's fourfold excess of micro-drops.
    for unit in sorted(tuple(free)):
        inventory = inventories[unit] or {}
        batch = _inventory_units(inventory)
        fertilizer_batch = int(inventory.get("FERTILIZER", 0))
        if batch >= int(POLICY["carrier_batch"]) or fertilizer_batch >= 8:
            target = _nearest_shed(positions[unit], size)
            actions[unit] = ["DROP"] if _at_shed(positions[unit], size) else _step_toward(positions[unit], target, unit)
            free.remove(unit)

    jobs = []
    for pos, tile in animals:
        if day < 29 and not tile.get("fed_today", False):
            # Only wheat carriers can execute FEED, handled above.
            pass
        if day < 29 and not tile.get("cared_today", False):
            jobs.append((2, pos, ["CARE"], "ANIMAL"))
        held = int(tile.get("yield_units", 0))
        if held >= 2 or (held > 0 and day >= 28):
            jobs.append((2, pos, ["HARVEST"], "ANIMAL"))
        if tile.get("fertilizer_available", False):
            jobs.append((2, pos, ["COLLECT_FERTILIZER"], "ANIMAL"))
    jobs.extend(_field_jobs(obs, farm, reserved))
    _assign_jobs(positions, free, jobs, size, unlocked, actions)

    # Idle workers carrying value return near the end of the day.  Earlier in
    # the day they keep servicing their local strip and accumulate a batch.
    for unit in sorted(free):
        inventory = inventories[unit] or {}
        if inventory and (hour >= 20 or not jobs):
            target = _nearest_shed(positions[unit], size)
            actions[unit] = ["DROP"] if _at_shed(positions[unit], size) else _step_toward(positions[unit], target, unit)
    return actions


def _fib_cost(start, count):
    a, b = 1, 1
    costs = []
    for _ in range(start + count):
        costs.append(a)
        a, b = b, a + b
    return sum(costs[start : start + count])


def _desired_hands(obs, farm):
    animals = len(_animal_tiles(farm))
    plants = sum(
        isinstance(tile, dict) and tile.get("kind") == "PLANT"
        for _x, _y, tile in _owned_cells(farm)
    )
    target = int(POLICY["routine_hands"])
    if animals + plants >= 64:
        target = int(POLICY["peak_hands"])
    emergencies = sum(
        bool(
            isinstance(tile, dict)
            and (
                (tile.get("kind") == "PLANT" and int(tile.get("consecutive_unwatered", 0)) >= 1)
                or (bool(tile.get("animal")) and int(tile.get("consecutive_unfed", 0)) >= 1)
            )
        )
        for _x, _y, tile in _owned_cells(farm)
    )
    if emergencies >= 5:
        target = int(POLICY["peak_hands"])
    if int(obs.get("day", 0)) >= 28:
        target = int(POLICY["peak_hands"])
    return target


def _same_turn_amounts(obs, unit_actions, animal_count):
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    amounts = {item: int(shed.get(item, 0)) for item in SELLABLE}
    inventories = private.get("inventories", []) or []
    for unit, action in enumerate(unit_actions):
        if action and action[0] == "DROP" and unit < len(inventories):
            for item in SELLABLE:
                amounts[item] += int((inventories[unit] or {}).get(item, 0))

    day = int(obs.get("day", 0))
    feed_reserve = 0 if day >= 29 else max(5, int(math.ceil(animal_count * 1.8)))
    # Field wheat is feed inventory first.  Routine buy/sell churn was a live
    # regression: it created no spread and added emergency shed travel.  Hold
    # all wheat until the final three days, then release only the true surplus.
    amounts["WHEAT"] = 0 if day < 27 else max(0, amounts["WHEAT"] - feed_reserve)
    # Keep fertilizer needed by the next recurring-crop window.
    own_farm = (obs.get("farms", []) or [])[int(obs.get("player", 0))]
    fertilizer_need = min(16, _fertilizer_reserve_need(obs, own_farm))
    amounts["FERTILIZER"] = max(0, amounts["FERTILIZER"] - fertilizer_need)

    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    shed_units = sum(int(value) for value in shed.values())
    for item in ("MELON", "STRAWBERRY", "MILK", "WOOL"):
        if day < 27 and shed_units < 75 and int(prices.get(item, 1)) <= max(5, int(BASE_PRICE[item] * 0.12)):
            amounts[item] = 0
    return amounts


def _land_wanted(obs, farm, crop_goals):
    day = int(obs.get("day", 0))
    quadrants = len(farm.get("unlocked_quadrants", []) or [])
    if quadrants >= int(POLICY["land_goal"]) or day > 14:
        return False
    animal_space = int(POLICY["animal_cap"])
    projected = animal_space + sum(int(value) for value in crop_goals.values())
    if projected <= quadrants * 25 - 3:
        return False
    money = float(farm.get("money", 0))
    cost = (1000, 2000, 4000)[min(2, quadrants - 1)]
    # The first expansion is part of the opening and should happen immediately;
    # the second waits for enough capital to preserve feed and seeds.
    reserve = 25 if quadrants == 1 else 900
    return (day >= 0 if quadrants == 1 else day >= 7) and money >= cost + reserve


def _market_actions(obs, farm, unit_actions, goals):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    animals = len(_animal_tiles(farm))

    if day == 0 and hour == 0 and not any((private.get("seeds", {}) or {}).values()) and not any(shed.get(kind, 0) for kind in ANIMALS):
        orders = [["HIRE"] for _ in range(int(POLICY["opening_hands"]))]
        for kind in ("SHEEP", "COW", "GOOSE"):
            quantity = int(POLICY["opening_animals"].get(kind, 0))
            if quantity:
                orders.append(["BUY_ANIMAL", kind, quantity])
        orders.append(["BUY_SEED", "MELON", int(POLICY["opening_melons"])])
        orders.append(["BUY_SEED", "WHEAT", int(POLICY["opening_wheat"])])
        orders.append(["BUY_PRODUCT", "WHEAT", int(POLICY["opening_feed"])])
        return orders[:10]

    amounts = _same_turn_amounts(obs, unit_actions, animals)
    sales = [item for item, quantity in amounts.items() if quantity > 0]
    sales.sort(key=lambda item: (-amounts[item] * int(prices.get(item, 1)), item))
    orders = []

    desired_hands = _desired_hands(obs, farm) if hour <= 2 else 0
    current_hires = int(farm.get("hires_today", 0))
    hire_count = max(0, desired_hands - current_hires)
    # Preserve at least one order for hiring across diverse sale days.
    sale_limit = min(len(sales), max(0, 10 - min(hire_count, 8)))
    for item in sales[:sale_limit]:
        orders.append(["SELL", item, amounts[item]])
    for _ in range(hire_count):
        if len(orders) >= 10:
            break
        orders.append(["HIRE"])

    liquid = float(farm.get("money", 0))
    liquid += sum(amounts[item] * int(prices.get(item, 1)) * 0.78 for item in sales[:sale_limit])
    liquid -= _fib_cost(current_hires, min(hire_count, max(0, 10 - sale_limit)))
    if day >= 29:
        # Oversized terminal orders also sell same-turn deposits that were not
        # visible when the observation was built.
        terminal = [["SELL", item, 9999] for item in SELLABLE]
        return terminal[:10]

    crop_goals = _crop_goals(obs, farm, animals)
    if len(orders) < 10 and _land_wanted(obs, farm, crop_goals):
        quadrants = len(farm.get("unlocked_quadrants", []) or [])
        cost = (1000, 2000, 4000)[min(2, quadrants - 1)]
        if liquid >= cost + (25 if quadrants == 1 else 900):
            orders.append(["BUY_LAND"])
            liquid -= cost

    # Hard two-day feed reserve.  Near-mature field wheat offsets only half its
    # expected output, so a missed harvest cannot expose the herd.
    total_wheat = _pending(private, "WHEAT")
    expected_wheat = 0
    for _x, _y, tile in _owned_cells(farm):
        if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "WHEAT":
            age = day - int(tile.get("planted_day", day))
            if age >= 2:
                expected_wheat += max(1, int(tile.get("yield_units", 0)))
    feed_target = max(5, int(math.ceil(animals * 2.1 - expected_wheat * 0.50)))
    buy_feed = max(0, feed_target - total_wheat)
    reserve_cash = max(150.0, animals * int(prices.get("WHEAT", 25)) * 0.75)
    if buy_feed and len(orders) < 10:
        affordable = max(0, int((liquid - 40.0) // max(1, int(prices.get("WHEAT", 25)))))
        quantity = min(buy_feed, affordable)
        if quantity > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            liquid -= quantity * int(prices.get("WHEAT", 25))

    reserved = set(_all_animal_slots(len(farm.get("tiles", []) or []) or 10))
    seeds = _seed_plan(obs, farm, reserved)
    for crop in sorted(seeds, key=lambda item: (_crop_priority(day, item), item)):
        if len(orders) >= 10:
            break
        quantity = int(seeds[crop])
        affordable = max(0, int((liquid - reserve_cash) // int(CROPS[crop]["seed"])))
        quantity = min(quantity, affordable)
        if quantity > 0:
            orders.append(["BUY_SEED", crop, quantity])
            liquid -= quantity * int(CROPS[crop]["seed"])

    owned = _owned_animals(farm, private)
    candidates = []
    # Late animals still mint fertilizer immediately and bank CARE into their
    # first production.  Replay winners compound through the final third; the
    # incumbent's 17/19 cutoffs abandoned profitable shop reactions.
    cutoffs = {"COW": 20, "SHEEP": 22, "GOOSE": 23}
    for kind in ANIMALS:
        missing = max(0, int(goals[kind]) - int(owned[kind]))
        if missing and day <= cutoffs[kind]:
            product = ANIMAL_PRODUCT[kind]
            margin = (
                OUTPUT_RATE[kind] * int(prices.get(product, BASE_PRICE[product]))
                + int(prices.get("FERTILIZER", 100))
                - int(prices.get("WHEAT", 25))
            )
            candidates.append((margin * missing, margin, kind, missing))
    if candidates and len(orders) < 10:
        _total, _margin, kind, missing = max(candidates)
        affordable = max(0, int((liquid - max(500.0, reserve_cash)) // ANIMAL_COST[kind]))
        phase_cap = (
            6 if day < 6 else 9 if day < 9 else 12 if day < 12 else int(POLICY["animal_cap"])
        )
        room = max(0, phase_cap - sum(owned.values()))
        quantity = min(2, missing, affordable, room)
        if quantity > 0:
            orders.append(["BUY_ANIMAL", kind, quantity])
    return orders[:10]


def agent_with_policy(obs, overrides=None):
    """Entry point used by focused policy probes as well as :func:`agent`."""
    if overrides:
        old = dict(POLICY)
        POLICY.update(overrides)
    try:
        farms = obs.get("farms", []) or []
        player = int(obs.get("player", 0))
        if player >= len(farms):
            return {"farmer": ["PASS"], "hands": [], "market": []}
        farm = farms[player]
        goals = _animal_goals(obs)
        units = _unit_actions(obs, farm, goals)
        return {
            "farmer": units[0] if units else ["PASS"],
            "hands": units[1:],
            "market": _market_actions(obs, farm, units, goals),
        }
    finally:
        if overrides:
            POLICY.clear()
            POLICY.update(old)


def agent(obs):
    """Kaggle entry point."""
    return agent_with_policy(obs)
