-- =============================================================================
-- 03_marts.sql
-- Analysis-ready tables. Everything downstream (notebook, Power BI, Tableau)
-- reads these, so each metric is defined once, here.
--
--   mart.credit_stage              long: bank x quarter x product x insurance x stage
--   mart.resi_mortgage_quarterly   wide: one row per bank-quarter (+ a Big Six total)
--   mart.m4_resi_monthly           monthly mortgage balances, growth, acquisitions
--   mart.e3_m4_reconciliation      E3 (quarterly, gross) vs M4 (monthly, net)
--   mart.period_alignment_test     which month each E3 quarter really ends in
--   mart.subsidiary_double_count   why "sum of banks" overstates the industry
-- =============================================================================

-- -----------------------------------------------------------------------------
-- mart.credit_stage
-- Gross exposure ("recorded investment") and allowance (expected credit losses,
-- ECL) by IFRS 9 stage for the Big Six and the two acquired banks.
--   * Fiscal 2018 filings split the allowance into individually and
--     collectively assessed parts; from fiscal 2019 OSFI reports one ECL figure.
--     The two 2018 parts are added together so the series is continuous.
--   * Insured = all residential mortgages minus the "of which uninsured" lines.
--     It is only derived when the bank actually reported the uninsured split
--     (Scotiabank's uninsured lines are blank until fiscal 2021).
-- -----------------------------------------------------------------------------
CREATE TABLE mart.credit_stage AS
WITH lines AS (
    SELECT f.bank_id,
           f.fiscal_year,
           f.fiscal_quarter,
           f.fiscal_quarter_label,
           f.quarter_end_date,
           l.product,
           l.insurance_scope,
           l.ifrs9_stage                                                      AS stage,
           sum(f.value_cad_k) FILTER (WHERE l.measure = 'gross_exposure')     AS gross_exposure,
           sum(f.value_cad_k) FILTER (WHERE l.measure = 'ecl')                AS ecl_reported,
           sum(f.value_cad_k) FILTER (WHERE l.measure IN ('ecl_individual', 'ecl_collective'))
                                                                              AS ecl_components
    FROM core.fact_e3 f
    JOIN core.dim_e3_line l USING (e3_line_key)
    JOIN core.dim_bank b USING (bank_id)
    WHERE b.bank_role IN ('big_six', 'acquired')
      AND l.ifrs9_stage IS NOT NULL
      AND l.product IN ('residential_mortgages', 'non_residential_mortgages',
                        'credit_cards', 'personal_loans_total')
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
),
with_ecl AS (
    SELECT *,
           coalesce(ecl_reported, ecl_components) AS ecl,
           CASE WHEN ecl_reported IS NOT NULL THEN 'Reported ECL (fiscal 2019+)'
                ELSE 'Individual + collective allowance (fiscal 2018)' END AS ecl_basis
    FROM lines
),
uninsured_reported AS (
    SELECT bank_id, fiscal_year, fiscal_quarter,
           coalesce(sum(gross_exposure), 0) > 0 AS is_reported
    FROM with_ecl
    WHERE product = 'residential_mortgages' AND insurance_scope = 'uninsured'
    GROUP BY 1, 2, 3
),
all_and_uninsured AS (
    SELECT w.bank_id, w.fiscal_year, w.fiscal_quarter, w.fiscal_quarter_label, w.quarter_end_date,
           w.product,
           CASE WHEN w.insurance_scope = 'uninsured' THEN 'Uninsured' ELSE 'All' END AS insurance_status,
           w.stage, w.gross_exposure, w.ecl, w.ecl_basis
    FROM with_ecl w
    LEFT JOIN uninsured_reported u USING (bank_id, fiscal_year, fiscal_quarter)
    WHERE w.insurance_scope = 'all'
       OR (w.insurance_scope = 'uninsured' AND u.is_reported)
),
insured AS (
    SELECT a.bank_id, a.fiscal_year, a.fiscal_quarter, a.fiscal_quarter_label, a.quarter_end_date,
           a.product, 'Insured' AS insurance_status, a.stage,
           a.gross_exposure - u.gross_exposure AS gross_exposure,
           a.ecl - u.ecl                       AS ecl,
           a.ecl_basis
    FROM all_and_uninsured a
    JOIN all_and_uninsured u
      ON (u.bank_id, u.fiscal_year, u.fiscal_quarter, u.product, u.stage)
       = (a.bank_id, a.fiscal_year, a.fiscal_quarter, a.product, a.stage)
     AND u.insurance_status = 'Uninsured'
    WHERE a.insurance_status = 'All'
)
SELECT c.bank_id,
       b.short_name,
       c.fiscal_year,
       c.fiscal_quarter,
       c.fiscal_quarter_label,
       c.quarter_end_date,
       CASE c.product
           WHEN 'residential_mortgages'     THEN 'Residential mortgages'
           WHEN 'non_residential_mortgages' THEN 'Non-residential mortgages'
           WHEN 'credit_cards'              THEN 'Credit cards'
           WHEN 'personal_loans_total'      THEN 'Personal loans (incl. cards)'
       END                                   AS product,
       c.insurance_status,
       c.stage,
       CASE c.stage
           WHEN 1 THEN 'Stage 1: performing'
           WHEN 2 THEN 'Stage 2: credit risk up significantly'
           WHEN 3 THEN 'Stage 3: credit-impaired'
       END                                   AS stage_name,
       c.gross_exposure                      AS gross_exposure_cad_k,
       c.ecl                                 AS ecl_cad_k,
       c.ecl_basis
FROM (SELECT * FROM all_and_uninsured UNION ALL SELECT * FROM insured) c
JOIN core.dim_bank b USING (bank_id);

ALTER TABLE mart.credit_stage
    ADD PRIMARY KEY (bank_id, fiscal_year, fiscal_quarter, product, insurance_status, stage);

-- -----------------------------------------------------------------------------
-- mart.resi_mortgage_quarterly
-- One row per bank-quarter for residential mortgages, plus a 'Big Six' total
-- (bank_id 0). All six banks have an October 31 year-end, so their quarter-end
-- dates line up and can be added together.
-- Ratios: stage shares are shares of gross exposure; coverage = ECL / gross,
-- in basis points (1 bp = 0.01%).
-- -----------------------------------------------------------------------------
CREATE TABLE mart.resi_mortgage_quarterly AS
WITH per_bank AS (
    SELECT s.bank_id, s.short_name, s.fiscal_year, s.fiscal_quarter, s.fiscal_quarter_label,
           s.quarter_end_date,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'All')              AS gross_total,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'All' AND stage = 1) AS gross_s1,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'All' AND stage = 2) AS gross_s2,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'All' AND stage = 3) AS gross_s3,
           sum(ecl_cad_k)            FILTER (WHERE insurance_status = 'All')              AS ecl_total,
           sum(ecl_cad_k)            FILTER (WHERE insurance_status = 'All' AND stage = 1) AS ecl_s1,
           sum(ecl_cad_k)            FILTER (WHERE insurance_status = 'All' AND stage = 2) AS ecl_s2,
           sum(ecl_cad_k)            FILTER (WHERE insurance_status = 'All' AND stage = 3) AS ecl_s3,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'Uninsured')        AS gross_uninsured,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'Uninsured' AND stage = 2) AS gross_uninsured_s2,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'Uninsured' AND stage = 3) AS gross_uninsured_s3,
           sum(ecl_cad_k)            FILTER (WHERE insurance_status = 'Uninsured')        AS ecl_uninsured,
           sum(gross_exposure_cad_k) FILTER (WHERE insurance_status = 'Insured')          AS gross_insured,
           sum(ecl_cad_k)            FILTER (WHERE insurance_status = 'Insured')          AS ecl_insured
    FROM mart.credit_stage s
    JOIN core.dim_bank b USING (bank_id)
    WHERE s.product = 'Residential mortgages' AND b.bank_role = 'big_six'
    GROUP BY 1, 2, 3, 4, 5, 6
),
big_six AS (
    SELECT 0 AS bank_id, 'Big Six'::text AS short_name,
           min(fiscal_year) AS fiscal_year, min(fiscal_quarter) AS fiscal_quarter,
           min(fiscal_quarter_label) AS fiscal_quarter_label, quarter_end_date,
           sum(gross_total), sum(gross_s1), sum(gross_s2), sum(gross_s3),
           sum(ecl_total), sum(ecl_s1), sum(ecl_s2), sum(ecl_s3),
           -- the insured/uninsured split is only summed when all six banks report it
           CASE WHEN count(gross_uninsured) = 6 THEN sum(gross_uninsured) END,
           CASE WHEN count(gross_uninsured) = 6 THEN sum(gross_uninsured_s2) END,
           CASE WHEN count(gross_uninsured) = 6 THEN sum(gross_uninsured_s3) END,
           CASE WHEN count(gross_uninsured) = 6 THEN sum(ecl_uninsured) END,
           CASE WHEN count(gross_uninsured) = 6 THEN sum(gross_insured) END,
           CASE WHEN count(gross_uninsured) = 6 THEN sum(ecl_insured) END
    FROM per_bank
    GROUP BY quarter_end_date
    HAVING count(*) = 6
),
combined AS (
    SELECT * FROM per_bank
    UNION ALL
    SELECT * FROM big_six
),
ratios AS (
    SELECT c.*,
           c.gross_total - c.ecl_total                              AS net_total,
           c.gross_s2 / c.gross_total                               AS stage2_share,
           c.gross_s3 / c.gross_total                               AS stage3_share,
           c.ecl_total / c.gross_total * 10000                      AS coverage_bps,
           c.ecl_s1 / nullif(c.gross_s1, 0) * 10000                 AS coverage_s1_bps,
           c.ecl_s2 / nullif(c.gross_s2, 0) * 100                   AS coverage_s2_pct,
           c.ecl_s3 / nullif(c.gross_s3, 0) * 100                   AS coverage_s3_pct,
           c.gross_uninsured / c.gross_total                        AS uninsured_share,
           c.gross_uninsured_s2 / nullif(c.gross_uninsured, 0)      AS uninsured_stage2_share,
           c.gross_uninsured_s3 / nullif(c.gross_uninsured, 0)      AS uninsured_stage3_share,
           c.ecl_uninsured / nullif(c.gross_uninsured, 0) * 10000   AS coverage_uninsured_bps,
           c.ecl_insured / nullif(c.gross_insured, 0) * 10000       AS coverage_insured_bps,
           c.ecl_uninsured / nullif(c.ecl_total, 0)                 AS uninsured_share_of_ecl
    FROM combined c
)
SELECT r.*,
       m.rate_cycle_phase,
       -- year-over-year changes (4 quarters back, same bank)
       r.gross_total / lag(r.gross_total, 4) OVER w - 1             AS gross_yoy_growth,
       (r.stage2_share - lag(r.stage2_share, 4) OVER w) * 100        AS stage2_share_yoy_pp,
       (r.stage3_share - lag(r.stage3_share, 4) OVER w) * 100        AS stage3_share_yoy_pp,
       r.coverage_bps - lag(r.coverage_bps, 4) OVER w                AS coverage_yoy_bps,
       -- quarter-over-quarter change in Stage 2 exposure, used to flag jumps
       r.gross_s2 / nullif(lag(r.gross_s2) OVER w, 0) - 1            AS gross_s2_qoq_change,
       -- peer rank among the six banks (1 = highest impaired share)
       CASE WHEN r.bank_id <> 0 THEN
           rank() OVER (PARTITION BY r.quarter_end_date, (r.bank_id = 0) ORDER BY r.stage3_share DESC)
       END                                                           AS stage3_rank,
       EXISTS (SELECT 1 FROM core.corporate_event e
               WHERE e.acquirer_bank_id = r.bank_id
                 AND e.first_quarter_end_consolidated = r.quarter_end_date) AS is_acquisition_quarter
