"""Configurable crop/livestock engine derived from leaderboard replays.

The core deliberately has no module-level episode state.  Every decision is
reconstructed from the observation so the same submitted module is safe in
parallel matches and either seat.
"""

from __future__ import annotations

import math
from collections import Counter

from candidates import crop as crop_policy
from candidates import livestock as livestock_policy


CROPS = crop_policy.CROPS
PRODUCTS = crop_policy.PRODUCTS
ANIMAL_PRODUCT = livestock_policy.ANIMAL_PRODUCT
ANIMAL_COST = livestock_policy.ANIMAL_COST
ANIMAL_STRUCTURE = livestock_policy.ANIMAL_STRUCTURE
ANIMALS = tuple(ANIMAL_PRODUCT)

PRODUCT_BASE = {
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

PRODUCT_PARAMS = {
    **crop_policy.MARKET,
    "EGG": {"base": 50, "I0": 10000, "T": 332, "below_func": "hinge", "below_target": .40, "above_func": "log", "above_target": .20},
    "MILK": {"base": 160, "I0": 10000, "T": 122, "below_func": "sqrt", "below_target": .60, "above_func": "linear", "above_target": 1.60},
    "WOOL": {"base": 200, "I0": 10000, "T": 105, "below_func": "log", "below_target": .20, "above_func": "sq", "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": 10000, "T": 200, "below_func": "linear", "below_target": .40, "above_func": "linear", "above_target": .40},
}

SHOP_PRODUCTS = {
    "BAKERY": {"EGG": 6, "WHEAT": 6},
    "PIZZA_SHOP": {"MILK": 6, "TOMATO": 6, "WHEAT": 6},
    "BRUNCH_SPOT": {"EGG": 6, "WHEAT": 6, "STRAWBERRY": 6},
    "YARN_STORE": {"WOOL": 12},
    "ICE_CREAM_SHOP": {"STRAWBERRY": 6, "MILK": 6, "WHEAT": 6},
    "PET_CAFE": {"CARROT": 12},
    "SMOOTHIE_SHOP": {"STRAWBERRY": 6, "MILK": 6},
    "FARMERS_MARKET": {"WHEAT": 6, "CARROT": 6, "TOMATO": 6, "STRAWBERRY": 6},
}

OUTPUT_RATE = {"GOOSE": 2.0, "COW": 1.5, "SHEEP": 4.0 / 3.0}


DEFAULT_POLICY = {
    "name": "residual_counter",
    "opening_animals": {"SHEEP": 2, "COW": 1, "GOOSE": 1},
    "opening_seeds": {"MELON": 9, "WHEAT": 5},
    "opening_feed": 5,
    "opening_hires": 4,
    "animal_mode": "residual",
    "crop_mode": "residual",
    "animal_caps": {"GOOSE": 7, "COW": 11, "SHEEP": 10},
    "total_animal_cap": 18,
    "land_goal": 3,
    "allow_fourth_land": False,
    "daily_plant_cap": 12,
    "max_hands": 12,
}


def _merged_policy(policy):
    result = dict(DEFAULT_POLICY)
    result.update(policy or {})
    for key in ("opening_animals", "opening_seeds", "animal_caps"):
        result[key] = {**DEFAULT_POLICY[key], **(policy or {}).get(key, {})}
    return result


def _owned_cells(farm):
    yield from crop_policy._owned_cells(farm)


def _animal_tiles(farm):
    return livestock_policy._animal_tiles(farm)


def _carried(private, item):
    return livestock_policy._carried(private, item)


def _pending(private, item):
    return int((private.get("shed", {}) or {}).get(item, 0)) + _carried(private, item)


def _owned_animals(farm, private):
    board = Counter(tile["animal"] for _pos, tile in _animal_tiles(farm))
    return {
        kind: board[kind] + _pending(private, kind)
        for kind in ANIMALS
    }


def _shop_counts(obs):
    return Counter((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])


def _town_rates(obs):
    rates = {item: 1.0 for item in PRODUCT_BASE if item != "FERTILIZER"}
    for shop in (obs.get("town", {}) or {}).get("unlocked_shops", []) or []:
        for item, amount in SHOP_PRODUCTS.get(shop, {}).items():
            rates[item] += amount
    return rates


def _opponent_animals(obs):
    me = int(obs.get("player", 0))
    counts = Counter()
    for player, farm in enumerate(obs.get("farms", []) or []):
        if player == me:
            continue
        counts.update(tile["animal"] for _pos, tile in _animal_tiles(farm))
    return counts


def _animal_goals(obs, policy):
    day = int(obs.get("day", 0))
    opening = {kind: int(policy["opening_animals"].get(kind, 0)) for kind in ANIMALS}
    if day < 3:
        return opening

    shops = _shop_counts(obs)
    mode = policy.get("animal_mode", "residual")
    if mode == "common":
        goals = {"GOOSE": 0, "COW": 10, "SHEEP": 4}
        if shops and next(iter(shops)) == "YARN_STORE":
            goals = {"GOOSE": 0, "COW": 6, "SHEEP": 12}
    elif mode == "arman":
        yarn = shops.get("YARN_STORE", 0)
        goals = {"GOOSE": 0, "COW": 11, "SHEEP": 4}
        if yarn == 1:
            goals = {"GOOSE": 0, "COW": 6, "SHEEP": 10}
        elif yarn >= 2:
            goals = {"GOOSE": 0, "COW": 8, "SHEEP": 14}
    elif mode == "tetsuya":
        milk_shops = sum(shops[name] for name in ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"))
        egg_shops = shops["BAKERY"] + shops["BRUNCH_SPOT"]
        goals = {
            "GOOSE": min(3, egg_shops),
            "COW": min(12, max(4, 3 + 2 * milk_shops)),
            "SHEEP": min(10, max(3, 3 + 3 * shops["YARN_STORE"])),
        }
    else:
        rates = _town_rates(obs)
        opponent = _opponent_animals(obs)
        product_kind = {"EGG": "GOOSE", "MILK": "COW", "WOOL": "SHEEP"}
        floors = {"GOOSE": opening["GOOSE"], "COW": opening["COW"], "SHEEP": opening["SHEEP"]}
        goals = {}
        for product, kind in product_kind.items():
            residual = max(
                0.0,
                rates[product] * 1.12 - opponent[kind] * OUTPUT_RATE[kind] * 0.82,
            )
            goals[kind] = max(floors[kind], int(math.ceil(residual / OUTPUT_RATE[kind])))

        # Fertilizer makes a compact base herd profitable even before the town
        # specializes.  These floors also prevent a single noisy observation
        # from creating an unserviceable all-in branch.
        goals["COW"] = max(goals["COW"], 2)
        goals["SHEEP"] = max(goals["SHEEP"], 2)
        goals["GOOSE"] = max(goals["GOOSE"], 1)

    caps = policy["animal_caps"]
    goals = {kind: min(int(caps[kind]), max(opening[kind], int(goals[kind]))) for kind in ANIMALS}
    total_cap = int(policy["total_animal_cap"])
    while sum(goals.values()) > total_cap:
        # Trim the most over-targeted product, preserving opening investments.
        choices = [kind for kind in ANIMALS if goals[kind] > opening[kind]]
        if not choices:
            break
        kind = max(choices, key=lambda value: (goals[value] - opening[value], value))
        goals[kind] -= 1
    return goals


def _preferred_slots(farm):
    tiles = farm.get("tiles", []) or []
    size = len(tiles) or 10
    half = size // 2
    shed = ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))

    def key(pos):
        x, y = pos
        distance = min(abs(x - sx) + abs(y - sy) for sx, sy in shed)
        return (distance, abs(y - (half - 0.5)), abs(x - (half - 0.5)), y, x)

    return sorted(
        ((x, y) for x, y, _tile in _owned_cells(farm)),
        key=key,
    )


