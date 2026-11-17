"""Fit transfusion demand models per blood product.

For each product: episodes per real day, and three candidate distributions for
bags per episode and bags per stay, compared by log-likelihood. Writes
phase2/results.json.

Run:    uv run python phase2/fit.py
Check:  uv run python phase2/grade.py
Needs phase2/episodes.csv and phase2/stay_bags.csv from sql/phase2.sql.

To fit exports kept in another folder, name it: tools/mimic_demo.sh runs
`phase2/fit.py mimic_demo/phase2` for the MIMIC-IV demo. The per-day numbers
only mean something when the exports cover every patient in the window.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
PRODUCTS = ["platelets", "rbc", "plasma"]

# Real days covered: 2008-01-01 to 2019-12-31, from patients.anchor_year_group.
# The dates in the data are shifted per patient, so they can't give this.
WINDOW_DAYS = 4383


def solve_for_mean(mean_of, target, lo, hi):
    """The parameter between lo and hi whose model mean equals target.

    mean_of must get larger as its parameter gets larger. Bisects until the
    interval can't shrink any further in floating point.
    """
    while True:
        mid = (lo + hi) / 2
        if mid in (lo, hi):
            return mid
        if mean_of(mid) < target:
            lo = mid
        else:
            hi = mid


def check_mean(mean, name):
    """Every size model starts at 1, so it can only fit a finite mean above 1."""
    if not math.isfinite(mean) or mean <= 1:
        raise ValueError(f"the {name} needs a finite mean above 1, got {mean}")


def log_likelihood(log_pmf, counts):
    """Total log-likelihood. counts maps each value k to how often it occurs."""
    return sum(n * log_pmf(k) for k, n in counts.items())


def fit_geometric(mean):
    """Geometric on k = 1, 2, ...: P(k) = p (1-p)^(k-1), mean 1/p."""
    check_mean(mean, "geometric")
    p = 1 / mean
    log_p = math.log(p)
    log_q = math.log1p(-p)  # log(1 - p)

    def log_pmf(k):
        if k < 1:
            return -math.inf
        return (k - 1) * log_q + log_p

    return p, log_pmf


def fit_poisson(mean):
    """The zero-truncated Poisson: it can't produce a 0."""
    check_mean(mean, "zero-truncated Poisson")

    def excess_and_slope(lam):
        """h(lam) = lam / (1 - e^-lam) - 1, the model mean minus 1, and h'(lam).

        Working with the excess over 1 avoids subtracting two numbers that are
        both close to 1 when the mean is close to 1.
        """
        if lam < 0.1:
            # Series for small lam, where the closed forms below lose accuracy:
            # h = lam/2 + lam^2/12 - lam^4/720 + lam^6/30240 - ...
            z = lam * lam
            excess = lam * (
                0.5
                + lam
                * (
                    1 / 12
                    + z
                    * (-1 / 720 + z * (1 / 30240 + z * (-1 / 1209600 + z / 47900160)))
                )
            )
            slope = 0.5 + lam * (
                1 / 6
                + z * (-1 / 180 + z * (1 / 5040 + z * (-1 / 151200 + z / 4790016)))
            )
            return excess, slope
        q = -math.expm1(-lam)  # 1 - e^-lam
        return (lam - q) / q, (q - lam * math.exp(-lam)) / (q * q)

    # Newton's method on h(lam) = mean - 1. h is increasing and convex, so
    # starting above the answer, every step moves down towards it without
    # overshooting. min(mean, 2 * (mean - 1)) is always above the answer.
    d = mean - 1
    lambda_ = min(mean, 2 * d)
    for _ in range(20):
        excess, slope = excess_and_slope(lambda_)
        step = (excess - d) / slope
        updated = lambda_ - step
        converged = updated == lambda_ or abs(step) <= 1e-12 * updated
        lambda_ = updated
        if converged:
            break
    else:
        raise ArithmeticError("zero-truncated Poisson fit did not converge")

    # log P(k) = (k - 1) log(lam) - log(k!) + log P(1),
    # where P(1) = lam e^-lam / (1 - e^-lam) = (1 + h) e^-lam.
    log_lambda = math.log(lambda_)
    log_p1 = math.log1p(excess_and_slope(lambda_)[0]) - lambda_

    def log_pmf(k):
        if k < 1:
            return -math.inf
        return (k - 1) * log_lambda - math.lgamma(k + 1) + log_p1

    return lambda_, log_pmf


def fit_logarithmic(mean):
    """Logarithmic on k = 1, 2, ...: P(k) = -theta^k / (k ln(1-theta))."""
    check_mean(mean, "logarithmic")

    def model_mean(theta):
        return -theta / ((1 - theta) * math.log1p(-theta))

    theta = solve_for_mean(model_mean, mean, 0.0, math.nextafter(1.0, 0.0))
    log_theta = math.log(theta)
    log_normalizer = math.log(-math.log1p(-theta))

    def log_pmf(k):
        if k < 1:
            return -math.inf
        return k * log_theta - math.log(k) - log_normalizer

    return theta, log_pmf


FITS = {
    "geometric": fit_geometric,
    "poisson": fit_poisson,
    "logarithmic": fit_logarithmic,
}


def compare_models(sizes):
    """Fit every candidate to a Series of sizes (each 1 or more)."""
    counts = sizes.value_counts().to_dict()
    mean = sizes.mean()
    fits = {name: fit(mean) for name, fit in FITS.items()}
    return {
        name: (param, log_likelihood(log_pmf, counts))
        for name, (param, log_pmf) in fits.items()
    }


def best_model(fitted):
    """The model with the highest log-likelihood, i.e. the one closest to 0."""
    return max(fitted, key=lambda name: fitted[name][1])


def main(folder=HERE):
    episodes = pd.read_csv(folder / "episodes.csv")
    stay_bags = pd.read_csv(folder / "stay_bags.csv")

    results = {"window_days": WINDOW_DAYS}
    for product in PRODUCTS:
        sizes = episodes.loc[episodes["product"] == product, "n_bags"]
        stays = stay_bags.loc[stay_bags["product"] == product, "n_bags"]
        stays_any = stays[stays >= 1]  # the models can't produce a 0
        size_fitted = compare_models(sizes)
        stay_fitted = compare_models(stays_any)

        results[product] = {
            "episodes": len(sizes),
            "episodes_per_day": len(sizes) / WINDOW_DAYS,
            "bags_per_episode": sizes.mean(),
            "share_one_bag": (sizes == 1).mean(),
            "size_params": {name: param for name, (param, _) in size_fitted.items()},
            "best_size_model": best_model(size_fitted),
            "bags_per_day": sizes.sum() / WINDOW_DAYS,
            "stays_any_share": len(stays_any) / len(stays),  # out of ALL stays
            "stays_bags_mean": stays_any.mean(),  # among stays with any bag
            "stays_bags_var": stays_any.var(),  # n - 1, same as var_samp
            "best_stay_model": best_model(stay_fitted),
        }

    (folder / "results.json").write_text(json.dumps(results, indent=2))
    print("Wrote", folder / "results.json")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE)
