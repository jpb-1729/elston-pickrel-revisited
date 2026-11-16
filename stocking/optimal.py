"""How far is order-up-to-S from the best possible ordering policy?

Order-up-to-S looks only at the total stock. The best policy may also look at
how old the stock is. Here the stocking problem is written as a Markov decision
process and solved exactly, so the two can be compared.

The day runs as in simulate.py, with next-morning delivery:
  state:  each evening, after outdating, the bags held with 1, 2, ...,
          usable_days - 1 days left (oldest first).
  action: how many bags to order. They arrive fresh the next morning.
  then:   demand is issued oldest first, what can't be met is short (and not
          carried over), bags on their last day are outdated, the rest age.
  cost:   SHORT_COST per bag short plus OUTDATE_COST per bag outdated, the
          25:4 ratio of Elston & Pickrel (1963).

The answer is exact for this model, not for a real blood bank: demand is the
fitted model with every day independent, and stock is capped at MAX_STOCK
bags (raising the cap does not change the results).

Writes stocking/optimal.csv, stocking/platelets_optimal.png (the loss for
every S against the best possible), stocking/platelets_orders.png (one shelf
total, to show that the best policy looks at the age of the stock) and
stocking/platelets_orders_grid.png (its order for every shelf).
Run:  uv run python stocking/optimal.py
"""

import itertools
import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from stocking.simulate import daily_demand_pmf

HERE = Path(__file__).parent
SHORT_COST, OUTDATE_COST = 25.0, 4.0
MAX_STOCK = 20  # most bags held after ordering; far above any sensible level
MAX_DEMAND = 80  # daily demand above this is counted as this
# usable_days is shelf life minus age on arrival, as in run.py.
SCENARIOS = [("3 usable days", 3), ("5 usable days", 5)]
LEVELS = range(15)  # the S values compared with the optimal policy
PLOT_LEVELS = (3, 12)  # the S values drawn; outside these the loss runs off the chart

# Shortage and outdating get their own colours, as blue and orange already
# mean the two shelf lives in platelets_tradeoff.png.
VIOLET, YELLOW = "#6250d6", "#eda100"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
BLUE = "#2a78d6"  # bags ordered
OLD, YOUNG = "#52514e", "#d3d2cc"  # bags on the shelf with one and two days left
# One blue, light to dark, for an order of 0, 1, 2, ... bags.
ORDER_BLUES = [
    "#cde2fb",
    "#9ec5f4",
    "#6da7ec",
    "#3987e5",
    "#256abf",
    "#184f95",
    "#0d366b",
]


@dataclass
class Model:
    """The stocking problem as tables, one row per state.

    An order is allowed when it keeps the total stock within max_stock.
    """

    states: np.ndarray  # [state, age]: bags with age + 1 days left
    pmf: np.ndarray  # P(daily demand = d)
    allowed: np.ndarray  # [state, order]: may this order be placed?
    next_state: np.ndarray  # [state, order, demand]: row of the next state
    short: np.ndarray  # [state, order]: expected bags short tomorrow
    outdated: np.ndarray  # [state, order]: expected bags outdated tomorrow

    @property
    def total(self):
        """Bags on hand in each state."""
        return self.states.sum(axis=1)

    def index(self, state):
        """The row of a state, given as bags with 1, 2, ... days left."""
        return int(np.flatnonzero((self.states == state).all(axis=1))[0])


def demand_pmf(episodes_per_day, theta, max_bags=MAX_DEMAND):
    """P(daily demand = d) for d = 0..max_bags, with the tail added to the end."""
    pmf = daily_demand_pmf(episodes_per_day, theta, max_bags)
    pmf[-1] += 1 - pmf.sum()
    return pmf


