from __future__ import annotations

import copy
from pathlib import Path

import pytest
from kaggle_environments import make

from candidates import resilient_portfolio as resilient
from candidates import throughput_portfolio as throughput


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidates" / "resilient_portfolio.py"


def _farm(*, quadrants=("NW", "NE", "SW"), money=20_000.0, hands=()):
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
        "hands": [list(position) for position in hands],
        "hires_today": len(hands),
        "unlocked_quadrants": list(quadrants),
    }


def _obs(
    *,
    day=8,
    hour=0,
    shops=(),
    farm=None,
    opponent=None,
    shed=None,
    seeds=None,
    inventories=None,
    prices=None,
):
    farm = farm or _farm()
    opponent = opponent or _farm()
    products = {item: 0 for item in (*resilient.PRODUCTS, *resilient.ANIMALS)}
    products.update(shed or {})
    market_prices = {
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
    market_prices.update(prices or {})
    crop_seeds = {crop: 0 for crop in resilient.CROPS}
    crop_seeds.update(seeds or {})
    inventories = inventories or [{} for _ in range(1 + len(farm["hands"]))]
    return {
        "player": 0,
        "step": day * 24 + hour,
        "day": day,
        "hour": hour,
        "farms": [farm, opponent],
        "private": {
            "shed": products,
            "seeds": crop_seeds,
            "inventories": inventories,
        },
        "market": {
            "inventory": {item: 10_000 for item in resilient.PRODUCTS},
            "prices": market_prices,
        },
        "town": {"unlocked_shops": list(shops)},
    }


def _animal(kind):
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


def _plant(crop, *, planted_day=4, watered=False, missed=0, fertilized=-1):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "watered_today": watered,
        "consecutive_unwatered": missed,
        "yield_units": 0,
        "fertilized_until_day": fertilized,
    }


def _place(farm, value, count):
    placed = 0
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if tile is not None:
                continue
            farm["tiles"][y][x] = copy.deepcopy(value)
            placed += 1
            if placed == count:
                return


def test_opening_book_and_baseline_labor_are_explicit():
    assert resilient.POLICY["opening_animals"] == {
        "GOOSE": 1,
        "COW": 2,
        "SHEEP": 2,
    }
    assert resilient.POLICY["opening_seeds"] == {"MELON": 8, "WHEAT": 7}
    assert resilient.POLICY["hands"] == 9
    assert resilient._desired_hands(_obs(), _farm()) == 9


def test_four_survival_deadlines_trigger_eleventh_hand():
    farm = _farm()
    for x in range(4):
        farm["tiles"][0][x] = _plant("STRAWBERRY", missed=1)
    obs = _obs(farm=farm)

    assert resilient._desired_hands(obs, farm) == 11


def test_large_stable_farm_uses_tenth_hand_without_waiting_for_failures():
    farm = _farm()
    _place(farm, _plant("WHEAT"), 42)

    assert resilient._desired_hands(_obs(farm=farm), farm) == 10


def test_animal_scale_tracks_animal_shops_and_residual_rival_supply():
    shops = ("BAKERY", "BAKERY")
    open_market = _obs(day=12, shops=shops)
    contested = copy.deepcopy(open_market)
    _place(contested["farms"][1], _animal("GOOSE"), 6)

    open_goals = resilient._animal_goals(open_market)
    contested_goals = resilient._animal_goals(contested)

    assert open_goals["GOOSE"] > contested_goals["GOOSE"]
    assert open_goals != contested_goals
    assert sum(open_goals.values()) == 10
    assert sum(contested_goals.values()) >= 5

    crop_only = resilient._animal_goals(
        _obs(day=12, shops=("PET_CAFE", "FARMERS_MARKET") * 4)
    )
    assert sum(crop_only.values()) == 8
    assert crop_only["GOOSE"] >= 1
    assert crop_only["COW"] >= 2
    assert crop_only["SHEEP"] >= 2

    late = _obs(day=24, shops=shops)
    _place(late["farms"][0], _animal("GOOSE"), 1)
    _place(late["farms"][0], _animal("COW"), 2)
    _place(late["farms"][0], _animal("SHEEP"), 2)
    assert resilient._animal_goals(late) == {"GOOSE": 1, "COW": 2, "SHEEP": 2}


