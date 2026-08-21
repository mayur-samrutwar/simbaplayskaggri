"""Replay and aggregate cached Kaggriculture leaderboard episodes exactly.

Recorded actions are executed again in the local environment with the replay's
seed.  Small hooks around the environment interpreter produce an exact market
ledger (units and dollars) while ordinary state inspection measures board and
action behavior.  The final rewards are checked against Kaggle's replay before
any metrics are accepted.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kaggle_environments import make
from kaggle_environments.envs.kaggriculture import kaggriculture as kg


ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = tuple(kg.PRODUCTS)
CROPS = tuple(kg.CROPS)
ANIMALS = tuple(kg.ANIMALS)
MOVES = set(kg.FARMER_MOVES)


class Hooks:
    """Temporarily instrument the environment's successful operations."""

    def __init__(self) -> None:
        self.day = 0
        self.hour = 0
        self.market: list[dict[str, Any]] = []
        self.hires: list[dict[str, Any]] = []
        self.land: list[dict[str, Any]] = []
        self.unit_requests: list[Counter[str]] = [Counter(), Counter()]
        self._process_market = kg._process_market
        self._commit = kg._commit_unit
        self._hire = kg._do_hire
        self._land = kg._do_buy_land

    def bind(self, env: Any) -> None:
        self.day = int(env.state[0].observation.day)
        self.hour = int(env.state[0].observation.hour)

    def install(self) -> None:
        owner = self

        def process_market(state, env):
            """Environment market interpreter with an exact per-player ledger."""
            obs0 = state[0].observation
            market = obs0.market
            farms = obs0.farms
            privates = [agent.observation.private for agent in state]
            board_size = int(kg.get(env.configuration, "boardSize", 10))
            max_orders = max(
                1, int(kg.get(env.configuration, "maxMarketOrdersPerTurn", 10))
            )
            hire_mult = int(
                kg.get(env.configuration, "farmHandCostMult", kg.FARM_HAND_COST_MULT)
            )
            shed_capacity = int(kg.get(env.configuration, "shedCapacity", 100))

            queues = []
            for agent in state:
                action = agent.action if isinstance(agent.action, dict) else {}
                orders = action.get("market", []) if isinstance(action, dict) else []
                queues.append(list(orders)[:max_orders] if isinstance(orders, list) else [])

            max_len = max((len(queue) for queue in queues), default=0)
            for order_index in range(max_len):
                order_states = [
                    kg._parse_order(queue[order_index]) if order_index < len(queue) else None
                    for queue in queues
                ]

                for player, order_state in enumerate(order_states):
                    if order_state is None:
                        continue
                    op = order_state["type"]
                    if op == "HIRE":
                        before_money = float(farms[player]["money"])
                        before_hands = len(farms[player]["hands"])
                        owner._hire(
                            farms[player], privates[player], board_size, hire_mult
                        )
                        if len(farms[player]["hands"]) > before_hands:
                            owner.hires.append(
                                {
                                    "player": player,
                                    "day": owner.day,
                                    "hour": owner.hour,
                                    "cost": before_money - float(farms[player]["money"]),
                                }
                            )
                        order_states[player] = None
                    elif op == "BUY_LAND":
                        before_money = float(farms[player]["money"])
                        before_count = len(farms[player]["unlocked_quadrants"])
                        owner._land(farms[player], board_size)
                        if len(farms[player]["unlocked_quadrants"]) > before_count:
                            owner.land.append(
                                {
                                    "player": player,
                                    "day": owner.day,
                                    "hour": owner.hour,
                                    "cost": before_money - float(farms[player]["money"]),
                                }
                            )
                        order_states[player] = None

                iterations = 0
                while True:
                    iterations += 1
                    if iterations >= 100_000:
                        raise RuntimeError("market order exceeded 100,000 unit iterations")
                    quoted = [None, None]
                    for player, order_state in enumerate(order_states):
                        if order_state is None or order_state["remaining"] <= 0:
                            continue
                        op = order_state["type"]
                        item = order_state["item"]
                        if op == "SELL" and item in PRODUCTS:
                            quoted[player] = (
                                op,
                                item,
                                kg.market_price(
                                    item,
                                    market["inventory"][item],
                                    market.get("params"),
                                ),
                                order_state,
                            )
                        elif op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"):
                            quoted[player] = (
                                op,
                                item,
                                kg.market_price(
                                    item,
                                    market["inventory"][item] - 1,
                                    market.get("params"),
                                ),
                                order_state,
                            )
                        elif op == "BUY_SEED" and item in CROPS:
                            quoted[player] = (op, item, kg.CROPS[item]["seed"], order_state)
                        elif op == "BUY_ANIMAL" and item in ANIMALS:
                            quoted[player] = (
                                op,
                                item,
                                kg.ANIMALS[item]["cost"],
                                order_state,
                            )
                        else:
                            order_states[player] = None

                    if all(quote is None for quote in quoted):
                        break

                    committed_any = False
                    for player, quote in enumerate(quoted):
                        if quote is None:
                            continue
                        op, item, price, order_state = quote
                        ok = owner._commit(
                            op,
                            item,
                            price,
                            farms[player],
                            privates[player],
                            market,
                            shed_capacity,
                        )
                        if ok:
                            order_state["remaining"] -= 1
                            committed_any = True
                            owner.market.append(
                                {
                                    "player": player,
                                    "day": owner.day,
                                    "hour": owner.hour,
                                    "op": op,
                                    "item": item,
                                    "price": int(price),
                                }
                            )
                        else:
                            order_states[player] = None
                    if not committed_any:
                        break

                kg._refresh_prices(market)

        kg._process_market = process_market

    def restore(self) -> None:
        kg._process_market = self._process_market


