"""Grade Phase 2. Prints PASS or FAIL for each check, and no answer-key values.

Run from the project root:  uv run python phase2/grade.py
Don't read this file while doing the exercise: like the answer key, it spells
out the answers.
"""
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
KEY = ROOT / "synth" / "answer_key"
PRODUCTS = {"platelets": "platelets", "rbc": "rbc", "plasma": "ffp"}
failed = False


def report(label, passed, advice=""):
    global failed
    failed |= not passed
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + (f"  ({advice})" if advice and not passed else ""))


def close(mine, truth, tol):
    return mine is not None and truth != 0 and abs(mine / truth - 1) <= tol


def solve(mean_of, target, lo, hi):
    for _ in range(200):
        mid = (lo + hi) / 2
        if mean_of(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def best_model(sizes):
    """The best of the three candidates by log-likelihood, for these sizes."""
    counts = sizes.value_counts().to_dict()
    m = sizes.mean()
    p = 1 / m
    lam = solve(lambda l: l / (1 - math.exp(-l)), m, 1e-9, 1000)
    th = solve(lambda t: -t / ((1 - t) * math.log(1 - t)), m, 1e-9, 1 - 1e-12)
    pmfs = {
        "geometric": lambda k: math.log(p) + (k - 1) * math.log(1 - p),
        "poisson": lambda k: k * math.log(lam) - lam - math.lgamma(k + 1) - math.log(1 - math.exp(-lam)),
        "logarithmic": lambda k: k * math.log(th) - math.log(k) - math.log(-math.log(1 - th)),
    }
    return max(pmfs, key=lambda name: sum(n * pmfs[name](k) for k, n in counts.items()))


def check_episodes():
    bags = pd.read_csv(KEY / "bags.csv.gz")
    bags = bags[bags["product"].isin(PRODUCTS.values())]
    key = (bags.groupby(["stay_id", "product", "episode_id"])
           .agg(episode_start=("shifted_start", "min"), n_bags=("bag_id", "count"))
           .reset_index().drop(columns="episode_id"))
    key["product"] = key["product"].replace("ffp", "plasma")
    cols = ["stay_id", "product", "episode_start", "n_bags"]
    mine = pd.read_csv(DIR / "episodes.csv")
    for frame in (key, mine):
        frame["episode_start"] = pd.to_datetime(frame["episode_start"])
    merged = key[cols].merge(mine[cols], how="outer", on=cols, indicator=True)
    report("every episode matches the key",
           (merged["_merge"] == "both").all(),
           "wrong gap threshold, or records instead of bags")
    return bags


def check_results(bags):
    results = json.loads((DIR / "results.json").read_text())
    targets = json.loads((KEY / "effective_targets.json").read_text())
    daily = pd.read_csv(KEY / "true_daily_demand.csv.gz", parse_dates=["real_date"])
    daily = daily[daily["real_date"].dt.year <= 2019]
    icu_stays = len(pd.read_csv(ROOT / "synth" / "icu" / "icustays.csv.gz", usecols=["stay_id"]))
    per_stay = bags.groupby(["product", "stay_id"]).size()
    episode_sizes = bags.groupby(["product", "episode_id"]).size()

    report("window_days", close(results.get("window_days"), len(daily), 0.005),
           "how many real days does the data cover?")

    for mine_name, key_name in PRODUCTS.items():
        mine, target = results.get(mine_name, {}), targets[key_name]
        any_stays = per_stay.loc[key_name]
        size_pmf = target["size_pmf"]
        sizes = episode_sizes.loc[key_name]
        checks = [
            ("episodes", close(mine.get("episodes"), target["episodes"], 0.001), "count of episodes"),
            ("episodes_per_day", close(mine.get("episodes_per_day"), target["episodes_per_day_mean"], 0.01),
             "check what you divided by"),
            ("bags_per_episode", close(mine.get("bags_per_episode"), target["bags_per_episode_mean"], 0.005),
             "average over episodes"),
            ("share_one_bag", close(mine.get("share_one_bag"), size_pmf["1"], 0.005),
             "share of episodes with exactly one bag"),
            ("size_params", close(mine.get("size_params", {}).get("logarithmic"), target["logseries_theta_mle"], 0.01),
             "check your fit_ functions"),
            ("best_size_model", mine.get("best_size_model") == best_model(sizes),
             "compare log-likelihoods for the sizes"),
            ("bags_per_day", close(mine.get("bags_per_day"), daily[key_name].mean(), 0.01),
             "episodes per day times bags per episode"),
            ("stays_any_share", close(mine.get("stays_any_share"), len(any_stays) / icu_stays, 0.005),
             "the bottom of this share is every ICU stay"),
            ("stays_bags_mean", close(mine.get("stays_bags_mean"), any_stays.mean(), 0.005),
             "only stays with at least one bag"),
            ("stays_bags_var", close(mine.get("stays_bags_var"), any_stays.var(), 0.01),
             "only stays with at least one bag"),
            ("best_stay_model", mine.get("best_stay_model") == best_model(any_stays),
             "compare log-likelihoods for bags per stay"),
        ]
        for label, passed, advice in checks:
            report(f"{mine_name}: {label}", passed, advice)


check_results(check_episodes())
print("All checks passed." if not failed else "Some checks failed.")
sys.exit(1 if failed else 0)
