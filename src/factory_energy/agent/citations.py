"""Check the citations in an answer against what the run actually retrieved and called.

A ``[source: ...]`` citation is valid only if search_knowledge returned that passage in this run
(the file path alone, or a heading prefix, is accepted); a ``[data: tool]`` citation is valid
only if that tool was called successfully. Anything else is removed from the answer and reported.

Near-misses are resolved, but only to something this run really retrieved or called:

- a file name without its folder (``EM-02_demand_management.md#...``),
- a heading without its file (``EM-02 Demand Management > Key terms``), matched on whole
  " > " segments (never a partial word) and used only when exactly one retrieved passage has it,
- a document title alone (``EM-03 Tariff Guide``), resolved to the document itself when every
  retrieved passage with that title comes from one file (a document-level citation),
- a tool name written as a source (``[source: get_energy]``),
- a tool name followed by extra words (``[data: get_meter_series MDB-3]``), or written without
  ``get_`` and with spaces (``[source: plant overview]`` for get_plant_overview),
- a citation nested in another (``[source: data: get_demand]``),
- several citations in one bracket (``[data: get_plant_overview, get_demand]``), accepted only
  if every part resolves.

A resolved citation is rewritten in canonical form and reported in ``repaired``, so a reader can
see how many citations needed help. Ambiguous or unsupported citations are still removed.

Typographic hyphens and spaces (``energy‑management`` with a non-breaking hyphen), full-width
brackets and colons (``【data: get_demand】``, which Nemotron writes) and backticks around the
value are read as plain ones first; that is a spelling of the same citation, not a repair.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Plain or full-width brackets and colon: "[data: x]", "【data: x】", "［data：x］".
CITATION = re.compile(r"([\[【［])\s*(source|data)\s*([:：])\s*([^\]】］]+?)\s*([\]】］])",
                      re.IGNORECASE)
NESTED = re.compile(r"(source|data)\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)
REMOVED = "[unverified citation removed]"
# Hyphens and spaces some models write in place of plain ones (Nemotron writes U+2011 and U+202F).
PLAIN_PUNCTUATION = {0x2010: "-", 0x2011: "-", 0x00A0: " ", 0x202F: " "}


@dataclass
class CitationReport:
    answer: str
    valid: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    repaired: list[str] = field(default_factory=list)  # "as written -> canonical"


def _source_ok(cited: str, retrieved: set[str]) -> str | None:
    if cited in retrieved:
        return cited
    for citation in sorted(retrieved):
        path = citation.split("#", 1)[0]
        if cited == path or (cited.startswith(path + "#") and citation.startswith(cited)):
            return citation
    return None


def _unique(matches: list[str]) -> str | None:
    return matches[0] if len(set(matches)) == 1 else None


def _segments_start(heading: str, wanted: str) -> bool:
    """True if ``wanted`` equals the leading whole segments of a "A > B > C" heading path."""
    have, want = heading.split(" > "), wanted.split(" > ")
    return have[: len(want)] == want


def _same_document(title: str, citation: str) -> bool:
    """True if ``title`` names the document of a retrieved citation: it equals the heading's first
    " > " segment, or is a whole-word prefix of that segment or of the file stem (so "SOP-06"
    fits "SOP-06 Heat Wave Pre-cooling" and "SOP-06_heat_wave", but "SOP-0" fits neither)."""
    path, _, heading = citation.partition("#")
    first = heading.split(" > ", 1)[0].strip().lower()
    stem = path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    wanted = title.strip().lower()
    if not wanted:
        return False
    if wanted == first:
        return True
    prefix = re.compile(re.escape(wanted) + r"(?![a-z0-9])")
    return bool(prefix.match(first) or prefix.match(stem))


def _names_document(title: str, citation: str) -> bool:
    """True if ``title`` is the whole name of a retrieved citation's document: its heading's first
    " > " segment, its file stem, or its code alone ("EM-03" for "EM-03 Tariff Guide"). A longer
    partial title ("EM-03 Tariff") is not a name."""
    path, _, heading = citation.partition("#")
    first = heading.split(" > ", 1)[0].strip().lower()
    stem = path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    wanted = title.strip().lower()
    return bool(wanted) and wanted in {first, stem, first.split(" ", 1)[0]}


def _resolve_source(cited: str, retrieved: set[str]) -> str | None:
    """A retrieved citation that a malformed one unambiguously means, or None. A heading counts
    only as whole " > " segments (never a partial word) and only if exactly one passage has it."""
    name, _, heading = cited.partition("#")
    if name.endswith((".md", ".txt", ".pdf")):  # a file name without its folder
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        same_file = [c for c in sorted(retrieved) if c.split("#", 1)[0].endswith("/" + base)]
        if not heading:
            return _unique([c.split("#", 1)[0] for c in same_file])
        return _unique([c for c in same_file if _segments_start(c.split("#", 1)[1], heading)])
    wanted = heading or cited  # "Doc title#heading" or a bare heading
    pool = sorted(retrieved)
    if heading:  # a title was given: only passages of that document qualify
        pool = [c for c in pool if _same_document(name, c)]
    exact = [c for c in pool if c.split("#", 1)[-1] == wanted]
    if exact:
        return _unique(exact)
    passage = _unique([c for c in pool if _segments_start(c.split("#", 1)[-1], wanted)])
    if passage or heading or " > " in cited:
        return passage
    # A bare document name ("EM-03 Tariff Guide", or just "EM-03") with several passages of
    # that document retrieved: cite the document, as long as the name fits only one file.
    return _unique([c.split("#", 1)[0] for c in pool if _names_document(cited, c)])


def _resolve_tool(value: str, tools_ok: set[str]) -> str | None:
    """The called tool a value names: its exact name followed by extra words, or its name without
    ``get_`` and with spaces ("plant overview"), matched on whole words. A one-word name such as
    "demand" or "energy" is too common in prose to count without ``get_``."""
    words = value.replace("(", " ").split()
    if words and words[0] in tools_ok:
        return words[0]
    spaced = " ".join(value.replace("_", " ").lower().split())
    names = {tool: tool.removeprefix("get_").replace("_", " ") for tool in sorted(tools_ok)}
    return _unique([tool for tool, name in names.items()
                    if " " in name and re.match(re.escape(name) + r"(?![a-z0-9])", spaced)])


Resolved = tuple[str, str, str]  # kind, citation recorded as valid, citation shown in the answer


def _resolve(kind: str, value: str, retrieved: set[str], tools_ok: set[str]) -> Resolved | None:
    nested = NESTED.fullmatch(value)
    if nested:  # "[source: data: get_demand]"
        kind, value = nested.group(1).lower(), nested.group(2).strip()
    if kind == "source":
        resolved = _source_ok(value, retrieved)
        if resolved:
            return "source", resolved, value
        fixed = _resolve_source(value, retrieved)
        if fixed:
            return "source", fixed, fixed
    elif value in tools_ok:
        return "data", value, value
    tool = _resolve_tool(value, tools_ok)
    return ("data", tool, tool) if tool else None


def check(answer: str, retrieved: set[str], tools_ok: set[str]) -> CitationReport:
    report = CitationReport(answer)

    def replace(match: re.Match[str]) -> str:
        opening, kind, colon, written, closing = match.groups()
        kind = kind.lower()
        value = written.translate(PLAIN_PUNCTUATION).strip("` ")
        hit = _resolve(kind, value, retrieved, tools_ok)
        parts = [hit] if hit else None
        if parts is None and re.search(r"[,;]", value):  # several citations in one bracket
            pieces = [_resolve(kind, piece.strip("` "), retrieved, tools_ok)
                      for piece in re.split(r"[,;]", value) if piece.strip("` ")]
            if pieces and all(pieces):
                parts = [piece for piece in pieces if piece]
        if not parts:
            report.invalid.append(f"{kind}:{value}")
            return REMOVED
        report.valid += [f"{k}:{recorded}" for k, recorded, _ in parts]
        shown = " ".join(f"[{k}: {s}]" for k, _, s in parts)
        if len(parts) == 1 and parts[0][0] == kind and parts[0][2] == value:  # not a repair
            plain = (opening, colon, closing) == ("[", ":", "]") and value == written
            return match.group(0) if plain else shown
        report.repaired.append(f"{kind}:{value} -> " + ", ".join(f"{k}:{s}" for k, _, s in parts))
        return shown

    report.answer = CITATION.sub(replace, answer)
    report.valid = list(dict.fromkeys(report.valid))
    return report
