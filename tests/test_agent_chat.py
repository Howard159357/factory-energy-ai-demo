"""The dashboard's agent chat: replay-clock cutoff, background runner, stop, rendering."""

import threading
import time
from dataclasses import replace
from datetime import datetime

import pytest
from dash import html

from factory_energy.agent.loop import Step
from factory_energy.dashboard import agent_runner, chat
from factory_energy.dashboard.agent_runner import AgentRunner
from factory_energy.llm.base import LLMClient, LLMError, LLMTurn, Message, ToolCall
from factory_energy.llm.fake import FakeClient
from factory_energy.tools import build_registry
from factory_energy.tools.context import ToolContext

REGISTRY = build_registry()
DURING_S2 = datetime(2025, 6, 16, 8, 10)  # the start-up surge has begun; the peak is at 08:15
SOP02 = "docs/knowledge/sop/SOP-02_weekend_shutdown.md"


def call(ctx: ToolContext, name: str, **arguments: object) -> dict:
    result = REGISTRY.call(ctx, name, arguments)
    assert result.ok, result.error
    return result.content


def test_demand_is_cut_off_at_the_replay_time(ctx: ToolContext) -> None:
    now = replace(ctx, as_of=DURING_S2)
    demand = call(now, "get_demand", start="2025-06-16T06:00", end="2025-06-16T11:00")
    later = call(ctx, "get_demand", start="2025-06-16T06:00", end="2025-06-16T11:00")
    assert later["peak_kw"] > 1300 and later["peak_interval_start"] == "2025-06-16T08:15"
    assert demand["series"][-1]["start"] < "2025-06-16T08:00"  # 08:00-08:15 is not complete
    assert demand["peak_kw"] < later["peak_kw"]
    future = REGISTRY.call(now, "get_demand", {"start": "2025-06-16T09:00",
                                               "end": "2025-06-16T10:00"})
    assert not future.ok and "does not exist yet" in future.error


def test_equipment_status_respects_now(ctx: ToolContext) -> None:
    now = replace(ctx, as_of=DURING_S2)
    assert call(now, "get_equipment_status")["as_of"] == "2025-06-16T08:10"
    later = call(now, "get_equipment_status", as_of="2025-06-16T10:00")
    assert later["as_of"] == "2025-06-16T08:10"  # a later moment is clipped to "now"


def test_detections_forecasts_and_overview_respect_now(ctx: ToolContext) -> None:
    now = replace(ctx, as_of=DURING_S2)
    kinds = {d["event_type"] for d in call(now, "list_detections", start="2025-06-16",
                                           end="2025-06-17")["detections"]}
    assert "DEMAND_EXCEEDANCE" not in kinds  # closes at 08:15, after "now"
    forecast = call(replace(ctx, as_of=datetime(2025, 6, 16, 7, 59)), "get_forecast",
                    as_of="2025-06-16T09:00")
    assert forecast["issued_at"] == "2025-06-16T07:30"  # nothing issued later is visible
    overview = call(now, "get_plant_overview")
    assert overview["current_time"] == "2025-06-16T08:10"
    assert "S2" not in {s["id"] for s in overview["incident_scenarios"]}
    whatif = REGISTRY.call(now, "whatif_staggered_start", {"scenario_id": "S2"})
    assert not whatif.ok and "after that day has ended" in whatif.error
    assert call(replace(ctx, as_of=datetime(2025, 6, 17, 6, 0)), "whatif_staggered_start",
                scenario_id="S2")["staggered_peak_kw"] < 1250