def build_model(pmf, usable_days, max_stock=MAX_STOCK):
    """Work out what every order does in every state, for every demand."""
    ages = usable_days - 1
    shelves = [
        s
        for s in itertools.product(range(max_stock + 1), repeat=ages)
        if sum(s) <= max_stock
    ]
    # With one usable day nothing is kept overnight: one state, no columns.
    states = np.array(shelves, dtype=np.int64).reshape(len(shelves), ages)
    n, orders = len(states), max_stock + 1
    demand = np.arange(len(pmf))

    # Give each state a single number so the next state's row can be looked up.
    place = (max_stock + 1) ** np.arange(ages)
    row_of = np.full((max_stock + 1) ** ages, -1, dtype=np.int32)
    row_of[states @ place] = np.arange(n)

    total = states.sum(axis=1)
    allowed = total[:, None] + np.arange(orders) <= max_stock
    next_state = np.zeros((n, orders, len(pmf)), dtype=np.int32)
    short = np.zeros((n, orders))
    outdated = np.zeros((n, orders))
    for q in range(orders):
        # Tomorrow's shelf, oldest first, with the q fresh bags at the end.
        stock = np.column_stack([states, np.full(n, q)])[:, None, :]
        # Issue oldest first, as in simulate.py.
        older = np.cumsum(stock, axis=2) - stock
        issued = np.minimum(stock, np.clip(demand[None, :, None] - older, 0, None))
        left = stock - issued
        next_state[:, q, :] = row_of[left[:, :, 1:] @ place]
        short[:, q] = (demand[None, :] - issued.sum(axis=2)) @ pmf
        outdated[:, q] = left[:, :, 0] @ pmf
    return Model(states, pmf, allowed, next_state, short, outdated)


def loss(model, short_cost=SHORT_COST, outdate_cost=OUTDATE_COST):
    """Expected cost of tomorrow for each state and order."""
    return short_cost * model.short + outdate_cost * model.outdated


def order_up_to(model, level):
    """The order-up-to-S policy: the order placed in each state."""
    return np.clip(level - model.total, 0, None)


def _iterate(model, cost, policy, tol):
    """Relative value iteration. Returns the average per day and the policy."""
    rows = np.arange(len(model.states))
    value = np.zeros(len(rows))
    while True:
        if policy is None:
            ahead = cost + value[model.next_state] @ model.pmf
            ahead = np.where(model.allowed, ahead, np.inf)
            new = ahead.min(axis=1)
        else:
            new = cost[rows, policy] + value[model.next_state[rows, policy]] @ model.pmf
        change = new - value
        value = new - new[0]
        if change.max() - change.min() < tol:
            break
    best = ahead.argmin(axis=1) if policy is None else policy
    return (change.max() + change.min()) / 2, best


def solve(model, cost, tol=1e-9):
    """The policy with the lowest long-run cost per day.

    cost is [state, order], as returned by loss(). Returns (cost per day, the
    order to place in each state).
    """
    return _iterate(model, cost, None, tol)


def evaluate(model, cost, policy, tol=1e-9):
    """The long-run average of cost per day under a given policy."""
    if not model.allowed[np.arange(len(policy)), policy].all():
        raise ValueError("the policy orders past max_stock in some state")
    return _iterate(model, cost, np.asarray(policy), tol)[0]


def visit_shares(model, policy, tol=1e-12):
    """The long-run share of evenings spent in each state under a policy."""
    rows = np.arange(len(model.states))
    step = np.zeros((len(rows), len(rows)))
    np.add.at(
        step,
        (rows[:, None], model.next_state[rows, policy]),
        np.broadcast_to(model.pmf, (len(rows), len(model.pmf))),
    )
    share = np.full(len(rows), 1 / len(rows))
    while True:
        new = share @ step
        if np.abs(new - share).sum() < tol:
            return new
        share = new


def compare(model, levels):
    """Yearly results for every order-up-to-S level and for the best policy.

    Returns the table rows and the best policy's order for each state.
    """
    _, best_policy = solve(model, loss(model))
    policies = [("order up to S", s, order_up_to(model, s)) for s in levels]
    policies.append(("optimal", None, best_policy))
    rows = []
    for name, s, policy in policies:
        short = 365 * evaluate(model, model.short, policy)
        outdated = 365 * evaluate(model, model.outdated, policy)
        rows.append(
            {
                "policy": name,
                "stock_level": s,
                "loss_per_year": SHORT_COST * short + OUTDATE_COST * outdated,
                "short_bags_per_year": short,
                "outdated_per_year": outdated,
            }
        )
    return rows, best_policy