FROM ratios r
JOIN core.dim_month m ON m.month_end_date = r.quarter_end_date
WINDOW w AS (PARTITION BY r.bank_id ORDER BY r.quarter_end_date);

ALTER TABLE mart.resi_mortgage_quarterly ADD PRIMARY KEY (bank_id, quarter_end_date);

-- -----------------------------------------------------------------------------
-- mart.m4_resi_monthly
-- Monthly residential mortgage balances (net of allowances) from M4.
-- Growth is shown two ways: as reported, and "organic", which removes the
-- acquired book for the 12 months in which it inflates year-over-year growth.
-- The acquired book is the target bank's last reported balance before it was
-- folded into the acquirer.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.m4_resi_monthly AS
WITH balances AS (
    SELECT f.bank_id,
           f.month_end_date,
           sum(f.value_cad_k) FILTER (WHERE f.dpa = '0540') AS insured,
           sum(f.value_cad_k) FILTER (WHERE f.dpa = '0542') AS uninsured,
           coalesce(sum(f.value_cad_k) FILTER (WHERE f.dpa = '0608'), 0) AS reverse_mortgages,
           sum(f.value_cad_k) FILTER (WHERE f.dpa = '0539') AS insured_foreign_ccy,
           sum(f.value_cad_k) FILTER (WHERE f.dpa = '0541') AS uninsured_foreign_ccy,
           sum(f.value_cad_k) FILTER (WHERE f.dpa = '1045') AS total_assets
    FROM core.fact_m4 f
    JOIN core.dim_bank b USING (bank_id)
    WHERE b.bank_role IN ('big_six', 'acquired')
    GROUP BY 1, 2
),
acquired_books AS (
    SELECT e.acquirer_bank_id AS bank_id,
           e.first_month_consolidated,
           (SELECT t.insured + t.uninsured + t.reverse_mortgages
            FROM balances t
            WHERE t.bank_id = e.target_bank_id
              AND t.month_end_date < e.first_month_consolidated
            ORDER BY t.month_end_date DESC
            LIMIT 1) AS acquired_resi_cad_k
    FROM core.corporate_event e
),
with_totals AS (
    SELECT bal.*,
           bal.insured + bal.uninsured + bal.reverse_mortgages AS resi_total,
           coalesce((
               SELECT sum(a.acquired_resi_cad_k)
               FROM acquired_books a
               WHERE a.bank_id = bal.bank_id
                 AND bal.month_end_date >= a.first_month_consolidated
                 AND bal.month_end_date <  (a.first_month_consolidated + interval '12 months')
           ), 0) AS acquired_in_yoy_window,
           EXISTS (SELECT 1 FROM acquired_books a
                   WHERE a.bank_id = bal.bank_id AND a.first_month_consolidated = bal.month_end_date)
               AS is_acquisition_month
    FROM balances bal
)
SELECT t.bank_id,
       b.short_name,
       b.bank_role,
       t.month_end_date,
       t.insured, t.uninsured, t.reverse_mortgages, t.resi_total,
       t.insured_foreign_ccy, t.uninsured_foreign_ccy, t.total_assets,
       t.insured / nullif(t.insured + t.uninsured, 0)                    AS insured_share,
       (t.insured_foreign_ccy + t.uninsured_foreign_ccy)
           / nullif(t.insured + t.uninsured, 0)                          AS foreign_currency_share,
       t.resi_total / nullif(t.total_assets, 0)                          AS resi_share_of_assets,
       t.resi_total - lag(t.resi_total) OVER w                           AS mom_change,
       t.resi_total / nullif(lag(t.resi_total, 12) OVER w, 0) - 1        AS yoy_growth,
       (t.resi_total - t.acquired_in_yoy_window)
           / nullif(lag(t.resi_total, 12) OVER w, 0) - 1                 AS organic_yoy_growth,
       t.acquired_in_yoy_window,
       t.is_acquisition_month,
       m.rate_cycle_phase