def _target_assignments(farm, kinds):
    """Assign unplaced/future animals to stable, crop-free coordinates."""
    kinds = list(kinds)
    if not kinds:
        return []
    occupied = {pos for pos, _tile in _animal_tiles(farm)}
    slots = []
    for pos in _preferred_slots(farm):
        if pos in occupied:
            continue
        tile = farm["tiles"][pos[1]][pos[0]]
        if tile is None or (
            isinstance(tile, dict)
            and tile.get("kind") in ("COOP", "PASTURE", "WEED")
            and not tile.get("animal")
        ):
            slots.append(pos)

    assignments = []
    unused = set(slots)
    for kind in kinds:
        matching = []
        for pos in slots:
            if pos not in unused:
                continue
            tile = farm["tiles"][pos[1]][pos[0]]
            if isinstance(tile, dict) and tile.get("kind") == ANIMAL_STRUCTURE[kind]:
                matching.append(pos)
        candidates = matching or [pos for pos in slots if pos in unused]
        if not candidates:
            break
        pos = candidates[0]
        unused.remove(pos)
        assignments.append((pos, kind))
    return assignments


def _future_target_kinds(obs, farm, private, goals):
    owned = _owned_animals(farm, private)
    unplaced = []
    for kind in ANIMALS:
        unplaced.extend([kind] * _pending(private, kind))
    # Reserve only the next purchase wave, not every hypothetical future tile.
    purchase_room = max(0, sum(goals.values()) - sum(owned.values()))
    for kind in ("GOOSE", "COW", "SHEEP"):
        if purchase_room <= 0:
            break
        missing = max(0, goals[kind] - owned[kind])
        reserve = min(4, missing, purchase_room)
        unplaced.extend([kind] * reserve)
        purchase_room -= reserve
    return unplaced


