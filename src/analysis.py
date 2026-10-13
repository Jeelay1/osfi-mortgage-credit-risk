"""Analysis functions shared by the notebook and the export step.

  decompose_allowance_change   Shapley split of the change in mortgage allowances
                               into book growth, stage mix and coverage per stage
  fit_interrupted_time_series  segmented regression of the impaired (Stage 3) share
                               around the first Bank of Canada rate hike
  migration_sensitivity        allowance needed if 1% of the book moved stage

Run directly to write the results to data/processed:
    python src/analysis.py
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from math import factorial
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson, jarque_bera

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

BANK_ORDER = ["RBC", "TD", "BNS", "BMO", "CIBC", "NBC"]

# Last quarter-end before the Bank of Canada's first hike (2 March 2022) and the
# first quarter-end after it. Fixed in advance, not chosen from the data.
BASELINE_QUARTER = pd.Timestamp("2022-01-31")
FIRST_POST_HIKE_QUARTER = pd.Timestamp("2022-04-30")


def load(name: str) -> pd.DataFrame:
    """Read one processed CSV, parsing any *_date columns."""
    df = pd.read_csv(PROCESSED / f"{name}.csv")
    for col in df.columns:
        if col.endswith("_date"):
            df[col] = pd.to_datetime(df[col])
    return df


# ---------------------------------------------------------------------------
# 1. Shapley decomposition of the change in allowances
# ---------------------------------------------------------------------------
def _ecl(volume: float, mix: np.ndarray, rate: np.ndarray) -> float:
    """Allowance = book size x sum over stages of (stage share x stage coverage)."""
    return float(volume * np.dot(mix, rate))


def shapley_three_factor(v0, m0, r0, v1, m1, r1) -> dict[str, float]:
    """Exact Shapley attribution of f(V, M, R) = V * (M . R) between two periods.

    Each factor's contribution is its average marginal effect over every order
    in which the three factors can be switched from period 0 to period 1, so the
    three pieces always add up to the total change with no leftover term.
    """
    start = {"volume": v0, "mix": m0, "rate": r0}
    end = {"volume": v1, "mix": m1, "rate": r1}
    names = list(start)
    contrib = dict.fromkeys(names, 0.0)
    orders = list(permutations(names))
    for order in orders:
        current = dict(start)
        before = _ecl(current["volume"], current["mix"], current["rate"])
        for name in order:
            current[name] = end[name]
            after = _ecl(current["volume"], current["mix"], current["rate"])
            contrib[name] += after - before
            before = after
    return {k: v / factorial(len(names)) for k, v in contrib.items()} | {"n_orders": len(orders)}


def decompose_allowance_change(
    quarterly: pd.DataFrame,
    monthly: pd.DataFrame,
    start: pd.Timestamp = BASELINE_QUARTER,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Split each bank's change in residential-mortgage allowances between two quarters.

    volume  : the book got bigger (organic growth and, for RBC and NBC, acquisitions)
    mix     : more of the book sits in Stage 2 or Stage 3, which carry higher coverage
    rate    : the bank holds more (or less) allowance per dollar within each stage
    """
    end = end or quarterly["quarter_end_date"].max()
    rows = []
    for bank in ["Big Six", *BANK_ORDER]:
        q = quarterly[quarterly["short_name"] == bank].set_index("quarter_end_date")
        p0, p1 = q.loc[start], q.loc[end]
        v0, v1 = p0["gross_total_cad_mn"], p1["gross_total_cad_mn"]
        m0 = np.array([p0[f"gross_s{s}_cad_mn"] for s in (1, 2, 3)]) / v0
        m1 = np.array([p1[f"gross_s{s}_cad_mn"] for s in (1, 2, 3)]) / v1
        r0 = np.array([p0[f"ecl_s{s}_cad_mn"] / p0[f"gross_s{s}_cad_mn"] for s in (1, 2, 3)])
        r1 = np.array([p1[f"ecl_s{s}_cad_mn"] / p1[f"gross_s{s}_cad_mn"] for s in (1, 2, 3)])
        parts = shapley_three_factor(v0, m0, r0, v1, m1, r1)

        # Acquired books (M4, last month before consolidation) inside the window.
        mm = monthly[(monthly["month_end_date"] > start) & (monthly["month_end_date"] <= end)]
        if bank == "Big Six":
            acquired = mm.loc[mm["is_acquisition_month"], "acquired_in_yoy_window_cad_mn"].sum()
        else:
            acquired = mm.loc[mm["is_acquisition_month"] & (mm["short_name"] == bank),
                              "acquired_in_yoy_window_cad_mn"].sum()
        acquired_share = acquired / (v1 - v0) if v1 != v0 else 0.0

        ecl0, ecl1 = p0["ecl_total_cad_mn"], p1["ecl_total_cad_mn"]
        rows.append({
            "short_name": bank,
            "start_quarter": start.date(),
            "end_quarter": end.date(),
            "ecl_start_cad_mn": ecl0,
            "ecl_end_cad_mn": ecl1,
            "ecl_change_cad_mn": ecl1 - ecl0,
            "ecl_change_pct": ecl1 / ecl0 - 1,
            "book_start_cad_mn": v0,
            "book_end_cad_mn": v1,
            "acquired_book_cad_mn": acquired,
            "volume_organic_cad_mn": parts["volume"] * (1 - acquired_share),
            "volume_acquired_cad_mn": parts["volume"] * acquired_share,
            "stage_mix_cad_mn": parts["mix"],
            "coverage_rate_cad_mn": parts["rate"],
            "check_sum_cad_mn": parts["volume"] + parts["mix"] + parts["rate"] - (ecl1 - ecl0),
        })
    out = pd.DataFrame(rows)
    assert out["check_sum_cad_mn"].abs().max() < 1e-6, "decomposition does not add up"
    return out


