from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html

from factory_energy.dashboard import theme
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.widgets import CENTER, add_band, contract_lines, now_line
from factory_energy.forecasting.model import PRIMARY_MODEL

PATH = "/forecast"
TITLE = "Forecast"
MODEL_LABELS = {
    "profile": "Weekly profile (spreadsheet baseline)",
    "linear": "Ridge regression",
    "hgb": "Gradient-boosted trees (scikit-learn HGB)",
    "lightgbm": "Gradient-boosted trees (LightGBM)",
    "ensemble": "Ensemble (LightGBM + Ridge)",
}


def layout() -> html.Div:
    return html.Div([
        html.Div([html.H2("Load forecast", className="page-title"),
                  html.P("Quantile models trained only on data before each forecast; bands are "
                         "calibrated to cover 80% of outcomes. Alerts use the primary model.",
                         className="page-sub")]),
        html.Div([
            html.Span("Model shown", className="muted"),
            dcc.Dropdown(id="fc-model", clearable=False, style={"minWidth": "320px"}),
        ], className="toolbar"),
        html.Div([
            theme.card("Next 3 hours (issued at the last completed interval)",
                       dcc.Graph(id="fc-next", config={"displayModeBar": False})),
            theme.card("Today: day-ahead forecast (issued yesterday) vs actual",
                       dcc.Graph(id="fc-day", config={"displayModeBar": False})),
        ], className="grid grid-equal-2"),
        html.Div([
            theme.card("Out-of-sample accuracy (primary model)", html.Div(id="fc-metrics")),
            theme.card("How it works", html.Ul([
                html.Li("Predicts the change from a recent anchor, so it can forecast loads "
                        "above anything seen in training."),
                html.Li("Uses only what is known at issue time: demand so far, the production "
                        "calendar and a weather forecast."),
                html.Li("The 10-50-90% quantiles give the chance of exceeding the contract: "
                        "20% raises a warning, 50% an alarm."),
                html.Li("A simultaneous start-up is not forecastable from history; it is "
                        "caught in real time by the start-up rule."),
            ])),
        ], className="grid grid-equal-2"),
        theme.card("Model comparison (same features, same backtest, same calibration)",
                   html.Div(id="fc-compare")),
    ], className="main-inner")


def next_figure(ctx: Context, now: datetime, model: str) -> go.Figure:
    fig = theme.figure(height=320)
    start = now - timedelta(hours=3)
    actual = ctx.data.plant_series(start, now + timedelta(minutes=1))
    fig.add_trace(go.Scatter(x=actual.ts, y=actual.kw, name="Actual plant load",
                             line={"color": theme.ACCENT, "width": 1.8}))
    ahead = ctx.data.next_forecast(now, 180, model)
    if len(ahead):
        x = ahead.target_ts + CENTER
        add_band(fig, x, ahead.p10, ahead.p90, "10-90% range", theme.WARN, 0.25)
        fig.add_trace(go.Scatter(x=x, y=ahead.p50, name=f"{MODEL_LABELS.get(model, model)} P50",
                                 mode="lines+markers", line={"color": theme.WARN, "width": 2}))
    contract_lines(fig, ctx)
    now_line(fig, now)
    fig.update_xaxes(range=[start, now + timedelta(hours=3, minutes=15)], tickformat="%H:%M")
    fig.update_yaxes(title="kW", rangemode="tozero")
    return fig


def day_figure(ctx: Context, now: datetime, model: str) -> go.Figure:
    midnight = datetime.combine(now.date(), datetime.min.time())
    fig = theme.figure(height=320)
    ahead = ctx.data.day_ahead(now.date(), model)
    if len(ahead):
        x = ahead.target_ts + CENTER
        add_band(fig, x, ahead.p10, ahead.p90, "10-90% range", theme.VIOLET, 0.22)
        fig.add_trace(go.Scatter(x=x, y=ahead.p50, name="Most likely (P50)",
                                 line={"color": theme.VIOLET, "width": 2}))
    actual = ctx.data.demand(midnight, now)
    fig.add_trace(go.Scatter(x=actual.w + CENTER, y=actual.kw, name="Actual 15-min demand",
                             mode="lines+markers", line={"color": theme.ACCENT, "width": 2},
                             marker={"size": 4}))
    contract_lines(fig, ctx)
    now_line(fig, now)
    fig.update_xaxes(range=[midnight, midnight + timedelta(days=1)], tickformat="%H:%M")
    fig.update_yaxes(title="kW", rangemode="tozero")
    return fig


