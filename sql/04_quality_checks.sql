-- =============================================================================
-- 04_quality_checks.sql
-- Every data-quality test in one table, with a status and what was done about
-- it. Metrics are computed from the data on each build, so a new OSFI release
-- that breaks an assumption shows up here instead of in a chart.
--   Pass     the assumption holds
--   Handled  a real problem in the source, fixed or worked around in the model
--   Warning  a limitation that remains; read results with it in mind
--   Open     not resolved with the data available
-- =============================================================================

CREATE TABLE mart.dq_checks (
    check_id    text PRIMARY KEY,
    area        text NOT NULL,
    check_name  text NOT NULL,
    status      text NOT NULL CHECK (status IN ('Pass', 'Handled', 'Warning', 'Open')),
    metric      text NOT NULL,
    finding     text NOT NULL,
    action      text NOT NULL
);

-- DQ01 Completeness: every Big Six bank has every quarter -----------------------
INSERT INTO mart.dq_checks
SELECT 'DQ01', 'Completeness', 'Big Six quarters present in E3',
       CASE WHEN min(n) = max(n) AND min(n) = (SELECT count(DISTINCT quarter_end_date)
                                               FROM mart.resi_mortgage_quarterly WHERE bank_id = 0)
            THEN 'Pass' ELSE 'Warning' END,
       min(n) || ' to ' || max(n) || ' quarters per bank',
       'Every Big Six bank reports residential-mortgage stages for every fiscal quarter from Q1 2018 to the latest quarter.',
       'None needed.'
FROM (SELECT bank_id, count(*) AS n FROM mart.resi_mortgage_quarterly WHERE bank_id <> 0 GROUP BY 1) x;

-- DQ02 Timeliness: the newest M4 month is published before most banks file -----
INSERT INTO mart.dq_checks
WITH by_month AS (
    SELECT month_end_date, count(*) FILTER (WHERE bank_id < 1000000) AS n_banks
    FROM core.fact_m4_industry WHERE dpa = '1045' GROUP BY 1
)
SELECT 'DQ02', 'Timeliness', 'Newest M4 month only partly filed',
       'Handled',
       to_char(max(month_end_date), 'Mon YYYY') || ': ' ||
           (SELECT n_banks FROM by_month ORDER BY month_end_date DESC LIMIT 1) || ' banks vs ' ||
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY n_banks) FROM by_month)::int || ' normally',
       'The latest month in the M4 file had been filed by only a handful of banks when it was downloaded.',
       'Months where fewer than 90% of the usual number of banks reported are excluded; monthly analysis ends at the last complete month.'
FROM by_month;

-- DQ03 Uniqueness: duplicated E3 keys ----------------------------------------------
INSERT INTO mart.dq_checks
SELECT 'DQ03', 'Uniqueness', 'Duplicate E3 rows with conflicting values',
       CASE WHEN count(*) = 0 THEN 'Pass' ELSE 'Handled' END,
       count(*) || ' rows (' || count(DISTINCT e3_line_key) || ' line items)',
       'OSFI''s E3 file repeats some keys with different values: ' ||
           coalesce(string_agg(DISTINCT b.short_name || ' fiscal Q' || q.fiscal_quarter || ' ' || q.fiscal_year, ', '), 'none') || '.',
       'Both copies are moved to core.e3_quarantine and not used. They are industry totals, which this project does not use anyway.'
FROM core.e3_quarantine q
JOIN core.dim_bank b USING (bank_id);

-- DQ04 Uniqueness: M4 industry totals split across two label versions -------------
INSERT INTO mart.dq_checks
SELECT 'DQ04', 'Uniqueness', 'M4 totals split across IFRS 9 and IAS 39 labels',
       CASE WHEN count(*) = 0 THEN 'Pass' ELSE 'Handled' END,
       count(*) || ' bank-month-lines in ' ||
           coalesce(string_agg(DISTINCT to_char(month_end_date, 'Mon YYYY'), ', '), 'no months'),
       'During the IFRS 9 changeover, OSFI''s industry totals appear twice per line: banks with an October year-end (already on IFRS 9) under the new label and banks with a December year-end under the old one. Taking one label would show a false 6-7% drop.',
       'The two rows cover different banks, so they are added together (core.fact_m4.n_label_versions records where).'
FROM (SELECT month_end_date FROM core.fact_m4 WHERE n_label_versions > 1
      UNION ALL
      SELECT month_end_date FROM core.fact_m4_industry WHERE n_label_versions > 1) x;

-- DQ05 Validity: line-item codes reused with a different meaning ------------------
INSERT INTO mart.dq_checks
SELECT 'DQ05', 'Validity', 'E3 line codes reused for a different measure',
       CASE WHEN count(*) = 0 THEN 'Pass' ELSE 'Handled' END,
       count(*) || ' codes: ' || min(dpa) || '-' || max(dpa),
       'Codes ' || min(dpa) || '-' || max(dpa) || ' meant "carrying amount of impaired assets" before 2018 and "net impaired amount" after. A series keyed on the code alone would splice two different measures.',
       'Line items are keyed on code + label (core.dim_e3_line).'
