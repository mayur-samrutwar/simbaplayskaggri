from candidates.crop import _field_tasks


def _final_day_observation(hour):
    tile = {
        "kind": "PLANT",
        "crop": "CARROT",
        "planted_day": 26,
        "watered_today": True,
        "consecutive_unwatered": 0,
        "yield_units": 3,
        "max_lifespan_step": 720,
        "fertilized_until_day": -1,
    }
    farm = {
        "tiles": [[tile]],
        "farmer": [0, 0],
        "hands": [],
        "unlocked_quadrants": ["NW"],
    }
    obs = {
        "player": 0,
        "day": 29,
        "hour": hour,
        "farms": [farm, farm],
        "private": {"shed": {}, "seeds": {}, "inventories": [{}]},
        "market": {"inventory": {}, "prices": {}},
        "town": {"unlocked_shops": []},
    }
    return obs, farm


def test_final_day_harvest_cutoff_leaves_time_to_liquidate():
    obs, farm = _final_day_observation(hour=13)
    assert any(task[3] == ["HARVEST"] for task in _field_tasks(obs, farm))

    obs, farm = _final_day_observation(hour=14)
    assert not any(task[3] == ["HARVEST"] for task in _field_tasks(obs, farm))


def _empty_field_observation(day, hour, seeds):
    farm = {
        "money": 3000,
        "tiles": [[None]],
        "farmer": [0, 0],
        "hands": [],
        "unlocked_quadrants": ["NW"],
    }
    obs = {
        "player": 0,
        "day": day,
        "hour": hour,
        "farms": [farm, farm],
        "private": {"shed": {}, "seeds": seeds, "inventories": [{}]},
        "market": {
            "inventory": {crop: 10_000 for crop in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")},
            "prices": {},
        },
        "town": {"unlocked_shops": []},
    }
    return obs, farm


def test_planting_stops_with_time_left_for_same_day_watering():
    obs, farm = _empty_field_observation(day=0, hour=20, seeds={"MELON": 1})
    assert any(task[3][0] == "PLANT" for task in _field_tasks(obs, farm))

    obs, farm = _empty_field_observation(day=0, hour=21, seeds={"MELON": 1})
    assert not any(task[3][0] == "PLANT" for task in _field_tasks(obs, farm))


def test_sunk_seed_is_not_planted_after_its_latest_maturity_day():
    obs, farm = _empty_field_observation(day=27, hour=0, seeds={"CARROT": 1})
    assert not any(task[3][0] == "PLANT" for task in _field_tasks(obs, farm))
