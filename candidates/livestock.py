"""Deterministic goose-first Kaggriculture agent.

The policy deliberately concentrates on the unusually strong goose loop:

* geese create a fertilizer unit every day, so they repay their purchase price
  before their first egg in an ordinary market;
* daily care turns steady-state egg production from one into two units; and
* cheap, daily-reset farm hands make the four animal actions affordable.

The implementation is observation-driven and keeps no cross-turn state.  That
makes it safe when the same submitted module is reused for several episodes.
"""

from __future__ import annotations

import math


ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_STRUCTURE = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
SALE_ITEMS = (
    "FERTILIZER",
    "EGG",
    "MILK",
    "WOOL",
    "WHEAT",
    "CARROT",
    "TOMATO",
    "STRAWBERRY",
    "MELON",
)
ROUTINE_SALE_ITEMS = tuple(item for item in SALE_ITEMS if item != "WHEAT")


def _owned(tile):
    return tile != "LOCKED"


def _shed_tiles(size):
    half = size // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _at_shed(pos, size):
    return tuple(pos) in _shed_tiles(size)


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(start, target):
    """One deterministic Manhattan step; horizontal first avoids oscillation."""
    x, y = start
    tx, ty = target
    if x < tx:
        return ["EAST"]
    if x > tx:
        return ["WEST"]
    if y < ty:
        return ["SOUTH"]
    if y > ty:
        return ["NORTH"]
    return ["PASS"]


def _nearest_shed(pos, size):
    return min(_shed_tiles(size), key=lambda p: (_distance(pos, p), p[1], p[0]))


def _slot_order(size, unlocked):
    """Compact snakes starting at each quadrant's shed-facing corner."""
    half = size // 2
    answer = []

    def add_quadrant(xs, ys):
        for row_number, y in enumerate(ys):
            row = list(xs)
            if row_number % 2:
                row.reverse()
            answer.extend((x, y) for x in row)

    if "NW" in unlocked:
        add_quadrant(range(half - 1, -1, -1), range(half - 1, -1, -1))
    if "NE" in unlocked:
        add_quadrant(range(half, size), range(half - 1, -1, -1))
    if "SW" in unlocked:
        add_quadrant(range(half - 1, -1, -1), range(half, size))
    if "SE" in unlocked:
        add_quadrant(range(half, size), range(half, size))
    return answer


def _market_units(n):
    """Normalize an intended positive market quantity."""
    return max(1, int(n))


def _fib_hire_bill(existing, additional):
    a, b = 1, 1
    costs = []
    for _ in range(existing + additional):
        costs.append(a)
        a, b = b, a + b
    return sum(costs[existing : existing + additional])


def _animal_tiles(farm):
    result = []
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal"):
                result.append(((x, y), tile))
    return result


def _carried(private, item):
    return sum(inv.get(item, 0) for inv in private.get("inventories", []))