# ---------------------------------------------------------------------------
# 2. Interrupted time series of the impaired (Stage 3) share
# ---------------------------------------------------------------------------
@dataclass
class ItsResult:
    name: str
    model: sm.regression.linear_model.RegressionResultsWrapper
    data: pd.DataFrame
    break_quarter: pd.Timestamp


def _its_frame(quarterly: pd.DataFrame, break_quarter: pd.Timestamp, banks: list[str]) -> pd.DataFrame:
    d = quarterly[quarterly["short_name"].isin(banks)].copy()
    quarters = sorted(d["quarter_end_date"].unique())
    index = {q: i for i, q in enumerate(quarters)}
    d["t"] = d["quarter_end_date"].map(index)
    t_break = index[break_quarter]
    d["post"] = (d["t"] >= t_break).astype(int)
    d["t_after"] = (d["t"] - t_break).clip(lower=0)
    d["stage3_bps"] = d["stage3_share"] * 1e4
    return d.sort_values(["short_name", "t"]).reset_index(drop=True)


def fit_interrupted_time_series(
    quarterly: pd.DataFrame,
    break_quarter: pd.Timestamp = FIRST_POST_HIKE_QUARTER,
    exclude: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    maxlags: int = 4,
) -> dict[str, ItsResult]:
    """Segmented regression: stage3_bps = level + pre-trend + jump + change in trend.

    panel     the six banks, a separate intercept per bank, Driscoll-Kraay
              standard errors (robust to autocorrelation, unequal variance and
              shocks that hit all banks in the same quarter)
    aggregate the Big Six combined series, Newey-West standard errors
    """
    results = {}
    panel = _its_frame(quarterly, break_quarter, BANK_ORDER)
    aggregate = _its_frame(quarterly, break_quarter, ["Big Six"])
    if exclude is not None:
        lo, hi = exclude
        keep = lambda d: d[~d["quarter_end_date"].between(lo, hi)]  # noqa: E731
        panel, aggregate = keep(panel), keep(aggregate)

    panel_model = smf.ols("stage3_bps ~ C(short_name) + t + post + t_after", data=panel).fit(
        cov_type="hac-groupsum", cov_kwds={"time": panel["t"].to_numpy(), "maxlags": maxlags}
    )
    agg_model = smf.ols("stage3_bps ~ t + post + t_after", data=aggregate).fit(
        cov_type="HAC", cov_kwds={"maxlags": maxlags}
    )
    results["panel"] = ItsResult("Six banks, bank fixed effects", panel_model, panel, break_quarter)
    results["aggregate"] = ItsResult("Big Six combined", agg_model, aggregate, break_quarter)
    return results


