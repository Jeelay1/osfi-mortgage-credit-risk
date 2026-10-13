"""Compare two folders of exported CSV files, allowing for floating-point noise.

Used by CI to prove the committed data/processed tables can be rebuilt exactly
from the raw OSFI snapshots:

    python src/compare_outputs.py /tmp/committed data/processed
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


def compare(a: Path, b: Path) -> list[str]:
    problems = []
    names_a = {p.name for p in a.glob("*.csv")}
    names_b = {p.name for p in b.glob("*.csv")}
    if names_a != names_b:
        problems.append(f"different files: {sorted(names_a ^ names_b)}")
    for name in sorted(names_a & names_b):
        x, y = pd.read_csv(a / name), pd.read_csv(b / name)
        if list(x.columns) != list(y.columns) or len(x) != len(y):
            problems.append(f"{name}: shape or columns differ {x.shape} vs {y.shape}")
            continue
        for col in x.columns:
            if pd.api.types.is_numeric_dtype(x[col]) and pd.api.types.is_numeric_dtype(y[col]):
                if not np.allclose(x[col], y[col], rtol=1e-9, atol=1e-9, equal_nan=True):
                    worst = (x[col] - y[col]).abs().max()
                    problems.append(f"{name}.{col}: values differ (max abs diff {worst:.3g})")
            elif not x[col].astype(str).equals(y[col].astype(str)):
                problems.append(f"{name}.{col}: text differs")
    return problems


def main() -> None:
    a, b = Path(sys.argv[1]), Path(sys.argv[2])
    problems = compare(a, b)
    if problems:
        print("Outputs differ:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"All {len(list(a.glob('*.csv')))} tables match.")


if __name__ == "__main__":
    main()
