"""Design system for the report, its PNG figures and the demo (every chart and the HTML import this).

One accent for O1, muted neutrals for the baselines (each also has its own marker shape and a direct label, so
colour is never the only cue), the oracle as a dashed gold outline. Pass/fail colours are reserved for state and
always ship with an icon and a word. Accent, gold and the status colours were checked with the dataviz
palette validator (light surface): CVD and normal-vision separation pass, all at least 3:1 on the surface.
"""

from __future__ import annotations

import plotly.graph_objects as go

SURFACE = "#fcfcfb"  # chart surface (also the solid PNG background)
PAGE = "#f6f5f1"  # page plane behind cards
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

ACCENT = "#2a78d6"  # O1, everywhere
ACCENT_SOFT = "#cde2fb"
GOLD = "#b07800"  # the oracle: dashed outline only
GOOD = "#0c7a0c"  # pass (with a check mark and the word)
BAD = "#d03b3b"  # fail / breach (with a cross and the word)
WARN = "#b25a1e"  # caution (with "!" and the word)

POLICY_ORDER = ("B1", "B2", "B3", "B4", "B5", "O1", "O1_live", "Oracle")


class PolicyStyle:
    def __init__(self, label: str, color: str, symbol: str, dash: str = "solid", fill: bool = True):
        self.label, self.color, self.symbol, self.dash, self.fill = label, color, symbol, dash, fill


POLICY: dict[str, PolicyStyle] = {
    "B1": PolicyStyle("B1 always-best", "#3f3e3b", "square"),
    "B2": PolicyStyle("B2 always-cheapest", "#8a8882", "triangle-up"),
    "B3": PolicyStyle("B3 static per task", "#6b6a65", "diamond"),
    "B4": PolicyStyle("B4 cheapest meeting floors", "#a5a39b", "cross"),
    "B5": PolicyStyle("B5 naive cascade", "#b9b7ae", "x"),
    "O1": PolicyStyle("O1 (simulated)", ACCENT, "circle"),
    "O1_live": PolicyStyle("O1 (live)", ACCENT, "circle"),
    "Oracle": PolicyStyle("Oracle", GOLD, "circle-open", dash="dash", fill=False),
    "failsafe": PolicyStyle("Fail-safe (analysis)", "#1c5cab", "star"),
    "recalibrated": PolicyStyle("Re-picked on audit", "#8a8882", "hexagon-open"),
}

SPLIT_LABEL = {"dev": "dev", "shifted": "shifted", "heldout": "held-out"}

# One display face + one text face: system stacks (no download, Arabic-capable on every desktop OS).
DISPLAY_FONT = (
    '"Segoe UI Variable Display", "Segoe UI", system-ui, -apple-system, "Noto Sans Arabic", sans-serif'
)
TEXT_FONT = '"Segoe UI", system-ui, -apple-system, "Noto Sans", "Noto Sans Arabic", Tahoma, sans-serif'

# label strings fixed by SPEC §7.5 (verbatim)
HEADLINE = "Cost without caching (headline)"
CACHED = "Cost with caching (actual)"
SIMULATED, LIVE = "simulated", "live"


class Size:
    """Pixel sizes for the two targets. PNG: 1920x1080 layout exported at 2x, min 24 px text."""

    def __init__(self, png: bool):
        self.png = png
        self.base = 26 if png else 13
        self.small = 24 if png else 11.5
        self.title = 40 if png else 0  # HTML titles live in the page, not in the chart
        self.label = 26 if png else 12.5
        self.marker = 22 if png else 11
        self.line = 4 if png else 2
        self.width, self.height = (1920, 1080) if png else (None, None)


def wrap(text: str, width: int) -> str:
    """Greedy word wrap with <br> (Plotly text); '$' is escaped so Plotly never reads it as LaTeX."""
    lines, cur = [], ""
    for word in text.split(" "):
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    lines.append(cur)
    return "<br>".join(lines).replace("$", "&#36;")


def layout(
    fig: go.Figure, size: Size, *, title: str = "", caption: str = "", height: int | None = None
) -> None:
    """House style: recessive hairline grid, no legend box (direct labels), solid surface."""
    title = wrap(title, 78) if size.png else title
    caption = wrap(caption, 140) if size.png else caption
    top = (120 + 52 * title.count("<br>") + 60) if (size.png and title) else 24
    bottom = (150 + 32 * caption.count("<br>")) if size.png else 48
    fig.update_layout(
        font={"family": TEXT_FONT, "size": size.base, "color": INK_2},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        showlegend=False,
        margin={"l": 40 if not size.png else 80, "r": 40 if not size.png else 80, "t": top, "b": bottom},
        hoverlabel={"font": {"family": TEXT_FONT, "size": 13}, "bgcolor": "white", "bordercolor": GRID},
        width=size.width,
        height=size.height or height,
    )
    fig.update_xaxes(
        gridcolor=GRID,
        linecolor=AXIS,
        zeroline=False,
        ticks="",
        tickfont={"color": MUTED, "size": size.small},
    )
    fig.update_yaxes(
        gridcolor=GRID,
        linecolor=AXIS,
        zeroline=False,
        ticks="",
        tickfont={"color": MUTED, "size": size.small},
    )
    if size.png and title:
        fig.update_layout(
            title={
                "text": title,
                "x": 0.0,
                "xref": "paper",
                "y": 1 - 36 / 1080,
                "yanchor": "top",
                "font": {"family": DISPLAY_FONT, "size": size.title, "color": INK},
            }
        )
    if size.png and caption:
        fig.add_annotation(
            text=caption,
            xref="paper",
            yref="paper",
            x=0,
            y=0,
            yshift=-bottom + 12,
            xanchor="left",
            yanchor="bottom",
            showarrow=False,
            font={"size": size.small, "color": MUTED},
            align="left",
        )


def css_vars() -> str:
    """The same tokens for the HTML page."""
    pairs = {
        "surface": SURFACE,
        "page": PAGE,
        "ink": INK,
        "ink-2": INK_2,
        "muted": MUTED,
        "grid": GRID,
        "axis": AXIS,
        "accent": ACCENT,
        "accent-soft": ACCENT_SOFT,
        "gold": GOLD,
        "good": GOOD,
        "bad": BAD,
        "warn": WARN,
        **{f"p-{k.lower()}": v.color for k, v in POLICY.items()},
    }
    body = "".join(f"--{k}:{v};" for k, v in pairs.items())
    return f":root{{{body}--display:{DISPLAY_FONT};--text:{TEXT_FONT};}}"
