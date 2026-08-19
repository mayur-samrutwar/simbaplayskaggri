"""Crop-first Kaggriculture agent.

The promoted opening plants sixteen melons and nine wheat in the NW field.  It
retains most of melon's exceptional first-cycle return while denying a 25-tile
melon opponent an uncontested premium-price tail.  The rest of the season is
allocated by marginal post-glut value after projected town consumption and
visible opponent production.  The implementation is observation-driven, so it
has no state that can leak between episodes or player seats.
"""

from __future__ import annotations

import math


CROPS = {
    "WHEAT": {
        "seed": 10,
        "first": 2,
        "peak": 4,
        "last": 4,
        "yield": 4,
        "ongoing": False,
    },
    "CARROT": {
        "seed": 20,
        "first": 2,
        "peak": 3,
        "last": 3,
        "yield": 3,
        "ongoing": False,
    },
    "TOMATO": {
        "seed": 50,
        "first": 8,
        "peak": 11,
        "last": 11,
        "yield": 4,
        "ongoing": True,
    },
    "STRAWBERRY": {
        "seed": 100,
        "first": 10,
        "peak": 16,
        "last": 16,
        "yield": 4,
        "ongoing": True,
    },
    "MELON": {
        "seed": 80,
        "first": 10,
        "peak": 10,
        "last": 12,
        "yield": 6,
        "ongoing": False,
    },
}


# Defaults from kaggle-environments 1.32.7.  If an episode supplies market
# overrides, the resolved parameters are exposed in obs["market"]["params"]
# and are used instead.
MARKET = {
    "WHEAT":      {"base": 25,  "I0": 10000, "T": 400, "below_func": "sqrt",  "below_target": .80, "above_func": "log",    "above_target": .20},
    "CARROT":     {"base": 35,  "I0": 10000, "T": 450, "below_func": "hinge", "below_target": 1.0, "above_func": "sqrt",  "above_target": .70},
    "TOMATO":     {"base": 60,  "I0": 10000, "T": 200, "below_func": "hinge", "below_target": .40, "above_func": "sqrt",  "above_target": .60},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "below_func": "sqrt",  "below_target": .70, "above_func": "linear", "above_target": 1.6},
    "MELON":      {"base": 250, "I0": 10000, "T": 300, "below_func": "log",   "below_target": .20, "above_func": "sq",     "above_target": 3.6},
}


SHOP_DEMAND = {
    "BAKERY": {"WHEAT": 6},
    "PIZZA_SHOP": {"WHEAT": 6, "TOMATO": 6},
    "BRUNCH_SPOT": {"WHEAT": 6, "STRAWBERRY": 6},
    "ICE_CREAM_SHOP": {"WHEAT": 6, "STRAWBERRY": 6},
    "PET_CAFE": {"CARROT": 12},
    "SMOOTHIE_SHOP": {"STRAWBERRY": 6},
    "FARMERS_MARKET": {
        "WHEAT": 6,
        "CARROT": 6,
        "TOMATO": 6,
        "STRAWBERRY": 6,
    },
}


PRODUCTS = (
    "MELON",
    "STRAWBERRY",
    "TOMATO",
    "CARROT",
    "WHEAT",
    "EGG",
    "MILK",
    "WOOL",
    "FERTILIZER",
)


def _shape(name, x, throughput):
    x = max(0.0, float(x))
    if name == "linear":
        return x
    if name == "sq":
        return x * x
    if name == "sqrt":
        return math.sqrt(x)
    if name == "log":
        return math.log1p(x)
    if name == "log10":
        return math.log10(1.0 + x)
    if name == "hinge":
        u = x / throughput if throughput > 0 else x
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def _price(item, inventory, params):
    p = params[item]
    base = float(p["base"])
    anchor = float(p["I0"])
    throughput = float(p["T"])
    if inventory < anchor:
        func = p["below_func"]
        target = float(p["below_target"])
        sign = 1.0
        distance = anchor - inventory
    else:
        func = p["above_func"]
        target = float(p["above_target"])
        sign = -1.0
        distance = inventory - anchor
    denominator = _shape(func, throughput, throughput)
    amplitude = target * base / denominator if denominator else 0.0
    return max(1, int(round(base + sign * amplitude * _shape(func, distance, throughput))))


def _average_sale(item, inventory, units, params):
    """Expected receipts for a small marginal batch.

    Floor-price sales do not add inventory in the real environment.  Treating
    them as though they did is harmless because the price remains floored.
    """
    return sum(_price(item, inventory + i, params) for i in range(max(0, units)))


