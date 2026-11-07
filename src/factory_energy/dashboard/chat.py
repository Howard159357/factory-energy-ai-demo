"""The agent chat: a drawer on every page of the dashboard.

A lightning button opens it; Enter sends (see ``assets/chat.js``). The agent is told which page
the user is looking at, and with "use the replay clock as now" on, it is told the replay time
and every tool is cut off at it. Example questions (the page's own and ten common ones) open
from the 💡 button. Each answer keeps its working (plan, model calls, tool calls) in a
collapsed section that opens on a click. Citation chips open the passage
they point to, or the tool calls behind a number. The conversation lives in the browser
session, so it survives moving between pages. ``CHAT_MODEL_LABEL`` replaces the model name in
the header and the working footer (for recordings that should not name the model).
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from datetime import datetime
from typing import Any

from dash import ALL, Dash, Input, Output, State, dcc, html, no_update
from dash import ctx as callback_context

from factory_energy.agent.loop import Step
from factory_energy.dashboard.agent_runner import AgentRunner, Run
from factory_energy.dashboard.clock import ClockState
from factory_energy.dashboard.context import Context
from factory_energy.paths import ROOT
from factory_energy.rag.chunk import chunk_markdown

CITATION = re.compile(r"\[(source|data):\s*([^\]]+?)\s*\]", re.IGNORECASE)
BOLD = re.compile(r"\*\*(.+?)\*\*")
KNOWLEDGE = "docs/knowledge/"
FONT_SIZES = (15, 17, 19, 21, 23)  # px; the chat starts one step above the page's 14 px
ALPHAS = 3  # window backgrounds: solid, glass (default), clear
DEFAULT_PREFS = {"font": 1, "alpha": 1, "big": False}
CONTEXT_TURNS = 3  # earlier turns sent with a question, so follow-ups make sense
MAX_QUESTION_CHARS = 4000  # the longest question the chat sends (also for replayed ones)
CONTEXT_CHARS = 1500  # each earlier answer is cut to this length (tokens cost time)
MAX_HISTORY = 30  # messages kept in the browser; older ones drop off (storage is ~5 MB)
OPEN_PATH = "/agent"  # a link that opens the dashboard (plant map) with the chat already open

GENERAL = (
    "What is the 15-minute demand right now, and is the plant close to its contract?",
    "Which loads can we shed right now, and how much would each save?",
    "Has anything unusual been detected in the last 24 hours?",
)
# path -> (what the page shows, suggested questions)
PAGES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "/": ("Plant map", "live load per area and equipment status on the floor plan", (
        GENERAL[0],
        "Is any equipment in alarm right now, and why?",
        "Which distribution board is drawing the most power right now?")),
    "/overview": ("Overview", "today's demand, energy and alerts at a glance", (
        GENERAL[0],
        "Summarise the plant's status right now in three lines.",
        "What is the night base load, and is it normal?")),
    "/demand": ("Demand", "15-minute demand against the contract, and the staggered-start "
                          "what-if", (
        GENERAL[0], GENERAL[1],
        "How are demand charges billed above the contract?")),
    "/equipment": ("Equipment", "live status of the sub-metered loads by distribution board", (
        "Is any equipment in alarm right now, and why?",
        "Which equipment is idle right now and could be switched off?",
        "What does the weekend shutdown procedure say about the reflow ovens?")),
    "/anomalies": ("Anomalies", "detections from the rule, baseline and ML layers with "
                                "their evidence", (
        GENERAL[2],
        "What should maintenance check when a power factor drops?",
        "Was a compressed-air leak detected in September 2025, and what would it cost a "
        "year?")),
    "/forecast": ("Forecast", "the demand forecast and the chance of exceeding the "
                              "contract", (
        "What is the chance of exceeding the contract in the next hour?",
        "What should operators do when a hot afternoon may exceed the contract?",
        "When is the summer weekday peak tariff period?")),
    "/history": ("History", "energy and cost over the whole year", (
        "Which distribution board used the most energy in June 2025?",
        "How much more energy did MDB-4 use in July 2025 than in January?",
        "What was the energy cost from 4 to 10 August 2025, excluding demand charges?")),
}


# Questions users ask most. The flag sets the replay clock when one is picked: True for
# "right now" questions, False for a fixed past date (the clock would hide it), None leaves it
# as it is.
COMMON: tuple[tuple[str, bool | None], ...] = (
    ("What is the 15-minute demand right now, and how far is it from the contract?", True),
    ("Which loads can we shed right now, and how much would each save?", True),
    ("Has anything unusual been detected in the last 24 hours?", True),
    ("What is the chance of exceeding the contract in the next hour?", True),
    ("What was the peak demand on the morning of 16 June 2025, what caused it, and how much "
     "would a staggered start have saved?", False),
    ("Which distribution board used the most energy in June 2025, and how much?", False),
    ("What was the energy cost from 4 to 10 August 2025, excluding demand charges?", False),
    ("Was a compressed-air leak detected in September 2025, and what would it cost a year?",
     False),
    ("What does the weekend shutdown procedure say about the reflow ovens, and why is standby "
     "not enough?", None),
    ("How are demand charges billed above the contract?", None),
)


def model_label(model: str) -> str:
    """The model as the chat shows it: ``CHAT_MODEL_LABEL`` when set, else its own name."""
    return os.environ.get("CHAT_MODEL_LABEL", "").strip() or model


def prompt(index: str, path: str | None) -> tuple[str, bool | None] | None:
    """The question behind a prompt button: "p<n>" for the page's own, "c<n>" for common."""
    kind, number = index[:1], int(index[1:])
    if kind == "p":
        page = suggestions(path)
        return (page[number], None) if number < len(page) else None
    return COMMON[number] if kind == "c" and number < len(COMMON) else None


