# Dashboards

Two dashboards read the same exported tables (`data/processed/`), so their numbers match the notebook.

## Power BI: `powerbi/MortgageCreditRisk.pbip`

A Power BI Project (PBIP): the report is stored in the PBIR format and the semantic model in TMDL, so every page, visual and DAX measure is a readable text file under version control.

**Open it**

1. Install Power BI Desktop (Windows, free) and open `powerbi/MortgageCreditRisk.pbip`.
2. The project ships without cached data. Select **Refresh**. The queries read the CSVs straight from this repository on GitHub; if asked how to connect to `raw.githubusercontent.com`, choose **Anonymous**.
3. To work offline instead: **Transform data > Edit parameters**, set `DataSource` to `Local folder` and `LocalDataFolder` to the full path of your `data/processed` folder.

**Model**: star schema with `Bank`, `Calendar` (monthly, with Big Six fiscal periods and a fiscal hierarchy), `Product`, `Insurance` and `Stage` dimensions around three fact tables: `Credit Stage` (E3), `Mortgage Balances` (M4) and `Reconciliation`. Disconnected tables drive the metric selector, the what-if scenario and the allowance bridge. Power Query loads every CSV through one function (`fnReadCsv`), converts $ millions to dollars and types every column with an explicit culture.

**Pages**

| Page | What it answers |
|---|---|
| Overview | Where credit quality stands now: exposure, Stage 2 and 3 shares, allowance and coverage, each with the change on a year earlier; Stage 3 trend and latest ranking by bank |
| Metric explorer | Pick any of six credit metrics and compare banks over time, by fiscal year (heat-mapped matrix) and on the year-earlier change |
| Allowances | What moved the allowance (bridge for the Big Six or any bank), insured vs. uninsured coverage, allowance by stage, and a what-if: extra allowance if 0.5-5% of the book left Stage 1 |
| Mortgage book | Monthly balances, insured share, and growth with and without acquisitions |
| Trend model | The interrupted time-series fit from the notebook, with how to read it |
| Data quality | The 22 automated checks and the E3-to-M4 reconciliation gap by bank |

**Measures** (82, all in the `Key Measures` table). Balances are semi-additive: every balance measure takes the latest period in context instead of summing over time, so a card shows the latest quarter and a fiscal-year matrix shows each year's last quarter. Totals are only shown when every bank in view has reported.

*Exposure*: `Gross Exposure`, `Stage 1 Exposure`, `Stage 2 Exposure`, `Stage 3 Exposure`, `Total Exposure`, `Stage 2 Share`, `Stage 3 Share`, `Share of Exposure`

*Allowance and coverage*: `Allowance`, `Stage 1 Allowance`, `Stage 2 Allowance`, `Stage 3 Allowance`, `Total Allowance`, `Allowance Coverage`, `Allowance Coverage (bp)`, `Stage 1 Coverage`, `Stage 2 Coverage`, `Stage 3 Coverage`, `Insured Coverage (bp)`, `Uninsured Coverage (bp)`, `Uninsured Share`, `Uninsured Share of Allowance`

*Year over year*: `Latest Quarter`, `Prior-Year Quarter`, `Total Exposure (Prior Year)`, `Total Allowance (Prior Year)`, `Stage 2 Share (Prior Year)`, `Stage 3 Share (Prior Year)`, `Allowance Coverage (bp, Prior Year)`, `Exposure Growth YoY`, `Allowance Growth YoY`, `Stage 2 Share YoY (pp)`, `Stage 3 Share YoY (pp)`, `Allowance Coverage YoY (bp)`

*Peers*: `Stage 2 Share Peer Median`, `Stage 3 Share Peer Median`, `Allowance Coverage Peer Median (bp)`, `Stage 3 Share vs Peer Median (pp)`, `Stage 3 Share Rank`

*Metric selector*: `Selected Metric`, `Selected Metric YoY (pp)`, `Selected Metric Peer Median`, `Selected Metric Title`

