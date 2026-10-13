# Data-quality log

22 checks run in PostgreSQL (`sql/04_quality_checks.sql`) every time the warehouse is rebuilt. Status: **Pass** (no issue), **Handled** (issue found and fixed in the SQL layer), **Warning** (issue disclosed next to the results it affects), **Open** (unexplained, worked around).

Pass: 5 · Handled: 9 · Warning: 7 · Open: 1

| ID | Area | Check | Status | Measured |
|---|---|---|---|---|
| DQ01 | Completeness | Big Six quarters present in E3 | Pass | 34 to 34 quarters per bank |
| DQ02 | Timeliness | Newest M4 month only partly filed | Handled | Aug 2026: 4 banks vs 52 normally |
| DQ03 | Uniqueness | Duplicate E3 rows with conflicting values | Handled | 88 rows (44 line items) |
| DQ04 | Uniqueness | M4 totals split across IFRS 9 and IAS 39 labels | Handled | 75 bank-month-lines in Nov 2017, Dec 2017 |
| DQ05 | Validity | E3 line codes reused for a different measure | Handled | 9 codes: 3193-3201 |
| DQ06 | Consistency | Institution name changes | Handled | 29 institution ids with 2+ names |
| DQ07 | Consistency | E3 fiscal quarters mapped to calendar month-ends | Pass | 8 of 8 banks best aligned at offset 0 |
| DQ08-BMO | Reconciliation | E3 vs M4 residential mortgages: BMO | Pass | gap 0.00% to 0.00% of E3 net |
| DQ08-BNS | Reconciliation | E3 vs M4 residential mortgages: BNS | Pass | gap -0.06% to 0.00% of E3 net |
| DQ08-CIBC | Reconciliation | E3 vs M4 residential mortgages: CIBC | Pass | gap 0.00% to 0.01% of E3 net |
| DQ08-NBC | Reconciliation | E3 vs M4 residential mortgages: NBC | Handled | gap 0.22% to 1.29% of E3 net |
| DQ08-RBC | Reconciliation | E3 vs M4 residential mortgages: RBC | Warning | gap -0.29% to -0.06% of E3 net |
| DQ08-TD | Reconciliation | E3 vs M4 residential mortgages: TD | Open | gap -9.09% to 0.00% of E3 net |
| DQ09 | Consistency | Uninsured exposure never exceeds total exposure | Warning | 4 violations in 713 bank-quarter-stages |
| DQ10 | Validity | Negative Stage 3 allowances | Warning | 24 bank-quarters (NBC, fiscal 2018 to 2023) |
| DQ11 | Completeness | Insured/uninsured split not reported | Handled | 15 bank-quarters missing |
| DQ12 | Comparability | Acquisitions add whole loan books in one month | Handled | RBC +34.4bn in Apr 2024 (target book 33.5bn); NBC +9.9bn in Feb 2025 (target book 9.4bn) |
| DQ13 | Comparability | Summing banks double-counts bank-owned subsidiaries | Warning | overstatement 0.71% to 1.30% of total domestic assets; 1 month(s) not fully explained |
| DQ14 | Comparability | Large one-quarter Stage 2 swings | Warning | 21 bank-quarters where Stage 2 exposure moved more than 40% in one quarter |
| DQ15 | Consistency | Fiscal 2018 allowance reported in two parts | Handled | 92 bank-quarter-stage rows built from components |
| DQ16 | Comparability | Returns are consolidated, including foreign mortgages | Warning | foreign-currency share of residential mortgages: BMO 17%, TD 15%, BNS 15%, NBC 10%, RBC 8%, CIBC 2% |
| DQ17 | Validity | CWB fiscal 2018 residential mortgages implausibly small | Warning | 4 quarters where E3 is under 1% of M4 |

### DQ01: Big Six quarters present in E3

**Status:** Pass · **Measured:** 34 to 34 quarters per bank

**Finding.** Every Big Six bank reports residential-mortgage stages for every fiscal quarter from Q1 2018 to the latest quarter.

**Action.** None needed.

### DQ02: Newest M4 month only partly filed

**Status:** Handled · **Measured:** Aug 2026: 4 banks vs 52 normally

**Finding.** The latest month in the M4 file had been filed by only a handful of banks when it was downloaded.

**Action.** Months where fewer than 90% of the usual number of banks reported are excluded; monthly analysis ends at the last complete month.

### DQ03: Duplicate E3 rows with conflicting values

**Status:** Handled · **Measured:** 88 rows (44 line items)

**Finding.** OSFI's E3 file repeats some keys with different values: Total All Banks fiscal Q4 2018.