def page_note(path: str | None) -> str:
    title, shows, _ = PAGES.get(path or "/", PAGES["/"])
    return (f"The user is looking at the dashboard's {title} page ({shows}). Use it to "
            "understand words like 'this' or 'here', but answer the question that was asked.")


def suggestions(path: str | None) -> tuple[str, ...]:
    return PAGES.get(path or "/", PAGES["/"])[2]


# ---------------------------------------------------------------- layout

def bolt(extra: str = "", **kwargs: Any) -> html.Span:
    return html.Span(className=f"bolt {extra}".strip(), **kwargs)


def icon_button(symbol: str, button_id: str, title: str) -> html.Button:
    return html.Button(symbol, id=button_id, className="chat-icon-btn", title=title)


def prompt_button(text: str, index: str, clock: bool | None) -> html.Button:
    hint = {True: "uses the replay clock", False: "a past date: the replay clock is switched off",
            None: ""}[clock]
    return html.Button(text, id={"type": "chat-prompt", "index": index},
                       className="chat-prompt" + ("" if clock is None else f" clock-{clock}"),
                       title=hint)


def fab() -> html.Button:
    return html.Button(bolt(), id="chat-fab", className="chat-fab",
                       title="Ask the energy assistant")


def live_working(show: bool) -> html.Details:
    """Rebuilt for each run, so a section opened by hand during one run starts closed in the
    next; during a run only the steps inside it are replaced, so it stays as the user left it."""
    return html.Details([html.Summary("Working"),
                         html.Div(id="chat-live-steps", className="agent-steps")],
                        open=show, className="chat-working")


