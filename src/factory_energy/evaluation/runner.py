"""Run the question set against a model configuration several times and report mean and spread."""

from __future__ import annotations

import json
import math
import os
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from factory_energy.agent.loop import Agent, AgentResult, Step
from factory_energy.evaluation.questions import CORE_CATEGORIES, EVAL_DIR, Question
from factory_energy.evaluation.score import SCORER_VERSION, score
from factory_energy.llm import LLMSettings, make_client
from factory_energy.llm.base import close
from factory_energy.tools.context import ToolContext
from factory_energy.tools.registry import ToolRegistry

CONFIGS = EVAL_DIR / "configs.yaml"
RESULTS = EVAL_DIR / "results"
HARD_RESULTS = EVAL_DIR / "results-hard"  # the X set is reported apart from the core set


@dataclass(frozen=True)
class EvalConfig:
    name: str
    description: str
    on_prem: bool
    env: dict[str, str]

    def llm_settings(self) -> LLMSettings:
        return LLMSettings.from_env({**os.environ, **self.env})


def load_configs(path: Path = CONFIGS) -> dict[str, EvalConfig]:
    with path.open(encoding="utf-8") as handle:
        rows = yaml.safe_load(handle)
    return {name: EvalConfig(name, row["description"], bool(row["on_prem"]),
                             {k: str(v) for k, v in row["env"].items()})
            for name, row in rows.items()}


def run_once(config: EvalConfig, questions: list[Question], golden: dict[str, float],
             registry: ToolRegistry, ctx: ToolContext, max_steps: int = 8,
             progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    rows = []
    for question in questions:
        client = make_client(config.llm_settings())
        agent = Agent(client, registry, ctx, max_steps=max_steps)
        try:
            result = agent.run(question.question)
        finally:
            close(client)
        graded = score(question, result, golden)
        rows.append({**graded.as_dict(), "answer": result.answer,
                     "tools_called": result.tools_called, "run_id": result.run_id,
                     "citations_valid": result.citations_valid,
                     "citations_invalid": result.citations_invalid,
                     "citations_repaired": result.citations_repaired,
                     "tool_steps": [[s.name, s.ok] for s in result.steps if s.kind == "tool"],
                     "model": result.model})
        if progress:
            mark = "PASS" if graded.success else "fail"
            progress(f"{question.id} {mark} {graded.latency_s:5.1f}s "
                     f"{'; '.join(graded.reasons)[:100]}")
    return rows


def undo_repairs(row: dict[str, Any]) -> dict[str, Any]:
    """A copy of a saved row as if the citation resolver had not helped: each repaired
    "X -> Y" loses one valid Y and gains an invalid X."""
    valid, invalid = list(row["citations_valid"]), list(row["citations_invalid"])
    for entry in row.get("citations_repaired", []):
        written, _, fixed = entry.partition(" -> ")
        if fixed in valid:
            valid.remove(fixed)
        invalid.append(written)
    return {**row, "citations_valid": valid, "citations_invalid": invalid}


def rescore(rows: list[dict[str, Any]], questions: list[Question],
            golden: dict[str, float], without_repairs: bool = False) -> list[dict[str, Any]]:
    """Grade saved answers again (after a scorer or question fix) without calling the model.
    ``without_repairs`` grades them as if no citation had been resolved."""
    by_id = {q.id: q for q in questions}
    fresh = []
    for row in (undo_repairs(r) for r in rows) if without_repairs else rows:
        result = AgentResult(
            by_id[row["question_id"]].question, row["answer"], "", row.get("model", ""),
            row.get("run_id", ""), datetime.now(), row["stop_reason"],
            [Step("tool", name, 0.0, 0.0, bool(ok)) for name, ok in row["tool_steps"]],
            list(row["citations_valid"]), list(row["citations_invalid"]),
            list(row["tools_called"]), int(row["prompt_tokens"]),
            int(row["completion_tokens"]), float(row["latency_s"]))
        graded = score(by_id[row["question_id"]], result, golden).as_dict()
        graded["tool_calls"] = row["tool_calls"]
        if ("success" in row and "success_v1" not in row
                and row.get("scorer_version", "1") == "1"):
            graded["success_v1"] = row["success"]  # the frozen v1 verdict is never lost
        fresh.append({**row, **graded})
    mark_sources(fresh, questions)
    return fresh


def save_run(config: EvalConfig, rows: list[dict[str, Any]], index: int,
             root: Path = RESULTS) -> Path:
    folder = root / config.name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"run-{index}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return path


def load_runs(config_name: str, root: Path = RESULTS) -> list[list[dict[str, Any]]]:
    folder = root / config_name
    return [[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            for path in sorted(folder.glob("run-*.jsonl"))]


def run_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    """One run's metrics; rates are shares of the questions they apply to."""
    def rate(items: list[bool]) -> float:
        return sum(items) / len(items) if items else float("nan")

    precisions = [r["citation_precision"] for r in rows if r["citation_precision"] is not None]
    with_sources = [r for r in rows if r.get("expects_sources", True)]
    latencies = sorted(r["latency_s"] for r in rows)
    metrics = {
        "success": rate([r["success"] for r in rows]),
        "accuracy": rate([r["correct"] for r in rows]),
        "tools": rate([r["tools_ok"] for r in rows]),
        "sources": rate([r["sources_ok"] for r in with_sources]),
        "citation_precision": statistics.fmean(precisions) if precisions else float("nan"),
        "median_latency_s": statistics.median(latencies),
        # Nearest-rank p95: with 25 questions this is the second slowest answer.
        "p95_latency_s": latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)],
        "tokens_in": statistics.fmean(r["prompt_tokens"] for r in rows),
        "tokens_out": statistics.fmean(r["completion_tokens"] for r in rows),
        "tool_calls": statistics.fmean(r["tool_calls"] for r in rows),
        # Citations the checker had to resolve (file without folder, heading without file...);
        # runs saved before the resolver existed have none recorded.
        "repaired": statistics.fmean(len(r.get("citations_repaired", [])) for r in rows),
    }
    for category in dict.fromkeys(r["category"] for r in rows):
        metrics[f"success_{category}"] = rate([r["success"] for r in rows
                                               if r["category"] == category])
    return metrics


