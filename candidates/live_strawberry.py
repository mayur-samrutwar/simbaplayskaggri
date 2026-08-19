"""Runnable wrapper for the independent low-cost strawberry archetype."""

from candidates.live_archetypes import agent_for


def agent(obs):
    return agent_for(obs, "strawberry")
