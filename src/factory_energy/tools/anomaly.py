"""Anomaly tools: stored detections, and the detectors run on demand over a window."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal

import pandas as pd
from pydantic import Field

from factory_energy.anomaly.data import load_plant_data
from factory_energy.anomaly.service import detect_all
from factory_energy.energy.impact import impact_text
from factory_energy.tools.context import ToolContext, Window, iso, num
from factory_energy.tools.registry import Tool

HISTORY = timedelta(days=14)  # rules and baselines compare against the preceding fortnight
MAX_ROWS = 50


class ListArgs(Window):
    layer: Literal["RULE", "BASELINE", "ML", "ANY"] = Field(
        default="ANY", description="Detector layer filter")


class DetectArgs(Window):
    include_ml: bool = Field(default=False, description="Also run the slow IsolationForest layer")


def _row(ctx: ToolContext, event_type: str, score: float, start: Any) -> str:
    when = pd.Timestamp(start).to_pydatetime()
    return impact_text(event_type, score, when, ctx.contract_kw, ctx.settings.tariff)


def list_detections(ctx: ToolContext, args: ListArgs) -> dict[str, Any]:
    layer = "" if args.layer == "ANY" else "AND layer = ?"
    params: tuple[Any, ...] = (args.end, args.start)
    if args.layer != "ANY":
        params += (args.layer,)
    if ctx.as_of is not None:
        layer += " AND detected_ts <= ?"
        params += (ctx.as_of,)
    frame = ctx.query(
        "SELECT layer, detector, event_type, meter_ids, start_ts, end_ts, detected_ts, severity, "
        f"score, message FROM detections WHERE start_ts < ? AND end_ts > ? {layer} "
        "ORDER BY start_ts", params)
    return {
        "count": int(len(frame)),
        "detections": [
            {"layer": r.layer, "event_type": r.event_type, "meters": list(r.meter_ids),
             "start": iso(r.start_ts), "end": iso(r.end_ts), "detected_at": iso(r.detected_ts),
             "severity": r.severity, "message": r.message,
             "impact": _row(ctx, r.event_type, float(r.score), r.start_ts)}
            for r in frame.head(MAX_ROWS).itertuples()
        ],
        "truncated": len(frame) > MAX_ROWS,
    }


def detect_anomalies(ctx: ToolContext, args: DetectArgs) -> dict[str, Any]:
    data = load_plant_data(ctx.connection(), ctx.contract_kw,
                           ctx.settings.demand.interval_minutes, args.start - HISTORY, args.end)
    if data.kw.empty:
        raise LookupError("no readings in this window")
    found = [d for d in detect_all(data, use_ml=args.include_ml)
             if d.start < args.end and d.end > args.start
             and (ctx.as_of is None or d.seen_at <= ctx.as_of)]
    return {
        "window_analysed_from": iso(args.start - HISTORY),
        "count": len(found),
        "detections": [
            {"layer": d.layer.value, "detector": d.detector, "event_type": d.event_type,
             "meters": list(d.meter_ids), "start": iso(d.start), "end": iso(d.end),
             "detected_at": iso(d.seen_at), "severity": d.severity, "score": num(d.score, 3),
             "message": d.message, "impact": _row(ctx, d.event_type, d.score, d.start)}
            for d in found[:MAX_ROWS]
        ],
    }


TOOLS = [
    Tool("list_detections",
         "Detections already recorded by the monitoring system (rules, night-load baseline, ML "
         "hints) overlapping a window, with severity, message and money/energy impact.",
         ListArgs, "read", list_detections),
    Tool("detect_anomalies",
         "Run the anomaly detectors now over a window (max 31 days; the preceding 14 days are "
         "used as history): simultaneous start, off-schedule running, low power factor, demand "
         "above contract, compressed-air leak drift; optional ML layer.",
         DetectArgs, "read", detect_anomalies),
]
