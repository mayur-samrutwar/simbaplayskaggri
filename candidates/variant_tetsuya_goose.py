"""Experimental tetsuya branch with a day-zero egg hedge."""

from candidates.hybrid_core import agent_with_policy


POLICY = {
    "name": "tetsuya_goose",
    "opening_animals": {"GOOSE": 1, "COW": 2, "SHEEP": 2},
    "opening_seeds": {
        "MELON": 0,
        "STRAWBERRY": 3,
        "TOMATO": 0,
        "CARROT": 0,
        "WHEAT": 10,
    },
    "opening_feed": 5,
    "opening_hires": 5,
    "animal_mode": "tetsuya",
    "crop_mode": "tetsuya",
    "animal_caps": {"GOOSE": 4, "COW": 12, "SHEEP": 10},
    "total_animal_cap": 15,
    "land_goal": 3,
    "allow_fourth_land": False,
    "daily_plant_cap": 12,
    "max_hands": 12,
}


def agent(obs):
    return agent_with_policy(obs, POLICY)