def its_summary(results: dict[str, ItsResult], label: str = "") -> pd.DataFrame:
    """One row per model: pre-trend, post-trend, change in trend, jump, p-values."""
    rows = []
    for key, res in results.items():
        m = res.model
        pre, change = m.params["t"], m.params["t_after"]
        # standard error of the post-break slope (pre + change) from the covariance matrix
        cov = m.cov_params()
        post_se = np.sqrt(cov.loc["t", "t"] + cov.loc["t_after", "t_after"] + 2 * cov.loc["t", "t_after"])
        rows.append({
            "specification": label or "Main",
            "model": res.name,
            "break_quarter": res.break_quarter.date(),
            "n_obs": int(m.nobs),
            "pre_trend_bps_per_qtr": pre,
            "pre_trend_p": m.pvalues["t"],
            "post_trend_bps_per_qtr": pre + change,
            "post_trend_se": post_se,
            "trend_change_bps_per_qtr": change,
            "trend_change_p": m.pvalues["t_after"],
            "level_jump_bps": m.params["post"],
            "level_jump_p": m.pvalues["post"],
            "r_squared": m.rsquared,
        })
    return pd.DataFrame(rows)


def its_diagnostics(result: ItsResult) -> pd.DataFrame:
    """Assumption checks for a fitted segmented regression."""
    m = result.model
    resid = m.resid
    exog = m.model.exog
    names = m.model.exog_names
    bp_stat, bp_p, _, _ = het_breuschpagan(resid, exog)
    jb_stat, jb_p, _, _ = jarque_bera(resid)
    lb = acorr_ljungbox(resid, lags=[4], return_df=True)
    trend_cols = [i for i, n in enumerate(names) if n in ("t", "post", "t_after")]
    vifs = {names[i]: variance_inflation_factor(exog, i) for i in trend_cols}
    return pd.DataFrame([
        {"check": "Residual autocorrelation (Durbin-Watson)", "value": durbin_watson(resid),
         "reading": "about 2 = none; well below 2 = positive autocorrelation",
         "response": "HAC / Driscoll-Kraay standard errors"},
        {"check": "Residual autocorrelation (Ljung-Box, 4 lags), p-value", "value": lb["lb_pvalue"].iloc[0],
         "reading": "p < 0.05 = autocorrelated", "response": "HAC / Driscoll-Kraay standard errors"},
        {"check": "Unequal variance (Breusch-Pagan), p-value", "value": bp_p,
         "reading": "p < 0.05 = heteroskedastic", "response": "robust standard errors"},
        {"check": "Normal residuals (Jarque-Bera), p-value", "value": jb_p,
         "reading": "p < 0.05 = not normal", "response": "large-sample robust inference; read p-values with care"},
        *[{"check": f"Variance inflation factor: {k}", "value": v,
           "reading": "> 10 = strong overlap between trend terms",
           "response": "expected for segmented trends; slopes are read jointly"} for k, v in vifs.items()],
    ])


def its_fitted_values(results: dict[str, ItsResult]) -> pd.DataFrame:
    """Fitted line and the 'no break' counterfactual for the combined series."""
    res = results["aggregate"]
    d = res.data.copy()
    d["fitted_bps"] = res.model.fittedvalues
    p = res.model.params
    d["pre_trend_extended_bps"] = p["Intercept"] + p["t"] * d["t"]
    return d[["quarter_end_date", "t", "post", "stage3_bps", "fitted_bps", "pre_trend_extended_bps"]]