def headline(table):
    """Per scenario: the best order-up-to-S row, then the optimal row."""
    picks = []
    for _, group in table.groupby("scenario", sort=False):
        levels = group[group["policy"] == "order up to S"]
        picks.append(levels.loc[[levels["loss_per_year"].idxmin()]])
        picks.append(group[group["policy"] == "optimal"])
    return pd.concat(picks, ignore_index=True)


def plot_platelets(table, path):
    """Loss for every S, split into shortage and outdating, against the floor.

    The dashed line is the optimal policy's loss: no ordering rule can get
    below it, so the space between it and the lowest bar is all there is to
    gain from a smarter rule.
    """
    dollars = FuncFormatter(lambda v, _: f"\\${v:,.0f}")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.8), sharey=True, facecolor=SURFACE)
    for ax, (label, group) in zip(
        axes, table.groupby("scenario", sort=False), strict=True
    ):
        floor = group.loc[group["policy"] == "optimal", "loss_per_year"].iloc[0]
        levels = group[group["stock_level"].between(*PLOT_LEVELS)]
        s = levels["stock_level"].astype(int).to_numpy()
        short = SHORT_COST * levels["short_bags_per_year"].to_numpy()
        outdated = OUTDATE_COST * levels["outdated_per_year"].to_numpy()
        total = short + outdated
        best = total.argmin()

        ax.set_facecolor(SURFACE)
        bar = {"width": 0.62, "edgecolor": SURFACE, "linewidth": 1.5, "zorder": 3}
        ax.bar(s, short, color=VIOLET, **bar)
        ax.bar(s, outdated, bottom=short, color=YELLOW, **bar)
        ax.axhline(floor, color=INK, lw=1.3, ls=(0, (4, 3)), zorder=4)

        gap = total[best] - floor
        ax.annotate(
            f"Best S = {s[best]}: \\${total[best]:,.0f} a year\n"
            f"Best possible: \\${floor:,.0f}\n"
            f"Gap: \\${gap:,.0f} ({100 * gap / floor:.1f}%)",
            xy=(s[best], total[best]),
            xytext=(s[best] + 0.6, total[best] + 1150),
            ha="center",
            fontsize=10.5,
            color=INK,
            linespacing=1.5,
            arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 1, "shrinkB": 3},
            zorder=5,
        )
        ax.set_title(label, loc="left", color=INK, fontsize=11.5, pad=8)
        ax.set_xticks(s)
        ax.set_xlabel("Stock level S (bags)", color=MUTED)
        ax.yaxis.set_major_formatter(dollars)
        ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
        ax.tick_params(colors=MUTED, length=0)
        ax.get_xticklabels()[best].set(color=INK, fontweight="bold")
        for side in ax.spines.values():
            side.set_visible(False)
    axes[0].set_ylabel("Loss per year", color=MUTED)

    fig.suptitle(
        "Platelets: the simple rule is within 2–4% of the best possible policy",
        x=0.06,
        y=0.975,
        ha="left",
        color=INK,
        fontsize=13.5,
    )
    fig.text(
        0.06,
        0.905,
        "Yearly loss from always ordering up to S bags, at "
        f"\\${SHORT_COST:g} per bag short and \\${OUTDATE_COST:g} per bag outdated "
        "(Elston & Pickrel, 1963). Synthetic ICU demand.",
        fontsize=9.5,
        color=MUTED,
    )
    fig.legend(
        handles=[
            Patch(color=VIOLET, label="Shortage"),
            Patch(color=YELLOW, label="Outdating"),
            Line2D(
                [],
                [],
                color=INK,
                lw=1.3,
                ls=(0, (4, 3)),
                label="Lowest loss any ordering policy can reach",
            ),
        ],
        loc="upper left",
        bbox_to_anchor=(0.052, 0.895),
        ncols=3,
        frameon=False,
        labelcolor=INK,
        fontsize=10,
        handlelength=1.6,
        columnspacing=1.8,
    )
    fig.tight_layout(rect=(0.03, 0, 0.99, 0.87))
    fig.savefig(path, dpi=160, facecolor=SURFACE)


