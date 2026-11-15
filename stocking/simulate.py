"""Order-up-to-S stocking of a perishable product, simulated day by day.

The policy: every evening, order enough to bring stock on hand plus stock on
order back up to S. Bags are issued oldest first and thrown away when their
shelf life runs out. Demand that can't be met from stock is a shortage, filled
by an emergency order from outside, so it is counted and not carried over.

One day, in order:
  1. Morning: the order due today arrives, as fresh bags.
  2. Day: demand is issued from stock, oldest bags first.
  3. Evening: bags on their last day are outdated; the rest age one day.
  4. Evening: a new order is placed for S - (on hand + on order).

Demand comes from the Elston & Pickrel model: a Poisson number of transfusion
episodes per day, each needing a logarithmic number of bags.
"""

import math
from dataclasses import dataclass

import numpy as np


def sample_daily_demand(episodes_per_day, theta, n_days, rng):
    """Bags demanded on each of n_days simulated days.

    Each day gets a Poisson number of episodes, and each episode a
    logarithmic(theta) number of bags.
    """
    episodes = rng.poisson(episodes_per_day, n_days)
    sizes = rng.logseries(theta, episodes.sum())
    day_of_episode = np.repeat(np.arange(n_days), episodes)
    return np.bincount(day_of_episode, weights=sizes, minlength=n_days).astype(int)


def daily_demand_pmf(episodes_per_day, theta, max_bags):
    """P(daily demand = k) for k = 0..max_bags under the model.

    A Poisson number of logarithmic episodes is negative binomial, with
    r = -rate / ln(1 - theta) and P(k) = C(k + r - 1, k) (1 - theta)^r theta^k.
    """
    r = -episodes_per_day / math.log(1 - theta)
    k = np.arange(max_bags + 1)
    log_pmf = (
        np.array([math.lgamma(i + r) - math.lgamma(i + 1) for i in k])
        - math.lgamma(r)
        + r * math.log(1 - theta)
        + k * math.log(theta)
    )
    return np.exp(log_pmf)


@dataclass
class Result:
    """Totals for each stock level, over the days after the warm-up."""

    levels: np.ndarray  # the S values tried
    days: int
    demand: int  # bags asked for (the same for every S)
    used: np.ndarray  # bags issued from stock
    short: np.ndarray  # bags that had to come from an emergency order
    short_days: np.ndarray  # days with at least one bag short
    delivered: np.ndarray  # bags received from routine orders
    outdated: np.ndarray  # bags thrown away at the end of their shelf life
    stock_sum: np.ndarray  # morning stock after delivery, added up over days
    start_stock: np.ndarray  # on hand before the first counted delivery
    end_stock: np.ndarray  # on hand after the last evening

    @property
    def short_day_rate(self):
        """Share of days with a shortage."""
        return self.short_days / self.days

    @property
    def short_bag_rate(self):
        """Share of bags demanded that stock could not supply."""
        return self.short / self.demand

    @property
    def outdate_rate(self):
        """Share of delivered bags that were thrown away."""
        return self.outdated / self.delivered

    @property
    def mean_stock(self):
        """Average bags on hand in the morning, after delivery."""
        return self.stock_sum / self.days


def simulate(demand, levels, usable_days=None, lead_time=0, warmup=0):
    """Run the order-up-to-S policy over a daily demand series.

    demand:      bags demanded on each day.
    levels:      the S values to try; all are run together on the same demand.
    usable_days: days a bag can be issued after it arrives (shelf life minus
                 its age on arrival). None means bags never expire.
    lead_time:   extra days an order takes. 0 means ordered in the evening,
                 delivered the next morning.
    warmup:      days at the start to run but leave out of the totals.
    """
    levels = np.asarray(levels, dtype=np.int64)
    n = len(levels)
    expires = usable_days is not None
    # stock[i, a]: bags held under levels[i] with a + 1 days left, so column 0
    # is the oldest. Without expiry one column holds everything.
    stock = np.zeros((n, usable_days if expires else 1), dtype=np.int64)
    stock[:, -1] = levels  # start full of fresh bags
    # pipeline[i, j]: bags arriving in j + 1 mornings' time.
    pipeline = np.zeros((n, lead_time + 1), dtype=np.int64)

    zeros = lambda: np.zeros(n, dtype=np.int64)
    used, short, short_days = zeros(), zeros(), zeros()
    delivered, outdated, stock_sum = zeros(), zeros(), zeros()
    start_stock = zeros()
    total_demand = 0

    for day, d in enumerate(demand):
        counting = day >= warmup
        if day == warmup:
            start_stock = stock.sum(axis=1)

        # 1. Morning delivery.
        arriving = pipeline[:, 0].copy()
        pipeline[:, :-1] = pipeline[:, 1:]
        pipeline[:, -1] = 0
        stock[:, -1] += arriving
        on_hand = stock.sum(axis=1)

        # 2. Issue oldest first: each column gives what is still needed after
        #    the older columns have been emptied.
        older = np.cumsum(stock, axis=1) - stock
        issued = np.minimum(stock, np.clip(d - older, 0, None))
        stock -= issued
        day_used = issued.sum(axis=1)
        day_short = d - day_used

        # 3. Outdate the bags on their last day and age the rest.
        if expires:
            day_outdated = stock[:, 0].copy()
            stock[:, :-1] = stock[:, 1:]
            stock[:, -1] = 0
        else:
            day_outdated = 0

        # 4. Order back up to S.
        pipeline[:, -1] = levels - stock.sum(axis=1) - pipeline.sum(axis=1)

        if counting:
            total_demand += int(d)
            used += day_used
            short += day_short
            short_days += day_short > 0
            delivered += arriving
            outdated += day_outdated
            stock_sum += on_hand

    return Result(
        levels=levels,
        days=len(demand) - warmup,
        demand=total_demand,
        used=used,
        short=short,
        short_days=short_days,
        delivered=delivered,
        outdated=outdated,
        stock_sum=stock_sum,
        start_stock=start_stock,
        end_stock=stock.sum(axis=1),
    )
