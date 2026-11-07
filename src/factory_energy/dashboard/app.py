from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from dash import Dash, Input, Output, State, dcc, html, no_update
from dash import ctx as callback_context

from factory_energy.config.models import FactorySettings, MeterCatalog
from factory_energy.dashboard import chat
from factory_energy.dashboard.clock import DEFAULT_SPEED, SPEEDS, ClockState
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.data import DashboardData
from factory_energy.dashboard.pages import (
    anomalies,
    demand,
    equipment,
    forecast,
    history,
    overview,
    plantmap,
)
from factory_energy.dashboard.widgets import banner

PAGES: list[ModuleType] = [plantmap, overview, demand, equipment, anomalies, forecast, history]
LEAD_IN = timedelta(minutes=45)  # "jump to event" lands a little before it starts


def _nav_id(page: ModuleType) -> str:
    return f"nav-{page.__name__.split('.')[-1]}"


def _top_bar(context: Context, default: ClockState) -> html.Div:
    options = [{"label": f"{s.scenario_id} · {s.title}", "value": s.scenario_id}
               for s in context.scenarios.values()]
    loads = len(context.data.equipment_ids)
    boards = len(context.data.feeder_ids)
    return html.Div([
        html.Div([
            html.Div("DemoTronics Energy Command Center", className="brand-title"),
            html.Div(f"Fictional electronics plant · {boards} distribution boards · "
                     f"{loads} sub-metered loads", className="brand-sub"),
            html.Span("SYNTHETIC DEMO DATA · SCRIPTED REPLAY", className="badge"),
        ], className="brand"),
        html.Div([html.Div(id="clock-time", className="clock-time"),
                  html.Div(id="clock-scenario", className="clock-scenario")], className="clock"),
        html.Div([
            dcc.Dropdown(id="scenario", options=options, value=default.scenario,
                         clearable=False, placeholder="No scenarios in this database",
                         style={"minWidth": "300px"}),
            html.Div([
                html.Span("speed", className="speed-label"),
                dcc.RadioItems(id="speed", options=list(SPEEDS), value=DEFAULT_SPEED,
                               inline=True, className="speed"),
            ], title="simulated minutes per second: 1, 5, 15, 60"),
            html.Button("Pause", id="play", className="btn"),
            html.Button("Jump to event", id="jump", className="btn btn-primary"),
            html.Button("Restart", id="restart", className="btn"),
        ], className="controls"),
    ], className="topbar")


def create_app(database: str | Path, settings: FactorySettings, catalog: MeterCatalog) -> Dash:
    context = Context(DashboardData(database, settings.demand.contract_capacity_kw), settings,
                      catalog)
    context.precompute()
    first = context.default_scenario()
    start, end = context.replay_window(first)
    default = ClockState(start, start, end, scenario=first)

    app = Dash(__name__, title="Energy Command Center", suppress_callback_exceptions=True,
               assets_folder=str(Path(__file__).parent / "assets"))
    app.layout = html.Div([
        dcc.Location(id="url"),
        dcc.Store(id="clock", data=default.to_store(), storage_type="session"),
        dcc.Interval(id="tick", interval=1000),
        _top_bar(context, default),
        html.Div(html.Nav([dcc.Link(p.TITLE, href=p.PATH, id=_nav_id(p)) for p in PAGES]),
                 className="nav"),
        html.Div([html.Div(id="banner"), html.Div(id="page")], className="main"),
        *chat.stores(), chat.fab(), chat.drawer(),  # outside the page, so it survives navigation
    ], className="shell")

    @app.callback(Output("page", "children"),
                  *[Output(_nav_id(p), "className") for p in PAGES],
                  Input("url", "pathname"))
    def _route(path: str | None) -> tuple[Any, ...]:
        page = next((p for p in PAGES if (path or "/") == p.PATH), plantmap)
        return (page.layout(), *["active" if p is page else "" for p in PAGES])

    @app.callback(
        Output("clock", "data"), Output("play", "children"),
        Input("tick", "n_intervals"), Input("scenario", "value"), Input("speed", "value"),
        Input("play", "n_clicks"), Input("jump", "n_clicks"), Input("restart", "n_clicks"),
        State("clock", "data"),
        prevent_initial_call=True,
    )
    def _clock(*args: Any) -> tuple[Any, Any]:
        scenario, speed, stored = args[1], args[2], args[-1]
        state = ClockState.from_store(stored)
        trigger = callback_context.triggered_id
        if trigger == "scenario":
            if scenario == state.scenario:
                return no_update, no_update
            lo, hi = context.replay_window(scenario)
            state = ClockState(lo, lo, hi, state.speed, True, scenario)
        elif trigger == "speed":
            state = state.with_speed(speed)
        elif trigger == "play":
            state = state.toggled()
        elif trigger == "jump":
            event = context.data.highlight(state.scenario or "", state.start, state.end)
            if event is not None:
                state = state.jump(event - LEAD_IN)
        elif trigger == "restart":
            state = state.restarted()
        elif not state.playing:
            return no_update, no_update  # paused or finished: nothing to redraw
        else:
            state = state.tick()
        return state.to_store(), "Pause" if state.playing else "Play"

    @app.callback(Output("scenario", "value"), Input("url", "pathname"), State("clock", "data"))
    def _sync_dropdown(_: str | None, stored: dict[str, Any]) -> str | None:
        return ClockState.from_store(stored).scenario

    @app.callback(Output("clock-time", "children"), Output("clock-scenario", "children"),
                  Output("banner", "children"), Input("clock", "data"))
    def _clock_text(stored: dict[str, Any]) -> tuple[str, str, html.Div]:
        state = ClockState.from_store(stored)
        info = context.scenarios.get(state.scenario or "")
        definition = context.scenario_definitions.get(state.scenario or "")
        # Prefer the YAML caption so wording edits show without rebuilding the database.
        caption = (definition.caption if definition and definition.caption
                   else info.caption if info else "no scenario loaded")
        status = " · paused" if not state.playing else ""
        return (f"{state.now:%a %d %b %Y  %H:%M}", f"{caption}{status}",
                banner(context.tick(state.now)))

    for page in PAGES:
        page.register(app, context)
    chat.register(app, context)
    return app
