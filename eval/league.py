"""Run a deterministic paired-seat round-robin league of local agents.

Each unordered pair plays every seed twice, once from each seat. Agent
references may be Python files, importable module names, or Kaggle's built-in
``pass``, ``random``, and ``starter`` agents.

Examples:
    python -m eval.league \
        --agent incumbent=main.py \
        --agent crop=candidates.crop \
        --agent livestock=candidates/livestock.py \
        --seeds 0:8

    python -m eval.league --agent main=main.py --agent starter=starter \
        --seeds 20,21,22 --json artifacts/league.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from eval.tournament import BUILT_INS, MatchSpec, _run_match, parse_seeds


@dataclass(frozen=True)
class AgentEntry:
    """A display name paired with a Kaggle-compatible agent reference."""

    name: str
    reference: str


@dataclass(frozen=True)
class LeagueMatchSpec:
    seed: int
    agent_a: AgentEntry
    agent_b: AgentEntry
    agent_a_seat: int
    episode_steps: int


@dataclass
class LeagueMatchResult:
    seed: int
    agent_a: str
    agent_b: str
    agent_a_seat: int
    agent_a_money: float
    agent_b_money: float
    agent_a_status: str
    agent_b_status: str
    outcome_for_a: str
    elapsed_seconds: float
    shops: str
    error: str = ""


def _resolve_agent_reference(raw: str) -> str:
    """Resolve a built-in, file path, or importable module to an agent path."""
    raw = raw.strip()
    if raw in BUILT_INS:
        return raw

    path = Path(raw).expanduser()
    if path.is_file():
        return str(path.resolve())
    if path.exists():
        raise ValueError(f"agent reference is not a file: {raw}")

    try:
        spec = importlib.util.find_spec(raw)
    except (ImportError, ModuleNotFoundError, AttributeError, ValueError):
        spec = None
    if spec is not None and spec.origin and spec.origin not in {"built-in", "frozen"}:
        module_path = Path(spec.origin)
        if module_path.is_file():
            return str(module_path.resolve())

    raise ValueError(
        f"agent reference {raw!r} is neither a file, an importable module, "
        f"nor one of: {', '.join(sorted(BUILT_INS))}"
    )


def parse_agent(raw: str) -> AgentEntry:
    """Parse ``NAME=REFERENCE`` and resolve its local module reference."""
    if "=" not in raw:
        raise ValueError("agent must be written as NAME=PATH_OR_MODULE")
    name, reference = raw.split("=", 1)
    name = name.strip()
    reference = reference.strip()
    if not name:
        raise ValueError("agent name cannot be empty")
    if not reference:
        raise ValueError(f"agent {name!r} has an empty reference")
    return AgentEntry(name=name, reference=_resolve_agent_reference(reference))


def _play(spec: LeagueMatchSpec) -> LeagueMatchResult:
    result = _run_match(
        MatchSpec(
            seed=spec.seed,
            candidate=spec.agent_a.reference,
            opponent=spec.agent_b.reference,
            candidate_seat=spec.agent_a_seat,
            episode_steps=spec.episode_steps,
        )
    )
    return LeagueMatchResult(
        seed=spec.seed,
        agent_a=spec.agent_a.name,
        agent_b=spec.agent_b.name,
        agent_a_seat=spec.agent_a_seat,
        agent_a_money=result.candidate_money,
        agent_b_money=result.opponent_money,
        agent_a_status=result.candidate_status,
        agent_b_status=result.opponent_status,
        outcome_for_a=result.outcome,
        elapsed_seconds=result.elapsed_seconds,
        shops=result.shops,
        error=result.error,
    )


def build_schedule(
    agents: list[AgentEntry], seeds: list[int], episode_steps: int
) -> list[LeagueMatchSpec]:
    """Build an unordered round robin with paired seats for every seed."""
    return [
        LeagueMatchSpec(seed, agent_a, agent_b, seat, episode_steps)
        for agent_a, agent_b in combinations(agents, 2)
        for seed in seeds
        for seat in (0, 1)
    ]


def standings(
    agents: list[AgentEntry], results: list[LeagueMatchResult]
) -> list[dict[str, object]]:
    """Return symmetric per-agent standings sorted by league rank."""
    rows: dict[str, dict[str, object]] = {
        agent.name: {
            "agent": agent.name,
            "played": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "points": 0.0,
            "money": [],
            "margins": [],
            "errors": 0,
        }
        for agent in agents
    }

    for match in results:
        a = rows[match.agent_a]
        b = rows[match.agent_b]
        a["played"] += 1
        b["played"] += 1
        a["money"].append(match.agent_a_money)
        b["money"].append(match.agent_b_money)
        margin = match.agent_a_money - match.agent_b_money
        a["margins"].append(margin)
        b["margins"].append(-margin)
        a["errors"] += int(match.agent_a_status != "DONE")
        b["errors"] += int(match.agent_b_status != "DONE")

        if match.outcome_for_a == "win":
            a["wins"] += 1
            a["points"] += 1.0
            b["losses"] += 1
        elif match.outcome_for_a == "loss":
            a["losses"] += 1
            b["wins"] += 1
            b["points"] += 1.0
        else:
            a["ties"] += 1
            b["ties"] += 1
            a["points"] += 0.5
            b["points"] += 0.5

    output: list[dict[str, object]] = []
    for row in rows.values():
        played = int(row["played"])
        money = row.pop("money")
        margins = row.pop("margins")
        row["win_rate"] = row["wins"] / played if played else 0.0
        row["point_rate"] = row["points"] / played if played else 0.0
        row["mean_money"] = statistics.fmean(money) if money else 0.0
        row["mean_margin"] = statistics.fmean(margins) if margins else 0.0
        output.append(row)

    output.sort(
        key=lambda row: (
            -float(row["points"]),
            -int(row["wins"]),
            -float(row["mean_margin"]),
            -float(row["mean_money"]),
            str(row["agent"]).casefold(),
        )
    )
    for rank, row in enumerate(output, start=1):
        row["rank"] = rank
    return output


def _print_standings(rows: list[dict[str, object]]) -> None:
    headers = ("RK", "AGENT", "P", "W", "L", "T", "PTS", "WIN%", "AVG$", "AVG +/-", "ERR")
    formatted = []
    for row in rows:
        formatted.append(
            (
                str(row["rank"]),
                str(row["agent"]),
                str(row["played"]),
                str(row["wins"]),
                str(row["losses"]),
                str(row["ties"]),
                f'{float(row["points"]):.1f}',
                f'{100.0 * float(row["win_rate"]):.1f}',
                f'{float(row["mean_money"]):.0f}',
                f'{float(row["mean_margin"]):+.0f}',
                str(row["errors"]),
            )
        )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in formatted))
        for index in range(len(headers))
    ]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in formatted:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _write_json(
    output: Path,
    args: argparse.Namespace,
    agents: list[AgentEntry],
    seeds: list[int],
    rows: list[dict[str, object]],
    results: list[LeagueMatchResult],
    elapsed_seconds: float,
) -> None:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agents": [asdict(agent) for agent in agents],
        "seeds": seeds,
        "episode_steps": args.episode_steps,
        "workers": args.workers,
        "match_count": len(results),
        "elapsed_seconds": elapsed_seconds,
        "standings": rows,
        "matches": [asdict(result) for result in results],
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a seeded round robin; every pair plays both seats per seed."
    )
    parser.add_argument(
        "--agent",
        action="append",
        required=True,
        metavar="NAME=REFERENCE",
        help="repeat for each agent; REFERENCE is a .py file, module, or built-in",
    )
    parser.add_argument("--seeds", default="0:8", help="START:STOP[:STEP] or comma list")
    parser.add_argument("--episode-steps", type=int, default=720)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel processes (default: 1; automatically falls back if unavailable)",
    )
    parser.add_argument("--json", type=Path, dest="json_output", help="optional JSON report path")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        agents = [parse_agent(raw) for raw in args.agent]
        seeds = parse_seeds(args.seeds)
    except ValueError as exc:
        parser.error(str(exc))

    if len(agents) < 2:
        parser.error("at least two --agent entries are required")
    names = [agent.name for agent in agents]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        parser.error(f"duplicate agent names: {', '.join(duplicate_names)}")
    if not seeds:
        parser.error("at least one seed is required")
    if args.episode_steps <= 0:
        parser.error("--episode-steps must be positive")
    if args.workers <= 0:
        parser.error("--workers must be positive")

    schedule = build_schedule(agents, seeds, args.episode_steps)
    started = time.perf_counter()
    if args.workers == 1:
        results = [_play(spec) for spec in schedule]
    else:
        results = []
        try:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(_play, spec) for spec in schedule]
                for future in as_completed(futures):
                    results.append(future.result())
        except PermissionError:
            print("process workers unavailable; falling back to one worker")
            results = [_play(spec) for spec in schedule]

    results.sort(key=lambda row: (row.agent_a.casefold(), row.agent_b.casefold(), row.seed, row.agent_a_seat))
    elapsed_seconds = time.perf_counter() - started
    rows = standings(agents, results)
    _print_standings(rows)
    error_matches = sum(
        result.agent_a_status != "DONE" or result.agent_b_status != "DONE"
        for result in results
    )
    print(
        f"matches={len(results)} seeds={len(seeds)} agents={len(agents)} "
        f"errors={error_matches} elapsed={elapsed_seconds:.1f}s"
    )
    for result in results:
        if result.error:
            print(
                f"seed={result.seed} {result.agent_a} seat={result.agent_a_seat} "
                f"vs {result.agent_b}: ERROR {result.error}"
            )

    if args.json_output:
        _write_json(
            args.json_output,
            args,
            agents,
            seeds,
            rows,
            results,
            elapsed_seconds,
        )
    return 1 if error_matches else 0


if __name__ == "__main__":
    raise SystemExit(main())