def _active_crop_counts(farm):
    counts = Counter()
    for _x, _y, tile in _owned_cells(farm):
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            counts[tile.get("crop")] += 1
    return counts


def _plan_crop_mix(obs, farm, count, policy, animal_count):
    if count <= 0:
        return {}
    day = int(obs.get("day", 0))
    mode = policy.get("crop_mode", "residual")
    active = _active_crop_counts(farm)
    planned = Counter()

    if day == 0:
        for crop, quantity in policy["opening_seeds"].items():
            missing = max(0, int(quantity) - active[crop])
            planned[crop] = min(missing, count - sum(planned.values()))
        return {crop: n for crop, n in planned.items() if n > 0}

    # A farm-grown feed base is the principal cost advantage over the common
    # leaderboard template.  One active wheat tile produces roughly one unit
    # per day at full care, so maintain a modest service margin.
    feed_target = int(math.ceil(max(4, animal_count * 1.25)))
    wheat_need = max(0, feed_target - active["WHEAT"])
    planned["WHEAT"] += min(count, wheat_need)

    remaining = count - sum(planned.values())
    if remaining <= 0:
        return dict(planned)

    if mode in ("common", "arman", "tetsuya"):
        strawberry_target = 38 if mode != "tetsuya" else 35
        if 4 <= day <= 12:
            add = min(remaining, max(0, strawberry_target - active["STRAWBERRY"]))
            planned["STRAWBERRY"] += add
            remaining -= add
        if mode == "arman" and 10 <= day <= 14 and remaining:
            add = min(remaining, max(0, 8 - active["CARROT"]))
            planned["CARROT"] += add
            remaining -= add

    for _ in range(remaining):
        scores = crop_policy._crop_scores(obs, planned)
        if not scores:
            break
        # Do not add another melon wave into the leaders' predictable day-10
        # dump unless the live marginal calculation remains exceptional.
        if day > 9 and "MELON" in scores:
            scores["MELON"] *= 0.55
        crop, score = max(scores.items(), key=lambda item: (item[1], item[0]))
        if score <= 0:
            break
        planned[crop] += 1
    return {crop: n for crop, n in planned.items() if n > 0}


def _crop_assignments(obs, farm, empties, reserved, policy, animal_count):
    private = obs.get("private", {}) or {}
    day = int(obs.get("day", 0))
    candidates = [pos for pos in empties if pos not in reserved]
    planted_today = sum(
        1
        for _x, _y, tile in _owned_cells(farm)
        if isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and int(tile.get("planted_day", -1)) == day
    )
    cap = max(0, int(policy["daily_plant_cap"]) - planted_today)
    candidates = candidates[:cap]
    desired = _plan_crop_mix(obs, farm, len(candidates), policy, animal_count)
    pool = {crop: int(n) for crop, n in (private.get("seeds", {}) or {}).items()}
    wanted = []
    for crop in ("MELON", "STRAWBERRY", "TOMATO", "CARROT", "WHEAT"):
        wanted.extend([crop] * desired.get(crop, 0))

    assignments = {}
    for pos in candidates:
        chosen = next((crop for crop in wanted if pool.get(crop, 0) > 0), None)
        if chosen is None:
            stocked = [
                crop
                for crop, quantity in pool.items()
                if quantity > 0 and crop in CROPS and CROPS[crop]["peak"] <= 29 - day
            ]
            if stocked:
                scores = crop_policy._crop_scores(obs, {})
                chosen = max(stocked, key=lambda crop: scores.get(crop, -1e9))
        if chosen is None:
            break
        assignments[pos] = chosen
        pool[chosen] -= 1
        if chosen in wanted:
            wanted.remove(chosen)
    return assignments


