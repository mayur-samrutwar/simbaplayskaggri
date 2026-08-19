"""Runnable wrapper for the independent tomato/goose live archetype."""

from candidates.live_archetypes import agent_for


def agent(obs):
    return agent_for(obs, "tomato_goose")