def _town_rates(obs):
    rates = {crop: 1.0 for crop in CROPS}  # town centre: one of each per day
    town = obs.get("town", {}) or {}
    for shop in town.get("unlocked_shops", []) or []:
        for crop, amount in SHOP_DEMAND.get(shop, {}).items():
            rates[crop] += amount
    return rates


def _tile_age(tile, day):
    return day - int(tile.get("planted_day", day))


def _visible_supply(obs, crop, horizon):
    """Production likely to hit the market before ``horizon`` days elapse."""
    day = int(obs.get("day", 0))
    supply = 0.0
    farms = obs.get("farms", []) or []
    me = int(obs.get("player", 0))
    for player, farm in enumerate(farms):
        # Opponent production is a little less certain: it may harvest early or
        # fail to water.  The discount keeps awareness from becoming paralysis.
        confidence = 1.0 if player == me else 0.82
        for row in farm.get("tiles", []):
            for tile in row:
                if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
                    continue
                if tile.get("crop") != crop:
                    continue
                data = CROPS[crop]
                age = _tile_age(tile, day)
                if data["ongoing"]:
                    first_in = max(0, data["first"] - age)
                    if first_in <= horizon:
                        # Scheduled output up to the candidate crop's sale date.
                        if crop == "TOMATO":
                            produced = min(4, horizon - first_in + 1)
                        else:
                            produced = min(4, (horizon - first_in) // 2 + 1)
                        supply += confidence * max(0, produced)
                elif age + horizon >= data["peak"]:
                    supply += confidence * max(data["yield"], int(tile.get("yield_units", 0)))
    return supply


def _pending_private(private, crop):
    total = int((private.get("shed", {}) or {}).get(crop, 0))
    for inventory in private.get("inventories", []) or []:
        total += int((inventory or {}).get(crop, 0))
    return total


def _crop_scores(obs, planned):
    """Marginal profit/day for adding one more tile of each crop."""
    day = int(obs.get("day", 0))
    remaining = 29 - day
    market = obs.get("market", {}) or {}
    inventories = market.get("inventory", {}) or {}
    params = market.get("params") or MARKET
    private = obs.get("private", {}) or {}
    rates = _town_rates(obs)
    scores = {}

    for crop, data in CROPS.items():
        delay = data["peak"]
        if delay > remaining:
            continue
        projected = float(inventories.get(crop, MARKET[crop]["I0"]))
        projected -= rates[crop] * delay
        projected += _visible_supply(obs, crop, delay)
        projected += _pending_private(private, crop)
        projected += planned.get(crop, 0) * data["yield"]
        receipts = _average_sale(crop, projected, data["yield"], params)
        net = receipts - data["seed"]
        # Ongoing plants require fewer harvest/replant actions but lock the tile
        # for longer.  A small setup discount reflects their delayed cashflow.
        if data["ongoing"]:
            net *= 0.96
        scores[crop] = net / max(1, delay)
    return scores


def _plan_crops(obs, count):
    """Greedily allocate slots by marginal value, including self-induced glut."""
    if count <= 0:
        return {}
    day = int(obs.get("day", 0))
    market_inv = (obs.get("market", {}) or {}).get("inventory", {}) or {}

    # A bounded paired-seat sweep promoted 16 melons + 9 wheat over the
    # monoculture: it preserved baseline wins while consistently beating a
    # 25-melon mirror whose unmatched tail collapses the premium curve.
    if day <= 3 and float(market_inv.get("MELON", 10000)) < 10040:
        melons = min(16, count)
        plan = {"MELON": melons}
        if count > melons:
            plan["WHEAT"] = count - melons
        return plan

    planned = {crop: 0 for crop in CROPS}
    for _ in range(count):
        scores = _crop_scores(obs, planned)
        if not scores:
            break
        # Stable tie order favours quick, resilient crops.
        order = {"CARROT": 0, "WHEAT": 1, "TOMATO": 2, "STRAWBERRY": 3, "MELON": 4}
        crop, score = max(scores.items(), key=lambda kv: (kv[1], -order[kv[0]]))
        # Planting for a non-positive expected return only creates chores.
        if score <= 0:
            break
        planned[crop] += 1
    return {crop: n for crop, n in planned.items() if n > 0}


def _owned_cells(farm):
    for y, row in enumerate(farm.get("tiles", [])):
        for x, tile in enumerate(row):
            if tile != "LOCKED":
                yield x, y, tile


def _soon_vacancies(farm, day):
    count = 0
    for _x, _y, tile in _owned_cells(farm):
        if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        data = CROPS.get(crop)
        if not data:
            continue
        age = _tile_age(tile, day)
        if data["ongoing"]:
            if age >= data["last"]:
                count += 1
        elif age >= data["peak"]:
            count += 1
    return count


def _desired_hands(farm):
    owned = sum(1 for _ in _owned_cells(farm))
    # Seven opening hands was the best bounded-search service level.  Larger
    # farms scale to the per-turn market cap of ten hires.
    if owned <= 25:
        return 7
    if owned <= 50:
        return 8
    return 10


def _hire_cost(start, count):
    a, b = 1, 1
    sequence = []
    for _ in range(start + count):
        sequence.append(a)
        a, b = b, a + b
    return sum(sequence[start:start + count])


def _inventory_products(inventory):
    return sum(int(inventory.get(item, 0)) for item in PRODUCTS if item != "FERTILIZER")


def _snake_key(pos):
    x, y = pos
    # Begin near the shed, alternate row directions, and stay deterministic.
    return (-y, -x if y % 2 == 0 else x)


def _plant_choices(obs, empties):
    """Map empty coordinates to already-owned seeds without over-requesting."""
    private = obs.get("private", {}) or {}
    pool = {crop: int(n) for crop, n in (private.get("seeds", {}) or {}).items()}
    desired = _plan_crops(obs, len(empties))
    wanted = []
    for crop in ("MELON", "STRAWBERRY", "TOMATO", "CARROT", "WHEAT"):
        wanted.extend([crop] * desired.get(crop, 0))

    assignments = {}
    cursor = 0
    for pos in sorted(empties, key=_snake_key):
        chosen = None
        while cursor < len(wanted):
            candidate = wanted[cursor]
            cursor += 1
            if pool.get(candidate, 0) > 0:
                chosen = candidate
                break
        if chosen is None:
            # Sunk seeds should be used before buying still more; choose the
            # currently most valuable stocked crop, but never create a plant
            # that cannot reach its planned harvest age before day 29.
            remaining_days = 29 - int(obs.get("day", 0))
            stocked = [
                crop
                for crop, n in pool.items()
                if n > 0 and crop in CROPS and CROPS[crop]["peak"] <= remaining_days
            ]
            if stocked:
                scores = _crop_scores(obs, {})
                chosen = max(stocked, key=lambda crop: (scores.get(crop, -1e9), crop))
        if chosen is None:
            break
        assignments[pos] = chosen
        pool[chosen] -= 1
    return assignments


def _field_tasks(obs, farm):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    final_day = day >= 29
    tasks = []
    empties = []

    for x, y, tile in _owned_cells(farm):
        if tile is None:
            empties.append((x, y))
            continue
        if not isinstance(tile, dict):
            continue
        kind = tile.get("kind")
        if kind == "WEED":
            if not final_day:
                tasks.append((3, x, y, ["DIG"]))
            continue
        if kind != "PLANT":
            continue

        crop = tile.get("crop")
        data = CROPS.get(crop)
        if not data:
            continue
        age = _tile_age(tile, day)
        units = int(tile.get("yield_units", 0))
        watered = bool(tile.get("watered_today", False))
        consecutive = int(tile.get("consecutive_unwatered", 0))

        if final_day:
            # A harvest on hour 13 can still leave the farthest NW/SW tile,
            # traverse eight steps, and DROP on the final hour 22.  From hour
            # 14 onward, returning carried value is the only safe field work.
            if hour <= 13 and units > 0 and age >= data["first"]:
                tasks.append((0, x, y, ["HARVEST"]))
            continue

        if data["ongoing"]:
            # Survival gets precedence late in the day.  Otherwise collect in
            # two-unit batches to halve traversal and harvest actions.
            needs_water = not watered and consecutive >= 1
            last_production = age >= data["last"]
            if needs_water and (hour >= 18 or units < 2):
                tasks.append((0, x, y, ["WATER"]))
            elif units >= 2 or (units > 0 and last_production):
                tasks.append((1, x, y, ["HARVEST"]))
            elif needs_water:
                tasks.append((0, x, y, ["WATER"]))
            continue

        bonus_start = (data["last"] + 1) // 2
        bonus_active = bonus_start <= age <= data["last"] and units < data["yield"]
        needs_water = not watered and (consecutive >= 1 or bonus_active)
        peak_ready = age >= data["peak"] and units >= data["yield"]
        overripe = age > data["last"]

        if needs_water:
            tasks.append((0, x, y, ["WATER"]))
        elif peak_ready or (age >= data["first"] and units >= 6) or overripe:
            tasks.append((1, x, y, ["HARVEST"]))
        elif age >= data["peak"] and units > 0:
            # Handles a missed bonus day without waiting into decay.
            tasks.append((1, x, y, ["HARVEST"]))

    # Newly planted crops begin with one missed watering day.  This scheduler
    # observes the new tile only next turn, so stop planting after hour 20 and
    # leave three turns of margin to perform the mandatory first watering.
    if not final_day and hour <= 20:
        for (x, y), crop in _plant_choices(obs, empties).items():
            tasks.append((4, x, y, ["PLANT", crop]))
    return tasks


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _move_toward(source, target, unit_index):
    x, y = source
    tx, ty = target
    # Alternating axis preference prevents a convoy of co-located hands from
    # taking exactly the same route while retaining deterministic behaviour.
    x_first = unit_index % 2 == 0
    if x_first and x != tx:
        return ["EAST" if tx > x else "WEST"]
    if y != ty:
        return ["SOUTH" if ty > y else "NORTH"]
    if x != tx:
        return ["EAST" if tx > x else "WEST"]
    return ["PASS"]


def _assign_group(units, available, group):
    """Greedy nearest-pair matching for one task-priority band."""
    group = list(group)
    while available and group:
        best = None
        for unit_index in sorted(available):
            position = units[unit_index]
            for task_index, task in enumerate(group):
                _priority, x, y, action = task
                candidate = (
                    _distance(position, (x, y)),
                    y,
                    x,
                    action[0],
                    unit_index,
                    task_index,
                )
                if best is None or candidate < best[0]:
                    best = (candidate, unit_index, task_index, task)
        _key, unit_index, task_index, task = best
        available.remove(unit_index)
        group.pop(task_index)
        yield unit_index, task


def _unit_actions(obs, farm):
    positions = [tuple(farm.get("farmer", (0, 0)))] + [tuple(p) for p in farm.get("hands", [])]
    private = obs.get("private", {}) or {}
    inventories = list(private.get("inventories", []) or [])
    inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
    tasks = _field_tasks(obs, farm)
    actions = [["PASS"] for _ in positions]
    available = set(range(len(positions)))
    day = int(obs.get("day", 0))

    # A worker carries at most two full melon harvests before banking them.  If
    # seven workers return together this remains below the 100-item shed cap.
    harvest_exists = any(task[3][0] == "HARVEST" for task in tasks)
    board_size = len(farm.get("tiles", [])) or 10
    half = board_size // 2
    shed_tiles = ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))

    returning = set()
    for index, inventory in enumerate(inventories[:len(positions)]):
        carried = _inventory_products(inventory or {})
        if carried and (day >= 29 or carried >= 12 or not harvest_exists):
            returning.add(index)

    # Do not sacrifice a plant that would weed tonight just to make a deposit.
    emergency = [task for task in tasks if task[0] == 0]
    for index in sorted(returning):
        if index not in available:
            continue
        if emergency and len(available) <= len(emergency):
            break
        position = positions[index]
        target = min(shed_tiles, key=lambda p: (_distance(position, p), p[1], p[0]))
        actions[index] = ["DROP"] if position in shed_tiles else _move_toward(position, target, index)
        available.remove(index)

    # Match critical care/harvest/dig before planting.
    for priority in (0, 1, 2, 3, 4):
        group = [task for task in tasks if task[0] == priority]
        for index, task in _assign_group(positions, available, group):
            _priority, x, y, op = task
            actions[index] = op if positions[index] == (x, y) else _move_toward(positions[index], (x, y), index)

    # Idle carriers should head home even when they have not reached the batch
    # threshold.  This makes same-day liquidation common without fragmenting a
    # harvest sweep.
    for index in sorted(available):
        inventory = inventories[index] or {}
        if _inventory_products(inventory):
            position = positions[index]
            target = min(shed_tiles, key=lambda p: (_distance(position, p), p[1], p[0]))
            actions[index] = ["DROP"] if position in shed_tiles else _move_toward(position, target, index)

    return actions


