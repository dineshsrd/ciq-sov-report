"""Brand palette + Plotly theme.

Colors per company brand guidelines:
    #210235 deep purple   - dark text / headlines
    #C231FF electric       - primary accent / CTAs / highlights  -> CLIENT
    #5AAFFE sky blue       - secondary accent
    #1F22B2 cobalt         - supporting blue
    #000000 black          - body text
    #FFFFFF white          - background
"""
from __future__ import annotations

DEEP_PURPLE = "#210235"
ELECTRIC = "#C231FF"
SKY = "#5AAFFE"
COBALT = "#1F22B2"
BLACK = "#000000"
WHITE = "#FFFFFF"

# The CLIENT brand is always rendered in the primary electric accent so it
# stands out against competitors.
CLIENT_COLOR = ELECTRIC

# Competitor palette (CLIENT excluded). Ordered for visual separation.
COMPETITOR_COLORS = [
    COBALT,
    SKY,
    DEEP_PURPLE,
    "#7A4FCF",  # muted violet
    "#2E8BEE",  # mid blue
    "#9AA0FF",  # periwinkle
    "#5E3A87",  # plum
    "#46C2D6",  # teal-blue
    "#B0B6C9",  # cool grey
    "#3D2A66",  # indigo
]

# Diverging scale for "client SOV" heat (low -> high). Reds discouraged by the
# palette, so we go grey -> sky -> electric for a positive ramp.
SOV_SCALE = [
    [0.0, "#ECECF2"],
    [0.5, SKY],
    [1.0, ELECTRIC],
]

FONT_FAMILY = "DM Sans, -apple-system, BlinkMacSystemFont, sans-serif"
MONO_FAMILY = "DM Mono, ui-monospace, SFMono-Regular, monospace"


def color_for_brand(brand: str, is_client: bool, competitor_index: int) -> str:
    if is_client:
        return CLIENT_COLOR
    return COMPETITOR_COLORS[competitor_index % len(COMPETITOR_COLORS)]


def plotly_template() -> dict:
    """A lightweight Plotly layout template matching the brand."""
    return {
        "layout": {
            "font": {"family": FONT_FAMILY, "color": "#0A0A0A", "size": 13},
            "paper_bgcolor": WHITE,
            "plot_bgcolor": WHITE,
            "colorway": [ELECTRIC, COBALT, SKY, DEEP_PURPLE, "#7A4FCF", "#2E8BEE"],
            "title": {"font": {"color": DEEP_PURPLE, "size": 18}},
            "xaxis": {"gridcolor": "#EDEDF2", "zerolinecolor": "#EDEDF2"},
            "yaxis": {"gridcolor": "#EDEDF2", "zerolinecolor": "#EDEDF2"},
            "legend": {"bgcolor": "rgba(0,0,0,0)"},
            "margin": {"l": 60, "r": 30, "t": 60, "b": 50},
        }
    }