def wait(runner: AgentRunner, run_id: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while not runner.get(run_id).done and time.time() < deadline:  # type: ignore[union-attr]
        time.sleep(0.05)


def test_runner_tells_the_agent_the_time_and_the_page(ctx: ToolContext) -> None:
    clients: list[FakeClient] = []

    def make() -> LLMClient:
        clients.append(FakeClient())
        return clients[-1]

    runner = AgentRunner(ctx, REGISTRY, make)
    run_id = runner.start("How long does a reflow oven preheat?", DURING_S2,
                          chat.page_note("/equipment"))
    wait(runner, run_id)
    run = runner.get(run_id)
    assert run is not None and run.result is not None and run.result.stop_reason == "answer"
    assert [s.kind for s in run.steps] == ["llm", "tool", "llm"]
    system = clients[-1].calls[0][0]["content"]
    assert "current time at the plant is 2025-06-16 08:10" in system
    assert "Equipment page" in system
    rec = chat.record(run, "Equipment")
    assert rec["answer"] and rec["footer"] and len(rec["steps"]) == 3
    assert rec["steps"][0]["plan"] and not rec["steps"][2]["plan"]  # the answer is not repeated
    planned = Step("llm", "m", 0.0, 1.0, content="1. **Find the step**: search SOP-03 **now**")
    assert chat.step_record(planned, True)["plan"] == "1. Find the step: search SOP-03 now"
    assert rec["now"] == "Mon 16 Jun 2025 08:10"
    log = str(chat.render_log([rec], show_working=False))
    assert "Working · 3 steps" in log and "open=False" in log


class SlowClient:
    """Asks for one tool call, then waits until the test lets it go."""

    def __init__(self, release: threading.Event) -> None:
        self.release = release

    @property
    def name(self) -> str:
        return "slow"

    def complete(self, messages: list[Message], tools: list[dict]) -> LLMTurn:
        self.release.wait(5)
        return LLMTurn("1. look", [ToolCall("a", "get_plant_overview", "{}")])


def test_stop_ends_the_run_at_once_and_the_agent_at_its_next_step(ctx: ToolContext) -> None:
    release = threading.Event()
    runner = AgentRunner(ctx, REGISTRY, lambda: SlowClient(release))
    run_id = runner.start("anything", None)
    run = runner.get(run_id)
    assert run is not None and not run.done
    runner.stop(run_id)
    assert run.done and run.stopped  # the chat stops waiting without the model's answer
    assert "Stopped" in chat.record(run, "Overview")["error"]
    release.set()
    deadline = time.time() + 10
    while run.result is None and time.time() < deadline:
        time.sleep(0.05)
    assert run.result is not None and run.result.stop_reason == "stopped"
    assert run.result.tools_called == []  # the tool call after the stop never ran


class CancellableClient(SlowClient):
    """Blocks in its model call until cancelled, like a long generation."""

    def __init__(self, release: threading.Event) -> None:
        super().__init__(release)
        self.cancelled = False

    def complete(self, messages: list[Message], tools: list[dict]) -> LLMTurn:
        if not self.release.wait(10):
            raise RuntimeError("never cancelled")
        raise LLMError("cancelled by the user")

    def cancel(self) -> None:
        self.cancelled = True
        self.release.set()


def test_stop_cancels_the_model_call_in_flight(ctx: ToolContext) -> None:
    clients: list[CancellableClient] = []

    def make() -> LLMClient:
        clients.append(CancellableClient(threading.Event()))
        return clients[-1]

    runner = AgentRunner(ctx, REGISTRY, make)
    run_id = runner.start("anything", None)
    deadline = time.time() + 10
    while not clients and time.time() < deadline:
        time.sleep(0.02)
    runner.stop(run_id)
    run = runner.get(run_id)
    assert run is not None and clients[0].cancelled
    while run.result is None and time.time() < deadline:
        time.sleep(0.02)
    assert run.result is not None and run.result.stop_reason == "stopped"  # not "llm_error"


def test_only_a_few_runs_use_the_model_and_the_rest_wait(ctx: ToolContext) -> None:
    release = threading.Event()
    made: list[SlowClient] = []

    def make() -> LLMClient:
        made.append(SlowClient(release))
        return made[-1]

    runner = AgentRunner(ctx, REGISTRY, make, max_concurrent=1)
    first = runner.start("first", None)
    deadline = time.time() + 10
    while not made and time.time() < deadline:
        time.sleep(0.02)
    second, third = runner.start("second", None), runner.start("third", None)
    time.sleep(0.5)
    runs = [runner.get(i) for i in (first, second, third)]
    assert [r.queued for r in runs] == [False, True, True]  # type: ignore[union-attr]
    assert [runner.queue_position(r) for r in runs[1:]] == [0, 1]  # type: ignore[arg-type]
    assert "next" in chat.live_status(runs[1], 0) and "1 question ahead" in chat.live_status(
        runs[2], 1)  # type: ignore[arg-type]
    runner.stop(third)  # stopped while waiting: it never reaches the model
    release.set()
    for run in runs[:2]:
        while run.result is None and time.time() < deadline:  # type: ignore[union-attr]
            time.sleep(0.05)
    assert len(made) == 2 and runs[2].llm is None  # type: ignore[union-attr]


def test_runner_shows_errors_instead_of_hanging(ctx: ToolContext) -> None:
    def broken() -> LLMClient:
        raise RuntimeError("model server unreachable")

    runner = AgentRunner(ctx, REGISTRY, broken)
    run_id = runner.start("anything", None)
    wait(runner, run_id)
    run = runner.get(run_id)
    assert run is not None and run.done and "unreachable" in run.error
    assert "unreachable" in str(chat.render_log([chat.record(run, "Overview")], False))


def test_citations_become_clickable_chips() -> None:
    parts = chat.render_answer("Peak 1,324 kW [data: get_demand]; see [source: docs/knowledge/"
                               "sop/SOP-01_monday_startup.md#SOP-01 Monday Start-up > Start "
                               "groups].", message=3)
    chips = [p for p in parts if isinstance(p, html.Button)]
    assert [c.children for c in chips] == ["data · get_demand",
                                           "SOP-01_monday_startup.md · Start groups"]
    assert [c.id["index"] for c in chips] == ["3:0", "3:1"]
    assert chips[1].title.startswith("docs/knowledge/sop/SOP-01")
    first = chat.render_answer("MDB-4 used **161,644 kWh** in June.", message=0)[0]
    assert [type(c).__name__ for c in first.children] == ["str", "B", "str"]


def test_citation_popup_shows_the_passage_or_the_tool_call() -> None:
    heading = "SOP-02 Weekend Shutdown > Why reflow ovens must be OFF, not standby"
    found = chat.passage(f"{SOP02}#{heading}")
    assert found is not None and found[0] == heading and "25.2 kW" in found[1]
    assert chat.passage(f"{SOP02}#No such section") is None
    assert chat.passage("docs/../pyproject.toml#x") is None  # only the knowledge base
    assert chat.passage("docs/knowledge/../../README.md#x") is None
    rec = {"answer": f"Off, not standby [source: {SOP02}#{heading}]; 1,324 kW "
                     "[data: get_demand].",
           "steps": [{"kind": "tool", "name": "get_demand", "ok": True, "error": "",
                      "seconds": 0.1, "tokens": "", "plan": "",
                      "arguments": {"start": "2025-06-16T06:00"}}]}
    title, body = chat.cite_view(rec, 0)
    assert "SOP-02_weekend_shutdown.md" in title and "25.2 kW" in str(body)
    title, body = chat.cite_view(rec, 1)
    assert title == "data · get_demand" and "start=2025-06-16T06:00" in str(body)


def test_window_preferences_stay_in_range() -> None:
    assert chat.window_class(None, False) == "chat fs-1 alpha-1"  # glass, 17 px, small window
    prefs = chat.next_prefs(None, "chat-size")
    assert chat.window_class(prefs, True) == "chat fs-1 alpha-1 big open"
    for _ in range(9):
        prefs = chat.next_prefs(prefs, "chat-larger")
    assert prefs["font"] == len(chat.FONT_SIZES) - 1
    prefs = chat.next_prefs(prefs, "chat-alpha")
    prefs = chat.next_prefs(prefs, "chat-alpha")
    assert prefs["alpha"] == 0  # glass -> clear -> solid
    assert chat.clean_prefs({"font": 99, "alpha": -1, "junk": 1}) == {
        "font": len(chat.FONT_SIZES) - 1, "alpha": 2, "big": False}


def test_every_page_has_a_note_and_suggestions() -> None:
    from factory_energy.dashboard.app import PAGES

    for page in PAGES:
        assert page.PATH in chat.PAGES, page.PATH
        assert len(chat.suggestions(page.PATH)) == 3
    assert "Plant map" in chat.page_note("/nowhere")


def test_follow_ups_carry_the_last_turns(ctx: ToolContext) -> None:
    history = [{"question": f"q{i}", "answer": f"answer {i} [data: get_demand]"}
               for i in range(5)]
    history.insert(4, {"question": "stopped", "answer": "", "error": "Stopped."})
    turns = chat.context_turns(history)
    assert turns == [("q2", "answer 2"), ("q3", "answer 3"), ("q4", "answer 4")]
    long = chat.context_turns([{"question": "q", "answer": "x" * 5000}])
    assert len(long[0][1]) < chat.CONTEXT_CHARS + 5

    clients: list[FakeClient] = []

    def make() -> LLMClient:
        clients.append(FakeClient())
        return clients[-1]

    runner = AgentRunner(ctx, REGISTRY, make)
    run_id = runner.start("And in July?", None, "", [("Energy of MDB-4 in June 2025?",
                                                     "About 161,644 kWh.")])
    wait(runner, run_id)
    sent = clients[-1].calls[0]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"].startswith("Energy of MDB-4") and sent[3]["content"] == "And in July?"
    assert "earlier turns of this conversation" in sent[0]["content"]


def test_example_questions() -> None:
    assert len(chat.COMMON) == 10
    assert chat.prompt("p1", "/demand") == (chat.suggestions("/demand")[1], None)
    text, clock = chat.prompt("c4", "/")  # type: ignore[misc]
    assert "16 June 2025" in text and clock is False  # a past date turns the clock off
    assert chat.prompt("c0", "/")[1] is True  # type: ignore[index]
    assert chat.prompt("c10", "/") is None and chat.prompt("p9", "/") is None
    # Only past-date questions turn the clock off; "right now" ones never name a date.
    for question, uses_clock in chat.COMMON:
        assert ("2025" in question) == (uses_clock is False), question


def test_replayed_history_is_checked_and_capped() -> None:
    history = [
        "not a record", None, {"question": 5, "answer": "a"}, {"question": "q", "answer": 7},
        {"question": "q", "answer": ["x"]}, {"answer": "no question"},
        {"question": "q" * 9000, "answer": "ok"},
    ]
    turns = chat.context_turns(history)  # type: ignore[arg-type]
    assert turns == [("q" * chat.MAX_QUESTION_CHARS, "ok")]
    many = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(10)]
    assert [q for q, _ in chat.context_turns(many)] == ["q7", "q8", "q9"]


