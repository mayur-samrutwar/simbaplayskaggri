"""Promoted replay-derived hybrid.

The opening copies the most efficient five-animal leaderboard shape while the
crop layer reacts to live town demand, shared prices, and visible opponent
production instead of committing to a fixed strawberry/melon portfolio.
"""

from candidates.hybrid_core import agent_with_policy


POLICY = {
    "name": "adaptive_tetsuya_hybrid",
    "opening_animals": {"GOOSE": 0, "COW": 2, "SHEEP": 3},
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
    "crop_mode": "residual",
    "animal_caps": {"GOOSE": 3, "COW": 12, "SHEEP": 10},
    "total_animal_cap": 15,
    "land_goal": 3,
    "allow_fourth_land": False,
    "daily_plant_cap": 12,
    "max_hands": 12,
}


def agent(obs):
    return agent_with_policy(obs, POLICY)