def metrics_panel(ctx: Context) -> html.Div:
    metrics = [m for m in ctx.forecast_metrics if m.model == PRIMARY_MODEL]
    if not metrics:
        return html.Div("No forecasts in this database (run `forecast`).", className="muted")
    period = ctx.data.forecast_period()
    hour = next((m for m in metrics if m.horizon == 4), metrics[0])
    takeaway = (f"One hour ahead the typical error is {hour.mae:,.0f} kW ({hour.wape:.1%} of "
                f"demand), {hour.skill:.0%} lower than assuming the load stays as it is.")
    rows = []
    for m in metrics:
        horizon = ("24 h (day-ahead)" if m.horizon >= 96
                   else f"{m.horizon // 4} h" if m.horizon >= 8 else f"{m.horizon * 15} min")
        rows.append(html.Tr([
            html.Td(horizon), html.Td(f"{m.mae:,.1f}"), html.Td(f"{m.wape:.1%}"),
            html.Td(f"{m.coverage_80:.0%}"), html.Td(f"{m.skill:+.0%}"),
            html.Td(m.baseline_name, className="muted"),
        ]))
    header = ("Horizon", "Typical error (kW)", "WAPE", "Inside 10-90% band",
              "Better than baseline", "Baseline")
    span = f"{period[0]:%b}-{period[1]:%b %Y}, out-of-sample" if period else "out-of-sample"
    return html.Div([
        html.Div(takeaway, className="callout"),
        html.Table([html.Thead(html.Tr([html.Th(h) for h in header])), html.Tbody(rows)],
                   className="data"),
        html.Div(f"Rolling-origin backtest, {span}: each month is forecast by a model that "
                 "saw only earlier months. WAPE = total absolute error / total demand.",
                 className="muted small"),
    ])


def comparison_panel(ctx: Context) -> html.Div:
    """One row per model: 1 h and 3 h errors, pinball, coverage, peak error, alarm leads."""
    metrics = ctx.forecast_metrics
    models = [m for m in MODEL_LABELS if any(x.model == m for x in metrics)]
    if len(models) < 2:
        return html.Div("Run `forecast` with all models to compare them.", className="muted")

    def pick(model: str, horizon: int) -> Any:
        return next((x for x in metrics if x.model == model and x.horizon == horizon), None)

    peaks = {p.model: p for p in ctx.peak_metrics}
    leads = ctx.alert_leads
    rows = []
    for model in models:
        h1, h3 = pick(model, 4), pick(model, 12)
        if h1 is None:
            continue
        peak = peaks.get(model)
        rows.append(html.Tr([
            html.Td([html.Strong(MODEL_LABELS[model]),
                     html.Span(" · primary", className="muted") if model == PRIMARY_MODEL else ""]),
            html.Td(f"{h1.mae:,.1f}"), html.Td(f"{h1.pinball:,.2f}"),
            html.Td(f"{h1.coverage_80:.0%}"),
            html.Td("-" if h3 is None else f"{h3.mae:,.1f}"),
            html.Td("-" if peak is None
                    else f"{peak.peak_mae:,.1f} / {peak.peak_time_error_min:.0f} min"),
            html.Td(", ".join(leads.get(model, [])) or "-"),
        ], className="primary" if model == PRIMARY_MODEL else ""))
    header = ("Model", "1 h error (kW)", "1 h pinball", "1 h in band", "3 h error (kW)",
              "3 h peak error / timing", "Alarm lead per exceedance (min)")
    best = min((r for r in metrics if r.horizon == 4), key=lambda r: r.pinball)
    profile = pick("profile", 4)
    verdict = (f"Best one-hour pinball loss: {MODEL_LABELS[best.model]}"
               + (f", {1 - best.pinball / profile.pinball:.0%} better than the weekly profile."
                  if profile else "."))
    return html.Div([
        html.Div(verdict, className="callout"),
        html.Table([html.Thead(html.Tr([html.Th(h) for h in header])), html.Tbody(rows)],
                   className="data"),
        html.Div("Pinball loss is the standard score for quantile forecasts (lower is better). "
                 "Peak error: highest forecast over the next 3 h vs the highest actual, and the "
                 "median timing error. Alarm lead: minutes between the first alarm "
                 "(P(exceed) ≥ 50% within the hour) and each real exceedance; '-' = missed.",
                 className="muted small"),
    ])


def register(app: Dash, ctx: Context) -> None:
    @app.callback(Output("fc-model", "options"), Output("fc-model", "value"),
                  Input("url", "pathname"), State("fc-model", "value"))
    def _models(_: str | None, current: str | None) -> tuple[list[dict[str, str]], str | None]:
        available = ctx.data.models()
        options = [{"label": MODEL_LABELS.get(m, m), "value": m}
                   for m in MODEL_LABELS if m in available]
        value = current if current in available else (
            PRIMARY_MODEL if PRIMARY_MODEL in available else (available[0] if available else None)
        )
        return options, value

    @app.callback(Output("fc-next", "figure"), Output("fc-day", "figure"),
                  Output("fc-metrics", "children"), Output("fc-compare", "children"),
                  Input("clock", "data"), Input("fc-model", "value"))
    def _refresh(clock: dict[str, Any], model: str | None) -> tuple[Any, ...]:
        now = ClockState.from_store(clock).now
        chosen = model or PRIMARY_MODEL
        return (next_figure(ctx, now, chosen), day_figure(ctx, now, chosen),
                metrics_panel(ctx), comparison_panel(ctx))
