import json
from types import SimpleNamespace

from eval.tournament import MatchResult, _write_results, parse_seeds, summarize


def test_parse_seed_ranges_and_lists():
    assert parse_seeds("0:4") == [0, 1, 2, 3]
    assert parse_seeds("1:8:3") == [1, 4, 7]
    assert parse_seeds("4, 9,12") == [4, 9, 12]


def test_summary_prioritizes_outcomes():
    rows = [
        MatchResult(0, 0, 4_000, 3_000, "DONE", "DONE", "win", 0.1, ""),
        MatchResult(0, 1, 2_999, 3_000, "DONE", "DONE", "loss", 0.1, ""),
        MatchResult(1, 0, 3_000, 3_000, "DONE", "DONE", "tie", 0.1, ""),
    ]
    summary = summarize(rows)
    assert summary["win_rate"] == 1 / 3
    assert summary["non_loss_rate"] == 2 / 3
    assert summary["mean_margin"] == 333


def test_result_manifest_keeps_portable_agent_references(tmp_path):
    result = MatchResult(0, 0, 4_000, 3_000, "DONE", "DONE", "win", 0.1, "")
    args = SimpleNamespace(
        candidate="candidates/champion_strawberry.py",
        opponent="starter",
        seeds="0",
        episode_steps=720,
        workers=1,
    )

    _write_results(tmp_path, [result], summarize([result]), args)

    manifest = json.loads((tmp_path / "summary.json").read_text())
    assert manifest["candidate"] == "candidates/champion_strawberry.py"
    assert manifest["opponent"] == "starter"
