"""Single-line diagram: utility supply -> main bus -> six distribution boards -> loads.

Rendered as an SVG string from the current tick state, so it needs no charting library and
costs almost nothing per tick. Line colour follows the loading of each board; load boxes
follow their running state and light up red when a detection is open on them.
"""

from __future__ import annotations

from base64 import b64encode
from html import escape

import pandas as pd

from factory_energy.dashboard import theme
from factory_energy.dashboard.context import Context
from factory_energy.dashboard.status import TickState
from factory_energy.dashboard.widgets import equipment_status

WIDTH = 1180
BOARD_W, BOARD_H = 176, 46
LOAD_W, LOAD_H = 66, 34
TOP = 24


def _tone(ratio: float, warn: float) -> str:
    if ratio >= 1.0:
        return theme.BAD
    return theme.WARN if ratio >= warn else theme.ACCENT


def render(ctx: Context, state: TickState, alerting: set[str]) -> str:
    meters = ctx.data.meters
    feeders = ctx.data.feeder_ids
    warn = ctx.settings.demand.warning_ratio
    columns = len(feeders)
    gap = WIDTH / columns
    plant_ratio = state.plant_kw / ctx.contract_kw
    plant_color = _tone(plant_ratio, warn)
    bus_y = TOP + 92
    board_y = bus_y + 46
    load_y0 = board_y + BOARD_H + 40
    max_loads = max(int((meters.feeder_id == f).sum()) for f in feeders)
    height = load_y0 + max_loads * (LOAD_H + 10) + 10
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
        f'width="100%" font-family="Segoe UI, Inter, sans-serif" font-size="12">',
        '<style>.l{fill:#e6edf7}.m{fill:#8b9ab3}.b{font-weight:700}</style>',
        # Utility supply and main incomer.
        f'<rect x="{WIDTH / 2 - 95}" y="{TOP}" width="190" height="40" rx="8" '
        f'fill="#172238" stroke="{plant_color}" stroke-width="2"/>',
        f'<text x="{WIDTH / 2}" y="{TOP + 17}" text-anchor="middle" class="l b">'
        f'Utility supply · {state.plant_kw:,.0f} kW</text>',
        f'<text x="{WIDTH / 2}" y="{TOP + 32}" text-anchor="middle" class="m">'
        f'contract {ctx.contract_kw:,.0f} kW · {plant_ratio:.0%}</text>',
        f'<line x1="{WIDTH / 2}" y1="{TOP + 40}" x2="{WIDTH / 2}" y2="{bus_y}" '
        f'stroke="{plant_color}" stroke-width="3"/>',
        # Main bus.
        f'<line x1="{gap / 2}" y1="{bus_y}" x2="{WIDTH - gap / 2}" y2="{bus_y}" '
        f'stroke="{plant_color}" stroke-width="4"/>',
    ]
    for index, feeder in enumerate(feeders):
        cx = gap * index + gap / 2
        kw = float(state.snapshot.kw.get(feeder, 0.0) or 0.0)
        kw = 0.0 if pd.isna(kw) else kw
        pf = state.snapshot.pf.get(feeder)
        rated = float(meters.at[feeder, "rated_kw"])
        color = theme.BAD if feeder in alerting else _tone(kw / rated, warn)
        width = 1.5 + 4 * min(kw / rated, 1.0)
        parts += [
            f'<line x1="{cx}" y1="{bus_y}" x2="{cx}" y2="{board_y}" stroke="{color}" '
            f'stroke-width="{width:.1f}"/>',
            f'<rect x="{cx - BOARD_W / 2}" y="{board_y}" width="{BOARD_W}" height="{BOARD_H}" '
            f'rx="8" fill="#121a2b" stroke="{color}" stroke-width="2"/>',
            f'<text x="{cx}" y="{board_y + 18}" text-anchor="middle" class="l b">'
            f'{escape(feeder)} · {kw:,.0f} kW</text>',
            f'<text x="{cx}" y="{board_y + 35}" text-anchor="middle" class="m" font-size="11">'
            f'{escape(ctx.data.name(feeder))}'
            + (f" · PF {pf:.2f}" if pf is not None and not pd.isna(pf) else "") + "</text>",
        ]
        loads = list(meters.index[meters.feeder_id == feeder])
        parts.append(f'<line x1="{cx}" y1="{board_y + BOARD_H}" x2="{cx}" '
                     f'y2="{load_y0 + (len(loads) - 1) * (LOAD_H + 10) + LOAD_H / 2}" '
                     f'stroke="#24314d" stroke-width="2"/>')
        for row, meter in enumerate(loads):
            y = load_y0 + row * (LOAD_H + 10)
            load_kw = float(state.snapshot.kw.get(meter, 0.0) or 0.0)
            load_kw = 0.0 if pd.isna(load_kw) else load_kw
            load_rated = float(meters.at[meter, "rated_kw"])
            status = "ALERT" if meter in alerting else equipment_status(load_kw, load_rated)
            stroke = {"ALERT": theme.BAD, "RUNNING": theme.OK, "IDLE": theme.WARN,
                      "OFF": "#3b4a66"}[status]
            stroke_width = 2 if status == "ALERT" else 1.2
            parts += [
                f'<line x1="{cx}" y1="{y + LOAD_H / 2}" x2="{cx + 18}" y2="{y + LOAD_H / 2}" '
                f'stroke="#24314d" stroke-width="2"/>',
                f'<rect x="{cx + 18}" y="{y}" width="{LOAD_W}" height="{LOAD_H}" rx="6" '
                f'fill="#121a2b" stroke="{stroke}" stroke-width="{stroke_width}"/>',
                f'<text x="{cx + 18 + LOAD_W / 2}" y="{y + 14}" text-anchor="middle" class="l b" '
                f'font-size="11">{escape(meter)}</text>',
                f'<text x="{cx + 18 + LOAD_W / 2}" y="{y + 28}" text-anchor="middle" class="m" '
                f'font-size="11">{load_kw:,.0f} kW</text>',
            ]
    parts.append("</svg>")
    return "".join(parts)


def data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + b64encode(svg.encode("utf-8")).decode("ascii")