# ---------------------------------------------------------------------------
# 3. Migration sensitivity
# ---------------------------------------------------------------------------
def migration_sensitivity(quarterly: pd.DataFrame, quarter: pd.Timestamp | None = None,
                          share_moved: float = 0.01) -> pd.DataFrame:
    """Extra allowance if `share_moved` of the whole book left Stage 1, at today's coverage.

    Uses each bank's own coverage per stage in the chosen quarter, so it answers
    "what would 1% of the book migrating cost this bank, with its current models?"
    """
    quarter = quarter or quarterly["quarter_end_date"].max()
    q = quarterly[quarterly["quarter_end_date"] == quarter].set_index("short_name")
    rows = []
    for bank in ["Big Six", *BANK_ORDER]:
        p = q.loc[bank]
        book = p["gross_total_cad_mn"]
        c1 = p["ecl_s1_cad_mn"] / p["gross_s1_cad_mn"]
        c2 = p["ecl_s2_cad_mn"] / p["gross_s2_cad_mn"]
        c3 = p["ecl_s3_cad_mn"] / p["gross_s3_cad_mn"]
        to_s2 = share_moved * book * (c2 - c1)
        to_s3 = share_moved * book * (c3 - c1)
        rows.append({
            "short_name": bank,
            "quarter_end_date": quarter.date(),
            "book_cad_mn": book,
            "ecl_cad_mn": p["ecl_total_cad_mn"],
            "coverage_s1_pct": c1 * 100,
            "coverage_s2_pct": c2 * 100,
            "coverage_s3_pct": c3 * 100,
            "moved_cad_mn": share_moved * book,
            "extra_ecl_if_to_stage2_cad_mn": to_s2,
            "extra_ecl_if_to_stage2_pct_of_ecl": to_s2 / p["ecl_total_cad_mn"],
            "extra_ecl_if_to_stage3_cad_mn": to_s3,
            "extra_ecl_if_to_stage3_pct_of_ecl": to_s3 / p["ecl_total_cad_mn"],
        })
    return pd.DataFrame(rows)


def main() -> None:
    quarterly = load("resi_mortgage_quarterly")
    monthly = load("m4_resi_monthly")

    decomposition = decompose_allowance_change(quarterly, monthly)
    decomposition.to_csv(PROCESSED / "allowance_decomposition.csv", index=False)

    main_fit = fit_interrupted_time_series(quarterly)
    specs = [its_summary(main_fit, "Main: break at first post-hike quarter (Apr 2022)")]
    for q in ["2022-07-31", "2022-10-31", "2023-01-31"]:
        specs.append(its_summary(fit_interrupted_time_series(quarterly, pd.Timestamp(q)),
                                 f"Robustness: break at {pd.Timestamp(q):%b %Y}"))
    specs.append(its_summary(
        fit_interrupted_time_series(quarterly, exclude=(pd.Timestamp("2020-04-30"), pd.Timestamp("2021-10-31"))),
        "Robustness: pandemic deferral quarters (Apr 2020-Oct 2021) removed"))
    pd.concat(specs, ignore_index=True).to_csv(PROCESSED / "its_results.csv", index=False)
    its_fitted_values(main_fit).to_csv(PROCESSED / "its_fitted.csv", index=False)
    pd.concat([its_diagnostics(main_fit["panel"]).assign(model="panel"),
               its_diagnostics(main_fit["aggregate"]).assign(model="aggregate")]
              ).to_csv(PROCESSED / "its_diagnostics.csv", index=False)

    migration_sensitivity(quarterly).to_csv(PROCESSED / "migration_sensitivity.csv", index=False)
    print("Wrote allowance_decomposition, its_results, its_fitted, its_diagnostics, migration_sensitivity")


if __name__ == "__main__":
    main()