FROM (SELECT dpa FROM core.dim_e3_line GROUP BY dpa HAVING count(DISTINCT dpa_label) > 1) x;

-- DQ06 Consistency: banks change names, ids do not -----------------------------------
INSERT INTO mart.dq_checks
SELECT 'DQ06', 'Consistency', 'Institution name changes',
       'Handled',
       count(*) || ' institution ids with 2+ names',
       'Examples: ' || string_agg(name_history, '; ' ORDER BY bank_id) FILTER (WHERE bank_id IN (28337, 28451, 28017)) || '.',
       'Banks are keyed on OSFI''s id and labelled with their latest name (core.dim_bank).'
FROM core.dim_bank WHERE n_names > 1;

-- DQ07 Consistency: fiscal year-ends verified, not assumed ---------------------------
INSERT INTO mart.dq_checks
SELECT 'DQ07', 'Consistency', 'E3 fiscal quarters mapped to calendar month-ends',
       CASE WHEN bool_and(month_offset = 0) THEN 'Pass' ELSE 'Warning' END,
       count(*) FILTER (WHERE month_offset = 0) || ' of ' || count(*) || ' banks best aligned at offset 0',
       'E3 is labelled by each bank''s own fiscal quarter, M4 by calendar month. Shifting E3 by -3..+3 months, quarter-on-quarter changes line up best with M4 at offset 0 for every bank, confirming October year-ends for the Big Six and CWB and a December year-end for HSBC Canada.',
       'core.fact_e3.quarter_end_date uses the verified year-end; OSFI''s E3 industry totals mix year-ends and are not used.'
FROM mart.period_alignment_test WHERE is_best_offset;

-- DQ08 Reconciliation: E3 (gross - ECL) vs M4 (net), one row per Big Six bank -------
INSERT INTO mart.dq_checks
SELECT 'DQ08-' || short_name, 'Reconciliation', 'E3 vs M4 residential mortgages: ' || short_name,
       CASE
           WHEN max(abs(gap_pct)) < 0.001 THEN 'Pass'   -- within 0.1% in every quarter
           WHEN bool_and(status IN ('Reconciles', 'Reconciles once reverse mortgages are added')) THEN 'Handled'
           WHEN max(abs(gap_pct)) < 0.005 THEN 'Warning'
           ELSE 'Open'
       END,
       'gap ' || to_char(min(gap_pct) * 100, 'FM990.00') || '% to ' || to_char(max(gap_pct) * 100, 'FM990.00') || '% of E3 net',
       CASE short_name
           WHEN 'NBC' THEN 'E3 includes reverse mortgages; M4 reports them on a separate line. Adding that line closes the gap exactly.'
           WHEN 'RBC' THEN 'M4 is 0.1-0.3% above E3 net in every quarter; small and stable.'
           WHEN 'TD'  THEN 'From fiscal Q2 2018, M4 is 4-9% above E3 net and the gap widens from 2023. E3 only covers loans that carry an expected-credit-loss allowance, so the likely cause is mortgages TD measures at fair value or holds for sale. TD''s filings would be needed to confirm.'
           ELSE 'E3 gross minus E3 allowance equals the M4 balance to the dollar in '
                || count(*) FILTER (WHERE status = 'Reconciles') || ' of ' || count(*) || ' quarters'
                || CASE WHEN count(*) FILTER (WHERE status <> 'Reconciles') > 0
                        THEN '; the others differ by less than ' || to_char(max(abs(gap_pct)) * 100, 'FM0.00') || '%.'
                        ELSE '.' END
       END,
       CASE short_name
           WHEN 'TD' THEN 'All ratios use E3 for both numerator and denominator, so they are internally consistent; TD''s balances are not compared across returns.'
           ELSE 'None needed.'
       END
FROM mart.e3_m4_reconciliation
WHERE bank_id IN (SELECT bank_id FROM core.dim_bank WHERE is_big_six)
GROUP BY short_name;

