"""Shared fixtures: the processed tables that the notebook and dashboards read."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "src"))

BIG_SIX = {"RBC", "TD", "BNS", "BMO", "CIBC", "NBC"}


def read(name: str) -> pd.DataFrame:
    dates = [c for c in pd.read_csv(PROCESSED / f"{name}.csv", nrows=0).columns
             if c.endswith("_date") or c in ("start_quarter", "end_quarter")]
    return pd.read_csv(PROCESSED / f"{name}.csv", parse_dates=dates)


@pytest.fixture(scope="session")
def credit_stage() -> pd.DataFrame:
    return read("fact_credit_stage")


@pytest.fixture(scope="session")
def quarterly() -> pd.DataFrame:
    return read("resi_mortgage_quarterly")


@pytest.fixture(scope="session")
def monthly() -> pd.DataFrame:
    return read("m4_resi_monthly")


@pytest.fixture(scope="session")
def processed():
    return read