def _tile_counts(farm: Any) -> tuple[Counter[str], Counter[str], int]:
    crops: Counter[str] = Counter()
    animals: Counter[str] = Counter()
    weeds = 0
    for row in farm["tiles"]:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "PLANT":
                crops[tile.get("crop", "UNKNOWN")] += 1
            if tile.get("animal"):
                animals[tile["animal"]] += 1
            if tile.get("kind") == "WEED":
                weeds += 1
    return crops, animals, weeds


def _private_total(private: Any, item: str) -> int:
    return int(private.get("shed", {}).get(item, 0)) + sum(
        int(inventory.get(item, 0)) for inventory in private.get("inventories", [])
    )


def _target_names(manifest: dict[str, Any], directory: Path) -> dict[str, str]:
    result = {}
    for submission_id, episode_ids in manifest["submissions"].items():
        counts: Counter[str] = Counter()
        for episode_id in episode_ids:
            replay = json.loads((directory / f"episode-{episode_id}-replay.json").read_text())
            counts.update(replay["info"]["TeamNames"])
        name, appearances = counts.most_common(1)[0]
        if appearances != len(episode_ids):
            raise RuntimeError(f"could not resolve team for submission {submission_id}: {counts}")
        result[submission_id] = name
    return result


def replay_episode(path: Path) -> dict[str, Any]:
    replay = json.loads(path.read_text())
    config = dict(replay["configuration"])
    config["seed"] = int(replay["info"]["seed"])
    env = make("kaggriculture", configuration=config, debug=True)
    final_public = replay["steps"][-1][0].get("observation", {}) or {}
    shop_sequence = list(
        (final_public.get("town", {}) or {}).get("unlocked_shops", []) or []
    )
    unlock_interval = max(1, int(config.get("townShopUnlockInterval", 3)))
    hooks = Hooks()
    hooks.install()

    maxima = [
        {
            "crops": Counter(),
            "animals": Counter(),
            "hands": 0,
            "quadrants": 1,
            "weeds": 0,
        }
        for _ in range(2)
    ]
    daily_cash: list[dict[str, list[float]]] = [defaultdict(list), defaultdict(list)]
    daily_state: list[dict[str, dict[str, Any]]] = [{}, {}]
    try:
        for replay_step in range(1, len(replay["steps"])):
            hooks.bind(env)
            actions = [replay["steps"][replay_step][player]["action"] for player in range(2)]
            for player, action in enumerate(actions):
                if not isinstance(action, dict):
                    hooks.unit_requests[player]["PASS"] += 1
                    continue
                unit_actions = [action.get("farmer", ["PASS"]), *action.get("hands", [])]
                for unit_action in unit_actions:
                    op = (
                        unit_action[0]
                        if isinstance(unit_action, list) and unit_action
                        else "PASS"
                    )
                    hooks.unit_requests[player][op] += 1
            env.step(actions)
            obs = env.state[0].observation
            # Generated counterfactual traces preserve the original public town
            # even when replacement farm occupancy changes the environment RNG.
            unlocked = min(len(shop_sequence), int(obs.day) // unlock_interval)
            obs.town["unlocked_shops"] = list(shop_sequence[:unlocked])
            for player, farm in enumerate(obs.farms):
                crops, animals, weeds = _tile_counts(farm)
                for crop, count in crops.items():
                    maxima[player]["crops"][crop] = max(maxima[player]["crops"][crop], count)
                for animal, count in animals.items():
                    maxima[player]["animals"][animal] = max(maxima[player]["animals"][animal], count)
                maxima[player]["hands"] = max(maxima[player]["hands"], len(farm["hands"]))
                maxima[player]["quadrants"] = max(
                    maxima[player]["quadrants"], len(farm["unlocked_quadrants"])
                )
                maxima[player]["weeds"] = max(maxima[player]["weeds"], weeds)
                if int(obs.hour) == 0:
                    daily_cash[player][str(int(obs.day))].append(float(farm["money"]))
                    daily_state[player][str(int(obs.day))] = {
                        "money": float(farm["money"]),
                        "crops": dict(crops),
                        "animals": dict(animals),
                        "quadrants": len(farm["unlocked_quadrants"]),
                        "weeds": weeds,
                        "shops": list(obs.town.get("unlocked_shops", [])),
                    }
    finally:
        hooks.restore()

    actual_rewards = [float(state.reward or 0.0) for state in env.state]
    expected_rewards = [float(value) for value in replay["rewards"]]
    if actual_rewards != expected_rewards:
        raise RuntimeError(
            f"replay mismatch {path.name}: expected {expected_rewards}, got {actual_rewards}"
        )

    players = []
    final_obs = env.state[0].observation
    for player in range(2):
        farm = final_obs.farms[player]
        private = env.state[player].observation.private
        crops, animals, weeds = _tile_counts(farm)
        market_rows = [row for row in hooks.market if row["player"] == player]
        ledger: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: {"units": 0, "dollars": 0.0})
        )
        opening: dict[str, Counter[str]] = defaultdict(Counter)
        daily_ledger: dict[str, dict[str, dict[str, dict[str, float]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: {"units": 0, "dollars": 0.0}))
        )
        for row in market_rows:
            entry = ledger[row["op"]][row["item"]]
            entry["units"] += 1
            entry["dollars"] += row["price"]
            daily_entry = daily_ledger[str(row["day"])][row["op"]][row["item"]]
            daily_entry["units"] += 1
            daily_entry["dollars"] += row["price"]
            if row["day"] == 0:
                opening[row["op"]][row["item"]] += 1

        requests = hooks.unit_requests[player]
        unit_total = sum(requests.values())
        terminal_products = {item: _private_total(private, item) for item in PRODUCTS}
        terminal_animals = {item: _private_total(private, item) for item in ANIMALS}
        players.append(
            {
                "name": replay["info"]["TeamNames"][player],
                "seat": player,
                "reward": actual_rewards[player],
                "opponent_reward": actual_rewards[1 - player],
                "outcome": (
                    "win"
                    if actual_rewards[player] > actual_rewards[1 - player]
                    else "loss"
                    if actual_rewards[player] < actual_rewards[1 - player]
                    else "tie"
                ),
                "ledger": ledger,
                "opening": opening,
                "hires": {
                    "count": sum(row["player"] == player for row in hooks.hires),
                    "cost": sum(row["cost"] for row in hooks.hires if row["player"] == player),
                },
                "land": {
                    "count": sum(row["player"] == player for row in hooks.land),
                    "cost": sum(row["cost"] for row in hooks.land if row["player"] == player),
                },
                "max_crops": dict(maxima[player]["crops"]),
                "max_animals": dict(maxima[player]["animals"]),
                "max_hands": maxima[player]["hands"],
                "max_quadrants": maxima[player]["quadrants"],
                "max_weeds": maxima[player]["weeds"],
                "unit_requests": dict(requests),
                "pass_share": requests.get("PASS", 0) / unit_total if unit_total else 0.0,
                "move_share": sum(requests.get(move, 0) for move in MOVES) / unit_total
                if unit_total
                else 0.0,
                "terminal": {
                    "products": terminal_products,
                    "animals": terminal_animals,
                    "seeds": dict(private.get("seeds", {})),
                    "crops": dict(crops),
                    "board_animals": dict(animals),
                    "weeds": weeds,
                },
                "daily_cash": {
                    day: values[-1] for day, values in daily_cash[player].items()
                },
                "daily_state": daily_state[player],
                "daily_ledger": daily_ledger,
            }
        )

    return {
        "episode_id": int(replay["info"]["EpisodeId"]),
        "seed": int(replay["info"]["seed"]),
        "shops": list(final_obs.town.get("unlocked_shops", [])),
        "players": players,
    }


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def aggregate_submission(
    submission_id: str,
    team_name: str,
    episode_ids: list[int],
    episodes: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for episode_id in episode_ids:
        episode = episodes[episode_id]
        player = next(player for player in episode["players"] if player["name"] == team_name)
        rows.append({"episode": episode, "player": player})

    result: dict[str, Any] = {
        "submission_id": int(submission_id),
        "team": team_name,
        "matches": len(rows),
        "wins": sum(row["player"]["outcome"] == "win" for row in rows),
        "losses": sum(row["player"]["outcome"] == "loss" for row in rows),
        "ties": sum(row["player"]["outcome"] == "tie" for row in rows),
        "mean_score": _mean([row["player"]["reward"] for row in rows]),
        "median_score": statistics.median(row["player"]["reward"] for row in rows),
        "mean_margin": _mean(
            [row["player"]["reward"] - row["player"]["opponent_reward"] for row in rows]
        ),
        "mean_pass_share": _mean([row["player"]["pass_share"] for row in rows]),
        "mean_move_share": _mean([row["player"]["move_share"] for row in rows]),
        "mean_hires": _mean([row["player"]["hires"]["count"] for row in rows]),
        "mean_hire_cost": _mean([row["player"]["hires"]["cost"] for row in rows]),
        "mean_land_buys": _mean([row["player"]["land"]["count"] for row in rows]),
        "mean_terminal_units": _mean(
            [
                sum(row["player"]["terminal"]["products"].values())
                + sum(row["player"]["terminal"]["animals"].values())
                for row in rows
            ]
        ),
        "matches_detail": [
            {
                "episode_id": row["episode"]["episode_id"],
                "opponent": row["episode"]["players"][1 - row["player"]["seat"]]["name"],
                "seat": row["player"]["seat"],
                "score": row["player"]["reward"],
                "opponent_score": row["player"]["opponent_reward"],
                "outcome": row["player"]["outcome"],
                "shops": row["episode"]["shops"],
            }
            for row in rows
        ],
    }

    for field, keys in (("sales", PRODUCTS), ("animal_buys", ANIMALS), ("seed_buys", CROPS)):
        op = {"sales": "SELL", "animal_buys": "BUY_ANIMAL", "seed_buys": "BUY_SEED"}[field]
        result[field] = {}
        for item in keys:
            units = [
                row["player"]["ledger"].get(op, {}).get(item, {}).get("units", 0)
                for row in rows
            ]
            dollars = [
                row["player"]["ledger"].get(op, {}).get(item, {}).get("dollars", 0.0)
                for row in rows
            ]
            result[field][item] = {
                "mean_units": _mean(units),
                "mean_dollars": _mean(dollars),
                "total_units": sum(units),
                "total_dollars": sum(dollars),
            }

    result["mean_max_crops"] = {
        crop: _mean([row["player"]["max_crops"].get(crop, 0) for row in rows])
        for crop in CROPS
    }
    result["mean_max_animals"] = {
        animal: _mean([row["player"]["max_animals"].get(animal, 0) for row in rows])
        for animal in ANIMALS
    }
    result["mean_opening_buys"] = {}
    for op, items in (("BUY_SEED", CROPS), ("BUY_ANIMAL", ANIMALS), ("BUY_PRODUCT", PRODUCTS)):
        result["mean_opening_buys"][op] = {
            item: _mean([row["player"]["opening"].get(op, {}).get(item, 0) for row in rows])
            for item in items
        }
    return result


def write_summary_csv(path: Path, submissions: list[dict[str, Any]]) -> None:
    rows = []
    for summary in submissions:
        sales = summary["sales"]
        rows.append(
            {
                "submission_id": summary["submission_id"],
                "team": summary["team"],
                "wins": summary["wins"],
                "losses": summary["losses"],
                "mean_score": round(summary["mean_score"], 1),
                "mean_margin": round(summary["mean_margin"], 1),
                "mean_pass_share": round(summary["mean_pass_share"], 4),
                "mean_hires": round(summary["mean_hires"], 1),
                "mean_land_buys": round(summary["mean_land_buys"], 2),
                "crop_revenue": round(
                    sum(sales[item]["mean_dollars"] for item in CROPS), 1
                ),
                "animal_revenue": round(
                    sum(sales[item]["mean_dollars"] for item in ("EGG", "MILK", "WOOL")), 1
                ),
                "fertilizer_revenue": round(sales["FERTILIZER"]["mean_dollars"], 1),
                "mean_terminal_units": round(summary["mean_terminal_units"], 1),
            }
        )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory", type=Path, default=ROOT / "replays" / "leaderboard"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    output = (args.output or directory / "analysis.json").resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    target_names = _target_names(manifest, directory)

    episodes: dict[int, dict[str, Any]] = {}
    unique_ids = manifest["unique_episode_ids"]
    for index, episode_id in enumerate(unique_ids, start=1):
        episodes[episode_id] = replay_episode(
            directory / f"episode-{episode_id}-replay.json"
        )
        print(f"analyzed {index}/{len(unique_ids)}: episode {episode_id}", flush=True)

    submissions = [
        aggregate_submission(
            submission_id,
            target_names[submission_id],
            episode_ids,
            episodes,
        )
        for submission_id, episode_ids in manifest["submissions"].items()
    ]
    result = {
        "target_names": target_names,
        "submissions": submissions,
        "episodes": episodes,
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    write_summary_csv(output.with_name("summary.csv"), submissions)
    print(f"analysis: {output}")
    print(f"summary: {output.with_name('summary.csv')}")


if __name__ == "__main__":
    main()
