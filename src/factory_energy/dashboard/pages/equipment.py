from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from dash import Dash, Input, Output, html

from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.status import TickState
from factory_energy.dashboard.widgets import equipment_status, event_label

PATH = "/equipment"
TITLE = "Equipment"


def layout() -> html.Div:
    return html.Div([
        html.Div([html.H2("Equipment", className="page-title"),
                  html.P("Sub-metered loads grouped by distribution board. Red cards have an "
                         "open detection.", className="page-sub")]),
        html.Div(id="eq-grid"),
    ], className="main-inner")


def open_detections(state: TickState) -> dict[str, str]:
    """meter -> reason, for detections that are still open (or closed within the hour)."""
    rows = state.detections_24h
    active = rows[(rows.end_ts >= state.now - timedelta(hours=1)) & (rows.layer != "ML")]
    reasons: dict[str, str] = {}
    for row in active.itertuples():
        for meter in row.meter_ids:
            reasons.setdefault(meter, event_label(row.event_type))
    return reasons


def cards(ctx: Context, now: datetime) -> list[html.Div]:
    state = ctx.tick(now)
    reasons = open_detections(state)
    energy = ctx.data.meter_energy(now.replace(minute=0) - timedelta(hours=24),
                                   now.replace(minute=0))
    meters = ctx.data.meters
    sections: list[html.Div] = []
    for feeder in ctx.data.feeder_ids:
        tiles = []
        for meter in meters.index[meters.feeder_id == feeder]:
            rated = float(meters.at[meter, "rated_kw"])
            kw = float(state.snapshot.kw.get(meter, 0.0) or 0.0)
            kw = 0.0 if pd.isna(kw) else kw
            alerting = meter in reasons
            status = "ALERT" if alerting else equipment_status(kw, rated)
            share = min(kw / rated, 1.0) if rated else 0.0
            tiles.append((alerting, html.Div([
                html.Div([html.Span(meter, className="equip-id"),
                          html.Span(status, className=f"chip {status}")], className="equip-head"),
                html.Div(ctx.data.name(meter), className="equip-name"),
                html.Div(f"{kw:,.1f} kW", className="equip-kw"),
                html.Div(html.Div(className=f"bar-fill {'bad' if alerting else ''}",
                                  style={"width": f"{share:.0%}"}), className="bar"),
                html.Div(reasons[meter] if alerting else
                         f"{share:.0%} of {rated:,.0f} kW · {energy.get(meter, 0):,.0f} kWh / 24 h",
                         className="equip-reason" if alerting else "equip-name"),
            ], className="equip alerting" if alerting else "equip")))
        tiles.sort(key=lambda t: not t[0])
        sections.append(html.Div([
            html.Div(f"{feeder} · {ctx.data.name(feeder)}", className="feeder-title"),
            html.Div([tile for _, tile in tiles], className="equip-grid"),
        ]))
    return sections


def register(app: Dash, ctx: Context) -> None:
    @app.callback(Output("eq-grid", "children"), Input("clock", "data"))
    def _refresh(clock: dict[str, Any]) -> list[html.Div]:
        return cards(ctx, ClockState.from_store(clock).now)
