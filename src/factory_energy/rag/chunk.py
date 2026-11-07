"""Split documents into citable chunks.

Markdown is split on headings first, so a chunk never spans two sections and always carries its
heading path ("Title > Section > Subsection") for citations. Long sections are then cut into
overlapping windows on paragraph boundaries. PDFs are chunked per page with the page number kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
MAX_CHARS = 1600  # about 400 tokens of English text
OVERLAP_CHARS = 240  # about 15 %


@dataclass(frozen=True)
class Chunk:
    source: str  # path relative to the repository root, forward slashes
    heading: str  # heading path, or "page N" for PDFs
    text: str
    index: int  # position of the chunk within its document
    page: int | None = None

    @property
    def chunk_id(self) -> str:
        return f"{self.source}#{self.index}"


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading path, body) pairs in document order; fenced code is never read as a heading."""
    path: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else HEADING.match(line)
        if match:
            level, title = len(match.group(1)), match.group(2).strip()
            path = [(lvl, name) for lvl, name in path if lvl < level] + [(level, title)]
            sections.append((" > ".join(name for _, name in path), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(body).strip()) for heading, body in sections]


def _windows(body: str, max_chars: int, overlap: int) -> list[str]:
    """Cut a long body into windows of whole paragraphs, repeating the tail as overlap."""
    if len(body) <= max_chars:
        return [body]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    windows: list[str] = []
    current: list[str] = []
    for paragraph in paragraphs:
        pieces = [paragraph[i:i + max_chars] for i in range(0, len(paragraph), max_chars)]
        for piece in pieces:
            if current and len("\n\n".join([*current, piece])) > max_chars:
                windows.append("\n\n".join(current))
                tail = windows[-1][-overlap:] if overlap else ""
                current = [tail] if tail else []
            current.append(piece)
    if current:
        windows.append("\n\n".join(current))
    return windows


def chunk_markdown(
    text: str, source: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS
) -> list[Chunk]:
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")
    chunks: list[Chunk] = []
    for heading, body in _sections(text):
        if not body:
            continue
        for window in _windows(body, max_chars, overlap):
            # The heading is repeated in the text so the embedding sees the section's topic.
            content = f"{heading}\n\n{window}" if heading else window
            chunks.append(Chunk(source, heading or Path(source).stem, content, len(chunks)))
    return chunks


def chunk_pdf(
    path: Path, source: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS
) -> list[Chunk]:
    from pypdf import PdfReader

    chunks: list[Chunk] = []
    for number, page in enumerate(PdfReader(path).pages, start=1):
        text = (page.extract_text() or "").strip()
        for window in _windows(text, max_chars, overlap) if text else []:
            chunks.append(Chunk(source, f"page {number}", window, len(chunks), page=number))
    return chunks
