"""Plotly chart builders. Every figure is brand-themed and CLIENT-highlighted."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from . import branding as B
from .metrics import CUTOFFS, METRIC_TYPES


def _apply_theme(fig: go.Figure, title: str, height: int = 420) -> go.Figure:
    fig.update_layout(B.plotly_template()["layout"])
    fig.update_layout(title=title, height=height,
                      title_font_color=B.DEEP_PURPLE)
    return fig


def _brand_colors(brands: list[str], is_client_flags: list[bool]) -> list[str]:
    colors, ci = [], 0
    for b, is_client in zip(brands, is_client_flags):
        if is_client:
            colors.append(B.CLIENT_COLOR)
        else:
            colors.append(B.COMPETITOR_COLORS[ci % len(B.COMPETITOR_COLORS)])
            ci += 1
    return colors


def leaderboard_bar(lb: pd.DataFrame, title: str = "Brand SOV leaderboard",
                    top: int = 12) -> go.Figure:
    d = lb.head(top).iloc[::-1]  # reverse so #1 is on top
    colors = _brand_colors(d["brand"].tolist(), d["is_client"].tolist())
    fig = go.Figure(go.Bar(
        x=d["sov_pct"], y=d["brand"], orientation="h", marker_color=colors,
        text=[f"{v:.1f}%" for v in d["sov_pct"]], textposition="outside",
        hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
    ))
    fig.update_layout(xaxis_title="SOV %", yaxis_title=None)
    return _apply_theme(fig, title, height=max(360, 34 * len(d) + 120))


def top_keywords_chart(kw: pd.DataFrame,
                       title: str = "Top keywords — your SOV") -> go.Figure:
    d = kw.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d["client_sov"], y=d["search_term"], orientation="h",
        marker_color=B.ELECTRIC,
        text=[f"{v:.1f}%" for v in d["client_sov"]], textposition="outside",
        customdata=d[["crawls", "intensity"]].values,
        hovertemplate=("%{y}<br>Your SOV: %{x:.2f}%"
                       "<br>Crawls: %{customdata[0]:.0f}"
                       "<br>Category weight: %{customdata[1]:.3f}<extra></extra>"),
    ))
    fig.update_layout(xaxis_title="Your SOV %", yaxis_title=None)
    return _apply_theme(fig, title, height=max(360, 34 * len(d) + 120))


def trend_lines(trend: pd.DataFrame,
                title: str = "SOV trend over time") -> go.Figure:
    fig = go.Figure()
    ci = 0
    # Plot client last so it sits on top.
    for is_client in (False, True):
        for brand, g in trend[trend["is_client"] == is_client].groupby("brand"):
            g = g.sort_values("period")
            if is_client:
                color, width = B.CLIENT_COLOR, 4
            else:
                color, width = B.COMPETITOR_COLORS[ci % len(B.COMPETITOR_COLORS)], 2
                ci += 1
            fig.add_trace(go.Scatter(
                x=g["period"], y=g["sov_pct"], mode="lines+markers",
                name=brand, line=dict(color=color, width=width),
                hovertemplate=f"{brand}<br>%{{x|%b %d}}: %{{y:.2f}}%<extra></extra>",
            ))
    fig.update_layout(xaxis_title=None, yaxis_title="SOV %")
    return _apply_theme(fig, title, height=440)


def channel_mix_bar(mix: pd.DataFrame,
                    title: str = "Your SOV by ad type") -> go.Figure:
    palette = {"sp": B.ELECTRIC, "organic": B.COBALT, "sb": B.SKY, "all": B.DEEP_PURPLE}
    fig = go.Figure(go.Bar(
        x=mix["channel"], y=mix["sov_pct"],
        marker_color=[palette.get(t, B.COBALT) for t in mix["type"]],
        text=[f"{v:.1f}%" for v in mix["sov_pct"]], textposition="outside",
    ))
    fig.update_layout(xaxis_title=None, yaxis_title="SOV %")
    return _apply_theme(fig, title, height=380)


def position_funnel_bar(funnel: pd.DataFrame,
                        title: str = "Where you win — position depth") -> go.Figure:
    fig = go.Figure(go.Bar(
        x=funnel["label"], y=funnel["sov_pct"], marker_color=B.ELECTRIC,
        text=[f"{v:.1f}%" for v in funnel["sov_pct"]], textposition="outside",
    ))
    fig.update_layout(xaxis_title=None, yaxis_title="Your SOV %")
    return _apply_theme(fig, title, height=380)


def branded_generic_bar(bg: pd.DataFrame,
                        title: str = "Branded vs generic — your SOV") -> go.Figure:
    palette = {"Branded": B.DEEP_PURPLE, "Generic": B.SKY}
    fig = go.Figure(go.Bar(
        x=bg["kw_class"], y=bg["client_sov"],
        marker_color=[palette.get(c, B.COBALT) for c in bg["kw_class"]],
        text=[f"{v:.1f}%" for v in bg["client_sov"]], textposition="outside",
        customdata=bg[["keywords"]].values,
        hovertemplate="%{x}<br>Your SOV: %{y:.2f}%<br>%{customdata[0]} keywords<extra></extra>",
    ))
    fig.update_layout(xaxis_title=None, yaxis_title="Your SOV %")
    return _apply_theme(fig, title, height=360)


def treemap_chart(overview: pd.DataFrame,
                  title: str = "Subcategory map — size = crawls, color = your SOV") -> go.Figure:
    if overview.empty:
        return _apply_theme(go.Figure(), title, height=420)
    fig = go.Figure(go.Treemap(
        labels=overview["category"], parents=[""] * len(overview),
        values=overview["crawls"],
        marker=dict(colors=overview["client_sov"], colorscale=B.SOV_SCALE,
                    cmin=0, cmax=max(50, overview["client_sov"].max()),
                    colorbar=dict(title="Your SOV %")),
        customdata=overview[["client_sov", "keywords"]].values,
        texttemplate="<b>%{label}</b><br>%{customdata[0]:.1f}% SOV<br>%{customdata[1]} kw",
        hovertemplate="%{label}<br>Your SOV: %{customdata[0]:.2f}%<br>Crawls: %{value:.0f}<extra></extra>",
    ))
    return _apply_theme(fig, title, height=440)


def overview_bar(ov: pd.DataFrame, brand_label: str = "your brand",
                 title: str | None = None) -> go.Figure:
    """Brand SOV across all its categories (the L1 landscape)."""
    title = title or f"{brand_label}: SOV across categories"
    d = ov.head(15).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d["client_sov"], y=d["category"], orientation="h",
        marker=dict(color=d["client_sov"], colorscale=B.SOV_SCALE,
                    cmin=0, cmax=max(40, float(d["client_sov"].max() or 1))),
        text=[f"{v:.1f}%" for v in d["client_sov"]], textposition="outside",
        customdata=d[["crawls", "keywords"]].values,
        hovertemplate="%{y}<br>Your SOV: %{x:.2f}%<br>Crawls: %{customdata[0]:.0f}"
                      "<br>%{customdata[1]} keywords<extra></extra>"))
    fig.update_layout(xaxis_title="Your SOV %", yaxis_title=None)
    return _apply_theme(fig, title, height=max(380, 32 * len(d) + 120))


def positioning_chart(kp: pd.DataFrame,
                      title: str = "You vs the category leader, by keyword") -> go.Figure:
    d = kp.iloc[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["leader_sov"], y=d["search_term"], orientation="h",
                         name="Category leader", marker_color=B.COBALT,
                         hovertemplate="Leader %{customdata}: %{x:.1f}%<extra></extra>",
                         customdata=d["leader"]))
    fig.add_trace(go.Bar(x=d["client_sov"], y=d["search_term"], orientation="h",
                         name="You", marker_color=B.ELECTRIC,
                         hovertemplate="You: %{x:.1f}%<extra></extra>"))
    fig.update_layout(barmode="overlay", xaxis_title="SOV %", yaxis_title=None,
                      legend=dict(orientation="h", y=1.04, x=0))
    fig.update_traces(opacity=0.92)
    return _apply_theme(fig, title, height=max(380, 34 * len(d) + 140))


def incrementality_chart(inc: pd.DataFrame,
                         title: str = "Organic vs paid-driven SOV, by keyword") -> go.Figure:
    d = inc.iloc[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["organic_sov"], y=d["search_term"], orientation="h",
                         name="Organic", marker_color=B.COBALT,
                         hovertemplate="Organic: %{x:.1f}%<extra></extra>"))
    fig.add_trace(go.Bar(x=d["incremental_sov"], y=d["search_term"], orientation="h",
                         name="Incremental (paid)", marker_color=B.ELECTRIC,
                         hovertemplate="Paid lift: %{x:.1f}%<extra></extra>"))
    fig.update_layout(barmode="stack", xaxis_title="SOV % (= organic + paid lift)",
                      yaxis_title=None, legend=dict(orientation="h", y=1.04, x=0))
    return _apply_theme(fig, title, height=max(380, 34 * len(d) + 140))


def winloss_bar(wl: pd.DataFrame,
                title: str = "SOV change — who's gaining and losing") -> go.Figure:
    d = wl.iloc[::-1]
    colors = [B.ELECTRIC if c else (B.SKY if v >= 0 else B.DEEP_PURPLE)
              for c, v in zip(d["is_client"], d["delta"])]
    fig = go.Figure(go.Bar(
        x=d["delta"], y=d["brand"], orientation="h", marker_color=colors,
        text=[f"{v:+.1f} pts" for v in d["delta"]], textposition="outside",
        hovertemplate="%{y}: %{x:+.2f} pts<extra></extra>"))
    fig.update_layout(xaxis_title="Δ SOV (pts, first → last week)", yaxis_title=None)
    return _apply_theme(fig, title, height=max(360, 34 * len(d) + 120))


def region_bar(reg: pd.DataFrame,
               title: str = "Your share of page-1 listings by region") -> go.Figure:
    if reg.empty:
        return _apply_theme(go.Figure(), title, height=360)
    d = reg.sort_values("share", ascending=True)
    fig = go.Figure(go.Bar(
        x=d["share"], y=d["region"], orientation="h", marker_color=B.ELECTRIC,
        text=[f"{v:.0f}%" for v in d["share"]], textposition="outside",
        hovertemplate="%{y}: %{x:.1f}% of page-1 listings<extra></extra>"))
    fig.update_layout(xaxis_title="Share of page-1 listings %", yaxis_title=None)
    return _apply_theme(fig, title, height=max(340, 28 * len(d) + 120))


def competitor_heatmap(matrix: pd.DataFrame,
                       title: str = "SOV by subcategory and brand") -> go.Figure:
    if matrix.empty:
        return _apply_theme(go.Figure(), title, height=420)
    pivot = matrix.pivot(index="brand", columns="category", values="sov_pct").fillna(0)
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=list(pivot.columns), y=list(pivot.index),
        colorscale=B.SOV_SCALE, colorbar=dict(title="SOV %"),
        hovertemplate="%{y} in %{x}<br>%{z:.2f}%<extra></extra>",
    ))
    return _apply_theme(fig, title, height=max(360, 40 * len(pivot) + 140))
