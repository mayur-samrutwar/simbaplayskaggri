"""Deterministic Kaggriculture scenarios with an explicit town economy.

The stock environment derives shop draws from the same daily RNG stream used
for weed spawning.  A strategy can therefore change later shop draws merely by
changing which tiles are empty.  Promotion comparisons need the exogenous town
sequence held fixed; this module supplies that small piece of scenario control
without modifying the installed environment package.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from kaggle_environments import make
from kaggle_environments.envs.kaggriculture import kaggriculture as kaggriculture_env


Agent = str | Path | Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class FixedShopScenarioResult:
    """Compact deterministic result returned by :func:`run_fixed_shop_scenario`."""

    seed: int
    candidate_seat: int
    requested_shops: tuple[str, ...]
    observed_shops: tuple[str, ...]
    candidate_money: float
    opponent_money: float
    candidate_status: str
    opponent_status: str
    outcome: str
    # One entry for the first recorded state of every observed day.  Including
    # this history makes it possible to audit that shops appeared at the right
    # unlock boundary rather than merely checking the final list.
    shop_history: tuple[tuple[int, tuple[str, ...]], ...]


def _validated_shops(shops: Sequence[str]) -> tuple[str, ...]:
    if isinstance(shops, (str, bytes)):
        raise ValueError("shops must be a sequence of shop names")
    resolved = tuple(shops)
    max_instances = int(kaggriculture_env.MAX_SHOP_INSTANCES)
    if len(resolved) > max_instances:
        raise ValueError(f"shops cannot contain more than {max_instances} instances")
    known = set(kaggriculture_env.SHOPS)
    invalid = [shop for shop in resolved if not isinstance(shop, str) or shop not in known]
    if invalid:
        raise ValueError(f"unknown shop names: {invalid!r}")
    return resolved


@contextmanager
def force_shop_sequence(shops: Sequence[str]) -> Iterator[tuple[str, ...]]:
    """Temporarily force the supplied town-shop unlock sequence.

    Duplicate shops are preserved.  The normal ``townShopUnlockInterval`` is
    respected, and after every end-of-day transition the town is replaced by
    exactly the prefix that should have unlocked by then.  The previous
    ``_end_of_day`` function is restored in ``finally`` on normal exit and on
    every exception.  Nested uses also restore the immediately enclosing hook.

    The Kaggle interpreter function is process-global.  Callers should use
    process isolation, not threads, when running several differently forced
    scenarios concurrently.
    """

    sequence = _validated_shops(shops)
    original_end_of_day = kaggriculture_env._end_of_day

    def end_of_day_with_fixed_shops(state, env, day):
        original_end_of_day(state, env, day)
        unlock_interval = max(
            1,
            int(
                kaggriculture_env.get(
                    env.configuration,
                    "townShopUnlockInterval",
                    3,
                )
            ),
        )
        unlocked_count = min(len(sequence), (int(day) + 1) // unlock_interval)
        state[0].observation.town["unlocked_shops"] = list(
            sequence[:unlocked_count]
        )

    kaggriculture_env._end_of_day = end_of_day_with_fixed_shops
    try:
        yield sequence
    finally:
        kaggriculture_env._end_of_day = original_end_of_day


def _agent_reference(agent: Agent):
    if isinstance(agent, Path):
        return str(agent.resolve())
    return agent


def _daily_shop_history(env) -> tuple[tuple[int, tuple[str, ...]], ...]:
    history: list[tuple[int, tuple[str, ...]]] = []
    seen_days: set[int] = set()
    for step in env.steps:
        observation = step[0].observation
        day = int(observation.get("day", 0))
        if day in seen_days:
            continue
        seen_days.add(day)
        shops = tuple(
            (observation.get("town", {}) or {}).get("unlocked_shops", []) or []
        )
        history.append((day, shops))
    return tuple(history)


def run_fixed_shop_scenario(
    candidate: Agent,
    opponent: Agent,
    *,
    seed: int,
    shops: Sequence[str],
    candidate_seat: int,
    episode_steps: int = 720,
    configuration: Mapping[str, Any] | None = None,
) -> FixedShopScenarioResult:
    """Run two agents with an explicit seed, shop sequence, and candidate seat.

    Additional environment configuration may be supplied, but the explicit
    ``seed`` and ``episode_steps`` arguments take precedence. Exceptions are
    intentionally allowed to propagate; :func:`force_shop_sequence` still
    restores the environment hook before they leave this function.
    """

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if candidate_seat not in (0, 1):
        raise ValueError("candidate_seat must be 0 or 1")
    if isinstance(episode_steps, bool) or not isinstance(episode_steps, int):
        raise ValueError("episode_steps must be a positive integer")
    if episode_steps <= 0:
        raise ValueError("episode_steps must be a positive integer")
    fixed_shops = _validated_shops(shops)

    resolved_configuration = dict(configuration or {})
    resolved_configuration["seed"] = seed
    resolved_configuration["episodeSteps"] = episode_steps
    candidate_ref = _agent_reference(candidate)
    opponent_ref = _agent_reference(opponent)
    agents = (
        [candidate_ref, opponent_ref]
        if candidate_seat == 0
        else [opponent_ref, candidate_ref]
    )

    env = make("kaggriculture", configuration=resolved_configuration, debug=True)
    with force_shop_sequence(fixed_shops):
        env.run(agents)

    final = env.steps[-1]
    candidate_state = final[candidate_seat]
    opponent_state = final[1 - candidate_seat]
    candidate_money = float(candidate_state.reward or 0.0)
    opponent_money = float(opponent_state.reward or 0.0)
    candidate_status = str(candidate_state.status)
    opponent_status = str(opponent_state.status)
    if candidate_status != "DONE":
        outcome = "loss"
    elif opponent_status != "DONE":
        outcome = "win"
    elif candidate_money > opponent_money:
        outcome = "win"
    elif candidate_money < opponent_money:
        outcome = "loss"
    else:
        outcome = "tie"

    observed_shops = tuple(
        (final[0].observation.get("town", {}) or {}).get("unlocked_shops", [])
        or []
    )
    return FixedShopScenarioResult(
        seed=seed,
        candidate_seat=candidate_seat,
        requested_shops=fixed_shops,
        observed_shops=observed_shops,
        candidate_money=candidate_money,
        opponent_money=opponent_money,
        candidate_status=candidate_status,
        opponent_status=opponent_status,
        outcome=outcome,
        shop_history=_daily_shop_history(env),
    )