def test_active_runs_are_never_evicted_and_are_capped(ctx: ToolContext) -> None:
    release = threading.Event()
    runner = AgentRunner(ctx, REGISTRY, lambda: SlowClient(release), max_concurrent=1)
    ids = [runner.start("q", None) for _ in range(agent_runner.KEEP)]
    with pytest.raises(RuntimeError, match="too many questions"):
        runner.start("one more", None)
    assert all(runner.get(i) is not None for i in ids)
    release.set()
    for run_id in ids:
        runner.stop(run_id)
        wait(runner, run_id)
    for _ in range(5):  # finished runs are evicted, oldest first, once the store is over KEEP
        runner.start("later", None)
    assert len(runner._runs) <= agent_runner.KEEP
    assert runner.get(ids[0]) is None


def test_model_name_builds_one_client(ctx: ToolContext) -> None:
    built: list[FakeClient] = []

    def make() -> LLMClient:
        built.append(FakeClient())
        return built[-1]

    runner = AgentRunner(ctx, REGISTRY, make)
    assert runner.model_name == runner.model_name == built[0].name
    assert len(built) == 1


def test_model_label_can_be_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAT_MODEL_LABEL", raising=False)
    assert chat.model_label("openai_compatible:some-model") == "openai_compatible:some-model"
    monkeypatch.setenv("CHAT_MODEL_LABEL", "local model server")
    assert chat.model_label("openai_compatible:some-model") == "local model server"
    monkeypatch.setenv("CHAT_MODEL_LABEL", "  ")
    assert chat.model_label("fake") == "fake"
