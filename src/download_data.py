"""Download the latest OSFI bank files from the Government of Canada Open Data portal.

The repository already ships a compressed snapshot of every input (data/raw and
data/interim), so you only need this script to refresh the data with OSFI's
latest release.

What it does
------------
1. Asks the portal's CKAN API for the "Banks financial data" dataset.
2. Downloads three resources into data/raw/:
      banks_quarterly_e3.csv     E3, allowances for expected credit losses (quarterly)
      banks_monthly_m4.csv       M4, consolidated balance sheet (monthly, about 750 MB)
      data-dictionary-banks.xlsx data dictionary
3. You then run src/extract_m4.py to cut M4 down to the rows this project uses.

If the portal blocks scripted downloads, download the same three files by hand
from the dataset page below and save them in data/raw/ with the names above.

Usage
-----
    python src/download_data.py            # all three files
    python src/download_data.py --skip-m4  # E3 and the dictionary only

Data licence: Open Government Licence - Canada
https://open.canada.ca/en/open-government-licence-canada
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DATASET_ID = "91ed76b4-a1a2-4f87-9c4c-59cd64f7a9de"
DATASET_PAGE = f"https://open.canada.ca/data/en/dataset/{DATASET_ID}"
API = f"https://open.canada.ca/data/api/action/package_show?id={DATASET_ID}"

# file we want -> text that identifies it in the resource URL or name
WANTED = {
    "banks_quarterly_e3.csv": "banks_quarterly_e3",
    "banks_monthly_m4.csv": "banks_monthly_m4",
    "data-dictionary-banks.xlsx": "data-dictionary-banks",
}
# Direct links (resource ids as of October 2026), used if the API lookup fails
BASE = f"https://open.canada.ca/data/dataset/{DATASET_ID}/resource"
DIRECT = {
    "banks_quarterly_e3.csv": f"{BASE}/1f86e088-7d29-49c2-94de-ddbfe6559725/download/banks_quarterly_e3.csv",
    "banks_monthly_m4.csv": f"{BASE}/d0f6040e-671c-4301-a235-e9e7ba164604/download/banks_monthly_m4.csv",
    "data-dictionary-banks.xlsx": f"{BASE}/52af898b-9901-4239-b130-3aa25e5b3f14/download/data-dictionary-banks.xlsx",
}
HEADERS = {"User-Agent": "osfi-mortgage-credit-risk/1.0 (portfolio project; python urllib)"}


def resources() -> list[dict]:
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    if not payload.get("success"):
        raise RuntimeError(f"CKAN API returned an error: {payload.get('error')}")
    return payload["result"]["resources"]


def pick(items: list[dict], key: str) -> dict:
    matches = [r for r in items if key in (r.get("url") or "").lower()]
    if not matches:
        raise LookupError(f"No resource matching '{key}' in dataset {DATASET_ID}")
    return matches[0]


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {dest.name}: {done / 1e6:,.0f} of {total / 1e6:,.0f} MB", end="", flush=True)
    tmp.replace(dest)
    print(f"\r  {dest.name}: {dest.stat().st_size / 1e6:,.1f} MB" + " " * 20)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-m4", action="store_true", help="skip the large monthly M4 file")
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    try:
        urls = {}
        items = resources()
        for filename, key in WANTED.items():
            res = pick(items, key)
            print(f"{res.get('name', '').strip()}  (updated {res.get('last_modified') or res.get('created')})")
            urls[filename] = res["url"]
    except Exception as exc:  # API changed or unreachable: fall back to the known links
        print(f"API lookup failed ({exc}); using the direct links.")
        urls = dict(DIRECT)
    try:
        for filename, url in urls.items():
            if args.skip_m4 and filename.startswith("banks_monthly_m4"):
                continue
            download(url, RAW / filename)
    except Exception as exc:
        sys.exit(f"Download failed ({exc}).\nDownload the files by hand from {DATASET_PAGE} into {RAW}.")
    print("Done. Next: python src/extract_m4.py")


if __name__ == "__main__":
    main()
