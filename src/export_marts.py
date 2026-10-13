"""Export the mart tables to CSV for the notebook, Power BI and Tableau.

All money columns are converted from OSFI's thousands of dollars to
millions of Canadian dollars (suffix _cad_mn). Ratios are fractions (0.05 = 5%)
unless the name ends in _bps (basis points) or _pp (percentage points); the
per-stage coverage columns coverage_s2_pct and coverage_s3_pct are in percent.
docs/data_dictionary.md gives the unit of every column.

Usage:
    python src/export_marts.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5433/osfi")

# One fixed bank order (the usual Big Six listing) fixes each bank's colour slot
# everywhere: notebook, Power BI theme and Tableau palette.
BANK_ORDER = ["RBC", "TD", "BNS", "BMO", "CIBC", "NBC"]
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

QUERIES = {
    "dim_bank": """
        SELECT bank_id, short_name, bank_name, bank_role, fiscal_year_end_month, name_history
        FROM core.dim_bank
        WHERE bank_role IN ('big_six', 'acquired')
        ORDER BY bank_id
    """,
    "dim_month": "SELECT * FROM core.dim_month ORDER BY month_end_date",
    "fact_credit_stage": """
        SELECT s.bank_id, s.short_name, s.quarter_end_date, s.fiscal_year, s.fiscal_quarter,
               s.fiscal_quarter_label, s.product, s.insurance_status, s.stage, s.stage_name,
               s.gross_exposure_cad_k / 1000.0 AS gross_exposure_cad_mn,
               s.ecl_cad_k / 1000.0            AS ecl_cad_mn,
               s.ecl_basis
        FROM mart.credit_stage s
        JOIN core.dim_bank b USING (bank_id)
        WHERE b.is_big_six
        ORDER BY s.bank_id, s.quarter_end_date, s.product COLLATE "C", s.insurance_status COLLATE "C", s.stage
    """,
    "resi_mortgage_quarterly": """
        SELECT bank_id, short_name, quarter_end_date, fiscal_year, fiscal_quarter, fiscal_quarter_label,
               rate_cycle_phase,
               gross_total / 1000.0 AS gross_total_cad_mn,
               gross_s1 / 1000.0 AS gross_s1_cad_mn, gross_s2 / 1000.0 AS gross_s2_cad_mn,
               gross_s3 / 1000.0 AS gross_s3_cad_mn,
               ecl_total / 1000.0 AS ecl_total_cad_mn,
               ecl_s1 / 1000.0 AS ecl_s1_cad_mn, ecl_s2 / 1000.0 AS ecl_s2_cad_mn,
               ecl_s3 / 1000.0 AS ecl_s3_cad_mn,
               net_total / 1000.0 AS net_total_cad_mn,
               gross_uninsured / 1000.0 AS gross_uninsured_cad_mn,
               ecl_uninsured / 1000.0 AS ecl_uninsured_cad_mn,
               gross_insured / 1000.0 AS gross_insured_cad_mn,
               ecl_insured / 1000.0 AS ecl_insured_cad_mn,
               stage2_share, stage3_share, coverage_bps, coverage_s1_bps, coverage_s2_pct,
               coverage_s3_pct, uninsured_share, uninsured_stage2_share, uninsured_stage3_share,
               coverage_uninsured_bps, coverage_insured_bps, uninsured_share_of_ecl,
               gross_yoy_growth, stage2_share_yoy_pp, stage3_share_yoy_pp, coverage_yoy_bps,
               gross_s2_qoq_change, stage3_rank, is_acquisition_quarter
        FROM mart.resi_mortgage_quarterly
        ORDER BY bank_id, quarter_end_date
    """,
    "m4_resi_monthly": """
        SELECT bank_id, short_name, month_end_date, rate_cycle_phase,
               insured / 1000.0 AS insured_cad_mn, uninsured / 1000.0 AS uninsured_cad_mn,
               reverse_mortgages / 1000.0 AS reverse_mortgages_cad_mn,
               resi_total / 1000.0 AS resi_total_cad_mn,
               insured_foreign_ccy / 1000.0 AS insured_foreign_ccy_cad_mn,
               uninsured_foreign_ccy / 1000.0 AS uninsured_foreign_ccy_cad_mn,
               total_assets / 1000.0 AS total_assets_cad_mn,
               insured_share, foreign_currency_share, resi_share_of_assets,
               mom_change / 1000.0 AS mom_change_cad_mn,
               yoy_growth, organic_yoy_growth,
               acquired_in_yoy_window / 1000.0 AS acquired_in_yoy_window_cad_mn,
               is_acquisition_month
        FROM mart.m4_resi_monthly
        WHERE bank_role = 'big_six'
          AND month_end_date <= (SELECT max(month_end_date) FROM mart.subsidiary_double_count)
        ORDER BY bank_id, month_end_date
    """,
    "e3_m4_reconciliation": """
        SELECT r.bank_id, r.short_name, r.quarter_end_date,
               r.e3_gross / 1000.0 AS e3_gross_cad_mn, r.e3_ecl / 1000.0 AS e3_ecl_cad_mn,
               r.e3_net / 1000.0 AS e3_net_cad_mn,
               r.m4_resi_excl_reverse / 1000.0 AS m4_resi_excl_reverse_cad_mn,
               r.m4_reverse_mortgages / 1000.0 AS m4_reverse_mortgages_cad_mn,
               r.gap_cad_k / 1000.0 AS gap_cad_mn, r.gap_pct, r.gap_pct_incl_reverse, r.status
        FROM mart.e3_m4_reconciliation r
        JOIN core.dim_bank b USING (bank_id)
        WHERE b.is_big_six
        ORDER BY r.bank_id, r.quarter_end_date
    """,
    "period_alignment_test": "SELECT * FROM mart.period_alignment_test ORDER BY bank_id, month_offset",
    "subsidiary_double_count": """
        SELECT month_end_date, n_domestic_banks_reporting,
               osfi_total_domestic / 1000.0 AS osfi_total_domestic_cad_mn,
               sum_of_domestic_banks / 1000.0 AS sum_of_domestic_banks_cad_mn,
               overstatement / 1000.0 AS overstatement_cad_mn,
               identified_subsidiaries / 1000.0 AS identified_subsidiaries_cad_mn,
               unexplained / 1000.0 AS unexplained_cad_mn,
               overstatement_pct
        FROM mart.subsidiary_double_count ORDER BY month_end_date
    """,
    "dq_checks": 'SELECT * FROM mart.dq_checks ORDER BY check_id COLLATE "C"',
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(DATABASE_URL) as conn:
        for name, sql in QUERIES.items():
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                df = pd.DataFrame(cur.fetchall(), columns=cols)
            if name == "dim_bank":
                # Big Six take slots 1-6; the two acquired banks follow in grey
                order = {b: i + 1 for i, b in enumerate(BANK_ORDER)}
                acquired = sorted(df.loc[~df["short_name"].isin(BANK_ORDER), "short_name"])
                order.update({b: len(BANK_ORDER) + i + 1 for i, b in enumerate(acquired)})
                df["sort_order"] = df["short_name"].map(order).astype(int)
                df["color_hex"] = df["short_name"].map(dict(zip(BANK_ORDER, PALETTE))).fillna("#898781")
                df = df.sort_values("sort_order")
                big_six = pd.DataFrame([{
                    "bank_id": 0, "short_name": "Big Six", "bank_name": "Big Six banks combined",
                    "bank_role": "aggregate", "fiscal_year_end_month": 10, "name_history": "",
                    "sort_order": 0, "color_hex": "#52514e",
                }])
                df = pd.concat([big_six, df], ignore_index=True)
            # psycopg returns Decimal for numeric columns; store plain floats
            for col in df.columns:
                if df[col].dtype == object and len(df) and df[col].map(type).astype(str).str.contains("Decimal").any():
                    df[col] = df[col].astype(float)
            df.to_csv(OUT / f"{name}.csv", index=False)
            print(f"  wrote {name + '.csv':<32} {len(df):>7,} rows")


if __name__ == "__main__":
    main()
