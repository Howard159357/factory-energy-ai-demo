from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, no_update

from factory_energy.dashboard import theme
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.widgets import LAYER_NAMES, event_label, impact_text

PATH = "/anomalies"
TITLE = "Anomalies"
SCORE_NAMES = {"layer RULE": "Rules", "layer BASELINE": "Baselines", "layer ML": "ML",
               "all layers": "All layers"}


def layout() -> html.Div:
    return html.Div([
        html.Div([html.H2("Anomaly center", className="page-title"),
                  html.P("Detections from three layers: engineering rules, statistical "
                         "baselines and machine learning. Each appears at the time it would "
                         "have been raised.", className="page-sub")]),
        html.Div(id="an-kpis", className="grid grid-4"),
        html.Div([
            theme.card("Detections so far", html.Div(id="an-table")),
            theme.card("Evidence", dcc.Dropdown(id="an-select", clearable=False,
                                                placeholder="Select a detection"),
                       dcc.Graph(id="an-evidence", config={"displayModeBar": False})),
        ], className="grid grid-equal-2"),
        html.Details([
            html.Summary("Detection performance against the labelled scenarios (whole year)"),
            html.Div(id="an-score"),
        ], className="card details"),
    ], className="main-inner")


def _label(row: Any) -> str:
    return (f"{pd.Timestamp(row.detected_ts):%d %b %H:%M} · {event_label(row.event_type)} · "
            f"{', '.join(row.meter_ids)}")


def table(ctx: Context, rows: pd.DataFrame) -> html.Table:
    body = [
        html.Tr([
            html.Td(f"{pd.Timestamp(r.detected_ts):%a %d %b %H:%M}"),
            html.Td(html.Span(LAYER_NAMES.get(r.layer, r.layer), className=f"tag {r.layer}")),
            html.Td(event_label(r.event_type)),
            html.Td(", ".join(r.meter_ids)),
            html.Td(html.Span(r.severity, className=f"chip sev-{r.severity}")),
            html.Td(impact_text(ctx, pd.Series(r._asdict())), className="muted"),
        ])
        for r in rows.head(25).itertuples()
    ]
    header = ("Detected", "Layer", "What", "Loads", "Severity", "Impact")
    return html.Table(
        [html.Thead(html.Tr([html.Th(h) for h in header])),
         html.Tbody(body or [html.Tr(html.Td("Nothing detected yet.", colSpan=6))])],
        className="data",
    )


def kpis(rows: pd.DataFrame) -> list[html.Div]:
    counts = rows.layer.value_counts() if len(rows) else pd.Series(dtype=int)
    return [
        theme.kpi("Detections to date", f"{len(rows)}", "all layers"),
        theme.kpi("Rules", f"{counts.get('RULE', 0)}", "explainable engineering rules"),
        theme.kpi("Baselines", f"{counts.get('BASELINE', 0)}",
                  "slow drift in night-time base load"),
        theme.kpi("Machine learning", f"{counts.get('ML', 0)}",
                  "days whose load pattern looks unusual"),
    ]


def evidence(
    ctx: Context, rows: pd.DataFrame, detection_id: str | None, now: datetime
) -> go.Figure:
    fig = theme.figure(height=330)
    if rows.empty:
        return fig
    match = rows[rows.detection_id == detection_id]
    row = (match if len(match) else rows).iloc[0]
    start = pd.Timestamp(row.start_ts)
    end = min(pd.Timestamp(row.end_ts), pd.Timestamp(now))  # never look past the clock
    long = end - start > pd.Timedelta(days=2)
    pad = pd.Timedelta(days=7) if long else pd.Timedelta(hours=6)
    meters = [m for m in row.meter_ids if m in ctx.data.meters.index] or ctx.data.feeder_ids
    series = ctx.data.meter_series(meters, (start - pad).to_pydatetime(), now)
    if long and len(series):
        series = series.resample("1h").mean()
    for index, meter in enumerate(series.columns):
        fig.add_trace(go.Scatter(x=series.index, y=series[meter], name=meter,
                                 line={"color": theme.SERIES[index % len(theme.SERIES)],
                                       "width": 1.4}))
    fig.add_vrect(x0=start, x1=end, fillcolor=theme.BAD, opacity=0.12, line_width=0,
                  annotation_text="event", annotation_position="bottom left",
                  annotation_font_color=theme.BAD)  # bottom: the "detected" label sits at the top
    fig.add_vline(x=pd.Timestamp(row.detected_ts), line={"color": theme.WARN, "dash": "dot"},
                  annotation_text="detected", annotation_font_color=theme.WARN)
    # The message is the chart title; the legend moves below the plot so the two never overlap.
    fig.update_layout(
        title={"text": row.message, "font": {"size": 12}, "x": 0, "xanchor": "left",
               "y": 0.98, "yanchor": "top"},
        legend={"orientation": "h", "y": -0.22, "x": 0},
        margin={"l": 50, "r": 16, "t": 40, "b": 56},
    )
    fig.update_yaxes(title="kW")
    return fig


def scores(ctx: Context) -> html.Div:
    rows = []
    for s in ctx.detection_scores:
        delay = "-" if s.median_delay is None else _duration(s.median_delay)
        rows.append(html.Tr([
            html.Td(SCORE_NAMES.get(s.name, event_label(s.name))), html.Td(s.detections),
            html.Td("-" if s.precision is None else f"{s.precision:.0%}"), html.Td(s.labels),
            html.Td("-" if s.recall is None else f"{s.recall:.0%}"), html.Td(delay),
        ]))
    header = ("", "Detections", "Precision", "Labelled events", "Recall",
              "Median time to detect")
    return html.Div([
        html.Table([html.Thead(html.Tr([html.Th(h) for h in header])), html.Tbody(rows)],
                   className="data"),
        html.Div("Scored on the same synthetic plant the thresholds were tuned on: a check that "
                 "the pipeline works end to end, not evidence of real-world accuracy.",
                 className="muted small"),
    ])


def _duration(value: timedelta) -> str:
    minutes = value.total_seconds() / 60
    if minutes < 90:
        return f"{minutes:.0f} min"
    return f"{minutes / 60:.1f} h" if minutes < 48 * 60 else f"{minutes / 1440:.1f} days"


def register(app: Dash, ctx: Context) -> None:
    @app.callback(
        Output("an-kpis", "children"), Output("an-table", "children"),
        Output("an-select", "options"), Output("an-select", "value"),
        Output("an-score", "children"),
        Input("clock", "data"), State("an-select", "value"), State("an-select", "options"),
    )
    def _refresh(clock: dict[str, Any], selected: str | None,
                 current: list[dict[str, str]] | None) -> tuple[Any, ...]:
        now: datetime = ClockState.from_store(clock).now
        rows = ctx.data.detections(now)
        options = [
            {"label": _label(r), "value": r.detection_id}
            for r in rows.head(40).itertuples()
        ]
        values = {o["value"] for o in options}
        value = selected if selected in values else (options[0]["value"] if options else None)
        unchanged = options == (current or []) and value == selected
        return (kpis(rows), table(ctx, rows),
                no_update if unchanged else options, no_update if unchanged else value,
                no_update if current else scores(ctx))

    @app.callback(Output("an-evidence", "figure"), Input("an-select", "value"),
                  State("clock", "data"))
    def _evidence(selected: str | None, clock: dict[str, Any]) -> go.Figure:
        now = ClockState.from_store(clock).now
        return evidence(ctx, ctx.data.detections(now), selected, now)