def drawer() -> html.Aside:
    head = html.Div([
        html.Div(bolt(), id="chat-badge", className="chat-badge"),
        html.Div([html.Div("Energy assistant", className="chat-title"),
                  html.Div(id="chat-model", className="chat-model")], className="chat-name"),
        html.Div([
            icon_button("↺", "chat-new", "New chat: clear the conversation"),
            icon_button("A−", "chat-smaller", "Smaller text"),
            icon_button("A+", "chat-larger", "Larger text"),
            icon_button("◐", "chat-alpha", "Transparency: solid, glass, clear"),
            icon_button("⤢", "chat-size", "Larger window"),
            icon_button("×", "chat-close", "Close (Esc)"),
        ], className="chat-tools"),
    ], className="chat-head")
    live = html.Div([
        html.Div(id="chat-live-q", className="chat-msg chat-user"),
        html.Div([
            html.Div([bolt("busy"), html.Span(id="chat-live-status")],
                     className="chat-live-head"),
            html.Div(live_working(False), id="chat-live-working"),
        ], className="chat-msg chat-bot"),
    ], id="chat-live", hidden=True)
    prompts = html.Div([
        html.Div([html.Div("Example questions", className="chat-cite-title"),
                  icon_button("×", "chat-prompts-close", "Close (Esc)")],
                 className="chat-cite-head"),
        html.Div([
            html.Div("On this page", className="chat-prompts-section"),
            html.Div(id="chat-prompts-page"),
            html.Div("Common questions", className="chat-prompts-section"),
            *[prompt_button(text, f"c{i}", clock)
              for i, (text, clock) in enumerate(COMMON)],
        ], className="chat-cite-body chat-prompts-list"),
    ], id="chat-prompts", className="chat-cite-view chat-prompts", hidden=True)
    compose = html.Div([
        html.Div([
            html.Button("💡", id="chat-prompts-btn", className="chat-tip-btn",
                        title="Example questions"),
            dcc.Textarea(id="chat-input", className="chat-input",
                         maxLength=MAX_QUESTION_CHARS, rows=2,
                         placeholder="Ask anything about the plant… (Enter sends)"),
            html.Button(html.Span(className="icon-stop"), id="chat-stop",
                        className="chat-send chat-stop", title="Stop", hidden=True),
            html.Button(html.Span(className="icon-send"), id="chat-send",
                        className="chat-send", title="Send (Enter)"),
        ], className="chat-input-row"),
        html.Div([
            dcc.Checklist(id="chat-clock", options=[{"label": "⏱ replay clock as now",
                                                     "value": "clock"}],
                          value=["clock"], persistence=True, persistence_type="local",
                          className="chat-clock-toggle"),
            html.Span("Shift+Enter: new line", className="chat-hint"),
        ], className="chat-options"),
    ], className="chat-compose")
    cite_view = html.Div([
        html.Div([html.Div(id="chat-cite-title", className="chat-cite-title"),
                  icon_button("×", "chat-cite-close", "Close (Esc)")],
                 className="chat-cite-head"),
        html.Div(id="chat-cite-body", className="chat-cite-body"),
    ], id="chat-cite-view", className="chat-cite-view", hidden=True)
    return html.Aside([
        head,
        html.Div([html.Div(id="chat-log"), live], id="chat-scroll", className="chat-scroll"),
        compose,
        prompts,
        cite_view,
    ], id="chat", className="chat")


def stores() -> list[Any]:
    return [
        dcc.Store(id="chat-history", data=[], storage_type="session"),
        dcc.Store(id="chat-open", data=False, storage_type="session"),
        dcc.Store(id="chat-prefs", data=dict(DEFAULT_PREFS), storage_type="local"),
        dcc.Store(id="chat-run"),
        dcc.Interval(id="chat-poll", interval=500, disabled=True),
    ]


def clean_prefs(prefs: dict[str, Any] | None) -> dict[str, Any]:
    """The viewer's window preferences (from browser storage), with every value in range."""
    merged = {**DEFAULT_PREFS, **(prefs or {})}
    return {"font": min(max(int(merged["font"]), 0), len(FONT_SIZES) - 1),
            "alpha": int(merged["alpha"]) % ALPHAS, "big": bool(merged["big"])}


def next_prefs(prefs: dict[str, Any] | None, button: str) -> dict[str, Any]:
    current = clean_prefs(prefs)
    if button in ("chat-smaller", "chat-larger"):
        current["font"] += 1 if button == "chat-larger" else -1
    elif button == "chat-alpha":
        current["alpha"] += 1
    elif button == "chat-size":
        current["big"] = not current["big"]
    return clean_prefs(current)


def window_class(prefs: dict[str, Any] | None, is_open: bool) -> str:
    p = clean_prefs(prefs)
    return (f"chat fs-{p['font']} alpha-{p['alpha']}" + (" big" if p["big"] else "")
            + (" open" if is_open else ""))


# ---------------------------------------------------------------- records and rendering

BOLD = re.compile(r"\*\*(.+?)\*\*")  # the plan is shown as plain text, so no ** markers


def step_record(step: Step, first_llm: bool) -> dict[str, Any]:
    return {
        "kind": step.kind, "name": step.name, "ok": step.ok, "error": step.error,
        "seconds": round(step.duration_s, 2),
        "tokens": f"{step.prompt_tokens:,} → {step.completion_tokens:,}",
        "arguments": step.arguments,
        "plan": BOLD.sub(r"\1", step.content.strip()) if step.kind == "llm" and first_llm else "",
    }


