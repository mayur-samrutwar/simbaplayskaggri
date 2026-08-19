"""Opponent-aware portfolio on the independent live-archetype scheduler.

The calibrated ``live_archetypes`` agent already has the strongest independent
opening, worker routing, and premium-sale cadence in this repository.  This
candidate deliberately leaves those mechanics alone.  It changes only the
post-opening portfolio:

* the day-0--2 melon/wheat opening is identical to ``melon_strawberry``;
* after the public boards reveal a rival, animal goals cover residual demand;
* a visible premium monoculture rotates our land into tomato/carrot/feed;
* recurring products retain the scheduler's proven hour-0--1 sale pacing.

All decisions are reconstructed from the current observation.  The cloned
function namespace is important: it lets the imported scheduler resolve the
crop-target override below without mutating ``candidates.live_archetypes`` in
the tournament process.
"""

from __future__ import annotations

import collections
import inspect
import math
import types

from candidates import live_archetypes as live


ANIMALS = live.ANIMALS
ANIMAL_PRODUCT = live.ANIMAL_PRODUCT
OUTPUT_RATE = {"GOOSE": 2.0, "COW": 1.5, "SHEEP": 4.0 / 3.0}

# Copy every mutable member: an adaptive call must never change a reference
# policy used by the opponent in the same Python interpreter.
BASE_POLICY = live.POLICIES["melon_strawberry"]
MILK_COUNTER_TARGETS = {"GOOSE": 0, "COW": 4, "SHEEP": 3}


def _copy_policy():
    return {
        **BASE_POLICY,
        "opening_animals": dict(BASE_POLICY["opening_animals"]),
        "animal_targets": dict(BASE_POLICY["animal_targets"]),
        "opening_seeds": dict(BASE_POLICY["opening_seeds"]),
        "slot_order": tuple(BASE_POLICY["slot_order"]),
    }


def _visible_animals(obs, player):
    counts = collections.Counter()
    farms = obs.get("farms", []) or []
    if 0 <= player < len(farms):
        for _pos, tile in live._animal_tiles(farms[player]):
            counts[tile.get("animal")] += 1
    return counts


def _visible_crops(obs, player):
    counts = collections.Counter()
    farms = obs.get("farms", []) or []
    if 0 <= player < len(farms):
        for _pos, tile in live._plant_tiles(farms[player]):
            counts[tile.get("crop")] += 1
    return counts


def _opponent_counts(obs):
    """Return public rival animals and crops across either player seat."""

    try:
        me = int(obs.get("player", 0))
    except (TypeError, ValueError):
        me = 0
    animals = collections.Counter()
    crops = collections.Counter()
    for player, _farm in enumerate(obs.get("farms", []) or []):
        if player == me:
            continue
        animals.update(_visible_animals(obs, player))
        crops.update(_visible_crops(obs, player))
    return animals, crops


def _is_balanced_signature(animals):
    """Recognize the incumbent 1-goose/7-cow/5-sheep public branch."""

    geese = int(animals["GOOSE"])
    cows = int(animals["COW"])
    sheep = int(animals["SHEEP"])
    # Its public opening is unique among the calibrated branches.  Once its
    # single goose appears, 2C/1S remains a safe transition signature: the
    # goose/tomato branch places several geese before expanding cows.
    return (geese == 0 and cows == 2 and sheep == 1) or (
        geese == 1 and cows >= 2 and sheep >= 1
    )


def _is_milk_signature(animals):
    """Recognize the cow-only public opening of the milk archetype."""

    return (
        int(animals["GOOSE"]) == 0
        and int(animals["COW"]) >= 3
        and int(animals["SHEEP"]) <= 1
    )


def _opening_layout_matches(farm, archetype):
    """Keep a public opening fingerprint usable after the herd expands."""

    policy = live.POLICIES[archetype]
    opening = {kind: int(policy["opening_animals"].get(kind, 0)) for kind in ANIMALS}
    expected = live._layout(farm, opening, policy)
    if len(expected) != sum(opening.values()):
        return False
    for pos, kind in expected:
        tile = farm["tiles"][pos[1]][pos[0]]
        if not isinstance(tile, dict) or tile.get("animal") != kind:
            return False
    return True


def _opponent_branch(obs):
    """Classify only signatures that are unambiguous on the public board."""

    try:
        me = int(obs.get("player", 0))
    except (TypeError, ValueError):
        me = 0
    farms = obs.get("farms", []) or []
    for player, farm in enumerate(farms):
        if player != me and _opening_layout_matches(farm, "milk"):
            return "milk"
    for player, farm in enumerate(farms):
        if player != me and _opening_layout_matches(farm, "melon_strawberry"):
            return "balanced"
    animals, _crops = _opponent_counts(obs)
    if _is_milk_signature(animals):
        return "milk"
    if _is_balanced_signature(animals):
        return "balanced"
    return "unknown"


