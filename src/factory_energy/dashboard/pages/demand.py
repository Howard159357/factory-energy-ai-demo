from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from factory_energy.dashboard import theme
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.pages.equipment import open_detections
from factory_energy.dashboard.playbook import shed_options
from factory_energy.dashboard.sld import data_uri, render
from factory_energy.dashboard.status import ALARM_PROBABILITY, WARNING_PROBABILITY, TickState
from factory_energy.dashboard.widgets import CENTER, contract_lines, event_markers, now_line
from factory_energy.energy.tariff import exceedance_penalty, money

PATH = "/demand"
TITLE = "Demand"


def layout() -> html.Div:
    return html.Div([
        html.Div([html.H2("Demand management", className="page-title"),
                  html.P("The running 15-minute interval against the contract, the next-hour "
                         "risk, and what can be shed right now.", className="page-sub")]),
        html.Div(id="dm-whatif"),
        html.Div(id="dm-kpis", className="grid grid-4"),
        html.Div([
            theme.card("15-minute demand (last 8 h) and next-hour forecast",
                       dcc.Graph(id="dm-demand", config={"displayModeBar": False})),
            theme.card("Load-shed playbook (available now)", html.Div(id="dm-playbook")),
        ], className="grid grid-2"),
        theme.card("Chance of exceeding the contract within the next hour (today)",
                   dcc.Graph(id="dm-risk", config={"displayModeBar": False})),
        theme.card("Single-line diagram: supply, distribution boards and loads",
                   html.Img(id="dm-sld", className="sld")),
    ], className="main-inner")


def kpis(ctx: Context, state: TickState) -> list[html.Div]:
    tone = theme.tone_for_ratio(state.contract_ratio, ctx.settings.demand.warning_ratio)
    return [
        theme.kpi("Interval in progress",
                  f"{state.interval_start:%H:%M}-{state.interval_end:%H:%M}",
                  f"{state.elapsed_min} of 15 min elapsed"),
        theme.kpi("Projected demand", f"{state.projected_kw:,.0f} kW",
                  f"average so far {state.so_far_kw:,.0f} kW", tone),
        theme.kpi("Headroom", f"{ctx.contract_kw - state.projected_kw:,.0f} kW",
                  f"to the {ctx.contract_kw:,.0f} kW contract", tone),
        theme.kpi("Next-hour risk", state.forecast_level.value,
                  f"{state.p_exceed:.0%} chance of exceeding the contract"
                  + (f" in {state.risk_interval}" if state.risk_interval else ""),
                  state.forecast_level.tone),
    ]


def demand_figure(ctx: Context, state: TickState) -> go.Figure:
    now = state.now
    history = ctx.data.demand(now - timedelta(hours=8), now)
    ratio = history.kw / ctx.contract_kw
    warn = ctx.settings.demand.warning_ratio
    colors = np.where(ratio >= 1, theme.BAD, np.where(ratio >= warn, theme.WARN, theme.ACCENT))
    fig = theme.figure(height=340)
    fig.add_trace(go.Bar(x=history.w + CENTER, y=history.kw, marker_color=colors,
                         name="Actual 15-min demand", width=13 * 60_000))
    if len(state.forecast):
        f = state.forecast
        fig.add_trace(go.Scatter(
            x=f.target_ts + CENTER, y=f.p50, mode="markers+lines",
            name="Forecast (most likely, with 10-90% range)",
            line={"color": theme.WARN, "width": 2},
            error_y={"type": "data", "symmetric": False, "array": f.p90 - f.p50,
                     "arrayminus": f.p50 - f.p10, "color": theme.WARN},
        ))
    contract_lines(fig, ctx)
    event_markers(fig, state, now - timedelta(hours=8), now)
    now_line(fig, now)
    fig.update_yaxes(title="kW", range=[0, ctx.contract_kw * 1.15])
    fig.update_xaxes(range=[now - timedelta(hours=8), now + timedelta(hours=1, minutes=15)],
                     tickformat="%H:%M")
    return fig


def risk_figure(ctx: Context, state: TickState) -> go.Figure:
    now = state.now
    midnight = datetime.combine(now.date(), datetime.min.time())
    risk = ctx.data.exceedance_timeline(midnight, now - timedelta(minutes=15))
    fig = theme.figure(height=220)
    fig.add_trace(go.Scatter(x=risk.issue_ts + timedelta(minutes=15), y=risk.p, fill="tozeroy",
                             name="Chance of exceeding within the next hour",
                             line={"color": theme.ACCENT}))
    fig.add_hline(y=ALARM_PROBABILITY, line={"color": theme.BAD, "dash": "dash"},
                  annotation_text="alarm", annotation_font_color=theme.BAD)
    fig.add_hline(y=WARNING_PROBABILITY, line={"color": theme.WARN, "dash": "dot"},
                  annotation_text="warning", annotation_font_color=theme.WARN)
    now_line(fig, now)
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    fig.update_xaxes(range=[midnight, midnight + timedelta(days=1)], tickformat="%H:%M")
    return fig


