"""Replay-derived emulator of Arman Tuganbaev's balanced top bot."""

from candidates.hybrid_core import agent_with_policy


POLICY = {
    "name": "leaderboard_arman",
    "opening_animals": {"GOOSE": 0, "COW": 0, "SHEEP": 4},
    "opening_seeds": {
        "MELON": 7,
        "STRAWBERRY": 0,
        "TOMATO": 0,
        "CARROT": 0,
        "WHEAT": 5,
    },
    "opening_feed": 8,
    "opening_hires": 5,
    "animal_mode": "arman",
    "crop_mode": "arman",
    "animal_caps": {"GOOSE": 0, "COW": 11, "SHEEP": 14},
    "total_animal_cap": 22,
    "land_goal": 3,
    "allow_fourth_land": True,
    "daily_plant_cap": 12,
    "max_hands": 14,
}


def agent(obs):
    return agent_with_policy(obs, POLICY)
