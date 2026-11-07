"""Guardrails around the model: retrieved-text quarantine, output filtering, tool-call limits.

Defence in depth. No single layer is trusted to stop prompt injection:

1. ``quarantine`` removes instruction-like text from retrieved documents before the model sees
   them (zero-width characters and HTML comments are stripped first, so hidden payloads become
   visible to the patterns), and reports what it removed;
2. the system prompt tells the model that tool text is data, never instructions;
3. write tools are disabled unless explicitly enabled, and ``ToolBudget`` caps tool calls per
   run and repeated identical calls;
4. ``guard_output`` redacts secret-like strings and external links from the answer and replaces
   an answer that reproduces the system prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
INSTRUCTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in (
        ("override", r"\b(ignore|disregard|forget)\b[^.\n]{0,40}"
                     r"\b(instructions?|prompts?|rules)\b"),
        ("system_prompt", r"\b(system|hidden|internal)\s+(prompt|instructions?|configuration)\b"),
        ("role_block", r"^\s*(system|assistant|developer)\s*:"),
        ("addressed_to_ai", r"\b(assistants?|ai systems?|language models?|chatbots?)\b\s*"
                            r"(must|should|:|reading this)"),
        ("persona", r"\b(from now on you are|you are now|act as|pretend to be)\b"),
        ("mode_switch", r"\b(maintenance|developer|debug|god)\s+mode\s+(enabled|on|activated)\b"
                        r"|\b(enter|switch to|activate)\w*\s+(maintenance|developer|debug|god)\s+"
                        r"mode"),
        ("tool_call", r"\bcall\b[^.\n]{0,30}\b(tool|generate_report|detect_anomalies|"
                      r"search_knowledge|get_\w+)\b"),
        ("answer_format", r"\b(reply|respond|answer|sign off|end (every|your) (answer|reply))\b"
                          r"[^.\n]{0,40}\b(only|exact|format|with|first line)\b"),
        ("append_phrase", r"\b(append|include|add|say|write)\b[^.\n]{0,30}\b(phrase|words?|code|"
                          r"image|at the end)\b"),
        ("fact_override", r"\bimportant fact\b|\balways report\b"),
    )
)
SENTENCE = re.compile(r"[^.!?\n]*(?:[.!?]+|\n|$)")
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
# External links (Markdown or bare). Loopback addresses in the project's own docs are allowed.
LINK = re.compile(r"!?\[[^\]]*\]\(\s*https?://[^)]*\)"
                  r"|https?://(?!(?:127\.0\.0\.1|localhost)[:/])[^\s)\]]+")
LEAK_WINDOW = 8  # words in a row shared with the system prompt that count as a leak
REMOVED = "[removed: instruction-like text]"


@dataclass
class Finding:
    layer: str  # "quarantine", "output", "tool_budget"
    kind: str
    detail: str


@dataclass
class Quarantined:
    text: str
    findings: list[Finding] = field(default_factory=list)


def quarantine(text: str) -> Quarantined:
    """Strip hidden carriers, then drop every sentence or line that reads as an instruction."""
    findings: list[Finding] = []
    if ZERO_WIDTH.search(text):
        findings.append(Finding("quarantine", "zero_width", "zero-width characters removed"))
        text = ZERO_WIDTH.sub("", text)
    if HTML_COMMENT.search(text):
        findings.append(Finding("quarantine", "html_comment", "HTML comment removed"))
        text = HTML_COMMENT.sub("", text)
    # Links go first and whole: their dots and question marks would split a sentence apart.
    for link in LINK.findall(text):
        findings.append(Finding("quarantine", "external_link", link[:120]))
    text = LINK.sub(REMOVED, text)
    kept: list[str] = []
    for line in text.split("\n"):
        pieces: list[str] = []
        for sentence in SENTENCE.findall(line):
            hit = next((name for name, p in INSTRUCTION_PATTERNS if p.search(sentence)), None)
            if hit:
                findings.append(Finding("quarantine", hit, sentence.strip()[:120]))
                if not pieces or pieces[-1] != REMOVED:
                    pieces.append(REMOVED)
            elif sentence:
                pieces.append(sentence.strip())
        kept.append(" ".join(p for p in pieces if p))
    return Quarantined("\n".join(kept), findings)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def leaks_prompt(answer: str, system_prompt: str, window: int = LEAK_WINDOW) -> bool:
    """True if the answer repeats `window` consecutive words of the system prompt."""
    prompt = _words(system_prompt)
    grams = {tuple(prompt[i:i + window]) for i in range(len(prompt) - window + 1)}
    words = _words(answer)
    return any(tuple(words[i:i + window]) in grams for i in range(len(words) - window + 1))


def guard_output(answer: str, system_prompt: str) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    if leaks_prompt(answer, system_prompt):
        findings.append(Finding("output", "prompt_leak", "answer reproduced the system prompt"))
        return "I can't share my instructions. Ask me about the plant instead.", findings
    for pattern in SECRET_PATTERNS:
        if pattern.search(answer):
            findings.append(Finding("output", "secret", pattern.pattern))
            answer = pattern.sub("[redacted]", answer)
    if LINK.search(answer):
        findings.append(Finding("output", "external_link", LINK.search(answer).group(0)[:80]))  # type: ignore[union-attr]
        answer = LINK.sub("[link removed]", answer)
    return answer, findings


@dataclass
class ToolBudget:
    """Caps tool calls per run and refuses the same call (tool + arguments) more than twice."""

    max_calls: int = 16
    max_repeats: int = 2
    calls: int = 0
    seen: dict[str, int] = field(default_factory=dict)

    def check(self, name: str, arguments: str) -> str:
        """Empty string if allowed, otherwise the reason for refusing."""
        key = f"{name}:{arguments}"
        if self.calls >= self.max_calls:
            return f"tool budget exhausted ({self.max_calls} calls per question)"
        if self.seen.get(key, 0) >= self.max_repeats:
            return f"identical call to {name} refused after {self.max_repeats} repeats"
        self.calls += 1
        self.seen[key] = self.seen.get(key, 0) + 1
        return ""
