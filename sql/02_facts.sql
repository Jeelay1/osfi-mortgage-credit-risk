-- =============================================================================
-- 02_facts.sql
-- Typed fact tables.
--   core.fact_e3           bank x fiscal quarter x E3 line   (IFRS 9 era, fiscal 2018+)
--   core.e3_quarantine     E3 rows held back because their key is duplicated
--   core.fact_m4           bank x month-end x M4 line        (banks studied here)
--   core.fact_m4_industry  every institution x month-end     (headline lines only)
-- All amounts are thousands of Canadian dollars, as filed with OSFI.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Step 1: type the E3 rows and attach each one's quarter-end date.
-- OSFI labels E3 periods with each bank's OWN fiscal quarter. For a bank whose
-- fiscal year ends in month F, fiscal quarter q of fiscal year Y ends in month
-- F - 3*(4 - q), rolling back into calendar year Y-1 when that month is <= 0.
-- Example: RBC (F = 10), 'Q2 - 2026' ends 2026-04-30.
-- Banks without a verified year-end (and OSFI's industry totals, which mix
-- banks with different year-ends) get a NULL date.
-- -----------------------------------------------------------------------------
CREATE TEMP TABLE e3_typed AS
SELECT r.fi_id::int                                   AS bank_id,
       r.fiscal_year::smallint                        AS fiscal_year,
       substr(r.fiscal_quarter, 2, 1)::smallint       AS fiscal_quarter,
       r.fiscal_quarter                               AS fiscal_quarter_label,
       l.e3_line_key,
       nullif(trim(r.measure_value), '')::numeric(20, 2) AS value_cad_k
FROM raw.e3 r
JOIN core.dim_e3_line l ON l.dpa = r.dpa AND l.dpa_label = r.dpa_label
WHERE r.fiscal_year::int >= 2018;

-- -----------------------------------------------------------------------------
-- Step 2: quarantine duplicated keys. OSFI's file repeats some keys with
-- different values (Total All Banks, fiscal Q4 2018). There is no way to tell
-- which row is right, so neither is used; they are kept here for the log.
-- -----------------------------------------------------------------------------
CREATE TABLE core.e3_quarantine AS
SELECT t.*, 'duplicate key, conflicting values'::text AS reason
FROM e3_typed t
JOIN (
    SELECT bank_id, fiscal_year, fiscal_quarter, e3_line_key
    FROM e3_typed
    GROUP BY 1, 2, 3, 4
    HAVING count(*) > 1
) dup USING (bank_id, fiscal_year, fiscal_quarter, e3_line_key);

CREATE TABLE core.fact_e3 AS
SELECT t.bank_id,
       t.fiscal_year,
       t.fiscal_quarter,
       t.fiscal_quarter_label,
       CASE WHEN b.fiscal_year_end_month IS NOT NULL THEN
           (make_date(
                CASE WHEN b.fiscal_year_end_month - 3 * (4 - t.fiscal_quarter) <= 0
                     THEN t.fiscal_year - 1 ELSE t.fiscal_year END,
                CASE WHEN b.fiscal_year_end_month - 3 * (4 - t.fiscal_quarter) <= 0
                     THEN b.fiscal_year_end_month - 3 * (4 - t.fiscal_quarter) + 12
                     ELSE b.fiscal_year_end_month - 3 * (4 - t.fiscal_quarter) END,
                1) + interval '1 month - 1 day')::date
       END                                            AS quarter_end_date,
       t.e3_line_key,
       t.value_cad_k
FROM e3_typed t
JOIN core.dim_bank b USING (bank_id)
WHERE NOT EXISTS (
    SELECT 1 FROM core.e3_quarantine q
    WHERE (q.bank_id, q.fiscal_year, q.fiscal_quarter, q.e3_line_key)
        = (t.bank_id, t.fiscal_year, t.fiscal_quarter, t.e3_line_key)
);

ALTER TABLE core.fact_e3
    ADD PRIMARY KEY (bank_id, fiscal_year, fiscal_quarter, e3_line_key),
    ADD FOREIGN KEY (bank_id)     REFERENCES core.dim_bank,
    ADD FOREIGN KEY (e3_line_key) REFERENCES core.dim_e3_line;
CREATE INDEX ON core.fact_e3 (bank_id, quarter_end_date);

-- -----------------------------------------------------------------------------
-- M4 facts. In Nov and Dec 2017 OSFI's industry totals appear twice per line:
-- once under the new IFRS 9 label (banks with an October year-end, which
-- adopted IFRS 9 on 1 Nov 2017) and once under the old IAS 39 label (banks
-- with a December year-end, which adopted on 1 Jan 2018). The two rows cover
-- different banks, so the correct total is their SUM. n_label_versions keeps a
-- record of where that happened.
-- -----------------------------------------------------------------------------
CREATE TABLE core.fact_m4 AS
SELECT r.fi_id::int                                         AS bank_id,
       r.calendar_month::date                               AS month_end_date,
       r.dpa,
       sum(nullif(trim(r.measure_value), '')::numeric(20, 2)) AS value_cad_k,
       count(DISTINCT r.dpa_label)::smallint                AS n_label_versions
FROM raw.m4 r
JOIN core.dim_m4_line l USING (dpa)
GROUP BY 1, 2, 3;

ALTER TABLE core.fact_m4
    ADD PRIMARY KEY (bank_id, month_end_date, dpa),
    ADD FOREIGN KEY (bank_id)        REFERENCES core.dim_bank,
    ADD FOREIGN KEY (month_end_date) REFERENCES core.dim_month,
    ADD FOREIGN KEY (dpa)            REFERENCES core.dim_m4_line;

CREATE TABLE core.fact_m4_industry AS
SELECT r.fi_id::int                                         AS bank_id,
       min(r.industry_group)                                AS industry_group,
       r.calendar_month::date                               AS month_end_date,
       r.dpa,
       sum(nullif(trim(r.measure_value), '')::numeric(20, 2)) AS value_cad_k,
       count(DISTINCT r.dpa_label)::smallint                AS n_label_versions
FROM raw.m4_keylines r
GROUP BY r.fi_id, r.calendar_month, r.dpa;

ALTER TABLE core.fact_m4_industry
    ADD PRIMARY KEY (bank_id, month_end_date, dpa),
    ADD FOREIGN KEY (bank_id) REFERENCES core.dim_bank;
