"""Compact routing with opponent-aware, diversified economics.

``strong_routes`` has the best worker geometry among the current candidates,
but its economic targets deliberately keep a large mixed-herd floor and a
32--38 strawberry floor.  Those two floors mirror a visible opponent and can
turn a shared premium market into a price collapse.  This candidate preserves
the route scheduler byte-for-byte while replacing only the economic decisions:

* animal targets cover *residual* town demand after visible rival production;
* total herd capacity grows with the unlocked shop economy, up to 21 animals;
* crop targets spread across the town's demand rather than forcing 32 berries;
* recurring premiums are released at roughly one day's demand over hours 0--1.

The function-cloning shim at the bottom gives the imported scheduler a private
global namespace.  It avoids mutating ``candidates.strong_routes`` (important
when several agents run in one interpreter) while still letting all of its
internal calls resolve to the overrides in this module.
"""

from __future__ import annotations

import inspect
import math
import types
from collections import Counter

from candidates import hybrid_core as core
from candidates import strong_routes as routes


CROPS = routes.CROPS
PRODUCTS = routes.PRODUCTS
ANIMALS = routes.ANIMALS
ANIMAL_PRODUCT = routes.ANIMAL_PRODUCT
OUTPUT_RATE = routes.OUTPUT_RATE

POLICY = core._merged_policy(
    {
        "name": "strong_residual",
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
        "animal_caps": {"GOOSE": 5, "COW": 13, "SHEEP": 16},
        "total_animal_cap": 21,
        "land_goal": 3,
        "allow_fourth_land": False,
        "daily_plant_cap": 10,
        "max_hands": 10,
    }
)

PACED_PRODUCTS = set(routes.PACED_PRODUCTS)
PREMIUM_HOLD_PRICE = {
    "STRAWBERRY": 105,
    "MELON": 130,
    "MILK": 105,
    "WOOL": 130,
}


def _shop_capacity(obs):
    """A small town cannot profitably absorb the same herd as a mature one."""

    shops = (obs.get("town", {}) or {}).get("unlocked_shops", []) or []
    # The base thirteen supports fertilizer and the generic market.  Every
    # unlocked shop adds room until the observed leader-sized ceiling of 21.
    return min(POLICY["total_animal_cap"], 15 + len(shops))


def _animal_goals(obs):
    """Cover demand the opponent has not already supplied.

    An opponent animal is discounted slightly because it may miss care or
    delivery.  Unlike the old mixed-herd floors, however, a visible large herd
    genuinely removes our incentive to buy the same animal.
    """

    opening = {
        kind: int(POLICY["opening_animals"].get(kind, 0)) for kind in ANIMALS
    }
    if int(obs.get("day", 0)) < 3:
        return opening

    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0))
    farm = farms[player] if player < len(farms) else {}
    private = obs.get("private", {}) or {}
    owned = core._owned_animals(farm, private)
    opponent = core._opponent_animals(obs)
    rates = core._town_rates(obs)
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}

    # A two-cow/two-sheep base is a compact fertilizer engine.  Geese are only
    # a floor when an egg shop exists, avoiding an otherwise weak generic buy.
    shops = Counter((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])
    egg_shops = shops["BAKERY"] + shops["BRUNCH_SPOT"]
    floors = {
        "GOOSE": max(opening["GOOSE"], 1 if egg_shops else 0),
        "COW": max(opening["COW"], 2),
        "SHEEP": max(opening["SHEEP"], 2),
    }

    goals = {}
    residual_by_kind = {}
    for kind in ANIMALS:
        product = ANIMAL_PRODUCT[kind]
        # Match the live bot's proven residual coefficients: preserve a small
        # scarcity sleeve, but credit only 82% of theoretical rival output.
        # This reacts to competition without gifting the rival an uncontested
        # premium price curve.
        residual = max(
            0.0,
            float(rates.get(product, 1.0)) * 1.12
            - float(opponent[kind]) * OUTPUT_RATE[kind] * 0.82,
        )
        residual_by_kind[kind] = residual
        target = int(math.ceil(residual / OUTPUT_RATE[kind]))
        goals[kind] = max(floors[kind], int(owned[kind]), target)
        goals[kind] = min(int(POLICY["animal_caps"][kind]), goals[kind])

    capacity = max(sum(int(owned[kind]) for kind in ANIMALS), _shop_capacity(obs))
    while sum(goals.values()) > capacity:
        choices = [
            kind
            for kind in ANIMALS
            if goals[kind] > max(floors[kind], int(owned[kind]))
        ]
        if not choices:
            break

        # Trim the animal with the weakest marginal economics after residual
        # coverage.  Fertilizer value is common, so product revenue separates
        # otherwise similar candidates without reintroducing hard herd floors.
        def marginal(kind):
            product = ANIMAL_PRODUCT[kind]
            covered = goals[kind] * OUTPUT_RATE[kind]
            oversupply = max(0.0, covered - residual_by_kind[kind])
            revenue = OUTPUT_RATE[kind] * int(
                prices.get(product, PRODUCTS[product])
            )
            return (oversupply, -revenue, kind)

        goals[max(choices, key=marginal)] -= 1
    return goals


