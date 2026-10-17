"""Plotly figure builders. Each function takes DataFrames and returns a figure.

Design notes (kept here so the choices are easy to explain):
  * One shared dark theme, large fonts so charts stay readable on a projector.
  * Teal = the main series. Amber = the second series in any two-series
    comparison (before/after, year A/year B). Two hues keep the legend simple.
  * Magnitude uses a single hue (teal), not a rainbow.
  * Charts never use a second y-axis.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from countries import INDIA_COORDS, INDIA_NAME, get_country_info

# --- palette ---------------------------------------------------------------
BG = "#0b1220"        # page background (navy)
PANEL = "#111a2e"     # chart surface
TEXT = "#e6edf7"
MUTED = "#9fb0c8"
GRID = "#22304a"
# Series colours for the chart marks. Checked with a palette validator against
# the PANEL surface: lightness band, colour-blind separation and contrast pass.
TEAL = "#10a89a"
AMBER = "#c97d06"
LAND = "#1f3050"      # non-partner land: visible but quiet
LAND_EDGE = "#3a4f78"

FONT = dict(family="Inter, Segoe UI, Helvetica, Arial, sans-serif", size=15, color=TEXT)


def _scale(max_value: float) -> tuple[float, str]:
    """Pick a readable unit for the axis: billions or millions of USD."""
    if max_value >= 1e9:
        return 1e9, "USD billion"
    return 1e6, "USD million"


def _base_layout(fig: go.Figure, title: str, height: int = 520) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color=TEXT), x=0.01, xanchor="left"),
        paper_bgcolor=PANEL,
        plot_bgcolor=PANEL,
        font=FONT,
        height=height,
        margin=dict(l=20, r=30, t=70, b=40),
        hoverlabel=dict(bgcolor=BG, font_size=15, font_color=TEXT, bordercolor=TEAL),
    )
    return fig


# --- 1. ranked bar chart -----------------------------------------------------
def partner_bar(table: pd.DataFrame, title: str, top_n: int = 15) -> go.Figure:
    """Horizontal ranked bars: biggest partner at the top."""
    shown = table.head(top_n)
    divisor, unit = _scale(float(shown["trade_value_usd"].max()))
    values = shown["trade_value_usd"] / divisor

    fig = go.Figure(
        go.Bar(
            x=values,
            y=shown["partner_country"],
            orientation="h",
            marker=dict(color=TEAL, cornerradius=4),
            text=[f"{v:,.2f}" for v in values],
            textposition="outside",
            textfont=dict(color=TEXT, size=14),
            cliponaxis=False,
            customdata=shown[["share_pct", "rank"]],
            hovertemplate=(
                "<b>%{y}</b><br>Rank: %{customdata[1]}<br>"
                f"Trade value: %{{x:,.3f}} {unit}<br>"
                "Share: %{customdata[0]:.1f}%<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=15))
    fig.update_xaxes(
        title=f"Trade value ({unit})", gridcolor=GRID, zeroline=False,
        rangemode="tozero",
    )
    height = max(380, 38 * len(shown) + 150)
    _base_layout(fig, title, height)
    fig.update_layout(margin=dict(l=20, r=70, t=70, b=50), showlegend=False)
    return fig


# --- 2. partner share (treemap) ------------------------------------------------
def share_treemap(table: pd.DataFrame, title: str, top_n: int = 10) -> go.Figure:
    """Each tile's area = that partner's share. Small partners fold into 'Other'."""
    top = table.head(top_n)
    rest = table.iloc[top_n:]
    labels = list(top["partner_country"])
    values = list(top["trade_value_usd"])
    if not rest.empty:
        labels.append(f"Other ({len(rest)} partners)")
        values.append(float(rest["trade_value_usd"].sum()))

    total = float(sum(values))
    shares = [v / total * 100 for v in values]

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=[""] * len(labels),
            values=values,
            customdata=shares,
            texttemplate="<b>%{label}</b><br>%{customdata:.1f}%",
            textfont=dict(size=17, color="#04121a"),
            marker=dict(
                colors=shares,
                colorscale=[[0, "#8ef0e3"], [1, TEAL]],
                line=dict(width=2, color=PANEL),
            ),
            hovertemplate="<b>%{label}</b><br>Share: %{customdata:.2f}%<extra></extra>",
            sort=True,
            pathbar=dict(visible=False),
        )
    )
    _base_layout(fig, title, height=460)
    fig.update_layout(margin=dict(l=10, r=10, t=70, b=10))
    return fig


# --- 3. network-style map ---------------------------------------------------------
# The map is drawn on ordinary x/y axes (x = longitude, y = latitude) from a small
# outline file shipped in data/. Plotly's own map layer would download its
# outlines from the internet at view time, which would break offline use.
WORLD_OUTLINE_PATH = Path(__file__).parent / "data" / "world_outline.json"


@lru_cache(maxsize=1)
def load_world_outline() -> list[dict]:
    """Country outlines (Natural Earth, public domain). Empty list if missing."""
    try:
        with WORLD_OUTLINE_PATH.open(encoding="utf-8") as f:
            return json.load(f)["countries"]
    except (OSError, ValueError, KeyError):
        return []  # the map still works: it just has no coastlines


def _outline_xy(countries: list[dict]) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """Flatten polygons into one x/y list; None breaks the line between polygons."""
    xs: list[Optional[float]] = []
    ys: list[Optional[float]] = []
    for country in countries:
        for ring in country["rings"]:
            xs.extend(pt[0] for pt in ring)
            ys.extend(pt[1] for pt in ring)
            xs.append(None)
            ys.append(None)
    return xs, ys


def _label_positions(lons: list[float]) -> list[str]:
    """Spread labels out: partners west of India go left, others above/below."""
    west = east = 0
    positions = []
    for lon in lons:
        if lon < INDIA_COORDS[1] - 5:
            positions.append("top left" if west % 2 == 0 else "bottom left")
            west += 1
        else:
            positions.append("top center" if east % 2 == 0 else "bottom center")
            east += 1
    return positions


def network_map(
    table: pd.DataFrame, title: str, trade_flow: str, top_n: int = 15
) -> tuple[go.Figure, list[str]]:
    """India at the centre, a line to each partner; line width = trade value.

    Returns (figure, names of partners that could not be placed on the map).
    The lines show "who trades with India", not real shipping routes.
    """
    shown = table.head(top_n)
    unmapped: list[str] = []
    placed = []
    for _, row in shown.iterrows():
        info = get_country_info(row["partner_country"])
        if info is None:
            unmapped.append(row["partner_country"])
        else:
            placed.append((row, info))

    fig = go.Figure()

    # 1) Land: every country outline in one dark trace.
    world = load_world_outline()
    if world:
        xs, ys = _outline_xy(world)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines", fill="toself", fillcolor=LAND,
            line=dict(color=LAND_EDGE, width=0.6), hoverinfo="skip", showlegend=False,
        ))

    if placed:
        max_value = max(r["trade_value_usd"] for r, _ in placed)
        divisor, unit = _scale(max_value)

        # 2) Partner countries shaded teal; darker tint = bigger trade value.
        by_iso = {c["iso3"]: c for c in world if c["iso3"]}
        for row, (iso3, _lat, _lon) in placed:
            country = by_iso.get(iso3)
            if country is None:
                continue  # tiny states are missing from the outline; the marker still shows
            xs, ys = _outline_xy([country])
            alpha = 0.25 + 0.45 * math.sqrt(row["trade_value_usd"] / max_value)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", fill="toself",
                fillcolor=f"rgba(16,168,154,{alpha:.2f})",
                line=dict(color=TEAL, width=0.8), hoverinfo="skip", showlegend=False,
            ))

        # 3) Lines from India to each partner; width = trade value.
        india_lat, india_lon = INDIA_COORDS
        for row, (_iso, lat, lon) in placed:
            width = 1.2 + 7.0 * math.sqrt(row["trade_value_usd"] / max_value)
            fig.add_trace(go.Scatter(
                x=[india_lon, lon], y=[india_lat, lat], mode="lines",
                line=dict(width=width, color="rgba(94,234,212,0.45)"),
                hoverinfo="skip", showlegend=False,
            ))

        # 4) Partner markers with hover details; sized by trade value.
        fig.add_trace(go.Scatter(
            x=[i[2] for _, i in placed],
            y=[i[1] for _, i in placed],
            mode="markers+text",
            text=[r["partner_country"] for r, _ in placed],
            # Show names only for the 8 biggest partners; others appear on hover.
            texttemplate=["%{text}" if k < 8 else "" for k in range(len(placed))],
            textposition=_label_positions([i[2] for _, i in placed]),
            textfont=dict(size=12, color=TEXT),
            marker=dict(
                size=[9 + 22 * math.sqrt(r["trade_value_usd"] / max_value) for r, _ in placed],
                color=TEAL, line=dict(width=2, color=BG),
            ),
            customdata=[
                [r["trade_value_usd"] / divisor, r["share_pct"], r["rank"]] for r, _ in placed
            ],
            hovertemplate=(
                "<b>%{text}</b><br>Rank: %{customdata[2]}<br>"
                f"Trade value: %{{customdata[0]:,.3f}} {unit}<br>"
                "Share: %{customdata[1]:.1f}%<extra></extra>"
            ),
            name="Partner (size = trade value)",
        ))

    fig.add_trace(go.Scatter(
        x=[INDIA_COORDS[1]], y=[INDIA_COORDS[0]], mode="markers+text",
        text=[INDIA_NAME], textposition="middle right",
        textfont=dict(size=15, color=AMBER),
        marker=dict(size=16, color=AMBER, symbol="diamond", line=dict(width=2, color=BG)),
        hovertemplate=f"<b>{INDIA_NAME}</b> (reporting country)<extra></extra>",
        name="India (reporter)",
    ))

    # No equal-aspect lock: the map stretches slightly to fill the panel, which is
    # fine for a network picture and far more readable on a projector.
    fig.update_xaxes(range=[-170, 180], visible=False)
    fig.update_yaxes(range=[-50, 80], visible=False)
    _base_layout(fig, title, height=560)
    fig.update_layout(
        margin=dict(l=0, r=0, t=60, b=40),
        legend=dict(orientation="h", y=-0.02, x=0.01, font=dict(size=14)),
        dragmode="pan",
    )
    return fig, unmapped


# --- 4. comparison ---------------------------------------------------------------
def comparison_bar(cmp: pd.DataFrame, title: str, top_n: int = 12) -> go.Figure:
    """Grouped horizontal bars: selection A (teal) vs selection B (amber)."""
    label_a, label_b = cmp.attrs["label_a"], cmp.attrs["label_b"]
    shown = cmp.head(top_n)
    divisor, unit = _scale(float(shown[["value_a", "value_b"]].max().max()))

    fig = go.Figure()
    for col, label, colour in (("value_a", label_a, TEAL), ("value_b", label_b, AMBER)):
        fig.add_trace(
            go.Bar(
                x=shown[col] / divisor,
                y=shown["partner_country"],
                orientation="h",
                name=label,
                marker=dict(color=colour, cornerradius=3),
                hovertemplate=(
                    "<b>%{y}</b><br>" + label + f": %{{x:,.3f}} {unit}<extra></extra>"
                ),
            )
        )
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=15))
    fig.update_xaxes(title=f"Trade value ({unit})", gridcolor=GRID, rangemode="tozero")
    _base_layout(fig, title, height=max(420, 62 * len(shown) + 160))
    fig.update_layout(margin=dict(l=20, r=30, t=100, b=50),
                      legend=dict(orientation="h", y=1.0, yanchor="bottom", x=1, xanchor="right", font=dict(size=15)))
    return fig


# --- 5. scenario ----------------------------------------------------------------
def scenario_chart(after: pd.DataFrame, title: str, top_n: int = 10) -> go.Figure:
    """Partner shares before vs after the illustrative reduction."""
    shown = after.sort_values("rank_before").head(top_n)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=shown["share_before_pct"], y=shown["partner_country"], orientation="h",
            name="Before (selected data)", marker=dict(color=TEAL, cornerradius=3),
            hovertemplate="<b>%{y}</b><br>Before: %{x:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=shown["share_after_pct"], y=shown["partner_country"], orientation="h",
            name="After (illustrative scenario)", marker=dict(color=AMBER, cornerradius=3),
            hovertemplate="<b>%{y}</b><br>After: %{x:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=15))
    fig.update_xaxes(title="Share of total trade (%)", gridcolor=GRID, rangemode="tozero")
    _base_layout(fig, title, height=max(420, 62 * len(shown) + 160))
    fig.update_layout(margin=dict(l=20, r=30, t=100, b=50),
                      legend=dict(orientation="h", y=1.0, yanchor="bottom", x=1, xanchor="right", font=dict(size=15)))
    return fig
