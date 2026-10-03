"""Static charts for ANALYSIS.md, rendered in a light and a dark variant.

Mark specs follow the project's data-viz rules: bars at most 24px thick with a 4px rounded
data end and a square baseline end, a 2px surface gap between touching fills, hairline
solid gridlines, text in ink tokens (never in series colours), and palettes checked with
the colour validator (light and dark surfaces).
"""

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # file output only, no GUI backend
import matplotlib.pyplot as plt  # noqa: E402  (backend must be chosen first)
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

DPI = 200
PX = 72 / DPI  # one pixel in points
BAR_PX = 14
GAP_PX = 2
RADIUS_PX = 4
WIDTH_IN = 8.0
FONT = ["Segoe UI", "Arial", "DejaVu Sans"]
SHORT_TITLES = {  # display names short enough for the y-axis
    "DA.PS": "Probability & Statistics",
    "DA.LA": "Linear Algebra",
    "DA.CO": "Calculus & Optimization",
    "DA.PD": "Programming, DS & Algorithms",
    "DA.DB": "Databases & Warehousing",
    "DA.ML": "Machine Learning",
    "DA.AI": "AI",
}


@dataclass(frozen=True)
class Theme:
    """Colour tokens of one mode."""

    name: str
    surface: str
    ink: str
    ink_secondary: str
    ink_muted: str
    grid: str
    baseline: str
    years: tuple[str, str, str]  # ordinal ramp, oldest -> newest (newest most prominent)
    asked: str
    never: str
    dot: str
    interval: str


LIGHT = Theme("light", "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7",
              ("#86b6ef", "#2a78d6", "#104281"), "#2a78d6", "#eb6834", "#2a78d6", "#86b6ef")
DARK = Theme("dark", "#1a1a19", "#ffffff", "#c3c2b7", "#898781", "#2c2c2a", "#383835",
             ("#184f95", "#3987e5", "#9ec5f4"), "#3987e5", "#d95926", "#6da7ec", "#2a78d6")
THEMES = (LIGHT, DARK)


def _figure(theme: Theme, rows: float) -> tuple[plt.Figure, plt.Axes]:
    """Figure with the theme surface, hairline grid and muted axes."""
    plt.rcParams["font.family"] = FONT
    fig, ax = plt.subplots(figsize=(WIDTH_IN, rows), dpi=DPI)
    fig.patch.set_facecolor(theme.surface)
    ax.set_facecolor(theme.surface)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(theme.baseline)
    ax.spines["bottom"].set_linewidth(PX)
    ax.tick_params(colors=theme.ink_muted, labelsize=8, length=0)
    ax.tick_params(axis="y", labelcolor=theme.ink_secondary, labelsize=8.5)
    ax.xaxis.grid(True, color=theme.grid, linewidth=PX, linestyle="-")
    ax.set_axisbelow(True)
    return fig, ax


def _titles(fig: plt.Figure, theme: Theme, title: str, subtitle: str) -> None:
    """Left-aligned title and subtitle in ink tokens."""
    fig.text(0.012, 0.985, title, ha="left", va="top", fontsize=11, fontweight="semibold", color=theme.ink)
    fig.text(0.012, 0.985 - 0.32 / fig.get_figheight(), subtitle, ha="left", va="top", fontsize=8.5,
             color=theme.ink_secondary)


