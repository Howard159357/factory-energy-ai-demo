from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from factory_energy.dashboard import theme
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.status import TickState
from factory_energy.dashboard.widgets import (
    CENTER,
    add_band,
    alert_items,
    contract_lines,
    event_markers,
    now_line,
)
from factory_energy.energy.tariff import money

PATH = "/overview"
TITLE = "Overview"
LOOKBACK = timedelta(hours=10)
LOOKAHEAD = timedelta(hours=2)


def layout() -> html.Div:
    return html.Div([
        html.Div([html.H2("Plant overview", className="page-title"),
                  html.P("Live load, demand against the contract, next-hour forecast and "
                         "active alerts.", className="page-sub")]),
        html.Div(id="ov-kpis", className="grid grid-6"),
        html.Div([
            theme.card("Plant load, forecast and detections",
                       dcc.Graph(id="ov-load", config={"displayModeBar": False})),
            theme.card("Alerts", html.Div(id="ov-alerts", className="alert-list")),
        ], className="grid grid-2"),
        theme.card("Load by distribution board", dcc.Graph(id="ov-feeders",
                                                          config={"displayModeBar": False})),
    ], className="main-inner")


def kpis(ctx: Context, state: TickState) -> list[html.Div]:
    tariff = ctx.settings.tariff
    tone = theme.tone_for_ratio(state.contract_ratio, ctx.settings.demand.warning_ratio)
    temp = state.temperature
    return [
        theme.kpi("Plant load", f"{state.plant_kw:,.0f} kW",
                  f"sum of {len(ctx.data.feeder_ids)} distribution boards"),
        theme.kpi("15-min demand (projected)", f"{state.projected_kw:,.0f} kW",
                  f"{state.elapsed_min} of 15 min elapsed · so far {state.so_far_kw:,.0f} kW",
                  tone),
        theme.kpi("Contract usage", f"{state.contract_ratio:.0%}",
                  f"of {ctx.contract_kw:,.0f} kW", tone),
        theme.kpi("Chance of exceeding", f"{state.p_exceed:.0%}",
                  "within the next hour (forecast)", state.forecast_level.tone),
        theme.kpi("Energy today", f"{state.energy_today_kwh / 1000:,.1f} MWh",
                  f"about {money(state.cost_today, tariff)} since 00:00"),
        theme.kpi("Next 3 h peak (forecast)",
                  "-" if state.peak_3h_kw is None else f"{state.peak_3h_kw:,.0f} kW",
                  ("-" if state.peak_3h_at is None else f"around {state.peak_3h_at:%H:%M}")
                  + ("" if temp is None else f" · {temp:.1f} °C outside"),
                  theme.tone_for_ratio((state.peak_3h_kw or 0.0) / ctx.contract_kw,
                                       ctx.settings.demand.warning_ratio)),
    ]


def load_figure(ctx: Context, state: TickState) -> go.Figure:
    now = state.now
    start, end = now - LOOKBACK, now + LOOKAHEAD
    fig = theme.figure(height=380)
    ahead = ctx.data.day_ahead(now.date())
    if len(ahead):
        x = ahead.target_ts + CENTER
        add_band(fig, x, ahead.p10, ahead.p90, "Day-ahead forecast band", theme.VIOLET, 0.12)
        fig.add_trace(go.Scatter(x=x, y=ahead.p50, name="Day-ahead forecast",
                                 line={"color": theme.VIOLET, "dash": "dot", "width": 1.2}))
    actual = ctx.data.plant_series(start, now + timedelta(minutes=1))
    fig.add_trace(go.Scatter(x=actual.ts, y=actual.kw, name="Actual plant load",
                             line={"color": theme.ACCENT, "width": 1.8}))
    if len(state.forecast):
        x = state.forecast.target_ts + CENTER
        add_band(fig, x, state.forecast.p10, state.forecast.p90, "Next-hour band",
                 theme.WARN, 0.3)
        fig.add_trace(go.Scatter(x=x, y=state.forecast.p50, name="Next-hour forecast",
                                 mode="lines+markers", line={"color": theme.WARN, "width": 2}))
    contract_lines(fig, ctx)
    event_markers(fig, state, start, now)
    now_line(fig, now)
    fig.update_xaxes(range=[start, end], tickformat="%H:%M")
    fig.update_yaxes(title="kW", rangemode="tozero")
    return fig


def feeder_figure(ctx: Context, state: TickState) -> go.Figure:
    feeders = ctx.data.feeder_ids
    values = [float(state.snapshot.kw.get(f, 0.0) or 0.0) for f in feeders]
    names = [f"{f} {ctx.data.name(f)}" for f in feeders]
    fig = theme.figure(height=230, hovermode="closest")
    fig.add_trace(go.Bar(x=values, y=names, orientation="h", marker_color=theme.SERIES[0],
                         text=[f"{v:,.0f} kW" for v in values], textposition="outside"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="kW")
    theme.pad_bar_labels(fig, values)
    return fig


def update(ctx: Context, now: datetime) -> tuple[Any, ...]:
    state = ctx.tick(now)
    return (kpis(ctx, state), load_figure(ctx, state), alert_items(ctx, state),
            feeder_figure(ctx, state))


def register(app: Dash, ctx: Context) -> None:
    @app.callback(
        Output("ov-kpis", "children"), Output("ov-load", "figure"),
        Output("ov-alerts", "children"), Output("ov-feeders", "figure"),
        Input("clock", "data"),
    )
    def _refresh(clock: dict[str, Any]) -> tuple[Any, ...]:
        return update(ctx, ClockState.from_store(clock).now)
