"""Plant map: the illustration of the plant with live load and alerts anchored on it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from dash import Dash, Input, Output, html
from pydantic import BaseModel, ConfigDict, Field

from factory_energy.config.loader import CONFIG_DIR
from factory_energy.dashboard import theme
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.pages.equipment import open_detections
from factory_energy.dashboard.status import TickState
from factory_energy.dashboard.widgets import alert_items, equipment_status

PATH = "/"
TITLE = "Plant map"
HOT_DAY_C = 33.0


class Zone(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feeder: str
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    label_side: str = "right"


class Marker(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meter: str
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)


class MapLayout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    image: str
    zones: tuple[Zone, ...]
    equipment: tuple[Marker, ...] = ()


def load_layout(path: Path = CONFIG_DIR / "layout.yaml") -> MapLayout:
    with path.open(encoding="utf-8") as handle:
        return MapLayout.model_validate(yaml.safe_load(handle))


def layout() -> html.Div:
    plan = load_layout()
    return html.Div([
        html.Div([html.H2("Plant map", className="page-title"),
                  html.P("Live load per distribution board and a status dot per load. Red "
                         "means an open detection.", className="page-sub")]),
        html.Div(id="pm-bar"),
        html.Div([
            html.Div([
                html.Img(src=f"/assets/{plan.image}", className="map-image", draggable="false"),
                html.Div(id="pm-overlay"),
                html.Div(id="pm-mood", className="map-mood"),
            ], className="map card"),
            theme.card("Alerts", html.Div(id="pm-alerts", className="alert-list")),
        ], className="grid grid-map"),
    ], className="main-inner")


def load_bar(ctx: Context, state: TickState) -> html.Div:
    ratio = min(state.plant_kw / ctx.contract_kw, 1.2)
    tone = theme.tone_for_ratio(state.plant_kw / ctx.contract_kw,
                                ctx.settings.demand.warning_ratio)
    return html.Div([
        html.Div([
            html.Span(f"{state.plant_kw:,.0f} kW", className="bar-value"),
            html.Span(f"of {ctx.contract_kw:,.0f} kW contract · projected 15-min demand "
                      f"{state.projected_kw:,.0f} kW", className="muted"),
        ], className="bar-head"),
        html.Div([
            html.Div(className=f"load-fill {tone}", style={"width": f"{ratio / 1.2:.1%}"}),
            html.Div(className="load-contract", style={"left": f"{1 / 1.2:.1%}"}),
        ], className="load-track"),
    ], className="card load-bar")


def overlay(ctx: Context, state: TickState, plan: MapLayout) -> list[html.Div]:
    reasons = open_detections(state)
    meters = ctx.data.meters
    items: list[html.Div] = []
    for zone in plan.zones:
        if zone.feeder not in meters.index:
            continue
        kw = float(state.snapshot.kw.get(zone.feeder, 0.0) or 0.0)
        kw = 0.0 if pd.isna(kw) else kw
        rated = float(meters.at[zone.feeder, "rated_kw"])
        alerting = [
            m for m in reasons
            if m in meters.index and (m == zone.feeder or meters.at[m, "feeder_id"] == zone.feeder)
        ]
        tone = "bad" if alerting else theme.tone_for_ratio(kw / rated, 0.85)
        reason = reasons.get(alerting[0]) if alerting else None
        items.append(html.Div([
            html.Div(className=f"zone-dot {tone}"),
            html.Div([
                html.Div(f"{zone.feeder} · {ctx.data.name(zone.feeder)}", className="zone-name"),
                html.Div(f"{kw:,.0f} kW", className="zone-kw"),
                html.Div(f"{reason} · {', '.join(alerting)}" if reason else
                         f"{kw / rated:.0%} of {rated:,.0f} kW", className="zone-sub"),
            ], className=f"zone-label {zone.label_side}"),
        ], className=f"zone {tone} side-{zone.label_side}",
            style={"left": f"{zone.x}%", "top": f"{zone.y}%"}))
    items += equipment_markers(ctx, state, plan, reasons)
    return items


def equipment_markers(
    ctx: Context, state: TickState, plan: MapLayout, reasons: dict[str, str]
) -> list[html.Div]:
    """One small dot per sub-metered load; alerting loads get a chip with the reason."""
    meters = ctx.data.meters
    items: list[html.Div] = []
    for marker in plan.equipment:
        if marker.meter not in meters.index:
            continue
        kw = float(state.snapshot.kw.get(marker.meter, 0.0) or 0.0)
        kw = 0.0 if pd.isna(kw) else kw
        rated = float(meters.at[marker.meter, "rated_kw"])
        status = "ALERT" if marker.meter in reasons else equipment_status(kw, rated)
        children: list[Any] = [html.Div(className=f"eq-dot {status}")]
        if status == "ALERT":  # the reason is already on the board's label; keep chips short
            children.append(html.Div(marker.meter, className="eq-chip"))
        items.append(html.Div(
            children, className="eq",
            title=f"{marker.meter} {ctx.data.name(marker.meter)}: {kw:,.1f} kW ({status})",
            style={"left": f"{marker.x}%", "top": f"{marker.y}%"},
        ))
    return items


def mood(state: TickState) -> tuple[str, str]:
    """A tint for hot afternoons and a dim for the night, with a caption."""
    hour = state.now.hour
    if state.temperature is not None and state.temperature >= HOT_DAY_C:
        return "hot", f"{state.temperature:.0f} °C outside"
    if hour < 6 or hour >= 20:
        return "night", ""
    return "", ""


def update(ctx: Context, now: Any) -> tuple[Any, ...]:
    state = ctx.tick(now)
    plan = load_layout()
    tint, caption = mood(state)
    return (load_bar(ctx, state), overlay(ctx, state, plan),
            html.Span(caption, className=f"mood-caption {tint}") if caption else "",
            alert_items(ctx, state, limit=6))


def register(app: Dash, ctx: Context) -> None:
    @app.callback(Output("pm-bar", "children"), Output("pm-overlay", "children"),
                  Output("pm-mood", "children"), Output("pm-alerts", "children"),
                  Input("clock", "data"))
    def _refresh(clock: dict[str, Any]) -> tuple[Any, ...]:
        return update(ctx, ClockState.from_store(clock).now)
