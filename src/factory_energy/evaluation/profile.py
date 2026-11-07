"""Inference profiling against an OpenAI-compatible server: time to first token, decode speed and
throughput with 1, 2 and 4 concurrent users.

Each request streams a chat completion of a fixed prompt. Per request we record the time to the
first content token (TTFT), the completion tokens (from the server's usage, or one per chunk when
the server sends no usage) and the decode rate after the first token. Per concurrency level we
report medians and the aggregate throughput (all completion tokens / wall time). Results label
the hardware and engine they came from; numbers from a laptop are indicative only.
"""

from __future__ import annotations

import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from factory_energy.llm.factory import LLMSettings

PROMPT = ("Explain in about 150 words why a factory's 15-minute demand matters for its electricity "
          "bill, and give two practical ways to keep it below the contract capacity.")


@dataclass
class Sample:
    ttft_s: float
    total_s: float
    completion_tokens: int
    prompt_tokens: int
    error: str = ""

    @property
    def decode_tok_s(self) -> float:
        decode = self.total_s - self.ttft_s
        return (self.completion_tokens - 1) / decode if decode > 0 and self.completion_tokens > 1 \
            else 0.0


@dataclass
class Level:
    users: int
    wall_s: float
    samples: list[Sample] = field(default_factory=list)

    @property
    def ok(self) -> list[Sample]:
        return [s for s in self.samples if not s.error]

    def summary(self) -> dict[str, float]:
        ok = self.ok
        if not ok:
            return {"users": self.users, "requests": len(self.samples), "errors": len(self.samples)}
        return {
            "users": self.users, "requests": len(self.samples),
            "errors": len(self.samples) - len(ok),
            "ttft_median_s": statistics.median(s.ttft_s for s in ok),
            "ttft_max_s": max(s.ttft_s for s in ok),
            "decode_tok_s_median": statistics.median(s.decode_tok_s for s in ok),
            "latency_median_s": statistics.median(s.total_s for s in ok),
            "throughput_tok_s": sum(s.completion_tokens for s in ok) / self.wall_s,
            "completion_tokens_median": statistics.median(s.completion_tokens for s in ok),
        }


def stream_once(client: Any, model: str, max_tokens: int, extra_body: dict[str, Any],
                prompt: str = PROMPT) -> Sample:
    """One streamed request; TTFT is measured to the first chunk that carries text."""
    began = time.perf_counter()
    first: float | None = None
    chunks = 0
    usage: Any = None
    try:
        stream = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens,
            temperature=0.0, stream=True, stream_options={"include_usage": True},
            extra_body=extra_body or None)
        for chunk in stream:
            if chunk.usage is not None:
                usage = chunk.usage
            if chunk.choices and (chunk.choices[0].delta.content or ""):
                chunks += 1
                if first is None:
                    first = time.perf_counter()
    except Exception as error:  # noqa: BLE001 - recorded per sample, the run goes on
        return Sample(0.0, time.perf_counter() - began, 0, 0, f"{type(error).__name__}: {error}")
    end = time.perf_counter()
    if first is None:
        return Sample(0.0, end - began, 0, 0, "no text in the stream")
    completion = int(usage.completion_tokens) if usage else chunks
    prompt_tokens = int(usage.prompt_tokens) if usage else 0
    return Sample(first - began, end - began, completion, prompt_tokens)


def run_level(make_client: Callable[[], Any], model: str, users: int, rounds: int,
              max_tokens: int, extra_body: dict[str, Any]) -> Level:
    """``users`` threads each send ``rounds`` requests back to back, all starting together."""
    samples: list[Sample] = []
    lock = threading.Lock()
    start = threading.Barrier(users)
    clients = [make_client() for _ in range(users)]  # built first: a failure cannot hang a Barrier

    def user(client: Any) -> None:
        start.wait()
        for _ in range(rounds):
            sample = stream_once(client, model, max_tokens, extra_body)
            with lock:
                samples.append(sample)

    threads = [threading.Thread(target=user, args=(c,)) for c in clients]
    began = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return Level(users, time.perf_counter() - began, samples)


def profile(settings: LLMSettings, levels: tuple[int, ...] = (1, 2, 4), rounds: int = 3,
            max_tokens: int = 256, warmup: bool = True,
            progress: Callable[[str], None] | None = None) -> list[Level]:
    from openai import OpenAI

    def make_client() -> Any:
        return OpenAI(base_url=settings.base_url, api_key=settings.api_key or "not-needed",
                      timeout=600, max_retries=0)

    if warmup:  # loads the model and fills caches, so the first level is not penalised
        stream_once(make_client(), settings.model, 16, settings.extra_body)
    results = []
    for users in levels:
        level = run_level(make_client, settings.model, users, rounds, max_tokens,
                          settings.extra_body)
        results.append(level)
        if progress:
            s = level.summary()
            progress(f"{users} user(s): {s.get('requests', 0)} requests, "
                     f"TTFT median {s.get('ttft_median_s', float('nan')):.2f} s, "
                     f"throughput {s.get('throughput_tok_s', float('nan')):.1f} tok/s, "
                     f"errors {s.get('errors', 0)}")
    return results


def markdown(levels: list[Level], label: str) -> str:
    lines = [
        f"# Inference profile: {label}", "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M')}. One fixed prompt, streamed, temperature 0. "
        "Each user sends its requests back to back; all users start together. TTFT is the time "
        "to the first text token; decode speed is per request after the first token; throughput "
        "is all completion tokens over the wall time of the level. Indicative numbers for the "
        "hardware named in the title.", "",
        "| Users | Requests | Errors | TTFT median (s) | TTFT max (s) | Decode tok/s per request "
        "(median) | Latency median (s) | Throughput tok/s (all users) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for level in levels:
        s = level.summary()
        if "ttft_median_s" not in s:
            lines.append(f"| {level.users} | {s['requests']} | {s['errors']} | - | - | - | - | - |")
            continue
        lines.append(
            f"| {level.users} | {s['requests']:.0f} | {s['errors']:.0f} | {s['ttft_median_s']:.2f} "
            f"| {s['ttft_max_s']:.2f} | {s['decode_tok_s_median']:.1f} | "
            f"{s['latency_median_s']:.1f} | {s['throughput_tok_s']:.1f} |")
    errors = [s.error for level in levels for s in level.samples if s.error]
    if errors:
        lines += ["", "Errors: " + "; ".join(sorted(set(errors)))[:500]]
    return "\n".join(lines) + "\n"