def test_crop_book_protects_feed_and_does_not_collapse_against_rival_supply():
    shops = ("PIZZA_SHOP", "BRUNCH_SPOT")
    open_market = _obs(shops=shops)
    contested = copy.deepcopy(open_market)
    _place(contested["farms"][1], _plant("STRAWBERRY"), 40)
    goals = {"GOOSE": 1, "COW": 4, "SHEEP": 3}

    open_targets = resilient._crop_targets(
        open_market, open_market["farms"][0], resilient.POLICY, goals
    )
    contested_targets = resilient._crop_targets(
        contested, contested["farms"][0], resilient.POLICY, goals
    )

    assert open_targets["TOMATO"] > 0  # one pizza shop is enough
    assert contested_targets["STRAWBERRY"] <= open_targets["STRAWBERRY"]
    assert contested_targets["STRAWBERRY"] >= 18
    assert contested_targets["WHEAT"] >= 16
    assert sum(contested_targets.values()) <= 75 - sum(goals.values())


def test_concentrated_town_economies_receive_large_matching_crop_sleeves():
    pet = _obs(day=12, shops=("PET_CAFE",) * 4)
    pet_goals = resilient._animal_goals(pet)
    pet_targets = resilient._crop_targets(
        pet, pet["farms"][0], resilient.POLICY, pet_goals
    )
    assert sum(pet_goals.values()) == 8
    assert pet_targets["CARROT"] >= 30

    farmers = _obs(day=12, shops=("FARMERS_MARKET",) * 4)
    farmers_goals = resilient._animal_goals(farmers)
    farmers_targets = resilient._crop_targets(
        farmers, farmers["farms"][0], resilient.POLICY, farmers_goals
    )
    assert farmers_targets["TOMATO"] >= 8
    assert farmers_targets["CARROT"] >= 8

    berry = _obs(day=12, shops=("SMOOTHIE_SHOP",) * 4)
    berry_goals = resilient._animal_goals(berry)
    berry_targets = resilient._crop_targets(
        berry, berry["farms"][0], resilient.POLICY, berry_goals
    )
    assert berry_goals["COW"] >= 8
    assert berry_targets["STRAWBERRY"] >= 30


def test_crop_heavy_town_can_trigger_third_land_without_ten_animals():
    farm = _farm(quadrants=("NW", "NE"), money=20_000)
    obs = _obs(day=9, hour=2, shops=("PET_CAFE",) * 4, farm=farm)
    goals = resilient._animal_goals(obs)
    layout = resilient._stable_layout(farm, goals, resilient.POLICY)
    actions = [["PASS"]]
    orders = resilient._market_actions(
        obs,
        farm,
        actions,
        resilient.POLICY,
        goals,
        {position for position, _kind in layout},
    )

    assert sum(goals.values()) == 8
    assert ["BUY_LAND"] in orders


def test_strawberry_cohort_is_bounded_and_afternoon_water_is_proactive():
    farm = _farm()
    farm["tiles"][0][0] = _plant("STRAWBERRY", planted_day=4, missed=0)
    obs = _obs(
        day=8,
        hour=12,
        shops=("BRUNCH_SPOT",),
        farm=farm,
        seeds={"STRAWBERRY": 40},
    )
    goals = {"GOOSE": 1, "COW": 2, "SHEEP": 2}
    tasks = resilient._crop_tasks(obs, farm, resilient.POLICY, goals, set())

    berry_plants = [
        task for task in tasks if task[2][:2] == ["PLANT", "STRAWBERRY"]
    ]
    assert len(berry_plants) <= 6
    assert any(task[1] == (0, 0) and task[2] == ["WATER"] for task in tasks)


def test_expired_recurring_crop_is_not_watered():
    farm = _farm()
    farm["tiles"][0][0] = _plant("STRAWBERRY", planted_day=0)
    obs = _obs(day=16, hour=12, farm=farm)
    tasks = resilient._crop_tasks(
        obs,
        farm,
        resilient.POLICY,
        {"GOOSE": 2, "COW": 8, "SHEEP": 6},
        set(),
    )

    assert not any(task[1] == (0, 0) and task[2] == ["WATER"] for task in tasks)


