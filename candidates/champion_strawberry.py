"""The proven live strawberry policy with kind-stable animal slots.

The calibrated ``live_strawberry`` agent is intentionally left unchanged here:
the opening, crop calendar, animal economics, worker scheduler, batching, and
sale pacing all execute from cloned copies of the original functions.  The one
replacement is animal layout.

The original layout shares one cursor across species.  If a later shop changes
the sheep target, every cow slot can move, leaving bought cows without a valid
destination.  This layout preserves the original empty-board geometry, treats
every occupied animal position as immutable, and clamps goals to animals
already committed on the board, in the shed, or in a worker inventory.
"""

from __future__ import annotations

import inspect
import types

from candidates import adaptive_archetype as adaptive
from candidates import live_archetypes as live


ANIMALS = live.ANIMALS
PRODUCTS = live.PRODUCTS
POLICY = live.POLICIES["strawberry"]


def _animal_goals(obs, policy):
    """Return the unchanged live goals, never below committed animals."""

    goals = dict(live._animal_goals(obs, policy))
    farms = obs.get("farms", []) or []
    try:
        player = int(obs.get("player", 0))
    except (TypeError, ValueError):
        player = 0
    if 0 <= player < len(farms):
        owned = live._owned_animals(farms[player], obs.get("private", {}) or {})
        for kind in ANIMALS:
            goals[kind] = max(int(goals.get(kind, 0)), int(owned[kind]))
    return goals


def _stable_layout(farm, animal_goals, policy):
    """Match empty-board geometry, then treat occupied positions as immutable.

    This is the minimal stable layout audited for ``adaptive_archetype``.  The
    normal strawberry herd receives the original coordinates exactly.  Once an
    animal is placed, its position/kind becomes an immutable prefix; subsequent
    goal changes allocate only from the remaining cells and therefore cannot
    relabel or strand that animal.
    """

    return adaptive._stable_layout(farm, animal_goals, policy)


def _clone_scheduler():
    """Clone live-archetype functions into an isolated override namespace."""

    namespace = dict(vars(live))
    namespace["_animal_goals"] = _animal_goals
    namespace["_layout"] = _stable_layout
    for name, value in vars(live).items():
        if name in {"_animal_goals", "_layout"}:
            continue
        if not inspect.isfunction(value) or value.__module__ != live.__name__:
            continue
        cloned = types.FunctionType(
            value.__code__, namespace, value.__name__, value.__defaults__, value.__closure__
        )
        cloned.__kwdefaults__ = value.__kwdefaults__
        cloned.__annotations__ = dict(getattr(value, "__annotations__", {}))
        cloned.__dict__.update(getattr(value, "__dict__", {}))
        namespace[name] = cloned
    return namespace


_SCHEDULER = _clone_scheduler()


def agent(obs):
    """Run the cloned, occupied-position-stable strawberry archetype."""

    return _SCHEDULER["agent_for"](obs, "strawberry")


__all__ = ["agent"]
