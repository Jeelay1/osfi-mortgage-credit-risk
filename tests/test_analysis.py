"""Tests for the analysis methods and the results they produced."""

from __future__ import annotations

import numpy as np
import pytest

import analysis as an


def test_shapley_parts_add_up_to_the_total_change():
    # book size, stage mix and coverage by stage, in two periods
    v0, m0, r0 = 100.0, np.array([0.95, 0.04, 0.01]), np.array([0.0005, 0.012, 0.15])
    v1, m1, r1 = 130.0, np.array([0.93, 0.05, 0.02]), np.array([0.0006, 0.014, 0.17])
    parts = an.shapley_three_factor(v0, m0, r0, v1, m1, r1)
    total = parts["volume"] + parts["mix"] + parts["rate"]
    assert total == pytest.approx(v1 * m1 @ r1 - v0 * m0 @ r0)
    assert parts["n_orders"] == 6


def test_shapley_gives_everything_to_the_only_factor_that_moved():
    m, r = np.array([0.9, 0.08, 0.02]), np.array([0.001, 0.01, 0.2])
    parts = an.shapley_three_factor(100.0, m, r, 150.0, m, r)
    assert parts["volume"] == pytest.approx(50 * m @ r)
    assert parts["mix"] == pytest.approx(0.0)
    assert parts["rate"] == pytest.approx(0.0)


def test_decomposition_reconciles_for_every_bank(processed):
    d = processed("allowance_decomposition")
    total = (d["ecl_start_cad_mn"] + d["volume_organic_cad_mn"] + d["volume_acquired_cad_mn"]
             + d["stage_mix_cad_mn"] + d["coverage_rate_cad_mn"])
    assert np.allclose(total, d["ecl_end_cad_mn"], atol=1e-6)
    assert set(d["short_name"]) == {"Big Six", "RBC", "TD", "BNS", "BMO", "CIBC", "NBC"}
    # only the two banks that bought another bank have an acquired book
    acquired = d.set_index("short_name")["volume_acquired_cad_mn"]
    assert (acquired.drop(["Big Six", "RBC", "NBC"]) == 0).all()


def test_trend_turned_up_after_the_hikes_in_every_specification(processed):
    its = processed("its_results")
    assert (its["pre_trend_bps_per_qtr"] < 0).all()
    assert (its["trend_change_bps_per_qtr"] > 0).all()
    assert (its["trend_change_p"] < 0.001).all()


def test_fitted_series_lines_up_with_the_actual(processed):
    fitted = processed("its_fitted")
    assert fitted["quarter_end_date"].is_monotonic_increasing
    pre = fitted[fitted["post"] == 0]
    assert np.allclose(pre["fitted_bps"], pre["pre_trend_extended_bps"])


def test_migration_sensitivity_moves_one_percent(processed):
    mig = processed("migration_sensitivity")
    assert np.allclose(mig["moved_cad_mn"], 0.01 * mig["book_cad_mn"])
    expected = mig["moved_cad_mn"] * (mig["coverage_s3_pct"] - mig["coverage_s1_pct"]) / 100
    assert np.allclose(mig["extra_ecl_if_to_stage3_cad_mn"], expected)
    # moving loans to Stage 3 always costs more than moving them to Stage 2
    assert (mig["extra_ecl_if_to_stage3_cad_mn"] > mig["extra_ecl_if_to_stage2_cad_mn"]).all()


def test_decomposition_function_on_the_exported_tables(quarterly, monthly):
    out = an.decompose_allowance_change(quarterly, monthly)
    assert np.allclose(out["check_sum_cad_mn"], 0, atol=1e-6)
    assert out.set_index("short_name").loc["Big Six", "ecl_change_cad_mn"] > 0
