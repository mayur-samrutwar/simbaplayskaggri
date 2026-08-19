"""Dependency-free statistics used by candidate promotion evaluations.

The helpers in this module deliberately make the unit of replication explicit.
In particular, :func:`stratified_paired_cluster_bootstrap_ci` treats the two
seats (and any other repeated rows) from one scenario as a single cluster and
gives every opponent family equal influence.  This prevents a large collection
of correlated or weak-opponent matches from creating spurious precision.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from statistics import NormalDist, fmean
from typing import Hashable, Iterable, Sequence


__all__ = [
    "BootstrapInterval",
    "lower_tail_cvar",
    "stratified_paired_cluster_bootstrap_ci",
    "weighted_quantile",
    "wilson_interval",
    "zero_failure_upper_bound",
]


@dataclass(frozen=True)
class BootstrapInterval:
    """Point estimate and two-sided percentile-bootstrap interval."""

    estimate: float
    lower: float
    upper: float
    confidence: float
    resamples: int


def _validate_probability(value: float, name: str, *, allow_endpoints: bool) -> float:
    try:
        probability = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite probability") from exc
    if not math.isfinite(probability):
        raise ValueError(f"{name} must be a finite probability")
    if allow_endpoints:
        valid = 0.0 <= probability <= 1.0
        interval = "[0, 1]"
    else:
        valid = 0.0 < probability < 1.0
        interval = "(0, 1)"
    if not valid:
        raise ValueError(f"{name} must be in {interval}")
    return probability


def _validate_count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def wilson_interval(
    successes: int,
    trials: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Return the two-sided Wilson score interval for a binomial proportion.

    With no trials there is no information, so the interval is ``(0, 1)``.
    This is preferable to silently reporting a zero-width interval at zero.
    """

    successes = _validate_count(successes, "successes")
    trials = _validate_count(trials, "trials")
    confidence = _validate_probability(confidence, "confidence", allow_endpoints=False)
    if successes > trials:
        raise ValueError("successes cannot exceed trials")
    if trials == 0:
        return 0.0, 1.0

    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    proportion = successes / trials
    z_squared = z * z
    denominator = 1.0 + z_squared / trials
    center = (proportion + z_squared / (2.0 * trials)) / denominator
    half_width = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / trials
            + z_squared / (4.0 * trials * trials)
        )
        / denominator
    )
    return max(0.0, center - half_width), min(1.0, center + half_width)


def _weighted_rows(
    values: Iterable[float], weights: Iterable[float] | None
) -> list[tuple[float, float]]:
    value_rows = list(values)
    weight_rows = [1.0] * len(value_rows) if weights is None else list(weights)
    if not value_rows:
        raise ValueError("values must not be empty")
    if len(value_rows) != len(weight_rows):
        raise ValueError("values and weights must have the same length")

    rows: list[tuple[float, float]] = []
    for raw_value, raw_weight in zip(value_rows, weight_rows, strict=True):
        try:
            value = float(raw_value)
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise ValueError("values and weights must be finite numbers") from exc
        if not math.isfinite(value) or not math.isfinite(weight):
            raise ValueError("values and weights must be finite numbers")
        if weight < 0.0:
            raise ValueError("weights must be non-negative")
        if weight > 0.0:
            rows.append((value, weight))
    if not rows:
        raise ValueError("at least one weight must be positive")
    rows.sort(key=lambda row: row[0])
    return rows


def weighted_quantile(
    values: Iterable[float],
    quantile: float,
    weights: Iterable[float] | None = None,
) -> float:
    """Return the inverse weighted empirical CDF at ``quantile``.

    The result is the smallest observed value whose cumulative positive weight
    reaches the requested fraction.  This non-interpolating definition is
    deterministic, preserves actual observations, and is suitable for risk
    floors such as a weighted tenth percentile.
    """

    quantile = _validate_probability(quantile, "quantile", allow_endpoints=True)
    rows = _weighted_rows(values, weights)
    if quantile == 0.0:
        return rows[0][0]
    if quantile == 1.0:
        return rows[-1][0]

    total_weight = math.fsum(weight for _value, weight in rows)
    threshold = quantile * total_weight
    cumulative = 0.0
    for value, weight in rows:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return rows[-1][0]  # Numerical guard for extreme floating-point weights.


def lower_tail_cvar(
    values: Iterable[float],
    fraction: float = 0.10,
    weights: Iterable[float] | None = None,
) -> float:
    """Return the weighted mean of the lowest ``fraction`` of observations.

    A fractional amount of the boundary observation is included when the tail
    cuts through its weight.  Consequently, unlike averaging values below a
    quantile, this function always represents exactly the requested mass.
    """

    fraction = _validate_probability(fraction, "fraction", allow_endpoints=True)
    if fraction == 0.0:
        raise ValueError("fraction must be in (0, 1]")
    rows = _weighted_rows(values, weights)
    total_weight = math.fsum(weight for _value, weight in rows)
    target_weight = fraction * total_weight
    remaining = target_weight
    weighted_sum = 0.0
    for value, weight in rows:
        used = min(weight, remaining)
        weighted_sum += value * used
        remaining -= used
        if remaining <= 0.0:
            break
    return weighted_sum / target_weight