-- DQ09 Consistency: an "of which" line must not exceed its total ---------------------
INSERT INTO mart.dq_checks
WITH pairs AS (
    SELECT a.short_name, a.fiscal_year, a.fiscal_quarter, a.stage,
           a.gross_exposure_cad_k AS all_gross, u.gross_exposure_cad_k AS uninsured_gross
    FROM mart.credit_stage a
    JOIN mart.credit_stage u
      ON (u.bank_id, u.fiscal_year, u.fiscal_quarter, u.product, u.stage)
       = (a.bank_id, a.fiscal_year, a.fiscal_quarter, a.product, a.stage)
     AND u.insurance_status = 'Uninsured'
    WHERE a.insurance_status = 'All' AND a.product = 'Residential mortgages'
)
SELECT 'DQ09', 'Consistency', 'Uninsured exposure never exceeds total exposure',
       CASE WHEN count(*) FILTER (WHERE uninsured_gross > all_gross) = 0 THEN 'Pass' ELSE 'Warning' END,
       count(*) FILTER (WHERE uninsured_gross > all_gross) || ' violations in ' || count(*) || ' bank-quarter-stages',
       'The "of which uninsured" line is larger than the total in: ' ||
           coalesce(string_agg(short_name || ' fiscal ' || fiscal_year || ' Q' || fiscal_quarter || ' Stage ' || stage
                               || ' (+$' || to_char((uninsured_gross - all_gross) / 1e6, 'FM990.000') || 'bn)', '; '
                               ORDER BY fiscal_year, fiscal_quarter)
                    FILTER (WHERE uninsured_gross > all_gross), 'none') ||
           '. NBC''s fiscal Q4 2020 Stage 2 total (about $0.2bn, against $1.5bn a quarter earlier and $1.5bn a quarter later) looks misfiled.',
       'Kept as reported and flagged; derived insured figures for these bank-quarters are negative and are not interpreted.'
FROM pairs;

-- DQ10 Validity: negative allowances ------------------------------------------------
INSERT INTO mart.dq_checks
SELECT 'DQ10', 'Validity', 'Negative Stage 3 allowances',
       CASE WHEN count(*) = 0 THEN 'Pass' ELSE 'Warning' END,
       count(*) || ' bank-quarters' || coalesce(' (' || string_agg(DISTINCT short_name, ', ') || ', fiscal '
           || min(fiscal_year) || ' to ' || max(fiscal_year) || ')', ''),
       'National Bank reports a negative Stage 3 allowance on residential mortgages from fiscal 2018 to 2023. Under IFRS 9, purchased or originated credit-impaired (POCI) loans can carry a negative allowance when expected recoveries improve after purchase (IFRS 9 para 5.5.14). OSFI''s data does not identify POCI loans, so this is the likely, not confirmed, cause.',
       'Values are kept as reported. NBC''s Stage 3 coverage is not used in peer comparisons for those years.'
FROM mart.credit_stage
WHERE product = 'Residential mortgages' AND insurance_status = 'All' AND stage = 3 AND ecl_cad_k < 0;

-- DQ11 Completeness: insured/uninsured split missing ---------------------------------
INSERT INTO mart.dq_checks
WITH x AS (
    SELECT short_name, count(*) FILTER (WHERE uninsured_share IS NULL) AS n_missing,
           min(quarter_end_date) FILTER (WHERE uninsured_share IS NOT NULL) AS first_reported
    FROM mart.resi_mortgage_quarterly WHERE bank_id <> 0 GROUP BY 1
)
SELECT 'DQ11', 'Completeness', 'Insured/uninsured split not reported',
       CASE WHEN sum(n_missing) = 0 THEN 'Pass' ELSE 'Handled' END,
       sum(n_missing) || ' bank-quarters missing',
       coalesce(string_agg(short_name || ' first reports it for the quarter ending ' || to_char(first_reported, 'Mon YYYY'), '; ')
                FILTER (WHERE n_missing > 0), 'All banks report it.') || '. Before then its uninsured lines are zero, which would wrongly make every mortgage "insured".',
       'Zeros are treated as "not reported", not as zero. Insured/uninsured metrics start when all six banks report them.'
FROM x;

-- DQ12 Comparability: acquisitions -------------------------------------------------
INSERT INTO mart.dq_checks
SELECT 'DQ12', 'Comparability', 'Acquisitions add whole loan books in one month',
       'Handled',
       string_agg(b.short_name || ' +' || to_char(m.mom_change / 1e6, 'FM990.0') || 'bn in ' || to_char(m.month_end_date, 'Mon YYYY')
                  || ' (target book ' || to_char(m.acquired_in_yoy_window / 1e6, 'FM990.0') || 'bn)', '; '),
       'RBC''s purchase of HSBC Bank Canada (closed 28 Mar 2024) and National Bank''s purchase of Canadian Western Bank (closed 3 Feb 2025) each show up as a one-month jump about equal to the target''s mortgage book.',
       'mart.m4_resi_monthly carries an organic growth rate that removes the acquired book for the 12 months it distorts year-over-year growth.'
FROM mart.m4_resi_monthly m
JOIN core.dim_bank b USING (bank_id)
WHERE m.is_acquisition_month;