def step_records(steps: list[Step], finished: bool) -> list[dict[str, Any]]:
    """Steps as plain data. The first model call's text is its plan, except when it is the
    only model call of a finished run: then it is the answer, shown once."""
    llm = [i for i, s in enumerate(steps) if s.kind == "llm"]
    plan_at = llm[0] if llm and not (finished and len(llm) == 1) else -1
    return [step_record(s, i == plan_at) for i, s in enumerate(steps)]


def record(run: Run, page: str) -> dict[str, Any]:
    """A finished (or stopped) run as plain data for the browser's session store."""
    steps = list(run.steps)  # the agent thread may still be appending after a stop
    rec: dict[str, Any] = {
        "question": run.question, "page": page,
        "now": f"{run.now:%a %d %b %Y %H:%M}" if run.now else "",
        "steps": step_records(steps, finished=True),
        "answer": "", "error": "", "notes": [], "footer": "",
    }
    result = run.result
    if run.stopped:
        rec["error"] = "Stopped. Ask again, or try a narrower question."
    elif run.error:
        rec["error"] = run.error
    elif result is not None:
        rec["answer"] = result.answer
        rec["footer"] = (f"{model_label(result.model)} · {len(result.steps)} steps · "
                         f"{result.latency_s:.1f} s "
                         f"(model {result.llm_s:.1f} s, tools {result.tool_s:.1f} s) · "
                         f"{result.prompt_tokens:,} / {result.completion_tokens:,} tokens · "
                         f"{result.stop_reason}")
        if result.citations_invalid:
            rec["notes"].append("Removed unverified citations: "
                                + ", ".join(result.citations_invalid))
        if result.security_events:
            rec["notes"].append("Guardrails: " + ", ".join(
                f"{e['layer']}:{e['kind']}" for e in result.security_events))
    return rec


def cite_label(kind: str, value: str) -> str:
    if kind == "source":
        path, _, heading = value.partition("#")
        name = path.rsplit("/", 1)[-1]
        return f"{name} · {heading.split(' > ')[-1]}" if heading else name
    return f"data · {value}"


def citations(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).lower(), m.group(2)) for m in CITATION.finditer(text)]


def render_answer(text: str, message: int) -> list[Any]:
    """The answer with each citation turned into a chip that opens what it points to."""
    parts: list[Any] = []
    cursor = 0
    for number, match in enumerate(CITATION.finditer(text)):
        parts.append(text[cursor:match.start()])
        kind, value = match.group(1).lower(), match.group(2)
        parts.append(html.Button(cite_label(kind, value), title=value,
                                 id={"type": "chat-cite", "index": f"{message}:{number}"},
                                 className=f"cite cite-{kind}"))
        cursor = match.end()
    parts.append(text[cursor:])
    return [html.Span(bold(p)) if isinstance(p, str) else p for p in parts if p != ""]


def bold(text: str) -> list[Any]:
    """Markdown **bold** as <b>, the one piece of markdown models use in short answers."""
    pieces = BOLD.split(text)  # odd positions are the bold parts
    return [html.B(p) if i % 2 else p for i, p in enumerate(pieces) if p]


def render_step(step: dict[str, Any]) -> html.Div:
    body: list[Any]
    extra: list[Any] = []
    if step["kind"] == "llm":
        body = [html.Span("model", className="tag"),
                html.Span(model_label(step["name"]), className="muted"),
                html.Span(f"{step['seconds']:.1f} s · {step['tokens']} tokens",
                          className="muted")]
        if step["plan"]:
            extra.append(html.Pre(step["plan"], className="agent-plan"))
    else:
        args = ", ".join(f"{k}={v}" for k, v in step["arguments"].items())
        body = [html.Span("tool", className="tag RULE"), html.Code(f"{step['name']}({args})"),
                html.Span(f"{step['seconds']:.2f} s", className="muted")]
    if not step["ok"]:
        extra.append(html.Div(step["error"], className="agent-error"))
    return html.Div([html.Div(body, className="agent-step-head"), *extra],
                    className="agent-step" + ("" if step["ok"] else " failed"))


