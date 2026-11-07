"""Discover the knowledge documents and keep the store in step with them.

A document is re-indexed only when its SHA-256 changed; documents that disappeared are removed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from factory_energy.rag.chunk import Chunk, chunk_markdown, chunk_pdf
from factory_energy.rag.settings import REPO_ROOT
from factory_energy.rag.store import KnowledgeStore

# The generated plant corpus plus the project's own technical documentation.
DEFAULT_SOURCES = (
    "docs/knowledge",
    "docs/simulator.md",
    "docs/scenarios.md",
    "docs/anomaly_detection.md",
    "docs/forecasting.md",
    "docs/dashboard.md",
)
SUFFIXES = {".md", ".txt", ".pdf"}


@dataclass
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    chunks: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


def discover(paths: tuple[str, ...] = DEFAULT_SOURCES, root: Path = REPO_ROOT) -> list[Path]:
    found: set[Path] = set()
    for item in paths:
        path = root / item
        if path.is_dir():
            found.update(p for p in path.rglob("*") if p.is_file() and p.suffix in SUFFIXES)
        elif path.is_file() and path.suffix in SUFFIXES:
            found.add(path)
    return sorted(found)


def relative(path: Path, root: Path = REPO_ROOT) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_chunks(path: Path, source: str) -> list[Chunk]:
    if path.suffix == ".pdf":
        return chunk_pdf(path, source)
    return chunk_markdown(path.read_text(encoding="utf-8"), source)


def ingest(store: KnowledgeStore, files: list[Path], root: Path = REPO_ROOT) -> IngestReport:
    report = IngestReport()
    indexed = store.document_hashes()
    seen: set[str] = set()
    for path in files:
        source = relative(path, root)
        seen.add(source)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if indexed.get(source) == digest:
            report.unchanged.append(source)
            continue
        chunks = load_chunks(path, source)
        if source in indexed:
            store.remove(source)
            report.updated.append(source)
        else:
            report.added.append(source)
        store.add(chunks, digest)
        report.chunks += len(chunks)
    for source in sorted(set(indexed) - seen):
        store.remove(source)
        report.removed.append(source)
    return report
