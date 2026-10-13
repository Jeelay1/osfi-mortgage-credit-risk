"""Invariants the exported tables must satisfy. Run with: pytest -q"""

from __future__ import annotations

import numpy as np
import pandas as pd

from conftest import BIG_SIX, PROCESSED

EXPECTED_FILES = {
    "dim_bank", "dim_month", "fact_credit_stage", "resi_mortgage_quarterly", "m4_resi_monthly",
    "e3_m4_reconciliation", "period_alignment_test", "subsidiary_double_count", "dq_checks",
    "allowance_decomposition", "its_results", "its_fitted", "its_diagnostics", "migration_sensitivity",
}
TOL = 1e-6  # $ millions


def test_every_export_is_present():
    found = {p.stem for p in PROCESSED.glob("*.csv")}
    assert EXPECTED_FILES <= found, EXPECTED_FILES - found


def test_credit_stage_grain_is_unique(credit_stage):
    key = ["bank_id", "quarter_end_date", "product", "insurance_status", "stage"]
    assert not credit_stage.duplicated(key).any()
    assert set(credit_stage["short_name"]) == BIG_SIX
    assert set(credit_stage["stage"]) == {1, 2, 3}
    assert set(credit_stage["insurance_status"]) == {"All", "Insured", "Uninsured"}


def test_quarters_are_big_six_fiscal_quarter_ends(credit_stage):
    # Big Six fiscal years end in October, so quarters end in January, April, July and October
    assert set(credit_stage["quarter_end_date"].dt.month) == {1, 4, 7, 10}
    assert (credit_stage["quarter_end_date"] + pd.offsets.MonthEnd(0) == credit_stage["quarter_end_date"]).all()


def test_insured_plus_uninsured_equals_all(credit_stage):
    resi = credit_stage[credit_stage["product"] == "Residential mortgages"]
    wide = resi.pivot_table(index=["bank_id", "quarter_end_date", "stage"], columns="insurance_status",
                            values="gross_exposure_cad_mn").dropna()
    assert len(wide) > 500
    assert np.allclose(wide["Insured"] + wide["Uninsured"], wide["All"], atol=TOL)


def test_stages_add_up_and_big_six_is_the_sum(quarterly):
    q = quarterly
    assert np.allclose(q["gross_s1_cad_mn"] + q["gross_s2_cad_mn"] + q["gross_s3_cad_mn"], q["gross_total_cad_mn"],
                       atol=TOL)
    b6 = q[q["short_name"] == "Big Six"].set_index("quarter_end_date")["gross_total_cad_mn"]
    banks = q[q["short_name"] != "Big Six"].groupby("quarter_end_date")["gross_total_cad_mn"].sum()
    assert np.allclose(b6.sort_index(), banks.sort_index(), atol=TOL)


def test_mart_agrees_with_fact(credit_stage, quarterly):
    fact = (credit_stage[(credit_stage["product"] == "Residential mortgages")
                         & (credit_stage["insurance_status"] == "All")]
            .groupby(["short_name", "quarter_end_date"])["gross_exposure_cad_mn"].sum())
    mart = quarterly[quarterly["short_name"] != "Big Six"].set_index(["short_name", "quarter_end_date"])
    assert np.allclose(fact.sort_index(), mart["gross_total_cad_mn"].sort_index(), atol=TOL)


def test_shares_are_valid_fractions(quarterly):
    for col in ["stage2_share", "stage3_share", "uninsured_share"]:
        s = quarterly[col].dropna()
        assert s.between(0, 1).all(), col


def test_monthly_balances_are_complete_and_consistent(monthly):
    assert set(monthly["short_name"]) == BIG_SIX
    for _, months in monthly.groupby("short_name")["month_end_date"]:
        gaps = months.sort_values().diff().dropna().dt.days
        assert gaps.between(28, 31).all(), "a month is missing"
    parts = monthly["insured_cad_mn"] + monthly["uninsured_cad_mn"] + monthly["reverse_mortgages_cad_mn"]
    assert np.allclose(parts, monthly["resi_total_cad_mn"], atol=TOL)
    assert monthly["insured_share"].between(0, 1).all()


def test_periods_line_up_at_offset_zero(processed):
    pa = processed("period_alignment_test")
    best = pa[pa["is_best_offset"]].set_index("short_name")["month_offset"]
    assert (best == 0).all(), best[best != 0]


def test_data_quality_log(processed):
    dq = processed("dq_checks")
    assert dq["check_id"].is_unique
    assert set(dq["status"]) <= {"Pass", "Handled", "Warning", "Open"}
    assert dq[["check_name", "finding", "action"]].notna().all().all()
