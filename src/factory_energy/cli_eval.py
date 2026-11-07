"""CLI wiring for the evaluation: golden answers, smoke database, runs, report, retrieval."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from factory_energy.rag.settings import REPO_ROOT

SMOKE_DB = "data/eval_smoke.duckdb"


def add_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ev = commands.add_parser("eval", help="evaluate the agent on the question set")
    sub = ev.add_subparsers(dest="eval_command", required=True)
    golden = sub.add_parser("golden", help="compute golden answers from the database")
    golden.add_argument("--db", default="data/plant.duckdb")
    smoke = sub.add_parser("smoke-db", help="build the small CI database (Jun 9 - Jul 27, S2+S3)")
    smoke.add_argument("--out", default=SMOKE_DB)
    run = sub.add_parser("run", help="run one configuration from eval/configs.yaml")
    run.add_argument("--config", required=True)
    run.add_argument("--repeat", type=int, default=3)
    run.add_argument("--smoke", action="store_true", help="smoke questions only, smoke results")
    run.add_argument("--only", default="", help="comma list of question ids")
    run.add_argument("--max-steps", type=int, default=8)
    run.add_argument("--set", choices=("core", "hard"), default="core",
                     help="core: the 25 questions; hard: the 10 X questions (eval/hard/)")
    sub.add_parser("report", help="write the summaries (core and hard) from the saved runs")
    again = sub.add_parser("rescore", help="grade saved answers again without calling the model")
    again.add_argument("--config", required=True)
    again.add_argument("--set", choices=("core", "hard"), default="core")
    again.add_argument("--without-repairs", action="store_true",
                       help="write nothing; compare success as saved and with the citation "
                            "resolver's repairs undone")
    sub.add_parser("retrieval", help="hit@k and MRR of the knowledge base, no model involved")
    prof = sub.add_parser("profile", help="TTFT, decode speed and throughput at 1/2/4 users")
    prof.add_argument("--config", required=True, help="an openai_compatible entry of configs.yaml")
    prof.add_argument("--users", default="1,2,4")
    prof.add_argument("--rounds", type=int, default=3, help="requests per user per level")
    prof.add_argument("--max-tokens", type=int, default=256)
    prof.add_argument("--label", required=True,
                      help='hardware and engine for the title, e.g. "laptop / Strata / model"')
    sec = sub.add_parser("security", help="prompt-injection attacks under defence profiles")
    sec.add_argument("--config", default="attacker",
                     help="'attacker' (gullible scripted model) or a name from eval/configs.yaml")
    sec.add_argument("--profiles", default="off,quarantine,guard,on")


def run(args: argparse.Namespace) -> int:
    handlers = {"golden": _golden, "smoke-db": _smoke_db, "run": _run, "report": _report,
                "retrieval": _retrieval, "rescore": _rescore, "security": _security,
                "profile": _profile}
    return handlers[args.eval_command](args)


def _db(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _question_set(name: str) -> tuple[Path, Path]:
    """(question file, results folder) of the core or the hard set."""
    from factory_energy.evaluation.questions import HARD_QUESTIONS, QUESTIONS
    from factory_energy.evaluation.runner import HARD_RESULTS, RESULTS

    return (HARD_QUESTIONS, HARD_RESULTS) if name == "hard" else (QUESTIONS, RESULTS)


def _golden(args: argparse.Namespace) -> int:
    import duckdb

    from factory_energy.config.loader import load_meters, load_settings
    from factory_energy.evaluation import golden

    with duckdb.connect(str(_db(args.db)), read_only=True) as connection:
        values = golden.compute(connection, load_settings(), load_meters())
        golden.save(values, connection)
    for name, value in values.items():
        print(f"{name:<34} {value:,.4f}")
    print(f"-> {golden.GOLDEN}")
    return 0


def _smoke_db(args: argparse.Namespace) -> int:
    import duckdb

    from factory_energy.anomaly.service import run_detection
    from factory_energy.config.loader import load_meters, load_settings
    from factory_energy.simulator.generator import SimulationConfig, run_simulation
    from factory_energy.simulator.scenarios import load_scenarios

    out = _db(args.out)
    out.unlink(missing_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    chosen = tuple(s for s in load_scenarios() if s.id in ("S2", "S3"))
    with duckdb.connect(str(out)) as connection:
        run_simulation(connection, SimulationConfig(date(2025, 6, 9), 49, 42, chosen),
                       load_settings(), load_meters())
        run_detection(connection, load_settings(), use_ml=False)
    print(f"smoke database -> {out}")
    return 0


def _run(args: argparse.Namespace) -> int:
    import os

    import duckdb

    from factory_energy.cli_agent import tool_context
    from factory_energy.evaluation import golden
    from factory_energy.evaluation.questions import load_questions
    from factory_energy.evaluation.runner import evaluate, load_configs
    from factory_energy.tools import build_registry

    configs = load_configs()
    if args.config not in configs:
        print(f"unknown config {args.config!r}; choose from {', '.join(configs)}", file=sys.stderr)
        return 2
    if args.smoke and args.set == "hard":
        print("--smoke covers the core set only", file=sys.stderr)
        return 2
    question_file, results = _question_set(args.set)
    questions = load_questions(question_file)
    if args.smoke:
        questions = [q for q in questions if q.smoke]
    if args.only:
        wanted = {q.strip() for q in args.only.split(",")}
        questions = [q for q in questions if q.id in wanted]
    ctx = tool_context()
    with duckdb.connect(str(ctx.db_path), read_only=True) as connection:
        try:
            answers = golden.load(connection)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
    root = results.parent / "results-smoke" if args.smoke else results
    os.environ.setdefault("AGENT_ALLOW_WRITE", "0")
    evaluate(configs[args.config], questions, answers, build_registry(), ctx, args.repeat,
             progress=lambda line: print(line, flush=True), root=root, max_steps=args.max_steps)
    ctx.close()
    from factory_energy.evaluation.runner import aggregate, load_runs

    agg = aggregate(load_runs(args.config, root))
    print(f"\n{args.config}: success {agg['success'][0]:.0%} ± {agg['success'][1]:.0%}, "
          f"accuracy {agg['accuracy'][0]:.0%}, tools {agg['tools'][0]:.0%}, "
          f"median latency {agg['median_latency_s'][0]:.1f} s")
    return 0


def _rescore(args: argparse.Namespace) -> int:
    import json

    import duckdb

    from factory_energy.cli_agent import tool_context
    from factory_energy.evaluation import golden
    from factory_energy.evaluation.questions import load_questions
    from factory_energy.evaluation.runner import rescore

    question_file, results = _question_set(args.set)
    folder = results / args.config
    with duckdb.connect(str(tool_context().db_path), read_only=True) as connection:
        answers = golden.load(connection)
    questions = load_questions(question_file)
    if args.without_repairs:
        rates: list[tuple[float, float]] = []
        for path in sorted(folder.glob("run-*.jsonl")):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            kept = sum(r["success"] for r in rescore(rows, questions, answers))
            undone = sum(r["success"] for r in rescore(rows, questions, answers, True))
            print(f"{path.stem}: success as saved {kept}/{len(rows)}, "
                  f"with repairs undone {undone}/{len(rows)}")
            rates.append((kept / len(rows), undone / len(rows)))
        if not rates:
            print(f"no saved runs in {folder}", file=sys.stderr)
            return 2
        with_, without = (sum(r[i] for r in rates) / len(rates) for i in (0, 1))
        print(f"mean success: {with_:.1%} as saved, {without:.1%} with repairs undone "
              f"({(with_ - without) * 100:+.1f} points from the resolver)")
        return 0
    for path in sorted(folder.glob("run-*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        fresh = rescore(rows, questions, answers)
        lines = [json.dumps(r, ensure_ascii=False) for r in fresh]
        path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        print(f"{path.name}: {sum(r['success'] for r in fresh)}/{len(fresh)} successful")
    return 0


def _report(args: argparse.Namespace) -> int:
    from factory_energy.evaluation.questions import CORE_CATEGORIES, HARD_CATEGORIES
    from factory_energy.evaluation.runner import (
        HARD_RESULTS,
        RESULTS,
        load_configs,
        summary_markdown,
    )

    configs = load_configs()
    path = RESULTS / "summary.md"
    path.write_text(summary_markdown(configs, RESULTS, CORE_CATEGORIES), encoding="utf-8")
    print(f"-> {path}")
    if HARD_RESULTS.exists():
        hard = HARD_RESULTS / "summary.md"
        hard.write_text(summary_markdown(configs, HARD_RESULTS, HARD_CATEGORIES,
                                         "Evaluation results: hard questions (X set)"),
                        encoding="utf-8")
        print(f"-> {hard}")
    return 0


def _retrieval(args: argparse.Namespace) -> int:
    from factory_energy.cli_agent import tool_context
    from factory_energy.evaluation.questions import load_questions
    from factory_energy.evaluation.retrieval import evaluate_retrieval, metrics

    store = tool_context().store()
    results = evaluate_retrieval(store, load_questions())
    for r in results:
        print(f"{r.question_id}  rank {r.rank or '-':>2}  top: {r.top}")
    scores = metrics(results)
    print(f"\nembedder {store.embedder.name}: hit@1 {scores['hit@1']:.0%}  "
          f"hit@3 {scores['hit@3']:.0%}  hit@5 {scores['hit@5']:.0%}  MRR {scores['mrr']:.2f}  "
          f"({scores['questions']:.0f} questions)")
    return 0


def _profile(args: argparse.Namespace) -> int:
    import json

    from factory_energy.evaluation.profile import markdown, profile
    from factory_energy.evaluation.questions import EVAL_DIR
    from factory_energy.evaluation.runner import load_configs

    configs = load_configs()
    if args.config not in configs:
        print(f"unknown config {args.config!r}", file=sys.stderr)
        return 2
    settings = configs[args.config].llm_settings()
    if settings.provider != "openai_compatible" or not settings.base_url:
        print("profiling needs an openai_compatible config with LLM_BASE_URL", file=sys.stderr)
        return 2
    levels = profile(settings, tuple(int(u) for u in args.users.split(",")), args.rounds,
                     args.max_tokens, progress=lambda line: print(line, flush=True))
    folder = EVAL_DIR / "profile"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{args.config}.md").write_text(markdown(levels, args.label), encoding="utf-8")
    raw = [{"users": lv.users, "wall_s": lv.wall_s, "samples": [s.__dict__ for s in lv.samples]}
           for lv in levels]
    (folder / f"{args.config}.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
    print(f"-> {folder / (args.config + '.md')}")
    return 0


def _security(args: argparse.Namespace) -> int:
    import tempfile

    from factory_energy.cli_agent import tool_context
    from factory_energy.evaluation.attacker import CompliantAttacker
    from factory_energy.evaluation.runner import load_configs
    from factory_energy.evaluation.security import (
        PROFILES,
        build_store,
        load_attacks,
        run_attacks,
        save,
        summarise,
    )
    from factory_energy.llm import LLMClient, make_client
    from factory_energy.rag.store import persistent_client
    from factory_energy.tools import build_registry

    if args.config == "attacker":
        def make_llm() -> LLMClient:
            return CompliantAttacker()
    else:
        configs = load_configs()
        if args.config not in configs:
            print(f"unknown config {args.config!r}", file=sys.stderr)
            return 2
        settings = configs[args.config].llm_settings()

        def make_llm() -> LLMClient:
            return make_client(settings)
    profiles = [PROFILES[p.strip()] for p in args.profiles.split(",")]
    store = build_store(persistent_client(Path(tempfile.mkdtemp(prefix="security-"))))
    rows = run_attacks(make_llm, build_registry(), tool_context(), store, load_attacks(),
                       profiles, progress=lambda line: print(line, flush=True))
    path = save(args.config, rows)
    print()
    for profile, s in summarise(rows).items():
        print(f"{profile:<11} delivered {s['delivered']:.0f}  breached {s['breached']:.0f}  "
              f"interception {s['interception']:.0%}")
    print(f"-> {path}")
    return 0
