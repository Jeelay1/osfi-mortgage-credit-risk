# Data

All inputs come from the Office of the Superintendent of Financial Institutions (OSFI),
[Banks financial data](https://open.canada.ca/data/en/dataset/91ed76b4-a1a2-4f87-9c4c-59cd64f7a9de)
on the Government of Canada Open Data portal.

Contains information licensed under the
[Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).

## Snapshot used in this project (downloaded 30 September 2026)

| File | Contents | SHA-256 (first 16) |
|---|---|---|
| `raw/banks_quarterly_e3.csv.gz` | E3, Return of Allowances for Expected Credit Losses: every bank, fiscal 1996 to Q2 2026 (145,957 rows) | `8c523ff541b3228d` |
| `raw/data-dictionary-banks.xlsx` | OSFI's data dictionary | `aea9d1878335080b` |
| `interim/m4_focus_2017plus.csv.gz` | M4, Consolidated Balance Sheet: every line, Jan 2017 to Aug 2026, for the 16 institutions studied (259,022 rows) | `ffd93830d4397b41` |
| `interim/m4_all_institutions_keylines_2017plus.csv.gz` | M4: six headline lines, Jan 2017 to Aug 2026, for every bank (32,233 rows) | `8f2b81f3af073fc3` |

The full M4 file is about 750 MB, so only the extract made by `src/extract_m4.py` is kept.
The compressed snapshot makes every number in this project reproducible even after OSFI
revises or extends its files. `src/build_database.py` reads the `.csv.gz` files directly.

## Refreshing the data

```bash
python src/download_data.py   # latest E3, M4 and data dictionary into data/raw/
python src/extract_m4.py      # cut M4 down to data/interim/
make all                      # rebuild the warehouse, tables, notebook and summary
```

## Folders

| Folder | What is in it | In git? |
|---|---|---|
| `raw/` | Files as published by OSFI | compressed snapshot only |
| `interim/` | M4 extract | compressed snapshot only |
| `processed/` | Tables exported from the PostgreSQL marts and the Python models; read by the notebook, Power BI and Tableau. See `docs/data_dictionary.md` | yes |
