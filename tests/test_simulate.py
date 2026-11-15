"""Checks on the stocking simulator: bookkeeping, limits and known answers."""

import numpy as np
import pytest

from stocking.simulate import daily_demand_pmf, sample_daily_demand, simulate

RATE, THETA = 1.02, 0.6  # close to the platelet fit
LEVELS = np.arange(0, 31)


@pytest.fixture(scope="module")
def demand():
    return sample_daily_demand(RATE, THETA, 100_000, np.random.default_rng(1))


def test_demand_mean_matches_model(demand):
    mean_bags_per_episode = -THETA / ((1 - THETA) * np.log(1 - THETA))
    assert demand.mean() == pytest.approx(RATE * mean_bags_per_episode, rel=0.02)


def test_demand_distribution_is_negative_binomial(demand):
    pmf = daily_demand_pmf(RATE, THETA, 200)
    assert pmf.sum() == pytest.approx(1, abs=1e-9)
    observed = np.bincount(demand, minlength=11)[:11] / len(demand)
    assert observed == pytest.approx(pmf[:11], abs=0.005)


@pytest.mark.parametrize("usable_days", [1, 3, 5, None])
@pytest.mark.parametrize("lead_time", [0, 2])
@pytest.mark.parametrize("warmup", [0, 500])
def test_every_bag_is_accounted_for(demand, usable_days, lead_time, warmup):
    r = simulate(demand[:5000], LEVELS, usable_days, lead_time, warmup)
    # Bags in = bags out, and every bag demanded was either issued or short.
    assert np.array_equal(
        r.start_stock + r.delivered, r.used + r.outdated + r.end_stock
    )
    assert np.array_equal(r.used + r.short, np.full(len(LEVELS), r.demand))


def test_position_never_exceeds_level(demand):
    r = simulate(demand[:5000], LEVELS, usable_days=3, lead_time=2)
    assert np.all(r.end_stock <= LEVELS)
    assert np.all(r.delivered >= 0)


def test_no_expiry_means_no_outdates(demand):
    r = simulate(demand, LEVELS, usable_days=None)
    assert not r.outdated.any()


def test_huge_stock_means_no_shortage(demand):
    r = simulate(demand, [10_000], usable_days=3)
    assert r.short[0] == 0


def test_zero_stock_means_everything_short(demand):
    r = simulate(demand, [0], usable_days=3)
    assert r.short[0] == r.demand
    assert r.delivered[0] == 0


def test_shortage_days_match_formula_without_expiry(demand):
    # With next-morning delivery and no expiry, every day starts with S bags,
    # so a day is short exactly when demand exceeds S.
    r = simulate(demand, LEVELS, usable_days=None)
    pmf = daily_demand_pmf(RATE, THETA, 400)
    p_exceeds = 1 - np.cumsum(pmf)[LEVELS]
    assert r.short_day_rate == pytest.approx(p_exceeds, abs=0.005)
    assert np.array_equal(r.stock_sum, LEVELS * r.days)


def test_one_day_life_matches_formula(demand):
    # With one usable day, every morning starts with S fresh bags and whatever
    # is left in the evening is thrown away: outdates = E[max(S - demand, 0)].
    r = simulate(demand, LEVELS, usable_days=1)
    pmf = daily_demand_pmf(RATE, THETA, 400)
    k = np.arange(len(pmf))
    expected = [(np.clip(s - k, 0, None) * pmf).sum() for s in LEVELS]
    assert r.outdated / r.days == pytest.approx(expected, abs=0.02)


def test_longer_life_never_wastes_more(demand):
    short_life = simulate(demand, LEVELS, usable_days=3)
    long_life = simulate(demand, LEVELS, usable_days=5)
    assert np.all(long_life.outdated <= short_life.outdated)
    assert np.all(long_life.short <= short_life.short)


def test_more_stock_never_means_more_shortage(demand):
    r = simulate(demand, LEVELS, usable_days=3)
    assert np.all(np.diff(r.short) <= 0)
    assert np.all(np.diff(r.outdated) >= 0)


def test_hand_worked_example():
    # S = 3, two usable days. Day by day:
    #   day 1: start 3 fresh, demand 1 -> 2 left (1 day left each)
    #   day 2: +1 fresh, demand 0 -> the 2 old bags outdate, 1 left
    #   day 3: +2 fresh, demand 5 -> 3 issued, 2 short, 0 left
    r = simulate([1, 0, 5], [3], usable_days=2)
    assert (r.used[0], r.short[0], r.outdated[0]) == (4, 2, 2)
    assert r.short_days[0] == 1
    assert r.delivered[0] == 3