def _field_jobs(obs, farm, reserved, policy, animal_count):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    jobs = []
    empties = []
    for x, y, tile in _owned_cells(farm):
        pos = (x, y)
        if tile is None:
            empties.append(pos)
            continue
        if not isinstance(tile, dict):
            continue
        if tile.get("kind") == "WEED":
            if pos not in reserved and day < 29:
                jobs.append((5, pos, ["DIG"]))
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
            if hour <= 13 and units > 0 and age >= data["first"]:
                jobs.append((0, pos, ["HARVEST"]))
            continue

        imminent = not watered and missed >= 1
        if data["ongoing"]:
            expiring = age >= data["last"]
            if units > 0 and (units >= 2 or expiring):
                jobs.append((1 if expiring else 2, pos, ["HARVEST"]))
            if imminent:
                jobs.append((0, pos, ["WATER"]))
            elif not watered and hour >= 14:
                jobs.append((3, pos, ["WATER"]))
        else:
            # One-time crops gain an extra unit for every watering in the
            # second half of their growth window.  Water the peak day before
            # harvesting or the most valuable final bonus is lost.
            bonus_start = (data["last"] + 1) // 2
            bonus_active = bonus_start <= age <= data["last"] and units < data["yield"]
            needs_water = not watered and (missed >= 1 or bonus_active)
            peak_ready = age >= data["peak"] and units >= data["yield"]
            overripe = age > data["last"]
            if needs_water:
                jobs.append((0, pos, ["WATER"]))
            elif peak_ready or overripe:
                jobs.append((1, pos, ["HARVEST"]))
            elif age >= data["peak"] and units > 0:
                jobs.append((1, pos, ["HARVEST"]))

    if day < 29 and hour <= 20:
        for pos, crop in _crop_assignments(
            obs, farm, sorted(empties, key=crop_policy._snake_key), reserved, policy, animal_count
        ).items():
            jobs.append((5, pos, ["PLANT", crop]))
    return jobs


def _nearest_assignment(positions, free, jobs):
    """Yield greedy nearest unit/job pairs in priority order."""
    jobs = list(jobs)
    while free and jobs:
        best = None
        for unit in sorted(free):
            for index, (priority, target, action) in enumerate(jobs):
                key = (
                    priority,
                    livestock_policy._distance(positions[unit], target),
                    target[1],
                    target[0],
                    action[0],
                    unit,
                    index,
                )
                if best is None or key < best[0]:
                    best = (key, unit, index, target, action)
        _key, unit, index, target, action = best
        free.remove(unit)
        jobs.pop(index)
        yield unit, target, action


def _inventory_value(inventory, prices):
    return sum(
        int(quantity) * int(prices.get(item, 1))
        for item, quantity in (inventory or {}).items()
        if item in PRODUCT_BASE and quantity > 0
    )


def _fertilizer_targets(obs, farm):
    day = int(obs.get("day", 0))
    if day >= 29:
        return []
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    fert_value = max(1, int(prices.get("FERTILIZER", 1)))
    targets = []
    for x, y, tile in _owned_cells(farm):
        if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        age = day - int(tile.get("planted_day", day))
        until = int(tile.get("fertilized_until_day", -1))
        if until >= day + 1:
            continue
        extra_units = 0
        if crop == "STRAWBERRY" and 7 <= age <= 14:
            extra_units = 2
        elif crop == "TOMATO" and 6 <= age <= 10:
            extra_units = 3
        if extra_units and extra_units * int(prices.get(crop, 1)) >= 1.20 * fert_value:
            targets.append(((x, y), crop, extra_units * int(prices.get(crop, 1))))
    return [pos for pos, _crop, _value in sorted(targets, key=lambda row: (-row[2], row[0][1], row[0][0]))]