def zero_failure_upper_bound(trials: int, confidence: float = 0.95) -> float:
    """Return the exact one-sided binomial upper bound after zero failures."""

    trials = _validate_count(trials, "trials")
    confidence = _validate_probability(confidence, "confidence", allow_endpoints=False)
    if trials == 0:
        return 1.0
    # Solve (1 - p) ** trials = 1 - confidence.  expm1 is stable when the
    # resulting failure probability is very small.
    return -math.expm1(math.log1p(-confidence) / trials)


def _linear_quantile(sorted_values: Sequence[float], quantile: float) -> float:
    """Linearly interpolate a quantile of an already sorted finite sample."""

    if len(sorted_values) == 1:
        return sorted_values[0]
    position = quantile * (len(sorted_values) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = position - lower_index
    return (
        sorted_values[lower_index] * (1.0 - fraction)
        + sorted_values[upper_index] * fraction
    )


def _stable_key(value: Hashable) -> tuple[str, str, str]:
    """Provide deterministic ordering for ordinary manifest identifiers."""

    value_type = type(value)
    return value_type.__module__, value_type.__qualname__, repr(value)


def stratified_paired_cluster_bootstrap_ci(
    candidate_values: Iterable[float],
    incumbent_values: Iterable[float],
    strata: Iterable[Hashable],
    clusters: Iterable[Hashable],
    *,
    confidence: float = 0.95,
    resamples: int = 10_000,
    seed: int = 0,
) -> BootstrapInterval:
    """Estimate an equally stratified paired difference and bootstrap its CI.

    Each input row is a paired candidate/incumbent measurement. Rows sharing a
    ``(stratum, cluster)`` key are averaged first; both seats from one seed
    should therefore use the same cluster identifier. Clusters are sampled
    with replacement *within* each stratum. Cluster means are equally weighted
    within a stratum, and stratum means are equally weighted overall.

    This hierarchy deliberately prevents three common errors:

    * treating the two seats from one scenario as independent;
    * giving duplicated rows additional statistical weight; and
    * allowing a family with many weak opponents to swamp a smaller strong
      family.

    The returned interval is the deterministic two-sided percentile interval
    from a local ``random.Random(seed)`` instance.
    """

    candidate_rows = list(candidate_values)
    incumbent_rows = list(incumbent_values)
    stratum_rows = list(strata)
    cluster_rows = list(clusters)
    lengths = {
        len(candidate_rows),
        len(incumbent_rows),
        len(stratum_rows),
        len(cluster_rows),
    }
    if len(lengths) != 1:
        raise ValueError("all bootstrap inputs must have the same length")
    if not candidate_rows:
        raise ValueError("bootstrap inputs must not be empty")
    confidence = _validate_probability(confidence, "confidence", allow_endpoints=False)
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples <= 0:
        raise ValueError("resamples must be a positive integer")

    grouped: dict[Hashable, dict[Hashable, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for raw_candidate, raw_incumbent, stratum, cluster in zip(
        candidate_rows,
        incumbent_rows,
        stratum_rows,
        cluster_rows,
        strict=True,
    ):
        try:
            hash(stratum)
            hash(cluster)
        except TypeError as exc:
            raise ValueError("strata and clusters must contain hashable identifiers") from exc
        try:
            candidate = float(raw_candidate)
            incumbent = float(raw_incumbent)
        except (TypeError, ValueError) as exc:
            raise ValueError("candidate and incumbent values must be finite numbers") from exc
        if not math.isfinite(candidate) or not math.isfinite(incumbent):
            raise ValueError("candidate and incumbent values must be finite numbers")
        grouped[stratum][cluster].append(candidate - incumbent)

    cluster_means_by_stratum: list[list[float]] = []
    for stratum in sorted(grouped, key=_stable_key):
        cluster_means_by_stratum.append(
            [
                fmean(grouped[stratum][cluster])
                for cluster in sorted(grouped[stratum], key=_stable_key)
            ]
        )

    estimate = fmean(fmean(cluster_means) for cluster_means in cluster_means_by_stratum)
    rng = random.Random(seed)
    bootstrap_estimates: list[float] = []
    for _ in range(resamples):
        stratum_estimates = []
        for cluster_means in cluster_means_by_stratum:
            count = len(cluster_means)
            sampled = [cluster_means[rng.randrange(count)] for _ in range(count)]
            stratum_estimates.append(fmean(sampled))
        bootstrap_estimates.append(fmean(stratum_estimates))

    bootstrap_estimates.sort()
    alpha = (1.0 - confidence) / 2.0
    return BootstrapInterval(
        estimate=estimate,
        lower=_linear_quantile(bootstrap_estimates, alpha),
        upper=_linear_quantile(bootstrap_estimates, 1.0 - alpha),
        confidence=confidence,
        resamples=resamples,
    )
