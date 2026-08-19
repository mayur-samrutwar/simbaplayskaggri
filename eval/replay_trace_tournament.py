"""Test a candidate against exact public-opponent action traces.

The opponent keeps the actions it issued in the downloaded Kaggle episode,
while the candidate replaces the original target team in the same seat.  This
does not recreate a reactive private bot, but it preserves an independently
implemented live strategy's crop calendar, labor schedule, routing, and market
timing.  Running the incumbent first provides an exact harness check.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from kaggle_environments import make
from kaggle_environments.envs.kaggriculture import kaggriculture as kaggriculture_env


@dataclass
class TraceResult:
    episode_id: int
    opponent: str
    candidate_seat: int
    candidate_money: float
    opponent_money: float
    original_candidate_money: float
    original_opponent_money: float
    outcome: str
    candidate_status: str
    opponent_status: str
    error: str = ""

    @property
    def margin(self) -> float:
        return self.candidate_money - self.opponent_money


def _step_index(obs: dict, turns_per_day: int) -> int:
    # Kaggriculture only copies `step` into player zero's observation.  The
    # public day/hour fields are equivalent and work from either seat.
    return int(obs.get("day", 0)) * turns_per_day + int(obs.get("hour", 0))


def _trace_agent(actions: list[dict], turns_per_day: int):
    def agent(obs):
        # Replay state N stores the action that produced state N.  An agent
        # observing step N must therefore issue the action recorded on N + 1.
        index = _step_index(obs, turns_per_day) + 1
        if 0 <= index < len(actions):
            action = actions[index]
            if isinstance(action, dict):
                return copy.deepcopy(action)
        farms = obs.get("farms", []) or []
        player = int(obs.get("player", 0))
        hands = farms[player].get("hands", []) if player < len(farms) else []
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in hands],
            "market": [],
        }

    return agent


@contextmanager
def _preserve_replay_shops(shop_sequence: list[str], unlock_interval: int):
    """Force the recorded shops after each end-of-day transition.

    Kaggriculture seeds a fresh RNG each day, then consumes a random value only
    for each *empty* farm tile before drawing a shop.  Replacing one player can
    therefore change shop draws despite using the replay seed.  Since public
    actions are conditioned on the original town, trace evaluation must restore
    that town sequence explicitly.
    """

    original = kaggriculture_env._end_of_day

    def end_of_day_with_replay_shops(state, env, day):
        original(state, env, day)
        unlocked = min(len(shop_sequence), (int(day) + 1) // unlock_interval)
        state[0].observation.town["unlocked_shops"] = list(
            shop_sequence[:unlocked]
        )

    kaggriculture_env._end_of_day = end_of_day_with_replay_shops
    try:
        yield
    finally:
        kaggriculture_env._end_of_day = original


def run_trace(
    candidate: Path,
    replay_path: Path,
    team: str,
    save_replay_dir: Path | None = None,
) -> TraceResult:
    replay = json.loads(replay_path.read_text())
    names = list(replay.get("info", {}).get("TeamNames", []))
    if team not in names or len(names) != 2:
        raise ValueError(f"{replay_path}: expected two teams including {team!r}, got {names!r}")
    candidate_seat = names.index(team)
    opponent_seat = 1 - candidate_seat
    actions = [step[opponent_seat].get("action") for step in replay["steps"]]

    configuration = dict(replay.get("configuration", {}))
    configuration["seed"] = int(replay.get("info", {}).get("seed", 0))
    turns_per_day = int(configuration.get("turnsPerDay", 24))
    unlock_interval = max(1, int(configuration.get("townShopUnlockInterval", 3)))
    final_observation = replay["steps"][-1][0].get("observation", {}) or {}
    shop_sequence = list(
        (final_observation.get("town", {}) or {}).get("unlocked_shops", []) or []
    )
    agents = [None, None]
    agents[candidate_seat] = str(candidate.resolve())
    agents[opponent_seat] = _trace_agent(actions, turns_per_day)

    try:
        env = make("kaggriculture", configuration=configuration, debug=True)
        with _preserve_replay_shops(shop_sequence, unlock_interval):
            env.run(agents)
        final = env.steps[-1]
        candidate_state = final[candidate_seat]
        opponent_state = final[opponent_seat]
        candidate_money = float(candidate_state.reward or 0.0)
        opponent_money = float(opponent_state.reward or 0.0)
        outcome = (
            "win" if candidate_money > opponent_money
            else "loss" if candidate_money < opponent_money
            else "tie"
        )
        error = "" if candidate_state.status == "DONE" else f"candidate: {candidate_state.status}"
        if save_replay_dir:
            save_replay_dir.mkdir(parents=True, exist_ok=True)
            generated = env.toJSON()
            generated.setdefault("info", {})["EpisodeId"] = int(
                replay.get("info", {}).get("EpisodeId", 0)
            )
            generated["info"]["seed"] = configuration["seed"]
            generated["info"]["TeamNames"] = [
                "candidate" if seat == candidate_seat else f"trace:{names[opponent_seat]}"
                for seat in range(2)
            ]
            output_path = save_replay_dir / (
                f"episode-{generated['info']['EpisodeId']}-replay.json"
            )
            output_path.write_text(json.dumps(generated))
        return TraceResult(
            episode_id=int(replay.get("info", {}).get("EpisodeId", 0)),
            opponent=names[opponent_seat],
            candidate_seat=candidate_seat,
            candidate_money=candidate_money,
            opponent_money=opponent_money,
            original_candidate_money=float(replay["steps"][-1][candidate_seat].get("reward") or 0.0),
            original_opponent_money=float(replay["steps"][-1][opponent_seat].get("reward") or 0.0),
            outcome=outcome,
            candidate_status=str(candidate_state.status),
            opponent_status=str(opponent_state.status),
            error=error,
        )
    except Exception as exc:  # pragma: no cover - diagnostic failure path
        return TraceResult(
            episode_id=int(replay.get("info", {}).get("EpisodeId", 0)),
            opponent=names[opponent_seat],
            candidate_seat=candidate_seat,
            candidate_money=0.0,
            opponent_money=0.0,
            original_candidate_money=float(replay["steps"][-1][candidate_seat].get("reward") or 0.0),
            original_opponent_money=float(replay["steps"][-1][opponent_seat].get("reward") or 0.0),
            outcome="loss",
            candidate_status="ERROR",
            opponent_status="UNKNOWN",
            error=f"{type(exc).__name__}: {exc}",
        )


def summarize(results: list[TraceResult]) -> dict[str, float | int]:
    valid = [result for result in results if not result.error]
    return {
        "matches": len(results),
        "wins": sum(result.outcome == "win" for result in results),
        "losses": sum(result.outcome == "loss" for result in results),
        "ties": sum(result.outcome == "tie" for result in results),
        "errors": sum(bool(result.error) for result in results),
        "mean_candidate_money": statistics.fmean(result.candidate_money for result in valid) if valid else 0.0,
        "mean_opponent_money": statistics.fmean(result.opponent_money for result in valid) if valid else 0.0,
        "mean_margin": statistics.fmean(result.margin for result in valid) if valid else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--team", default="astro")
    parser.add_argument("--replay", type=Path, action="append", default=[])
    parser.add_argument("--replay-dir", type=Path)
    parser.add_argument("--episode", type=int, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--save-replays", type=Path)
    args = parser.parse_args()

    replay_paths = list(args.replay)
    if args.replay_dir:
        if args.episode:
            replay_paths.extend(
                args.replay_dir / f"episode-{episode_id}-replay.json"
                for episode_id in args.episode
            )
        else:
            replay_paths.extend(sorted(args.replay_dir.glob("episode-*-replay.json")))
    replay_paths = sorted(set(path.resolve() for path in replay_paths))
    if not replay_paths:
        raise SystemExit("provide --replay or --replay-dir")

    results = [
        run_trace(args.candidate, path, args.team, args.save_replays)
        for path in replay_paths
    ]
    payload = {"summary": summarize(results), "matches": [asdict(result) | {"margin": result.margin} for result in results]}
    print(json.dumps(payload, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")
    return 1 if payload["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