**Action.** Both copies are moved to core.e3_quarantine and not used. They are industry totals, which this project does not use anyway.

### DQ04: M4 totals split across IFRS 9 and IAS 39 labels

**Status:** Handled · **Measured:** 75 bank-month-lines in Nov 2017, Dec 2017

**Finding.** During the IFRS 9 changeover, OSFI's industry totals appear twice per line: banks with an October year-end (already on IFRS 9) under the new label and banks with a December year-end under the old one. Taking one label would show a false 6-7% drop.

**Action.** The two rows cover different banks, so they are added together (core.fact_m4.n_label_versions records where).

### DQ05: E3 line codes reused for a different measure

**Status:** Handled · **Measured:** 9 codes: 3193-3201

**Finding.** Codes 3193-3201 meant "carrying amount of impaired assets" before 2018 and "net impaired amount" after. A series keyed on the code alone would splice two different measures.

**Action.** Line items are keyed on code + label (core.dim_e3_line).

### DQ06: Institution name changes

**Status:** Handled · **Measured:** 29 institution ids with 2+ names

**Finding.** Examples: Dundee Wealth Bank | Dundee Bank of Canada | Hollis Canadian Bank | ADS Canadian Bank; ING Bank of Canada | Tangerine Bank; Walmart Canada Bank | Duo Bank of Canada | Fairstone Bank of Canada.

**Action.** Banks are keyed on OSFI's id and labelled with their latest name (core.dim_bank).

### DQ07: E3 fiscal quarters mapped to calendar month-ends

**Status:** Pass · **Measured:** 8 of 8 banks best aligned at offset 0

**Finding.** E3 is labelled by each bank's own fiscal quarter, M4 by calendar month. Shifting E3 by -3..+3 months, quarter-on-quarter changes line up best with M4 at offset 0 for every bank, confirming October year-ends for the Big Six and CWB and a December year-end for HSBC Canada.

**Action.** core.fact_e3.quarter_end_date uses the verified year-end; OSFI's E3 industry totals mix year-ends and are not used.

### DQ08-BMO: E3 vs M4 residential mortgages: BMO

**Status:** Pass · **Measured:** gap 0.00% to 0.00% of E3 net

**Finding.** E3 gross minus E3 allowance equals the M4 balance to the dollar in 34 of 34 quarters.

**Action.** None needed.

### DQ08-BNS: E3 vs M4 residential mortgages: BNS

**Status:** Pass · **Measured:** gap -0.06% to 0.00% of E3 net

**Finding.** E3 gross minus E3 allowance equals the M4 balance to the dollar in 32 of 34 quarters; the others differ by less than 0.06%.

**Action.** None needed.

### DQ08-CIBC: E3 vs M4 residential mortgages: CIBC

**Status:** Pass · **Measured:** gap 0.00% to 0.01% of E3 net

**Finding.** E3 gross minus E3 allowance equals the M4 balance to the dollar in 34 of 34 quarters.

**Action.** None needed.

### DQ08-NBC: E3 vs M4 residential mortgages: NBC

**Status:** Handled · **Measured:** gap 0.22% to 1.29% of E3 net

**Finding.** E3 includes reverse mortgages; M4 reports them on a separate line. Adding that line closes the gap exactly.

**Action.** None needed.

### DQ08-RBC: E3 vs M4 residential mortgages: RBC

**Status:** Warning · **Measured:** gap -0.29% to -0.06% of E3 net

**Finding.** M4 is 0.1-0.3% above E3 net in every quarter; small and stable.

**Action.** None needed.

### DQ08-TD: E3 vs M4 residential mortgages: TD

**Status:** Open · **Measured:** gap -9.09% to 0.00% of E3 net

**Finding.** From fiscal Q2 2018, M4 is 4-9% above E3 net and the gap widens from 2023. E3 only covers loans that carry an expected-credit-loss allowance, so the likely cause is mortgages TD measures at fair value or holds for sale. TD's filings would be needed to confirm.

**Action.** All ratios use E3 for both numerator and denominator, so they are internally consistent; TD's balances are not compared across returns.

### DQ09: Uninsured exposure never exceeds total exposure

**Status:** Warning · **Measured:** 4 violations in 713 bank-quarter-stages

**Finding.** The "of which uninsured" line is larger than the total in: BMO fiscal 2020 Q1 Stage 3 (+$0.000bn); NBC fiscal 2020 Q4 Stage 2 (+$0.512bn); CIBC fiscal 2024 Q1 Stage 2 (+$2.883bn); CIBC fiscal 2024 Q2 Stage 2 (+$2.628bn). NBC's fiscal Q4 2020 Stage 2 total (about $0.2bn, against $1.5bn a quarter earlier and $1.5bn a quarter later) looks misfiled.

**Action.** Kept as reported and flagged; derived insured figures for these bank-quarters are negative and are not interpreted.

### DQ10: Negative Stage 3 allowances

**Status:** Warning · **Measured:** 24 bank-quarters (NBC, fiscal 2018 to 2023)

**Finding.** National Bank reports a negative Stage 3 allowance on residential mortgages from fiscal 2018 to 2023. Under IFRS 9, purchased or originated credit-impaired (POCI) loans can carry a negative allowance when expected recoveries improve after purchase (IFRS 9 para 5.5.14). OSFI's data does not identify POCI loans, so this is the likely, not confirmed, cause.

**Action.** Values are kept as reported. NBC's Stage 3 coverage is not used in peer comparisons for those years.

### DQ11: Insured/uninsured split not reported

**Status:** Handled · **Measured:** 15 bank-quarters missing

**Finding.** BNS first reports it for the quarter ending Oct 2021. Before then its uninsured lines are zero, which would wrongly make every mortgage "insured".

**Action.** Zeros are treated as "not reported", not as zero. Insured/uninsured metrics start when all six banks report them.

### DQ12: Acquisitions add whole loan books in one month

**Status:** Handled · **Measured:** RBC +34.4bn in Apr 2024 (target book 33.5bn); NBC +9.9bn in Feb 2025 (target book 9.4bn)

**Finding.** RBC's purchase of HSBC Bank Canada (closed 28 Mar 2024) and National Bank's purchase of Canadian Western Bank (closed 3 Feb 2025) each show up as a one-month jump about equal to the target's mortgage book.

**Action.** mart.m4_resi_monthly carries an organic growth rate that removes the acquired book for the 12 months it distorts year-over-year growth.

### DQ13: Summing banks double-counts bank-owned subsidiaries

**Status:** Warning · **Measured:** overstatement 0.71% to 1.30% of total domestic assets; 1 month(s) not fully explained

**Finding.** Adding up every domestic bank overstates OSFI's domestic total by $57-120bn because subsidiaries (Tangerine, B2B Bank, Concentra, Home Bank, ADS Canadian Bank, and CWB in Feb 2025) are already inside their parents' returns. With these identified, the gap is zero in every month except Jul 2026 ($5.4bn).

**Action.** This project compares the Big Six bank by bank and never sums institutions; OSFI's List of Bank Subsidiaries would resolve the remaining month.

### DQ14: Large one-quarter Stage 2 swings

**Status:** Warning · **Measured:** 21 bank-quarters where Stage 2 exposure moved more than 40% in one quarter

**Finding.** IFRS 9 leaves "significant increase in credit risk" to each bank's own criteria and models, so a bank's Stage 2 can jump or halve in one quarter when its models, assumptions or thresholds change. Recent examples: BMO Jan 2023 (+105%), CIBC Jul 2023 (+105%), BMO Apr 2024 (+137%), BNS Jul 2024 (+82%), BNS Apr 2025 (+72%), RBC Apr 2025 (+101%), RBC Apr 2026 (-50%).

**Action.** Peer comparisons lean on Stage 3 (credit-impaired), which follows a common 90-days-past-due backstop. Stage 2 is shown per bank, over time.

### DQ15: Fiscal 2018 allowance reported in two parts

**Status:** Handled · **Measured:** 92 bank-quarter-stage rows built from components

**Finding.** In fiscal 2018 E3 split each stage's allowance into individually and collectively assessed parts; from fiscal 2019 it reports one figure (OSFI change log, amendment 13).

**Action.** The two parts are added together; mart.credit_stage.ecl_basis records which rows were built this way.

### DQ16: Returns are consolidated, including foreign mortgages

**Status:** Warning · **Measured:** foreign-currency share of residential mortgages: BMO 17%, TD 15%, BNS 15%, NBC 10%, RBC 8%, CIBC 2%

**Finding.** E3 and M4 cover each bank's whole group, so mortgages in the US (BMO, TD), Latin America and the Caribbean (BNS) and Cambodia (NBC) are mixed with Canadian ones. E3 has no geographic split.

**Action.** Cross-bank differences in coverage are read with each bank's foreign share in mind (shown in the notebook and dashboards).

### DQ17: CWB fiscal 2018 residential mortgages implausibly small

**Status:** Warning · **Measured:** 4 quarters where E3 is under 1% of M4

**Finding.** Canadian Western Bank's fiscal 2018 E3 shows about $30 million of residential mortgages against about $7 billion in M4; from fiscal 2019 the two agree.

**Action.** CWB data is only used to size the book National Bank acquired in 2025, which comes from M4.