def _clamp_goals_to_owned(farm, private, goals):
    """Never orphan a board, shed, or carried animal after retargeting."""

    owned = live._owned_animals(farm, private or {})
    return {
        kind: max(int((goals or {}).get(kind, 0)), int(owned[kind]))
        for kind in ANIMALS
    }


def _forecast_opponent_crops(animals):
    """Infer the calibrated public branch before its private seeds are visible.

    Crop purchases are private and both players start the day-6 cohort at the
    same time.  By then, however, the four replay-calibrated branches have a
    distinctive public herd.  The forecast is deliberately discounted later;
    it is evidence for avoiding a simultaneous mirror, not a claim that every
    opponent must be one of these exact policies.
    """

    geese = int(animals["GOOSE"])
    cows = int(animals["COW"])
    sheep = int(animals["SHEEP"])
    if geese >= 2:
        return collections.Counter({"STRAWBERRY": 20, "TOMATO": 12})
    if cows >= 3 and sheep <= 1:
        return collections.Counter({"STRAWBERRY": 28, "TOMATO": 8})
    if sheep >= 2 and cows <= 2:
        return collections.Counter({"STRAWBERRY": 40, "TOMATO": 4})
    if cows or sheep:
        return collections.Counter({"STRAWBERRY": 32, "TOMATO": 4})
    return collections.Counter()


def _opponent_crop_pressure(obs):
    """Blend planted crops with a conservative pre-planting branch forecast."""

    animals, visible = _opponent_counts(obs)
    forecast = _forecast_opponent_crops(animals)
    pressure = collections.Counter(visible)
    day = int(obs.get("day", 0))
    # Forecast only while a simultaneous seed purchase can still be avoided.
    # Once fields are visible, the board itself is the stronger signal.
    if 3 <= day <= 8:
        for crop, amount in forecast.items():
            pressure[crop] = max(pressure[crop], int(math.ceil(amount * 0.75)))
    return pressure