def aggregate(runs: list[list[dict[str, Any]]]) -> dict[str, tuple[float, float]]:
    """Mean and sample standard deviation of every metric across runs."""
    per_run = [run_metrics(rows) for rows in runs]
    out = {}
    for key in per_run[0]:
        values = [m[key] for m in per_run if key in m]
        spread = statistics.stdev(values) if len(values) > 1 else 0.0
        out[key] = (statistics.fmean(values), spread)
    return out


def _pct(value: tuple[float, float]) -> str:
    mean, spread = value
    return f"{mean:.0%} ± {spread:.0%}"


def _num(value: tuple[float, float], digits: int = 1) -> str:
    mean, spread = value
    return f"{mean:,.{digits}f} ± {spread:,.{digits}f}"


def _v1_note(all_runs: dict[str, list[list[dict[str, Any]]]]) -> list[str]:
    """A line comparing task success with the v1 verdicts kept by ``rescore``."""
    changed = []
    seen = False
    for name, runs in all_runs.items():
        rows = [r for run in runs for r in run if "success_v1" in r]
        seen = seen or bool(rows)
        if any(r["success_v1"] != r["success"] for r in rows):
            v1 = statistics.fmean(sum(r.get("success_v1", r["success"]) for r in run) / len(run)
                                  for run in runs)
            v2 = statistics.fmean(sum(r["success"] for r in run) / len(run) for run in runs)
            changed.append(f"{name} {v1:.0%} -> {v2:.0%}")
    if changed:
        return ["", f"Task success changed between scorer v1 and v{SCORER_VERSION}: "
                + "; ".join(changed) + "."]
    if seen:
        return ["", f"Task success unchanged under scorer v{SCORER_VERSION} "
                "(v1 verdicts kept as `success_v1`)."]
    return []