FROM with_totals t
JOIN core.dim_bank b USING (bank_id)
JOIN core.dim_month m USING (month_end_date)
WINDOW w AS (PARTITION BY t.bank_id ORDER BY t.month_end_date);

ALTER TABLE mart.m4_resi_monthly ADD PRIMARY KEY (bank_id, month_end_date);

-- -----------------------------------------------------------------------------
-- mart.e3_m4_reconciliation
-- E3 reports GROSS exposure; M4 reports balances NET of the allowance. So
-- E3 gross - E3 ECL should equal the M4 balance at the same quarter-end.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.e3_m4_reconciliation AS
WITH e3 AS (
    SELECT bank_id, quarter_end_date,
           sum(gross_exposure_cad_k) AS e3_gross,
           sum(ecl_cad_k)            AS e3_ecl
    FROM mart.credit_stage
    WHERE product = 'Residential mortgages' AND insurance_status = 'All'
    GROUP BY 1, 2
)
SELECT e3.bank_id,
       b.short_name,
       e3.quarter_end_date,
       e3.e3_gross,
       e3.e3_ecl,
       e3.e3_gross - e3.e3_ecl                                            AS e3_net,
       m.insured + m.uninsured                                            AS m4_resi_excl_reverse,
       m.reverse_mortgages                                                AS m4_reverse_mortgages,
       (e3.e3_gross - e3.e3_ecl) - (m.insured + m.uninsured)              AS gap_cad_k,
       ((e3.e3_gross - e3.e3_ecl) - (m.insured + m.uninsured))
           / (e3.e3_gross - e3.e3_ecl)                                    AS gap_pct,
       ((e3.e3_gross - e3.e3_ecl) - m.resi_total)
           / (e3.e3_gross - e3.e3_ecl)                                    AS gap_pct_incl_reverse,
       CASE
           WHEN abs(((e3.e3_gross - e3.e3_ecl) - (m.insured + m.uninsured))
                    / (e3.e3_gross - e3.e3_ecl)) < 0.0001 THEN 'Reconciles'
           WHEN abs(((e3.e3_gross - e3.e3_ecl) - m.resi_total)
                    / (e3.e3_gross - e3.e3_ecl)) < 0.0001 THEN 'Reconciles once reverse mortgages are added'
           WHEN abs(((e3.e3_gross - e3.e3_ecl) - (m.insured + m.uninsured))
                    / (e3.e3_gross - e3.e3_ecl)) < 0.005  THEN 'Small gap (< 0.5%)'
           ELSE 'Open item (> 0.5%)'
       END                                                                AS status
