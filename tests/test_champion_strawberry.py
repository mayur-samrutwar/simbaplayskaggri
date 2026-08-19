from __future__ import annotations

import copy
from pathlib import Path

import pytest
from kaggle_environments import make

from candidates import champion_strawberry, live_archetypes


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidates" / "champion_strawberry.py"


def _farm(*, quadrants=("NW", "NE", "SW")):
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
        "money": 20_000.0,
        "tiles": tiles,
        "farmer": [4, 4],
        "hands": [],
        "hires_today": 0,
        "unlocked_quadrants": list(quadrants),
    }


def _animal_tile(kind):
    return {
        "kind": "COOP" if kind == "GOOSE" else "PASTURE",
        "animal": kind,
        "placed_day": 0,
        "yield_units": 0,
        "fed_today": False,
        "consecutive_unfed": 0,
        "cared_today": False,
        "fertilizer_available": False,
    }


def _obs(farm, *, shed=None, inventories=None, shops=()):
    products = {
        item: 0
        for item in (*live_archetypes.PRODUCTS, *live_archetypes.ANIMALS)
    }
    products.update(shed or {})
    return {
        "player": 0,
        "day": 8,
        "hour": 0,
        "step": 8 * 24,
        "farms": [farm, _farm()],
        "private": {
            "shed": products,
            "seeds": {crop: 0 for crop in live_archetypes.CROPS},
            "inventories": inventories or [{}],
        },
        "market": {
            "inventory": {item: 10_000 for item in live_archetypes.PRODUCTS},
            "prices": {
                "WHEAT": 25,
                "CARROT": 35,
                "TOMATO": 60,
                "STRAWBERRY": 120,
                "MELON": 250,
                "EGG": 50,
                "MILK": 160,
                "WOOL": 200,
                "FERTILIZER": 100,
            },
        },
        "town": {"unlocked_shops": list(shops)},
    }


def _positions(layout, kind):
    return {position for position, slot_kind in layout if slot_kind == kind}


def test_opening_action_matches_proven_live_strawberry_exactly():
    env = make("kaggriculture", configuration={"episodeSteps": 8, "seed": 31}, debug=True)
    observation = env.steps[0][0].observation

    champion = champion_strawberry.agent(copy.deepcopy(observation))
    baseline = live_archetypes.agent_for(copy.deepcopy(observation), "strawberry")

    assert champion == baseline


def test_private_clone_does_not_mutate_live_scheduler():
    assert (
        champion_strawberry._SCHEDULER["_unit_actions"].__globals__["_layout"]
        is champion_strawberry._stable_layout
    )
    assert live_archetypes._unit_actions.__globals__["_layout"] is live_archetypes._layout
    assert champion_strawberry._SCHEDULER["_unit_actions"] is not live_archetypes._unit_actions


def test_empty_board_matches_original_and_target_change_preserves_herd():
    farm = _farm(quadrants=("NW", "NE"))
    policy = champion_strawberry.POLICY
    base_goals = {"GOOSE": 0, "COW": 4, "SHEEP": 3}
    low_sheep = champion_strawberry._stable_layout(
        farm, base_goals, policy
    )
    assert low_sheep == live_archetypes._layout(farm, base_goals, policy)

    for position, kind in low_sheep:
        farm["tiles"][position[1]][position[0]] = _animal_tile(kind)
    high_sheep = champion_strawberry._stable_layout(
        farm, {"GOOSE": 0, "COW": 4, "SHEEP": 8}, policy
    )
    high_cows = champion_strawberry._stable_layout(
        farm, {"GOOSE": 0, "COW": 9, "SHEEP": 3}, policy
    )

    assert _positions(low_sheep, "COW") == _positions(high_sheep, "COW")
    assert _positions(low_sheep, "SHEEP") == _positions(high_cows, "SHEEP")
    assert _positions(high_sheep, "COW").isdisjoint(_positions(high_sheep, "SHEEP"))


def test_existing_positions_and_pending_animals_are_all_represented():
    farm = _farm(quadrants=("NW", "NE"))
    farm["tiles"][0][0] = _animal_tile("COW")
    farm["tiles"][4][9] = _animal_tile("SHEEP")
    obs = _obs(
        farm,
        shed={"COW": 4, "SHEEP": 1},
        inventories=[{"COW": 1}, {"SHEEP": 1}],
    )

    goals = champion_strawberry._animal_goals(obs, champion_strawberry.POLICY)
    layout = champion_strawberry._stable_layout(
        farm, goals, champion_strawberry.POLICY
    )

    assert ((0, 0), "COW") in layout
    assert ((9, 4), "SHEEP") in layout
    assert len(_positions(layout, "COW")) >= 6
    assert len(_positions(layout, "SHEEP")) >= 3


@pytest.fixture(scope="module")
def full_season_states():
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 47},
        debug=True,
    )
    env.run([str(CANDIDATE), str(CANDIDATE)])
    return env.steps[-1]


def test_full_season_leaves_no_pending_animals(full_season_states):
    for state in full_season_states:
        assert state.status == "DONE"
        private = state.observation.private
        pending = sum(int(private["shed"].get(kind, 0)) for kind in live_archetypes.ANIMALS)
        pending += sum(
            int((inventory or {}).get(kind, 0))
            for inventory in private.get("inventories", [])
            for kind in live_archetypes.ANIMALS
        )
        assert pending == 0


def test_full_season_liquidates_all_sellable_inventory(full_season_states):
    for state in full_season_states:
        private = state.observation.private
        sellable = sum(int(private["shed"].get(item, 0)) for item in live_archetypes.PRODUCTS)
        sellable += sum(
            int((inventory or {}).get(item, 0))
            for inventory in private.get("inventories", [])
            for item in live_archetypes.PRODUCTS
        )
        assert sellable == 0
