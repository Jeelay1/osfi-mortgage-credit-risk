"""Chart helpers with one consistent, accessible style.

Design rules (from the project's data-visualisation checklist):
  * one y-axis per chart, hairline solid gridlines, no chart borders
  * 2px lines, >= 8px end markers with a surface-coloured ring
  * bars at most ~24px thick, rounded at the data end, square at the baseline
  * every bank keeps the same colour in every chart (colour follows the entity)
  * text is always ink-coloured; colour lives on the marks
  * a legend whenever there are two or more series, plus selective direct labels
The six bank colours are the validated reference palette (adjacent-pair CVD
separation >= 9.1 dE); the three-colour factor set passes the all-pairs test.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "reports" / "figures"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
CONTEXT = "#c9c8c1"          # de-emphasised peer lines

BANK_ORDER = ["RBC", "TD", "BNS", "BMO", "CIBC", "NBC"]
BANK_COLORS = dict(zip(BANK_ORDER, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]))
BANK_COLORS["Big Six"] = INK_2
ACCENT = "#2a78d6"
SECOND = "#eb6834"
THIRD = "#1baf7a"
FOURTH = "#eda100"
INCREASE = "#8e3b46"         # waterfall steps: one colour for increases (same as the Power BI report)
DECREASE = "#3a7d8c"

FIRST_HIKE = pd.Timestamp("2022-03-02")
FIRST_CUT = pd.Timestamp("2024-06-05")


def use_style() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.titlepad": 10,
        "axes.edgecolor": BASELINE,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 2,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "figure.dpi": 110,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    })


def title_block(fig, title: str, subtitle: str | None = None, source: str | None = None) -> None:
    """Headline-style title and subtitle above the plot, source line below."""
    fig.text(0.0, 1.0, title, ha="left", va="bottom", fontsize=13, fontweight="semibold",
             color=INK, transform=fig.transFigure)
    if subtitle:
        fig.text(0.0, 0.985, subtitle, ha="left", va="top", fontsize=10, color=INK_2,
                 transform=fig.transFigure)
    if source:
        fig.text(0.0, -0.02, source, ha="left", va="top", fontsize=8, color=MUTED,
                 transform=fig.transFigure)


def mark_rate_cycle(ax, label: bool = True, y_frac: float = 0.97) -> None:
    """Hairline at the first Bank of Canada hike."""
    ax.axvline(FIRST_HIKE, color=BASELINE, linewidth=1, zorder=0)
    if label:
        ax.text(FIRST_HIKE, y_frac, " First rate hike\n Mar 2022", transform=ax.get_xaxis_transform(),
                ha="left", va="top", fontsize=8, color=MUTED)


def end_dot(ax, x, y, color) -> None:
    ax.scatter([x], [y], s=46, color=color, edgecolor=SURFACE, linewidth=2, zorder=5)


def pct_axis(ax, decimals: int = 1, axis: str = "y") -> None:
    fmt = mticker.PercentFormatter(xmax=1, decimals=decimals)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def year_axis(ax) -> None:
    ax.xaxis.set_major_locator(mpl.dates.YearLocator())
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%Y"))


def rounded_bars(ax, positions, values, color, thickness, horizontal=True, radius_px=4, zorder=3):
    """Bars with a rounded data end and a square baseline end.

    Must be called after the axis limits are final, because the corner radius is
    converted from pixels to data units on each axis.
    """
    fig = ax.figure
    fig.canvas.draw()
    bbox = ax.get_window_extent()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    px_x = (x1 - x0) / bbox.width     # data units per pixel
    px_y = (y1 - y0) / bbox.height
    colors = color if isinstance(color, (list, tuple, np.ndarray)) else [color] * len(values)
    for pos, val, col in zip(positions, values, colors):
        if val == 0 or pd.isna(val):
            continue
        if horizontal:
            x, y, w, h = min(0, val), pos - thickness / 2, abs(val), thickness
            r_len = radius_px * px_x
            aspect = px_y / px_x
        else:
            x, y, w, h = pos - thickness / 2, min(0, val), thickness, abs(val)
            r_len = radius_px * px_y
            aspect = px_y / px_x
        r_len = min(r_len, (w if horizontal else h) / 2)
        if horizontal:
            patch = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r_len}",
                                   mutation_aspect=aspect, linewidth=0, facecolor=col, zorder=zorder)
            ax.add_patch(patch)
            # square off the baseline end
            sq_x = x if val > 0 else x + w - r_len
            ax.add_patch(Rectangle((sq_x, y), r_len, h, linewidth=0, facecolor=col, zorder=zorder))
        else:
            patch = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r_len / aspect}",
                                   mutation_aspect=aspect, linewidth=0, facecolor=col, zorder=zorder)
            ax.add_patch(patch)
            sq_y = y if val > 0 else y + h - r_len
            ax.add_patch(Rectangle((x, sq_y), w, r_len, linewidth=0, facecolor=col, zorder=zorder))


def save(fig, name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / f"{name}.png"
    fig.savefig(path)
    return path


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
def bank_small_multiples(q: pd.DataFrame, column: str, title: str, subtitle: str,
                         value_fmt, ylim=None, source: str | None = None, scale: float = 1.0):
    """One panel per bank: that bank in its colour, the other five in grey."""
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.2), sharex=True, sharey=True)
    data = q[q["short_name"].isin(BANK_ORDER)].copy()
    data["v"] = data[column] * scale
    for ax, bank in zip(axes.flat, BANK_ORDER):
        for other in BANK_ORDER:
            if other == bank:
                continue
            d = data[data["short_name"] == other]
            ax.plot(d["quarter_end_date"], d["v"], color=CONTEXT, linewidth=1, zorder=1)
        d = data[data["short_name"] == bank]
        ax.plot(d["quarter_end_date"], d["v"], color=BANK_COLORS[bank], linewidth=2, zorder=3)
        last = d.iloc[-1]
        end_dot(ax, last["quarter_end_date"], last["v"], BANK_COLORS[bank])
        ax.annotate(value_fmt(last["v"]), (last["quarter_end_date"], last["v"]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK)
        ax.set_title(bank, fontsize=10, pad=4)
        mark_rate_cycle(ax, label=(bank == BANK_ORDER[0]))
        year_axis(ax)
        ax.tick_params(axis="x", labelsize=8)
        for lab in ax.get_xticklabels():
            lab.set_rotation(0)
        if ylim:
            ax.set_ylim(*ylim)
        ax.set_xlim(pd.Timestamp("2017-11-01"), pd.Timestamp("2026-12-31"))
    title_block(fig, title, subtitle, source)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def headline_its(fitted: pd.DataFrame, summary_row: pd.Series, source: str, compact: bool = False):
    """Big Six impaired share with the segmented fit and the extended pre-hike trend.

    compact=True draws a small, title-free version for the one-page executive summary.
    """
    fig, ax = plt.subplots(figsize=(5.0, 2.8) if compact else (10, 5))
    d = fitted.sort_values("quarter_end_date")
    pre = d[d["post"] == 0]
    post = d[d["post"] == 1]
    ax.plot(d["quarter_end_date"], d["pre_trend_extended_bps"].where(d["post"] == 1), color=CONTEXT,
            linewidth=2, zorder=1)
    ax.plot(pre["quarter_end_date"], pre["fitted_bps"], color=MUTED, linewidth=1.2, zorder=2)
    ax.plot(post["quarter_end_date"], post["fitted_bps"], color=MUTED, linewidth=1.2, zorder=2)
    ax.plot(d["quarter_end_date"], d["stage3_bps"], color=ACCENT, linewidth=2, zorder=3)
    ax.scatter(d["quarter_end_date"], d["stage3_bps"], s=22, color=ACCENT, edgecolor=SURFACE,
               linewidth=1.5, zorder=4)
    last = d.iloc[-1]
    end_dot(ax, last["quarter_end_date"], last["stage3_bps"], ACCENT)
    ax.annotate(f"{last['stage3_bps'] / 100:.2f}%", (last["quarter_end_date"], last["stage3_bps"]),
                xytext=(8, 0), textcoords="offset points", va="center", fontsize=10, color=INK,
                fontweight="semibold")
    trough = d.loc[d["stage3_bps"].idxmin()]
    ax.annotate(f"Low: {trough['stage3_bps'] / 100:.2f}%\n{trough['quarter_end_date']:%b %Y}",
                (trough["quarter_end_date"], trough["stage3_bps"]), xytext=(0, -30 if not compact else -14),
                textcoords="offset points", ha="center", va="top", fontsize=9, color=INK_2)
    ext_last = d.iloc[-1]["pre_trend_extended_bps"]
    ax.annotate("Pre-hike trend" if compact else "Pre-hike trend, extended",
                (d.iloc[-1]["quarter_end_date"], ext_last), xytext=(8 if not compact else 4, 0),
                textcoords="offset points", va="center", fontsize=9, color=MUTED)
    if not compact:
        ax.annotate(f"Fitted trend: {summary_row['pre_trend_bps_per_qtr']:+.1f} bp a quarter before the first hike,\n"
                    f"{summary_row['post_trend_bps_per_qtr']:+.1f} bp a quarter after",
                    xy=(0.02, 0.06), xycoords="axes fraction", fontsize=9, color=INK_2)
    mark_rate_cycle(ax)
    year_axis(ax)
    if compact:
        ax.set_xticks([pd.Timestamp(f"{y}-01-01") for y in range(2020, 2027, 2)])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 100:.1f}%" if compact else f"{v / 100:.2f}%"))
    ax.set_ylim(0, max(d["stage3_bps"].max(), 60) * 1.15)
    ax.set_xlim(pd.Timestamp("2017-11-01"), pd.Timestamp("2028-06-30" if compact else "2027-06-30"))
    if compact:
        fig.tight_layout(pad=0.4)
        return fig
    title_block(fig, "Impaired mortgages at the Big Six have more than doubled since mid-2022",
                "Stage 3 (credit-impaired) share of residential mortgage exposure, Big Six combined, by quarter",
                source)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return fig


def decomposition_waterfall(row: pd.Series, source: str, compact: bool = False):
    """Big Six change in allowances split into its drivers.

    compact=True draws a small, title-free version for the one-page executive summary.
    """
    end = f"{pd.Timestamp(row['end_quarter']):%b %Y}"
    names = ([f"Start\nJan 2022", "Organic\ngrowth", "Acquired\nbooks", "Stage\nmigration", "Coverage\nrates",
              f"End\n{end}"] if compact else
             ["Allowance\nJan 2022", "Book growth\n(organic)", "Book growth\n(acquired)", "More loans in\nStage 2 and 3",
              "More set aside\nper dollar", f"Allowance\n{end}"])
    values = [row["ecl_start_cad_mn"], row["volume_organic_cad_mn"], row["volume_acquired_cad_mn"],
              row["stage_mix_cad_mn"], row["coverage_rate_cad_mn"], row["ecl_end_cad_mn"]]
    kinds = ["total", "part", "part", "part", "part", "total"]
    steps = list(zip(names, values, kinds))
    fig, ax = plt.subplots(figsize=(5.0, 2.8) if compact else (10, 5))
    running = 0.0
    bottoms, heights, cols = [], [], []
    for label, val, kind in steps:
        if kind == "total":
            bottoms.append(0)
            heights.append(val)
            cols.append(INK_2)
            running = val
        else:
            bottoms.append(running if val >= 0 else running + val)
            heights.append(abs(val))
            cols.append(INCREASE if val >= 0 else DECREASE)
            running += val
    x = np.arange(len(steps))
    ax.bar(x, heights, bottom=bottoms, width=0.36 if compact else 0.24, color=cols, linewidth=0, zorder=3)
    total_change = row["ecl_change_cad_mn"]
    for i, (label, val, kind) in enumerate(steps):
        top = bottoms[i] + heights[i]
        sign = "+" if val >= 0 else "\u2212"
        text = f"${val / 1000:,.2f}bn" if kind == "total" else f"{sign}${abs(val):,.0f}M\n({val / total_change:.0%})"
        biggest = kind == "part" and val == max(v for _, v, k in steps if k == "part")
        ax.text(i, top + 60, text, ha="center", va="bottom", fontsize=9, color=INK,
                fontweight="bold" if biggest else "normal")
    ax.set_xticks(x, [s[0] for s in steps], fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v / 1000:.0f}bn" if compact else f"${v / 1000:.1f}bn"))
    ax.set_ylim(0, row["ecl_end_cad_mn"] * (1.28 if compact else 1.18))
    if compact:
        fig.tight_layout(pad=0.4)
        return fig
    title_block(fig, "Most of the rise in mortgage allowances came from loans moving into riskier stages",
                f"Big Six residential mortgage allowance (ECL), Jan 2022 to {pd.Timestamp(row['end_quarter']):%b %Y}, "
                "split into drivers (Shapley decomposition)", source)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return fig


def book_and_insured_share(monthly: pd.DataFrame, source: str):
    """Two separate panels (never a dual axis): book size, and the insured share."""
    agg = monthly.groupby("month_end_date")[["insured_cad_mn", "uninsured_cad_mn", "resi_total_cad_mn"]].sum()
    agg["insured_share"] = agg["insured_cad_mn"] / (agg["insured_cad_mn"] + agg["uninsured_cad_mn"])
    agg = agg[agg.index >= "2018-01-31"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.plot(agg.index, agg["resi_total_cad_mn"] / 1e6, color=ACCENT)
    end_dot(ax, agg.index[-1], agg["resi_total_cad_mn"].iloc[-1] / 1e6, ACCENT)
    ax.annotate(f"${agg['resi_total_cad_mn'].iloc[-1] / 1e6:.2f}T", (agg.index[-1], agg["resi_total_cad_mn"].iloc[-1] / 1e6),
                xytext=(6, 0), textcoords="offset points", va="center", fontsize=9)
    ax.set_title("Residential mortgages, $ trillions (net of allowances)", fontsize=10)
    ax.set_ylim(0, agg["resi_total_cad_mn"].max() / 1e6 * 1.15)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.5))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.1f}T"))
    ax = axes[1]
    ax.plot(agg.index, agg["insured_share"], color=SECOND)
    end_dot(ax, agg.index[-1], agg["insured_share"].iloc[-1], SECOND)
    ax.annotate(f"{agg['insured_share'].iloc[-1]:.0%}", (agg.index[-1], agg["insured_share"].iloc[-1]),
                xytext=(6, 0), textcoords="offset points", va="center", fontsize=9)
    ax.annotate(f"{agg['insured_share'].iloc[0]:.0%}", (agg.index[0], agg["insured_share"].iloc[0]),
                xytext=(0, 8), textcoords="offset points", ha="left", fontsize=9)
    ax.set_title("Share of the book with default insurance", fontsize=10)
    ax.set_ylim(0, 0.55)
    pct_axis(ax, 0)
    for a in axes:
        mark_rate_cycle(a, label=False)
        year_axis(a)
        a.set_xlim(agg.index.min() - pd.Timedelta(days=60), agg.index.max() + pd.Timedelta(days=300))
    title_block(fig, "The book grew by more than half while the insured share halved",
                "Big Six combined, M4 monthly balance sheet", source)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def insured_vs_uninsured(q: pd.DataFrame, source: str, title: str):
    d = q[(q["short_name"] == "Big Six")].dropna(subset=["coverage_uninsured_bps"])
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for col, color, label in [("coverage_uninsured_bps", ACCENT, "Uninsured mortgages"),
                              ("coverage_insured_bps", SECOND, "Insured mortgages")]:
        ax.plot(d["quarter_end_date"], d[col], color=color, linewidth=2, label=label)
        last = d.iloc[-1]
        end_dot(ax, last["quarter_end_date"], last[col], color)
        ax.annotate(f"{label}: {last[col]:.1f} bp", (last["quarter_end_date"], last[col]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK)
    ax.set_ylabel("Allowance per $ of exposure (basis points)")
    ax.set_ylim(0, d["coverage_uninsured_bps"].max() * 1.25)
    ax.set_xlim(d["quarter_end_date"].min() - pd.Timedelta(days=30), pd.Timestamp("2027-09-30"))
    ax.legend(loc="upper left", ncols=2)
    year_axis(ax)
    title_block(fig, title,
                "Big Six residential mortgage coverage (allowance / gross exposure), basis points", source)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return fig


def latest_stage3_bars(q: pd.DataFrame, source: str):
    latest = q["quarter_end_date"].max()
    base = pd.Timestamp("2022-07-31")
    d = q[(q["quarter_end_date"] == latest) & (q["short_name"].isin(BANK_ORDER))].set_index("short_name")
    b = q[(q["quarter_end_date"] == base) & (q["short_name"].isin(BANK_ORDER))].set_index("short_name")
    order = d["stage3_share"].sort_values().index.tolist()
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = np.arange(len(order))
    ax.set_xlim(0, d["stage3_share"].max() * 1.35)
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    rounded_bars(ax, y, d.loc[order, "stage3_share"].values, [BANK_COLORS[b_] for b_ in order],
                 thickness=0.42, horizontal=True)
    ax.scatter(b.loc[order, "stage3_share"].values, y, s=36, color=SURFACE, edgecolor=INK_2, linewidth=1.5,
               zorder=4, label=f"{base:%b %Y} (Big Six low point)")
    for yi, bank in zip(y, order):
        v = d.loc[bank, "stage3_share"]
        ax.text(v + d["stage3_share"].max() * 0.02, yi, f"{v:.2%}  (x{v / b.loc[bank, 'stage3_share']:.1f})",
                va="center", fontsize=9, color=INK)
    ax.set_yticks(y, order)
    pct_axis(ax, 1, axis="x")
    ax.legend(loc="lower right")
    title_block(fig, "Every Big Six bank's impaired-mortgage share is up since mid-2022",
                f"Stage 3 share of residential mortgages, quarter ending {latest:%b %Y} "
                f"(bar) vs {base:%b %Y} (circle); multiple in brackets", source)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def acquisition_growth(monthly: pd.DataFrame, source: str):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    for ax, bank, event in zip(axes, ["RBC", "NBC"], ["HSBC Canada, Apr 2024", "CWB, Feb 2025"]):
        d = monthly[(monthly["short_name"] == bank) & (monthly["month_end_date"] >= "2022-01-31")]
        ax.plot(d["month_end_date"], d["yoy_growth"], color=CONTEXT, linewidth=2, label="As reported")
        ax.plot(d["month_end_date"], d["organic_yoy_growth"], color=BANK_COLORS[bank], linewidth=2,
                label="Organic (acquired book removed)")
        acq = d[d["is_acquisition_month"]].iloc[0]
        ax.annotate(f"Acquires {event}", (acq["month_end_date"], acq["yoy_growth"]), xytext=(8, 6),
                    textcoords="offset points", fontsize=8.5, color=INK_2)
        ax.set_title(bank, fontsize=10)
        ax.yaxis.set_major_locator(mticker.MultipleLocator(0.05))
        pct_axis(ax, 0)
        ax.set_ylim(0, 0.25)
        year_axis(ax)
        ax.legend(loc="lower left", fontsize=8.5)
    title_block(fig, "Acquisitions inflate reported mortgage growth for a year",
                "Year-over-year growth in residential mortgages (M4, monthly)", source)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def reconciliation_gaps(recon: pd.DataFrame, source: str):
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for bank in BANK_ORDER:
        d = recon[recon["short_name"] == bank]
        hi = bank in ("TD", "NBC")
        ax.plot(d["quarter_end_date"], d["gap_pct"], color=BANK_COLORS[bank] if hi else CONTEXT,
                linewidth=2 if hi else 1.2, zorder=3 if hi else 1)
        last = d.iloc[-1]
        if hi:
            end_dot(ax, last["quarter_end_date"], last["gap_pct"], BANK_COLORS[bank])
            note = {"TD": "TD: open item", "NBC": "NBC: reverse mortgages"}[bank]
            ax.annotate(f"{note} ({last['gap_pct']:+.1%})", (last["quarter_end_date"], last["gap_pct"]),
                        xytext=(8, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
    ax.text(pd.Timestamp("2018-09-01"), -0.012, "RBC, BNS, BMO, CIBC (grey): within 0.3% in every quarter",
            fontsize=9, color=INK_2)
    ax.axhline(0, color=BASELINE, linewidth=1)
    pct_axis(ax, 0)
    year_axis(ax)
    ax.set_xlim(recon["quarter_end_date"].min() - pd.Timedelta(days=40), pd.Timestamp("2027-10-31"))
    title_block(fig, "Two returns, one balance: five of the six banks reconcile",
                "(E3 gross exposure \u2212 E3 allowance \u2212 M4 balance) \u00f7 E3 net balance, residential mortgages, by quarter", source)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def double_count_chart(dc: pd.DataFrame, source: str):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    d = dc.sort_values("month_end_date")
    ax.plot(d["month_end_date"], d["overstatement_cad_mn"] / 1000, color=ACCENT, linewidth=2,
            label="Sum of banks minus OSFI total")
    ax.plot(d["month_end_date"], d["unexplained_cad_mn"] / 1000, color=SECOND, linewidth=2,
            label="Left after removing identified subsidiaries")
    spike = d.loc[d["overstatement_cad_mn"].idxmax()]
    ax.annotate("Feb 2025: CWB files its own return\nafter National Bank buys it", (spike["month_end_date"],
                spike["overstatement_cad_mn"] / 1000), xytext=(-12, -4), textcoords="offset points", ha="right",
                va="top", fontsize=8.5, color=INK_2)
    ax.set_ylabel("$ billions of total assets")
    ax.set_ylim(-5, d["overstatement_cad_mn"].max() / 1000 * 1.2)
    ax.legend(loc="upper left")
    year_axis(ax)
    title_block(fig, "Adding up every bank counts bank-owned subsidiaries twice",
                "Total assets of domestic banks: sum of individual returns vs OSFI's own total", source)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig
