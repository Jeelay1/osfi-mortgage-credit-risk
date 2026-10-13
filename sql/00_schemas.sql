-- =============================================================================
-- 00_schemas.sql
-- Creates the three-layer warehouse used by this project:
--   raw   : OSFI files loaded as-is (every column as text, nothing dropped)
--   core  : typed dimensions and facts (star schema)
--   mart  : analysis-ready tables consumed by the notebook, Power BI and Tableau
-- Target: PostgreSQL 16
-- =============================================================================

DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
DROP SCHEMA IF EXISTS raw  CASCADE;

CREATE SCHEMA raw;
CREATE SCHEMA core;
CREATE SCHEMA mart;

-- E3: Return of Allowances for Expected Credit Losses (quarterly, fiscal quarters)
CREATE TABLE raw.e3 (
    fiscal_year         text,
    fiscal_quarter      text,   -- e.g. 'Q2 - 2026' (the bank's OWN fiscal quarter)
    fiscal_quarter_fr   text,
    fi_id               text,
    fi_name             text,
    fi_name_fr          text,
    industry_group      text,
    industry_group_fr   text,
    return_code         text,
    return_title        text,
    return_title_fr     text,
    dpa                 text,   -- data point address (line-item code)
    dpa_label           text,
    dpa_label_fr        text,
    fi_inactive_date    text,
    measure_value       text    -- thousands of Canadian dollars
);

-- M4: Consolidated Balance Sheet (monthly, calendar month-ends).
-- The full file is 751 MB; src/extract_m4.py keeps 2017+ rows for the banks
-- studied here (all line items) and English columns only.
CREATE TABLE raw.m4 (
    calendar_year       text,
    calendar_month      text,   -- month-end date, e.g. '2026-07-31'
    fi_id               text,
    fi_name             text,
    industry_group      text,
    return_code         text,
    return_title        text,
    dpa                 text,
    dpa_label           text,
    fi_inactive_date    text,
    measure_value       text
);

-- Same layout: every institution, but only a handful of headline lines
-- (total assets and mortgage lines). Used for the subsidiary double-count check.
CREATE TABLE raw.m4_keylines (LIKE raw.m4);