def _unit_actions(obs, farm, policy, goals):
    private = obs.get("private", {}) or {}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    size = len(farm.get("tiles", [])) or 10
    positions = [tuple(farm.get("farmer", (0, 0))), *[tuple(pos) for pos in farm.get("hands", [])]]
    inventories = list(private.get("inventories", []) or [])
    inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
    shed = private.get("shed", {}) or {}
    actions = [["PASS"] for _ in positions]
    free = set(range(len(positions)))
    animals = _animal_tiles(farm)
    animal_count = len(animals)
    owned = _owned_animals(farm, private)

    target_kinds = _future_target_kinds(obs, farm, private, goals)
    assignments = _target_assignments(farm, target_kinds)
    reserved = {pos for pos, _kind in assignments}

    # On the terminal day, collect valuable existing output, then return early
    # enough for a same-turn DROP/SELL liquidation.
    if day >= 29 and hour >= 14:
        for unit in sorted(free):
            if inventories[unit]:
                target = livestock_policy._nearest_shed(positions[unit], size)
                actions[unit] = (
                    ["DROP"]
                    if livestock_policy._at_shed(positions[unit], size)
                    else livestock_policy._step_toward(positions[unit], target)
                )
        return actions

    # Carried animals build or enter their assigned structure before ordinary
    # service work.  Assignments are deterministic by kind and coordinate.
    used_targets = set()
    for unit in sorted(tuple(free)):
        carried = next((kind for kind in ANIMALS if inventories[unit].get(kind, 0) > 0), None)
        if carried is None:
            continue
        choices = [pos for pos, kind in assignments if kind == carried and pos not in used_targets]
        if not choices:
            continue
        target = min(choices, key=lambda pos: (livestock_policy._distance(positions[unit], pos), pos))
        used_targets.add(target)
        if positions[unit] != target:
            actions[unit] = livestock_policy._step_toward(positions[unit], target)
        else:
            tile = farm["tiles"][target[1]][target[0]]
            structure = ANIMAL_STRUCTURE[carried]
            if tile is None:
                actions[unit] = ["BUILD_COOP" if structure == "COOP" else "BUILD_PASTURE"]
            elif isinstance(tile, dict) and tile.get("kind") == structure and not tile.get("animal"):
                actions[unit] = ["PLACE", carried]
            elif isinstance(tile, dict) and not tile.get("animal"):
                actions[unit] = ["DIG"]
        free.remove(unit)

    # Pick up one waiting animal per worker for parallel placement.
    waiting = Counter({kind: int(shed.get(kind, 0)) for kind in ANIMALS})
    for unit in sorted(tuple(free)):
        if not livestock_policy._at_shed(positions[unit], size):
            continue
        kind = next(
            (
                kind
                for kind in ("SHEEP", "COW", "GOOSE")
                if waiting[kind] > 0
                and any(target_kind == kind and pos not in used_targets for pos, target_kind in assignments)
            ),
            None,
        )
        if kind is None:
            continue
        actions[unit] = ["PICKUP", kind, 1]
        waiting[kind] -= 1
        free.remove(unit)

    # Feeding and care on the terminal day cannot create another production
    # refresh.  Spend those actions collecting and returning existing value.
    unfed = [] if day >= 29 else [
        (pos, tile) for pos, tile in animals if not tile.get("fed_today", False)
    ]
    unfed_positions = {pos for pos, _tile in unfed}

    # Existing wheat carriers fan out over distinct animals.
    for unit in sorted(tuple(free)):
        if inventories[unit].get("WHEAT", 0) <= 0 or not unfed_positions:
            continue
        target = min(unfed_positions, key=lambda pos: (livestock_policy._distance(positions[unit], pos), pos))
        unfed_positions.remove(target)
        actions[unit] = ["FEED"] if positions[unit] == target else livestock_policy._step_toward(positions[unit], target)
        free.remove(unit)

    # Spawn feed carriers at the shed.  Four units per carrier balances pickup
    # overhead against long cross-field tours.
    wheat_in_hands = sum(min(4, inv.get("WHEAT", 0)) for inv in inventories)
    pickup_need = max(0, len(unfed) - wheat_in_hands)
    available_wheat = min(pickup_need, int(shed.get("WHEAT", 0)))
    scheduled_pickup_units = 0
    for unit in sorted(tuple(free)):
        if available_wheat <= 0:
            break
        if not livestock_policy._at_shed(positions[unit], size):
            continue
        share = min(4, available_wheat)
        actions[unit] = ["PICKUP", "WHEAT", share]
        available_wheat -= share
        scheduled_pickup_units += share
        free.remove(unit)

    # If an animal has already missed a feed and the currently scheduled
    # carriers cannot cover every urgent target, preserve workers for a shed
    # run before lower-value crop and care jobs consume them.
    urgent = sum(
        not tile.get("fed_today", False)
        and int(tile.get("consecutive_unfed", 0)) >= 1
        for _pos, tile in animals
    )
    uncovered_urgent = max(0, urgent - wheat_in_hands - scheduled_pickup_units)
    while uncovered_urgent > 0 and free and int(shed.get("WHEAT", 0)) > scheduled_pickup_units:
        unit = min(
            free,
            key=lambda value: (
                livestock_policy._distance(
                    positions[value], livestock_policy._nearest_shed(positions[value], size)
                ),
                value,
            ),
        )
        target = livestock_policy._nearest_shed(positions[unit], size)
        actions[unit] = (
            ["PICKUP", "WHEAT", min(4, uncovered_urgent)]
            if livestock_policy._at_shed(positions[unit], size)
            else livestock_policy._step_toward(positions[unit], target)
        )
        scheduled_pickup_units += min(4, uncovered_urgent)
        uncovered_urgent -= 4
        free.remove(unit)

    # Carried fertilizer is invested only when its expected incremental crop
    # value dominates an immediate sale.
    fertilizer_targets = _fertilizer_targets(obs, farm)
    used_fertilizer_targets = set()
    for unit in sorted(tuple(free)):
        if inventories[unit].get("FERTILIZER", 0) <= 0:
            continue
        choices = [pos for pos in fertilizer_targets if pos not in used_fertilizer_targets]
        if not choices:
            continue
        target = min(choices, key=lambda pos: (livestock_policy._distance(positions[unit], pos), pos))
        used_fertilizer_targets.add(target)
        actions[unit] = ["FERTILIZE"] if positions[unit] == target else livestock_policy._step_toward(positions[unit], target)
        free.remove(unit)

    # Return valuable output before generic work fills the schedule.  Feed and
    # crop-survival emergencies above retain precedence.
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    for unit in sorted(tuple(free)):
        inventory = inventories[unit] or {}
        carried_units = sum(int(n) for item, n in inventory.items() if item in PRODUCT_BASE)
        if carried_units and (
            hour >= 17
            or carried_units >= 10
            or _inventory_value(inventory, prices) >= 1200
        ):
            target = livestock_policy._nearest_shed(positions[unit], size)
            actions[unit] = (
                ["DROP"]
                if livestock_policy._at_shed(positions[unit], size)
                else livestock_policy._step_toward(positions[unit], target)
            )
            free.remove(unit)

    jobs = []
    for pos, tile in animals:
        if day < 29 and not tile.get("cared_today", False):
            jobs.append((1, pos, ["CARE"]))
        if tile.get("fertilizer_available", False):
            jobs.append((2, pos, ["COLLECT_FERTILIZER"]))
        held = int(tile.get("yield_units", 0))
        if held > 0:
            jobs.append((1 if held >= 3 else 2, pos, ["HARVEST"]))

    jobs.extend(_field_jobs(obs, farm, reserved, policy, animal_count))
    for unit, target, action in _nearest_assignment(positions, free, jobs):
        actions[unit] = action if positions[unit] == target else livestock_policy._step_toward(positions[unit], target)

    return actions