def _crop_targets(obs, farm, animal_count):
    """Town-weighted crop portfolio with a real opponent-supply subtraction."""

    day = int(obs.get("day", 0))
    shops = Counter((obs.get("town", {}) or {}).get("unlocked_shops", []) or [])
    if day <= 3:
        return {
            "MELON": 10,
            "WHEAT": max(7, min(11, int(math.ceil(animal_count * 0.72)) + 3)),
            "STRAWBERRY": 0,
            "TOMATO": 0,
            "CARROT": 0,
        }

    berry_shops = sum(
        shops[name]
        for name in (
            "BRUNCH_SPOT",
            "ICE_CREAM_SHOP",
            "SMOOTHIE_SHOP",
            "FARMERS_MARKET",
        )
    )
    tomato_shops = shops["PIZZA_SHOP"] + shops["FARMERS_MARKET"]
    carrot_weight = 2 * shops["PET_CAFE"] + shops["FARMERS_MARKET"]

    opponent_berries = routes._opponent_crop_count(obs, "STRAWBERRY")
    opponent_tomatoes = routes._opponent_crop_count(obs, "TOMATO")
    opponent_carrots = routes._opponent_crop_count(obs, "CARROT")

    # Keep a productive generic sleeve, then credit one quarter of a visible
    # rival field.  Thus a common 30--40 berry rival moves us from 30+ plants
    # toward roughly twenty, rather than either mirroring 32--38 or abandoning
    # the game's strongest recurring crop almost completely.
    strawberry = max(0, 18 + 4 * berry_shops - int(0.25 * opponent_berries))
    strawberry = min(34, strawberry)
    tomato = max(0, 2 + 5 * tomato_shops - int(0.35 * opponent_tomatoes))
    tomato = min(18, tomato)
    carrot = max(0, 2 + 5 * carrot_weight - int(0.35 * opponent_carrots))
    carrot = min(18, carrot)

    if day > 13:
        strawberry = 0
    if day > 18:
        tomato = 0
    if day > 26:
        carrot = 0
    # A roughly one-plant-per-animal field materially reduces bought feed and
    # gives the two feed carriers local supply.  The cap still preserves room
    # for the diversified premium portfolio on three quadrants.
    wheat = max(7, min(18, int(math.ceil(animal_count * 0.90)) + 2))
    return {
        "MELON": 0,
        "WHEAT": wheat,
        "STRAWBERRY": strawberry,
        "TOMATO": tomato,
        "CARROT": carrot,
    }