def playbook(ctx: Context, state: TickState) -> html.Div:
    needed = max(state.projected_kw - ctx.contract_kw, 0.0)
    rows, total = [], 0.0
    for option in shed_options(ctx, state.snapshot):
        if option.shed_kw <= 0.5:
            continue
        total += option.shed_kw
        rows.append(html.Tr([html.Td(option.action), html.Td(", ".join(option.meters)),
                             html.Td(f"{option.load_kw:,.0f}"),
                             html.Td(f"{option.shed_kw:,.0f}")]))
    rows.append(html.Tr([html.Td(html.Strong("Total available")), html.Td(""), html.Td(""),
                         html.Td(html.Strong(f"{total:,.0f} kW"))]))
    if needed > 0:
        verdict = (f"Need to shed {needed:,.0f} kW · "
                   + ("covered by the playbook" if total >= needed else "playbook is not enough"))
        tone = "ok" if total >= needed else "bad"
    else:
        verdict, tone = "Nothing to shed right now", "muted"
    return html.Div([
        html.Div(verdict, className=f"verdict {tone}"),
        html.Table(
            [html.Thead(html.Tr([html.Th("Action"), html.Th("Loads"), html.Th("Load kW"),
                                 html.Th("Shed kW (assumed)")])),
             html.Tbody(rows)],
            className="data",
        ),
        html.Div("Shed shares are illustrative assumptions for the demo plant.",
                 className="muted small"),
    ])


def whatif_panel(ctx: Context, scenario: str | None) -> html.Div | None:
    result = ctx.whatif(scenario) if scenario else None
    if result is None:
        return None
    tariff = ctx.settings.tariff
    day = datetime.combine(result.day, datetime.min.time())
    minutes = pd.date_range(day, periods=result.actual_kw.size, freq="min")

    def interval(kw: np.ndarray) -> pd.Series:
        series = pd.Series(kw, index=minutes).resample("15min").mean()
        return series[(series.index >= day + timedelta(hours=6))
                      & (series.index < day + timedelta(hours=12))]

    fig = theme.figure(height=260)
    for kw, name, color in ((result.actual_kw, "As it happened: everything at 08:00", theme.BAD),
                            (result.staggered_kw,
                             f"Staggered start, {result.stagger_minutes} min apart", theme.OK)):
        part = interval(kw)
        fig.add_trace(go.Scatter(x=part.index + CENTER, y=part, name=name, mode="lines+markers",
                                 line={"color": color}))
    contract_lines(fig, ctx)
    fig.update_yaxes(title="15-min demand kW")
    demand = pd.Series(result.actual_kw, index=minutes).resample("15min").mean()
    peak_at = pd.Timestamp(demand.idxmax()).to_pydatetime()
    penalty = exceedance_penalty(result.actual_peak_kw, ctx.contract_kw, tariff, peak_at)
    below = result.staggered_peak_kw < ctx.contract_kw
    return html.Div([
        html.Div([
            html.Div("What-if: staggered start-up (re-simulated day)", className="hero-title"),
            html.Div([
                html.Div([html.Div(f"-{result.reduction_kw:,.0f} kW", className="hero-number"),
                          html.Div("peak demand", className="hero-sub")]),
                html.Div([html.Div(money(penalty, tariff), className="hero-number"),
                          html.Div("exceedance penalty avoided this month",
                                   className="hero-sub")]),
                html.Div([
                    html.Div(f"{result.actual_peak_kw:,.0f} → {result.staggered_peak_kw:,.0f} kW",
                             className="hero-number small"),
                    html.Div(f"{'below' if below else 'still above'} the "
                             f"{ctx.contract_kw:,.0f} kW contract",
                             className=f"hero-sub {'ok' if below else 'bad'}"),
                ]),
            ], className="hero-row"),
            html.Div("Same simulator, same day, machines started "
                     f"{result.stagger_minutes} minutes apart instead of all at once.",
                     className="muted small"),
        ], className="hero-text"),
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
    ], className="card hero")


def single_line(ctx: Context, state: TickState) -> str:
    alerting = set(open_detections(state))
    return data_uri(render(ctx, state, alerting))


def update(ctx: Context, clock: ClockState) -> tuple[Any, ...]:
    state = ctx.tick(clock.now)
    return (kpis(ctx, state), demand_figure(ctx, state), playbook(ctx, state),
            risk_figure(ctx, state), single_line(ctx, state))


def register(app: Dash, ctx: Context) -> None:
    @app.callback(
        Output("dm-kpis", "children"), Output("dm-demand", "figure"),
        Output("dm-playbook", "children"), Output("dm-risk", "figure"),
        Output("dm-sld", "src"),
        Input("clock", "data"),
    )
    def _refresh(clock: dict[str, Any]) -> tuple[Any, ...]:
        return update(ctx, ClockState.from_store(clock))

    @app.callback(Output("dm-whatif", "children"), Input("scenario", "value"))
    def _whatif(scenario: str | None) -> html.Div | None:
        return whatif_panel(ctx, scenario)
