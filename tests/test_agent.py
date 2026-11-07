import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from factory_energy.agent import citations
from factory_energy.agent.loop import Agent
from factory_energy.agent.trace import setup_tracing, write_jsonl
from factory_energy.agent.working import strip_working
from factory_energy.llm import LLMError, LLMSettings, LLMTurn, ToolCall, make_client
from factory_energy.llm.fake import FakeClient
from factory_energy.llm.openai_compatible import OpenAICompatibleClient
from factory_energy.tools import build_registry
from factory_energy.tools.context import ToolContext

S2 = json.dumps({"start": "2025-06-16T06:00", "end": "2025-06-16T11:00"})


@pytest.fixture(scope="module")
def spans() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    if setup_tracing({}, extra=SimpleSpanProcessor(exporter)) is None:
        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def agent(ctx: ToolContext, script: list[LLMTurn] | None = None, steps: int = 6) -> Agent:
    return Agent(FakeClient(script), build_registry(), ctx, max_steps=steps)


def test_planner_answers_from_the_documents_with_a_valid_citation(
    ctx: ToolContext, spans: InMemorySpanExporter, tmp_path: Path
) -> None:
    spans.clear()
    result = agent(ctx).run("Why must reflow ovens be switched off at the weekend?")
    assert result.stop_reason == "answer" and result.plan.startswith("Plan:")
    assert result.tools_called == ["search_knowledge"]
    assert result.citations_valid and not result.citations_invalid
    assert "[source: docs/knowledge/" in result.answer
    assert [s.kind for s in result.steps] == ["llm", "tool", "llm"]
    names = [s.name for s in spans.get_finished_spans()]
    assert names.count("execute_tool search_knowledge") == 1
    assert names[-1] == "invoke_agent energy-agent" and sum("chat" in n for n in names) == 2
    root = spans.get_finished_spans()[-1]
    assert root.attributes is not None and root.attributes["gen_ai.usage.input_tokens"] > 0
    assert len(result.run_id) == 32  # the OpenTelemetry trace id

    path = write_jsonl(result, tmp_path)
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["run_start", "llm", "tool", "llm", "final"]
    assert events[2]["name"] == "search_knowledge" and events[2]["duration_s"] >= 0


def test_parallel_calls_errors_and_citation_checking(ctx: ToolContext) -> None:
    script = [
        LLMTurn("1. Get demand. 2. Look up the procedure.", [
            ToolCall("a", "get_demand", S2),
            ToolCall("b", "search_knowledge", json.dumps({"query": "staggered start-up"})),
            ToolCall("c", "get_demand", "{not json"),
            ToolCall("d", "drop_database", "{}"),
            ToolCall("e", "generate_report", json.dumps({"title": "x", "body_markdown": "y" * 20})),
        ]),
        LLMTurn("Peak 1,324 kW [data: get_demand]; stagger starts [source: "
                "docs/knowledge/sop/SOP-01_monday_startup.md] and see [source: made/up.md#x] "
                "and [data: get_energy]."),
    ]
    result = agent(ctx, script).run("What was the S2 peak and how do we avoid it?")
    tools = [s for s in result.steps if s.kind == "tool"]
    assert [t.ok for t in tools] == [True, True, False, False, False]
    assert "not valid JSON" in tools[2].error and "unknown tool" in tools[3].error
    assert "disabled" in tools[4].error
    assert "data:get_demand" in result.citations_valid
    assert any(c.startswith("source:docs/knowledge/sop/SOP-01") for c in result.citations_valid)
    assert result.citations_invalid == ["source:made/up.md#x", "data:get_energy"]
    assert result.answer.count(citations.REMOVED) == 2


