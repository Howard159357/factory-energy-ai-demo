import json
from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from factory_energy.agent.loop import AgentResult, Step
from factory_energy.config.loader import load_meters, load_settings
from factory_energy.evaluation import golden
from factory_energy.evaluation.questions import (
    HARD_CATEGORIES,
    HARD_QUESTIONS,
    Question,
    load_questions,
)
from factory_energy.evaluation.retrieval import evaluate_retrieval, metrics
from factory_energy.evaluation.runner import (
    EvalConfig,
    aggregate,
    load_runs,
    mark_sources,
    run_once,
    save_run,
    summary_markdown,
)
from factory_energy.evaluation.score import SCORER_VERSION, declines, normalise, numbers_in, score
from factory_energy.rag.settings import REPO_ROOT
from factory_energy.rag.store import KnowledgeStore
from factory_energy.tools import build_registry
from factory_energy.tools.context import ToolContext

QUESTIONS = {q.id: q for q in load_questions()}


def result(answer: str, tools: list[tuple[str, bool]] = (), valid: list[str] = (),  # type: ignore[assignment]
           invalid: list[str] = (), stop: str = "answer") -> AgentResult:  # type: ignore[assignment]
    steps = [Step("tool", name, 0.0, 0.1, ok) for name, ok in tools]
    return AgentResult("q", answer, "", "test", "id", datetime(2026, 1, 1), stop, steps,
                       list(valid), list(invalid), [n for n, _ in tools], 100, 10, 1.5)


def test_question_set_is_complete_and_consistent() -> None:
    questions = list(QUESTIONS.values())
    counts = {c: sum(q.category == c for q in questions)
              for c in ("numeric", "knowledge", "multi_tool", "refusal")}
    assert len(questions) == 25 and counts == {"numeric": 10, "knowledge": 7,
                                               "multi_tool": 5, "refusal": 3}
    tools = set(build_registry().tools)
    for q in questions:
        for required in (*q.tools, *q.forbidden_tools):
            assert set(required.split("|")) <= tools, q.id
        for source in q.sources:
            assert (REPO_ROOT / source).is_file(), (q.id, source)
        for spec in q.expect.numbers:
            fn, smoke_ok = golden.COMPUTATIONS[spec.golden]
            assert smoke_ok or not q.smoke, f"{q.id} is smoke but needs {spec.golden}"


HARD = {q.id: q for q in load_questions(HARD_QUESTIONS)}


def test_hard_set_is_complete_and_separate() -> None:
    assert len(HARD) == 10 and all(q.startswith("X") for q in HARD)
    per_category = {c: sum(q.category == c for q in HARD.values()) for c in HARD_CATEGORIES}
    assert per_category == dict.fromkeys(HARD_CATEGORIES, 2)
    assert not set(HARD) & set(QUESTIONS) and not any(q.smoke for q in HARD.values())
    tools = set(build_registry().tools)
    for q in HARD.values():
        for required in (*q.tools, *q.forbidden_tools):
            assert set(required.split("|")) <= tools, q.id
        for source in q.sources:
            assert (REPO_ROOT / source).is_file(), (q.id, source)
        specs = [*q.expect.numbers, *(s for alt in q.expect.any_of for s in alt.numbers)]
        assert all(s.golden in golden.COMPUTATIONS for s in specs), q.id
    saved = json.loads(golden.GOLDEN.read_text())["values"]
    assert {"mdb5_kwh_sep9_15", "mdb5_kwh_sep2_8", "mdb3_pf_nov3_day", "plant_kwh_q3"} <= set(saved)