def _bag(ax, x, y, color, text="", text_color=INK):
    """One bag: a rounded square, with the days it has left written inside."""
    ax.add_patch(
        FancyBboxPatch(
            (x + 0.09, y - 0.36),
            0.72,
            0.72,
            boxstyle="round,pad=0,rounding_size=0.12",
            facecolor=color,
            edgecolor="none",
        )
    )
    ax.text(
        x + 0.45, y, text, ha="center", va="center", fontsize=10.5, color=text_color
    )


def _paragraph(fig, y, text, heading=None, width=120):
    """Write a wrapped paragraph y inches from the top. Returns where it ends."""
    height = fig.get_figheight()
    lines = textwrap.wrap(text, width)
    if heading:
        fig.text(
            0.045, 1 - y / height, heading, fontsize=10.5, color=INK, fontweight="bold"
        )
        y += 0.24
    for line in lines:
        fig.text(0.045, 1 - y / height, line, fontsize=10, color=INK)
        y += 0.215
    return y + 0.13


def plot_orders_by_age(model, policy, level, simple_loss, best_loss, path, bags=5):
    """One shelf total, every mix of ages: what each rule orders.

    Each row is a shelf holding the same number of bags, with more of them
    about to expire further down. Order-up-to-S orders the same in every row.
    Shelves the best policy never reaches are left out. The text is written
    for a reader who knows nothing about blood banking or inventory rules.
    simple_loss and best_loss are the two rules' yearly losses, for the text.
    """
    simple = order_up_to(model, level)
    reached = visit_shares(model, policy) >= 0.0005
    shelves = [
        (old, model.index([old, bags - old]))
        for old in range(bags + 1)
        if reached[model.index([old, bags - old])]
    ]
    usable_days = model.states.shape[1] + 1
    top = len(shelves)
    unit = 0.47  # inches per bag square
    table_height = unit * (top + 1.35)
    width, height = 11, 5.3 + table_height
    fig = plt.figure(figsize=(width, height), facecolor=SURFACE)

    fig.text(
        0.045,
        1 - 0.42 / height,
        f"Platelets: the same {bags} bags on the shelf, but the best policy "
        "orders more when they are old",
        color=INK,
        fontsize=13.5,
    )
    y = _paragraph(
        fig,
        0.85,
        f"Platelets last only {usable_days} days after they arrive. Every evening "
        "the blood bank orders fresh bags for the next morning. Too few and a "
        "patient may go without; too many and bags expire unused.",
        heading="The decision",
    )
    y = _paragraph(
        fig,
        y,
        f"\u201cOrder up to {level}\u201d is the simple rule from Elston & "
        "Pickrel\u2019s 1963 paper: order enough to bring the shelf back to "
        f"{level} bags. The \u201cbest possible policy\u201d is the lowest-cost "
        "rule of any kind, found by computer. Both are charged "
        f"${SHORT_COST:g} per bag short and ${OUTDATE_COST:g} per bag thrown "
        "away.".replace("$", "\\$"),
        heading="The two rules",
    )
    y = _paragraph(
        fig,
        y,
        f"Each row is an evening with {bags} bags on the shelf. Further down, more "
        "of them are on their last day.",
    )

    ax = fig.add_axes(
        (0.045, 1 - (y + table_height) / height, 0.91, table_height / height)
    )
    ax.set_facecolor(SURFACE)
    span = 0.91 * width / unit  # the axes' width in bag squares
    shelf_x, simple_x, best_x = 4.6, 11.3, 16.6
    for x, label in [
        (shelf_x, f"On the shelf tonight: {bags} bags\n(number = days each has left)"),
        (simple_x, f"Order up to {level}\norders"),
        (best_x, "Best possible policy\norders"),
    ]:
        ax.text(x + 0.09, top + 0.75, label, fontsize=10.5, color=INK, va="bottom")
    ax.plot([0, span], [top + 0.55] * 2, color=GRID, lw=1)
    for row, (old, state) in enumerate(shelves):
        row_y = top - row
        note = "none expire" if old == 0 else f"{old} expire{'s' if old == 1 else ''}"
        ax.text(0, row_y, f"{note} tomorrow night", va="center", color=MUTED)
        for i in range(bags):
            if i < old:
                _bag(ax, shelf_x + i * 0.9, row_y, OLD, "1", "white")
            else:
                _bag(ax, shelf_x + i * 0.9, row_y, YOUNG, "2")
        for x, orders in [(simple_x, simple), (best_x, policy)]:
            q = int(orders[state])
            for i in range(q):
                _bag(ax, x + i * 0.9, row_y, BLUE)
            more = orders is policy and q != simple[state]
            ax.text(
                x + max(q, 1) * 0.9 + 0.25,
                row_y,
                f"{q} bag{'' if q == 1 else 's'}",
                va="center",
                fontsize=10.5,
                color=INK,
                fontweight="bold" if more else "normal",
            )
    ax.set_xlim(0, span)
    ax.set_ylim(0.4, top + 1.75)
    ax.axis("off")

    y = _paragraph(
        fig,
        y + table_height + 0.3,
        f"The simple rule counts {bags} bags and always orders "
        f"{int(simple[shelves[0][1]])}. But bags on their last day are gone by "
        "tomorrow night, used or not. With an old shelf, an extra fresh bag will "
        "still be wanted later. With a young shelf, it is more likely to expire "
        "unused.",
        heading="Why order more when the stock is old?",
    )
    extra = 100 * (simple_loss / best_loss - 1)
    _paragraph(
        fig,
        y,
        f"Very little. The simple rule costs ${simple_loss:,.0f} a year and the "
        f"best possible policy ${best_loss:,.0f}, a difference of {extra:.1f}%. "
        "Demand is simulated from synthetic intensive-care data.".replace("$", "\\$"),
        heading="How much does it matter?",
    )
    fig.savefig(path, dpi=160, facecolor=SURFACE)