FROM e3
JOIN core.dim_bank b USING (bank_id)
JOIN mart.m4_resi_monthly m
  ON m.bank_id = e3.bank_id AND m.month_end_date = e3.quarter_end_date;

ALTER TABLE mart.e3_m4_reconciliation ADD PRIMARY KEY (bank_id, quarter_end_date);

-- -----------------------------------------------------------------------------
-- mart.period_alignment_test
-- Tests the fiscal year-end assumption instead of trusting it: shift every E3
-- quarter-end by -3..+3 months and compare E3 (net) with M4 at that month.
-- Two scores per offset:
--   median_abs_gap_pct  level difference (fails when a bank's two returns have a
--                       standing level gap, as TD's do)
--   change_correlation  correlation of quarter-on-quarter changes in E3 with
--                       3-month changes in M4 (robust to a level gap)
-- The true quarter-end should win on both. Acquisition quarters and implausible
-- jumps (> 50% in a quarter) are left out of the correlation.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.period_alignment_test AS
WITH e3 AS (
    SELECT bank_id, quarter_end_date,
           sum(gross_exposure_cad_k) - sum(ecl_cad_k) AS e3_net
    FROM mart.credit_stage
    WHERE product = 'Residential mortgages' AND insurance_status = 'All'
    GROUP BY 1, 2
),
e3_changes AS (
    SELECT e3.*,
           e3_net / nullif(lag(e3_net) OVER (PARTITION BY bank_id ORDER BY quarter_end_date), 0) - 1
               AS e3_qoq_change
    FROM e3
),
m4_changes AS (
    SELECT bank_id, month_end_date, resi_total,
           resi_total / nullif(lag(resi_total, 3) OVER (PARTITION BY bank_id ORDER BY month_end_date), 0) - 1
               AS m4_3m_change
    FROM mart.m4_resi_monthly
),
shifted AS (
    SELECT e.bank_id, k.month_offset, e.quarter_end_date, e.e3_net, e.e3_qoq_change,
           (date_trunc('month', e.quarter_end_date)
              + make_interval(months => k.month_offset)
              + interval '1 month - 1 day')::date AS m4_month
    FROM e3_changes e
    CROSS JOIN generate_series(-3, 3) AS k(month_offset)
),
scores AS (
    SELECT s.bank_id, s.month_offset,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(s.e3_net - m.resi_total) / s.e3_net)
               AS median_abs_gap_pct,
           corr(s.e3_qoq_change, m.m4_3m_change) FILTER (
               WHERE abs(s.e3_qoq_change) < 0.5
                 AND NOT EXISTS (SELECT 1 FROM core.corporate_event ce
                                 WHERE ce.acquirer_bank_id = s.bank_id
                                   AND ce.first_quarter_end_consolidated = s.quarter_end_date)
           )                                     AS change_correlation,
           count(*)                              AS n_quarters
    FROM shifted s
    JOIN m4_changes m ON m.bank_id = s.bank_id AND m.month_end_date = s.m4_month
    GROUP BY 1, 2
)
SELECT sc.bank_id,
       b.short_name,
       b.fiscal_year_end_month,
       sc.month_offset,
       sc.median_abs_gap_pct,
       sc.change_correlation,
       sc.n_quarters,
       sc.change_correlation = max(sc.change_correlation) OVER (PARTITION BY sc.bank_id) AS is_best_offset
