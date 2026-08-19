"""Compact, deadline-first Kaggriculture candidate.

This candidate keeps the live bot's profitable mixed-animal engine, but uses a
different scheduler.  Hands retain a quadrant preference for the whole day,
workers batch valuable output, feed carriers keep multi-animal routes, and
routine hiring is capped at nine hands (ten for a deadline and eleven only for
a shop-supported herd of at least seventeen animals).

The module deliberately keeps no cross-call state: worker roles and zones are
derived from stable hand indices, so it remains safe in parallel episodes and
in either player seat.
"""

from __future__ import annotations

import math
from collections import Counter

from candidates import crop as crop_policy
from candidates import hybrid_core as core
from candidates import livestock as livestock_policy


CROPS = core.CROPS
PRODUCTS = core.PRODUCT_BASE
ANIMALS = core.ANIMALS
ANIMAL_PRODUCT = core.ANIMAL_PRODUCT
ANIMAL_COST = core.ANIMAL_COST
ANIMAL_STRUCTURE = core.ANIMAL_STRUCTURE
OUTPUT_RATE = core.OUTPUT_RATE

POLICY = core._merged_policy(
    {
        "name": "strong_routes",
        "opening_animals": {"GOOSE": 0, "COW": 1, "SHEEP": 2},
        "opening_seeds": {
            "MELON": 10,
            "STRAWBERRY": 0,
            "TOMATO": 0,
            "CARROT": 0,
            "WHEAT": 7,
        },
        "opening_feed": 8,
        "opening_hires": 9,
        "animal_mode": "residual",
        "animal_caps": {"GOOSE": 8, "COW": 10, "SHEEP": 16},
        "total_animal_cap": 22,
        "land_goal": 3,
        "allow_fourth_land": False,
        "daily_plant_cap": 10,
        "max_hands": 10,
    }
)

SALE_ORDER = (
    "STRAWBERRY",
    "MELON",
    "WOOL",
    "MILK",
    "EGG",
    "TOMATO",
    "CARROT",
    "FERTILIZER",
    "WHEAT",
)
PACED_PRODUCTS = {"STRAWBERRY", "MELON", "MILK", "WOOL"}
PREMIUM_HOLD_PRICE = {"STRAWBERRY": 105, "MELON": 130, "MILK": 105, "WOOL": 130}
QUADRANTS = ("NW", "NE", "SW", "SE")


def _owned_cells(farm):
    yield from core._owned_cells(farm)


def _quadrant(pos, size):
    x, y = pos
    half = size // 2
    return ("S" if y >= half else "N") + ("E" if x >= half else "W")


def _quadrant_slots(size, unlocked):
    """Return shed-facing snakes, interleaved across bought quadrants.

    The old global ``-y`` snake filled the far edge of SW before its near edge.
    Every local list below starts at the shed and works outward instead.
    Interleaving prevents one field from becoming a remote monoculture.
    """

    half = size // 2
    specs = {
        "NW": (range(half - 1, -1, -1), range(half - 1, -1, -1)),
        "NE": (range(half, size), range(half - 1, -1, -1)),
        "SW": (range(half - 1, -1, -1), range(half, size)),
        "SE": (range(half, size), range(half, size)),
    }
    local = {}
    for name in QUADRANTS:
        if name not in unlocked:
            continue
        xs, ys = specs[name]
        rows = []
        for row_index, y in enumerate(ys):
            row = list(xs)
            if row_index % 2:
                row.reverse()
            rows.extend((x, y) for x in row)
        local[name] = rows

    answer = []
    for index in range(half * half):
        for name in QUADRANTS:
            if name in local:
                answer.append(local[name][index])
    return answer


def _animal_slot_plan(farm, kinds):
    """Stable, compact animal coordinates, with matching structures first."""

    size = len(farm.get("tiles", [])) or 10
    unlocked = set(farm.get("unlocked_quadrants", ["NW"]))
    occupied = {pos for pos, _tile in core._animal_tiles(farm)}
    candidates = []
    for pos in _quadrant_slots(size, unlocked):
        if pos in occupied:
            continue
        tile = farm["tiles"][pos[1]][pos[0]]
        if tile is None or (
            isinstance(tile, dict)
            and tile.get("kind") in ("COOP", "PASTURE", "WEED")
            and not tile.get("animal")
        ):
            candidates.append(pos)

    answer = []
    unused = set(candidates)
    for kind in kinds:
        structure = ANIMAL_STRUCTURE[kind]
        matching = [
            pos
            for pos in candidates
            if pos in unused
            and isinstance(farm["tiles"][pos[1]][pos[0]], dict)
            and farm["tiles"][pos[1]][pos[0]].get("kind") == structure
        ]
        available = matching or [pos for pos in candidates if pos in unused]
        if not available:
            break
        pos = available[0]
        unused.remove(pos)
        answer.append((pos, kind))
    return answer


