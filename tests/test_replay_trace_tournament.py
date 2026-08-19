import json

from kaggle_environments import make

from eval.replay_trace_tournament import _trace_agent, run_trace


def test_trace_agent_uses_action_that_produces_the_next_replay_state():
    actions = [
        {"farmer": ["PASS"], "hands": [], "market": []},
        {"farmer": ["NORTH"], "hands": [], "market": [["HIRE"]]},
        {"farmer": ["SOUTH"], "hands": [["PASS"]], "market": []},
    ]
    agent = _trace_agent(actions, turns_per_day=24)

    assert agent({"day": 0, "hour": 0}) == actions[1]
    assert agent({"day": 0, "hour": 1}) == actions[2]


def test_trace_agent_falls_back_to_pass_after_last_action():
    actions = [
        {"farmer": ["PASS"], "hands": [], "market": []},
    ]
    agent = _trace_agent(actions, turns_per_day=24)
    obs = {
        "day": 0,
        "hour": 0,
        "player": 0,
        "farms": [{"hands": [[4, 4], [5, 4]]}],
    }

    assert agent(obs) == {
        "farmer": ["PASS"],
        "hands": [["PASS"], ["PASS"]],
        "market": [],
    }


def test_run_trace_preserves_original_shop_sequence(tmp_path):
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 96, "seed": 712},
        debug=True,
    )
    env.run(["starter", "pass"])
    replay = env.toJSON()
    replay["info"]["EpisodeId"] = 42
    replay["info"]["seed"] = 712
    replay["info"]["TeamNames"] = ["target", "trace"]
    replay_path = tmp_path / "episode-42-replay.json"
    replay_path.write_text(json.dumps(replay))

    candidate = tmp_path / "candidate.py"
    candidate.write_text(
        "def agent(obs):\n"
        "    return {'farmer': ['PASS'], 'hands': [], 'market': []}\n"
    )
    generated_dir = tmp_path / "generated"
    result = run_trace(candidate, replay_path, "target", generated_dir)

    assert not result.error
    generated = json.loads(
        (generated_dir / "episode-42-replay.json").read_text()
    )
    expected = replay["steps"][-1][0]["observation"]["town"]["unlocked_shops"]
    actual = generated["steps"][-1][0]["observation"]["town"]["unlocked_shops"]
    assert actual == expected