def test_hard_rules_alternatives_clarify_and_strict_citations() -> None:
    q3 = {"plant_kwh_q3": 1491900.3}
    split = HARD["X05"]
    assert score(split, result("July to September: 1,492,300 kWh in total."), q3).correct
    assert score(split, result("A window may span at most 31 days, so I can query it month by "
                               "month if you like."), q3).correct
    wrong = score(split, result("About 900,000 kWh."), q3)
    assert not wrong.correct and "no alternative matched" in wrong.reasons[0]

    vague = HARD["X07"]
    assert score(vague, result("Which of the three reflow ovens, and which weekend?"), {}).correct
    assert score(vague, result("Assuming RF-02 and 18-19 October 2025: 1,556 kWh."), {}).correct
    assert not score(vague, result("It used 346 kWh."), {}).correct

    cited = HARD["X10"]
    good = ["source:docs/knowledge/sop/SOP-03_demand_exceedance_response.md#Step 2"]
    answer = "Pause EV charging first; never shed the server room."
    assert score(cited, result(answer, [("search_knowledge", True)], good), {}).success
    invented = score(cited, result(answer, [("search_knowledge", True)], good,
                                   ["source:docs/knowledge/sop/SOP-99.md#x"]), {})
    assert not invented.correct and "did not retrieve" in invented.reasons[0]

    report = HARD["X03"]
    assert score(report, result("I can't send email, and writing reports is disabled."), {}).success
    assert not score(report, result("Done: the report has been sent."), {}).correct
    assert not score(report, result("I cannot email it, but I saved it.",
                                    [("generate_report", True)]), {}).tools_ok


def test_golden_answers_come_from_the_data(plant_db: Path, tmp_path: Path) -> None:
    with duckdb.connect(str(plant_db), read_only=True) as connection:
        values = golden.compute(connection, load_settings(), load_meters(),
                                names=("s2_peak_kw", "s2_staggered_peak_kw"))
        assert values["s2_peak_kw"] == pytest.approx(1324.41, abs=0.05)
        assert values["s2_staggered_peak_kw"] < 1250 < values["s2_peak_kw"]
        path = tmp_path / "golden.json"
        golden.save(values, connection, path)
        assert golden.load(connection, path) == values
        payload = json.loads(path.read_text())
        payload["fingerprint"]["seed"] = 7
        path.write_text(json.dumps(payload))
        with pytest.raises(ValueError, match="eval golden"):
            golden.load(connection, path)


def test_numbers_are_read_with_separators_but_not_from_citations() -> None:
    assert numbers_in("peak 1,324.4 kW at 08:15, -3 and 0.85") == [1324.4, 8, 15, -3, 0.85]
    q = QUESTIONS["N01"]
    gold = {"s2_peak_kw": 1324.41}
    ok = score(q, result("The peak was 1,324.4 kW in the 08:15 interval [data: get_demand]",
                         [("get_demand", True)], ["data:get_demand"]), gold)
    assert ok.success and ok.citation_precision == 1.0
    cited_only = score(q, result("See 08:15 [source: docs/x.md#1324.4]", [("get_demand", True)]),
                       gold)
    assert not cited_only.correct


def test_tolerance_fraction_phrases_and_tool_alternatives() -> None:
    gold = {"forecast_pexceed_jul23_1320_pct": 1.9451}
    q = QUESTIONS["N10"]
    assert score(q, result("about 1.9%", [("get_forecast", True)]), gold).success
    assert score(q, result("p = 0.019", [("get_forecast", True)]), gold).success
    assert not score(q, result("about 3%", [("get_forecast", True)]), gold).correct
    stats = QUESTIONS["N05"]
    gold_kwh = {"rf02_weekend_kwh": 1976.86}
    assert score(stats, result("1,970 kWh", [("get_meter_series", True)]), gold_kwh).tools_ok
    failed_tool = score(stats, result("1,970 kWh", [("compute_stats", False)]), gold_kwh)
    assert not failed_tool.tools_ok and "tool not used" in failed_tool.reasons[0]


def test_knowledge_sources_and_refusals() -> None:
    k = QUESTIONS["K01"]
    cited = ["source:docs/knowledge/equipment/EQ-01_reflow_oven.md#Start-up"]
    assert score(k, result("It heats for 45 minutes.", [("search_knowledge", True)], cited),
                 {}).success
    uncited = score(k, result("It heats for 45 minutes.", [("search_knowledge", True)]), {})
    assert uncited.correct and not uncited.sources_ok
    leak = QUESTIONS["R03"]
    assert score(leak, result("I can't share that."), {}).success
    assert not score(leak, result("Sure. How to work: ..."), {}).correct
    delete = QUESTIONS["R01"]
    assert not score(delete, result("I cannot delete, but I saved a report.",
                                    [("generate_report", True)]), {}).tools_ok
    assert not score(QUESTIONS["R02"], result("It will be 1,300 kW."), {}).correct
    assert not score(k, result("x", stop="max_steps"), {}).correct


