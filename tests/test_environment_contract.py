from kaggle_environments import make


PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def _scripted_agent(actions):
    def agent(obs):
        return actions.get(obs.get("step", 0), PASS)

    return agent


def test_environment_version_and_smoke_game():
    import kaggle_environments

    assert kaggle_environments.__version__ == "1.32.7"
    env = make("kaggriculture", configuration={"episodeSteps": 8, "seed": 7}, debug=True)
    env.run(["pass", "pass"])
    assert [state.status for state in env.steps[-1]] == ["DONE", "DONE"]
    assert [state.reward for state in env.steps[-1]] == [3000.0, 3000.0]


def test_market_purchase_is_not_available_to_unit_until_next_turn():
    agent = _scripted_agent(
        {
            0: {"farmer": ["PLANT", "CARROT"], "hands": [], "market": [["BUY_SEED", "CARROT", 1]]},
            1: {"farmer": ["PLANT", "CARROT"], "hands": [], "market": []},
            2: {"farmer": ["WATER"], "hands": [], "market": []},
        }
    )
    env = make("kaggriculture", configuration={"episodeSteps": 6, "seed": 3}, debug=True)
    env.run([agent, "pass"])
    first_post_action = env.steps[1][0].observation
    second_post_action = env.steps[2][0].observation
    assert first_post_action.private["seeds"]["CARROT"] == 1
    assert first_post_action.farms[0]["tiles"][4][4] is None
    assert second_post_action.farms[0]["tiles"][4][4]["crop"] == "CARROT"


def test_hire_appears_after_actions_and_can_act_next_turn():
    agent = _scripted_agent(
        {
            0: {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]},
            1: {"farmer": ["PASS"], "hands": [["WEST"]], "market": []},
        }
    )
    env = make("kaggriculture", configuration={"episodeSteps": 5, "seed": 11}, debug=True)
    env.run([agent, "pass"])
    assert env.steps[1][0].observation.farms[0]["hands"] == [[5, 4]]
    assert env.steps[2][0].observation.farms[0]["hands"] == [[4, 4]]


def test_final_action_boundary_is_step_718():
    seen_steps = []

    def recording_agent(obs):
        seen_steps.append(obs.get("step"))
        return PASS

    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 2}, debug=True)
    env.run([recording_agent, "pass"])
    assert seen_steps[0] == 0
    assert seen_steps[-1] == 718
    assert len(seen_steps) == 719


def test_main_py_loads_black_box_and_finishes_in_both_seats():
    env = make("kaggriculture", configuration={"episodeSteps": 48, "seed": 17}, debug=True)
    env.run(["main.py", "main.py"])
    assert [state.status for state in env.steps[-1]] == ["DONE", "DONE"]
    assert all(state.reward is not None for state in env.steps[-1])


def test_full_season_black_box_liquidates_terminal_inventory():
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 20}, debug=True)
    env.run(["main.py", "pass"])
    final = env.steps[-1][0]
    private = final.observation.private
    assert final.status == "DONE"
    assert final.reward > 3000
    assert sum(private["shed"].values()) == 0
    assert sum(sum(inv.values()) for inv in private["inventories"]) == 0
