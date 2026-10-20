"""Building blocks shared by several pages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from dash import html

from factory_energy.dashboard import theme
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.status import Level, TickState
from factory_energy.energy.tariff import (
    PERIOD_NAMES,
    average_rate,
    exceedance_penalty,
    money,
    period_at,
    power_factor_adjustment,
    rate_at,
)

CENTER = timedelta(minutes=7, seconds=30)  # plot a 15-min interval at its middle


@dataclass(frozen=True)
class EventText:
    label: str
    action: str


EVENTS: dict[str, EventText] = {
    "SIMULTANEOUS_START": EventText(
        "Simultaneous start-up", "Stagger machine start-ups 15 min apart"),
    "DEMAND_EXCEEDANCE": EventText(
        "Demand above contract", "Shed load now; review the start-up sequence"),
    "OFF_SCHEDULE_RUNNING": EventText(
        "Running outside schedule", "Switch the machine off; add it to the shutdown checklist"),
    "LOW_POWER_FACTOR": EventText(
        "Low power factor", "Inspect the capacitor bank on this board"),
    "AIR_LEAK": EventText(
        "Compressed-air leak suspected", "Walk the air network with an ultrasonic leak detector"),
    "UNUSUAL_DAY": EventText(
        "Unusual load pattern", "Low priority: check against the production plan"),
}
LAYER_NAMES = {"RULE": "Rule", "BASELINE": "Baseline", "ML": "ML"}


def event_label(event_type: str) -> str:
    text = EVENTS.get(event_type)
    return text.label if text else event_type.replace("_", " ").capitalize()


def impact_text(ctx: Context, row: pd.Series) -> str:
    """One line of money or energy impact per detection, from its stored score."""
    tariff = ctx.settings.tariff
    kind, score = str(row.event_type), float(row.score)
    if kind == "DEMAND_EXCEEDANCE":
        when = pd.Timestamp(row.start_ts).to_pydatetime()
        penalty = exceedance_penalty(score, ctx.contract_kw, tariff, when)
        return (f"Impact: {score - ctx.contract_kw:,.0f} kW over in the "
                f"{PERIOD_NAMES[period_at(when, tariff)]} period · up to {money(penalty, tariff)}")
    if kind == "OFF_SCHEDULE_RUNNING":
        cost = score * rate_at(pd.Timestamp(row.start_ts).to_pydatetime(), tariff)
        return f"Impact: {score:,.0f} kWh wasted · about {money(cost, tariff)}"
    if kind == "AIR_LEAK":
        yearly = score * 24 * 365 * average_rate(tariff)
        return f"Impact: +{score:,.0f} kW around the clock · about {money(yearly, tariff)}/year"
    if kind == "SIMULTANEOUS_START":
        return f"Impact: {int(score)} machines started together"
    if kind == "LOW_POWER_FACTOR":
        rule = tariff.power_factor
        change = power_factor_adjustment(score, tariff)
        best = -power_factor_adjustment(rule.cap, tariff)
        effect = (f"surcharge {change:.1%} of the bill" if change > 0
                  else f"bill credit {-change:.1%} instead of {best:.1%}")
        return (f"Impact: power factor {score:.2f} · {effect} "
                f"(surcharge below {rule.base:.2f})")
    return ""


def alert_items(ctx: Context, state: TickState, limit: int = 12) -> list[html.Div]:
    items: list[html.Div] = []
    if state.forecast_level is not Level.OK:
        items.append(forecast_alert(ctx, state))
    for row in state.detections_24h.head(limit).itertuples():
        text = EVENTS.get(row.event_type)
        items.append(html.Div([
            html.Div([
                html.Span(event_label(row.event_type), className="alert-title"),
                html.Span(LAYER_NAMES.get(row.layer, row.layer), className=f"tag {row.layer}"),
            ], className="alert-head"),
            html.Div(", ".join(row.meter_ids), className="alert-meta"),
            html.Div(impact_text(ctx, pd.Series(row._asdict())), className="alert-impact"),
            html.Div(f"Do: {text.action}" if text else "", className="alert-action"),
            html.Div(f"detected {pd.Timestamp(row.detected_ts):%a %d %b %H:%M}",
                     className="alert-meta"),
        ], className=f"alert {row.severity}"))
    if not items:
        items.append(html.Div("No active alerts.", className="muted"))
    return items


def forecast_alert(ctx: Context, state: TickState) -> html.Div:
    worst = state.forecast.loc[state.forecast.p_exceed.idxmax()]
    target = pd.Timestamp(worst.target_ts)
    level = state.forecast_level.value.lower()
    return html.Div([
        html.Div([
            html.Span(f"Forecast {level}: demand may exceed the contract",
                      className="alert-title"),
            html.Span("Forecast", className="tag FORECAST"),
        ], className="alert-head"),
        html.Div(
            f"{state.p_exceed:.0%} chance for {target:%H:%M}-{target + timedelta(minutes=15):%H:%M}"
            f" · most likely {worst.p50:,.0f} kW · 1-in-10 worst case {worst.p90:,.0f} kW",
            className="alert-meta",
        ),
        html.Div(f"Do: {state.action}", className="alert-action"),
    ], className="alert forecast")


def contract_lines(fig: go.Figure, ctx: Context) -> None:
    fig.add_hline(y=ctx.contract_kw, line={"color": theme.BAD, "dash": "dash", "width": 1.5},
                  annotation_text=f"Contract {ctx.contract_kw:,.0f} kW",
                  annotation_position="top left", annotation_font_color=theme.BAD)
    fig.add_hline(y=ctx.warning_kw, line={"color": theme.WARN, "dash": "dot", "width": 1},
                  annotation_text=f"{ctx.settings.demand.warning_ratio:.0%} of contract",
                  annotation_position="bottom left", annotation_font_color=theme.WARN)


def now_line(fig: go.Figure, now: datetime) -> None:
    fig.add_vline(x=now, line={"color": theme.MUTED, "width": 1},
                  annotation_text="now", annotation_position="top right",
                  annotation_font_color=theme.MUTED)


def event_markers(fig: go.Figure, state: TickState, start: datetime, end: datetime) -> None:
    """Mark detections that fired inside [start, end]: shaded event, dotted 'detected' line."""
    rows = state.detections_24h
    rows = rows[(rows.detected_ts >= start) & (rows.detected_ts <= end) & (rows.layer != "ML")]
    labelled: set[str] = set()
    for row in rows.sort_values("detected_ts").head(8).itertuples():
        fig.add_vrect(x0=row.start_ts, x1=min(row.end_ts, state.now), fillcolor=theme.BAD,
                      opacity=0.10, line_width=0)
        if row.event_type in labelled:
            continue  # one label per kind of event keeps the chart readable
        labelled.add(row.event_type)
        # Labels of events minutes apart would overprint: stack them one line per kind.
        fig.add_vline(x=row.detected_ts, line={"color": theme.WARN, "dash": "dot", "width": 1},
                      annotation_text=event_label(row.event_type),
                      annotation_position="top left", annotation_font_color=theme.WARN,
                      annotation_font_size=10, annotation_yshift=-14 * (len(labelled) - 1))


def add_band(
    fig: go.Figure, x: pd.Series, low: pd.Series, high: pd.Series, name: str, color: str,
    opacity: float = 0.18,
) -> None:
    fig.add_trace(go.Scatter(x=x, y=high, line={"width": 0}, hoverinfo="skip",
                             showlegend=False))
    fig.add_trace(go.Scatter(
        x=x, y=low, line={"width": 0}, fill="tonexty", name=name, hoverinfo="skip",
        fillcolor=_rgba(color, opacity),
    ))


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def equipment_status(kw: float, rated: float) -> str:
    if kw > 0.2 * rated:
        return "RUNNING"
    return "IDLE" if kw > 0.03 * rated else "OFF"


def banner(state: TickState) -> html.Div:
    return html.Div([
        html.Span(state.level.value, className=f"level {state.level.tone}"),
        html.Span(state.headline, className="banner-text"),
        html.Span(f"Action: {state.action}", className="banner-action"),
        html.Span("Internal management alert for dispatch decisions; not the utility's "
                  "official exceedance ruling.", className="banner-note"),
    ], className=f"banner {state.level.tone}")