def plot_order_grid(model, policy, level, path, upto=7):
    """What order-up-to-S and the best policy order, by the age of the stock.

    For 3 usable days the shelf each evening is two numbers: the bags that
    expire tomorrow night and the bags with a day more. Order-up-to-S only sees
    their sum, so its orders are the same along each diagonal. Shelves a policy
    never reaches are faded. Returns the share of evenings on which the two
    policies order differently.
    """
    simple = order_up_to(model, level)
    differ = visit_shares(model, policy)[policy != simple].sum()
    grid = np.arange(upto + 1)
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.95), sharey=True, facecolor=SURFACE)
    panels = [(f"Order up to {level}", simple), ("Best possible policy", policy)]
    for ax, (label, orders) in zip(axes, panels, strict=True):
        ax.set_facecolor(SURFACE)
        reached = visit_shares(model, orders) >= 0.0005
        for old in grid:
            for young in grid:
                state = model.index([old, young])
                q = int(orders[state])
                fade = 1 if reached[state] else 0.3
                ax.add_patch(
                    plt.Rectangle(
                        (young - 0.5, old - 0.5),
                        1,
                        1,
                        facecolor=ORDER_BLUES[q],
                        edgecolor=SURFACE,
                        linewidth=2,
                        alpha=fade,
                    )
                )
                ax.text(
                    young,
                    old,
                    str(q),
                    ha="center",
                    va="center",
                    fontsize=11.5,
                    color="white" if q >= 3 and reached[state] else INK,
                    alpha=1 if reached[state] else 0.45,
                )
                if q != simple[state]:
                    ax.add_patch(
                        plt.Rectangle(
                            (young - 0.41, old - 0.41),
                            0.82,
                            0.82,
                            fill=False,
                            edgecolor=INK,
                            linewidth=1.6,
                            alpha=fade,
                        )
                    )
        ax.set_xlim(-0.5, upto + 0.5)
        ax.set_ylim(-0.5, upto + 0.5)
        ax.set_aspect("equal")
        ax.set_xticks(grid)
        ax.set_yticks(grid)
        ax.set_title(label, loc="left", color=INK, fontsize=11.5, pad=8)
        ax.set_xlabel("Bags with two days left", color=MUTED)
        ax.tick_params(colors=MUTED, length=0)
        for side in ax.spines.values():
            side.set_visible(False)
    axes[0].set_ylabel("Bags with one day left", color=MUTED)

    fig.suptitle(
        "Platelets: the best policy orders more when the shelf is nearly full and old",
        x=0.06,
        y=0.975,
        ha="left",
        color=INK,
        fontsize=13.5,
    )
    fig.text(
        0.06,
        0.845,
        "Bags to order each evening, by what is on the shelf (3 usable days). "
        f"Order-up-to-{level} only looks at the total.\n"
        "Outlined: the best policy orders more, which happens on "
        f"{100 * differ:.0f}% of evenings.\n"
        "Faded: shelves that policy never reaches. Synthetic ICU demand.",
        fontsize=9.5,
        color=MUTED,
        linespacing=1.6,
    )
    fig.tight_layout(rect=(0.03, 0.01, 0.99, 0.855))
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    return differ


