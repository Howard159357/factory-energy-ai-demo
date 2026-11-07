from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from factory_energy import __version__
from factory_energy.config.loader import load_meters, load_settings

if TYPE_CHECKING:
    from factory_energy.rag.store import KnowledgeStore


def _check_config() -> int:
    settings = load_settings()
    catalog = load_meters()
    categories = Counter(item.category for item in catalog.equipment)
    print(f"{settings.plant.name} (fictional demo plant)")
    print("Configuration: PASS")
    print(f"Feeders (plant total): {len(catalog.feeder_ids)}")
    print(f"Equipment sub-meters:  {len(catalog.equipment)}")
    for feeder in catalog.feeders:
        names = ", ".join(e.meter_id for e in catalog.equipment_on(feeder.meter_id))
        print(f"  {feeder.meter_id:<6} {feeder.name:<22} {names}")
    print(f"Equipment categories:  {len(categories)}")
    print(f"Contract capacity:     {settings.demand.contract_capacity_kw:,.0f} kW")
    print(f"Demand interval:       {settings.demand.interval_minutes} min")
    print(f"Timezone:              {settings.plant.timezone}")
    return 0


def _simulate(args: argparse.Namespace) -> int:
    from factory_energy.simulator.generator import SimulationConfig, run_simulation
    from factory_energy.simulator.scenarios import load_scenarios
    from factory_energy.storage.connection import open_local

    out = Path(args.out)
    if out.exists():
        if not args.force:
            print(f"{out} already exists; pass --force to replace it", file=sys.stderr)
            return 2
        out.unlink()
        Path(f"{out}.wal").unlink(missing_ok=True)
    available = {scenario.id: scenario for scenario in load_scenarios()}
    if args.scenarios == "all":
        chosen = list(available.values())
    elif args.scenarios == "none":
        chosen = []
    else:
        wanted = [item.strip() for item in args.scenarios.split(",")]
        missing = [item for item in wanted if item not in available]
        if missing:
            print(f"unknown scenario(s): {', '.join(missing)}", file=sys.stderr)
            return 2
        chosen = [available[item] for item in wanted]
    config = SimulationConfig(args.start, args.days, args.seed, tuple(chosen))

    def progress(meter_id: str, done: int, total: int) -> None:
        print(f"\r  [{done:>2}/{total}] {meter_id:<8}", end="", flush=True)

    print(f"Simulating {config.days} days from {config.start} (seed {config.seed}) -> {out}")
    with open_local(out) as connection:
        summary = run_simulation(connection, config, load_settings(), load_meters(), progress)
    print()
    print(f"Rows written:        {summary.rows:,} ({summary.meters} meters)")
    print(
        f"Peak 15-min demand:  {summary.peak_demand_kw:,.0f} kW "
        f"at {summary.peak_demand_start:%Y-%m-%d %H:%M}"
    )
    print(f"Night base load:     {summary.night_base_kw:,.0f} kW (median 02:00-04:00)")
    print(f"Plant energy:        {summary.plant_mwh:,.1f} MWh")
    print(f"Scenarios:           {', '.join(s.id for s in chosen) or 'none'}")
    print(f"Labelled events:     {summary.labelled_events} "
          f"(+{summary.exceedance_intervals} demand-exceedance intervals)")
    print(f"Elapsed:             {summary.elapsed_seconds:,.1f} s")
    return 0


def _detect(args: argparse.Namespace) -> int:
    from factory_energy.anomaly.service import run_detection
    from factory_energy.storage.connection import open_local

    if not Path(args.db).exists():
        print(f"{args.db} not found; run `simulate` first", file=sys.stderr)
        return 2
    with open_local(args.db) as connection:
        detections, scores = run_detection(connection, load_settings(), use_ml=not args.no_ml)
    print(f"Detections written: {len(detections)} (table `detections` in {args.db})")
    print()
    print(f"{'':<22}{'detections':>11}{'precision':>11}{'labels':>8}{'recall':>8}"
          f"{'median delay':>15}")
    for row in scores:
        precision = "-" if row.precision is None else f"{row.precision:.0%}"
        recall = "-" if row.recall is None else f"{row.recall:.0%}"
        delay = "-" if row.median_delay is None else str(row.median_delay)
        print(f"{row.name:<22}{row.detections:>11}{precision:>11}{row.labels:>8}"
              f"{recall:>8}{delay:>15}")
    return 0


