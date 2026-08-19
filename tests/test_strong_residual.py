from __future__ import annotations

import copy
from pathlib import Path

from kaggle_environments import make

from candidates import strong_residual, strong_routes


ROOT = Path(__file__).resolve().parents[1]


def _farm(*, quadrants=("NW",), money=20_000.0):
    tiles = [["LOCKED" for _x in range(10)] for _y in range(10)]
    ranges = {
        "NW": (range(0, 5), range(0, 5)),
        "NE": (range(5, 10), range(0, 5)),
        "SW": (range(0, 5), range(5, 10)),
        "SE": (range(5, 10), range(5, 10)),
    }
    for quadrant in quadrants:
        xs, ys = ranges[quadrant]
        for y in ys:
            for x in xs:
                tiles[y][x] = None
    return {
        "money": money,
        "tiles": tiles,
        "farmer": [0, 0],
        "hands": [],
        "hires_today": 0,
        "unlocked_quadrants": list(quadrants),
    }


def _obs(*, day=8, hour=0, shops=(), prices=None):
    products = {
        item: 0
        for item in (*strong_residual.PRODUCTS, *strong_residual.ANIMALS)
    }
    resolved_prices = dict(strong_residual.PRODUCTS)
    resolved_prices.update(prices or {})
    return {
        "player": 0,
        "step": day * 24 + hour,
        "day": day,
        "hour": hour,
        "farms": [_farm(quadrants=("NW", "NE")), _farm(quadrants=("NW", "NE"))],
        "private": {
            "shed": products,
            "seeds": {crop: 0 for crop in strong_residual.CROPS},
            "inventories": [{}],
        },
        "market": {
            "inventory": {item: 10_000 for item in strong_residual.PRODUCTS},
            "prices": resolved_prices,
        },
        "town": {"unlocked_shops": list(shops)},
    }


def _place_animals(farm, kind, count):
    placed = 0
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if tile is not None:
                continue
            farm["tiles"][y][x] = {
                "kind": "COOP" if kind == "GOOSE" else "PASTURE",
                "animal": kind,
                "placed_day": 0,
                "yield_units": 0,
                "fed_today": False,
                "consecutive_unfed": 0,
                "cared_today": False,
                "fertilizer_available": False,
            }
            placed += 1
            if placed == count:
                return


def _place_crops(farm, crop, count):
    placed = 0
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if tile is not None:
                continue
            farm["tiles"][y][x] = {
                "kind": "PLANT",
                "crop": crop,
                "planted_day": 4,
                "watered_today": False,
                "consecutive_unwatered": 0,
                "yield_units": 0,
                "fertilized_until_day": -1,
            }
            placed += 1
            if placed == count:
                return


def test_visible_opponent_herd_reduces_residual_target():
    shops = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
    open_market = _obs(shops=shops)
    contested = copy.deepcopy(open_market)
    _place_animals(contested["farms"][1], "COW", 10)

    open_goals = strong_residual._animal_goals(open_market)
    contested_goals = strong_residual._animal_goals(contested)

    assert open_goals["COW"] > contested_goals["COW"]
    assert contested_goals["COW"] <= open_goals["COW"] // 2
    assert sum(open_goals.values()) <= strong_residual._shop_capacity(open_market)


def test_existing_animals_are_never_abandoned_by_dynamic_capacity():
    obs = _obs(shops=())
    _place_animals(obs["farms"][0], "SHEEP", 15)
    goals = strong_residual._animal_goals(obs)

    assert goals["SHEEP"] >= 15
    assert sum(goals.values()) >= 15


def test_contested_strawberries_rotate_into_other_shop_crops():
    shops = (
        "BRUNCH_SPOT",
        "ICE_CREAM_SHOP",
        "SMOOTHIE_SHOP",
        "FARMERS_MARKET",
        "PIZZA_SHOP",
        "PET_CAFE",
    )
    open_market = _obs(shops=shops)
    contested = copy.deepcopy(open_market)
    _place_crops(contested["farms"][1], "STRAWBERRY", 40)

    open_targets = strong_residual._crop_targets(open_market, open_market["farms"][0], 12)
    contested_targets = strong_residual._crop_targets(contested, contested["farms"][0], 12)

    assert open_targets["STRAWBERRY"] > contested_targets["STRAWBERRY"]
    assert contested_targets["STRAWBERRY"] < 32
    assert contested_targets["TOMATO"] > 0
    assert contested_targets["CARROT"] > 0


def test_premium_hold_and_daily_demand_pacing():
    low = _obs(day=15, hour=0, shops=("BRUNCH_SPOT",), prices={"STRAWBERRY": 90})
    farm = low["farms"][0]
    assert strong_residual._paced_sale_amount(low, farm, "STRAWBERRY", 25, 25) == 0

    high = copy.deepcopy(low)
    high["market"]["prices"]["STRAWBERRY"] = 120
    assert strong_residual._paced_sale_amount(high, farm, "STRAWBERRY", 25, 25) == 6

    high["hour"] = 3
    assert strong_residual._paced_sale_amount(high, farm, "STRAWBERRY", 25, 25) == 0

    high["day"] = 29
    assert strong_residual._paced_sale_amount(high, farm, "STRAWBERRY", 25, 25) == 25


def test_route_overlay_has_private_globals_and_does_not_mutate_source():
    assert strong_residual.agent is not strong_routes.agent
    assert strong_residual.agent.__globals__["POLICY"] is strong_residual.POLICY
    assert strong_routes.agent.__globals__["POLICY"] is strong_routes.POLICY


def test_animal_jobs_are_sequenced_and_idle_feed_worker_steals_backlog():
    positions = [(0, 0), (0, 0), (0, 0), (0, 0)]
    jobs = [
        (2, (4, 4), ["CARE"], "service"),
        (3, (4, 4), ["COLLECT_FERTILIZER"], "service"),
        (2, (4, 4), ["HARVEST"], "service"),
        (7, (4, 3), ["DIG"], "service"),
    ]

    assignments = list(
        strong_residual._assign_jobs(positions, {1, 3}, jobs, ["NW"], 10)
    )

    assert len(assignments) == 2
    assert assignments[0][2] == ["CARE"]
    assert assignments[1][2] == ["DIG"]
    assert {unit for unit, _target, _action in assignments} == {1, 3}

    after_care = [job for job in jobs if job[2] != ["CARE"]]
    next_assignments = list(
        strong_residual._assign_jobs(positions, {1, 3}, after_care, ["NW"], 10)
    )
    assert next_assignments[0][2] == ["COLLECT_FERTILIZER"]


def test_strong_residual_finishes_short_game():
    path = ROOT / "candidates" / "strong_residual.py"
    env = make("kaggriculture", configuration={"episodeSteps": 72, "seed": 44}, debug=True)
    env.run([str(path), "pass"])

    assert env.steps[-1][0].status == "DONE"
    assert env.steps[-1][0].reward is not None