def _fib_cost(start, count):
    a, b = 1, 1
    costs = []
    for _ in range(start + count):
        costs.append(a)
        a, b = b, a + b
    return sum(costs[start:start + count])


def _desired_hands(obs, farm, goals, policy):
    animals = len(_animal_tiles(farm))
    plants = sum(
        isinstance(tile, dict) and tile.get("kind") == "PLANT"
        for _x, _y, tile in _owned_cells(farm)
    )
    target = 7 + math.ceil(animals / 4) + math.ceil(plants / 30)
    if any(
        isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and int(tile.get("consecutive_unwatered", 0)) >= 1
        for _x, _y, tile in _owned_cells(farm)
    ):
        target += 1
    if int(obs.get("day", 0)) >= 27:
        target = max(target, 10)
    return min(int(policy["max_hands"]), max(8, target))


def _liquidation(obs, unit_actions, animal_count):
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    day = int(obs.get("day", 0))
    amounts = {item: int(shed.get(item, 0)) for item in PRODUCT_BASE}
    inventories = private.get("inventories", []) or []
    for unit, action in enumerate(unit_actions):
        if action and action[0] == "DROP" and unit < len(inventories):
            for item in PRODUCT_BASE:
                amounts[item] += int((inventories[unit] or {}).get(item, 0))

    # No feed has value after the terminal transition.  Selling it here also
    # captures wheat dropped by a unit earlier in this same turn.
    feed_reserve = (
        0
        if day >= 29
        else max(12, int(math.ceil((animal_count + 2) * 3.0)))
    )
    amounts["WHEAT"] = max(0, amounts["WHEAT"] - feed_reserve)
    total_shed = sum(int(n) for n in shed.values())
    for item in ("MELON", "STRAWBERRY", "MILK", "WOOL"):
        if day < 27 and total_shed < 72 and int(prices.get(item, 1)) <= max(5, int(PRODUCT_BASE[item] * 0.12)):
            amounts[item] = 0
    return amounts