def _future_animals(farm, private, goals):
    owned = core._owned_animals(farm, private)
    kinds = []
    for kind in ("SHEEP", "COW", "GOOSE"):
        kinds.extend([kind] * core._pending(private, kind))
    room = max(0, sum(goals.values()) - sum(owned.values()))
    for kind in ("SHEEP", "COW", "GOOSE"):
        missing = max(0, goals[kind] - owned[kind])
        take = min(missing, room)
        kinds.extend([kind] * take)
        room -= take
    return kinds


def _active_crops(farm):
    counts = Counter()
    for _x, _y, tile in _owned_cells(farm):
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            counts[tile.get("crop")] += 1
    return counts


def _animal_goals(obs):
    """Residual goals with a proven mixed-herd production floor.

    Visible opponent supply can trim an over-crowded niche, but it must not
    erase the animal engine that remained profitable in the live losses.
    """

    goals = core._animal_goals(obs, POLICY)
    if int(obs.get("day", 0)) < 3:
        return goals
    shops = Counter((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])
    milk_shops = shops["PIZZA_SHOP"] + shops["ICE_CREAM_SHOP"] + shops["SMOOTHIE_SHOP"]
    egg_shops = shops["BAKERY"] + shops["BRUNCH_SPOT"]
    floors = {
        "GOOSE": 1 if egg_shops < 2 else min(3, egg_shops),
        "COW": 4 if milk_shops < 2 else min(10, 4 + milk_shops),
        # Each Yarn Store consumes twelve wool/day while one cared sheep emits
        # about 1.33/day.  Replay leaders responded with ~14 sheep to two Yarn
        # Stores; the old hard cap of eight surrendered that entire niche.
        "SHEEP": 4 if not shops["YARN_STORE"] else min(16, 4 + 5 * shops["YARN_STORE"]),
    }
    for kind in ANIMALS:
        goals[kind] = min(POLICY["animal_caps"][kind], max(goals[kind], floors[kind]))

    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    while sum(goals.values()) > POLICY["total_animal_cap"]:
        choices = [kind for kind in ANIMALS if goals[kind] > floors[kind]]
        if not choices:
            choices = [kind for kind in ANIMALS if goals[kind] > POLICY["opening_animals"].get(kind, 0)]
        if not choices:
            break
        # Trim the least valuable marginal animal first.
        kind = min(
            choices,
            key=lambda item: (
                OUTPUT_RATE[item] * int(prices.get(ANIMAL_PRODUCT[item], PRODUCTS[ANIMAL_PRODUCT[item]])),
                item,
            ),
        )
        goals[kind] -= 1
    return goals


def _opponent_crop_count(obs, crop):
    me = int(obs.get("player", 0))
    return sum(
        isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and tile.get("crop") == crop
        for player, farm in enumerate(obs.get("farms", []) or [])
        if player != me
        for row in farm.get("tiles", []) or []
        for tile in row
    )