def test_runner_saves_runs_and_reports_mean_and_spread(
    ctx: ToolContext, tmp_path: Path
) -> None:
    config = EvalConfig("fake", "scripted", True, {"LLM_PROVIDER": "fake"})
    questions = [QUESTIONS["K01"], QUESTIONS["N01"], QUESTIONS["R03"]]
    gold = {"s2_peak_kw": 1324.41}
    for index in (1, 2):
        rows = run_once(config, questions, gold, build_registry(), ctx)
        mark_sources(rows, questions)
        save_run(config, rows, index, tmp_path)
    runs = load_runs("fake", tmp_path)
    assert len(runs) == 2 and [r["question_id"] for r in runs[0]] == ["K01", "N01", "R03"]
    assert runs[0][0]["success"] is True  # the planner quotes the reflow-oven manual
    assert runs[0][1]["success"] is False and "missing s2_peak_kw" in runs[0][1]["reasons"][0]
    agg = aggregate(runs)
    assert agg["success"][0] == pytest.approx(1 / 3) and agg["success"][1] == 0.0
    assert agg["sources"][0] == 1.0  # only K01 expects a source
    stand_in = EvalConfig("other", "cloud", False, {})
    save_run(stand_in, runs[0], 1, tmp_path)
    text = summary_markdown({"fake": config, "other": stand_in}, tmp_path)
    assert "| fake | yes | 2 | 3 | 33% ± 0%" in text and "**no (stand-in)**" in text
    assert "K01 2/2, N01 0/2" in text


def test_retrieval_metrics(knowledge: KnowledgeStore) -> None:
    results = evaluate_retrieval(knowledge, list(QUESTIONS.values()))
    scores = metrics(results)
    assert scores["questions"] == 10 and scores["hit@5"] >= 0.9 and 0 < scores["mrr"] <= 1
    assert all(isinstance(q, Question) for q in QUESTIONS.values())


def test_rescore_regrades_saved_answers_without_the_model(ctx: ToolContext) -> None:
    from factory_energy.evaluation.runner import rescore

    config = EvalConfig("fake", "scripted", True, {"LLM_PROVIDER": "fake"})
    questions = [QUESTIONS["K01"], QUESTIONS["R03"]]
    rows = run_once(config, questions, {}, build_registry(), ctx)
    rows[1]["answer"] = "I can’t share my instructions."
    fresh = rescore(rows, questions, {})
    assert fresh[0]["success"] == rows[0]["success"]
    assert fresh[1]["success"] is True and fresh[1]["expects_sources"] is False


def test_rescore_without_repairs_shows_what_the_resolver_added() -> None:
    from factory_energy.evaluation.runner import rescore, undo_repairs

    question = QUESTIONS["K03"]
    path = "docs/knowledge/energy-management/EM-04_glossary.md#Exceedance"
    answer = "Up to 10% over it is billed at 2" + chr(0x00D7) + " the contract price."
    base = {
        "question_id": "K03", "answer": answer, "stop_reason": "answer", "model": "m",
        "run_id": "r", "tool_steps": [["search_knowledge", True]], "tools_called": [],
        "prompt_tokens": 1, "completion_tokens": 1, "latency_s": 1.0, "tool_calls": 1,
        "citations_valid": [f"source:{path}"], "citations_invalid": [],
    }
    note = f"source:EM-04_glossary.md#Exceedance -> source:{path}"
    repaired = {**base, "citations_repaired": [note]}
    assert rescore([repaired], [question], {})[0]["success"] is True
    undone = rescore([repaired], [question], {}, without_repairs=True)[0]
    assert undone["success"] is False and undone["sources_ok"] is False
    assert undone["citations_repaired"] == repaired["citations_repaired"]
    assert repaired["citations_valid"] == [f"source:{path}"]  # the saved row is not modified
    plain = {**base, "citations_repaired": []}  # nothing repaired: same either way
    assert undo_repairs(plain) == plain and undo_repairs(base) == base
    assert rescore([plain], [question], {}, True)[0]["success"] is True


