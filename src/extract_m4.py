"""Cut OSFI's monthly M4 file (about 750 MB) down to the rows this project uses.

The full banks_monthly_m4.csv holds every balance-sheet line for every bank
and every month OSFI publishes. This script streams it once (constant memory)
and writes two compressed extracts to data/interim/:

  m4_focus_2017plus.csv.gz
      Every M4 line, from 2017, for the institutions the analysis needs:
      the Big Six, the two banks they bought (HSBC Bank Canada, Canadian
      Western Bank), bank subsidiaries that file their own returns, and the
      OSFI industry totals.

  m4_all_institutions_keylines_2017plus.csv.gz
      A few key lines (total assets, residential mortgages, personal and
      business loans), from 2017, for every bank. Used to test whether OSFI's
      industry totals double count subsidiaries.

French duplicate columns are dropped and the columns are renamed to snake_case.

Usage
-----
    python src/extract_m4.py                        # reads data/raw/banks_monthly_m4.csv
    python src/extract_m4.py --source path/to/banks_monthly_m4.csv
"""

from __future__ import annotations

import argparse
import csv
import gzip
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "raw" / "banks_monthly_m4.csv"
OUT = ROOT / "data" / "interim"
FIRST_YEAR = 2017

FOCUS_IDS = {
    "27996", "27997", "27998", "27999", "28000", "28002",  # CIBC, RBC, BMO, TD, BNS, NBC
    "28058", "28010",                                       # HSBC Bank Canada, Canadian Western Bank (acquired)
    "28337", "28454", "28326", "149032", "28456",           # subsidiaries and other banks checked for double counting
    "1000000", "1000001", "1000002",                        # OSFI industry totals
}
KEY_DPA = {
    "1045",  # total assets
    "0540",  # residential mortgages, insured
    "0542",  # residential mortgages, uninsured
    "2117",  # non-residential mortgages
    "0534",  # personal (non-business) loans
    "0572",  # business and government loans
}
# position in the bilingual source file -> output column (French duplicates dropped)
KEEP = {0: "calendar_year", 1: "calendar_month", 2: "id", 3: "fi", 5: "industry_group", 7: "return",
        8: "return_title", 10: "dpa", 11: "label", 13: "fi_inactive_date", 14: "value"}


def check_header(header: list[str]) -> None:
    expected = {0: "calendar year", 2: "id", 10: "data point address", 14: "measure value"}
    bad = {i: header[i] if i < len(header) else None for i, text in expected.items()
           if i >= len(header) or not header[i].strip().lower().startswith(text)}
    if len(header) != 15 or bad:
        sys.exit(f"Unexpected M4 layout ({len(header)} columns; mismatches: {bad}).\nHeader: {header}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the M4 rows used by this project.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    if not args.source.exists():
        sys.exit(f"Missing {args.source}. Run src/download_data.py first.")

    OUT.mkdir(parents=True, exist_ok=True)
    focus_path = OUT / "m4_focus_2017plus.csv.gz"
    key_path = OUT / "m4_all_institutions_keylines_2017plus.csv.gz"
    started = time.perf_counter()
    n_in = n_focus = n_key = 0
    with args.source.open(encoding="utf-8-sig", newline="") as src, \
            gzip.open(focus_path, "wt", encoding="utf-8", newline="") as f_focus, \
            gzip.open(key_path, "wt", encoding="utf-8", newline="") as f_key:
        reader = csv.reader(src)
        check_header(next(reader))
        w_focus, w_key = csv.writer(f_focus), csv.writer(f_key)
        w_focus.writerow(KEEP.values())
        w_key.writerow(KEEP.values())
        for row in reader:
            n_in += 1
            if not row or int(row[0]) < FIRST_YEAR:
                continue
            out = [row[i] for i in KEEP]
            if row[2] in FOCUS_IDS:
                w_focus.writerow(out)
                n_focus += 1
            if row[10] in KEY_DPA:
                w_key.writerow(out)
                n_key += 1
            if n_in % 5_000_000 == 0:
                print(f"  {n_in:,} rows read...", flush=True)
    print(f"Read {n_in:,} rows in {time.perf_counter() - started:.0f}s")
    print(f"  {focus_path.name}: {n_focus:,} rows")
    print(f"  {key_path.name}: {n_key:,} rows")


if __name__ == "__main__":
    main()