def render_message(rec: dict[str, Any], message: int, show_working: bool) -> list[Any]:
    meta = " · ".join(x for x in (rec.get("page", ""), rec["now"] and f"as of {rec['now']}") if x)
    question = html.Div([html.Div(rec["question"]),
                         html.Div(meta, className="chat-meta") if meta else None],
                        className="chat-msg chat-user")
    body: list[Any] = []
    if rec["answer"]:
        body.append(html.Div(render_answer(rec["answer"], message), className="chat-answer"))
    if rec["error"]:
        body.append(html.Div(rec["error"], className="agent-error"))
    body += [html.Div(note, className="muted small") for note in rec["notes"]]
    steps = rec["steps"]
    if steps:
        working = [render_step(s) for s in steps]
        if rec["footer"]:
            working.append(html.Div(rec["footer"], className="muted small"))
        body.append(html.Details([html.Summary(f"Working · {len(steps)} steps"),
                                  html.Div(working, className="agent-steps")],
                                 open=show_working, className="chat-working"))
    return [question, html.Div(body, className="chat-msg chat-bot")]


def render_log(history: list[dict[str, Any]], show_working: bool) -> list[Any]:
    if not history:
        return [html.Div([
            html.Div("Ask about demand, energy, equipment or procedures, in any language.",
                     className="chat-welcome-title"),
            html.Div("The assistant queries the plant data and the documents and cites what it "
                     "used; click a citation to see it. 💡 next to the input has example "
                     "questions. All data is synthetic.", className="muted"),
        ], className="chat-welcome")]
    out: list[Any] = []
    for number, rec in enumerate(history):
        out += render_message(rec, number, show_working)
    return out


