"""Runnable wrapper for the independent melon/strawberry live archetype."""

from candidates.live_archetypes import agent_for


def agent(obs):
    return agent_for(obs, "melon_strawberry")
