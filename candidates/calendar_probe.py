"""Temporary policy probe for the calendar candidate."""

from candidates.hybrid_core import agent_with_policy


POLICY = {
    "name": "calendar_probe",
    "opening_animals": {"GOOSE": 0, "COW": 1, "SHEEP": 2},
    "opening_seeds": {
        "MELON": 10,
        "STRAWBERRY": 0,
        "TOMATO": 0,
        "CARROT": 0,
        "WHEAT": 6,
    },
    "opening_feed": 5,
    "opening_hires": 5,
    "animal_mode": "residual",
    "crop_mode": "common",
    "animal_caps": {"GOOSE": 6, "COW": 10, "SHEEP": 10},
    "total_animal_cap": 14,
    "land_goal": 3,
    "allow_fourth_land": False,
    "daily_plant_cap": 12,
    "max_hands": 10,
}


def agent(obs):
    return agent_with_policy(obs, POLICY)
