"""Compatibility alias for the promoted 16-melon/9-wheat crop policy."""

from __future__ import annotations

from candidates.crop import agent as _promoted_agent


def agent(obs):
    return _promoted_agent(obs)
