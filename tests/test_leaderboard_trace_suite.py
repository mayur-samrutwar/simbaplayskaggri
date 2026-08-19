from __future__ import annotations

import json

from eval.leaderboard_trace_suite import load_cases


def test_load_cases_replaces_target_opponent(tmp_path):
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    (replay_dir / "episode-42-replay.json").write_text(
        json.dumps({"info": {"TeamNames": ["target", "historical opponent"]}})
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"submissions": {"123": [42]}}))
    analysis = tmp_path / "analysis.json"
    analysis.write_text(json.dumps({"target_names": {"123": "target"}}))

    assert load_cases(manifest, analysis, replay_dir) == [
        ("123", "historical opponent", replay_dir / "episode-42-replay.json")
    ]


def test_load_cases_filters_and_limits(tmp_path):
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    for episode_id in (1, 2, 3):
        (replay_dir / f"episode-{episode_id}-replay.json").write_text(
            json.dumps({"info": {"TeamNames": ["target", "other"]}})
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"submissions": {"123": [1, 2], "456": [3]}})
    )
    analysis = tmp_path / "analysis.json"
    analysis.write_text(
        json.dumps({"target_names": {"123": "target", "456": "target"}})
    )

    cases = load_cases(
        manifest,
        analysis,
        replay_dir,
        submission_ids={"123"},
        limit_per_team=1,
    )
    assert cases == [("123", "other", replay_dir / "episode-1-replay.json")]
