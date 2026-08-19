from __future__ import annotations

import pytest
from kaggle_environments.envs.kaggriculture import kaggriculture as kaggriculture_env

from eval.scenarios import force_shop_sequence, run_fixed_shop_scenario


SHOPS = ("YARN_STORE", "YARN_STORE", "PIZZA_SHOP")


def test_fixed_sequence_is_exact_at_each_shop_unlock_boundary():
    result = run_fixed_shop_scenario(
        "pass",
        "pass",
        seed=712,
        shops=SHOPS,
        candidate_seat=0,
        episode_steps=220,
    )
    history = dict(result.shop_history)

    assert history[0] == ()
    assert history[2] == ()
    assert history[3] == ("YARN_STORE",)
    assert history[5] == ("YARN_STORE",)
    assert history[6] == ("YARN_STORE", "YARN_STORE")
    assert history[9] == SHOPS
    assert result.observed_shops == SHOPS


def test_fixed_scenario_repeats_deterministically():
    kwargs = {
        "seed": 144,
        "shops": ("SMOOTHIE_SHOP", "FARMERS_MARKET"),
        "candidate_seat": 0,
        "episode_steps": 168,
    }
    first = run_fixed_shop_scenario("starter", "pass", **kwargs)
    second = run_fixed_shop_scenario("starter", "pass", **kwargs)

    assert first == second


@pytest.mark.parametrize("candidate_seat", [0, 1])
def test_runner_maps_candidate_results_from_both_seats(candidate_seat):
    result = run_fixed_shop_scenario(
        "starter",
        "pass",
        seed=31,
        shops=("BAKERY", "ICE_CREAM_SHOP"),
        candidate_seat=candidate_seat,
        episode_steps=120,
    )

    assert result.candidate_seat == candidate_seat
    assert result.candidate_status == "DONE"
    assert result.opponent_status == "DONE"
    assert result.candidate_money > result.opponent_money
    assert result.outcome == "win"
    assert result.observed_shops == ("BAKERY",)


def test_shop_hook_is_restored_after_normal_exit_and_exception():
    original = kaggriculture_env._end_of_day
    with force_shop_sequence(("PET_CAFE",)):
        assert kaggriculture_env._end_of_day is not original
    assert kaggriculture_env._end_of_day is original

    with pytest.raises(RuntimeError, match="deliberate"):
        with force_shop_sequence(("PET_CAFE",)):
            assert kaggriculture_env._end_of_day is not original
            raise RuntimeError("deliberate")
    assert kaggriculture_env._end_of_day is original


def test_nested_shop_hooks_restore_the_enclosing_hook():
    original = kaggriculture_env._end_of_day
    with force_shop_sequence(("BAKERY",)):
        outer = kaggriculture_env._end_of_day
        with force_shop_sequence(("YARN_STORE",)):
            assert kaggriculture_env._end_of_day is not outer
        assert kaggriculture_env._end_of_day is outer
    assert kaggriculture_env._end_of_day is original


@pytest.mark.parametrize(
    "kwargs",
    [
        {"candidate_seat": 2, "shops": ()},
        {"candidate_seat": 0, "shops": ("NOT_A_SHOP",)},
        {"candidate_seat": 0, "shops": ("BAKERY",) * 9},
    ],
)
def test_runner_rejects_invalid_seats_and_shop_sequences(kwargs):
    with pytest.raises(ValueError):
        run_fixed_shop_scenario(
            "pass",
            "pass",
            seed=1,
            episode_steps=8,
            **kwargs,
        )
