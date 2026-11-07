"""Programmatic scoring of one agent answer. No model grades another model here.

- correct: every expected number appears within tolerance, every phrase group matches, one
  of the alternatives matches (when any are given), a refusal declines, a clarify question
  asks back or states its assumption, a strict-citation question cites nothing it did not
  retrieve, and no forbidden string appears;
- tools_ok: each expected tool (or one of its alternatives) was called successfully and no
  forbidden tool was;
- sources_ok: when sources are expected, at least one is cited with a verified citation;
- citation_precision: verified citations / all citations the answer made;
- success: all three of the above.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from factory_energy.agent.citations import PLAIN_PUNCTUATION
from factory_energy.agent.loop import AgentResult
from factory_energy.evaluation.questions import NumberSpec, Question

NUMBER = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")
REFUSAL = (
    "cannot", "can't", "can not", "unable", "not able", "won't", "will not", "not possible",
    "read-only", "read only", "no tool", "not available", "don't have", "do not have",
    "not supported", "outside", "only covers", "no data", "isn't available", "is not available",
    "not allowed", "not permitted", "decline", "only has data", "only contains",
    "no readings", "no record", "does not cover", "doesn't cover", "not cover",
)
# "No peak demand is available for ..." and similar data-unavailable wording.
REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bno\b[^.;:!?\n]{0,40}\b(?:is|are) available\b", re.IGNORECASE),
)
# v2 only widens the decline wording (data-unavailable phrasings); v1 judgements are kept
# in saved rows as ``success_v1``. v3 also reads typographic hyphens and spaces as plain ones.
SCORER_VERSION = "3"
# Wording of an answer that asks back or makes its assumption explicit. A keyword rule is
# coarse: it is reported as such and used only for the "ambiguous" hard questions.
CLARIFY = (
    "which ", "do you mean", "did you mean", "clarify", "specify", "assum", "please confirm",
    "could you confirm", "can you confirm", "if you mean", "interpret", "taking it as",
    "i take this", "i'll take", "i will take",
)


@dataclass
class Score:
    question_id: str
    category: str
    correct: bool
    tools_ok: bool
    sources_ok: bool
    citation_precision: float | None
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    tool_calls: int
    stop_reason: str
    reasons: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.correct and self.tools_ok and self.sources_ok

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "success": self.success, "scorer_version": SCORER_VERSION}


def numbers_in(text: str) -> list[float]:
    found = []
    for raw in NUMBER.findall(text):
        try:
            found.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return found


# Typographic characters models write, mapped to what the expectations use:
# right and left single quotes to an apostrophe, the multiplication sign to "x", and
# non-breaking hyphens and spaces to plain ones ("pre‑cooling", "10 %").
_PLAIN = str.maketrans({chr(0x2019): "'", chr(0x2018): "'", chr(0x00D7): "x",
                        **{chr(code): plain for code, plain in PLAIN_PUNCTUATION.items()}})


# A no-break or narrow no-break space between digits and exactly three more digits is a
# thousands separator ("110 634.5", the SI style); plain spaces are left alone.
_THOUSANDS = re.compile("(?<=\\d)[\u00a0\u202f](?=\\d{3}(?!\\d))")


def normalise(text: str) -> str:
    return _THOUSANDS.sub("", text).translate(_PLAIN)


def declines(lower: str) -> bool:
    """Whether a normalised, lower-cased answer declines or says the data is unavailable."""
    return (any(p in lower for p in REFUSAL)
            or any(pattern.search(lower) for pattern in REFUSAL_PATTERNS))


def _strip_citations(text: str) -> str:
    """Numbers inside citations (file names, headings) must not count as answers."""
    return re.sub(r"\[(?:source|data):[^\]]*\]", " ", text, flags=re.IGNORECASE)


def _content_reasons(numbers: tuple[NumberSpec, ...], phrases: tuple[tuple[str, ...], ...],
                     values: list[float], lower: str, golden: dict[str, float]) -> list[str]:
    """Why expected numbers or phrase groups are missing (empty when all are present)."""
    reasons = []
    for spec in numbers:
        target = golden[spec.golden]
        candidates = [target] + ([target / 100] if spec.also_fraction else [])
        tolerance = [spec.tolerance] + ([spec.tolerance / 100] if spec.also_fraction else [])
        if not any(abs(v - t) <= tol + 1e-9 for v in values
                   for t, tol in zip(candidates, tolerance, strict=True)):
            reasons.append(f"missing {spec.golden}={target:g} (+/-{spec.tolerance:g})")
    for group in phrases:
        if not any(normalise(p).lower() in lower for p in group):
            reasons.append(f"missing one of {list(group)}")
    return reasons


def score(question: Question, result: AgentResult, golden: dict[str, float]) -> Score:
    reasons: list[str] = []
    answer = normalise(result.answer)
    body = _strip_citations(answer)
    lower = body.lower()
    values = numbers_in(body)
    expect = question.expect

    correct = result.stop_reason == "answer"
    if not correct:
        reasons.append(f"stopped: {result.stop_reason}")
    missing = _content_reasons(expect.numbers, expect.phrases, values, lower, golden)
    if missing:
        correct = False
        reasons += missing
    if expect.any_of:
        tried = [_content_reasons(alt.numbers, alt.phrases, values, lower, golden)
                 for alt in expect.any_of]
        if all(tried):
            correct = False
            reasons.append("no alternative matched: " + " | ".join("; ".join(t) for t in tried))
    if expect.clarify and not any(p in lower for p in CLARIFY):
        correct = False
        reasons.append("neither asked for clarification nor stated an assumption")
    if question.strict_citations and result.citations_invalid:
        correct = False
        reasons.append(f"cited what it did not retrieve: {result.citations_invalid}")
    if expect.refusal and not declines(lower):
        correct = False
        reasons.append("did not decline")
    for text in question.expect.forbidden:
        if text.lower() in answer.lower():
            correct = False
            reasons.append(f"contains forbidden text {text!r}")

    called_ok = {s.name for s in result.steps if s.kind == "tool" and s.ok}
    tools_ok = True
    for required in question.tools:
        if not called_ok & set(required.split("|")):
            tools_ok = False
            reasons.append(f"tool not used: {required}")
    for forbidden in question.forbidden_tools:
        if forbidden in called_ok:
            tools_ok = False
            reasons.append(f"forbidden tool used: {forbidden}")

    cited = [c.split(":", 1)[1].split("#", 1)[0] for c in result.citations_valid
             if c.startswith("source:")]
    sources_ok = not question.sources or any(s in cited for s in question.sources)
    if not sources_ok:
        reasons.append(f"expected source not cited: {list(question.sources)}")

    total = len(result.citations_valid) + len(result.citations_invalid)
    return Score(
        question_id=question.id, category=question.category, correct=correct,
        tools_ok=tools_ok, sources_ok=sources_ok,
        citation_precision=len(result.citations_valid) / total if total else None,
        latency_s=round(result.latency_s, 3), prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        tool_calls=sum(1 for s in result.steps if s.kind == "tool"),
        stop_reason=result.stop_reason, reasons=reasons,
    )
