-- =============================================================================
-- 01_dimensions.sql
-- Dimension tables for the star schema.
--   core.bank_seed         hand-maintained attributes (short names, fiscal year-ends)
--   core.dim_bank          one row per OSFI institution id (latest legal name)
--   core.dim_month         calendar month spine, with the Big Six fiscal calendar
--   core.dim_e3_line       E3 line items parsed into product / stage / measure
--   core.dim_m4_line       M4 line items used in this project
--   core.corporate_event   acquisitions that break the time series
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Seed attributes that OSFI does not publish.
-- Fiscal year-end months are verified by mart.period_alignment_test (03_marts.sql)
-- and check DQ07 (04_quality_checks.sql), which match E3 (quarterly) against M4
-- (monthly) at every candidate month offset.
-- -----------------------------------------------------------------------------
CREATE TABLE core.bank_seed (
    bank_id               integer PRIMARY KEY,
    short_name            text NOT NULL,
    fiscal_year_end_month smallint CHECK (fiscal_year_end_month BETWEEN 1 AND 12),
    bank_role             text NOT NULL
        CHECK (bank_role IN ('big_six', 'acquired', 'bank_subsidiary', 'other', 'industry_total'))
);

INSERT INTO core.bank_seed VALUES
    (27997,   'RBC',          10,   'big_six'),
    (27999,   'TD',           10,   'big_six'),
    (28000,   'BNS',          10,   'big_six'),
    (27998,   'BMO',          10,   'big_six'),
    (27996,   'CIBC',         10,   'big_six'),
    (28002,   'NBC',          10,   'big_six'),
    (28058,   'HSBC Canada',  12,   'acquired'),        -- bought by RBC, closed 2024-03-28
    (28010,   'CWB',          10,   'acquired'),        -- bought by NBC, closed 2025-02-03
    (28337,   'Tangerine',    NULL, 'bank_subsidiary'), -- owned by BNS
    (28454,   'B2B Bank',     NULL, 'bank_subsidiary'), -- owned by Laurentian Bank
    (149032,  'Concentra',    NULL, 'bank_subsidiary'), -- owned by Equitable Bank since Nov 2022
    (28326,   'Laurentian',   NULL, 'other'),
    (28456,   'Equitable',    NULL, 'other'),
    (1000000, 'Total All Banks',                 NULL, 'industry_total'),
    (1000001, 'Total Domestic Banks',            NULL, 'industry_total'),
    (1000002, 'Total Foreign Bank Subsidiaries', NULL, 'industry_total');

-- -----------------------------------------------------------------------------
-- dim_bank. OSFI keeps the id when a bank changes its name (ING Bank of Canada
-- became Tangerine, Walmart Canada Bank became Fairstone ...), so the id is
-- the key and the most recent name is the label.
-- -----------------------------------------------------------------------------
CREATE TABLE core.dim_bank AS
WITH observations AS (
    -- E3 is ordered by fiscal period, M4 by calendar month. Both are only used
    -- to put each id's names in time order, so a rough common ordering is enough.
    SELECT fi_id::int AS bank_id, fi_name, industry_group,
           make_date(fiscal_year::int, 1, 1)
             + (substr(fiscal_quarter, 2, 1)::int * interval '3 months') AS seen_at
    FROM raw.e3
    UNION ALL
    SELECT fi_id::int, fi_name, industry_group, calendar_month::date FROM raw.m4
    UNION ALL
    SELECT fi_id::int, fi_name, industry_group, calendar_month::date FROM raw.m4_keylines
),
-- Text is ordered with COLLATE "C" (byte order) wherever order reaches the
-- output, so the result is the same whatever locale the database was created with.
latest AS (
    SELECT DISTINCT ON (bank_id) bank_id, fi_name, industry_group
    FROM observations
    ORDER BY bank_id, seen_at DESC, fi_name COLLATE "C"
),
history AS (
    -- Every name the id has filed under, oldest first
    SELECT bank_id,
           string_agg(fi_name, ' | ' ORDER BY first_seen, fi_name COLLATE "C") AS name_history,
           count(*)                                                          AS n_names
    FROM (SELECT bank_id, fi_name, min(seen_at) AS first_seen
          FROM observations
          GROUP BY bank_id, fi_name) names
    GROUP BY bank_id
)
SELECT l.bank_id,
       l.fi_name                                  AS bank_name,
       coalesce(s.short_name, l.fi_name)          AS short_name,
       l.industry_group,
       s.fiscal_year_end_month,
       coalesce(s.bank_role, 'other')             AS bank_role,
       coalesce(s.bank_role = 'big_six', false)   AS is_big_six,
       h.name_history,
       h.n_names
