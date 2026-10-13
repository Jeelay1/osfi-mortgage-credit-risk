"""Build the one-page executive summary (reports/executive_summary.pdf).

Every number is taken from the same facts the notebook quotes
(build_notebook.gather_facts), so the summary cannot disagree with the analysis.

Usage:
    python src/build_summary.py [--repo-url URL]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import analysis as an  # noqa: E402
import build_notebook as bn  # noqa: E402
import charts as ch  # noqa: E402

OUT = ROOT / "reports" / "executive_summary.pdf"
FIG = ROOT / "reports" / "figures"
INK, INK2, MUTED, RULE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


def styles() -> dict:
    base = dict(fontName="Helvetica", textColor=colors.HexColor(INK), alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("title", **{**base, "fontName": "Helvetica-Bold"}, fontSize=17, leading=21),
        "sub": ParagraphStyle("sub", **{**base, "textColor": colors.HexColor(INK2)}, fontSize=8.8, leading=12),
        "h": ParagraphStyle("h", **{**base, "fontName": "Helvetica-Bold"}, fontSize=10.2, leading=13,
                            spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("body", **base, fontSize=8.9, leading=11.7),
        "bullet": ParagraphStyle("bullet", **base, fontSize=8.7, leading=11.2),
        "cell": ParagraphStyle("cell", **base, fontSize=8, leading=10),
        "cap": ParagraphStyle("cap", **{**base, "textColor": colors.HexColor(INK2)}, fontSize=7.4, leading=9.2),
        "foot": ParagraphStyle("foot", **{**base, "textColor": colors.HexColor(MUTED)}, fontSize=7, leading=9),
    }


def pct(x: float, d: int = 0) -> str:
    return f"{x * 100:.{d}f}%"


def bullets(items: list[str], st: ParagraphStyle, numbered: bool = False) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(t, st), leftIndent=12, value=i + 1 if numbered else None) for i, t in enumerate(items)],
        bulletType="1" if numbered else "bullet", start="1" if numbered else None,
        bulletFontName="Helvetica-Bold" if numbered else "Helvetica", bulletFontSize=8.2, leftIndent=12,
        bulletColor=colors.HexColor(INK2))


def compact_charts(folder: Path) -> tuple[Path, Path]:
    """Small, title-free versions of the two headline charts, sized for this page."""
    ch.use_style()
    its = an.load("its_results")
    main = its[its["specification"].str.startswith("Main")].set_index("model").loc["Big Six combined"]
    figs = {
        "its.png": ch.headline_its(an.load("its_fitted"), main, "", compact=True),
        "drivers.png": ch.decomposition_waterfall(
            an.load("allowance_decomposition").set_index("short_name").loc["Big Six"], "", compact=True),
    }
    for name, fig in figs.items():
        fig.savefig(folder / name, dpi=300)
        plt.close(fig)
    return folder / "its.png", folder / "drivers.png"


def peer_table(fx: dict, st: dict) -> Table:
    """Residential mortgages by bank at the latest quarter, Big Six combined last."""
    q = an.load("resi_mortgage_quarterly")
    latest, low_q = fx["latest"], fx["low_q"]
    now = q[q["quarter_end_date"] == latest].set_index("short_name")
    low = q[q["quarter_end_date"] == low_q].set_index("short_name")
    head = ["", "Gross exposure", "Stage 2 share", "Stage 3 share", f"Stage 3 vs {low_q:%b %Y}",
            "Coverage", "Uninsured coverage"]
    rows = [head]
    for b in ch.BANK_ORDER + ["Big Six"]:
        r = now.loc[b]
        rows.append([b, f"${r['gross_total_cad_mn'] / 1e3:,.0f}bn", pct(r["stage2_share"], 2),
                     pct(r["stage3_share"], 2), f"{(r['stage3_share'] - low.loc[b, 'stage3_share']) * 100:+.2f} pp",
                     f"{r['coverage_bps']:.1f} bp", f"{r['coverage_uninsured_bps']:.1f} bp"])
    widths = [0.7, 1.05, 1.0, 1.0, 1.3, 0.95, 1.3]
    table = Table(rows, colWidths=[w * inch for w in widths], rowHeights=[12] * len(rows), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.9),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.6),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 7.9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(INK2)),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(INK)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(RULE)),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor(RULE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]))
    return table


def build(repo_url: str, tmp: str) -> Path:
    fx = bn.gather_facts()
    st = styles()
    low_q = f"{fx['low_q']:%b %Y}"
    latest = fx["latest_label"]
    mig_ratio = fx["mig_s3_bn"] * 1000 / fx["mig_s2_mn"]

    story = [
        Paragraph("Mortgage credit risk at Canada's Big Six banks", st["title"]),
        Spacer(1, 2),
        Paragraph(f"Executive summary &nbsp;·&nbsp; OSFI regulatory returns E3 and M4, fiscal 2018 to "
                  f"{fx['latest_fq']} (quarter ending {latest}) &nbsp;·&nbsp; Jeelay Pillai", st["sub"]),
        Spacer(1, 6),
        Table([[""]], colWidths=[7.3 * inch], rowHeights=[1],
              style=TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.HexColor(RULE))])),
        Paragraph("Overview", st["h"]),
        Paragraph(
            "About 60% of Canadian mortgages renew in 2025 and 2026, most at higher payments. Using the returns the "
            f"Big Six file with their regulator, OSFI, this project measures how credit quality in their "
            f"${fx['book_latest_t']:.2f} trillion residential mortgage book has changed since rates started rising "
            "in March 2022, what drove the rise in loan-loss allowances, and where the risk sits. The public data "
            f"needed real cleaning first: {fx['n_checks']} automated checks are built into the pipeline.",
            st["body"]),
    ]

    w = 3.58 * inch
    its_png, drivers_png = compact_charts(Path(tmp))
    figs = Table(
        [[Image(str(its_png), width=w, height=w * 2.8 / 5), Image(str(drivers_png), width=w, height=w * 2.8 / 5)],
         [Paragraph("Stage 3 (impaired) share of mortgages, Big Six combined. The trend turned up after the first "
                    "rate hike.", st["cap"]),
          Paragraph(f"What moved the mortgage allowance from Jan 2022 to {latest}: "
                    f"{pct(fx['mix_share'])} came from loans migrating into Stages 2 and 3.", st["cap"])]],
        colWidths=[w + 0.07 * inch, w + 0.07 * inch],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 1), (-1, 1), 2)]))
    story += [Spacer(1, 7), figs]

    story += [
        Paragraph("Key findings", st["h"]),
        bullets([
            f"<b>Impaired mortgages more than doubled from the low.</b> The Stage 3 share rose from "
            f"{pct(fx['s3_low'], 2)} ({low_q}) to {pct(fx['s3_latest'], 2)} ({latest}), from "
            f"${fx['s3_gross_low_bn']:.1f} billion to ${fx['s3_gross_latest_bn']:.1f} billion, and it is up at all "
            "six banks.",
            f"<b>The trend reversed after the hikes.</b> An interrupted time-series model puts the trend at "
            f"{fx['its_pre']:+.1f} bp a quarter before the first hike and {fx['its_post']:+.1f} bp after "
            "(p &lt; 0.001), robust to the break date and to dropping the pandemic quarters.",
            f"<b>Allowances rose {pct(fx['ecl_change_pct'])}</b>, from ${fx['ecl_jan22_bn']:.2f} billion to "
            f"${fx['ecl_latest_bn']:.2f} billion (coverage {fx['cov_jan22']:.1f} to {fx['cov_latest']:.1f} bp). "
            f"{pct(fx['mix_share'])} of the rise came from stage migration and only {pct(fx['rate_share'])} from "
            "holding more per dollar of loans.",
            f"<b>The risk sits in uninsured loans:</b> {pct(fx['unins_share_latest'])} of the book but "
            f"{pct(fx['unins_ecl_share_latest'])} of the allowance. The insured share of the book fell from "
            f"{pct(fx['ins_share_2018'])} in 2018 to {pct(fx['ins_share_latest'])}.",
            f"<b>Stage 3 is the expensive move.</b> Shifting 1% of the book from Stage 1 to Stage 3 would add "
            f"${fx['mig_s3_bn']:.1f} billion of allowance ({pct(fx['mig_s3_pct'])} of today's), about "
            f"{mig_ratio:.0f} times the cost of the same shift into Stage 2.",
        ], st["bullet"]),
        Paragraph(f"Peer snapshot, quarter ending {latest}", st["h"]),
        peer_table(fx, st),
        Paragraph("Recommendations for a retail credit risk team", st["h"]),
        bullets([
            "<b>Watch Stage 3 in the uninsured book first:</b> it is the most comparable signal across banks and "
            "it is where the allowance sits.",
            "<b>Benchmark quarterly changes against the peer median, not levels.</b> Level gaps mostly reflect "
            "foreign books, insurance mix and model choices.",
            f"<b>Plan for the trend to continue through the renewal wave:</b> about "
            f"{fx['its_post'] * 4 / 100:.2f} percentage points a year on the impaired share, roughly "
            f"${fx['impaired_per_year_bn']:.1f} billion of newly impaired loans a year on today's book.",
        ], st["bullet"], numbered=True),
        Paragraph("How it was built", st["h"]),
        Paragraph(
            f"PostgreSQL warehouse (raw, core, mart) with {fx['n_checks']} automated data-quality checks; Python "
            "(pandas, statsmodels) for the time-series model, Shapley decomposition and stress test; Power BI "
            "(star schema, DAX) and Tableau (LOD expressions, parameters) dashboards.", st["body"]),
        Spacer(1, 6),
        Paragraph(
            "Data: OSFI financial data for banks, Open Government Licence – Canada. Figures are reported "
            "accounting estimates, not a statement about any bank's safety or investment advice. "
            f"Code, notebook and dashboards: {repo_url}", st["foot"]),
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.45 * inch,
                            title="Mortgage credit risk at Canada's Big Six banks: executive summary",
                            author="Jeelay Pillai", subject="OSFI E3 and M4 analysis")
    doc.build(story)
    return OUT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-url", default="github.com/Jeelay1/osfi-mortgage-credit-risk")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        out = build(args.repo_url, tmp)
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
