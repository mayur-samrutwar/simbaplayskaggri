from __future__ import annotations

import copy
from pathlib import Path

import pytest
from kaggle_environments import make

from candidates import adaptive_archetype, live_archetypes


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def milk_full_season():
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 32}, debug=True)
    env.run(
        [
            str(ROOT / "candidates" / "adaptive_archetype.py"),
            str(ROOT / "candidates" / "live_milk.py"),
        ]
    )
    return env


def _farm(*, quadrants=("NW", "NE", "SW"), money=20_000.0):
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
        "farmer": [4, 4],
        "hands": [],
        "hires_today": 0,
        "unlocked_quadrants": list(quadrants),
    }


def _obs(*, day=7, shops=()):
    products = {item: 0 for item in (*live_archetypes.PRODUCTS, *live_archetypes.ANIMALS)}
    prices = {
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
    return {
        "player": 0,
        "step": day * 24,
        "day": day,
        "hour": 0,
        "farms": [_farm(), _farm()],
        "private": {
            "shed": products,
            "seeds": {crop: 0 for crop in live_archetypes.CROPS},
            "inventories": [{}],
        },
        "market": {
            "inventory": {item: 10_000 for item in live_archetypes.PRODUCTS},
            "prices": prices,
        },
        "town": {"unlocked_shops": list(shops)},
    }


def _place_animals(farm, kind, count):
    for _ in range(count):
        for y, row in enumerate(farm["tiles"]):
            for x, tile in enumerate(row):
                if tile is None:
                    farm["tiles"][y][x] = {
                        "kind": "COOP" if kind == "GOOSE" else "PASTURE",
                        "animal": kind,
                        "yield_units": 0,
                        "fed_today": False,
                        "cared_today": False,
                        "fertilizer_available": False,
                    }
                    break
            else:
                continue
            break


def _place_crops(farm, crop, count):
    for _ in range(count):
        for y, row in enumerate(farm["tiles"]):
            for x, tile in enumerate(row):
                if tile is None:
                    farm["tiles"][y][x] = {
                        "kind": "PLANT",
                        "crop": crop,
                        "planted_day": 4,
                        "watered_today": False,
                        "consecutive_unwatered": 0,
                        "yield_units": 0,
                        "fertilized_until_day": -1,
                    }
                    break
            else:
                continue
            break


def test_uses_private_live_scheduler_without_hybrid_dependency():
    source = (ROOT / "candidates" / "adaptive_archetype.py").read_text(encoding="utf-8")
    assert "hybrid_core" not in source
    assert adaptive_archetype._SCHEDULER["_unit_actions"].__globals__["_crop_targets"] is adaptive_archetype._crop_targets
    assert adaptive_archetype._SCHEDULER["_unit_actions"].__globals__["_layout"] is adaptive_archetype._stable_layout
    assert adaptive_archetype._SCHEDULER["_market_actions"].__globals__["_layout"] is adaptive_archetype._stable_layout
    assert live_archetypes._unit_actions.__globals__["_crop_targets"] is live_archetypes._crop_targets


def test_balanced_opening_signature_does_not_alias_other_branches():
    assert adaptive_archetype._is_balanced_signature(
        {"GOOSE": 0, "COW": 2, "SHEEP": 1}
    )
    assert adaptive_archetype._is_balanced_signature(
        {"GOOSE": 1, "COW": 7, "SHEEP": 5}
    )
    assert not adaptive_archetype._is_balanced_signature(
        {"GOOSE": 0, "COW": 4, "SHEEP": 3}
    )
    assert not adaptive_archetype._is_balanced_signature(
        {"GOOSE": 3, "COW": 1, "SHEEP": 0}
    )


def test_balanced_early_return_is_clamped_to_placed_and_pending_animals():
    obs = _obs(day=7)
    _place_animals(obs["farms"][1], "COW", 2)
    _place_animals(obs["farms"][1], "SHEEP", 1)
    _place_animals(obs["farms"][0], "GOOSE", 2)
    obs["private"]["shed"]["GOOSE"] = 3
    obs["private"]["inventories"][0]["COW"] = 9

    goals = adaptive_archetype._animal_goals(
        obs, obs["farms"][0], adaptive_archetype._copy_policy()
    )
    assert adaptive_archetype._opponent_branch(obs) == "balanced"
    assert goals["GOOSE"] >= 5
    assert goals["COW"] >= 9


def test_stable_layout_matches_static_scheduler_and_preserves_actual_kinds():
    farm = _farm()
    policy = adaptive_archetype._copy_policy()
    goals = {"GOOSE": 2, "COW": 5, "SHEEP": 4}
    assert adaptive_archetype._stable_layout(farm, goals, policy) == live_archetypes._layout(
        farm, goals, policy
    )

    # Deliberately place kinds on coordinates from the other kind's canonical
    # sleeve; neither a count change nor an offset may relabel those animals.
    farm["tiles"][0][0] = {
        "kind": "COOP",
        "animal": "GOOSE",
        "yield_units": 0,
        "fed_today": False,
        "cared_today": False,
    }
    farm["tiles"][9][4] = {
        "kind": "PASTURE",
        "animal": "SHEEP",
        "yield_units": 0,
        "fed_today": False,
        "cared_today": False,
    }
    layout = adaptive_archetype._stable_layout(farm, goals, policy)
    positions = [pos for pos, _kind in layout]
    assert ((0, 0), "GOOSE") in layout
    assert ((4, 9), "SHEEP") in layout
    assert len(positions) == len(set(positions))
    assert copy.copy(dict(layout))[(0, 0)] == "GOOSE"
    assert copy.copy(dict(layout))[(4, 9)] == "SHEEP"
    assert {kind: sum(planned == kind for _pos, planned in layout) for kind in goals} == goals


def test_milk_opening_selects_fixed_strawberry_counter_and_preserves_owned():
    obs = _obs(day=7, shops=("PIZZA_SHOP", "ICE_CREAM_SHOP"))
    _place_animals(obs["farms"][1], "COW", 3)
    _place_animals(obs["farms"][0], "GOOSE", 1)
    policy = adaptive_archetype._adaptive_policy(obs, obs["farms"][0])

    assert adaptive_archetype._opponent_branch(obs) == "milk"
    assert policy["animal_targets"] == {"GOOSE": 1, "COW": 4, "SHEEP": 3}
    assert policy["strawberries"] == 40
    assert policy["tomatoes"] == 4
    targets = adaptive_archetype._crop_targets(
        obs, obs["farms"][0], policy, policy["animal_targets"]
    )
    assert targets["STRAWBERRY"] >= 40


def test_opening_action_and_calendar_match_balanced_live_archetype():
    env = make("kaggriculture", configuration={"episodeSteps": 8, "seed": 31}, debug=True)
    observation = env.steps[0][0].observation
    adaptive = adaptive_archetype.agent(copy.deepcopy(observation))
    baseline = live_archetypes.agent_for(copy.deepcopy(observation), "melon_strawberry")

    assert adaptive == baseline
    policy = adaptive_archetype._adaptive_policy(observation, observation["farms"][0])
    assert policy["opening_seeds"] == {"MELON": 12, "WHEAT": 8}
    assert live_archetypes.POLICIES["melon_strawberry"]["opening_seeds"] == {
        "MELON": 12,
        "WHEAT": 8,
    }


def test_visible_strawberry_field_rotates_post_opening_portfolio():
    shops = ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET")
    open_market = _obs(shops=shops)
    contested = copy.deepcopy(open_market)
    _place_crops(contested["farms"][1], "STRAWBERRY", 40)

    open_policy = adaptive_archetype._adaptive_policy(open_market, open_market["farms"][0])
    contested_policy = adaptive_archetype._adaptive_policy(contested, contested["farms"][0])
    open_targets = adaptive_archetype._crop_targets(
        open_market,
        open_market["farms"][0],
        open_policy,
        open_policy["animal_targets"],
    )
    contested_targets = adaptive_archetype._crop_targets(
        contested,
        contested["farms"][0],
        contested_policy,
        contested_policy["animal_targets"],
    )

    assert open_targets["STRAWBERRY"] > contested_targets["STRAWBERRY"]
    assert open_targets["STRAWBERRY"] - contested_targets["STRAWBERRY"] <= 4
    assert contested_targets["TOMATO"] > open_targets["TOMATO"]
    assert contested_targets["CARROT"] >= open_targets["CARROT"]


def test_visible_cow_herd_reduces_new_cow_goal_without_abandoning_owned_animals():
    shops = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
    open_market = _obs(shops=shops)
    contested = copy.deepcopy(open_market)
    _place_animals(contested["farms"][1], "COW", 10)

    base_policy = adaptive_archetype._copy_policy()
    open_goals = adaptive_archetype._animal_goals(
        open_market, open_market["farms"][0], base_policy
    )
    contested_goals = adaptive_archetype._animal_goals(
        contested, contested["farms"][0], base_policy
    )
    assert contested_goals["COW"] < open_goals["COW"]

    _place_animals(contested["farms"][0], "COW", 9)
    retained = adaptive_archetype._animal_goals(
        contested, contested["farms"][0], base_policy
    )
    assert retained["COW"] >= 9


def test_adaptive_archetype_finishes_short_game():
    env = make("kaggriculture", configuration={"episodeSteps": 96, "seed": 32}, debug=True)
    env.run(
        [
            str(ROOT / "candidates" / "adaptive_archetype.py"),
            str(ROOT / "candidates" / "live_melon_strawberry.py"),
        ]
    )
    assert env.steps[-1][0].status == "DONE"
    assert env.steps[-1][0].reward is not None


def test_full_season_goals_never_drop_below_placed_or_pending(milk_full_season):
    for step in milk_full_season.steps:
        observation = step[0].observation
        farm = observation["farms"][0]
        owned = live_archetypes._owned_animals(farm, observation.get("private", {}))
        goals = adaptive_archetype._adaptive_policy(observation, farm)["animal_targets"]
        for kind in adaptive_archetype.ANIMALS:
            assert goals[kind] >= owned[kind]


def test_full_season_finishes_with_zero_pending_animals(milk_full_season):
    final = milk_full_season.steps[-1][0]
    assert final.status == "DONE"
    private = final.observation["private"]
    for kind in adaptive_archetype.ANIMALS:
        assert int(private["shed"].get(kind, 0)) == 0
        assert sum(int(inventory.get(kind, 0)) for inventory in private["inventories"]) == 0