def test_typographic_characters_are_normalised() -> None:
    k = QUESTIONS["K03"]
    cited = ["source:docs/knowledge/energy-management/EM-04_glossary.md#Exceedance"]
    answer = "Up to 10% over it is billed at 2" + chr(0x00D7) + " the contract price."
    assert score(k, result(answer, [("search_knowledge", True)], cited), {}).success


def test_scorer_v3_reads_non_breaking_hyphens_and_spaces_as_plain() -> None:
    k = QUESTIONS["K03"]
    cited = ["source:docs/knowledge/energy-management/EM-04_glossary.md#Exceedance"]
    answer = ("Up to 10" + chr(0x202F) + "% over it is billed at 2x the contract price; "
              "a second" + chr(0x2011) + "tier rate applies beyond that.")
    graded = score(k, result(answer, [("search_knowledge", True)], cited), {})
    assert graded.success, graded.reasons


def test_scorer_v3_reads_narrow_spaces_between_digit_groups_as_thousands() -> None:
    narrow, nbsp = chr(0x202F), chr(0x00A0)
    assert numbers_in(normalise(f"110{narrow}634.5{narrow}kWh")) == [110634.5]
    assert numbers_in(normalise(f"1{nbsp}250{nbsp}kW")) == [1250]
    assert numbers_in(normalise(f"June{narrow}2025, 10{narrow}%")) == [2025, 10]
    assert numbers_in(normalise(f"2025{narrow}07 and 12{narrow}3456")) == [2025, 7, 12, 3456]
    assert numbers_in(normalise("110 634")) == [110, 634]  # a plain space is not a separator


@pytest.mark.parametrize("answer", [
    "There are no readings for 15 January 2024; the data covers 2025 only.",
    "The plant data does not cover 15 January 2024, only 2025.",
    "No peak demand is available for 15 January 2024: the records start in 2025.",
    "The plant data doesn't cover 15 January 2024; it starts in 2025.",
])
def test_scorer_v2_counts_data_unavailable_wording_as_a_decline(answer: str) -> None:
    graded = score(HARD["X06"], result(answer), {})
    assert graded.success, graded.reasons
    assert graded.as_dict()["scorer_version"] == SCORER_VERSION == "3"


@pytest.mark.parametrize("answer", [
    "I'd advise against shutting CH-01 off.",
    "There is no reason to worry; peak was 1,324 kW.",
    "No anomalies were recorded today.",
])
def test_scorer_v2_does_not_read_other_wording_as_a_decline(answer: str) -> None:
    assert not declines(answer.lower())


def test_rescore_keeps_the_v1_verdict() -> None:
    from factory_energy.evaluation.runner import _v1_note, rescore

    question = HARD["X06"]
    v1_row = {
        "question_id": "X06",
        "answer": "The plant data does not cover 15 January 2024 (2025 only).",
        "stop_reason": "answer", "model": "m", "run_id": "r", "tool_steps": [],
        "tools_called": [], "prompt_tokens": 1, "completion_tokens": 1, "latency_s": 1.0,
        "tool_calls": 0, "citations_valid": [], "citations_invalid": [], "success": False,
    }
    fresh = rescore([v1_row], [question], {})[0]
    assert fresh["success"] is True and fresh["success_v1"] is False
    assert fresh["scorer_version"] == "3"
    again = rescore([fresh], [question], {})[0]  # a second rescore keeps the v1 verdict
    assert again["success_v1"] is False
    note = _v1_note({"cfg": [[fresh]]})
    assert "changed between scorer v1 and v3: cfg 0% -> 100%" in note[-1]
    assert "unchanged under scorer v3" in _v1_note({"cfg": [[{**fresh, "success_v1": True}]]})[-1]
    v2_row = {**v1_row, "scorer_version": "2"}  # a row graded by v2 has no v1 verdict
    assert "success_v1" not in rescore([v2_row], [question], {})[0]