def print_orders(model, policy, upto=8):
    """The optimal order by stock age, for a two-age state (3 usable days)."""
    print("\nBags to order (3 usable days), by bags held:")
    print(
        "  expiring tonight |  with one more day: "
        + " ".join(map(str, range(upto + 1)))
    )
    for old in range(upto + 1):
        orders = [policy[model.index([old, young])] for young in range(upto + 1)]
        print(f"  {old:16d} |                     " + " ".join(map(str, orders)))


def main():
    fit = json.loads((ROOT / "phase2" / "results.json").read_text())["platelets"]
    pmf = demand_pmf(fit["episodes_per_day"], fit["size_params"]["logarithmic"])
    rows = []
    for label, usable_days in SCENARIOS:
        model = build_model(pmf, usable_days)
        compared, policy = compare(model, LEVELS)
        for row in compared:
            rows.append({"product": "platelets", "scenario": label, **row})
        if usable_days == 3:
            orders_model, orders_policy = model, policy
        print(f"solved platelets, {label} ({len(model.states)} states)")
    table = pd.DataFrame(rows)
    table["stock_level"] = table["stock_level"].astype("Int64")
    table.to_csv(HERE / "optimal.csv", index=False, float_format="%.2f")

    plot_platelets(table, HERE / "platelets_optimal.png")

    print(f"\nLoss at {SHORT_COST:g} per bag short, {OUTDATE_COST:g} per bag outdated:")
    best = headline(table)
    print(best.round(1).to_string(index=False))
    for label, group in best.groupby("scenario", sort=False):
        s, floor = group["loss_per_year"]
        print(f"{label}: order-up-to-S costs {100 * (s / floor - 1):.1f}% more")
    print_orders(orders_model, orders_policy)

    level = int(best.loc[0, "stock_level"])
    simple_loss, best_loss = best["loss_per_year"][:2]
    plot_orders_by_age(
        orders_model,
        orders_policy,
        level,
        simple_loss,
        best_loss,
        HERE / "platelets_orders.png",
    )
    differ = plot_order_grid(
        orders_model, orders_policy, level, HERE / "platelets_orders_grid.png"
    )
    print(
        f"\nThe best policy and order-up-to-{level} differ on {100 * differ:.1f}% of evenings"
    )


if __name__ == "__main__":
    main()
