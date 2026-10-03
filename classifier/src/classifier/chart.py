import io

import matplotlib

matplotlib.use("Agg")  # headless: render straight to a buffer, no display server

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from classifier.timeline import MINUTES_PER_DAY, TimelineBlock

# Fixed category -> colour assignment. Per the data-viz method, categorical
# hues are assigned in a fixed order and never by rank, so a category keeps its
# colour regardless of where it lands on the timeline. Values are the validated
# light-mode categorical palette; idle is a muted grey so machine-on-but-unused
# time reads as recessive next to real activity (and distinct from the empty
# track, which means machine-off / missed poll).
_COLORS: dict[str, str] = {
    "productive": "#2a78d6",          # blue
    "gaming": "#1baf7a",              # aqua
    "video_entertainment": "#eda100", # yellow
    "social_media": "#d55181",        # pink (distinct from gaming aqua)
    "browsing": "#4a3aa7",      # violet
    "idle": "#898781",                # muted grey
}
_DISPLAY_NAMES: dict[str, str] = {
    "productive": "Productive",
    "gaming": "Gaming",
    "video_entertainment": "Video / streaming",
    "social_media": "Social media",
    "browsing": "Web browsing",
    "idle": "Idle",
}

# Chrome + ink from the light reference surface.
_SURFACE = "#fcfcfb"
_PRIMARY = "#0b0b0b"
_MUTED = "#898781"
_GRID = "#e1e0d9"
# The empty timeline track (idle / machine off) sits just above the surface so
# gaps between activity blocks read as intentional, not as missing chrome.
_TRACK = "#ecebe4"
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


def render_timeline(blocks: list[TimelineBlock], day_label: str) -> bytes:
    """Render the day as a 00:00->24:00 activity timeline and return PNG bytes.

    A single horizontal track spans the whole local day; each block colours the
    span it covers by activity (its fixed category hue), and idle stretches stay
    the empty track colour. A legend lists only the categories that appear.
    """
    present = [category for category in _COLORS if any(b.category == category for b in blocks)]

    with plt.rc_context({"font.family": _FONT, "font.size": 11}):
        fig, ax = plt.subplots(figsize=(9, 2.6), dpi=150)
        fig.patch.set_facecolor(_SURFACE)
        ax.set_facecolor(_SURFACE)

        # Empty-day track first, so any gaps between blocks show through as idle.
        ax.broken_barh([(0, MINUTES_PER_DAY)], (0, 1), facecolors=_TRACK, zorder=2)
        for category in present:
            spans = [
                (block.start_minute, block.duration)
                for block in blocks
                if block.category == category
            ]
            ax.broken_barh(spans, (0, 1), facecolors=_COLORS[category], zorder=3)

        ax.set_xlim(0, MINUTES_PER_DAY)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.set_xticks(range(0, MINUTES_PER_DAY + 1, 3 * 60))
        ax.set_xticklabels([f"{hour:02d}:00" for hour in range(0, 25, 3)])
        ax.set_xticks(range(0, MINUTES_PER_DAY + 1, 60), minor=True)
        ax.grid(axis="x", which="minor", color=_GRID, linewidth=0.6, zorder=4, alpha=0.6)
        ax.grid(axis="x", which="major", color=_GRID, linewidth=1, zorder=4)
        ax.set_axisbelow(False)

        ax.set_title(
            f"Activity through the day · {day_label}",
            color=_PRIMARY,
            fontsize=14,
            fontweight="bold",
            loc="left",
            pad=14,
        )
        ax.tick_params(colors=_MUTED, length=0)
        for spine_name, spine in ax.spines.items():
            spine.set_visible(spine_name == "bottom")
            spine.set_color(_GRID)

        if present:
            handles = [Patch(facecolor=_COLORS[category], label=_DISPLAY_NAMES[category]) for category in present]
            ax.legend(
                handles=handles,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.28),
                ncol=min(len(handles), 4),
                frameon=False,
                fontsize=10,
                handlelength=1.1,
                handleheight=1.1,
                columnspacing=1.6,
                labelcolor=_PRIMARY,
            )

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor=_SURFACE, bbox_inches="tight")
        plt.close(fig)
        return buffer.getvalue()


def render_range_timeline(days: list[tuple[str, list[TimelineBlock]]], title: str) -> bytes:
    """Render several days as stacked 00:00->24:00 tracks and return PNG bytes.

    One row per ``(row_label, blocks)`` pair, top to bottom in the order given,
    using the same per-category hues as the single-day timeline. A day with no
    blocks is a bare track marked "no data" (PC off or offline).
    """
    present = [category for category in _COLORS if any(b.category == category for _, blocks in days for b in blocks)]
    rows = len(days)

    with plt.rc_context({"font.family": _FONT, "font.size": 11}):
        fig, ax = plt.subplots(figsize=(9, 1.2 + 0.42 * rows), dpi=150)
        fig.patch.set_facecolor(_SURFACE)
        ax.set_facecolor(_SURFACE)

        for row, (_, blocks) in enumerate(days):
            y = rows - 1 - row  # first day on top
            ax.broken_barh([(0, MINUTES_PER_DAY)], (y + 0.15, 0.7), facecolors=_TRACK, zorder=2)
            if not blocks:
                ax.text(MINUTES_PER_DAY / 2, y + 0.5, "no data", ha="center", va="center", color=_MUTED, fontsize=9, zorder=5)
            for category in present:
                spans = [(b.start_minute, b.duration) for b in blocks if b.category == category]
                if spans:
                    ax.broken_barh(spans, (y + 0.15, 0.7), facecolors=_COLORS[category], zorder=3)

        ax.set_xlim(0, MINUTES_PER_DAY)
        ax.set_ylim(0, rows)
        ax.set_yticks([rows - 1 - row + 0.5 for row in range(rows)])
        ax.set_yticklabels([label for label, _ in days], color=_PRIMARY)
        ax.set_xticks(range(0, MINUTES_PER_DAY + 1, 3 * 60))
        ax.set_xticklabels([f"{hour:02d}:00" for hour in range(0, 25, 3)])
        ax.set_xticks(range(0, MINUTES_PER_DAY + 1, 60), minor=True)
        ax.grid(axis="x", which="minor", color=_GRID, linewidth=0.6, zorder=4, alpha=0.6)
        ax.grid(axis="x", which="major", color=_GRID, linewidth=1, zorder=4)
        ax.set_axisbelow(False)

        ax.set_title(title, color=_PRIMARY, fontsize=14, fontweight="bold", loc="left", pad=14)
        ax.tick_params(colors=_MUTED, length=0)
        ax.tick_params(axis="y", labelcolor=_PRIMARY)
        for spine_name, spine in ax.spines.items():
            spine.set_visible(spine_name == "bottom")
            spine.set_color(_GRID)

        if present:
            handles = [Patch(facecolor=_COLORS[category], label=_DISPLAY_NAMES[category]) for category in present]
            ax.legend(
                handles=handles,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.6 / rows - 0.06),
                ncol=min(len(handles), 3),
                frameon=False,
                fontsize=10,
                handlelength=1.1,
                handleheight=1.1,
                columnspacing=1.6,
                labelcolor=_PRIMARY,
            )

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor=_SURFACE, bbox_inches="tight")
        plt.close(fig)
        return buffer.getvalue()
