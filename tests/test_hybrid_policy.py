from __future__ import annotations

import copy

import pytest
from kaggle_environments import make

from candidates import hybrid_core


_CROP_NAMES = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
_SHED_NAMES = (*hybrid_core.PRODUCT_BASE, "GOOSE", "COW", "SHEEP")


def _farm(*, money: float = 20_000.0):
    tiles = [["LOCKED" for _x in range(10)] for _y in range(10)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = None
    return {
        "money": money,
        "tiles": tiles,
        "farmer": [4, 4],
        "hands": [],
        "hires_today": 0,
        "unlocked_quadrants": ["NW"],
    }


def _observation(*, day=0, hour=0, shops=(), opponent_melons=0, opponent_geese=0):
    farm = _farm(money=3_000.0 if day == 0 else 20_000.0)
    opponent = _farm(money=3_000.0)

    positions = [(x, y) for y in range(5) for x in range(5)]
    for x, y in positions[:opponent_melons]:
        opponent["tiles"][y][x] = {
            "kind": "PLANT",
            "crop": "MELON",
            "planted_day": 0,
            "watered_today": True,
            "consecutive_unwatered": 0,
            "yield_units": 0,
            "max_lifespan_step": -1,
            "fertilized_until_day": -1,
        }
    for x, y in positions[opponent_melons : opponent_melons + opponent_geese]:
        opponent["tiles"][y][x] = {
            "kind": "COOP",
            "animal": "GOOSE",
            "placed_day": 0,
            "fed_today": True,
            "cared_today": True,
            "consecutive_unfed": 0,
            "fertilizer_available": False,
            "yield_units": 0,
            "pending_care_bonus": 0,
        }

    obs = {
        "player": 0,
        "day": day,
        "hour": hour,
        "step": day * 24 + hour,
        "farms": [farm, opponent],
        "private": {
            "shed": {item: 0 for item in _SHED_NAMES},
            "seeds": {crop: 0 for crop in _CROP_NAMES},
            "inventories": [{}],
        },
        "market": {
            "inventory": {item: 10_000 for item in hybrid_core.PRODUCT_BASE},
            "prices": dict(hybrid_core.PRODUCT_BASE),
        },
        "town": {"unlocked_shops": list(shops)},
    }
    return obs, farm


def _market_quantity(action, operation, item):
    return sum(
        int(order[2])
        for order in action["market"]
        if len(order) >= 3 and order[0] == operation and order[1] == item
    )


def test_default_opening_is_deterministic_and_includes_all_three_animals():
    obs, _farm_state = _observation()

    first = hybrid_core.agent_with_policy(copy.deepcopy(obs))
    second = hybrid_core.agent_with_policy(copy.deepcopy(obs))

    expected_market = [
        ["HIRE"],
        ["HIRE"],
        ["HIRE"],
        ["HIRE"],
        ["BUY_ANIMAL", "SHEEP", 2],
        ["BUY_ANIMAL", "COW", 1],
        ["BUY_ANIMAL", "GOOSE", 1],
        ["BUY_SEED", "MELON", 9],
        ["BUY_SEED", "WHEAT", 5],
        ["BUY_PRODUCT", "WHEAT", 5],
    ]
    assert first == second
    assert first == {"farmer": ["PASS"], "hands": [], "market": expected_market}
    assert len(first["market"]) == 10


def test_residual_animal_goals_add_geese_and_subtract_visible_opponent_supply():
    policy = hybrid_core._merged_policy(None)
    shops = ("BAKERY", "BRUNCH_SPOT")

    uncontested, _farm_state = _observation(day=6, hour=3, shops=shops)
    contested, _farm_state = _observation(
        day=6,
        hour=3,
        shops=shops,
        opponent_geese=8,
    )

    uncontested_goals = hybrid_core._animal_goals(uncontested, policy)
    contested_goals = hybrid_core._animal_goals(contested, policy)

    assert uncontested_goals["GOOSE"] == policy["animal_caps"]["GOOSE"]
    assert contested_goals["GOOSE"] == policy["opening_animals"]["GOOSE"]
    assert uncontested_goals["GOOSE"] > contested_goals["GOOSE"]
    assert uncontested_goals["COW"] >= 2
    assert uncontested_goals["SHEEP"] >= 2


def test_residual_animal_market_branch_can_purchase_geese():
    obs, _farm_state = _observation(
        day=6,
        hour=3,
        shops=("BAKERY", "BRUNCH_SPOT"),
    )
    # Make the requested residual product decisively more valuable than the
    # two compact-herd floors so this assertion isolates the goose branch.
    obs["market"]["prices"].update({"EGG": 500, "MILK": 10, "WOOL": 10})

    action = hybrid_core.agent_with_policy(obs)

    assert _market_quantity(action, "BUY_ANIMAL", "GOOSE") == 4
    assert _market_quantity(action, "BUY_ANIMAL", "COW") == 0
    assert _market_quantity(action, "BUY_ANIMAL", "SHEEP") == 0


@pytest.mark.parametrize(
    ("shop", "crop"),
    (("PIZZA_SHOP", "TOMATO"), ("PET_CAFE", "CARROT")),
)
def test_crop_market_branch_buys_underproduced_shop_crop(shop, crop):
    # A visible 25-melon opponent suppresses another premium-crop pile-up.
    # Eight copies is a valid maximum-shop edge case and makes the residual
    # tomato/carrot signal unambiguous.
    obs, _farm_state = _observation(
        day=6,
        hour=3,
        shops=(shop,) * 8,
        opponent_melons=25,
    )

    action = hybrid_core.agent_with_policy(obs)

    assert _market_quantity(action, "BUY_SEED", crop) > 0
    assert _market_quantity(action, "BUY_SEED", "WHEAT") > 0


def _hybrid_agent(obs):
    return hybrid_core.agent_with_policy(obs)


def test_full_season_hybrid_smoke_game():
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 61},
        debug=True,
    )
    env.run([_hybrid_agent, "pass"])

    final = env.steps[-1][0]
    assert final.status == "DONE"
    assert final.reward > 3_000
    assert any(
        isinstance(tile, dict) and tile.get("animal") == "GOOSE"
        for step in env.steps
        for row in step[0].observation.farms[0]["tiles"]
        for tile in row
    )