FROM latest l
JOIN history h USING (bank_id)
LEFT JOIN core.bank_seed s USING (bank_id);

ALTER TABLE core.dim_bank ADD PRIMARY KEY (bank_id);

-- -----------------------------------------------------------------------------
-- dim_month: month-end spine with the Big Six fiscal calendar (year ends Oct 31)
-- and the Bank of Canada policy-rate phase each month falls in.
-- -----------------------------------------------------------------------------
CREATE TABLE core.dim_month AS
SELECT d::date                                                     AS month_end_date,
       extract(year  FROM d)::int                                  AS calendar_year,
       extract(month FROM d)::int                                  AS calendar_month,
       to_char(d, 'Mon YYYY')                                      AS month_label,
       'Q' || extract(quarter FROM d)::int || ' ' || extract(year FROM d)::int
                                                                   AS calendar_quarter_label,
       -- Big Six fiscal calendar: Q1 = Nov-Jan, Q2 = Feb-Apr, Q3 = May-Jul, Q4 = Aug-Oct
       (extract(year FROM d)::int + CASE WHEN extract(month FROM d) >= 11 THEN 1 ELSE 0 END)
                                                                   AS big6_fiscal_year,
       ((extract(month FROM d)::int + 1) % 12) / 3 + 1             AS big6_fiscal_quarter,
       extract(month FROM d)::int IN (1, 4, 7, 10)                 AS is_big6_quarter_end,
       CASE
           WHEN d <  date '2020-03-01' THEN '1. Pre-pandemic'
           WHEN d <  date '2022-03-01' THEN '2. Pandemic, emergency low rates'
           WHEN d <  date '2024-06-01' THEN '3. Rate hikes'
           ELSE                             '4. Rate cuts'
       END                                                         AS rate_cycle_phase
FROM generate_series(date '2017-01-01', date '2026-12-01', interval '1 month') AS g(m)
CROSS JOIN LATERAL (SELECT (date_trunc('month', m) + interval '1 month - 1 day')::date AS d) x;

ALTER TABLE core.dim_month ADD PRIMARY KEY (month_end_date);

-- -----------------------------------------------------------------------------
-- dim_e3_line: OSFI labels are long, comma-separated paths such as
-- 'E3, Allowances for expected credit losses, loans, mortgage loans,
--  residential, of which uninsured, Stage II, recorded investment'.
-- They are parsed into product, insurance scope, IFRS 9 stage and measure.
-- The key is (dpa, label): some codes (3195-3198) were reused in 2018 for a
-- different measure, so the code alone is not a stable identifier.
-- -----------------------------------------------------------------------------
CREATE TABLE core.dim_e3_line AS
WITH labels AS (
    SELECT dpa, dpa_label,
           min(fiscal_year::int * 10 + substr(fiscal_quarter, 2, 1)::int) AS first_period,
           max(fiscal_year::int * 10 + substr(fiscal_quarter, 2, 1)::int) AS last_period,
           count(*) AS n_rows
    FROM raw.e3
    GROUP BY dpa, dpa_label
)
SELECT row_number() OVER (ORDER BY dpa COLLATE "C", first_period, dpa_label COLLATE "C")::int
                                                                    AS e3_line_key,
       dpa,
       dpa_label,
       regexp_replace(dpa_label, '^E3, Allowances for expected credit losses, ', '') AS short_label,
       (dpa_label LIKE 'E3, %')                                     AS is_ifrs9_line,
       CASE
           WHEN dpa_label ~ 'mortgage loans, residential'                      THEN 'residential_mortgages'
           WHEN dpa_label ~ 'mortgage loans, non-residential'                  THEN 'non_residential_mortgages'
           WHEN dpa_label ~ 'non-business purposes, credit cards'              THEN 'credit_cards'
           WHEN dpa_label ~ 'non-business purposes, other'                     THEN 'personal_loans_other'
           WHEN dpa_label ~ 'to individuals for non-business purposes'         THEN 'personal_loans_total'
           WHEN dpa_label ~ 'deposits with regulated financial institutions'   THEN 'deposits_with_fis'
           WHEN dpa_label ~ ', securities, '                                   THEN 'securities'
           WHEN dpa_label ~ ', acceptances, '                                  THEN 'acceptances'
           WHEN dpa_label ~ 'other recognized assets'                          THEN 'other_assets'
           WHEN dpa_label ~ ', total, '                                        THEN 'total'
           ELSE 'other'
       END                                                          AS product,
       CASE WHEN dpa_label ~ 'of which uninsured' THEN 'uninsured' ELSE 'all' END AS insurance_scope,
       CASE
           WHEN dpa_label ~ 'Stage III' THEN 3
           WHEN dpa_label ~ 'Stage II'  THEN 2
           WHEN dpa_label ~ 'Stage I'   THEN 1
       END                                                          AS ifrs9_stage,
       CASE
           WHEN dpa_label !~ '^E3, '                               THEN 'legacy_pre_2018'
           WHEN dpa_label ~ 'recorded investment$'                 THEN 'gross_exposure'
           WHEN dpa_label ~ 'Expected Credit Losses$'              THEN 'ecl'
           WHEN dpa_label ~ 'individually assessed allowance$'     THEN 'ecl_individual'
           WHEN dpa_label ~ 'collectively assessed allowance$'     THEN 'ecl_collective'
           WHEN dpa_label ~ 'net impaired amount$'                 THEN 'net_impaired'
           ELSE 'other'
       END                                                          AS measure,
       first_period,
       last_period,
       n_rows