def _crop_targets(obs, farm, animal_count):
    """Fertilizer-aware live-evidence targets, not base-yield scoring.

    A maintained strawberry can produce eight units when fertilizer is routed
    correctly.  The generic marginal scorer only models four, which is why the
    live bot stopped near ten plants while winning bots held about thirty-four.
    """

    day = int(obs.get("day", 0))
    shops = Counter((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])
    strawberry_shops = sum(
        shops[name]
        for name in ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET")
    )
    tomato_shops = shops["PIZZA_SHOP"] + shops["FARMERS_MARKET"]
    carrot_shops = shops["PET_CAFE"] + shops["FARMERS_MARKET"]

    if day <= 3:
        return {
            "MELON": 10,
            "WHEAT": max(7, min(10, int(math.ceil(animal_count * 0.70)) + 3)),
            "STRAWBERRY": 0,
            "TOMATO": 0,
            "CARROT": 0,
        }

    # Visible competition tempers only the optional demand sleeve.  It never
    # erases the recurring-crop base that the replay audit found decisive.
    contested = min(4, _opponent_crop_count(obs, "STRAWBERRY") // 10)
    strawberry = min(38, max(32, 34 + 2 * strawberry_shops - contested))
    if day > 13:
        strawberry = 0  # a newly planted strawberry can no longer reach peak

    tomato = min(10, 2 * tomato_shops)
    carrot = min(10, 3 * carrot_shops)
    if day > 18:
        tomato = 0
    if day > 26:
        carrot = 0

    return {
        "MELON": 0,
        "WHEAT": max(7, min(10, int(math.ceil(animal_count * 0.70)) + 1)),
        "STRAWBERRY": strawberry,
        "TOMATO": tomato,
        "CARROT": carrot,
    }


def _crop_plan(obs, farm, count, animal_count):
    if count <= 0:
        return {}
    active = _active_crops(farm)
    targets = _crop_targets(obs, farm, animal_count)
    plan = Counter()
    remaining = count
    # Feed first after the opening; premium recurring crops get the remaining
    # high-value setup capacity before one-time demand sleeves.
    order = (
        ("WHEAT", "MELON", "STRAWBERRY", "TOMATO", "CARROT")
        if int(obs.get("day", 0)) <= 3
        else ("STRAWBERRY", "TOMATO", "CARROT", "WHEAT", "MELON")
    )
    for crop in order:
        needed = max(0, int(targets.get(crop, 0)) - active[crop])
        take = min(needed, remaining)
        if take:
            plan[crop] += take
            remaining -= take
        if not remaining:
            break
    return dict(plan)


def _crop_assignments(obs, farm, reserved, animal_count):
    day = int(obs.get("day", 0))
    size = len(farm.get("tiles", [])) or 10
    empties = [
        pos
        for pos in _quadrant_slots(size, set(farm.get("unlocked_quadrants", [])))
        if pos not in reserved and farm["tiles"][pos[1]][pos[0]] is None
    ]
    planted_today = sum(
        isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and int(tile.get("planted_day", -1)) == day
        for _x, _y, tile in _owned_cells(farm)
    )
    count = min(len(empties), max(0, POLICY["daily_plant_cap"] - planted_today))
    desired = _crop_plan(obs, farm, count, animal_count)
    pool = Counter((obs.get("private", {}) or {}).get("seeds", {}) or {})

    # Wheat lives closest to the shed; recurring crops then fill compact local
    # strips.  Melons take the farther bootstrap slots that will free on day 10.
    wanted = []
    crop_order = (
        ("WHEAT", "MELON", "STRAWBERRY", "TOMATO", "CARROT")
        if day <= 3
        else ("STRAWBERRY", "TOMATO", "CARROT", "WHEAT", "MELON")
    )
    for crop in crop_order:
        wanted.extend([crop] * int(desired.get(crop, 0)))
    assignments = {}
    for pos in empties[:count]:
        crop = next((item for item in wanted if pool[item] > 0), None)
        if crop is None:
            break
        assignments[pos] = crop
        pool[crop] -= 1
        wanted.remove(crop)
    return assignments


def _fertilizer_targets(obs, farm):
    day = int(obs.get("day", 0))
    if day >= 29:
        return []
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    fert_price = max(1, int(prices.get("FERTILIZER", 100)))
    targets = []
    for x, y, tile in _owned_cells(farm):
        if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        age = day - int(tile.get("planted_day", day))
        until = int(tile.get("fertilized_until_day", -1))
        if until >= day + 1:
            continue
        if crop == "STRAWBERRY" and 7 <= age <= 15:
            value = 2 * int(prices.get(crop, 120))
        elif crop == "TOMATO" and 6 <= age <= 10:
            value = 3 * int(prices.get(crop, 60))
        else:
            continue
        if value >= fert_price:
            targets.append((value, (x, y)))
    return [pos for _value, pos in sorted(targets, key=lambda row: (-row[0], row[1]))]


def _field_jobs(obs, farm, reserved, animal_count):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    jobs = []
    for x, y, tile in _owned_cells(farm):
        pos = (x, y)
        if not isinstance(tile, dict):
            continue
        if tile.get("kind") == "WEED":
            if day < 28 and pos not in reserved:
                jobs.append((7, pos, ["DIG"], "service"))
            continue
        if tile.get("kind") != "PLANT":
            continue
        crop = tile.get("crop")
        data = CROPS.get(crop)
        if not data:
            continue
        age = day - int(tile.get("planted_day", day))
        held = int(tile.get("yield_units", 0))
        watered = bool(tile.get("watered_today", False))
        missed = int(tile.get("consecutive_unwatered", 0))

        if day >= 29:
            if hour <= 14 and held > 0:
                jobs.append((0, pos, ["HARVEST"], "service"))
            continue

        # A second miss kills the plant.  These jobs outrank every profitable
        # but non-survival action, regardless of role or quadrant.
        if not watered and missed >= 1:
            jobs.append((0, pos, ["WATER"], "urgent"))
            continue

        if data["ongoing"]:
            expiring = age >= data["last"]
            if held > 0 and (held >= 2 or expiring or hour >= 18):
                jobs.append((2 if expiring else 3, pos, ["HARVEST"], "service"))
            if not watered and hour >= 8:
                jobs.append((2, pos, ["WATER"], "service"))
        else:
            bonus_start = (data["last"] + 1) // 2
            bonus = bonus_start <= age <= data["last"] and held < data["yield"]
            if not watered and bonus:
                jobs.append((1, pos, ["WATER"], "service"))
            elif age >= data["peak"] and held > 0:
                jobs.append((2, pos, ["HARVEST"], "service"))

    if day < 28 and hour <= 18:
        for pos, crop in _crop_assignments(obs, farm, reserved, animal_count).items():
            # Days 11-13 are the last strawberry cohort window.  Finish setup
            # before routine care/collection can consume the whole day.
            priority = 1 if 10 <= day <= 13 and crop == "STRAWBERRY" else 5
            jobs.append((priority, pos, ["PLANT", crop], "service"))
    return jobs


def _role(unit):
    if unit <= 2:
        return "collect"
    if unit <= 4:
        return "feed"
    return "service"


def _zone(unit, unlocked):
    # Two feed carriers stay free to follow the animal strip.  Other hands keep
    # a stable local field for the whole day, inferred from their index.
    if unit in (3, 4) or not unlocked:
        return None
    return unlocked[unit % len(unlocked)]


def _assign_jobs(positions, free, jobs, unlocked, size):
    """Assign every coordinate to a stable role/zone owner.

    Re-running a global nearest-job match on every observation lets workers
    steal each other's destination as their distances cross; the live trace
    showed long east/west oscillations.  Coordinate ownership is stateless but
    persistent, so a worker keeps approaching the same local route until the
    action is complete.
    """

    free = set(free)
    buckets = {unit: [] for unit in free}
    jobs = list(jobs)
    for index, job in enumerate(jobs):
        priority, target, _action, job_role = job
        if job_role in ("collect", "service"):
            # Water/care/harvest/collect share the same local route.  Splitting
            # them among specialist workers made multiple people traverse the
            # same tiles and left daily fertilizer behind.
            candidates = [unit for unit in free if _role(unit) != "feed"]
        else:  # urgent survival work can use any uncommitted field worker
            candidates = list(free)
        if not candidates:
            candidates = list(free)
        if not candidates:
            break

        target_zone = _quadrant(target, size)
        local = [unit for unit in candidates if _zone(unit, unlocked) == target_zone]
        if local:
            candidates = local
        candidates.sort()
        # Contiguous vertical strips give a worker the crop and animal actions
        # on the same tiles.  This is stable across turns and avoids checkerboard
        # routes that repeatedly cross in the center of a quadrant.
        half = size // 2
        column = target[0] if target_zone.endswith("W") else target[0] - half
        owner = candidates[min(len(candidates) - 1, column * len(candidates) // half)]
        buckets[owner].append((priority, target, _action, job_role, index))

    for unit in sorted(free):
        choices = buckets[unit]
        if not choices:
            continue
        priority, target, action, _job_role, index = min(
            choices,
            key=lambda row: (
                row[0],
                livestock_policy._distance(positions[unit], row[1]),
                row[1][1],
                row[1][0],
                row[4],
            ),
        )
        yield unit, target, action


def _unit_actions(obs, farm, goals):
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    size = len(farm.get("tiles", [])) or 10
    unlocked = [name for name in QUADRANTS if name in set(farm.get("unlocked_quadrants", []))]
    positions = [tuple(farm.get("farmer", (4, 4))), *map(tuple, farm.get("hands", []) or [])]
    inventories = list(private.get("inventories", []) or [])
    inventories.extend({} for _ in range(max(0, len(positions) - len(inventories))))
    actions = [["PASS"] for _ in positions]
    free = set(range(len(positions)))
    animals = core._animal_tiles(farm)
    animal_count = len(animals)

    kinds = _future_animals(farm, private, goals)
    placements = _animal_slot_plan(farm, kinds)
    reserved = {pos for pos, _kind in placements}

    # Hard terminal boundary: hours 15-22 are return/drop turns.  The market
    # plan includes same-turn DROP quantities in its oversized SELL orders.
    if day >= 29 and hour >= 15:
        for unit in sorted(free):
            if not inventories[unit]:
                continue
            target = livestock_policy._nearest_shed(positions[unit], size)
            actions[unit] = (
                ["DROP"]
                if livestock_policy._at_shed(positions[unit], size)
                else livestock_policy._step_toward(positions[unit], target)
            )
        return actions

    # Complete carried-animal placement before generic routing.
    used = set()
    for unit in sorted(tuple(free)):
        carried = next((kind for kind in ANIMALS if inventories[unit].get(kind, 0) > 0), None)
        if carried is None:
            continue
        choices = [pos for pos, kind in placements if kind == carried and pos not in used]
        if not choices:
            continue
        target = min(choices, key=lambda pos: (livestock_policy._distance(positions[unit], pos), pos))
        used.add(target)
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

    waiting = Counter({kind: int(shed.get(kind, 0)) for kind in ANIMALS})
    for unit in sorted(tuple(free)):
        if not livestock_policy._at_shed(positions[unit], size):
            continue
        kind = next(
            (
                kind
                for kind in ("SHEEP", "COW", "GOOSE")
                if waiting[kind]
                and any(target_kind == kind and pos not in used for pos, target_kind in placements)
            ),
            None,
        )
        if kind:
            actions[unit] = ["PICKUP", kind, 1]
            waiting[kind] -= 1
            free.remove(unit)

    # Existing feed carriers follow a persistent nearest-neighbour route.
    unfed = [] if day >= 29 else [(pos, tile) for pos, tile in animals if not tile.get("fed_today", False)]
    remaining_unfed = {pos for pos, _tile in unfed}
    for unit in sorted(tuple(free)):
        if int(inventories[unit].get("WHEAT", 0)) <= 0 or not remaining_unfed:
            continue
        animal_by_pos = dict(unfed)
        target = min(
            remaining_unfed,
            key=lambda pos: (
                int(animal_by_pos[pos].get("consecutive_unfed", 0)) < 1,
                livestock_policy._distance(positions[unit], pos),
                pos,
            ),
        )
        remaining_unfed.remove(target)
        actions[unit] = ["FEED"] if positions[unit] == target else livestock_policy._step_toward(positions[unit], target)
        free.remove(unit)

    # Two carriers take large batches rather than spawning one four-unit trip
    # per worker.  Urgent carriers may cross zones, by design.
    wheat_in_hands = sum(int(inv.get("WHEAT", 0)) for inv in inventories)
    need = max(0, len(unfed) - wheat_in_hands)
    available = min(need, int(shed.get("WHEAT", 0)))
    for unit in (3, 4):
        if unit not in free or available <= 0:
            continue
        if livestock_policy._at_shed(positions[unit], size):
            quantity = min(12, available)
            actions[unit] = ["PICKUP", "WHEAT", quantity]
            available -= quantity
        else:
            target = livestock_policy._nearest_shed(positions[unit], size)
            actions[unit] = livestock_policy._step_toward(positions[unit], target)
        free.remove(unit)

    # Any uncovered animal with one prior miss pulls the nearest free worker
    # toward feed immediately, even if the normal carriers are occupied.
    urgent_unfed = sum(
        not tile.get("fed_today", False) and int(tile.get("consecutive_unfed", 0)) >= 1
        for _pos, tile in animals
    )
    uncovered = max(0, urgent_unfed - wheat_in_hands - (need - available))
    while uncovered > 0 and free and int(shed.get("WHEAT", 0)) > (need - available):
        unit = min(
            free,
            key=lambda index: livestock_policy._distance(
                positions[index], livestock_policy._nearest_shed(positions[index], size)
            ),
        )
        target = livestock_policy._nearest_shed(positions[unit], size)
        actions[unit] = (
            ["PICKUP", "WHEAT", min(8, uncovered)]
            if livestock_policy._at_shed(positions[unit], size)
            else livestock_policy._step_toward(positions[unit], target)
        )
        uncovered -= 8
        free.remove(unit)

    # Fertilizer stays in the field and is routed directly onto high-value
    # recurring crops instead of being sold by a premature return rule.
    fert_targets = _fertilizer_targets(obs, farm)
    used_fert = set()
    for unit in sorted(tuple(free)):
        if int(inventories[unit].get("FERTILIZER", 0)) <= 0:
            continue
        choices = [pos for pos in fert_targets if pos not in used_fert]
        zone = _zone(unit, unlocked)
        local_choices = [pos for pos in choices if zone and _quadrant(pos, size) == zone]
        if local_choices:
            choices = local_choices
        if not choices:
            continue
        target = min(choices, key=lambda pos: (livestock_policy._distance(positions[unit], pos), pos))
        used_fert.add(target)
        actions[unit] = ["FERTILIZE"] if positions[unit] == target else livestock_policy._step_toward(positions[unit], target)
        free.remove(unit)

    # Field workers make mid-day sale runs only with a real batch.  All other
    # inventories auto-drop at day-end for sale next morning.
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    for unit in sorted(tuple(free)):
        inv = inventories[unit] or {}
        units = sum(int(inv.get(item, 0)) for item in PRODUCTS)
        value = sum(int(inv.get(item, 0)) * int(prices.get(item, 1)) for item in PRODUCTS)
        if _role(unit) != "feed" and units and (units >= 20 or value >= 3200):
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
            jobs.append((2, pos, ["CARE"], "service"))
        if tile.get("fertilizer_available", False):
            jobs.append((3, pos, ["COLLECT_FERTILIZER"], "service"))
        held = int(tile.get("yield_units", 0))
        if held > 0:
            jobs.append((2 if held >= 3 or day >= 29 else 3, pos, ["HARVEST"], "service"))
    jobs.extend(_field_jobs(obs, farm, reserved, animal_count))

    for unit, target, action in _assign_jobs(positions, free, jobs, unlocked, size):
        actions[unit] = action if positions[unit] == target else livestock_policy._step_toward(positions[unit], target)
    return actions


def _desired_hires(obs, farm):
    day = int(obs.get("day", 0))
    plants = 0
    animals = 0
    emergency = False
    for _x, _y, tile in _owned_cells(farm):
        if not isinstance(tile, dict):
            continue
        if tile.get("kind") == "PLANT":
            plants += 1
            emergency |= int(tile.get("consecutive_unwatered", 0)) >= 1
        if tile.get("animal"):
            animals += 1
            emergency |= int(tile.get("consecutive_unfed", 0)) >= 1
    target = 9 if day == 0 or plants + animals >= 24 else 8
    if emergency or plants + 3 * animals >= 85 or day >= 28:
        target = 10
    if animals >= 17 or plants + 3 * animals >= 105:
        target = 11
    return target


def _terminal_amounts(obs, unit_actions):
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    amounts = {item: int(shed.get(item, 0)) for item in PRODUCTS}
    inventories = private.get("inventories", []) or []
    if int(obs.get("day", 0)) >= 29:
        for unit, action in enumerate(unit_actions):
            if unit < len(inventories) and action and action[0] == "DROP":
                for item in PRODUCTS:
                    amounts[item] += int((inventories[unit] or {}).get(item, 0))
    return amounts


def _paced_sale_amount(obs, farm, item, amount, shed_total):
    """Adapt the independently tested live-archetype premium pacing gate.

    The archetype's demand cap, shed-pressure escape, and day-26 ramp are kept.
    This scheduler can also deliver batches after every town tick, so it uses
    those post-demand hours rather than restricting all sales to hours 0--1.
    """

    amount = max(0, int(amount))
    if not amount or item not in PACED_PRODUCTS:
        return amount
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    if day >= 29:
        return amount

    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    price = int(prices.get(item, 1))
    base = int(PRODUCTS[item])
    pressure = shed_total >= 72
    late = day >= 26
    post_demand = hour in (1, 5, 9, 13, 17, 21)
    capital_starved = day <= 13 and float(farm.get("money", 0)) < 650.0
    if not (post_demand or pressure or capital_starved or late):
        return 0
    # A softer fraction of the archetype floor avoids carrying a large cohort
    # into one terminal fire-sale when both players occupy the same niche.
    floor = min(int(0.42 * base), PREMIUM_HOLD_PRICE[item])
    if price < floor and not pressure and not late:
        return 0

    # This route's ten-melon cohort often reaches the shed alongside a much
    # larger opponent wave, so it uses the same paced release as recurring
    # premiums instead of assuming it can front-run the market.
    demand = float(core._town_rates(obs).get(item, 1.0))
    cap = max(2, int(math.ceil(demand / 3.0)))
    if pressure:
        cap = max(cap, shed_total - 62, int(math.ceil(amount * 0.30)))
    if price >= base:
        cap = max(cap, int(math.ceil(amount * 0.45)))
    if late:
        cap = max(cap, int(math.ceil(amount / max(1, 29 - day))))
    return min(amount, cap)


def _land_wanted(obs, farm, goals):
    day = int(obs.get("day", 0))
    quadrants = len(farm.get("unlocked_quadrants", []))
    if quadrants >= 3 or day < 3 or day > 16:
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
    # Unlock the second compact field before strawberries are seed-gated; buy
    # the third only when the projected portfolio cannot fit in fifty tiles.
    projected = sum(_crop_targets(obs, farm, sum(core._owned_animals(farm, obs.get("private", {})).values())).values())
    projected += sum(goals.values())
    if quadrants == 1:
        return occupied >= 16
    return projected > 46 and day >= 7


def _seed_plan(obs, farm, goals):
    day = int(obs.get("day", 0))
    private = obs.get("private", {}) or {}
    size = len(farm.get("tiles", [])) or 10
    reserved = {
        pos
        for pos, _kind in _animal_slot_plan(
            farm, _future_animals(farm, private, goals)
        )
    }
    empties = sum(
        farm["tiles"][y][x] is None and (x, y) not in reserved
        for x, y in _quadrant_slots(size, set(farm.get("unlocked_quadrants", [])))
    )
    soon = crop_policy._soon_vacancies(farm, day)
    planted_today = sum(
        isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and int(tile.get("planted_day", -1)) == day
        for _x, _y, tile in _owned_cells(farm)
    )
    count = min(empties + soon, max(0, POLICY["daily_plant_cap"] - planted_today))
    plan = _crop_plan(obs, farm, count, len(core._animal_tiles(farm)))
    seeds = private.get("seeds", {}) or {}
    cutoffs = {"MELON": 18, "STRAWBERRY": 13, "TOMATO": 18, "CARROT": 26, "WHEAT": 25}
    return {
        crop: max(0, int(quantity) - int(seeds.get(crop, 0)))
        for crop, quantity in plan.items()
        if day <= cutoffs[crop] and int(quantity) > int(seeds.get(crop, 0))
    }


def _market_actions(obs, farm, unit_actions, goals):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    animal_count = len(core._animal_tiles(farm))
    amounts = _terminal_amounts(obs, unit_actions)

    # Two full days of feed are untouchable.  Grown wheat and carried wheat are
    # counted before another market purchase, eliminating the old buy/sell loop.
    feed_reserve = 0 if day >= 29 else max(8, 2 * (animal_count + 1))
    sale_amounts = dict(amounts)
    sale_amounts["WHEAT"] = max(0, sale_amounts["WHEAT"] - feed_reserve)
    shed_total = sum(int(value) for value in shed.values())
    for item in PACED_PRODUCTS:
        sale_amounts[item] = _paced_sale_amount(
            obs, farm, item, sale_amounts.get(item, 0), shed_total
        )
    orders = []

    desired = _desired_hires(obs, farm) if hour <= 2 else 0
    current = int(farm.get("hires_today", 0))
    hires = max(0, desired - current)

    # At hour zero labor arrives first; one high-value sale can share the ten
    # market slots.  Purchases resume at hour one with the full queue.
    for _ in range(hires):
        if len(orders) >= 10:
            break
        orders.append(["HIRE"])
    sales = [item for item in SALE_ORDER if sale_amounts.get(item, 0) > 0]
    sales.sort(key=lambda item: (-sale_amounts[item] * int(prices.get(item, 1)), SALE_ORDER.index(item)))
    for item in sales:
        if len(orders) >= 10:
            break
        orders.append(["SELL", item, sale_amounts[item]])

    liquid = float(farm.get("money", 0))
    liquid += sum(
        sale_amounts[item] * int(prices.get(item, 1)) * 0.82
        for item in sales[: max(0, 10 - hires)]
    )
    liquid -= core._fib_cost(current, min(hires, 10))
    feed_cost = max(1, int(prices.get("WHEAT", 25)))
    capital_reserve = max(300.0, feed_reserve * feed_cost)

    if day >= 29:
        return orders[:10]

    # Special opening sequence fits nine hires plus the melon bootstrap on turn
    # zero; the balanced herd, feed, and wheat seed arrive on turn one.
    seeds = private.get("seeds", {}) or {}
    owned = core._owned_animals(farm, private)
    if day == 0 and hour == 0 and not any(seeds.values()):
        if len(orders) < 10:
            orders.append(["BUY_SEED", "MELON", 10])
        return orders[:10]
    opening_missing = False
    if day == 0 and hour <= 2:
        opening = (
            ("SHEEP", 2),
            ("COW", 1),
        )
        for kind, target in opening:
            missing = max(0, target - owned[kind])
            opening_missing |= missing > 0
            cost = ANIMAL_COST[kind] * missing
            if missing and len(orders) < 10 and liquid >= cost:
                orders.append(["BUY_ANIMAL", kind, missing])
                liquid -= cost
        wheat_seed_need = max(0, 7 - int(seeds.get("WHEAT", 0)))
        opening_missing |= wheat_seed_need > 0
        if wheat_seed_need and len(orders) < 10 and liquid >= wheat_seed_need * CROPS["WHEAT"]["seed"]:
            orders.append(["BUY_SEED", "WHEAT", wheat_seed_need])
            liquid -= wheat_seed_need * CROPS["WHEAT"]["seed"]

        opening_feed_need = max(0, 8 - int(shed.get("WHEAT", 0)))
        opening_missing |= opening_feed_need > 0
        if opening_feed_need and len(orders) < 10:
            affordable = max(0, int((liquid - 100.0) // feed_cost))
            quantity = min(opening_feed_need, affordable)
            if quantity:
                orders.append(["BUY_PRODUCT", "WHEAT", quantity])
        # Purchases above do not appear in this observation.  Returning avoids
        # the generic animal/seed/feed branches duplicating them in one queue.
        if opening_missing:
            return orders[:10]

    if len(orders) < 10 and _land_wanted(obs, farm, goals):
        quadrants = len(farm.get("unlocked_quadrants", []))
        land_cost = (1000, 2000, 4000)[min(2, quadrants - 1)]
        land_reserve = min(capital_reserve, 120.0 + max(0, feed_reserve - int(shed.get("WHEAT", 0))) * feed_cost)
        if liquid >= land_reserve + land_cost:
            orders.append(["BUY_LAND"])
            liquid -= land_cost

    # Buy only the economically supported residual animal.  Feed for the
    # resulting herd is reserved before committing capital.
    candidates = []
    cutoffs = {"COW": 17, "SHEEP": 19, "GOOSE": 20}
    for kind in ANIMALS:
        missing = max(0, goals[kind] - owned[kind])
        if not missing or day > cutoffs[kind]:
            continue
        product = ANIMAL_PRODUCT[kind]
        margin = (
            OUTPUT_RATE[kind] * int(prices.get(product, PRODUCTS[product]))
            + int(prices.get("FERTILIZER", 100))
            - feed_cost
        )
        candidates.append((margin * missing, margin, kind, missing))
    if candidates and len(orders) < 10:
        _priority, _margin, kind, missing = max(candidates)
        room = max(0, POLICY["total_animal_cap"] - sum(owned.values()))
        affordable = max(0, int((liquid - capital_reserve) // ANIMAL_COST[kind]))
        quantity = min(3, missing, room, affordable)
        if quantity:
            orders.append(["BUY_ANIMAL", kind, quantity])
            liquid -= quantity * ANIMAL_COST[kind]

    carried_wheat = sum(int((inv or {}).get("WHEAT", 0)) for inv in private.get("inventories", []) or [])
    total_wheat = int(shed.get("WHEAT", 0)) + carried_wheat
    wanted_feed = max(0, feed_reserve - total_wheat)
    if wanted_feed and len(orders) < 10:
        affordable = max(0, int((liquid - 120.0) // feed_cost))
        quantity = min(wanted_feed, affordable)
        if quantity:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            liquid -= quantity * feed_cost

    plan = _seed_plan(obs, farm, goals)
    # Premium recurring seeds precede low-margin feed seeds once the existing
    # two-day feed buffer is safe.
    for crop in ("STRAWBERRY", "TOMATO", "CARROT", "WHEAT", "MELON"):
        quantity = int(plan.get(crop, 0))
        if not quantity or len(orders) >= 10:
            continue
        affordable = max(0, int((liquid - capital_reserve) // CROPS[crop]["seed"]))
        quantity = min(quantity, affordable)
        if quantity:
            orders.append(["BUY_SEED", crop, quantity])
            liquid -= quantity * CROPS[crop]["seed"]
    return orders[:10]


def agent(obs):
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    if player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    goals = _animal_goals(obs)
    unit_actions = _unit_actions(obs, farm, goals)
    return {
        "farmer": unit_actions[0] if unit_actions else ["PASS"],
        "hands": unit_actions[1:],
        "market": _market_actions(obs, farm, unit_actions, goals),
    }
