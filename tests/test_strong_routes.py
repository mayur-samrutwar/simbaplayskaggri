from __future__ import annotations

import copy

from kaggle_environments import make

from candidates import strong_routes


def _farm(*, money=20_000.0, hands=()):
    tiles = [["LOCKED" for _x in range(10)] for _y in range(10)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = None
    return {
        "money": money,
        "tiles": tiles,
        "farmer": [0, 0],
        "hands": [list(pos) for pos in hands],
        "hires_today": len(hands),
        "unlocked_quadrants": ["NW"],
    }


def _obs(*, day=5, hour=3, shed=None, inventories=None, farm=None):
    farm = farm or _farm()
    opponent = _farm()
    products = {item: 0 for item in (*strong_routes.PRODUCTS, *strong_routes.ANIMALS)}
    products.update(shed or {})
    inventories = inventories or [{} for _ in range(1 + len(farm["hands"]))]
    return {
        "player": 0,
        "step": day * 24 + hour,
        "day": day,
        "hour": hour,
        "farms": [farm, opponent],
        "private": {
            "shed": products,
            "seeds": {crop: 0 for crop in strong_routes.CROPS},
            "inventories": inventories,
        },
        "market": {
            "inventory": {item: 10_000 for item in strong_routes.PRODUCTS},
            "prices": dict(strong_routes.PRODUCTS),
        },
        "town": {"unlocked_shops": []},
    }


def test_quadrant_slots_start_at_each_shed_facing_corner():
    slots = strong_routes._quadrant_slots(10, {"NW", "NE", "SW"})

    assert slots[:3] == [(4, 4), (5, 4), (4, 5)]
    assert slots[3:6] == [(3, 4), (6, 4), (3, 5)]


def test_routine_hiring_is_nine_and_emergency_is_ten():
    obs = _obs(day=10, hour=0)
    farm = obs["farms"][0]
    for index in range(25):
        x, y = index % 5, index // 5
        farm["tiles"][y][x] = {
            "kind": "PLANT",
            "crop": "STRAWBERRY",
            "planted_day": 4,
            "watered_today": True,
            "consecutive_unwatered": 0,
            "yield_units": 0,
            "fertilized_until_day": -1,
        }

    assert strong_routes._desired_hires(obs, farm) == 9
    farm["tiles"][0][0]["consecutive_unwatered"] = 1
    assert strong_routes._desired_hires(obs, farm) == 10


def test_market_preserves_two_day_feed_reserve():
    obs = _obs(shed={"WHEAT": 20})
    farm = obs["farms"][0]
    for x in (3, 4):
        farm["tiles"][4][x] = {
            "kind": "PASTURE",
            "animal": "COW",
            "placed_day": 0,
            "yield_units": 0,
            "fed_today": True,
            "consecutive_unfed": 0,
            "cared_today": True,
            "fertilizer_available": False,
        }
    goals = strong_routes.core._animal_goals(obs, strong_routes.POLICY)
    actions = strong_routes._unit_actions(obs, farm, goals)
    market = strong_routes._market_actions(obs, farm, actions, goals)
    wheat_sales = [order for order in market if order[:2] == ["SELL", "WHEAT"]]

    assert wheat_sales == [["SELL", "WHEAT", 12]]
    assert not any(order[:2] == ["BUY_PRODUCT", "WHEAT"] for order in market)


def test_collector_waits_for_batch_threshold():
    low = _obs(inventories=[{"STRAWBERRY": 19}])
    farm = low["farms"][0]
    goals = strong_routes.core._animal_goals(low, strong_routes.POLICY)

    assert strong_routes._unit_actions(low, farm, goals)[0] == ["PASS"]

    batch = copy.deepcopy(low)
    batch["private"]["inventories"][0]["STRAWBERRY"] = 20
    assert strong_routes._unit_actions(batch, farm, goals)[0] == ["EAST"]


def test_terminal_drop_is_sold_in_the_same_turn():
    farm = _farm()
    farm["farmer"] = [4, 4]
    obs = _obs(
        day=29,
        hour=15,
        farm=farm,
        inventories=[{"STRAWBERRY": 3}],
    )
    goals = strong_routes.core._animal_goals(obs, strong_routes.POLICY)
    actions = strong_routes._unit_actions(obs, farm, goals)
    market = strong_routes._market_actions(obs, farm, actions, goals)

    assert actions[0] == ["DROP"]
    assert ["SELL", "STRAWBERRY", 3] in market


def test_premium_sales_wait_for_a_town_demand_window_and_use_a_batch():
    quiet = _obs(day=15, hour=2, shed={"STRAWBERRY": 20})
    farm = quiet["farms"][0]
    goals = strong_routes._animal_goals(quiet)
    actions = strong_routes._unit_actions(quiet, farm, goals)

    assert not any(
        order[:2] == ["SELL", "STRAWBERRY"]
        for order in strong_routes._market_actions(quiet, farm, actions, goals)
    )

    window = copy.deepcopy(quiet)
    window["hour"] = 5
    market = strong_routes._market_actions(window, farm, actions, goals)
    sale = next(order for order in market if order[:2] == ["SELL", "STRAWBERRY"])
    assert 0 < sale[2] < 20


def test_full_season_finishes_and_liquidates():
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 73},
        debug=True,
    )
    env.run([strong_routes.agent, "pass"])
    final = env.steps[-1][0]

    assert final.status == "DONE"
    assert final.reward > 50_000
    assert sum(final.observation.private["shed"].values()) == 0
    assert sum(
        sum(inventory.values())
        for inventory in final.observation.private["inventories"]
    ) == 0