FROM labels;

ALTER TABLE core.dim_e3_line ADD PRIMARY KEY (e3_line_key);
CREATE UNIQUE INDEX ON core.dim_e3_line (dpa, dpa_label);

-- -----------------------------------------------------------------------------
-- dim_m4_line: only the M4 lines this project uses. All M4 asset lines are
-- reported NET of the allowance for expected credit losses.
-- -----------------------------------------------------------------------------
CREATE TABLE core.dim_m4_line (
    dpa            text PRIMARY KEY,
    line_name      text NOT NULL,
    product        text NOT NULL,
    currency_basis text NOT NULL CHECK (currency_basis IN ('all currencies', 'foreign currency only'))
);

INSERT INTO core.dim_m4_line VALUES
    ('0540', 'Residential mortgages, insured',               'resi_insured',      'all currencies'),
    ('0539', 'Residential mortgages, insured',               'resi_insured',      'foreign currency only'),
    ('0542', 'Residential mortgages, uninsured',             'resi_uninsured',    'all currencies'),
    ('0541', 'Residential mortgages, uninsured',             'resi_uninsured',    'foreign currency only'),
    ('0608', 'Residential mortgages, reverse mortgages',     'resi_reverse',      'all currencies'),
    ('0554', 'Residential mortgages, of which NHA MBS',      'resi_nha_mbs',      'all currencies'),
    ('2117', 'Non-residential mortgages',                    'non_resi_mortgage', 'all currencies'),
    ('0534', 'Non-mortgage loans to individuals',            'personal_loans',    'all currencies'),
    ('1076', 'Personal loans secured by residential property (e.g. HELOCs)', 'personal_secured_resi', 'all currencies'),
    ('0572', 'Non-mortgage loans for business purposes',     'business_loans',    'all currencies'),
    ('1045', 'Total assets',                                 'total_assets',      'all currencies');

-- -----------------------------------------------------------------------------
-- Acquisitions that add a whole loan book to the acquirer in one month.
-- Sources: RBC and National Bank press releases (source_url column).
-- -----------------------------------------------------------------------------
CREATE TABLE core.corporate_event (
    acquirer_bank_id         integer NOT NULL REFERENCES core.dim_bank,
    target_bank_id           integer NOT NULL REFERENCES core.dim_bank,
    close_date               date    NOT NULL,
    first_month_consolidated date    NOT NULL,  -- first M4 month-end that includes the target
    first_quarter_end_consolidated date NOT NULL, -- first E3 quarter-end that includes the target
    description              text    NOT NULL,
    source_url               text    NOT NULL,
    PRIMARY KEY (acquirer_bank_id, target_bank_id)
);

INSERT INTO core.corporate_event VALUES
    (27997, 28058, date '2024-03-28', date '2024-04-30', date '2024-04-30',
     'RBC acquires HSBC Bank Canada',
     'https://www.newswire.ca/news-releases/rbc-completes-acquisition-of-hsbc-bank-canada-849432219.html'),
    (28002, 28010, date '2025-02-03', date '2025-02-28', date '2025-04-30',
     'National Bank acquires Canadian Western Bank',
     'https://www.nbc.ca/about-us/news-media/press-release/2025/20250203-nbc-concludes-acquisition-cwb.html');