def test_the_model_sees_tool_errors_and_results(ctx: ToolContext) -> None:
    client = FakeClient([LLMTurn("", [ToolCall("a", "get_demand", '{"start": "2025-06-16"}')]),
                         LLMTurn("Done.")])
    Agent(client, build_registry(), ctx).run("demand?")
    tool_message = client.calls[1][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "a"
    assert "end: Field required" in json.loads(tool_message["content"])["error"]


def test_the_answer_leaves_out_the_models_working(ctx: ToolContext) -> None:
    # As Qwen3.6-27B wrote it: a remark, a draft, then a lead-in line and the answer.
    draft = ("Now I have all the information I need. EV-01 draws 9.1 kW.\n\n"
             "Let me provide the answer:\n\nPause EV-01: 9.1 kW [data: get_demand]")
    client = FakeClient([LLMTurn("", [ToolCall("a", "get_demand", S2)]), LLMTurn(draft)])
    result = Agent(client, build_registry(), ctx).run("What to shed?")
    assert result.answer == "Pause EV-01: 9.1 kW [data: get_demand]"
    assert strip_working("Plan done.\n\n**Answer:**\n\nYes, 92%.") == "Yes, 92%."
    assert strip_working("Now I have all the data I need. Peak 1,324 kW.") == "Peak 1,324 kW."
    # Nothing to take out, or only a heading with nothing after it: unchanged.
    assert strip_working("I have the data: peak 1,324 kW.") == "I have the data: peak 1,324 kW."
    plain = "The answer is 1,324 kW.\nAnswer: see above."
    assert strip_working(plain) == plain
    assert strip_working("Draft.\n\nAnswer:") == "Draft.\n\nAnswer:"


def test_step_limit_input_limit_and_model_errors(ctx: ToolContext) -> None:
    loop = [LLMTurn("", [ToolCall(str(i), "get_plant_overview", "{}")]) for i in range(5)]
    stuck = agent(ctx, loop, steps=3).run("loop forever")
    assert stuck.stop_reason == "max_steps" and len(stuck.tools_called) == 2
    # The third identical call is refused by the tool budget, not executed.
    assert stuck.security_events[-1]["layer"] == "tool_budget"
    assert agent(ctx).run(" ").stop_reason == "rejected_input"
    assert agent(ctx).run("x" * 5000).stop_reason == "rejected_input"

    class Broken(FakeClient):
        def complete(self, messages: list, tools: list) -> LLMTurn:
            raise LLMError("connection refused")

    failed = Agent(Broken(), build_registry(), ctx).run("anything")
    assert failed.stop_reason == "llm_error" and "connection refused" in failed.answer


def test_citation_rules() -> None:
    retrieved = {"docs/a.md#Title > Part", "docs/b.md#B"}
    report = citations.check(
        "x [source: docs/a.md] y [source: docs/a.md#Title] z [source: docs/b.md#Other] "
        "[Source: docs/b.md#B] [data: get_demand]", retrieved, {"get_demand"})
    assert report.valid == ["source:docs/a.md#Title > Part", "source:docs/b.md#B",
                            "data:get_demand"]
    assert report.invalid == ["source:docs/b.md#Other"]
    assert report.repaired == []  # well-formed citations need no help


def test_typographic_hyphens_and_spaces_in_citations_are_read_as_plain() -> None:
    path = "docs/knowledge/energy-management/EM-04_glossary.md#EM-04 Glossary > Exceedance"
    nb_hyphen, narrow_space = chr(0x2011), chr(0x202F)
    written = path.replace("-", nb_hyphen).replace("EM-04 Glossary", f"EM-04{narrow_space}Glossary")
    report = citations.check(f"x [source: {written}] [data: get{nb_hyphen}demand]",
                             {path}, {"get-demand"})
    assert report.invalid == [] and report.repaired == []  # same citation, not a repair
    assert report.valid == [f"source:{path}", "data:get-demand"]
    assert f"[source: {path}]" in report.answer


def test_full_width_brackets_and_backticks_are_read_as_plain() -> None:
    sop = "docs/knowledge/sop/SOP-03.md#SOP-03 > Purpose"
    report = citations.check(f"a【data: get_demand】 b［source：{sop}］ c [data: `get_energy`]",
                             {sop}, {"get_demand", "get_energy"})
    assert report.invalid == [] and report.repaired == []  # same citations, not repairs
    assert report.valid == ["data:get_demand", f"source:{sop}", "data:get_energy"]
    assert report.answer == (f"a[data: get_demand] b[source: {sop}] c [data: get_energy]")


def test_nested_split_and_spaced_tool_citations_are_repaired() -> None:
    sop = "docs/knowledge/sop/SOP-03.md#SOP-03 > Purpose"
    tools = {"get_plant_overview", "get_demand"}
    report = citations.check(
        "a [source: data: get_demand] b [data: get_plant_overview, data: get_demand] "
        f"c [source: plant overview – contract 1250 kW] d [source: {sop}; get_demand]",
        {sop}, tools)
    assert report.invalid == [] and len(report.repaired) == 4
    assert report.answer == ("a [data: get_demand] b [data: get_plant_overview] "
                             "[data: get_demand] c [data: get_plant_overview] "
                             f"d [source: {sop}] [data: get_demand]")
    # every part must resolve, and a spaced name must be a whole tool name that was called
    bad = citations.check("[data: get_demand, get_forecast] [source: plant] [source: demand x]",
                          {sop}, tools)
    assert bad.valid == [] and len(bad.invalid) == 3


def test_near_miss_citations_resolve_only_to_what_was_retrieved() -> None:
    em02 = "docs/knowledge/energy-management/EM-02_demand_management.md#EM-02 Demand Management"
    retrieved = {f"{em02} > Key terms", f"{em02} > Warning line",
                 "docs/knowledge/sop/SOP-03_demand_exceedance_response.md#SOP-03 > Purpose",
                 "docs/knowledge/sop/SOP-06_heat_wave.md#SOP-06 > Purpose"}
    report = citations.check(
        # no folder; no file; title#heading; tool as source; extra words; heading prefix
        "a [source: EM-02_demand_management.md#EM-02 Demand Management > Key terms] "
        "b [source: EM-02 Demand Management > Warning line] "
        "c [source: EM-02#EM-02 Demand Management > Key terms] "
        "d [source: get_energy] "
        "e [data: get_meter_series MDB-3] "
        "f [source: SOP-03 > Purpose]",
        retrieved, {"get_energy", "get_meter_series"})
    assert report.invalid == []
    assert len(report.repaired) == 6
    assert f"[source: {em02} > Key terms]" in report.answer
    assert f"[source: {em02} > Warning line]" in report.answer
    assert "[data: get_energy]" in report.answer and "[data: get_meter_series]" in report.answer
    assert "source:docs/knowledge/sop/SOP-03_demand_exceedance_response.md#SOP-03 > Purpose" \
        in report.valid


def test_heading_prefixes_must_be_whole_segments() -> None:
    sop = "docs/knowledge/sop/SOP-03.md#SOP-03 Demand Exceedance Response"
    em = "docs/knowledge/em/EM-02.md#EM-02 Demand Management"
    retrieved = {f"{sop} > Purpose", f"{em} > Key terms", f"{em} > Warning line"}
    partial = citations.check("[source: E] [source: EM-02 Demand] [source: SOP-03 Demand Ex]",
                              retrieved, set())
    assert partial.valid == [] and len(partial.invalid) == 3 and partial.repaired == []
    whole = citations.check(
        "[source: SOP-03 Demand Exceedance Response] [source: EM-02 Demand Management] "
        "[source: EM-02.md#EM-02 Demand Management > Key terms]", retrieved, set())
    # Two passages of EM-02 share the title, so the bare title cites the document itself.
    assert whole.valid == [f"source:{sop} > Purpose", "source:docs/knowledge/em/EM-02.md",
                           f"source:{em} > Key terms"]
    assert whole.invalid == [] and len(whole.repaired) == 3
    assert "[source: docs/knowledge/em/EM-02.md]" in whole.answer


def test_a_bare_title_cites_the_document_only_when_it_fits_one_file() -> None:
    em3 = "docs/knowledge/em/EM-03_tariff_guide.md#EM-03 Tariff Guide"
    retrieved = {f"{em3} > Demand charges", f"{em3} > Exceedance charges",
                 "docs/knowledge/sop/SOP-03.md#SOP-03 Demand Exceedance Response > Purpose"}
    for title in ("EM-03 Tariff Guide", "EM-03", "em-03_tariff_guide"):
        report = citations.check(f"[source: {title}]", retrieved, set())
        assert report.valid == ["source:docs/knowledge/em/EM-03_tariff_guide.md"], title
        assert report.repaired == [f"source:{title} -> "
                                   "source:docs/knowledge/em/EM-03_tariff_guide.md"]
    # A heading path, a partial word or a title shared by two files never falls back to a document.
    two_files = retrieved | {"docs/knowledge/em/EM-03_tariff_guide_old.md#EM-03 Tariff Guide > X"}
    for text, pool in (("[source: EM-03 Tariff Guide > Nowhere]", retrieved),
                       ("[source: EM-03 Tariff]", retrieved),
                       ("[source: EM-03 Tariff Guide]", two_files)):
        report = citations.check(text, pool, set())
        assert report.valid == [] and len(report.invalid) == 1, text


def test_ambiguous_or_unsupported_citations_are_still_removed() -> None:
    retrieved = {"docs/knowledge/sop/SOP-03.md#Purpose", "docs/knowledge/sop/SOP-06.md#Purpose",
                 "docs/knowledge/em/EM-02.md#Key terms"}
    report = citations.check(
        "[source: Purpose] "                     # two passages have this heading: no guess
        "[source: EM-09.md#Key terms] "          # never retrieved
        "[source: Tariff > Peak hours] "         # nothing retrieved has this heading
        "[source: get_forecast] "                # a tool that was not called
        "[data: compute_stats MDB-3]",           # not called either
        retrieved, {"get_energy"})
    assert report.repaired == [] and report.valid == []
    assert len(report.invalid) == 5 and report.answer.count(citations.REMOVED) == 5


def test_api_key_can_come_from_a_file(tmp_path: Path) -> None:
    from factory_energy.llm.factory import LLMSettings

    secret = tmp_path / "key.txt"
    secret.write_text("# paste the key below\n\n  test-key-123  \n", encoding="utf-8")
    assert LLMSettings.from_env({"LLM_API_KEY_FILE": str(secret)}).api_key == "test-key-123"
    assert LLMSettings.from_env({"LLM_API_KEY": "direct",
                                 "LLM_API_KEY_FILE": str(secret)}).api_key == "direct"
    assert LLMSettings.from_env({}).api_key == ""
    with pytest.raises(ValueError, match="cannot be read"):
        LLMSettings.from_env({"LLM_API_KEY_FILE": str(tmp_path / "missing.txt")})


def test_backend_selection() -> None:
    assert make_client(LLMSettings.from_env({})).name == "fake:planner"
    with pytest.raises(ValueError):
        make_client(LLMSettings.from_env({"LLM_PROVIDER": "cloud"}))
    with pytest.raises(ValueError):
        make_client(LLMSettings.from_env({"LLM_PROVIDER": "openai_compatible"}))
    settings = LLMSettings.from_env({"LLM_EXTRA_BODY": '{"top_k": 20}'})
    assert settings.extra_body == {"top_k": 20}


class _ChatHandler(BaseHTTPRequestHandler):
    """Answers /v1/chat/completions like vLLM does, once with tool calls, then with text."""

    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _ChatHandler.requests.append(body)
        if len(_ChatHandler.requests) == 1:
            message = {"role": "assistant", "content": "Plan: check demand.",
                       "reasoning_content": "The user wants the S2 peak.",
                       "tool_calls": [{"id": "call_1", "type": "function", "function": {
                           "name": "get_demand", "arguments": S2}}]}
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": "1,324 kW [data: get_demand]"}
            finish = "stop"
        payload = json.dumps({
            "id": "x", "object": "chat.completion", "created": 0, "model": "local-model",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 40, "total_tokens": 940},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def chat_server() -> Iterator[str]:
    _ChatHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), _ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_openai_compatible_client_drives_the_loop(ctx: ToolContext, chat_server: str) -> None:
    client = OpenAICompatibleClient(chat_server, "local-model",
                                    extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    result = Agent(client, build_registry(), ctx).run("What was the S2 peak?")
    assert result.answer == "1,324 kW [data: get_demand]"
    assert result.citations_valid == ["data:get_demand"]
    assert (result.prompt_tokens, result.completion_tokens) == (1800, 80)
    first, second = _ChatHandler.requests
    assert first["tool_choice"] == "auto" and len(first["tools"]) == 11
    assert first["chat_template_kwargs"] == {"enable_thinking": False}
    assert second["messages"][-1]["role"] == "tool"
    assert json.loads(second["messages"][-1]["content"])["peak_kw"] > 1300


def test_openai_compatible_client_reports_connection_errors() -> None:
    client = OpenAICompatibleClient("http://127.0.0.1:9/v1", "m", timeout=2.0, max_retries=0)
    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "hi"}], [])