def test_fertilizer_never_targets_melon_and_is_price_gated():
    farm = _farm()
    farm["tiles"][0][0] = _plant("MELON", planted_day=1)
    farm["tiles"][0][1] = _plant("STRAWBERRY", planted_day=-2)
    farm["tiles"][0][2] = _plant("TOMATO", planted_day=0)
    low = _obs(
        day=8,
        farm=farm,
        prices={"STRAWBERRY": 20, "TOMATO": 20, "FERTILIZER": 100},
    )
    assert resilient._fertilizer_targets(low, farm, set()) == []

    high = copy.deepcopy(low)
    high["market"]["prices"].update({"STRAWBERRY": 120, "TOMATO": 60})
    targets = resilient._fertilizer_targets(high, farm, set())
    assert (0, 0) not in targets
    assert (1, 0) in targets
    assert (2, 0) in targets


def test_fertilizer_uses_actual_remaining_events_and_yield_headroom():
    farm = _farm()
    farm["tiles"][0][0] = _plant("STRAWBERRY", planted_day=0)
    farm["tiles"][0][1] = _plant("TOMATO", planted_day=0)
    obs = _obs(
        day=10,
        farm=farm,
        prices={"STRAWBERRY": 100, "TOMATO": 100, "FERTILIZER": 100},
    )

    assert resilient._fertilizer_targets(obs, farm, set()) == []


def test_seed_procurement_keeps_only_one_plantable_wave():
    farm = _farm()
    obs = _obs(day=8, farm=farm, shops=("BRUNCH_SPOT", "PIZZA_SHOP"))
    needs = resilient._seed_needs(
        obs,
        farm,
        resilient.POLICY,
        {"GOOSE": 2, "COW": 5, "SHEEP": 4},
        set(),
    )

    assert needs["STRAWBERRY"] <= 8
    assert needs["WHEAT"] <= 10


def test_storage_pressure_overrides_premium_hold_and_starts_a_bank_run():
    farm = _farm()
    obs = _obs(
        day=20,
        hour=20,
        farm=farm,
        shed={"STRAWBERRY": 85},
        inventories=[{"STRAWBERRY": 10}],
        prices={"STRAWBERRY": 50},
    )
    goals = resilient._animal_goals(obs)
    actions = resilient._unit_actions(obs, farm, resilient.POLICY, goals)
    amounts = resilient._liquidation(obs, actions, 0)

    assert actions[0] != ["PASS"]
    assert amounts["STRAWBERRY"] >= 15


def test_stable_layout_never_relabels_an_occupied_animal():
    farm = _farm(quadrants=("NW", "NE"))
    first = resilient._stable_layout(
        farm, {"GOOSE": 1, "COW": 2, "SHEEP": 2}, resilient.POLICY
    )
    for position, kind in first:
        farm["tiles"][position[1]][position[0]] = _animal(kind)
    expanded = resilient._stable_layout(
        farm, {"GOOSE": 5, "COW": 4, "SHEEP": 4}, resilient.POLICY
    )

    assert set(first).issubset(set(expanded))


def test_stable_layout_uses_empty_cells_before_a_premium_crop():
    farm = _farm(quadrants=("NW", "NE"))
    farm["tiles"][4][5] = _plant("STRAWBERRY", planted_day=0)
    layout = resilient._stable_layout(
        farm,
        {"GOOSE": 2, "COW": 5, "SHEEP": 4},
        resilient.POLICY,
    )

    assert (5, 4) not in {position for position, _kind in layout}


@pytest.fixture(scope="module")
def full_season_state():
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 83},
        debug=True,
    )
    env.run([str(CANDIDATE), "pass"])
    return env.steps[-1][0]


def test_full_season_completes_and_liquidates_every_location(full_season_state):
    assert full_season_state.status == "DONE"
    private = full_season_state.observation.private
    assert sum(private["seeds"].values()) == 0
    assert sum(private["shed"].values()) == 0
    assert sum(
        sum(inventory.values()) for inventory in private.get("inventories", [])
    ) == 0
    farm = full_season_state.observation.farms[0]
    assert not any(
        isinstance(tile, dict) and int(tile.get("yield_units", 0)) > 0
        for row in farm["tiles"]
        for tile in row
    )
    assert not any(
        isinstance(tile, dict) and tile.get("fertilizer_available", False)
        for row in farm["tiles"]
        for tile in row
    )