def _crop_plan(obs, farm, count, animal_count):
    """Fill target gaps by expected return, with feed protected first."""

    if count <= 0:
        return {}
    active = routes._active_crops(farm)
    targets = _crop_targets(obs, farm, animal_count)
    day = int(obs.get("day", 0))
    if day <= 3:
        order = ("WHEAT", "MELON", "STRAWBERRY", "TOMATO", "CARROT")
    else:
        prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
        expected_units = {
            "STRAWBERRY": 8,
            "TOMATO": 6,
            "CARROT": 3,
            "WHEAT": 4,
            "MELON": 6,
        }
        deadlines = {
            "STRAWBERRY": 13,
            "TOMATO": 18,
            "CARROT": 26,
            "WHEAT": 25,
            "MELON": 18,
        }

        def score(crop):
            gap = max(0, int(targets.get(crop, 0)) - active[crop])
            gross = expected_units[crop] * int(prices.get(crop, PRODUCTS[crop]))
            net = gross - int(CROPS[crop]["seed"])
            urgency = 1.0 + 0.035 * max(0, day - deadlines[crop] + 5)
            return (gap > 0, net * urgency, -CROPS[crop]["first"], crop)

        ranked = sorted(
            ("STRAWBERRY", "TOMATO", "CARROT", "WHEAT", "MELON"),
            key=score,
            reverse=True,
        )
        # Protect a working feed field before economic ranking can spend every
        # near-shed slot on premiums.
        feed_need = max(0, int(targets["WHEAT"]) - active["WHEAT"])
        order = tuple((["WHEAT"] if feed_need >= max(4, count // 2) else []) + ranked)

    plan = Counter()
    remaining = int(count)
    seen = set()
    for crop in order:
        if crop in seen:
            continue
        seen.add(crop)
        needed = max(0, int(targets.get(crop, 0)) - active[crop] - plan[crop])
        take = min(needed, remaining)
        if take:
            plan[crop] += take
            remaining -= take
        if remaining <= 0:
            break
    return dict(plan)


def _paced_sale_amount(obs, farm, item, amount, shed_total):
    """Use the live-archetype hold floor and daily-demand release cadence."""

    amount = max(0, int(amount))
    if not amount or item not in PACED_PRODUCTS:
        return amount
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    if day >= 29:
        return amount

    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    if (
        day < 26
        and shed_total < 72
        and int(prices.get(item, 1)) < PREMIUM_HOLD_PRICE[item]
    ):
        return 0

    # Melons are a single opening cohort: front-run the common day-10 harvest
    # in one acceptable sale instead of stretching it into a recurring curve.
    if item == "MELON":
        return amount

    if hour > 1 and shed_total < 80:
        return 0
    daily_demand = float(core._town_rates(obs).get(item, 1.0))
    cap = max(6, int(math.ceil(daily_demand / 2.0)))
    if shed_total >= 80:
        cap = max(cap, shed_total - 62)
    if day >= 26:
        cap = max(cap, int(math.ceil(amount / max(1, 29 - day))))
    return min(amount, cap)


def _assign_jobs(positions, free, jobs, unlocked, size):
    """Keep stable owners first, then let idle workers steal their backlog.

    The base allocator permanently maps a coordinate strip to one worker and
    excludes feed-role units from service.  That prevents oscillation, but an
    overloaded strip can miss fertilizer while other hands pass.  Feed work is
    already assigned before this function is called, so every still-free feed
    carrier is safe to use in the greedy second pass.
    """

    raw_jobs = list(jobs)
    animal_targets = {
        position
        for _priority, position, action, _role in raw_jobs
        if action and action[0] in ("CARE", "COLLECT_FERTILIZER")
    }
    promoted = []
    for index, (priority, position, action, role) in enumerate(raw_jobs):
        op = action[0] if action else "PASS"
        if position in animal_targets:
            # One operation per animal tile and turn, in the live-proven order.
            # A held-at-cap harvest arrives with base priority two; smaller
            # batches remain one step lower and wait until service is complete.
            if op == "CARE":
                priority = 1
            elif op == "COLLECT_FERTILIZER":
                priority = 2
            elif op == "HARVEST":
                priority = 3 if priority <= 2 else 4
        promoted.append((priority, position, action, role, index))

    base_jobs = [job[:4] for job in promoted]
    first = list(routes._assign_jobs(positions, free, base_jobs, unlocked, size))
    assigned_units = {unit for unit, _target, _action in first}
    assigned_targets = {target for _unit, target, _action in first}
    for assignment in first:
        yield assignment

    remaining = [job for job in promoted if job[1] not in assigned_targets]
    for unit in sorted(set(free) - assigned_units):
        if not remaining:
            break
        chosen = min(
            remaining,
            key=lambda row: (
                row[0],
                routes.livestock_policy._distance(positions[unit], row[1]),
                row[1][1],
                row[1][0],
                row[4],
            ),
        )
        _priority, target, action, _role, _index = chosen
        yield unit, target, action
        # Avoid two simultaneous workers attempting different operations on
        # the same animal or plant tile.
        remaining = [job for job in remaining if job[1] != target]


def _clone_route_scheduler():
    """Return a private strong_routes namespace wired to these overrides."""

    namespace = dict(vars(routes))
    namespace.update(
        {
            "POLICY": POLICY,
            "PACED_PRODUCTS": PACED_PRODUCTS,
            "PREMIUM_HOLD_PRICE": PREMIUM_HOLD_PRICE,
            "_animal_goals": _animal_goals,
            "_crop_targets": _crop_targets,
            "_crop_plan": _crop_plan,
            "_paced_sale_amount": _paced_sale_amount,
            "_assign_jobs": _assign_jobs,
        }
    )
    overrides = set(namespace) - set(vars(routes))
    overrides.update(
        {
            "POLICY",
            "PACED_PRODUCTS",
            "PREMIUM_HOLD_PRICE",
            "_animal_goals",
            "_crop_targets",
            "_crop_plan",
            "_paced_sale_amount",
            "_assign_jobs",
        }
    )
    for name, value in vars(routes).items():
        if name in overrides:
            continue
        if not inspect.isfunction(value) or value.__module__ != routes.__name__:
            continue
        cloned = types.FunctionType(
            value.__code__, namespace, value.__name__, value.__defaults__, value.__closure__
        )
        cloned.__kwdefaults__ = value.__kwdefaults__
        cloned.__annotations__ = dict(getattr(value, "__annotations__", {}))
        cloned.__dict__.update(getattr(value, "__dict__", {}))
        namespace[name] = cloned
    return namespace


_SCHEDULER = _clone_route_scheduler()
agent = _SCHEDULER["agent"]


__all__ = ["POLICY", "agent"]