def _units_per_px(ax: plt.Axes) -> tuple[float, float]:
    """Data units per display pixel along x and y (call after limits and layout are final)."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    box = ax.get_window_extent()
    return (x1 - x0) / box.width, abs(y1 - y0) / box.height


def _hbar(ax: plt.Axes, y: float, left: float, width: float, height_px: float, color: str, round_end: bool = True) -> None:
    """Horizontal bar with a square start and (optionally) a 4px rounded data end."""
    if width <= 0:
        return
    ux, uy = _units_per_px(ax)
    height = height_px * uy
    radius = min(RADIUS_PX * ux, width / 2)
    if round_end and width > radius:
        ax.add_patch(FancyBboxPatch(
            (left, y - height / 2), width, height, boxstyle=f"round,pad=0,rounding_size={radius}",
            mutation_aspect=uy / ux, facecolor=color, edgecolor="none", linewidth=0,
        ))
        ax.add_patch(Rectangle((left, y - height / 2), width - radius, height, facecolor=color, edgecolor="none"))
    else:
        ax.add_patch(Rectangle((left, y - height / 2), width, height, facecolor=color, edgecolor="none"))


def section_marks_chart(rows: list[dict], years: list[int], path: Path, theme: Theme) -> None:
    """Grouped horizontal bars: DA marks per syllabus section in each paper."""
    da = sorted((r for r in rows if r["part"] == "DA"), key=lambda r: r["marks_mean"])
    group_px = 3 * BAR_PX + 2 * GAP_PX
    fig, ax = _figure(theme, rows=0.62 * len(da) + 1.3)
    ax.set_ylim(-0.6, len(da) - 0.4)
    ax.set_xlim(0, max(max(r[f"marks_{y}"] for y in years) for r in da) * 1.18)
    ax.set_yticks(range(len(da)), [SHORT_TITLES[r["section_id"]] for r in da])
    fig.subplots_adjust(left=0.25, right=0.97, top=1 - 0.95 / fig.get_figheight(), bottom=0.42 / fig.get_figheight())
    fig.canvas.draw()
    _, uy = _units_per_px(ax)
    for row_index, row in enumerate(da):
        for year_index, year in enumerate(years):
            offset_px = group_px / 2 - BAR_PX / 2 - year_index * (BAR_PX + GAP_PX)  # oldest on top
            centre = row_index + offset_px * uy
            value = row[f"marks_{year}"]
            _hbar(ax, centre, 0, value, BAR_PX, theme.years[year_index])
            if year == years[-1]:
                ax.text(value + 0.25, centre, f"{value:g}", va="center", ha="left", fontsize=7.5, color=theme.ink_secondary)
    ax.set_xlabel("Marks (of 85 DA marks per paper)", color=theme.ink_muted, fontsize=8)
    handles = [Rectangle((0, 0), 1, 1, facecolor=color) for color in theme.years]
    legend = fig.legend(handles, [str(y) for y in years], loc="upper right", ncol=3, frameon=False, fontsize=8,
                        bbox_to_anchor=(0.97, 1 - 0.55 / fig.get_figheight()), handlelength=1.0, handleheight=0.8)
    for text in legend.get_texts():
        text.set_color(theme.ink_secondary)
    _titles(fig, theme, "DA marks by syllabus section, per paper", "Marks attributed to each question's primary syllabus item; latest paper labelled")
    fig.savefig(path, facecolor=theme.surface)
    plt.close(fig)


def coverage_chart(items: list[dict], path: Path, theme: Theme) -> None:
    """Stacked horizontal bars: DA items asked at least once vs never asked, per section."""
    sections: dict[str, dict] = {}
    for item in items:
        if item["part"] != "DA":
            continue
        entry = sections.setdefault(item["section_id"], {"title": SHORT_TITLES[item["section_id"]], "asked": 0, "never": 0})
        entry["never" if item["status"] == "never_asked" else "asked"] += 1
    ordered = sorted(sections.values(), key=lambda s: (s["never"] / (s["asked"] + s["never"]), s["never"]))
    fig, ax = _figure(theme, rows=0.42 * len(ordered) + 1.3)
    ax.set_ylim(-0.6, len(ordered) - 0.4)
    ax.set_xlim(0, max(s["asked"] + s["never"] for s in ordered) * 1.32)
    ax.set_yticks(range(len(ordered)), [s["title"] for s in ordered])
    fig.subplots_adjust(left=0.25, right=0.97, top=1 - 0.95 / fig.get_figheight(), bottom=0.42 / fig.get_figheight())
    fig.canvas.draw()
    ux, _ = _units_per_px(ax)
    for index, section in enumerate(ordered):
        _hbar(ax, index, 0, section["asked"] - (GAP_PX * ux if section["never"] else 0), 18, theme.asked,
              round_end=not section["never"])
        if section["never"]:
            _hbar(ax, index, section["asked"], section["never"], 18, theme.never)
        total = section["asked"] + section["never"]
        ax.text(total + 0.3, index, f"{section['never']} of {total} never asked", va="center", ha="left", fontsize=7.5,
                color=theme.ink_secondary)
    ax.set_xlabel("Syllabus items", color=theme.ink_muted, fontsize=8)
    handles = [Rectangle((0, 0), 1, 1, facecolor=theme.asked), Rectangle((0, 0), 1, 1, facecolor=theme.never)]
    legend = fig.legend(handles, ["asked at least once (primary or secondary)", "never asked in 2024–2026"], loc="upper right",
                        ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.97, 1 - 0.55 / fig.get_figheight()),
                        handlelength=1.0, handleheight=0.8)
    for text in legend.get_texts():
        text.set_color(theme.ink_secondary)
    _titles(fig, theme, "How much of each DA section the papers have covered", "Count of syllabus items per section")
    fig.savefig(path, facecolor=theme.surface)
    plt.close(fig)


def forecast_chart(items: list[dict], path: Path, theme: Theme, top: int = 20) -> None:
    """Dot + interval: expected marks next paper for the top DA items."""
    da = [i for i in items if i["part"] == "DA"]
    chosen = sorted(da, key=lambda i: i["forecast_expected_marks"], reverse=True)[:top][::-1]
    fig, ax = _figure(theme, rows=0.27 * len(chosen) + 1.3)
    labels = [f"{i['label'][:40]}  ·  {i['section_id'].split('.')[1]}" for i in chosen]
    ax.set_ylim(-0.8, len(chosen) - 0.2)
    ax.set_yticks(range(len(chosen)), labels)
    scale = [i["forecast_expected_marks"] / i["forecast_expected_questions"] for i in chosen]
    high = max(i["forecast_rate_high"] * s for i, s in zip(chosen, scale))
    ax.set_xlim(0, high * 1.08)
    fig.subplots_adjust(left=0.40, right=0.97, top=1 - 0.95 / fig.get_figheight(), bottom=0.42 / fig.get_figheight())
    for index, (item, marks_each) in enumerate(zip(chosen, scale)):
        ax.plot([item["forecast_rate_low"] * marks_each, item["forecast_rate_high"] * marks_each], [index, index],
                color=theme.interval, linewidth=2 * PX * 2, solid_capstyle="round")
        ax.scatter([item["forecast_expected_marks"]], [index], s=(10 * PX) ** 2 * 4, color=theme.dot,
                   edgecolors=theme.surface, linewidths=2 * PX, zorder=3)
    ax.set_xlabel("Expected marks in the next paper (dot) with 80% credible interval (line)", color=theme.ink_muted, fontsize=8)
    _titles(fig, theme, f"Forecast: top {top} DA syllabus items by expected marks",
            "Empirical-Bayes Gamma–Poisson on 2024–2026 primary tags; items differ in size, so plan by section")
    fig.savefig(path, facecolor=theme.surface)
    plt.close(fig)


def render_all(document: dict, out_dir: Path) -> list[str]:
    """Render every chart in both themes; return the base names written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    years = document["years"]
    names = []
    for theme in THEMES:
        section_marks_chart(document["sections"]["primary"], years, out_dir / f"section_marks_{theme.name}.png", theme)
        coverage_chart(document["items"], out_dir / f"coverage_{theme.name}.png", theme)
        forecast_chart(document["items"], out_dir / f"forecast_{theme.name}.png", theme)
    names += ["section_marks", "coverage", "forecast"]
    return names