def context_turns(history: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """The last few answered turns as (question, answer). Citations are taken out: they point
    to passages of an earlier run, and the citation check only accepts what this run retrieves."""
    # The history lives in the browser, so it is untrusted: skip malformed records, cap lengths.
    answered = [rec for rec in history if isinstance(rec, dict)
                and isinstance(rec.get("question"), str) and isinstance(rec.get("answer"), str)
                and rec["answer"]][-CONTEXT_TURNS:]
    turns = []
    for rec in answered:
        answer = CITATION.sub("", rec["answer"]).strip()
        if len(answer) > CONTEXT_CHARS:
            answer = answer[:CONTEXT_CHARS] + " …"
        turns.append((rec["question"][:MAX_QUESTION_CHARS], answer))
    return turns


def live_status(run: Run, ahead: int = 0) -> str:
    if run.queued:
        place = f"{ahead} question{'s' if ahead != 1 else ''} ahead" if ahead else "next"
        return (f"Waiting for the model · {place} · {run.elapsed_s:.0f} s "
                "(only a few questions run at a time)")
    when = f" as of {run.now:%a %d %b %H:%M}" if run.now else ""
    last = next((s.name for s in reversed(run.steps) if s.kind == "tool"), "")
    doing = f" · last tool: {last}" if last else ""
    return f"Working{when} · {run.elapsed_s:.0f} s · {len(run.steps)} steps{doing}"


def passage(citation: str) -> tuple[str, str] | None:
    """(heading, text) of the knowledge-base section a citation points to, or None."""
    source, _, heading = citation.partition("#")
    if not source.startswith(KNOWLEDGE) or not source.endswith(".md"):
        return None  # only the knowledge base is readable here
    base = (ROOT / KNOWLEDGE).resolve()
    path = (ROOT / source).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        return None
    chunks = [c for c in chunk_markdown(path.read_text(encoding="utf-8"), source)
              if c.heading == heading]
    if not chunks:
        return None
    text = "\n\n".join(c.text.removeprefix(f"{heading}\n\n") for c in chunks)
    return heading, text


def cite_view(rec: dict[str, Any], number: int) -> tuple[str, list[Any]]:
    found = citations(rec["answer"])
    if number >= len(found):
        return "Citation", [html.Div("This citation is no longer available.",
                                     className="muted")]
    kind, value = found[number]
    if kind == "source":
        section = passage(value)
        title = cite_label(kind, value)
        if section is None:
            return title, [html.Div(f"The passage for {value} is not available here.",
                                    className="muted")]
        return title, [html.Div(f"{value.partition('#')[0]} · {section[0]}",
                                className="muted small"),
                       dcc.Markdown(section[1], className="chat-passage")]
    calls = [s for s in rec["steps"] if s["kind"] == "tool" and s["name"] == value]
    if not calls:
        return f"data · {value}", [html.Div("No call to this tool was recorded.",
                                            className="muted")]
    return f"data · {value}", [
        html.Div("The number comes from this tool call:" if len(calls) == 1 else
                 f"The number comes from one of these {len(calls)} tool calls:",
                 className="muted small"),
        *[render_step(s) for s in calls]]


# ---------------------------------------------------------------- callbacks

def register(app: Dash, ctx: Context) -> None:
    from factory_energy.cli_agent import tool_context
    from factory_energy.llm import LLMSettings, make_client
    from factory_energy.tools import build_registry

    settings = LLMSettings.from_env()
    base = replace(tool_context(), db_path=ctx.data.database)  # the dashboard's own database
    attach(app, AgentRunner(base, build_registry(), lambda: make_client(settings)))


def attach(app: Dash, runner: AgentRunner) -> None:
    @app.callback(Output("chat-model", "children"), Input("url", "pathname"))
    def _model(_: str | None) -> str:
        return f"model: {model_label(runner.model_name)}"  # cached by the runner

    @app.callback(Output("chat-open", "data"),
                  Input("chat-fab", "n_clicks"), Input("chat-close", "n_clicks"),
                  Input("url", "pathname"), State("chat-open", "data"))
    def _open(_fab: int | None, _close: int | None, path: str | None, is_open: bool) -> Any:
        trigger = callback_context.triggered_id
        if trigger == "chat-fab":
            return not is_open
        if trigger == "chat-close":
            return False
        return True if path == OPEN_PATH else no_update

    @app.callback(Output("chat", "className"), Output("chat-fab", "className"),
                  Output("chat-badge", "className"), Output("chat-size", "title"),
                  Input("chat-open", "data"), Input("chat-prefs", "data"),
                  Input("chat-run", "data"))
    def _classes(is_open: bool, prefs: dict[str, Any] | None,
                 run_id: str | None) -> tuple[str, str, str, str]:
        busy = " busy" if run_id else ""
        big = bool(clean_prefs(prefs)["big"])
        return (window_class(prefs, bool(is_open)) + busy,
                "chat-fab" + (" hidden" if is_open else "") + busy, "chat-badge" + busy,
                "Smaller window" if big else "Larger window")

    @app.callback(Output("chat-prefs", "data"),
                  Input("chat-smaller", "n_clicks"), Input("chat-larger", "n_clicks"),
                  Input("chat-alpha", "n_clicks"), Input("chat-size", "n_clicks"),
                  State("chat-prefs", "data"), prevent_initial_call=True)
    def _prefs(_s: int | None, _l: int | None, _a: int | None, _z: int | None,
               prefs: dict[str, Any] | None) -> dict[str, Any]:
        return next_prefs(prefs, str(callback_context.triggered_id))

    @app.callback(Output("chat-prompts-page", "children"), Input("url", "pathname"))
    def _page_prompts(path: str | None) -> list[Any]:
        return [prompt_button(text, f"p{i}", None) for i, text in enumerate(suggestions(path))]

    @app.callback(Output("chat-prompts", "hidden"),
                  Input("chat-prompts-btn", "n_clicks"), Input("chat-prompts-close", "n_clicks"),
                  State("chat-prompts", "hidden"), prevent_initial_call=True)
    def _toggle_prompts(_b: int | None, _c: int | None, hidden: bool | None) -> bool:
        if callback_context.triggered_id == "chat-prompts-close":
            return True
        return not hidden

    @app.callback(Output("chat-input", "value"), Output("chat-clock", "value"),
                  Output("chat-prompts", "hidden", allow_duplicate=True),
                  Input({"type": "chat-prompt", "index": ALL}, "n_clicks"),
                  State("url", "pathname"), prevent_initial_call=True)
    def _use_prompt(clicks: list[int | None], path: str | None) -> tuple[Any, Any, Any]:
        trigger = callback_context.triggered_id
        if not isinstance(trigger, dict) or not any(clicks):
            return no_update, no_update, no_update
        chosen = prompt(str(trigger["index"]), path)
        if chosen is None:
            return no_update, no_update, no_update
        text, clock = chosen
        return text, no_update if clock is None else (["clock"] if clock else []), True

    @app.callback(Output("chat-run", "data"),
                  Output("chat-input", "value", allow_duplicate=True),
                  Output("chat-history", "data", allow_duplicate=True),
                  Input("chat-send", "n_clicks"),
                  State("chat-input", "value"), State("chat-clock", "value"),
                  State("clock", "data"), State("url", "pathname"), State("chat-run", "data"),
                  State("chat-history", "data"), prevent_initial_call=True)
    def _ask(_: int | None, question: str | None, use_clock: list[str] | None,
             clock: dict[str, Any], path: str | None, current: str | None,
             history: list[dict[str, Any]] | None) -> tuple[Any, Any, Any]:
        active = runner.get(current or "")
        if not question or not question.strip() or (active is not None and not active.done):
            return no_update, no_update, no_update
        now: datetime | None = ClockState.from_store(clock).now if use_clock else None
        try:
            return runner.start(question.strip(), now, page_note(path),
                                context_turns(history or [])), "", no_update
        except RuntimeError as error:  # too many questions waiting: show it like other errors
            failed = {"question": question.strip()[:MAX_QUESTION_CHARS], "page": "", "now": "",
                      "steps": [], "answer": "", "error": str(error), "notes": [], "footer": ""}
            return no_update, no_update, [*(history or []), failed][-MAX_HISTORY:]


    @app.callback(Output("chat-stop", "disabled"), Input("chat-stop", "n_clicks"),
                  State("chat-run", "data"), prevent_initial_call=True)
    def _stop(_: int | None, run_id: str | None) -> bool:
        runner.stop(run_id or "")
        return True

    @app.callback(Output("chat-live", "hidden"), Output("chat-send", "hidden"),
                  Output("chat-stop", "hidden"),
                  Output("chat-stop", "disabled", allow_duplicate=True),
                  Output("chat-poll", "disabled"), Output("chat-live-q", "children"),
                  Output("chat-live-status", "children"), Output("chat-live-working", "children"),
                  Input("chat-run", "data"), prevent_initial_call=True)
    def _busy(run_id: str | None) -> tuple[Any, ...]:
        run = runner.get(run_id or "")
        if run is None:
            return True, False, True, False, True, "", "", no_update
        return (False, True, False, False, False, run.question,
                live_status(run, runner.queue_position(run)),
                live_working(False))

    @app.callback(Output("chat-live-status", "children", allow_duplicate=True),
                  Output("chat-live-steps", "children", allow_duplicate=True),
                  Output("chat-history", "data"),
                  Output("chat-run", "data", allow_duplicate=True),
                  Input("chat-poll", "n_intervals"), State("chat-run", "data"),
                  State("chat-history", "data"), State("url", "pathname"),
                  prevent_initial_call=True)
    def _poll(_: int | None, run_id: str | None, history: list[dict[str, Any]] | None,
              path: str | None) -> tuple[Any, Any, Any, Any]:
        run = runner.get(run_id or "")
        if run is None:  # the dashboard restarted while a run was going
            return no_update, no_update, no_update, None
        if run.done:
            page = PAGES.get(path or "/", PAGES["/"])[0]
            kept = [*(history or []), record(run, page)][-MAX_HISTORY:]
            return no_update, no_update, kept, None
        steps = [render_step(s) for s in step_records(list(run.steps), finished=False)]
        return live_status(run, runner.queue_position(run)), steps, no_update, no_update

    @app.callback(Output("chat-history", "data", allow_duplicate=True),
                  Input("chat-new", "n_clicks"), prevent_initial_call=True)
    def _new(_: int | None) -> list[Any]:
        return []

    @app.callback(Output("chat-log", "children"), Input("chat-history", "data"))
    def _log(history: list[dict[str, Any]] | None) -> list[Any]:
        return render_log(history or [], show_working=False)  # opened per answer when wanted

    @app.callback(Output("chat-cite-title", "children"), Output("chat-cite-body", "children"),
                  Output("chat-cite-view", "hidden"),
                  Input({"type": "chat-cite", "index": ALL}, "n_clicks"),
                  Input("chat-cite-close", "n_clicks"), State("chat-history", "data"),
                  prevent_initial_call=True)
    def _cite(clicks: list[int | None], _close: int | None,
              history: list[dict[str, Any]] | None) -> tuple[Any, Any, Any]:
        trigger = callback_context.triggered_id
        if trigger == "chat-cite-close":
            return no_update, no_update, True
        if not isinstance(trigger, dict) or not any(clicks):
            return no_update, no_update, no_update
        message, number = (int(x) for x in str(trigger["index"]).split(":"))
        if not history or message >= len(history):
            return no_update, no_update, no_update
        title, body = cite_view(history[message], number)
        return title, body, False