FROM scores sc
JOIN core.dim_bank b USING (bank_id);

-- -----------------------------------------------------------------------------
-- mart.subsidiary_double_count
-- OSFI's "Total Domestic Banks" leaves out banks owned by another bank, because
-- their numbers are already inside the parent's consolidated return. Adding up
-- every domestic bank therefore counts those subsidiaries twice.
-- core.bank_subsidiary_period records which banks are excluded, and from when;
-- each period was confirmed by matching OSFI's total to the dollar.
-- -----------------------------------------------------------------------------
CREATE TABLE core.bank_subsidiary_period (
    subsidiary_bank_id integer NOT NULL REFERENCES core.dim_bank,
    parent_name        text,
    valid_from         date    NOT NULL,
    valid_to           date    NOT NULL,
    evidence           text    NOT NULL,
    PRIMARY KEY (subsidiary_bank_id, valid_from)
);

INSERT INTO core.bank_subsidiary_period VALUES
    (28337,  'The Bank of Nova Scotia', date '2017-01-31', date '9999-12-31', 'Excluded from OSFI total in every month'),
    (28454,  'Laurentian Bank of Canada', date '2017-01-31', date '9999-12-31', 'Excluded from OSFI total in every month'),
    (149032, 'Equitable Bank',          date '2022-11-30', date '9999-12-31', 'Excluded from OSFI total from Nov 2022 (Equitable acquisition)'),
    (28010,  'National Bank of Canada', date '2025-02-28', date '2025-02-28', 'Filed its own M4 in Feb 2025 while already consolidated by National Bank'),
    (28453,  NULL,                      date '2024-12-31', date '9999-12-31', 'Excluded from OSFI total from Dec 2024; residual matches its total assets exactly'),
    (28017,  NULL,                      date '2017-01-31', date '2022-10-31', 'Formerly Dundee Bank of Canada; excluded in every month it reported (to Oct 2022); residual matches its total assets exactly');