def test_throughput_herd_scales_with_relevant_shops_not_crop_only_shops():
    crop_only = throughput._animal_goals(
        _obs(day=12, shops=("PET_CAFE", "FARMERS_MARKET") * 2)
    )
    wool = throughput._animal_goals(_obs(day=12, shops=("YARN_STORE",) * 4))
    egg = throughput._animal_goals(_obs(day=12, shops=("BAKERY",) * 4))

    assert sum(crop_only.values()) == 8
    assert crop_only["GOOSE"] == 0
    assert sum(wool.values()) == 16
    assert sum(egg.values()) == 16
    assert wool["SHEEP"] > crop_only["SHEEP"]
    assert egg["GOOSE"] > 0


def test_throughput_engine_does_not_collapse_against_rival_supply():
    obs = _obs(day=12, shops=("YARN_STORE",) * 4)
    _place(obs["farms"][1], _animal("SHEEP"), 14)

    assert sum(throughput._animal_goals(obs).values()) == 16


def test_throughput_prioritizes_paid_premium_seed_near_deadline():
    farm = _farm()
    obs = _obs(
        day=14,
        shops=("SMOOTHIE_SHOP",),
        farm=farm,
        seeds={"STRAWBERRY": 6},
    )
    goals = throughput._animal_goals(obs)
    tasks = throughput._crop_tasks(obs, farm, throughput.POLICY, goals, set())

    berry_priorities = [
        priority
        for priority, _target, operation in tasks
        if operation[:2] == ["PLANT", "STRAWBERRY"]
    ]
    assert berry_priorities
    assert set(berry_priorities) == {-1}


def test_throughput_rotates_only_uncommitted_cells_into_demanded_berries():
    farm = _farm()
    obs = _obs(
        day=8,
        shops=("SMOOTHIE_SHOP", "BRUNCH_SPOT", "PIZZA_SHOP", "FARMERS_MARKET"),
        farm=farm,
    )
    goals = throughput._animal_goals(obs)
    baseline = resilient._crop_targets(obs, farm, throughput.POLICY, goals)
    targets = throughput._crop_targets(obs, farm, throughput.POLICY, goals)

    assert 0 < targets["STRAWBERRY"] - baseline["STRAWBERRY"] <= 6
    assert targets["WHEAT"] == baseline["WHEAT"]
    assert sum(targets.values()) == sum(baseline.values())

    late = copy.deepcopy(obs)
    late.update(day=14, step=14 * 24)
    assert throughput._crop_targets(late, farm, throughput.POLICY, goals) == (
        resilient._crop_targets(late, farm, throughput.POLICY, goals)
    )


def test_throughput_fills_only_three_idle_cells_with_wheat():
    farm = _farm()
    obs = _obs(day=8, shops=(), farm=farm)
    goals = throughput._animal_goals(obs)
    baseline = resilient._crop_targets(obs, farm, throughput.POLICY, goals)
    targets = throughput._crop_targets(obs, farm, throughput.POLICY, goals)

    assert targets["WHEAT"] - baseline["WHEAT"] == 3
    assert targets["STRAWBERRY"] == baseline["STRAWBERRY"]
    assert sum(targets.values()) - sum(baseline.values()) == 3

    carrot_obs = _obs(day=8, shops=("PET_CAFE", "PET_CAFE"), farm=farm)
    carrot_goals = throughput._animal_goals(carrot_obs)
    assert throughput._crop_targets(
        carrot_obs, farm, throughput.POLICY, carrot_goals
    ) == resilient._crop_targets(
        carrot_obs, farm, throughput.POLICY, carrot_goals
    )


def test_throughput_twelfth_hand_requires_backlog_and_town_diversity():
    farm = _farm()
    for x in range(4):
        farm["tiles"][0][x] = _plant("STRAWBERRY", missed=1)

    diverse = _obs(
        farm=farm,
        shops=("SMOOTHIE_SHOP", "PIZZA_SHOP", "YARN_STORE"),
    )
    repeated = _obs(farm=farm, shops=("SMOOTHIE_SHOP",) * 3)

    assert throughput._desired_hands(diverse, farm) == 12
    assert throughput._desired_hands(repeated, farm) == 11


def test_throughput_full_season_finishes_without_inventory():
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 197},
        debug=True,
    )
    env.run([str(ROOT / "candidates" / "throughput_portfolio.py"), "pass"])
    final = env.steps[-1][0]

    assert final.status == "DONE"
    assert sum(final.observation.private["shed"].values()) == 0
    assert sum(final.observation.private["seeds"].values()) == 0
    assert not any(final.observation.private["inventories"])
