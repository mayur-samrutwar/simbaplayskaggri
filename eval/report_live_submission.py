"""Compare a submitted agent's live wins and losses from exact replay analysis."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path


CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
ANIMAL_PRODUCTS = ("EGG", "MILK", "WOOL")
ANIMALS = ("GOOSE", "COW", "SHEEP")
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}


def _ledger_total(player: dict, operation: str, items: tuple[str, ...] | None = None) -> float:
    ledger = player.get("ledger", {}).get(operation, {})
    selected = items if items is not None else tuple(ledger)
    return sum(float(ledger.get(item, {}).get("dollars", 0.0)) for item in selected)


def _sale(player: dict, item: str) -> tuple[float, float]:
    row = player.get("ledger", {}).get("SELL", {}).get(item, {})
    return float(row.get("units", 0.0)), float(row.get("dollars", 0.0))


def _period_cash(player: dict, start_day: int, end_day: int) -> tuple[float, float, float]:
    """Return sales, bought-product spend, and normalized cash for a day range.

    Several live opponents buy and immediately resell large wheat quantities.
    Counting those sales as production inflates revenue, so the normalized
    figure subtracts BUY_PRODUCT spend in the same period.
    """
    sales = 0.0
    bought_products = 0.0
    daily = player.get("daily_ledger", {}) or {}
    for day in range(start_day, end_day):
        ledger = daily.get(str(day), {}) or {}
        sales += sum(float(row.get("dollars", 0.0)) for row in ledger.get("SELL", {}).values())
        bought_products += sum(
            float(row.get("dollars", 0.0))
            for row in ledger.get("BUY_PRODUCT", {}).values()
        )
    return sales, bought_products, sales - bought_products


def _archetype(player: dict) -> str:
    animals = Counter(player.get("max_animals", {}))
    crops = Counter(player.get("max_crops", {}))
    total_animals = sum(animals.values())
    if total_animals <= 2:
        return "crop_only"
    if animals["GOOSE"] >= max(5, animals["COW"] + animals["SHEEP"]):
        return "goose_heavy"
    if animals["COW"] >= 8 and animals["SHEEP"] <= 4:
        return "cow_heavy_hybrid"
    if animals["SHEEP"] >= 8 and animals["COW"] <= 6:
        return "sheep_heavy_hybrid"
    if total_animals >= 10:
        return "balanced_hybrid"
    if sum(crops.values()) >= 35:
        return "crop_heavy_hybrid"
    return "small_hybrid"


def player_metrics(player: dict) -> dict[str, float | int | str]:
    crop_revenue = _ledger_total(player, "SELL", CROPS)
    animal_revenue = _ledger_total(player, "SELL", ANIMAL_PRODUCTS)
    fertilizer_revenue = _ledger_total(player, "SELL", ("FERTILIZER",))
    gross_revenue = crop_revenue + animal_revenue + fertilizer_revenue
    seed_cost = _ledger_total(player, "BUY_SEED")
    animal_cost = _ledger_total(player, "BUY_ANIMAL")
    feed_cost = _ledger_total(player, "BUY_PRODUCT")
    labor_cost = float(player.get("hires", {}).get("cost", 0.0))
    land_cost = float(player.get("land", {}).get("cost", 0.0))
    total_cost = seed_cost + animal_cost + feed_cost + labor_cost + land_cost
    capital_cost = seed_cost + animal_cost + labor_cost + land_cost
    productive_cash = gross_revenue - feed_cost
    net_cash_generation = productive_cash - capital_cost
    terminal_seeds = player.get("terminal", {}).get("seeds", {})
    unused_seed_cost = sum(int(terminal_seeds.get(crop, 0)) * SEED_COST[crop] for crop in CROPS)
    terminal_product_units = sum(
        int(quantity)
        for quantity in (player.get("terminal", {}).get("products", {}) or {}).values()
    )
    requests = Counter(player.get("unit_requests", {}) or {})
    period_metrics = {}
    for label, start_day, end_day in (
        ("early", 0, 10),
        ("middle", 10, 20),
        ("late", 20, 30),
    ):
        sales, bought_products, normalized = _period_cash(player, start_day, end_day)
        period_metrics[f"{label}_sales"] = sales
        period_metrics[f"{label}_bought_products"] = bought_products
        period_metrics[f"{label}_productive_cash"] = normalized
    result: dict[str, float | int | str] = {
        "score": float(player["reward"]),
        "gross_revenue": gross_revenue,
        "productive_cash": productive_cash,
        "net_cash_generation": net_cash_generation,
        "crop_revenue": crop_revenue,
        "animal_revenue": animal_revenue,
        "fertilizer_revenue": fertilizer_revenue,
        "total_cost": total_cost,
        "capital_cost": capital_cost,
        "seed_cost": seed_cost,
        "animal_cost": animal_cost,
        "feed_cost": feed_cost,
        "labor_cost": labor_cost,
        "land_cost": land_cost,
        "hires": int(player.get("hires", {}).get("count", 0)),
        "pass_share": float(player.get("pass_share", 0.0)),
        "move_share": float(player.get("move_share", 0.0)),
        "pass_requests": requests["PASS"],
        "move_requests": sum(requests[direction] for direction in ("NORTH", "SOUTH", "EAST", "WEST")),
        "pickup_requests": requests["PICKUP"],
        "drop_requests": requests["DROP"],
        "plant_requests": requests["PLANT"],
        "water_requests": requests["WATER"],
        "harvest_requests": requests["HARVEST"],
        "feed_requests": requests["FEED"],
        "care_requests": requests["CARE"],
        "fertilize_requests": requests["FERTILIZE"],
        "unused_seed_cost": unused_seed_cost,
        "terminal_product_units": terminal_product_units,
        "terminal_weeds": int(player.get("terminal", {}).get("weeds", 0)),
        "max_weeds": int(player.get("max_weeds", 0)),
        "max_land": int(player.get("max_quadrants", 1)),
        "max_hands": int(player.get("max_hands", 0)),
        "max_animals_total": sum(int(n) for n in player.get("max_animals", {}).values()),
        "max_crops_total": sum(int(n) for n in player.get("max_crops", {}).values()),
        "archetype": _archetype(player),
    }
    result.update(period_metrics)
    for item in (*CROPS, *ANIMAL_PRODUCTS, "FERTILIZER"):
        units, dollars = _sale(player, item)
        key = item.lower()
        result[f"{key}_units"] = units
        result[f"{key}_revenue"] = dollars
        result[f"{key}_price"] = dollars / units if units else 0.0
    for animal in ANIMALS:
        result[f"max_{animal.lower()}"] = int(player.get("max_animals", {}).get(animal, 0))
    for crop in CROPS:
        result[f"max_{crop.lower()}"] = int(player.get("max_crops", {}).get(crop, 0))
    return result


def build_rows(analysis: dict, team: str) -> list[dict]:
    rows = []
    for episode_id, episode in analysis["episodes"].items():
        own = next(player for player in episode["players"] if player["name"] == team)
        opponent = episode["players"][1 - own["seat"]]
        own_metrics = player_metrics(own)
        opponent_metrics = player_metrics(opponent)
        row = {
            "episode_id": int(episode_id),
            "outcome": own["outcome"],
            "seat": own["seat"],
            "opponent": opponent["name"],
            "shops": "|".join(episode["shops"]),
            "margin": float(own["reward"]) - float(opponent["reward"]),
        }
        row.update({f"our_{key}": value for key, value in own_metrics.items()})
        row.update({f"opp_{key}": value for key, value in opponent_metrics.items()})
        rows.append(row)
    return sorted(rows, key=lambda row: row["episode_id"])


def grouped_summary(rows: list[dict]) -> dict:
    numeric_fields = [
        "score", "gross_revenue", "productive_cash", "net_cash_generation",
        "crop_revenue", "animal_revenue", "fertilizer_revenue", "total_cost",
        "capital_cost", "seed_cost", "animal_cost",
        "feed_cost", "labor_cost", "hires", "pass_share", "move_share",
        "pass_requests", "move_requests", "pickup_requests", "drop_requests",
        "plant_requests", "water_requests", "harvest_requests", "feed_requests",
        "care_requests", "fertilize_requests", "unused_seed_cost",
        "terminal_product_units", "terminal_weeds", "max_weeds",
        "max_animals_total", "max_crops_total",
        "early_sales", "early_bought_products", "early_productive_cash",
        "middle_sales", "middle_bought_products", "middle_productive_cash",
        "late_sales", "late_bought_products", "late_productive_cash",
        "wheat_revenue", "carrot_revenue", "tomato_revenue",
        "strawberry_revenue", "melon_revenue", "egg_revenue",
        "milk_revenue", "wool_revenue", "fertilizer_revenue",
    ]
    result = {}
    for outcome in ("win", "loss", "tie", "all"):
        selected = rows if outcome == "all" else [row for row in rows if row["outcome"] == outcome]
        if not selected:
            continue
        group = {
            "matches": len(selected),
            "mean_margin": statistics.fmean(float(row["margin"]) for row in selected),
            "opponent_archetypes": dict(Counter(str(row["opp_archetype"]) for row in selected)),
        }
        for side in ("our", "opp"):
            for field in numeric_fields:
                group[f"{side}_{field}"] = statistics.fmean(
                    float(row[f"{side}_{field}"]) for row in selected
                )
        result[outcome] = group
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--team", default="astro")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    analysis = json.loads(args.analysis.read_text())
    rows = build_rows(analysis, args.team)
    payload = {"team": args.team, "matches": rows, "groups": grouped_summary(rows)}
    if args.output:
        args.output.write_text(json.dumps(payload, indent=2) + "\n")
    if args.csv and rows:
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(payload["groups"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