def _liquidation_quantities(obs, unit_actions):
    private = obs.get("private", {}) or {}
    amounts = {item: int((private.get("shed", {}) or {}).get(item, 0)) for item in PRODUCTS}
    inventories = private.get("inventories", []) or []
    for index, action in enumerate(unit_actions):
        if action and action[0] == "DROP" and index < len(inventories):
            for item in PRODUCTS:
                amounts[item] += int((inventories[index] or {}).get(item, 0))
    return amounts


def _effective_wealth(obs):
    player = int(obs.get("player", 0))
    farms = obs.get("farms", []) or []
    if player >= len(farms):
        return 0.0
    wealth = float(farms[player].get("money", 0))
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    private = obs.get("private", {}) or {}
    for item in PRODUCTS:
        quantity = _pending_private(private, item)
        wealth += quantity * float(prices.get(item, 0)) * 0.65
    return wealth


def _want_land(obs, farm):
    day = int(obs.get("day", 0))
    extra = max(0, len(farm.get("unlocked_quadrants", [])) - 1)
    if day < 8 or day > 19 or extra >= 3:
        return False
    costs = (1000, 2000, 4000)
    thresholds = (2500, 8000, 15000)
    return _effective_wealth(obs) >= costs[extra] + thresholds[extra]


def _market_actions(obs, farm, unit_actions):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}
    market = obs.get("market", {}) or {}
    prices = market.get("prices", {}) or {}
    orders = []

    amounts = _liquidation_quantities(obs, unit_actions)
    sale_candidates = [item for item, n in amounts.items() if n > 0]
    sale_candidates.sort(key=lambda item: (-int(prices.get(item, 0)) * amounts[item], item))

    # Hour zero is the only hiring opportunity we use.  Reserve enough order
    # slots for all cheap hands and liquidate the most valuable batch first.
    desired_hires = _desired_hands(farm) if hour == 0 else 0
    current_hires = int(farm.get("hires_today", 0))
    hire_count = max(0, desired_hires - current_hires)
    max_sales = max(0, 10 - hire_count)
    for item in sale_candidates[:max_sales]:
        orders.append(["SELL", item, amounts[item]])

    for _ in range(hire_count):
        if len(orders) >= 10:
            break
        orders.append(["HIRE"])

    # Expansion and seed shopping can happen after a harvest-funded sell in the
    # same market queue.  On hour zero, defer them if hiring filled the queue.
    if len(orders) < 10 and _want_land(obs, farm):
        orders.append(["BUY_LAND"])

    owned = list(_owned_cells(farm))
    empties = sum(tile is None or (isinstance(tile, dict) and tile.get("kind") == "WEED") for _x, _y, tile in owned)
    need = empties + _soon_vacancies(farm, day)
    if day >= 29:
        need = 0
    desired = _plan_crops(obs, need)
    seeds = private.get("seeds", {}) or {}
    # A valuation change between turns can alter the desired mix.  Existing
    # seeds are sunk, universally plantable inventory, so let them fill total
    # capacity before buying replacements of the newly preferred variety.
    buy_capacity = max(0, need - sum(max(0, int(n)) for n in seeds.values()))

    # Estimate cash conservatively.  Orders are still safe if the estimate is
    # wrong: market buys stop atomically when funds run out.
    cash = float(farm.get("money", 0))
    cash += sum(amounts[item] * float(prices.get(item, 0)) * 0.55 for item in sale_candidates[:max_sales])
    cash -= _hire_cost(current_hires, hire_count)
    if any(order[0] == "BUY_LAND" for order in orders):
        extra = max(0, len(farm.get("unlocked_quadrants", [])) - 1)
        cash -= (1000, 2000, 4000)[min(extra, 2)]
    reserve = 150.0

    scores = _crop_scores(obs, {})
    crop_order = sorted(desired, key=lambda crop: (-scores.get(crop, -1e9), crop))
    for crop in crop_order:
        if len(orders) >= 10 or buy_capacity <= 0:
            break
        quantity = max(0, desired[crop] - int(seeds.get(crop, 0)))
        affordable = max(0, int((cash - reserve) // CROPS[crop]["seed"]))
        quantity = min(quantity, affordable, buy_capacity)
        if quantity <= 0:
            continue
        orders.append(["BUY_SEED", crop, quantity])
        cash -= quantity * CROPS[crop]["seed"]
        buy_capacity -= quantity
    return orders[:10]


def agent(obs):
    """Kaggle entry point."""
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    if player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    unit_actions = _unit_actions(obs, farm)
    market_orders = _market_actions(obs, farm, unit_actions)
    return {
        "farmer": unit_actions[0] if unit_actions else ["PASS"],
        "hands": unit_actions[1:],
        "market": market_orders,
    }
