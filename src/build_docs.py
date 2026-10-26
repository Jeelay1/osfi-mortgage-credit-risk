"""Generate the reference docs from the data, so they never drift from it.

    docs/data_dictionary.md    every exported table and column, with units
    docs/data_quality_log.md   the automated checks and what was done about each
    docs/dashboards.md         how to open the Power BI and Tableau files, what is on
                               each page, the measures, and the numbers to expect

Usage:
    python src/build_docs.py
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
DOCS = ROOT / "docs"
TMDL = ROOT / "powerbi" / "MortgageCreditRisk.SemanticModel" / "definition"
BANKS = ["RBC", "TD", "BNS", "BMO", "CIBC", "NBC"]

M = "$ millions"
FRAC = "fraction (0.05 = 5%)"
TABLES: dict[str, tuple[str, dict[str, str]]] = {
    "dim_bank": ("Banks in the analysis, plus a 'Big Six' row for the combined figures.", {
        "bank_id": "OSFI institution id (0 = Big Six combined)",
        "short_name": "Short name used in every chart",
        "bank_name": "Legal name in the latest filing",
        "bank_role": "big_six, acquired (HSBC Bank Canada, Canadian Western Bank) or aggregate",
        "fiscal_year_end_month": "Month the bank's fiscal year ends (10 = October)",
        "name_history": "Every name the institution has filed under, oldest first",
        "sort_order": "Fixed display order; also fixes each bank's colour",
        "color_hex": "Bank colour used in the notebook, Power BI and Tableau",
    }),
    "dim_month": ("One row per calendar month, Jan 2017 to Dec 2026.", {
        "month_end_date": "Calendar month-end date",
        "calendar_year": "Calendar year",
        "calendar_month": "Calendar month number",
        "month_label": "Label such as 'Apr 2026'",
        "calendar_quarter_label": "Calendar quarter label such as 'Q2 2026'",
        "big6_fiscal_year": "Big Six fiscal year (November to October)",
        "big6_fiscal_quarter": "Big Six fiscal quarter (1 = Nov to Jan)",
        "is_big6_quarter_end": "True for January, April, July and October",
        "rate_cycle_phase": "Pre-pandemic; pandemic emergency rates (from Mar 2020); rate hikes (from Mar 2022); "
                            "rate cuts (from Jun 2024)",
    }),
    "fact_credit_stage": ("OSFI E3 at its natural grain: bank x fiscal quarter x product x insurance status x "
                          "IFRS 9 stage (Big Six only).", {
        "bank_id": "OSFI institution id",
        "short_name": "Bank",
        "quarter_end_date": "Calendar date the fiscal quarter ends",
        "fiscal_year": "Bank's fiscal year",
        "fiscal_quarter": "Bank's fiscal quarter",
        "fiscal_quarter_label": "OSFI label such as 'Q2 - 2026'",
        "product": "Residential mortgages, Non-residential mortgages, Personal loans (incl. cards), Credit cards",
        "insurance_status": "All, Insured or Uninsured (insured = All minus Uninsured; residential mortgages only)",
        "stage": "IFRS 9 stage (1, 2, 3)",
        "stage_name": "Stage label",
        "gross_exposure_cad_mn": f"Gross carrying amount, {M}",
        "ecl_cad_mn": f"Allowance for expected credit losses, {M}",
        "ecl_basis": "Reported ECL (fiscal 2019+) or individual + collective allowance (fiscal 2018)",
    }),
    "resi_mortgage_quarterly": ("Residential mortgages by bank and quarter, with the Big Six combined "
                                "(bank_id 0) and the ratios used throughout.", {
        "bank_id": "OSFI institution id (0 = Big Six combined)",
        "short_name": "Bank or 'Big Six'",
        "quarter_end_date": "Calendar date the fiscal quarter ends",
        "fiscal_year": "Fiscal year",
        "fiscal_quarter": "Fiscal quarter",
        "fiscal_quarter_label": "OSFI label such as 'Q2 - 2026'",
        "rate_cycle_phase": "Rate-cycle phase of the quarter-end month",
        "gross_total_cad_mn": f"Gross exposure, all stages, {M}",
        "gross_s1_cad_mn": f"Gross exposure, Stage 1, {M}",
        "gross_s2_cad_mn": f"Gross exposure, Stage 2, {M}",
        "gross_s3_cad_mn": f"Gross exposure, Stage 3, {M}",
        "ecl_total_cad_mn": f"Allowance, all stages, {M}",
        "ecl_s1_cad_mn": f"Allowance, Stage 1, {M}",
        "ecl_s2_cad_mn": f"Allowance, Stage 2, {M}",
        "ecl_s3_cad_mn": f"Allowance, Stage 3, {M}",
        "net_total_cad_mn": f"Gross exposure minus allowance, {M}",
        "gross_uninsured_cad_mn": f"Gross exposure, uninsured, {M} (blank until reported)",
        "ecl_uninsured_cad_mn": f"Allowance, uninsured, {M}",
        "gross_insured_cad_mn": f"Gross exposure, insured, {M}",
        "ecl_insured_cad_mn": f"Allowance, insured, {M}",
        "stage2_share": f"Stage 2 gross / total gross, {FRAC}",
        "stage3_share": f"Stage 3 gross / total gross, {FRAC}",
        "coverage_bps": "Allowance / gross exposure, basis points",
        "coverage_s1_bps": "Stage 1 allowance / Stage 1 gross, basis points",
        "coverage_s2_pct": "Stage 2 allowance / Stage 2 gross, percent (1.4 = 1.4%)",
        "coverage_s3_pct": "Stage 3 allowance / Stage 3 gross, percent",
        "uninsured_share": f"Uninsured gross / total gross, {FRAC}",
        "uninsured_stage2_share": f"Stage 2 share within the uninsured book, {FRAC}",
        "uninsured_stage3_share": f"Stage 3 share within the uninsured book, {FRAC}",
        "coverage_uninsured_bps": "Coverage on uninsured mortgages, basis points",
        "coverage_insured_bps": "Coverage on insured mortgages, basis points",
        "uninsured_share_of_ecl": f"Uninsured allowance / total allowance, {FRAC}",
        "gross_yoy_growth": f"Gross exposure vs four quarters earlier, {FRAC}",
        "stage2_share_yoy_pp": "Change in Stage 2 share vs four quarters earlier, percentage points",
        "stage3_share_yoy_pp": "Change in Stage 3 share vs four quarters earlier, percentage points",
        "coverage_yoy_bps": "Change in coverage vs four quarters earlier, basis points",
        "gross_s2_qoq_change": f"Stage 2 exposure vs the previous quarter, {FRAC}",
        "stage3_rank": "Rank among the six banks by Stage 3 share (1 = highest)",
        "is_acquisition_quarter": "True in the first quarter an acquired bank is consolidated",
    }),
    "m4_resi_monthly": ("OSFI M4: monthly residential mortgage balances (net of allowance) by bank, to the last "
                        "complete month.", {
        "bank_id": "OSFI institution id",
        "short_name": "Bank",
        "month_end_date": "Calendar month-end",
        "rate_cycle_phase": "Rate-cycle phase",
        "insured_cad_mn": f"Insured residential mortgages, {M}",
        "uninsured_cad_mn": f"Uninsured residential mortgages, {M}",
        "reverse_mortgages_cad_mn": f"Reverse mortgages (reported on their own line), {M}",
        "resi_total_cad_mn": f"Insured + uninsured + reverse mortgages, {M}",
        "insured_foreign_ccy_cad_mn": f"Insured mortgages booked in foreign currency, {M}",
        "uninsured_foreign_ccy_cad_mn": f"Uninsured mortgages booked in foreign currency, {M}",
        "total_assets_cad_mn": f"Total assets, {M}",
        "insured_share": f"Insured / (insured + uninsured), {FRAC}",
        "foreign_currency_share": f"Foreign-currency mortgages / (insured + uninsured), {FRAC}",
        "resi_share_of_assets": f"Residential mortgages / total assets, {FRAC}",
        "mom_change_cad_mn": f"Change from the previous month, {M}",
        "yoy_growth": f"Growth vs 12 months earlier, as reported, {FRAC}",
        "organic_yoy_growth": f"Growth vs 12 months earlier with acquired books removed, {FRAC}",
        "acquired_in_yoy_window_cad_mn": f"Acquired book carried for the 12 months it inflates growth, {M}",
        "is_acquisition_month": "True in the month an acquired bank is first consolidated",
    }),
    "e3_m4_reconciliation": ("E3 net residential mortgages compared with M4 at each quarter-end.", {
        "bank_id": "OSFI institution id",
        "short_name": "Bank",
        "quarter_end_date": "Quarter-end date",
        "e3_gross_cad_mn": f"E3 gross exposure, {M}",
        "e3_ecl_cad_mn": f"E3 allowance, {M}",
        "e3_net_cad_mn": f"E3 gross minus allowance, {M}",
        "m4_resi_excl_reverse_cad_mn": f"M4 insured + uninsured mortgages, {M}",
        "m4_reverse_mortgages_cad_mn": f"M4 reverse mortgages, {M}",
        "gap_cad_mn": f"E3 net minus M4 (excluding reverse mortgages), {M}",
        "gap_pct": f"Gap / E3 net, {FRAC}",
        "gap_pct_incl_reverse": f"Gap after adding reverse mortgages to M4 / E3 net, {FRAC}",
        "status": "Reconciles; reconciles once reverse mortgages are added; small gap (< 0.5%); open item (> 0.5%)",
    }),
    "period_alignment_test": ("Which month offset lines E3's fiscal quarters up with M4's calendar months "
                              "(checks each bank's fiscal year-end).", {
        "bank_id": "OSFI institution id",
        "short_name": "Bank",
        "fiscal_year_end_month": "Fiscal year-end month assumed",
        "month_offset": "Months E3 is shifted against M4 (-3 to +3)",
        "median_abs_gap_pct": f"Median absolute level gap between E3 net and M4, {FRAC}",
        "change_correlation": "Correlation of quarter-on-quarter changes in E3 with 3-month changes in M4",
        "n_quarters": "Quarters compared",
        "is_best_offset": "True for the offset with the highest change correlation",
    }),
    "subsidiary_double_count": ("Does adding up every domestic bank double count subsidiaries? (total assets)", {
        "month_end_date": "Month-end",
        "n_domestic_banks_reporting": "Domestic banks that filed M4 that month",
        "osfi_total_domestic_cad_mn": f"OSFI's own 'Total Domestic Banks' line, {M}",
        "sum_of_domestic_banks_cad_mn": f"Sum of the individual domestic banks, {M}",
        "overstatement_cad_mn": f"Sum minus OSFI total, {M}",
        "identified_subsidiaries_cad_mn": f"Assets of subsidiaries already inside a parent's return, {M}",
        "unexplained_cad_mn": f"Overstatement not explained by those subsidiaries, {M}",
        "overstatement_pct": f"Overstatement / OSFI total, {FRAC}",
    }),
    "dq_checks": ("The automated data-quality checks (see data_quality_log.md).", {
        "check_id": "Check id", "area": "Quality dimension", "check_name": "What is checked",
        "status": "Pass, Handled (issue found and fixed), Warning (disclosed) or Open",
        "metric": "What was measured", "finding": "What the check found", "action": "What was done about it",
    }),
    "allowance_decomposition": ("Shapley decomposition of the change in residential mortgage allowance, "
                                "Jan 2022 to the latest quarter.", {
        "short_name": "Bank or 'Big Six'",
        "start_quarter": "Start quarter (last quarter-end before the first hike)",
        "end_quarter": "End quarter (latest)",
        "ecl_start_cad_mn": f"Allowance at the start, {M}",
        "ecl_end_cad_mn": f"Allowance at the end, {M}",
        "ecl_change_cad_mn": f"Change in allowance, {M}",
        "ecl_change_pct": f"Change in allowance, {FRAC}",
        "book_start_cad_mn": f"Gross exposure at the start, {M}",
        "book_end_cad_mn": f"Gross exposure at the end, {M}",
        "acquired_book_cad_mn": f"Book bought through acquisitions inside the window, {M}",
        "volume_organic_cad_mn": f"Part of the change from organic book growth, {M}",
        "volume_acquired_cad_mn": f"Part of the change from acquired books, {M}",
        "stage_mix_cad_mn": f"Part of the change from loans moving between stages, {M}",
        "coverage_rate_cad_mn": f"Part of the change from coverage within each stage, {M}",
        "check_sum_cad_mn": f"Parts minus total change (zero by construction), {M}",
    }),
    "its_results": ("Interrupted time-series results: main model and robustness checks.", {
        "specification": "Main model or robustness variant",
        "model": "Six banks with bank fixed effects (Driscoll-Kraay errors) or Big Six combined (Newey-West)",
        "break_quarter": "First quarter of the post-hike segment",
        "n_obs": "Observations",
        "pre_trend_bps_per_qtr": "Trend before the break, basis points a quarter",
        "pre_trend_p": "p-value of the pre-break trend",
        "post_trend_bps_per_qtr": "Trend after the break, basis points a quarter",
        "post_trend_se": "Standard error of the post-break trend",
        "trend_change_bps_per_qtr": "Change in trend at the break, basis points a quarter",
        "trend_change_p": "p-value of the trend change",
        "level_jump_bps": "Level shift at the break, basis points",
        "level_jump_p": "p-value of the level shift",
        "r_squared": "R-squared",
    }),
    "its_fitted": ("Big Six Stage 3 share with the model fit, for charts.", {
        "quarter_end_date": "Quarter-end", "t": "Quarter number (0 = Jan 2018)",
        "post": "1 from the break quarter on", "stage3_bps": "Actual Stage 3 share, basis points",
        "fitted_bps": "Model fit, basis points",
        "pre_trend_extended_bps": "Pre-hike trend carried forward, basis points",
    }),
    "its_diagnostics": ("Residual diagnostics for the time-series models.", {
        "check": "Diagnostic", "value": "Statistic or p-value", "reading": "How to read it",
        "response": "What the model does about it", "model": "panel or aggregate",
    }),
    "migration_sensitivity": ("Extra allowance if 1% of the book left Stage 1, at each bank's current "
                              "coverage rates.", {
        "short_name": "Bank or 'Big Six'", "quarter_end_date": "Quarter used (latest)",
        "book_cad_mn": f"Gross exposure, {M}", "ecl_cad_mn": f"Allowance, {M}",
        "coverage_s1_pct": "Stage 1 coverage, percent", "coverage_s2_pct": "Stage 2 coverage, percent",
        "coverage_s3_pct": "Stage 3 coverage, percent", "moved_cad_mn": f"1% of the book, {M}",
        "extra_ecl_if_to_stage2_cad_mn": f"Extra allowance if it moved to Stage 2, {M}",
        "extra_ecl_if_to_stage2_pct_of_ecl": f"Same, as a share of today's allowance, {FRAC}",
        "extra_ecl_if_to_stage3_cad_mn": f"Extra allowance if it moved to Stage 3, {M}",
        "extra_ecl_if_to_stage3_pct_of_ecl": f"Same, as a share of today's allowance, {FRAC}",
    }),
}


def data_dictionary() -> str:
    lines = ["# Data dictionary", "",
             "Tables exported to `data/processed/` by `src/export_marts.py` and `src/analysis.py`. "
             "They feed the notebook, the Power BI report and the Tableau workbook. Generated by "
             "`src/build_docs.py` from the files themselves.", "",
             "**Units.** OSFI reports thousands of dollars; every money column here is in millions of Canadian "
             "dollars (`_cad_mn`). Ratios are fractions unless the name ends in `_bps` (basis points, "
             "1 bp = 0.01%) or `_pp` (percentage points), or the description says percent.", ""]
    for name, (desc, cols) in TABLES.items():
        df = pd.read_csv(PROCESSED / f"{name}.csv")
        missing = set(df.columns) ^ set(cols)
        assert not missing, f"{name}: columns not documented or no longer exported: {missing}"
        lines += [f"## `{name}`", "", f"{desc} {len(df):,} rows.", "", "| Column | Description |", "|---|---|"]
        lines += [f"| `{c}` | {cols[c]} |" for c in df.columns]
        lines.append("")
    lines += ["## Source files", "",
              "| File | What it is |", "|---|---|",
              "| `data/raw/banks_quarterly_e3.csv.gz` | OSFI E3, Return of Allowances for Expected Credit Losses "
              "(quarterly, all banks, all years) |",
              "| `data/interim/m4_focus_2017plus.csv.gz` | OSFI M4, Consolidated Balance Sheet: every line from "
              "2017 for the 16 institutions studied (made by `src/extract_m4.py`) |",
              "| `data/interim/m4_all_institutions_keylines_2017plus.csv.gz` | OSFI M4: six headline lines from "
              "2017 for every bank |",
              "| `data/raw/data-dictionary-banks.xlsx` | OSFI's data dictionary for the files above |", ""]
    return "\n".join(lines)


def data_quality_log() -> str:
    dq = pd.read_csv(PROCESSED / "dq_checks.csv")
    counts = dq["status"].value_counts()
    lines = ["# Data-quality log", "",
             f"{len(dq)} checks run in PostgreSQL (`sql/04_quality_checks.sql`) every time the warehouse is "
             "rebuilt. Status: **Pass** (no issue), **Handled** (issue found and fixed in the SQL layer), "
             "**Warning** (issue disclosed next to the results it affects), **Open** (unexplained, worked "
             "around).", "",
             " · ".join(f"{s}: {counts.get(s, 0)}" for s in ["Pass", "Handled", "Warning", "Open"]), "",
             "| ID | Area | Check | Status | Measured |", "|---|---|---|---|---|"]
    lines += [f"| {r.check_id} | {r.area} | {r.check_name} | {r.status} | {r.metric} |" for r in dq.itertuples()]
    lines.append("")
    for r in dq.itertuples():
        lines += [f"### {r.check_id}: {r.check_name}", "", f"**Status:** {r.status} · **Measured:** {r.metric}",
                  "", f"**Finding.** {r.finding}", "", f"**Action.** {r.action}", ""]
    return "\n".join(lines)


def measures_by_folder() -> dict[str, list[tuple[str, str]]]:
    text = (TMDL / "tables" / "Key Measures.tmdl").read_text(encoding="utf-8")
    out: dict[str, list[tuple[str, str]]] = {}
    for block in re.split(r"\n(?=\t(?:///|measure ))", text):
        m = re.search(r"^\tmeasure ('(?:[^']|'')+'|\S+) =", block, re.M)
        if not m:
            continue
        name = m.group(1).strip("'").replace("''", "'")
        desc = " ".join(re.findall(r"^\t/// (.*)$", block, re.M))
        folder = re.search(r"displayFolder: (.+)$", block, re.M).group(1).strip()
        out.setdefault(folder, []).append((name, desc))
    return dict(sorted(out.items(), key=lambda kv: int(kv[0].split(".")[0])))


def expected_values() -> list[tuple[str, str, str]]:
    """What the Power BI report shows with no slicers set, computed independently from the CSVs."""
    f = pd.read_csv(PROCESSED / "fact_credit_stage.csv", parse_dates=["quarter_end_date"])
    m4 = pd.read_csv(PROCESSED / "m4_resi_monthly.csv", parse_dates=["month_end_date"])
    rec = pd.read_csv(PROCESSED / "e3_m4_reconciliation.csv", parse_dates=["quarter_end_date"])
    dq = pd.read_csv(PROCESSED / "dq_checks.csv")
    drv = pd.read_csv(PROCESSED / "allowance_decomposition.csv").set_index("short_name")

    def view(quarter, banks=BANKS, insurance="All"):
        s = f[(f["quarter_end_date"] == quarter) & f["short_name"].isin(banks)
              & (f["product"] == "Residential mortgages") & (f["insurance_status"] == insurance)]
        g = s.groupby("stage")[["gross_exposure_cad_mn", "ecl_cad_mn"]].sum()
        tg, te = g["gross_exposure_cad_mn"].sum(), g["ecl_cad_mn"].sum()
        return {"gross": tg, "ecl": te, "s2": g.loc[2, "gross_exposure_cad_mn"] / tg,
                "s3": g.loc[3, "gross_exposure_cad_mn"] / tg, "cov": te / tg * 1e4,
                "c1": g.loc[1, "ecl_cad_mn"] / g.loc[1, "gross_exposure_cad_mn"],
                "c2": g.loc[2, "ecl_cad_mn"] / g.loc[2, "gross_exposure_cad_mn"],
                "c3": g.loc[3, "ecl_cad_mn"] / g.loc[3, "gross_exposure_cad_mn"]}

    q = f["quarter_end_date"].max()
    now, then = view(q), view(q - pd.offsets.MonthEnd(12))
    per = {b: view(q, [b]) for b in BANKS}
    s3_order = sorted(BANKS, key=lambda b: -per[b]["s3"])
    unins = {b: view(q, [b], "Uninsured")["cov"] for b in BANKS}
    ins = {b: view(q, [b], "Insured")["cov"] for b in BANKS}
    big = drv.loc["Big Six"]
    moved = now["gross"] * 0.01
    mm = m4["month_end_date"].max()
    cur, prev = m4[m4["month_end_date"] == mm], m4[m4["month_end_date"] == mm - pd.offsets.MonthEnd(12)]
    ins_m, unins_m = cur["insured_cad_mn"].sum(), cur["uninsured_cad_mn"].sum()
    fc = cur["insured_foreign_ccy_cad_mn"].sum() + cur["uninsured_foreign_ccy_cad_mn"].sum()
    bal, bal_prev, acq = cur["resi_total_cad_mn"].sum(), prev["resi_total_cad_mn"].sum(), \
        cur["acquired_in_yoy_window_cad_mn"].sum()
    gap = rec[rec["quarter_end_date"] == rec["quarter_end_date"].max()].set_index("short_name")["gap_pct"]
    c = dq["status"].value_counts()
    return [
        ("Overview", "Quarter shown", f"{q:%B %-d, %Y}"),
        ("Overview", "Gross exposure", f"${now['gross'] / 1e6:.2f}T ({now['gross'] / then['gross'] - 1:+.1%} vs. a year earlier)"),
        ("Overview", "Stage 2 share", f"{now['s2']:.2%} ({(now['s2'] - then['s2']) * 100:+.2f} pp)"),
        ("Overview", "Stage 3 share", f"{now['s3']:.2%} ({(now['s3'] - then['s3']) * 100:+.2f} pp)"),
        ("Overview", "Allowance", f"${now['ecl'] / 1e3:.2f}bn ({now['ecl'] / then['ecl'] - 1:+.1%})"),
        ("Overview", "Coverage", f"{now['cov']:.1f} bp ({now['cov'] - then['cov']:+.1f} bp)"),
        ("Overview", "Stage 3 share by bank", ", ".join(f"{b} {per[b]['s3']:.2%}" for b in s3_order)),
        ("Allowances", "Bridge, Big Six ($M)",
         f"{big.ecl_start_cad_mn:,.0f} → organic {big.volume_organic_cad_mn:+,.0f}, acquired "
         f"{big.volume_acquired_cad_mn:+,.0f}, stage mix {big.stage_mix_cad_mn:+,.0f}, coverage rates "
         f"{big.coverage_rate_cad_mn:+,.0f} → {big.ecl_end_cad_mn:,.0f}"),
        ("Allowances", "Coverage, insured / uninsured (bp)", ", ".join(f"{b} {ins[b]:.1f} / {unins[b]:.1f}" for b in BANKS)),
        ("Allowances", "What-if total row (1% of book)",
         f"Stage 2: ${moved * (now['c2'] - now['c1']):,.0f}M ({moved * (now['c2'] - now['c1']) / now['ecl']:.1%}); "
         f"Stage 3: {moved * (now['c3'] - now['c1']) / now['ecl']:.1%} of allowance"),
        ("Mortgage book", "Month shown", f"{mm:%B %-d, %Y}"),
        ("Mortgage book", "Residential mortgages", f"${bal / 1e6:.2f}T"),
        ("Mortgage book", "Growth / organic growth", f"{bal / bal_prev - 1:.1%} / {(bal - acq) / bal_prev - 1:.1%}"),
        ("Mortgage book", "Insured / foreign-currency share", f"{ins_m / (ins_m + unins_m):.1%} / {fc / (ins_m + unins_m):.1%}"),
        ("Data quality", "Checks run / passed / handled / flagged",
         f"{len(dq)} / {c.get('Pass', 0)} / {c.get('Handled', 0)} / {c.get('Warning', 0) + c.get('Open', 0)}"),
        ("Data quality", "Reconciliation gap, latest quarter", ", ".join(f"{b} {gap[b]:.2%}" for b in BANKS)),
    ]


def dashboards() -> str:
    folders = measures_by_folder()
    n_measures = sum(len(v) for v in folders.values())
    lines = [
        "# Dashboards", "",
        "Two dashboards read the same exported tables (`data/processed/`), so their numbers match the notebook.", "",
        "## Power BI: `powerbi/MortgageCreditRisk.pbip`", "",
        "A Power BI Project (PBIP): the report is stored in the PBIR format and the semantic model in TMDL, so "
        "every page, visual and DAX measure is a readable text file under version control.", "",
        "**Open it**", "",
        "1. Install Power BI Desktop (Windows, free) and open `powerbi/MortgageCreditRisk.pbip`.",
        "2. The project ships without cached data. Select **Refresh**. The queries read the CSVs straight from "
        "this repository on GitHub; if asked how to connect to `raw.githubusercontent.com`, choose "
        "**Anonymous**.",
        "3. To read a fork or another branch instead, change the `GitHubDataUrl` parameter (**Transform data > "
        "Edit parameters**).", "",
        "**Model**: star schema with `Bank`, `Calendar` (monthly, with Big Six fiscal periods and a fiscal "
        "hierarchy), `Product`, `Insurance` and `Stage` dimensions around three fact tables: `Credit Stage` (E3), "
        "`Mortgage Balances` (M4) and `Reconciliation`. Disconnected tables drive the metric selector, the what-if "
        "scenario and the allowance bridge. Power Query loads every CSV through one function (`fnReadCsv`), "
        "converts $ millions to dollars and types every column with an explicit culture.", "",
        "**Pages**", "",
        "| Page | What it answers |", "|---|---|",
        "| Overview | Where credit quality stands now: exposure, Stage 2 and 3 shares, allowance and coverage, each "
        "with the change on a year earlier; Stage 3 trend and latest ranking by bank |",
        "| Metric explorer | Pick any of six credit metrics and compare banks over time, by fiscal year (heat-mapped "
        "matrix) and on the year-earlier change |",
        "| Allowances | What moved the allowance (bridge for the Big Six or any bank), insured vs. uninsured coverage, "
        "allowance by stage, and a what-if: extra allowance if 0.5-5% of the book left Stage 1 |",
        "| Mortgage book | Monthly balances, insured share, and growth with and without acquisitions |",
        "| Trend model | The interrupted time-series fit from the notebook, with how to read it |",
        "| Data quality | The 22 automated checks and the E3-to-M4 reconciliation gap by bank |", "",
        f"**Measures** ({n_measures}, all in the `Key Measures` table). Balances are semi-additive: every "
        "balance measure takes the latest period in context instead of summing over time, so a card shows the "
        "latest quarter and a fiscal-year matrix shows each year's last quarter. Totals are only shown when every "
        "bank in view has reported.", "",
    ]
    for folder, items in folders.items():
        lines += [f"*{folder.split('. ', 1)[1]}*: " + ", ".join(f"`{n}`" for n, _ in items), ""]
    lines += [
        "**Numbers to expect** with no slicers set (computed independently from the CSVs by `src/build_docs.py`):", "",
        "| Page | Item | Value |", "|---|---|---|"]
    with np.errstate(divide="ignore", invalid="ignore"):
        rows = expected_values()
    lines += [f"| {p} | {i} | {v} |" for p, i, v in rows]
    lines += [
        "",
        "## Tableau: `tableau/OSFI_Mortgage_Credit_Risk.twbx`", "",
        "A packaged workbook: the CSVs and the extracts built from them travel inside it. Open it with Tableau "
        "Public or Tableau Desktop 2022.1 or later.", "",
        "| Dashboard | Sheets | Techniques |", "|---|---|---|",
        "| Credit quality | Metric trend; Latest quarter by bank; Change from low | Parameter-driven metric "
        "(`CASE` on a parameter), dynamic sheet title, nested FIXED level-of-detail expressions (each bank's own "
        "low point and the quarter it happened), `RANK` table calculation, fixed bank colours |",
        "| Mortgage book | Mortgage balances; Insured share | Monthly continuous dates, ratio-of-sums "
        "calculations |", "",
        "Both data sources ship as Hyper extracts built from the packaged CSVs, because Tableau Public only opens "
        "workbooks whose data are extracts. **Publish to Tableau Public**: open the workbook in Tableau Public, "
        "then **File > Save to Tableau Public As...**.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    for name, text in [("data_dictionary.md", data_dictionary()), ("data_quality_log.md", data_quality_log()),
                       ("dashboards.md", dashboards())]:
        (DOCS / name).write_text(text, encoding="utf-8")
        print(f"Wrote docs/{name}")


if __name__ == "__main__":
    main()