def _forecast(args: argparse.Namespace) -> int:
    from factory_energy.forecasting.model import MODELS
    from factory_energy.forecasting.service import run_forecasting
    from factory_energy.storage.connection import open_local

    if not Path(args.db).exists():
        print(f"{args.db} not found; run `simulate` first", file=sys.stderr)
        return 2
    models = MODELS if args.models == "all" else tuple(args.models.split(","))
    unknown = [m for m in models if m not in MODELS]
    if unknown:
        print(f"unknown model(s): {', '.join(unknown)}; choose from {', '.join(MODELS)}",
              file=sys.stderr)
        return 2

    def progress(message: str) -> None:
        print(f"  {message}", flush=True)

    with open_local(args.db) as connection:
        report = run_forecasting(connection, load_settings(), progress, models,
                                 refresh=args.refresh, workers=args.workers)
    print(f"\nBacktest runs: {report.units_total} ({report.units_reused} reused from cache)")
    print("\nRolling-origin backtest (out-of-sample, Jun-Dec); MAE and pinball loss in kW")
    print(f"{'model':<10}{'horizon':>8}{'MAE':>8}{'WAPE':>7}{'pinball':>9}{'cover':>7}"
          f"{'baseline':>10}{'skill':>7}")
    for m in sorted(report.metrics, key=lambda x: (x.horizon, x.mae)):
        print(f"{m.model:<10}{m.horizon * 15:>5}min{m.mae:>8.1f}{m.wape:>7.1%}"
              f"{m.pinball:>9.2f}{m.coverage_80:>7.0%}{m.baseline_mae:>10.1f}{m.skill:>7.0%}")
    print("\nNext-3-hour peak (highest P50 over 15 min-3 h vs highest actual)")
    print(f"{'model':<10}{'issues':>8}{'peak MAE':>10}{'bias':>8}{'time err':>10}")
    for pk in sorted(report.peaks, key=lambda x: x.peak_mae):
        print(f"{pk.model:<10}{pk.issues:>8}{pk.peak_mae:>10.1f}{pk.peak_bias:>+8.1f}"
              f"{pk.peak_time_error_min:>8.0f}min")
    print(f"\nDemand-exceedance alerts (next-hour forecast), primary model: {report.primary}")
    for level, (episodes, false_alarms) in report.alerts[report.primary].items():
        print(f"  {level}: false-alarm hours {false_alarms}")
        for e in episodes:
            minutes = None if e.lead is None else e.lead.total_seconds() / 60
            lead = "missed" if minutes is None else f"{minutes:.0f} min ahead"
            print(f"    {e.start:%Y-%m-%d %H:%M}-{e.end:%H:%M}  peak {e.peak_kw:,.0f} kW  {lead}")
    print("\nAlarm lead by model (minutes ahead per episode; '-' = missed)")
    for model, levels in report.alerts.items():
        episodes, false_alarms = levels["alarm"]
        leads = ["-" if e.lead is None else f"{e.lead.total_seconds() / 60:.0f}" for e in episodes]
        print(f"  {model:<10} {' '.join(leads):<30} false-alarm hours {false_alarms}")
    return 0


def _dashboard(args: argparse.Namespace) -> int:
    from factory_energy.dashboard.app import create_app

    if not Path(args.db).exists():
        print(f"{args.db} not found; run `build-demo` first", file=sys.stderr)
        return 2
    app = create_app(args.db, load_settings(), load_meters())
    print(f"Dashboard: http://127.0.0.1:{args.port}  (synthetic demo data, local only)")
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


def _build_demo(args: argparse.Namespace) -> int:
    """Simulate the default year, then run detection and the forecast backtest."""
    steps = [
        ["simulate", "--out", args.db, "--force"],
        ["detect", "--db", args.db],
        ["forecast", "--db", args.db],
    ]
    for step in steps:
        print()
        print(f"== {' '.join(step)}")
        code = main(step)
        if code:
            return code
    return 0


def _rag_store(rebuild: bool = False) -> KnowledgeStore:
    from factory_energy.rag.embed import embedder_from
    from factory_energy.rag.settings import RagSettings
    from factory_energy.rag.store import KnowledgeStore, drop_collection, open_client

    settings = RagSettings.from_env()
    embedder = embedder_from(settings)
    client = open_client(settings)
    if rebuild:
        drop_collection(client, settings.collection)
    return KnowledgeStore(client, embedder, settings.collection)