def _land_wanted(obs, farm, goals, policy):
    day = int(obs.get("day", 0))
    quadrants = len(farm.get("unlocked_quadrants", []))
    desired = int(policy["land_goal"])
    if policy.get("allow_fourth_land") and sum(goals.values()) >= 19:
        desired = 4
    if quadrants >= desired or day < 5 or day > 16:
        return False
    occupied = sum(
        isinstance(tile, dict)
        and (
            tile.get("kind") == "PLANT"
            or bool(tile.get("animal"))
            or tile.get("kind") in ("COOP", "PASTURE")
        )
        for _x, _y, tile in _owned_cells(farm)
    )
    capacity = 25 * quadrants
    utilization = occupied / capacity if capacity else 0.0
    thresholds = {1: (0.58, 1900), 2: (0.68, 5200), 3: (0.78, 11000)}
    required_utilization, required_money = thresholds[quadrants]
    return utilization >= required_utilization and float(farm.get("money", 0)) >= required_money


def _seed_plan(obs, farm, policy, goals, reserved):
    day = int(obs.get("day", 0))
    if day >= 28:
        return {}
    private = obs.get("private", {}) or {}
    empties = sum(
        tile is None and (x, y) not in reserved
        for x, y, tile in _owned_cells(farm)
    )
    soon = crop_policy._soon_vacancies(farm, day)
    planted_today = sum(
        1
        for _x, _y, tile in _owned_cells(farm)
        if isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and int(tile.get("planted_day", -1)) == day
    )
    count = min(
        empties + soon,
        max(0, int(policy["daily_plant_cap"]) - planted_today),
    )
    mix = _plan_crop_mix(obs, farm, count, policy, len(_animal_tiles(farm)))
    seeds = private.get("seeds", {}) or {}
    remaining_days = 29 - day
    usable_seeds = sum(
        max(0, int(quantity))
        for crop, quantity in seeds.items()
        if crop in CROPS and CROPS[crop]["peak"] <= remaining_days
    )
    buy_capacity = max(0, count - usable_seeds)
    deficits = {
        crop: max(0, quantity - int(seeds.get(crop, 0)))
        for crop, quantity in mix.items()
    }
    scores = crop_policy._crop_scores(obs, {})
    plan = {}
    for crop in sorted(deficits, key=lambda item: (-scores.get(item, -1e9), item)):
        quantity = min(deficits[crop], buy_capacity)
        if quantity > 0:
            plan[crop] = quantity
            buy_capacity -= quantity
        if buy_capacity <= 0:
            break
    return plan


