"""Build the PostgreSQL warehouse from the OSFI files.

Steps
-----
1. Run sql/00_schemas.sql (creates the raw / core / mart schemas and raw tables).
2. Bulk-load the CSV files into the raw tables with COPY.
3. Run every remaining sql/NN_*.sql file in order (dimensions, facts, marts,
   data-quality checks).

Inputs are read from data/raw and data/interim, either as plain .csv or as the
compressed .csv.gz snapshot that ships with the repository.

Usage
-----
    python src/build_database.py

The connection string comes from the DATABASE_URL environment variable and
defaults to a local PostgreSQL 16 server: postgresql://postgres@localhost:5433/osfi
"""

from __future__ import annotations

import gzip
import os
import sys
import time
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5433/osfi")

RAW_FILES = {
    "raw.e3": ROOT / "data" / "raw" / "banks_quarterly_e3.csv",
    "raw.m4": ROOT / "data" / "interim" / "m4_focus_2017plus.csv",
    "raw.m4_keylines": ROOT / "data" / "interim" / "m4_all_institutions_keylines_2017plus.csv",
}


def open_input(path: Path):
    """Open the plain CSV if present, otherwise the compressed snapshot."""
    if path.exists():
        return path.open("rb"), path.name
    gz = path.with_name(path.name + ".gz")
    if gz.exists():
        return gzip.open(gz, "rb"), gz.name
    sys.exit(f"Missing input file: {path} (or {gz.name})\n"
             "Run src/download_data.py and src/extract_m4.py first.")


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    started = time.perf_counter()
    conn.execute(path.read_text(encoding="utf-8"))
    print(f"  ran {path.name:<28} {time.perf_counter() - started:6.1f}s")


def copy_csv(conn: psycopg.Connection, table: str, path: Path) -> int:
    """Stream a CSV file (with header) into an existing table using COPY."""
    started = time.perf_counter()
    source, label = open_input(path)
    with conn.cursor() as cur:
        with source as f, cur.copy(
            f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"
        ) as copy:
            while chunk := f.read(1 << 20):
                copy.write(chunk)
        n_rows = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(f"  loaded {table:<18} {n_rows:>10,} rows {time.perf_counter() - started:6.1f}s  ({label})")
    return n_rows


def main() -> None:
    sql_files = sorted(SQL_DIR.glob("[0-9][0-9]_*.sql"))
    print(f"Building warehouse in {DATABASE_URL}")
    with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
        run_sql_file(conn, sql_files[0])          # 00_schemas.sql
        for table, path in RAW_FILES.items():
            copy_csv(conn, table, path)
        for path in sql_files[1:]:
            run_sql_file(conn, path)
        conn.commit()
    print("Done.")


if __name__ == "__main__":
    main()