def _rag(args: argparse.Namespace) -> int:
    from factory_energy.rag.ingest import discover, ingest

    try:
        store = _rag_store(rebuild=getattr(args, "rebuild", False))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if args.rag_command == "ingest":
        report = ingest(store, discover())
        print(f"Embedder: {store.embedder.name}  collection: {store.collection_name}")
        print(f"Added {len(report.added)}, updated {len(report.updated)}, "
              f"unchanged {len(report.unchanged)}, removed {len(report.removed)} documents; "
              f"{report.chunks} chunks embedded; {store.count()} chunks in the index")
        return 0
    try:
        passages = store.search(args.query, k=args.k)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if not passages:
        print("No passages (is the index empty? run `rag ingest`)")
    for rank, passage in enumerate(passages, 1):
        print(f"\n[{rank}] {passage.score:.3f}  {passage.citation}")
        snippet = " ".join(passage.text.split())
        print(f"    {snippet[:300]}{'...' if len(snippet) > 300 else ''}")
    return 0


def _load_env() -> None:
    """Read the repository's .env, if any; variables already set in the shell win."""
    from dotenv import load_dotenv

    from factory_energy.paths import ROOT

    load_dotenv(ROOT / ".env", override=False)


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(prog="factory-energy", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-config", help="validate config/factory.yaml and config/meters.yaml")
    sim = commands.add_parser("simulate", help="generate synthetic plant data into DuckDB")
    sim.add_argument("--start", type=date.fromisoformat, default=date(2025, 1, 1))
    sim.add_argument("--days", type=int, default=365)
    sim.add_argument("--seed", type=int, default=42)
    sim.add_argument("--out", default="data/plant.duckdb")
    sim.add_argument("--force", action="store_true", help="replace an existing database file")
    sim.add_argument(
        "--scenarios", default="all", help="'all', 'none' or a comma list such as S2,S3"
    )
    detect = commands.add_parser("detect", help="run anomaly detection and score it")
    detect.add_argument("--db", default="data/plant.duckdb")
    detect.add_argument("--no-ml", action="store_true", help="skip the IsolationForest layer")
    forecast = commands.add_parser("forecast", help="backtest demand forecasts and alerts")
    forecast.add_argument("--db", default="data/plant.duckdb")
    forecast.add_argument("--models", default="all",
                          help="'all' or a comma list: profile,linear,hgb,lightgbm,ensemble")
    forecast.add_argument("--refresh", action="store_true", help="ignore cached backtest runs")
    forecast.add_argument("--workers", type=int, default=4, help="parallel processes")
    board = commands.add_parser("dashboard", help="run the local Dash command center")
    board.add_argument("--db", default="data/plant.duckdb")
    board.add_argument("--port", type=int, default=8731)
    build = commands.add_parser("build-demo", help="simulate, detect and forecast in one go")
    build.add_argument("--db", default="data/plant.duckdb")
    rag = commands.add_parser("rag", help="knowledge base: ingest documents, query passages")
    rag_commands = rag.add_subparsers(dest="rag_command", required=True)
    rag_ingest = rag_commands.add_parser("ingest", help="index docs/knowledge and project docs")
    rag_ingest.add_argument("--rebuild", action="store_true", help="drop the index first")
    rag_query = rag_commands.add_parser("query", help="search the knowledge base")
    rag_query.add_argument("query")
    rag_query.add_argument("-k", type=int, default=5, help="passages to return (1-20)")
    from factory_energy import cli_agent, cli_eval

    cli_agent.add_parsers(commands)
    cli_eval.add_parsers(commands)
    args = parser.parse_args(argv)
    if args.command == "check-config":
        return _check_config()
    if args.command == "simulate":
        return _simulate(args)
    if args.command == "detect":
        return _detect(args)
    if args.command == "forecast":
        return _forecast(args)
    if args.command == "dashboard":
        return _dashboard(args)
    if args.command == "build-demo":
        return _build_demo(args)
    if args.command == "rag":
        return _rag(args)
    if args.command in ("agent", "mcp", "api"):
        return cli_agent.run(args)
    if args.command == "eval":
        return cli_eval.run(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
