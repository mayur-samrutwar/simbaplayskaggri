"""Runnable wrapper for the independent cow-heavy milk archetype."""

from candidates.live_archetypes import agent_for


def agent(obs):
    return agent_for(obs, "milk")
