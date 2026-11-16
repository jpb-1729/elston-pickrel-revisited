"""Checks on the optimal-policy solver: known answers, limits and the simulator."""

import numpy as np
import pytest

from stocking.optimal import (
    build_model,
    demand_pmf,
    evaluate,
    loss,
    order_up_to,
    solve,
    visit_shares,
)
from stocking.simulate import sample_daily_demand, simulate

RATE, THETA = 1.02, 0.6  # close to the platelet fit
MAX_STOCK = 16


@pytest.fixture(scope="module")
def pmf():
    return demand_pmf(RATE, THETA)


@pytest.fixture(scope="module")
def model(pmf):
    return build_model(pmf, usable_days=3, max_stock=MAX_STOCK)


def test_pmf_sums_to_one(pmf):
    assert pmf.sum() == pytest.approx(1, abs=1e-12)


def test_hand_worked_step(model):
    # Hold 2 bags expiring tonight and 1 with a day more; order 3; demand 4.
    # Issued oldest first: 2 + 1 + 1 fresh. Nothing is short or outdated, and
    # the 2 fresh bags left have two days left tomorrow evening.
    start = model.index([2, 1])
    assert model.next_state[start, 3, 4] == model.index([0, 2])
    # Demand 1 instead: 1 old bag is issued, the other is outdated.
    assert model.next_state[start, 3, 1] == model.index([1, 3])
    # Demand 8: all 6 bags go and nothing is left.
    assert model.next_state[start, 3, 8] == model.index([0, 0])


def test_expected_short_and_outdated_by_hand(model, pmf):
    # From an empty shelf, ordering q: short = E[max(D - q, 0)], and fresh
    # bags can't be outdated on their first day.
    d = np.arange(len(pmf))
    empty = model.index([0, 0])
    for q in (0, 3, 7):
        assert model.short[empty, q] == pytest.approx(
            (np.clip(d - q, 0, None) * pmf).sum()
        )
        assert model.outdated[empty, q] == 0


def test_orders_past_the_cap_are_not_allowed(model):
    assert model.allowed[model.index([0, 0])].all()
    full = model.index([MAX_STOCK, 0])
    assert model.allowed[full].tolist() == [True] + [False] * MAX_STOCK
    with pytest.raises(ValueError):
        evaluate(model, loss(model), np.full(len(model.states), 1))


def test_one_day_life_is_the_newsvendor(pmf):
    # With one usable day every morning starts with just the order q, so the
    # best q is the smallest with P(D <= q) >= 25 / (25 + 4).
    model = build_model(pmf, usable_days=1, max_stock=MAX_STOCK)
    cost, policy = solve(model, loss(model))
    d = np.arange(len(pmf))
    q = int(np.argmax(np.cumsum(pmf) >= 25 / 29))
    expected = (25 * np.clip(d - q, 0, None) + 4 * np.clip(q - d, 0, None)) @ pmf
    assert policy.tolist() == [q]
    assert cost == pytest.approx(expected)


def test_order_up_to_matches_the_simulator(model):
    demand = sample_daily_demand(RATE, THETA, 400_000, np.random.default_rng(7))
    levels = [3, 6, 9]
    r = simulate(demand, levels, usable_days=3, warmup=365)
    for i, level in enumerate(levels):
        policy = order_up_to(model, level)
        short = evaluate(model, model.short, policy)
        outdated = evaluate(model, model.outdated, policy)
        assert short == pytest.approx(r.short[i] / r.days, rel=0.05)
        assert outdated == pytest.approx(r.outdated[i] / r.days, rel=0.05)


def test_optimal_is_never_worse_than_any_order_up_to(model):
    cost = loss(model)
    best, _ = solve(model, cost)
    for level in range(MAX_STOCK + 1):
        assert best <= evaluate(model, cost, order_up_to(model, level)) + 1e-7


def test_solve_and_evaluate_agree(model):
    cost = loss(model)
    best, policy = solve(model, cost)
    assert evaluate(model, cost, policy) == pytest.approx(best)
    parts = 25 * evaluate(model, model.short, policy) + 4 * evaluate(
        model, model.outdated, policy
    )
    assert parts == pytest.approx(best)


def test_raising_the_cap_changes_nothing(model, pmf):
    bigger = build_model(pmf, usable_days=3, max_stock=MAX_STOCK + 4)
    assert solve(bigger, loss(bigger))[0] == pytest.approx(solve(model, loss(model))[0])


def test_longer_life_never_costs_more(model, pmf):
    shorter = build_model(pmf, usable_days=2, max_stock=MAX_STOCK)
    assert solve(model, loss(model))[0] <= solve(shorter, loss(shorter))[0]


def test_free_shortage_means_order_nothing(model):
    cost, policy = solve(model, loss(model, short_cost=0))
    assert cost == pytest.approx(0)
    assert policy[model.index([0, 0])] == 0


def test_free_outdating_means_fill_the_shelf(model, pmf):
    # With nothing to lose from waste, hold the cap: short = E[max(D - cap, 0)].
    cost, policy = solve(model, loss(model, short_cost=1, outdate_cost=0))
    d = np.arange(len(pmf))
    assert cost == pytest.approx((np.clip(d - MAX_STOCK, 0, None) * pmf).sum())
    assert policy[model.index([0, 0])] == MAX_STOCK


def test_older_stock_means_a_bigger_order(model):
    # Same number of bags on hand, but older: never order less.
    _, policy = solve(model, loss(model))
    for bags in range(1, 9):
        orders = [policy[model.index([old, bags - old])] for old in range(bags + 1)]
        assert orders == sorted(orders)


def test_visit_shares_give_the_same_averages(model):
    # Averaging tomorrow's shortage over where the evenings are spent is the
    # long-run shortage per day.
    policy = order_up_to(model, 6)
    shares = visit_shares(model, policy)
    rows = np.arange(len(policy))
    assert shares.sum() == pytest.approx(1)
    assert shares @ model.short[rows, policy] == pytest.approx(
        evaluate(model, model.short, policy)
    )
    # Order-up-to-6 never holds more than 6 bags overnight.
    assert shares[model.total > 6].sum() == pytest.approx(0, abs=1e-9)
