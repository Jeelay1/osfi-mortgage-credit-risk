"""Consistency checks for the Power BI project and the Tableau workbook.

These do not need Power BI or Tableau installed: they read the files as text,
JSON and XML and check that every field a visual uses exists in the model and
every file a data source points to is in the package.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile

import pytest

from conftest import ROOT

PBI = ROOT / "powerbi"
MODEL = PBI / "MortgageCreditRisk.SemanticModel" / "definition"
REPORT = PBI / "MortgageCreditRisk.Report" / "definition"
TWBX = ROOT / "tableau" / "OSFI_Mortgage_Credit_Risk.twbx"


def unquote(name: str) -> str:
    name = name.strip()
    if name.startswith("'") and name.endswith("'"):
        name = name[1:-1].replace("''", "'")
    return name


@pytest.fixture(scope="module")
def model() -> dict:
    """{table: {"Column": {...}, "Measure": {...}}} parsed from the TMDL files."""
    out = {}
    for path in sorted((MODEL / "tables").glob("*.tmdl")):
        text = path.read_text(encoding="utf-8")
        table = unquote(re.search(r"^table (.+)$", text, re.M).group(1))
        out[table] = {
            "Column": {unquote(m) for m in re.findall(r"^\tcolumn (.+?)\s*$", text, re.M)},
            "Measure": {unquote(m) for m in re.findall(r"^\tmeasure (.+?) =", text, re.M)},
        }
    return out


def fields(obj, found):
    if isinstance(obj, dict):
        for kind in ("Column", "Measure"):
            node = obj.get(kind)
            if isinstance(node, dict) and "Property" in node and "Entity" in node.get("Expression", {}).get("SourceRef", {}):
                found.append((kind, node["Expression"]["SourceRef"]["Entity"], node["Property"]))
        for v in obj.values():
            fields(v, found)
    elif isinstance(obj, list):
        for v in obj:
            fields(v, found)
    return found


def test_semantic_model_has_the_expected_tables(model):
    expected = {"Bank", "Calendar", "Product", "Insurance", "Stage", "Credit Stage", "Mortgage Balances",
                "Reconciliation", "Allowance Drivers", "Stage 3 Trend Model", "Data Quality", "Metric",
                "Migration Scenario", "Key Measures"}
    assert expected <= set(model)
    assert len(model["Key Measures"]["Measure"]) >= 60


def test_relationships_point_at_real_columns(model):
    text = (MODEL / "relationships.tmdl").read_text(encoding="utf-8")
    ends = re.findall(r"(?:fromColumn|toColumn): (.+)$", text, re.M)
    assert len(ends) >= 20
    for end in ends:
        table, column = re.match(r"('(?:[^']|'')+'|[^.]+)\.(.+)$", end.strip()).groups()
        assert unquote(column) in model[unquote(table)]["Column"], end


def test_every_report_field_exists_in_the_model(model):
    visuals = sorted(REPORT.glob("pages/*/visuals/*/visual.json"))
    assert len(visuals) >= 40
    for path in visuals:
        for kind, table, prop in fields(json.loads(path.read_text(encoding="utf-8")), []):
            assert table in model, f"{path}: unknown table {table}"
            assert prop in model[table][kind], f"{path}: {kind} {table}[{prop}] missing"


def test_pages_metadata_matches_page_folders():
    meta = json.loads((REPORT / "pages" / "pages.json").read_text(encoding="utf-8"))
    folders = {p.parent.name for p in REPORT.glob("pages/*/page.json")}
    assert set(meta["pageOrder"]) == folders
    for name in folders:
        page = json.loads((REPORT / "pages" / name / "page.json").read_text(encoding="utf-8"))
        assert page["name"] == name


def test_dax_measures_only_reference_known_measures(model):
    text = (MODEL / "tables" / "Key Measures.tmdl").read_text(encoding="utf-8")
    text = text.split("\n\tpartition ")[0]  # measures only, not the Power Query of the placeholder table
    measures = model["Key Measures"]["Measure"]
    # bare [Name] references (not preceded by a table name) must be measures
    for ref in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", text):
        assert ref in measures, ref


@pytest.fixture(scope="module")
def twb():
    with zipfile.ZipFile(TWBX) as z:
        names = set(z.namelist())
        twb_name = next(n for n in names if n.endswith(".twb"))
        root = ET.fromstring(z.read(twb_name))
    return root, names


def test_tableau_package_contains_its_data(twb):
    root, names = twb
    files = [c for c in root.iter("connection") if c.get("class") == "textscan"]
    assert len(files) == 2
    for c in files:
        assert f"{c.get('directory')}/{c.get('filename')}" in names


def test_tableau_calculations_reference_defined_fields(twb):
    root, _ = twb
    for ds in root.find("datasources"):
        if ds.get("name") == "Parameters":
            continue
        defined = {c.get("name") for c in ds.findall("column")}
        defined |= {f"[{rec.findtext('remote-name')}]" for rec in ds.iter("metadata-record")
                    if rec.get("class") == "column"}
        for col in ds.findall("column"):
            calc = col.find("calculation")
            if calc is None:
                continue
            for ref in re.findall(r"(\[[^\]]+\])(?!\.)", calc.get("formula")):
                if ref == "[Parameters]":
                    continue
                assert ref in defined or ref == "[Parameter 1]", f"{col.get('caption')}: {ref}"


def test_tableau_dashboards_use_existing_sheets(twb):
    root, _ = twb
    sheets = {w.get("name") for w in root.find("worksheets")}
    for dash in root.find("dashboards"):
        for zone in dash.iter("zone"):
            if zone.get("name") and zone.get("type-v2") in (None, "color"):
                assert zone.get("name") in sheets
