"""Runs agent questions for the dashboard in background threads and keeps their live progress.

The chat starts a run and polls it; each finished step (plan, model call, tool call) appears as
soon as the agent records it. When the replay clock is used as "now", the run's tool context
gets ``as_of`` so no tool can return data from after that moment.

- Stop: the chat stops waiting at once, the model call in flight is cancelled (the Codex
  process tree is killed, or the HTTP connection to the model server closed), and the agent
  makes no further model or tool request.
- Concurrency: at most ``max_concurrent`` runs (``AGENT_MAX_CONCURRENT``, default 2) use the
  model at the same time; later questions wait in order and show their place in the queue.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from factory_energy.agent.loop import Agent, AgentResult, Step
from factory_energy.llm.base import LLMClient, cancel, close
from factory_energy.tools.context import ToolContext
from factory_energy.tools.registry import ToolRegistry

KEEP = 20  # runs kept for the chat to read; also the most that may be active (queued/running)
WAIT_TICK_S = 0.2  # how often a queued run checks whether it was stopped


def max_concurrent_from_env() -> int:
    return max(1, int(os.environ.get("AGENT_MAX_CONCURRENT", "2")))


@dataclass
class Run:
    question: str
    now: datetime | None
    note: str = ""
    history: tuple[tuple[str, str], ...] = ()  # earlier (question, answer) turns, oldest first
    steps: list[Step] = field(default_factory=list)
    result: AgentResult | None = None
    error: str = ""
    started: float = field(default_factory=time.monotonic)
    cancel: threading.Event = field(default_factory=threading.Event)
    queued: bool = True  # waiting for a free slot
    llm: LLMClient | None = None  # the client in use, so a stop can cancel its call

    @property
    def stopped(self) -> bool:
        return self.cancel.is_set()

    @property
    def done(self) -> bool:
        return self.result is not None or bool(self.error) or self.stopped

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started


class AgentRunner:
    def __init__(self, base: ToolContext, registry: ToolRegistry,
                 make_llm: Callable[[], LLMClient], max_steps: int = 8,
                 max_concurrent: int | None = None) -> None:
        self.base = base
        self.registry = registry
        self.make_llm = make_llm
        self.max_steps = max_steps
        self.max_concurrent = max_concurrent or max_concurrent_from_env()
        self._slots = threading.Semaphore(self.max_concurrent)
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._lock = threading.Lock()
        self._model_name: str | None = None

    @property
    def model_name(self) -> str:
        """The backend's name, found once: building a client can create files (Codex temp dir)."""
        if self._model_name is None:
            client = self.make_llm()
            try:
                self._model_name = client.name
            finally:
                close(client)
        return self._model_name

    def start(self, question: str, now: datetime | None, note: str = "",
              history: Sequence[tuple[str, str]] = ()) -> str:
        run_id = uuid.uuid4().hex
        run = Run(question, now, note, tuple(history))
        with self._lock:
            if sum(1 for r in self._runs.values() if not r.done) >= KEEP:
                raise RuntimeError("too many questions are waiting; try again shortly")
            self._runs[run_id] = run
            for old_id in [i for i, r in self._runs.items() if r.done]:  # oldest first
                if len(self._runs) <= KEEP:
                    break
                del self._runs[old_id]
        threading.Thread(target=self._execute, args=(run,), daemon=True).start()
        return run_id

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def queue_position(self, run: Run) -> int:
        """How many questions started earlier are still waiting (0: next to start)."""
        with self._lock:
            waiting = [r for r in self._runs.values() if r.queued and not r.stopped]
        return waiting.index(run) if run in waiting else 0

    def stop(self, run_id: str) -> None:
        run = self.get(run_id)
        if run is None:
            return
        run.cancel.set()
        if run.llm is not None:
            cancel(run.llm)  # kill the model call in flight, where the backend allows it

    def _execute(self, run: Run) -> None:
        while not self._slots.acquire(timeout=WAIT_TICK_S):
            if run.stopped:  # stopped while waiting: never touch the model
                run.queued = False
                return
        run.queued = False
        try:
            if not run.stopped:
                self._answer(run)
        finally:
            self._slots.release()

    def _answer(self, run: Run) -> None:
        # One context per run: its own read-only connection and, if asked, the replay cutoff.
        ctx = replace(self.base, as_of=run.now, knowledge=self.base.store)
        try:
            run.llm = self.make_llm()
            if run.stopped:  # stopped while the client was being made
                return
            agent = Agent(run.llm, self.registry, ctx, max_steps=self.max_steps,
                          on_step=run.steps.append, should_stop=run.cancel.is_set)
            run.result = agent.run(run.question, now=run.now, note=run.note,
                                   history=run.history)
        except Exception as error:  # noqa: BLE001 - shown in the chat instead of a dead spinner
            run.error = f"{type(error).__name__}: {error}"
        finally:
            if run.llm is not None:
                close(run.llm)
            ctx.close()
