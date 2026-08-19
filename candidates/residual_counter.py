"""Residual-demand counter retained as a replay-derived test opponent."""

from candidates.hybrid_core import agent_with_policy


POLICY = {
    "name": "residual_counter",
    "opening_animals": {"GOOSE": 1, "COW": 1, "SHEEP": 2},
    "opening_seeds": {
        "MELON": 9,
        "STRAWBERRY": 0,
        "TOMATO": 0,
        "CARROT": 0,
        "WHEAT": 5,
    },
    "opening_feed": 5,
    "opening_hires": 4,
    "animal_mode": "residual",
    "crop_mode": "residual",
    "animal_caps": {"GOOSE": 7, "COW": 11, "SHEEP": 10},
    "total_animal_cap": 18,
    "land_goal": 3,
    "allow_fourth_land": False,
    "daily_plant_cap": 12,
    "max_hands": 12,
}


def agent(obs):
    return agent_with_policy(obs, POLICY)