def summary_markdown(configs: dict[str, EvalConfig], root: Path = RESULTS,
                     categories: tuple[str, ...] = CORE_CATEGORIES,
                     title: str = "Evaluation results") -> str:
    present = [c for c in configs.values() if (root / c.name).exists() and load_runs(c.name, root)]
    all_runs = {c.name: load_runs(c.name, root) for c in present}
    versions = sorted({str(r.get("scorer_version", "1"))
                       for runs in all_runs.values() for rows in runs for r in rows})
    lines = [
        f"# {title}", "",
        f"Scorer version: {', '.join(versions) or SCORER_VERSION} (see CHANGELOG).", "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}. All data is synthetic. Each configuration "
        "answers the same questions in several independent runs; values are mean ± sample "
        "standard deviation across runs. Golden answers are computed from the database "
        "(`eval/golden.json`).", "",
        "| Configuration | On-prem | Runs | Questions | Task success | Answer accuracy | "
        "Tool use | Expected source cited | Citation precision | Median latency (s) | "
        "p95 latency (s) | Tool calls per question | Tokens in / out per question | "
        "Citations repaired per question |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for config in present:
        runs = load_runs(config.name, root)
        agg = aggregate(runs)
        lines.append(
            f"| {config.name} | {'yes' if config.on_prem else '**no (stand-in)**'} | {len(runs)} "
            f"| {len(runs[0])} | {_pct(agg['success'])} | {_pct(agg['accuracy'])} | "
            f"{_pct(agg['tools'])} | {_pct(agg['sources'])} | "
            f"{_pct(agg['citation_precision'])} | {_num(agg['median_latency_s'])} | "
            f"{_num(agg['p95_latency_s'])} | {_num(agg['tool_calls'])} | "
            f"{agg['tokens_in'][0]:,.0f} / {agg['tokens_out'][0]:,.0f} | "
            f"{agg['repaired'][0]:.2f} |")
    lines += _v1_note(all_runs)
    lines += ["", "## Task success by category", "",
              "| Configuration | " + " | ".join(categories) + " |",
              "|---|" + "---|" * len(categories)]
    for config in present:
        agg = aggregate(load_runs(config.name, root))
        cells = [_pct(agg[f"success_{c}"]) if f"success_{c}" in agg else "-" for c in categories]
        lines.append(f"| {config.name} | " + " | ".join(cells) + " |")
    lines += ["", "## Per question (passes / runs)", ""]
    for config in present:
        runs = load_runs(config.name, root)
        counts: dict[str, int] = {}
        reasons: dict[str, str] = {}
        for rows in runs:
            for row in rows:
                counts[row["question_id"]] = counts.get(row["question_id"], 0) + int(row["success"])
                if not row["success"] and row["question_id"] not in reasons:
                    reasons[row["question_id"]] = "; ".join(row["reasons"])
        passes = ", ".join(f"{q} {n}/{len(runs)}" for q, n in counts.items())
        lines += [f"**{config.name}** ({config.description}): {passes}", ""]
        for qid, why in reasons.items():
            lines.append(f"- {qid}: {why}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def mark_sources(rows: list[dict[str, Any]], questions: list[Question]) -> None:
    """Record whether each question expects a source, so the source rate uses only those."""
    expects = {q.id: bool(q.sources) for q in questions}
    for row in rows:
        row["expects_sources"] = expects.get(row["question_id"], False)


def evaluate(config: EvalConfig, questions: list[Question], golden: dict[str, float],
             registry: ToolRegistry, ctx: ToolContext, repeat: int,
             progress: Callable[[str], None] | None = None, root: Path = RESULTS,
             max_steps: int = 8) -> list[list[dict[str, Any]]]:
    """Run `repeat` independent passes; earlier result files of this configuration are replaced."""
    folder = root / config.name
    for old in folder.glob("run-*.jsonl") if folder.exists() else []:
        old.unlink()
    runs: list[list[dict[str, Any]]] = []
    for index in range(1, repeat + 1):
        if progress:
            progress(f"== {config.name} run {index}/{repeat}")
        rows = run_once(config, questions, golden, registry, ctx, max_steps, progress)
        mark_sources(rows, questions)
        save_run(config, rows, index, root)
        runs.append(rows)
    return runs