CREATE TABLE mart.subsidiary_double_count AS
WITH assets AS (
    SELECT bank_id, industry_group, month_end_date, value_cad_k
    FROM core.fact_m4_industry
    WHERE dpa = '1045'
),
reporting AS (
    -- the newest month is published before most banks have filed; skip months
    -- where fewer than 90% of the usual number of banks reported
    SELECT month_end_date, count(*) AS n_banks
    FROM assets
    WHERE industry_group = 'Domestic Banks' AND bank_id < 1000000
    GROUP BY 1
),
complete_months AS (
    SELECT month_end_date, n_banks
    FROM reporting
    WHERE n_banks >= 0.9 * (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n_banks) FROM reporting)
)
SELECT c.month_end_date,
       c.n_banks                                                       AS n_domestic_banks_reporting,
       t.value_cad_k                                                   AS osfi_total_domestic,
       sum(a.value_cad_k)                                              AS sum_of_domestic_banks,
       sum(a.value_cad_k) - t.value_cad_k                              AS overstatement,
       coalesce(sum(a.value_cad_k) FILTER (WHERE sp.subsidiary_bank_id IS NOT NULL), 0)
                                                                       AS identified_subsidiaries,
       sum(a.value_cad_k) - t.value_cad_k
         - coalesce(sum(a.value_cad_k) FILTER (WHERE sp.subsidiary_bank_id IS NOT NULL), 0)
                                                                       AS unexplained,
       (sum(a.value_cad_k) - t.value_cad_k) / t.value_cad_k            AS overstatement_pct
FROM complete_months c
JOIN assets t ON t.month_end_date = c.month_end_date AND t.bank_id = 1000001
JOIN assets a ON a.month_end_date = c.month_end_date
             AND a.industry_group = 'Domestic Banks' AND a.bank_id < 1000000
LEFT JOIN core.bank_subsidiary_period sp
       ON sp.subsidiary_bank_id = a.bank_id
      AND c.month_end_date BETWEEN sp.valid_from AND sp.valid_to
GROUP BY c.month_end_date, c.n_banks, t.value_cad_k;

ALTER TABLE mart.subsidiary_double_count ADD PRIMARY KEY (month_end_date);