def _market_actions(obs, farm, unit_actions, policy, goals):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    animal_count = len(_animal_tiles(farm))

    if day == 0 and hour == 0 and not any(private.get("seeds", {}).values()) and not any(shed.get(kind, 0) for kind in ANIMALS):
        orders = [["HIRE"] for _ in range(int(policy["opening_hires"]))]
        for kind in ("SHEEP", "COW", "GOOSE"):
            quantity = int(policy["opening_animals"].get(kind, 0))
            if quantity:
                orders.append(["BUY_ANIMAL", kind, quantity])
        for crop in ("MELON", "STRAWBERRY", "TOMATO", "CARROT", "WHEAT"):
            quantity = int(policy["opening_seeds"].get(crop, 0))
            if quantity:
                orders.append(["BUY_SEED", crop, quantity])
        if int(policy["opening_feed"]) > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", int(policy["opening_feed"])])
        while len(orders) > 10:
            try:
                orders.pop(max(index for index, order in enumerate(orders) if order[0] == "HIRE"))
            except ValueError:
                break
        return orders[:10]

    amounts = _liquidation(obs, unit_actions, animal_count)
    sales = [item for item, quantity in amounts.items() if quantity > 0]
    sales.sort(key=lambda item: (-amounts[item] * int(prices.get(item, 1)), item))
    orders = []

    desired_hands = _desired_hands(obs, farm, goals, policy) if hour <= 2 else 0
    current_hires = int(farm.get("hires_today", 0))
    hire_count = max(0, desired_hands - current_hires)
    sale_limit = max(0, 10 - hire_count)
    for item in sales[:sale_limit]:
        orders.append(["SELL", item, amounts[item]])
    for _ in range(hire_count):
        if len(orders) >= 10:
            break
        orders.append(["HIRE"])

    liquid = float(farm.get("money", 0))
    liquid += sum(amounts[item] * int(prices.get(item, 1)) * 0.78 for item in sales[:sale_limit])
    liquid -= _fib_cost(current_hires, hire_count)
    reserve = max(350.0, animal_count * int(prices.get("WHEAT", 25)) * 1.5)

    if len(orders) < 10 and _land_wanted(obs, farm, goals, policy):
        land_cost = (1000, 2000, 4000)[min(2, len(farm.get("unlocked_quadrants", [])) - 1)]
        if liquid >= reserve + land_cost:
            orders.append(["BUY_LAND"])
            liquid -= land_cost

    owned = _owned_animals(farm, private)
    cutoffs = {"COW": 17, "SHEEP": 19, "GOOSE": 20}
    candidates = []
    for kind in ANIMALS:
        missing = max(0, goals[kind] - owned[kind])
        if missing and day <= cutoffs[kind]:
            product = ANIMAL_PRODUCT[kind]
            margin = (
                OUTPUT_RATE[kind] * int(prices.get(product, PRODUCT_BASE[product]))
                + int(prices.get("FERTILIZER", 100))
                - int(prices.get("WHEAT", 25))
            )
            # Missing capacity matters as well as unit margin.  This keeps a
            # large egg/tomato-style residual niche from being delayed behind
            # a single high-base-price sheep.
            candidates.append((margin * missing, margin, kind, missing))
    if candidates and len(orders) < 10:
        _priority, _margin, kind, missing = max(candidates)
        affordable = max(0, int((liquid - reserve) // ANIMAL_COST[kind]))
        animal_room = max(0, int(policy["total_animal_cap"]) - sum(owned.values()))
        quantity = min(4, missing, affordable, animal_room)
        if quantity > 0:
            orders.append(["BUY_ANIMAL", kind, quantity])
            liquid -= quantity * ANIMAL_COST[kind]

    total_wheat = _pending(private, "WHEAT")
    feed_target = max(12, int(math.ceil((animal_count + 2) * 3.0)))
    buy_wheat = max(0, feed_target - total_wheat)
    if buy_wheat and len(orders) < 10 and day < 29:
        affordable = max(0, int((liquid - reserve * 0.35) // max(1, int(prices.get("WHEAT", 25)))))
        quantity = min(buy_wheat, affordable)
        if quantity > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            liquid -= quantity * int(prices.get("WHEAT", 25))

    reserved = {
        pos
        for pos, _kind in _target_assignments(
            farm, _future_target_kinds(obs, farm, private, goals)
        )
    }
    seed_plan = _seed_plan(obs, farm, policy, goals, reserved)
    scores = crop_policy._crop_scores(obs, {})
    for crop in sorted(seed_plan, key=lambda item: (-scores.get(item, -1e9), item)):
        if len(orders) >= 10:
            break
        quantity = int(seed_plan[crop])
        affordable = max(0, int((liquid - reserve) // CROPS[crop]["seed"]))
        quantity = min(quantity, affordable)
        if quantity > 0:
            orders.append(["BUY_SEED", crop, quantity])
            liquid -= quantity * CROPS[crop]["seed"]
    return orders[:10]


def agent_with_policy(obs, policy=None):
    policy = _merged_policy(policy)
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    if player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    goals = _animal_goals(obs, policy)
    unit_actions = _unit_actions(obs, farm, policy, goals)
    market = _market_actions(obs, farm, unit_actions, policy, goals)
    return {
        "farmer": unit_actions[0] if unit_actions else ["PASS"],
        "hands": unit_actions[1:],
        "market": market,
    }
