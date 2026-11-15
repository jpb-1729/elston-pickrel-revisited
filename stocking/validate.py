"""What does the constant-rate demand model cost? A check on synthetic data.

Real MIMIC-IV shifts every patient's dates, so the true bags-per-day series
can't be built and the simulator runs on model demand instead. The synthetic
data keeps the true calendar (synth/answer_key/true_daily_demand.csv.gz), so
here both are run through the same simulator and compared.

The model is run on many stretches as long as the true series, to show how
much two runs differ by chance alone.

Writes stocking/validation.csv and stocking/platelets_validation.png.
Run:  uv run python stocking/validate.py
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from stocking.simulate import sample_daily_demand, simulate

HERE = Path(__file__).parent
TRUE_SERIES = ROOT / "synth" / "answer_key" / "true_daily_demand.csv.gz"
N_STRETCHES = 200
SEED = 1971
SCENARIOS = [("platelets", 3), ("platelets", 5), ("rbc", 42), ("plasma", 365)]

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"


def outdate_rate(r):
    return r.outdated / np.maximum(r.delivered, 1)


def compare(product, usable_days, true_demand, fit, rng):
    """One row per stock level: the true series against the model's range."""
    levels = np.arange(0, int(true_demand.mean() * 5) + 1)
    true = simulate(true_demand, levels, usable_days)
    model_demand = sample_daily_demand(
        fit["episodes_per_day"],
        fit["size_params"]["logarithmic"],
        len(true_demand) * N_STRETCHES,
        rng,
    )
    runs = [
        simulate(stretch, levels, usable_days)
        for stretch in model_demand.reshape(N_STRETCHES, -1)
    ]
    short = np.array([r.short_day_rate for r in runs])
    outdated = np.array([outdate_rate(r) for r in runs])
    return pd.DataFrame(
        {
            "product": product,
            "usable_days": usable_days,
            "stock_level": levels,
            "true_mean_demand": true_demand.mean(),
            "true_var_demand": true_demand.var(),
            "model_mean_demand": model_demand.mean(),
            "model_var_demand": model_demand.var(),
            "short_day_rate_true": true.short_day_rate,
            "short_day_rate_model": short.mean(axis=0),
            "short_day_rate_model_lo": np.quantile(short, 0.025, axis=0),
            "short_day_rate_model_hi": np.quantile(short, 0.975, axis=0),
            "outdate_rate_true": outdate_rate(true),
            "outdate_rate_model": outdated.mean(axis=0),
            "outdate_rate_model_lo": np.quantile(outdated, 0.025, axis=0),
            "outdate_rate_model_hi": np.quantile(outdated, 0.975, axis=0),
        }
    )


def plot(table, path):
    """Shortage days against S for platelets: model range and true series."""
    t = table[(table["product"] == "platelets") & (table["usable_days"] == 3)]
    t = t[t["stock_level"].between(2, 8)]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), facecolor=SURFACE)
    panels = [
        ("short_day_rate", "Days with a shortage (%)"),
        ("outdate_rate", "Bags outdated (% of delivered)"),
    ]
    for ax, (measure, title) in zip(axes, panels, strict=True):
        ax.set_facecolor(SURFACE)
        s = t["stock_level"]
        ax.fill_between(
            s,
            t[f"{measure}_model_lo"] * 100,
            t[f"{measure}_model_hi"] * 100,
            color=BLUE,
            alpha=0.2,
            lw=0,
            label="Model, 95% of 12-year runs",
        )
        ax.plot(s, t[f"{measure}_model"] * 100, color=BLUE, lw=2, label="Model, mean")
        ax.plot(
            s,
            t[f"{measure}_true"] * 100,
            color=ORANGE,
            lw=0,
            marker="o",
            ms=7,
            mec=SURFACE,
            mew=1.5,
            label="True daily series",
            zorder=4,
        )
        ax.set_title(title, loc="left", color=INK, fontsize=11)
        ax.set_xlabel("Stock level S (bags)", color=MUTED)
        ax.set_ylim(bottom=0)
        ax.grid(color=GRID, lw=0.8, zorder=0)
        ax.tick_params(colors=MUTED, length=0)
        for side in ax.spines.values():
            side.set_visible(False)
    axes[0].legend(frameon=False, labelcolor=INK, loc="upper right")
    fig.suptitle(
        "Platelets, 3 usable days: the model against the true calendar "
        "(synthetic data)",
        x=0.01,
        ha="left",
        color=INK,
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)


def main():
    fits = json.loads((ROOT / "phase2" / "results.json").read_text())
    true = pd.read_csv(TRUE_SERIES).rename(columns={"ffp": "plasma"})
    rng = np.random.default_rng(SEED)
    table = pd.concat(
        [
            compare(product, days, true[product].to_numpy(), fits[product], rng)
            for product, days in SCENARIOS
        ],
        ignore_index=True,
    )
    table.to_csv(HERE / "validation.csv", index=False, float_format="%.5f")
    plot(table, HERE / "platelets_validation.png")

    for (product, days), t in table.groupby(["product", "usable_days"], sort=False):
        first = t.iloc[0]
        s_true = t.loc[t["short_day_rate_true"] <= 0.05, "stock_level"].min()
        s_model = t.loc[t["short_day_rate_model"] <= 0.05, "stock_level"].min()
        print(
            f"{product}, {days} usable days: "
            f"variance of daily demand true {first['true_var_demand']:.2f}, "
            f"model {first['model_var_demand']:.2f}; "
            f"S for 5% shortage days true {s_true}, model {s_model}"
        )


if __name__ == "__main__":
    main()
