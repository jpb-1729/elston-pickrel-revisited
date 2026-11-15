"""Shortage against outdating for a range of stock levels, per blood product.

Reads the fitted demand model from phase2/results.json, simulates the
order-up-to-S policy for every S, and writes:
  stocking/results.csv              one row per scenario and stock level
  stocking/recommended.csv          the smallest S meeting each shortage target
  stocking/platelets_tradeoff.png   the platelet curves

Run:  uv run python stocking/run.py
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from stocking.simulate import sample_daily_demand, simulate

HERE = Path(__file__).parent
N_DAYS = 200_000
WARMUP = 365
SEED = 1971
# Shortage targets: for each, report the smallest S that is short on at most
# this share of days.
TARGETS = [0.05, 0.01, 0.005]

# usable_days is shelf life minus age on arrival. These are assumptions, not
# data: platelets last 5 days, and "3" allows 2 days for testing and transport.
SCENARIOS = [
    ("platelets", "3 usable days", 3),
    ("platelets", "5 usable days", 5),
    ("rbc", "42 usable days", 42),
    ("plasma", "365 usable days (frozen)", 365),
]

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"


def run_scenarios(fits):
    rows = []
    for i, (product, label, usable_days) in enumerate(SCENARIOS):
        fit = fits[product]
        rate = fit["episodes_per_day"]
        theta = fit["size_params"]["logarithmic"]
        # The same seed per product, so its scenarios face the same demand.
        seed = SEED + [p for p, _, _ in SCENARIOS].index(product)
        demand = sample_daily_demand(rate, theta, N_DAYS, np.random.default_rng(seed))
        levels = np.arange(0, int(demand.mean() * 8) + 1)
        r = simulate(demand, levels, usable_days, warmup=WARMUP)
        rows.append(
            pd.DataFrame(
                {
                    "product": product,
                    "scenario": label,
                    "usable_days": usable_days,
                    "stock_level": r.levels,
                    "mean_daily_demand": r.demand / r.days,
                    "short_day_rate": r.short_day_rate,
                    "short_bag_rate": r.short_bag_rate,
                    "outdate_rate": np.where(
                        r.delivered > 0, r.outdated / np.maximum(r.delivered, 1), 0.0
                    ),
                    "mean_stock": r.mean_stock,
                }
            )
        )
        print(f"simulated {product}, {label} ({i + 1}/{len(SCENARIOS)})")
    return pd.concat(rows, ignore_index=True)


def recommended(results):
    """The smallest S per scenario and target that keeps shortage days within it."""
    picks = []
    for target in TARGETS:
        ok = results[results["short_day_rate"] <= target]
        pick = ok.groupby(["product", "scenario"], sort=False).first().reset_index()
        pick.insert(2, "target", target)
        picks.append(pick)
    return pd.concat(picks, ignore_index=True)


def plot_platelets(results, picks, path):
    """Shortage days against outdating for every S, with the targets marked.

    The shortage axis is logarithmic so the 5%, 1% and 0.5% targets are all
    readable on one chart.
    """
    fig, ax = plt.subplots(figsize=(8.5, 5.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    platelets = results[results["product"] == "platelets"]
    for (label, group), color in zip(
        platelets.groupby("scenario", sort=False), [BLUE, ORANGE], strict=True
    ):
        group = group[group["stock_level"].between(1, 13)]
        x, y = group["outdate_rate"] * 100, group["short_day_rate"] * 100
        ax.plot(x, y, color=color, lw=2, marker="o", ms=4.5, label=label, zorder=3)
        pick = picks[(picks["product"] == "platelets") & (picks["scenario"] == label)]
        px, py = pick["outdate_rate"] * 100, pick["short_day_rate"] * 100
        ax.scatter(px, py, s=150, facecolor="none", edgecolor=color, lw=2, zorder=4)
        marked = set(pick["stock_level"])
        for s, xi, yi in zip(group["stock_level"], x, y, strict=True):
            if s in marked or s in (1, 13):
                ax.annotate(
                    f"S={s}",
                    (xi, yi),
                    textcoords="offset points",
                    xytext=(9, 6),
                    fontsize=9.5,
                    color=INK if s in marked else MUTED,
                )

    ax.set_yscale("log")
    ax.set_xlim(-2, 68)
    for target in TARGETS:
        ax.axhline(target * 100, color=MUTED, lw=1, ls=(0, (4, 3)), zorder=2)
        ax.text(
            -1.5,
            target * 100 * 1.07,
            f"target {target * 100:g}%",
            fontsize=9,
            color=MUTED,
        )
    ax.set_yticks([0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 40])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.minorticks_off()
    ax.set_xlabel("Bags outdated (% of bags delivered)", color=MUTED)
    ax.set_ylabel("Days with a shortage (%, log scale)", color=MUTED)
    ax.set_title(
        "Platelets: holding more stock trades shortages for waste",
        loc="left",
        color=INK,
        fontsize=13,
        pad=28,
    )
    ax.text(
        0,
        1.03,
        "Each point is one stock level S, from 1 to 13 bags. Circled: the smallest S "
        "meeting each target. Synthetic ICU demand.",
        transform=ax.transAxes,
        fontsize=9,
        color=MUTED,
    )
    ax.grid(color=GRID, lw=0.8, zorder=0)
    ax.tick_params(colors=MUTED, length=0)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.legend(frameon=False, labelcolor=INK, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)


def main():
    fits = json.loads((ROOT / "phase2" / "results.json").read_text())
    results = run_scenarios(fits)
    results.to_csv(HERE / "results.csv", index=False, float_format="%.5f")
    picks = recommended(results)
    picks.to_csv(HERE / "recommended.csv", index=False, float_format="%.5f")
    plot_platelets(results, picks, HERE / "platelets_tradeoff.png")
    print("\nSmallest S that is short on at most the target share of days:")
    columns = [
        "product",
        "scenario",
        "target",
        "stock_level",
        "short_day_rate",
        "short_bag_rate",
        "outdate_rate",
    ]
    print(
        picks.sort_values(["product", "scenario"])[columns]
        .round(4)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