*Mortgage book (M4)*: `Latest Month`, `Mortgage Balance`, `Insured Balance`, `Uninsured Balance`, `Reverse Mortgage Balance`, `Foreign Currency Balance`, `Insured Share`, `Foreign Currency Share`, `Mortgage Balance (Prior Year)`, `Mortgage Growth YoY`, `Acquired Book in YoY Window`, `Organic Growth YoY`, `Mortgage Share of Assets`

*Reconciliation*: `Reconciliation Gap`, `Reconciliation Gap %`

*Allowance bridge*: `Bridge Bank`, `Allowance Bridge Amount`, `Allowance Bridge Title`

*Trend model*: `Stage 3 Actual (bp)`, `Stage 3 Fitted (bp)`, `Stage 3 Pre-hike Trend (bp)`

*What-if migration*: `Migration Share`, `Book Migrating`, `Extra Allowance, Stage 1 to 2`, `Extra Allowance, Stage 1 to 3`, `Extra Allowance, Stage 1 to 2 (% of Allowance)`, `Extra Allowance, Stage 1 to 3 (% of Allowance)`

*Data quality*: `Checks`, `Checks Passed`, `Checks Handled`, `Checks Flagged`

*Labels*: `As Of Label`, `Exposure YoY Label`, `Allowance YoY Label`, `Stage 2 Share YoY Label`, `Stage 3 Share YoY Label`, `Coverage YoY Label`, `Mortgage Growth Label`, `Mortgage As Of Label`

**Numbers to expect** with no slicers set (computed independently from the CSVs by `src/build_docs.py`):

| Page | Item | Value |
|---|---|---|
| Overview | Quarter shown | April 30, 2026 |
| Overview | Gross exposure | $1.79T (+1.5% vs. a year earlier) |
| Overview | Stage 2 share | 5.75% (-0.91 pp) |
| Overview | Stage 3 share | 0.57% (+0.12 pp) |
| Overview | Allowance | $3.90bn (+10.9%) |
| Overview | Coverage | 21.8 bp (+1.9 bp) |
| Overview | Stage 3 share by bank | NBC 1.18%, BNS 0.79%, BMO 0.54%, CIBC 0.53%, RBC 0.43%, TD 0.36% |
| Allowances | Bridge, Big Six ($M) | 2,039 → organic +462, acquired +76, stage mix +1,138, coverage rates +184 → 3,900 |
| Allowances | Coverage, insured / uninsured (bp) | RBC 12.3 / 19.4, TD 6.3 / 18.5, BNS 4.9 / 47.8, BMO 1.6 / 14.0, CIBC 3.5 / 20.8, NBC 4.9 / 38.4 |
| Allowances | What-if total row (1% of book) | Stage 2: $232M (5.9%); Stage 3: 77.9% of allowance |
| Mortgage book | Month shown | July 31, 2026 |
| Mortgage book | Residential mortgages | $1.83T |
| Mortgage book | Growth / organic growth | 1.7% / 1.7% |
| Mortgage book | Insured / foreign-currency share | 21.6% / 10.9% |
| Data quality | Checks run / passed / handled / flagged | 22 / 5 / 9 / 8 |
| Data quality | Reconciliation gap, latest quarter | RBC -0.23%, TD -9.09%, BNS 0.00%, BMO 0.00%, CIBC 0.00%, NBC 0.22% |

## Tableau: `tableau/OSFI_Mortgage_Credit_Risk.twbx`

A packaged workbook: the CSVs and the extracts built from them travel inside it. Open it with Tableau Public or Tableau Desktop 2022.1 or later.

| Dashboard | Sheets | Techniques |
|---|---|---|
| Credit quality | Metric trend; Latest quarter by bank; Change from low | Parameter-driven metric (`CASE` on a parameter), dynamic sheet title, nested FIXED level-of-detail expressions (each bank's own low point and the quarter it happened), `RANK` table calculation, fixed bank colours |
| Mortgage book | Mortgage balances; Insured share | Monthly continuous dates, ratio-of-sums calculations |

Both data sources ship as Hyper extracts built from the packaged CSVs, because Tableau Public only opens workbooks whose data are extracts. **Publish to Tableau Public**: open the workbook in Tableau Public, then **File > Save to Tableau Public As...**.
