from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from factory_energy.dashboard import theme
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context

PATH = "/history"
TITLE = "History"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def layout() -> html.Div:
    return html.Div([
        html.Div([html.H2("Historical analysis", className="page-title"),
                  html.P("Where and when the plant uses energy over the full simulated year.",
                         className="page-sub")]),
        html.Div(id="hi-insight", className="callout"),
        html.Div([
            theme.card("Average plant load by weekday and hour (kW)",
                       dcc.Graph(id="hi-heatmap", config={"displayModeBar": False})),
            theme.card("Top loads, last 30 days (kWh)",
                       dcc.Graph(id="hi-ranking", config={"displayModeBar": False})),
        ], className="grid grid-equal-2"),
        theme.card("Monthly energy by distribution board (MWh)",
                   dcc.Graph(id="hi-monthly", config={"displayModeBar": False})),
    ], className="main-inner")


def heatmap(ctx: Context) -> go.Figure:
    profile = ctx.weekday_hour.pivot(index="weekday", columns="hour", values="kw")
    fig = theme.figure(height=320, hovermode="closest")
    fig.add_trace(go.Heatmap(z=profile.to_numpy(), x=list(profile.columns),
                             y=[WEEKDAYS[i] for i in profile.index], colorscale="Viridis",
                             colorbar={"title": "kW"}))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="hour of day", dtick=2)
    return fig


def monthly(ctx: Context) -> go.Figure:
    frame = ctx.monthly_energy
    fig = theme.figure(height=320, barmode="stack")
    for index, (meter, part) in enumerate(frame.groupby("meter_id")):
        fig.add_trace(go.Bar(x=part.month, y=part.mwh, name=f"{meter} {ctx.data.name(str(meter))}",
                             marker_color=theme.SERIES[index % len(theme.SERIES)]))
    fig.update_xaxes(tickformat="%b")
    fig.update_yaxes(title="MWh")
    return fig


def insight(ctx: Context) -> str:
    frame = ctx.monthly_energy
    if frame.empty:
        return ""
    share = frame.groupby("meter_id").mwh.sum()
    share = (share / share.sum()).sort_values(ascending=False)
    top = ", ".join(f"{ctx.data.name(str(m))} {v:.0%}" for m, v in share.head(3).items())
    return f"Where the energy goes: {top}."


@lru_cache(maxsize=64)
def _ranking_cached(ctx_id: int, hour: datetime) -> go.Figure:
    ctx = _CONTEXTS[ctx_id]
    energy = ctx.data.meter_energy(hour - timedelta(days=30), hour).sort_values(
        ascending=False
    ).head(10)
    fig = theme.figure(height=320, hovermode="closest")
    fig.add_trace(go.Bar(x=energy.to_numpy(),
                         y=[f"{m} {ctx.data.name(str(m))}" for m in energy.index],
                         orientation="h", marker_color=theme.ACCENT,
                         text=[f"{v:,.0f}" for v in energy], textposition="outside"))
    fig.update_yaxes(autorange="reversed")
    theme.pad_bar_labels(fig, [float(v) for v in energy])
    return fig


_CONTEXTS: dict[int, Context] = {}


def ranking(ctx: Context, now: datetime) -> go.Figure:
    _CONTEXTS[id(ctx)] = ctx
    return _ranking_cached(id(ctx), now.replace(minute=0, second=0, microsecond=0))


def register(app: Dash, ctx: Context) -> None:
    @app.callback(Output("hi-heatmap", "figure"), Output("hi-monthly", "figure"),
                  Output("hi-insight", "children"), Input("url", "pathname"))
    def _static(_: str) -> tuple[Any, ...]:
        return heatmap(ctx), monthly(ctx), insight(ctx)

    @app.callback(Output("hi-ranking", "figure"), Input("clock", "data"))
    def _ranking(clock: dict[str, Any]) -> go.Figure:
        return ranking(ctx, ClockState.from_store(clock).now)
