"""Replay-derived emulator of the common 2C/2S leaderboard family."""

from candidates.hybrid_core import agent_with_policy


POLICY = {
    "name": "leaderboard_common",
    "opening_animals": {"GOOSE": 0, "COW": 2, "SHEEP": 2},
    "opening_seeds": {
        "MELON": 12,
        "STRAWBERRY": 0,
        "TOMATO": 0,
        "CARROT": 0,
        "WHEAT": 7,
    },
    "opening_feed": 5,
    "opening_hires": 5,
    "animal_mode": "common",
    "crop_mode": "common",
    "animal_caps": {"GOOSE": 0, "COW": 10, "SHEEP": 12},
    "total_animal_cap": 18,
    "land_goal": 3,
    "allow_fourth_land": True,
    "daily_plant_cap": 12,
    "max_hands": 12,
}


def agent(obs):
    return agent_with_policy(obs, POLICY)