def test_steps_are_streamed_as_they_finish(ctx: ToolContext) -> None:
    seen: list[str] = []
    result = Agent(FakeClient(), build_registry(), ctx,
                   on_step=lambda step: seen.append(f"{step.kind}:{step.name}")).run(
        "How long does a reflow oven preheat?")
    assert seen == [f"{s.kind}:{s.name}" for s in result.steps]
    assert seen[1] == "tool:search_knowledge"


def test_a_cited_title_must_match_the_document() -> None:
    sop6 = "docs/knowledge/sop/SOP-06_heat_wave_precooling.md#SOP-06 Heat Wave Pre-cooling"
    em3 = "docs/knowledge/em/EM-03_tariff.md#EM-03 Tariff Guide"
    retrieved = {f"{sop6} > Purpose", f"{em3} > X"}
    wrong = citations.check("[source: SOP-99 Wrong#EM-03 Tariff Guide > X]", retrieved, set())
    assert wrong.valid == [] and len(wrong.invalid) == 1
    partial = citations.check("[source: SOP-0#SOP-06 Heat Wave Pre-cooling > Purpose]",
                              retrieved, set())
    assert partial.valid == []
    for title in ("SOP-06 Heat Wave Pre-cooling", "SOP-06", "sop-06_heat_wave_precooling"):
        ok = citations.check(f"[source: {title}#SOP-06 Heat Wave Pre-cooling > Purpose]",
                             retrieved, set())
        assert ok.valid == [f"source:{sop6} > Purpose"], title


def test_api_key_is_not_in_the_settings_repr() -> None:
    settings = LLMSettings.from_env({"LLM_API_KEY": "sk-secret-123"})
    assert settings.api_key == "sk-secret-123" and "sk-secret-123" not in repr(settings)