def _animal_capacity(obs):
    shops = sum(live._shop_counts(obs).values())
    return min(15, 13 + min(2, shops // 2))


def _animal_goals(obs, farm, policy):
    """Build a compact herd for town demand left uncovered by the rival."""

    day = int(obs.get("day", 0))
    private = obs.get("private", {}) or {}
    owned = live._owned_animals(farm, private)
    opening = collections.Counter(policy["opening_animals"])
    branch = _opponent_branch(obs)

    if branch == "milk":
        # The fixed strawberry archetype swept the milk branch on holdout play.
        # Preserve anything already purchased before the public fingerprint
        # appeared, but make every still-uncommitted slot match that counter.
        return _clamp_goals_to_owned(farm, private, MILK_COUNTER_TARGETS)

    # Keep the calibrated high-output expansion through the opening.  By day 3
    # most of that herd is public (or already ours); adaptation changes only
    # the still-uncommitted sleeve rather than sacrificing early production.
    if day <= 2:
        return _clamp_goals_to_owned(
            farm, private, live._animal_goals(obs, BASE_POLICY)
        )

    opponent, _crops = _opponent_counts(obs)
    if branch == "balanced":
        return _clamp_goals_to_owned(
            farm, private, live._animal_goals(obs, BASE_POLICY)
        )
    shops = live._shop_counts(obs)
    demand = {
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
    floors = {
        "GOOSE": max(int(opening["GOOSE"]), 1 if demand["GOOSE"] > 1 else 0),
        "COW": max(int(opening["COW"]), 2),
        "SHEEP": max(int(opening["SHEEP"]), 2),
    }
    caps = {"GOOSE": 7, "COW": 10, "SHEEP": 9}
    goals = {}
    residual = {}
    for kind in ANIMALS:
        residual[kind] = max(
            0.0,
            float(demand[kind]) * 1.06
            - float(opponent[kind]) * OUTPUT_RATE[kind] * 0.90,
        )
        target = int(math.ceil(residual[kind] / OUTPUT_RATE[kind]))
        residual_goal = min(
            caps[kind],
            max(floors[kind], int(owned[kind]), target),
        )
        # The live herd is a proven fertilizer engine.  Residual supply may
        # redirect at most two not-yet-owned slots from any one product.
        baseline = int(live._animal_goals(obs, BASE_POLICY)[kind])
        goals[kind] = max(residual_goal, int(owned[kind]), baseline - 2)

    capacity = max(sum(int(owned[kind]) for kind in ANIMALS), _animal_capacity(obs))
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}

    def marginal(kind):
        product = ANIMAL_PRODUCT[kind]
        product_price = int(prices.get(product, {"EGG": 50, "MILK": 160, "WOOL": 200}[product]))
        covered = goals[kind] * OUTPUT_RATE[kind]
        shortage = max(0.0, residual[kind] - covered)
        rival_penalty = 1.0 + 0.12 * int(opponent[kind])
        return (
            OUTPUT_RATE[kind] * product_price / rival_penalty
            + 45.0
            + 30.0 * shortage,
            kind,
        )

    # Fill the compact fertilizer engine with the strongest non-mirrored
    # margin.  This preserves output instead of leaving land idle merely
    # because the opponent already covers all explicit shop consumption.
    while sum(goals.values()) < capacity:
        choices = [kind for kind in ANIMALS if goals[kind] < caps[kind]]
        if not choices:
            break
        goals[max(choices, key=marginal)] += 1

    while sum(goals.values()) > capacity:
        choices = [
            kind
            for kind in ANIMALS
            if goals[kind] > max(floors[kind], int(owned[kind]))
        ]
        if not choices:
            break
        goals[min(choices, key=marginal)] -= 1
    return _clamp_goals_to_owned(farm, private, goals)


def _adaptive_policy(obs, farm):
    """Expose the dynamic choices in the familiar live-policy shape."""

    policy = _copy_policy()
    if _opponent_branch(obs) == "milk":
        policy["animal_targets"] = dict(MILK_COUNTER_TARGETS)
        policy["strawberries"] = 40
        policy["tomatoes"] = 4
    goals = _animal_goals(obs, farm, policy)
    policy["animal_targets"] = dict(goals)
    # Worker count and land goal intentionally remain the calibrated 8/3.
    return policy


def _crop_targets(obs, farm, policy, animal_goals):
    """Redirect a bounded crop sleeve after subtracting public rival supply."""

    day = int(obs.get("day", 0))
    baseline = collections.Counter(live._crop_targets(obs, farm, BASE_POLICY, animal_goals))
    if day <= 3:
        return baseline

    shops = live._shop_counts(obs)
    branch = _opponent_branch(obs)
    if branch == "balanced":
        return baseline
    if branch == "milk":
        return collections.Counter(
            live._crop_targets(obs, farm, policy, animal_goals)
        )
    pressure = _opponent_crop_pressure(obs)
    targets = collections.Counter(baseline)

    berry_shops = (
        shops["BRUNCH_SPOT"]
        + shops["ICE_CREAM_SHOP"]
        + shops["SMOOTHIE_SHOP"]
        + shops["FARMERS_MARKET"]
    )
    tomato_shops = shops["PIZZA_SHOP"] + shops["FARMERS_MARKET"]
    carrot_weight = 2 * shops["PET_CAFE"] + shops["FARMERS_MARKET"]

    # Mirroring also suppresses the rival's price, so abandoning the category
    # entirely is counterproductive in paired play.  Rotate only four slots:
    # enough to reduce our dump while retaining defensive market pressure.
    strawberry_cut = 0
    if day <= 15 and pressure["STRAWBERRY"] >= 16:
        strawberry_cut = min(4, int(pressure["STRAWBERRY"]) // 10)
        targets["STRAWBERRY"] = max(26, targets["STRAWBERRY"] - strawberry_cut)

    # Spend the released sleeve only where the town actually consumes it.
    # Otherwise keep the berry field: generic tomato/carrot does not replace
    # the recurring yield and would hand the rival a premium monopoly.
    redirected = max(0, baseline["STRAWBERRY"] - targets["STRAWBERRY"])
    if redirected and day <= 18 and tomato_shops:
        tomato_room = max(0, min(16, 4 + 4 * tomato_shops) - targets["TOMATO"])
        add = min(redirected, tomato_room)
        targets["TOMATO"] += add
        redirected -= add
    if redirected and day <= 26 and carrot_weight:
        carrot_room = max(0, min(18, 3 + 4 * carrot_weight) - targets["CARROT"])
        add = min(redirected, carrot_room)
        targets["CARROT"] += add
        redirected -= add
    if redirected:
        targets["STRAWBERRY"] += redirected

    # A tomato monoculture gets the same bounded treatment when another crop
    # demand is available; the common live policies rarely trigger this path,
    # but it makes the portfolio rule symmetric for leaderboard opponents.
    if day <= 18 and pressure["TOMATO"] >= 12 and targets["TOMATO"] > 4:
        cut = min(3, int(pressure["TOMATO"]) // 12, targets["TOMATO"] - 4)
        targets["TOMATO"] -= cut
        if day <= 26 and carrot_weight:
            targets["CARROT"] += cut
        else:
            targets["STRAWBERRY"] += cut

    # The normal three-quadrant farm has 75 cells. Feed is inherited unchanged
    # from the calibrated policy; trim only an adaptive addition if necessary.
    capacity = max(0, 25 * int(policy["land"]) - sum(animal_goals.values()))
    if sum(targets.values()) <= capacity:
        return targets
    while sum(targets.values()) > capacity:
        choices = [
            crop
            for crop in ("CARROT", "TOMATO", "STRAWBERRY")
            if targets[crop] > baseline[crop]
        ]
        if not choices:
            break
        targets[choices[0]] -= 1
    return targets


def _stable_layout(farm, animal_goals, policy):
    """Anchor every live animal and add disjoint, kind-stable target slots.

    ``live_archetypes._layout`` offsets all later kinds when an earlier count
    changes.  That is harmless for a static policy but can leave a dynamic
    sheep on a coordinate newly labelled for a cow.  Existing animals are the
    immutable prefix here; matching empty structures and the original layout
    geometry supply only the remaining slots.
    """

    occupied = sorted(
        (
            (pos, tile.get("animal"))
            for pos, tile in live._animal_tiles(farm)
            if tile.get("animal") in ANIMALS
        ),
        key=lambda item: (item[0][1], item[0][0], item[1]),
    )
    occupied_positions = {pos for pos, _kind in occupied}
    visible = collections.Counter(kind for _pos, kind in occupied)
    size = len(farm.get("tiles", [])) or 10
    half = size // 2

    def quadrant(pos):
        x, y = pos
        return 0 if x < half and y < half else 1 if y < half else 2 if x < half else 3

    visible_nw = collections.Counter(
        kind for pos, kind in occupied if quadrant(pos) == 0
    )
    cells = [
        (x, y)
        for x, y, _tile in live._owned_cells(farm)
        if (x, y) not in occupied_positions
    ]
    nw = sorted(
        (pos for pos in cells if quadrant(pos) == 0),
        key=lambda pos: (
            live._distance(pos, live._nearest_shed(pos, size)),
            pos[1],
            -pos[0],
        ),
    )
    expansion = sorted(
        (pos for pos in cells if quadrant(pos) != 0),
        key=lambda pos: (
            quadrant(pos),
            live._distance(pos, live._nearest_shed(pos, size)),
            pos[1],
            pos[0],
        ),
    )

    result = list(occupied)
    nw_cursor = expansion_cursor = 0
    opening = policy["opening_animals"]
    order = tuple(policy.get("slot_order", ())) + tuple(
        kind for kind in ANIMALS if kind not in policy.get("slot_order", ())
    )
    for kind in order:
        goal = max(0, int((animal_goals or {}).get(kind, 0)))
        remaining = max(0, goal - visible[kind])
        opening_goal = min(goal, max(0, int(opening.get(kind, 0))))
        opening_missing = max(0, opening_goal - visible_nw[kind])
        nw_count = min(remaining, opening_missing, len(nw) - nw_cursor)
        for _ in range(nw_count):
            result.append((nw[nw_cursor], kind))
            nw_cursor += 1
        remaining -= nw_count
        expansion_count = min(remaining, len(expansion) - expansion_cursor)
        for _ in range(expansion_count):
            result.append((expansion[expansion_cursor], kind))
            expansion_cursor += 1
    return result


def _clone_scheduler():
    """Clone live-archetype functions into a private override namespace."""

    namespace = dict(vars(live))
    namespace["_crop_targets"] = _crop_targets
    namespace["_layout"] = _stable_layout
    for name, value in vars(live).items():
        if name in {"_crop_targets", "_layout"}:
            continue
        if not inspect.isfunction(value) or value.__module__ != live.__name__:
            continue
        cloned = types.FunctionType(
            value.__code__, namespace, value.__name__, value.__defaults__, value.__closure__
        )
        cloned.__kwdefaults__ = value.__kwdefaults__
        cloned.__annotations__ = dict(getattr(value, "__annotations__", {}))
        cloned.__dict__.update(getattr(value, "__dict__", {}))
        namespace[name] = cloned
    return namespace


_SCHEDULER = _clone_scheduler()


def agent(obs):
    """Return one deterministic opponent-aware live-archetype action."""

    farms = obs.get("farms", []) or []
    try:
        player = int(obs.get("player", 0))
    except (TypeError, ValueError):
        player = 0
    if player < 0 or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    policy = _adaptive_policy(obs, farm)
    goals = _clamp_goals_to_owned(
        farm, obs.get("private", {}) or {}, policy["animal_targets"]
    )
    policy["animal_targets"] = dict(goals)
    layout = _SCHEDULER["_layout"](farm, goals, policy)
    reserved = {pos for pos, _kind in layout}
    actions = _SCHEDULER["_unit_actions"](obs, farm, policy, goals)
    market = _SCHEDULER["_market_actions"](
        obs, farm, actions, policy, goals, reserved
    )
    return {
        "farmer": actions[0] if actions else ["PASS"],
        "hands": actions[1:],
        "market": market,
    }


__all__ = ["agent"]
