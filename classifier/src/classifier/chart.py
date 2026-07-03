import io

import matplotlib

matplotlib.use("Agg")  # headless: render straight to a buffer, no display server

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from classifier.aggregate import CategorySummary

# Fixed category -> colour assignment. Per the data-viz method, categorical
# hues are assigned in a fixed order and never by rank, so a category keeps its
# colour regardless of where it lands in the sorted bars. Values are the
# validated light-mode categorical palette; idle_locked is a muted grey so
# "no activity" reads as recessive next to real activity.
_COLORS: dict[str, str] = {
    "schoolwork": "#2a78d6",          # blue
    "gaming": "#1baf7a",              # aqua
    "video_entertainment": "#eda100", # yellow
    "social_media": "#008300",        # green
    "browsing_other": "#4a3aa7",      # violet
    "idle_locked": "#898781",         # muted grey
}
_DISPLAY_NAMES: dict[str, str] = {
    "schoolwork": "Schoolwork",
    "gaming": "Gaming",
    "video_entertainment": "Video / streaming",
    "social_media": "Social media",
    "browsing_other": "Other browsing",
    "idle_locked": "Idle / locked",
}

# Chrome + ink from the light reference surface.
_SURFACE = "#fcfcfb"
_PRIMARY = "#0b0b0b"
_MUTED = "#898781"
_GRID = "#e1e0d9"
# DejaVu Sans ships with matplotlib, so it always resolves on a headless server
# (a UI face like system-ui isn't installed there and only prints font warnings).
_FONT = ["DejaVu Sans", "sans-serif"]


def format_duration(minutes: float) -> str:
    """Minutes as a compact ``2h 30m`` / ``45m`` / ``3h`` string."""
    total = int(round(minutes))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def render_chart(summaries: list[CategorySummary], day_label: str) -> bytes:
    """Render a horizontal time-per-category bar chart and return PNG bytes.

    Bars are sorted by magnitude (largest at top) but keep their fixed category
    colour. Each bar carries a direct duration + share label — the data-viz
    relief rule, since a few light-mode hues sit below 3:1 on the surface.
    """
    ordered = sorted(summaries, key=lambda summary: summary.minutes, reverse=True)
    names = [_DISPLAY_NAMES[summary.category] for summary in ordered]
    minutes = [summary.minutes for summary in ordered]
    colors = [_COLORS[summary.category] for summary in ordered]
    total = sum(minutes) or 1
    headroom = (max(minutes) or 1) * 1.18

    with plt.rc_context({"font.family": _FONT, "font.size": 11}):
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
        fig.patch.set_facecolor(_SURFACE)
        ax.set_facecolor(_SURFACE)

        positions = range(len(ordered))
        bars = ax.barh(list(positions), minutes, height=0.62, color=colors, zorder=3)
        ax.invert_yaxis()  # largest bar at the top
        ax.set_yticks(list(positions))
        ax.set_yticklabels(names, color=_PRIMARY)
        ax.set_xlim(0, headroom)

        for bar, mins in zip(bars, minutes):
            if mins <= 0:
                continue
            ax.text(
                bar.get_width() + headroom * 0.012,
                bar.get_y() + bar.get_height() / 2,
                f"{format_duration(mins)}  ·  {mins / total * 100:.0f}%",
                va="center",
                ha="left",
                color=_PRIMARY,
                fontsize=10,
            )

        ax.set_title(
            f"Screen time by activity · {day_label}",
            color=_PRIMARY,
            fontsize=14,
            fontweight="bold",
            loc="left",
            pad=14,
        )
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: format_duration(value)))
        ax.tick_params(colors=_MUTED, length=0)
        ax.grid(axis="x", color=_GRID, linewidth=1, zorder=0)
        ax.set_axisbelow(True)
        for spine_name, spine in ax.spines.items():
            spine.set_visible(spine_name == "bottom")
            spine.set_color(_GRID)

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor=_SURFACE, bbox_inches="tight")
        plt.close(fig)
        return buffer.getvalue()