-- DQ13 Comparability: subsidiaries double-counted when summing banks ---------------
INSERT INTO mart.dq_checks
SELECT 'DQ13', 'Comparability', 'Summing banks double-counts bank-owned subsidiaries',
       CASE WHEN count(*) FILTER (WHERE abs(unexplained) > 10000) = 0 THEN 'Handled' ELSE 'Warning' END,
       'overstatement ' || to_char(min(overstatement_pct) * 100, 'FM0.00') || '% to ' || to_char(max(overstatement_pct) * 100, 'FM0.00') ||
           '% of total domestic assets; ' || count(*) FILTER (WHERE abs(unexplained) > 10000) || ' month(s) not fully explained',
       'Adding up every domestic bank overstates OSFI''s domestic total by $57-120bn because subsidiaries (Tangerine, B2B Bank, Concentra, Home Bank, ADS Canadian Bank, and CWB in Feb 2025) are already inside their parents'' returns. With these identified, the gap is zero in every month except ' ||
           coalesce(string_agg(to_char(month_end_date, 'Mon YYYY') || ' ($' || to_char(unexplained / 1e6, 'FM990.0') || 'bn)', ', ')
                    FILTER (WHERE abs(unexplained) > 10000), 'none') || '.',
       'This project compares the Big Six bank by bank and never sums institutions; OSFI''s List of Bank Subsidiaries would resolve the remaining month.'
FROM mart.subsidiary_double_count;

-- DQ14 Comparability: Stage 2 depends on each bank's own models -------------------
INSERT INTO mart.dq_checks
SELECT 'DQ14', 'Comparability', 'Large one-quarter Stage 2 swings',
       'Warning',
       count(*) || ' bank-quarters where Stage 2 exposure moved more than 40% in one quarter',
       'IFRS 9 leaves "significant increase in credit risk" to each bank''s own criteria and models, so a bank''s Stage 2 can jump or halve in one quarter when its models, assumptions or thresholds change. Recent examples: ' ||
           string_agg(short_name || ' ' || to_char(quarter_end_date, 'Mon YYYY') || ' (' ||
                      to_char(gross_s2_qoq_change * 100, 'FMS990') || '%)', ', ' ORDER BY quarter_end_date)
               FILTER (WHERE quarter_end_date >= '2023-01-01') || '.',
       'Peer comparisons lean on Stage 3 (credit-impaired), which follows a common 90-days-past-due backstop. Stage 2 is shown per bank, over time.'
FROM mart.resi_mortgage_quarterly
WHERE bank_id <> 0 AND abs(gross_s2_qoq_change) > 0.4;

-- DQ15 Consistency: 2018 allowance format -------------------------------------------
INSERT INTO mart.dq_checks
SELECT 'DQ15', 'Consistency', 'Fiscal 2018 allowance reported in two parts',
       'Handled',
       count(*) || ' bank-quarter-stage rows built from components',
       'In fiscal 2018 E3 split each stage''s allowance into individually and collectively assessed parts; from fiscal 2019 it reports one figure (OSFI change log, amendment 13).',
       'The two parts are added together; mart.credit_stage.ecl_basis records which rows were built this way.'
FROM mart.credit_stage
WHERE ecl_basis LIKE 'Individual%' AND product = 'Residential mortgages' AND insurance_status = 'All';

-- DQ16 Comparability: consolidated returns include foreign mortgages ---------------
INSERT INTO mart.dq_checks
SELECT 'DQ16', 'Comparability', 'Returns are consolidated, including foreign mortgages',
       'Warning',
       'foreign-currency share of residential mortgages: ' ||
           string_agg(short_name || ' ' || to_char(foreign_currency_share * 100, 'FM990') || '%', ', ' ORDER BY foreign_currency_share DESC),
       'E3 and M4 cover each bank''s whole group, so mortgages in the US (BMO, TD), Latin America and the Caribbean (BNS) and Cambodia (NBC) are mixed with Canadian ones. E3 has no geographic split.',
       'Cross-bank differences in coverage are read with each bank''s foreign share in mind (shown in the notebook and dashboards).'
FROM mart.m4_resi_monthly
WHERE bank_role = 'big_six'
  AND month_end_date = (SELECT max(month_end_date) FROM mart.subsidiary_double_count);

-- DQ17 Validity: CWB fiscal 2018 misfiled ---------------------------------------
INSERT INTO mart.dq_checks
SELECT 'DQ17', 'Validity', 'CWB fiscal 2018 residential mortgages implausibly small',
       CASE WHEN count(*) = 0 THEN 'Pass' ELSE 'Warning' END,
       count(*) || ' quarters where E3 is under 1% of M4',
       'Canadian Western Bank''s fiscal 2018 E3 shows about $30 million of residential mortgages against about $7 billion in M4; from fiscal 2019 the two agree.',
       'CWB data is only used to size the book National Bank acquired in 2025, which comes from M4.'
FROM mart.e3_m4_reconciliation
WHERE short_name = 'CWB' AND e3_net < 0.01 * m4_resi_excl_reverse;
