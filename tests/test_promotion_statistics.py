from __future__ import annotations

import math

import pytest

from eval.statistics import (
    lower_tail_cvar,
    stratified_paired_cluster_bootstrap_ci,
    weighted_quantile,
    wilson_interval,
    zero_failure_upper_bound,
)


def test_wilson_interval_matches_known_values_and_handles_no_trials():
    lower, upper = wilson_interval(60, 100)
    assert lower == pytest.approx(0.5020025868)
    assert upper == pytest.approx(0.6905987136)
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_weighted_quantile_uses_weighted_empirical_distribution():
    values = [1, 10, 100]
    weights = [1, 8, 1]
    assert weighted_quantile(values, 0.0, weights) == 1
    assert weighted_quantile(values, 0.5, weights) == 10
    assert weighted_quantile(values, 0.9, weights) == 10
    assert weighted_quantile(values, 1.0, weights) == 100
    assert weighted_quantile([999, 3], 0.5, [0, 1]) == 3


def test_lower_tail_cvar_uses_exact_tail_mass():
    assert lower_tail_cvar([0, 10], 0.5) == 0
    assert lower_tail_cvar([0, 10], 0.75) == pytest.approx(10 / 3)
    assert lower_tail_cvar([0, 10, 100], 0.5, [1, 2, 1]) == pytest.approx(5)
    assert lower_tail_cvar([0, 10, 20], 1.0) == 10


def test_zero_failure_upper_bound_is_exact_and_stable():
    assert zero_failure_upper_bound(0) == 1.0
    assert zero_failure_upper_bound(448) == pytest.approx(0.0066645948)
    assert zero_failure_upper_bound(100, confidence=0.95) == pytest.approx(
        1 - 0.05 ** (1 / 100)
    )


def test_bootstrap_known_constant_difference_has_degenerate_interval():
    interval = stratified_paired_cluster_bootstrap_ci(
        candidate_values=[12, 14, 22, 24],
        incumbent_values=[10, 12, 20, 22],
        strata=["milk", "milk", "wool", "wool"],
        clusters=[1, 2, 1, 2],
        resamples=200,
        seed=7,
    )
    assert interval.estimate == 2
    assert interval.lower == 2
    assert interval.upper == 2


def test_cluster_rows_are_averaged_before_resampling():
    # Ten duplicate seat/trace rows in cluster A must not outweigh cluster B.
    repeated = 10
    interval = stratified_paired_cluster_bootstrap_ci(
        candidate_values=[10] * repeated + [20],
        incumbent_values=[0] * repeated + [20],
        strata=["family"] * (repeated + 1),
        clusters=["A"] * repeated + ["B"],
        resamples=1_000,
        seed=19,
    )
    assert interval.estimate == 5


def test_families_have_equal_weight_regardless_of_match_count():
    # One hundred easy wins are one weak-family mean, not 100 independent votes.
    interval = stratified_paired_cluster_bootstrap_ci(
        candidate_values=[1] * 100 + [-1],
        incumbent_values=[0] * 101,
        strata=["weak"] * 100 + ["strong"],
        clusters=list(range(100)) + ["only-strong-cluster"],
        resamples=200,
        seed=3,
    )
    assert interval.estimate == 0
    assert interval.lower == 0
    assert interval.upper == 0


def test_weak_wins_cannot_mask_a_strong_family_collapse():
    interval = stratified_paired_cluster_bootstrap_ci(
        candidate_values=[1] * 100 + [-3],
        incumbent_values=[0] * 101,
        strata=["weak"] * 100 + ["strong"],
        clusters=list(range(100)) + ["strong-collapse"],
        resamples=200,
        seed=5,
    )
    assert interval.estimate == -1
    assert interval.upper == -1


def test_bootstrap_is_deterministic_for_seed_and_input_order():
    args = {
        "candidate_values": [3, 5, 8, 13, 21, 34],
        "incumbent_values": [2, 6, 6, 15, 18, 30],
        "strata": ["a", "a", "a", "b", "b", "b"],
        "clusters": [1, 2, 3, 1, 2, 3],
        "resamples": 500,
        "seed": 20260820,
    }
    first = stratified_paired_cluster_bootstrap_ci(**args)
    second = stratified_paired_cluster_bootstrap_ci(**args)
    assert first == second


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (wilson_interval, (-1, 10)),
        (wilson_interval, (11, 10)),
        (weighted_quantile, ([], 0.5)),
        (weighted_quantile, ([1], -0.1)),
        (weighted_quantile, ([1, 2], 0.5, [1])),
        (weighted_quantile, ([1, 2], 0.5, [0, 0])),
        (lower_tail_cvar, ([1], 0)),
        (zero_failure_upper_bound, (-1,)),
    ],
)
def test_scalar_helpers_reject_invalid_inputs(function, args):
    with pytest.raises(ValueError):
        function(*args)


def test_bootstrap_rejects_empty_mismatched_nonfinite_and_bad_configuration():
    with pytest.raises(ValueError, match="must not be empty"):
        stratified_paired_cluster_bootstrap_ci([], [], [], [])
    with pytest.raises(ValueError, match="same length"):
        stratified_paired_cluster_bootstrap_ci([1], [], ["a"], [1])
    with pytest.raises(ValueError, match="finite"):
        stratified_paired_cluster_bootstrap_ci(
            [math.nan], [0], ["a"], [1]
        )
    with pytest.raises(ValueError, match="hashable"):
        stratified_paired_cluster_bootstrap_ci([1], [0], [["a"]], [1])
    with pytest.raises(ValueError, match="positive integer"):
        stratified_paired_cluster_bootstrap_ci(
            [1], [0], ["a"], [1], resamples=0
        )
