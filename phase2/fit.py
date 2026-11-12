"""Phase 2 worksheet: the modelling part. Steps 8 to 11 of EXERCISE.md.

Fill in every TODO, then:  uv run python phase2/fit.py
Then check it:             uv run python phase2/grade.py
Needs phase2/episodes.csv and phase2/stay_bags.csv from sql/phase2.sql.
"""
import json
import math
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
PRODUCTS = ["platelets", "rbc", "plasma"]
MODELS = ["geometric", "poisson", "logarithmic"]

episodes = pd.read_csv(HERE / "episodes.csv")
stay_bags = pd.read_csv(HERE / "stay_bags.csv")

# Step 5: how many real days the data covers.
WINDOW_DAYS = None  # TODO


def solve_for_mean(mean_of, target, lo, hi):
    """The parameter between lo and hi whose model mean equals target.

    mean_of must get larger as its parameter gets larger.
    """
    for _ in range(200):
        mid = (lo + hi) / 2
        if mean_of(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def log_likelihood(log_pmf, counts):
    """Total log-likelihood. counts maps each value k to how often it occurs."""
    return sum(n * log_pmf(k) for k, n in counts.items())


# Step 8: each function takes the mean of the sizes and returns the fitted
# parameter and a function k -> log P(k). See the table in EXERCISE.md.
def fit_geometric(mean):
    raise NotImplementedError  # TODO


def fit_poisson(mean):
    """The zero-truncated Poisson: it can't produce a 0."""
    raise NotImplementedError  # TODO


def fit_logarithmic(mean):
    raise NotImplementedError  # TODO


FITS = {"geometric": fit_geometric, "poisson": fit_poisson, "logarithmic": fit_logarithmic}


def compare_models(sizes):
    """Fit every candidate to a Series of sizes (each 1 or more)."""
    counts = sizes.value_counts().to_dict()
    mean = sizes.mean()
    fits = {name: fit(mean) for name, fit in FITS.items()}
    return {name: (param, log_likelihood(log_pmf, counts))
            for name, (param, log_pmf) in fits.items()}


results = {"window_days": WINDOW_DAYS}
for product in PRODUCTS:
    sizes = episodes.loc[episodes["product"] == product, "n_bags"]
    stays = stay_bags.loc[stay_bags["product"] == product, "n_bags"]
    fitted = compare_models(sizes)

    # Step 9: pick the best of MODELS by log-likelihood (closest to 0 is best).
    best_size_model = None  # TODO

    # Step 10: the same comparison for bags per stay, among stays with any.
    best_stay_model = None  # TODO

    results[product] = {
        # Step 5
        "episodes": int(len(sizes)),
        "episodes_per_day": None,  # TODO
        # Step 8
        "bags_per_episode": None,  # TODO
        "share_one_bag": None,  # TODO
        "size_params": {name: fit[0] for name, fit in fitted.items()},
        "best_size_model": best_size_model,
        # Step 11: expected bags per real day
        "bags_per_day": None,  # TODO
        # Step 10
        "stays_any_share": None,  # TODO: share of ALL stays with at least one bag
        "stays_bags_mean": None,  # TODO: among stays with at least one bag
        "stays_bags_var": None,  # TODO: among stays with at least one bag
        "best_stay_model": best_stay_model,
    }

(HERE / "results.json").write_text(json.dumps(results, indent=2))
print("Wrote", HERE / "results.json")