def _market_plan(obs, farm, private, animal_count, owned_animals, animal_goals):
    """Sell promptly, hire early, then compound into feed and more geese."""
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    shed = private.get("shed", {})
    prices = obs.get("market", {}).get("prices", {})
    money = float(farm.get("money", 0))
    orders = []

    # A deliberately oversized sale also liquidates anything dropped by a unit
    # earlier in this same turn (unit actions precede market processing).
    sale_items = SALE_ITEMS if day >= 29 else ROUTINE_SALE_ITEMS
    for item in sale_items:
        if shed.get(item, 0) > 0 or (day >= 29 and hour >= 14):
            orders.append(["SELL", item, 9999])

    # Value stock that is about to be sold.  The discount leaves room for price
    # movement while a multi-unit sale is processed.
    liquid = money
    for item in sale_items:
        n = shed.get(item, 0)
        if n:
            liquid += n * max(1, prices.get(item, 1)) * 0.90

    # Eleven hands is enough to service a full 5x5 goose field.  Early days use
    # fewer while the flock is small.  Hiring is confined to the first hours so
    # every hand has time to repay its Fibonacci cost.
    desired_hands = min(11, 7 + animal_count // 5)
    if day == 0:
        desired_hands = max(desired_hands, 8)
    hire_room = max(0, desired_hands - len(farm.get("hands", []))) if hour <= 2 else 0

    # Preserve two market slots for feed and geese.  Positive shed products are
    # already represented by sale orders and normally number only one or two.
    max_hires_now = max(0, 8 - len(orders))
    hires_now = min(hire_room, max_hires_now)
    for _ in range(hires_now):
        orders.append(["HIRE"])
    liquid -= _fib_hire_bill(int(farm.get("hires_today", 0)), hires_now)

    # Nothing bought on the final day can improve the terminal bank balance.
    if day >= 29:
        return orders[:10]

    remaining_days = 30 - day
    egg_price = max(1, prices.get("EGG", 50))
    fert_price = max(1, prices.get("FERTILIZER", 100))
    wheat_price = max(1, prices.get("WHEAT", 25))

    # Buy at most eight initially and four thereafter.  Smoothing purchases
    # avoids filling the shed and gives carriers time to place each bird.
    missing_geese = max(0, animal_goals["GOOSE"] - owned_animals["GOOSE"])
    buy_kind = None
    buy_count = 0
    if day <= 18 and remaining_days >= 11 and hour <= 8:
        reserve = max(180.0, (animal_count + 4) * wheat_price * 0.65)
        # Geese establish the fertilizer cash engine first.  Once ten are owned,
        # add a small sheep/cow sleeve to avoid saturating the egg market.  Town
        # demand can raise those goals later in the season.
        priorities = ["GOOSE"]
        if owned_animals["GOOSE"] >= 10:
            priorities = ["SHEEP", "COW", "GOOSE"]
        margins = {
            "GOOSE": 2.0 * egg_price + fert_price - wheat_price,
            "COW": 1.5 * max(1, prices.get("MILK", 160)) + fert_price - wheat_price,
            "SHEEP": (4.0 / 3.0) * max(1, prices.get("WOOL", 200)) + fert_price - wheat_price,
        }
        for kind in priorities:
            missing = max(0, animal_goals[kind] - owned_animals[kind])
            cost = ANIMAL_COST[kind]
            affordable = max(0, int((liquid - reserve) // cost))
            cap = 8 if day == 0 and kind == "GOOSE" else (3 if kind == "GOOSE" else 2)
            if missing and affordable and (margins[kind] >= 25 or day <= 8):
                buy_kind = kind
                buy_count = min(missing, affordable, cap)
                break

    if buy_kind and buy_count and len(orders) < 10:
        orders.append(["BUY_ANIMAL", buy_kind, _market_units(buy_count)])
        liquid -= ANIMAL_COST[buy_kind] * buy_count

    # Keep roughly a day and a half of feed, with a small opening buffer.  Feed
    # is bought after geese so an ambitious purchase cannot consume its capital.
    field_wheat = _carried(private, "WHEAT")
    target_wheat = max(12, int(math.ceil((animal_count + buy_count) * 1.55)))
    current_wheat = shed.get("WHEAT", 0) + field_wheat
    wanted = max(0, target_wheat - current_wheat)
    affordable_wheat = max(0, int(max(0.0, liquid - 30.0) // wheat_price))
    buy_wheat = min(wanted, affordable_wheat)
    if buy_wheat and len(orders) < 10:
        orders.append(["BUY_PRODUCT", "WHEAT", _market_units(buy_wheat)])

    # Final actions have no end-of-day inventory transfer; keep every remaining
    # market slot available for the oversized sale orders above.
    return orders[:10]


def agent(obs):
    farms = obs.get("farms", [])
    player = int(obs.get("player", 0))
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    private = obs.get("private", {}) or {}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    size = len(farm.get("tiles", [])) or 10
    positions = [tuple(farm["farmer"])] + [tuple(p) for p in farm.get("hands", [])]
    inventories = list(private.get("inventories", []))
    while len(inventories) < len(positions):
        inventories.append({})

    actions = [["PASS"] for _ in positions]
    free = set(range(len(positions)))
    animals = _animal_tiles(farm)
    animal_count = len(animals)
    shed = private.get("shed", {})
    owned_animals = {}
    for kind in ANIMAL_PRODUCT:
        on_board = sum(tile.get("animal") == kind for _, tile in animals)
        owned_animals[kind] = on_board + shed.get(kind, 0) + _carried(private, kind)

    # Four premium animals diversify the flock without flooding the steep milk
    # and wool curves.  Fourteen geese was the best stable fertilizer/egg scale
    # in local sweeps; larger monocultures lose money to feed scarcity.
    animal_goals = {"GOOSE": 14, "COW": 2, "SHEEP": 2}

    slots = _slot_order(size, set(farm.get("unlocked_quadrants", ["NW"])))[:25]
    slot_plan = []
    cursor = 0
    for kind in ("GOOSE", "SHEEP", "COW"):
        for _ in range(animal_goals[kind]):
            if cursor < len(slots):
                slot_plan.append((slots[cursor], kind))
                cursor += 1
    planned_slots = [pos for pos, _ in slot_plan]
    planned_kind = {pos: kind for pos, kind in slot_plan}
    occupied_slots = {pos for pos, _ in animals}

    market = _market_plan(obs, farm, private, animal_count, owned_animals, animal_goals)

    # Day 29 has no end-of-day refresh.  Use its first fourteen hours solely to
    # collect already-created products/fertilizer, then give even the farthest
    # NW tile eight moves plus one DROP before the final actionable hour (22).
    if day >= 29:
        if hour >= 14:
            for idx in sorted(free):
                if inventories[idx]:
                    target = _nearest_shed(positions[idx], size)
                    actions[idx] = ["DROP"] if positions[idx] == target else _step_toward(positions[idx], target)
                else:
                    actions[idx] = ["PASS"]
        else:
            final_jobs = []
            prices = obs.get("market", {}).get("prices", {})
            for pos, tile in animals:
                if tile.get("yield_units", 0) > 0:
                    product = ANIMAL_PRODUCT[tile["animal"]]
                    value = int(tile.get("yield_units", 0)) * prices.get(product, 1)
                    final_jobs.append((-value, pos, ["HARVEST"]))
                if tile.get("fertilizer_available", False):
                    final_jobs.append((-prices.get("FERTILIZER", 1), pos, ["COLLECT_FERTILIZER"]))
            while free and final_jobs:
                best = None
                for idx in free:
                    for j, (neg_value, target, op) in enumerate(final_jobs):
                        score = (neg_value, _distance(positions[idx], target), target[1], target[0], idx, j)
                        if best is None or score < best[0]:
                            best = (score, idx, j, target, op)
                _, idx, job_index, target, op = best
                actions[idx] = op if positions[idx] == target else _step_toward(positions[idx], target)
                free.remove(idx)
                final_jobs.pop(job_index)
        return {"farmer": actions[0], "hands": actions[1:], "market": market}

    # Feed stock is spread over a few workers.  Reserving the observed shed
    # amount prevents simultaneous PICKUP commands from silently starving later
    # workers in interpreter order.
    unfed = [(pos, tile) for pos, tile in animals if not tile.get("fed_today", False)]
    wheat_in_field = _carried(private, "WHEAT")
    # A distant worker cannot realistically visit the whole field in one day.
    # Count at most four carried units per worker when deciding whether to make
    # additional feed carriers at the shed.
    serviceable_wheat = sum(min(4, inv.get("WHEAT", 0)) for inv in inventories)
    pickup_need = max(0, len(unfed) - serviceable_wheat)
    available_wheat = min(pickup_need, shed.get("WHEAT", 0))
    center_workers = [
        i for i in sorted(free)
        if _at_shed(positions[i], size)
        and not any(inventories[i].get(kind, 0) for kind in ANIMAL_PRODUCT)
    ]
    if available_wheat and center_workers:
        desired_pickers = min(len(center_workers), max(1, math.ceil(available_wheat / 5)))
        left = available_wheat
        for ordinal, idx in enumerate(center_workers[:desired_pickers]):
            share = min(5, math.ceil(left / (desired_pickers - ordinal)))
            actions[idx] = ["PICKUP", "WHEAT", share]
            left -= share
            free.discard(idx)

    # Animal carriers prepare their own tile if necessary, then place the animal.
    delivery_targets = [p for p in planned_slots if p not in occupied_slots]
    reserved_delivery = set()
    for idx in sorted(tuple(free)):
        carried_kind = next((kind for kind in ANIMAL_PRODUCT if inventories[idx].get(kind, 0) > 0), None)
        if carried_kind is None:
            continue
        choices = [
            p for p in delivery_targets
            if p not in reserved_delivery and planned_kind.get(p) == carried_kind
        ]
        if not choices:
            continue
        target = min(choices, key=lambda p: (_distance(positions[idx], p), planned_slots.index(p)))
        reserved_delivery.add(target)
        if positions[idx] != target:
            actions[idx] = _step_toward(positions[idx], target)
        else:
            tile = farm["tiles"][target[1]][target[0]]
            structure = ANIMAL_STRUCTURE[carried_kind]
            if tile is None:
                actions[idx] = ["BUILD_COOP" if structure == "COOP" else "BUILD_PASTURE"]
            elif isinstance(tile, dict) and tile.get("kind") == structure and "animal" not in tile:
                actions[idx] = ["PLACE", carried_kind]
            elif isinstance(tile, dict) and "animal" not in tile:
                actions[idx] = ["DIG"]
            else:
                actions[idx] = ["PASS"]
        free.discard(idx)

    # Pick up waiting animals only after reserving feed carriers.  One per
    # worker gives placement much better parallelism than a bulk pickup.
    waiting_animals = {kind: shed.get(kind, 0) for kind in ANIMAL_PRODUCT}
    for idx in sorted(tuple(free)):
        if not _at_shed(positions[idx], size):
            continue
        kind = next(
            (
                kind for kind in ("SHEEP", "COW", "GOOSE")
                if waiting_animals[kind] > 0
                and any(planned_kind.get(p) == kind and p not in reserved_delivery for p in delivery_targets)
            ),
            None,
        )
        if kind is None:
            continue
        actions[idx] = ["PICKUP", kind, 1]
        waiting_animals[kind] -= 1
        free.discard(idx)
        # The actual delivery target is selected from the next observation.

    # Match wheat carriers to distinct unfed animals, nearest first.
    unfed_positions = {pos for pos, _ in unfed}
    for idx in sorted(tuple(free)):
        if inventories[idx].get("WHEAT", 0) <= 0 or not unfed_positions:
            continue
        target = min(unfed_positions, key=lambda p: (_distance(positions[idx], p), p[1], p[0]))
        unfed_positions.remove(target)
        actions[idx] = ["FEED"] if positions[idx] == target else _step_toward(positions[idx], target)
        free.discard(idx)

    # If the field is short of carried feed, route enough empty workers back to
    # the shed.  They will pick up on the following observation.
    unresolved_feed = max(0, len(unfed_positions) - max(0, wheat_in_field - len(unfed) + len(unfed_positions)))
    if unresolved_feed and shed.get("WHEAT", 0) > 0:
        fetchers = max(1, math.ceil(unresolved_feed / 5))
        choices = sorted(
            free,
            key=lambda i: (_distance(positions[i], _nearest_shed(positions[i], size)), i),
        )
        for idx in choices[:fetchers]:
            target = _nearest_shed(positions[idx], size)
            actions[idx] = ["PICKUP", "WHEAT", min(5, unresolved_feed)] if positions[idx] == target else _step_toward(positions[idx], target)
            unresolved_feed -= 5
            free.discard(idx)

    # Independent jobs may share a tile: FEED, CARE, COLLECT and HARVEST can all
    # be performed simultaneously by different workers.  Priority protects care
    # and expiring daily fertilizer while harvesting before the held cap.
    jobs = []
    for pos, tile in animals:
        if not tile.get("cared_today", False):
            jobs.append((0, pos, ["CARE"]))
        if tile.get("fertilizer_available", False):
            jobs.append((1, pos, ["COLLECT_FERTILIZER"]))
        yield_units = int(tile.get("yield_units", 0))
        if yield_units > 0:
            priority = 1 if yield_units >= 3 else 2
            jobs.append((priority, pos, ["HARVEST"]))

    while free and jobs:
        best = None
        for idx in free:
            for j, (priority, target, op) in enumerate(jobs):
                score = (priority, _distance(positions[idx], target), target[1], target[0], idx, j)
                if best is None or score < best[0]:
                    best = (score, idx, j, target, op)
        _, idx, job_index, target, op = best
        actions[idx] = op if positions[idx] == target else _step_toward(positions[idx], target)
        free.remove(idx)
        jobs.pop(job_index)

    # Spare workers prepare compact coop slots.  Weeds and obsolete empty
    # structures are cleared first; a later turn builds the coop.
    build_jobs = []
    for pos, desired_animal in slot_plan:
        tile = farm["tiles"][pos[1]][pos[0]]
        if pos in occupied_slots:
            continue
        desired_structure = ANIMAL_STRUCTURE[desired_animal]
        if tile is None:
            build_jobs.append((pos, ["BUILD_COOP" if desired_structure == "COOP" else "BUILD_PASTURE"]))
        elif isinstance(tile, dict) and tile.get("kind") != desired_structure and "animal" not in tile:
            build_jobs.append((pos, ["DIG"]))

    while free and build_jobs:
        best = None
        for idx in free:
            for j, (target, op) in enumerate(build_jobs):
                score = (_distance(positions[idx], target), planned_slots.index(target), idx, j)
                if best is None or score < best[0]:
                    best = (score, idx, j, target, op)
        _, idx, job_index, target, op = best
        actions[idx] = op if positions[idx] == target else _step_toward(positions[idx], target)
        free.remove(idx)
        build_jobs.pop(job_index)

    # When core work is finished, bank carried products early so the next market
    # pass can sell them.  End-of-day auto-drop remains the fallback.
    for idx in sorted(tuple(free)):
        inv = inventories[idx]
        if inv and (hour >= 18 or not jobs):
            target = _nearest_shed(positions[idx], size)
            actions[idx] = ["DROP"] if positions[idx] == target else _step_toward(positions[idx], target)

    return {
        "farmer": actions[0],
        "hands": actions[1:],
        "market": market,
    }
