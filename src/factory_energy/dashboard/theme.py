from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from dash import html

BG = "#0b1220"
PANEL = "#121a2b"
LINE = "#24314d"
TEXT = "#e6edf7"
MUTED = "#8b9ab3"
ACCENT = "#22d3ee"
OK = "#10b981"
WARN = "#f59e0b"
BAD = "#ef4444"
VIOLET = "#a78bfa"
SERIES = ["#22d3ee", "#a78bfa", "#f59e0b", "#10b981", "#f472b6", "#60a5fa", "#facc15"]


def figure(height: int = 320, **layout: Any) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=height,
        margin={"l": 50, "r": 16, "t": 36, "b": 36},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT, "family": "Segoe UI, Inter, sans-serif", "size": 12},
        legend={"orientation": "h", "y": 1.12, "x": 0, "bgcolor": "rgba(0,0,0,0)"},
        xaxis={"gridcolor": LINE, "zeroline": False, "hoverformat": "%H:%M"},
        yaxis={"gridcolor": LINE, "zeroline": False, "hoverformat": ",.0f"},
        hovermode="x unified",
        # Dark hover box (Plotly's default is white), whole-number values, untruncated names.
        hoverlabel={"bgcolor": PANEL, "bordercolor": LINE, "namelength": -1,
                    "font": {"color": TEXT, "size": 12, "family": "Segoe UI, Inter, sans-serif"}},
        uirevision="keep",
    )
    fig.update_layout(**layout)
    return fig


def pad_bar_labels(fig: go.Figure, values: list[float]) -> None:
    """Horizontal bars with outside labels: extend the axis so labels are not clipped."""
    top = max(values, default=0.0)
    fig.update_xaxes(range=[0, top * 1.22 if top > 0 else 1])
    fig.update_traces(cliponaxis=False)


def kpi(title: str, value: str, sub: str = "", tone: str = "") -> html.Div:
    return html.Div(
        [
            html.H3(title),
            html.Div(value, className="kpi-value"),
            html.Div(sub, className="kpi-sub"),
        ],
        className=f"card kpi {tone}",
    )


def card(title: str, *children: Any, class_name: str = "") -> html.Div:
    return html.Div([html.H3(title), *children], className=f"card {class_name}")


def tone_for_ratio(ratio: float, warning: float = 0.9) -> str:
    if ratio >= 1.0:
        return "bad"
    return "warn" if ratio >= warning else "ok"
