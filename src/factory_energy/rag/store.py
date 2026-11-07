"""Chroma-backed store of knowledge chunks, with cited passage search.

Embeddings are computed by our own ``Embedder`` and handed to Chroma, so the collection never
depends on Chroma's embedding-function registry. The collection records which embedder built
it; querying with a different one is refused instead of returning meaningless neighbours.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from factory_energy.rag.chunk import Chunk
from factory_energy.rag.embed import Embedder
from factory_energy.rag.settings import RagSettings

MAX_K = 20
MAX_QUERY_CHARS = 2000
BATCH = 64


@dataclass(frozen=True)
class Passage:
    source: str
    heading: str
    text: str
    score: float  # cosine similarity, 1 is identical
    page: int | None = None

    @property
    def citation(self) -> str:
        where = f"p.{self.page}" if self.page is not None else self.heading
        return f"{self.source}#{where}"


def open_client(settings: RagSettings) -> Any:
    """Embedded persistent Chroma by default, the Chroma server when CHROMA_HOST is set."""
    import chromadb
    from chromadb.config import Settings

    private = Settings(anonymized_telemetry=False)  # on-premises: no usage telemetry
    if settings.chroma_host:
        # The server may still be starting (compose, Kubernetes): retry for a while.
        deadline = time.monotonic() + settings.chroma_wait_seconds
        while True:
            try:
                client = chromadb.HttpClient(host=settings.chroma_host,
                                             port=settings.chroma_port, settings=private)
                client.heartbeat()
                return client
            except Exception:  # noqa: BLE001 - any connection failure means "not up yet"
                if time.monotonic() >= deadline:
                    raise
                time.sleep(2)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_path), settings=private)


def drop_collection(client: Any, name: str) -> None:
    """Delete a collection if it exists."""
    with contextlib.suppress(Exception):  # absent collection: nothing to drop
        client.delete_collection(name)


def persistent_client(path: Path) -> Any:
    """An embedded store in its own folder (used by the tests: isolated and long-lived)."""
    import chromadb
    from chromadb.config import Settings

    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def ephemeral_client() -> Any:
    import chromadb
    from chromadb.config import Settings

    return chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))


class KnowledgeStore:
    def __init__(self, client: Any, embedder: Embedder, collection: str) -> None:
        self.client = client
        self.embedder = embedder
        self.collection_name = collection
        self.collection = self._open()

    def _open(self) -> Any:
        collection = self.client.get_or_create_collection(
            self.collection_name,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"embedder": self.embedder.name},
        )
        built_with = (collection.metadata or {}).get("embedder")
        if built_with != self.embedder.name:
            raise ValueError(
                f"collection {self.collection_name!r} was built with {built_with!r}, not "
                f"{self.embedder.name!r}; run `rag ingest --rebuild`"
            )
        return collection

    def reset(self) -> None:
        """Drop and recreate the collection (used when the embedder changes)."""
        drop_collection(self.client, self.collection_name)
        self.collection = self._open()

    def count(self) -> int:
        return int(self.collection.count())

    def document_hashes(self) -> dict[str, str]:
        """source -> sha256 of the indexed version."""
        rows = self.collection.get(include=["metadatas"])
        return {str(m["source"]): str(m["sha256"]) for m in rows["metadatas"] or []}

    def remove(self, source: str) -> None:
        self.collection.delete(where={"source": source})

    def add(self, chunks: list[Chunk], sha256: str) -> None:
        for start in range(0, len(chunks), BATCH):
            batch = chunks[start:start + BATCH]
            self.collection.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                embeddings=self.embedder.embed([c.text for c in batch]),
                metadatas=[_metadata(c, sha256) for c in batch],
            )

    def search(self, query: str, k: int = 5, source_prefix: str = "") -> list[Passage]:
        query = query.strip()
        if not query:
            raise ValueError("query is empty")
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(f"query longer than {MAX_QUERY_CHARS} characters")
        if not 1 <= k <= MAX_K:
            raise ValueError(f"k must be between 1 and {MAX_K}")
        if self.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=self.embedder.embed_queries([query]),
            n_results=min(k * 3 if source_prefix else k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        passages = [
            Passage(
                source=str(meta["source"]),
                heading=str(meta["heading"]),
                text=str(text),
                score=round(1.0 - float(distance), 4),
                page=int(meta["page"]) if int(meta["page"]) > 0 else None,
            )
            for text, meta, distance in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0],
                strict=True,
            )
        ]
        if source_prefix:
            passages = [p for p in passages if p.source.startswith(source_prefix)]
        return passages[:k]

    def sources(self) -> Iterable[str]:
        return sorted(self.document_hashes())


def _metadata(chunk: Chunk, sha256: str) -> dict[str, str | int]:
    return {
        "source": chunk.source,
        "heading": chunk.heading,
        "chunk_index": chunk.index,
        "page": chunk.page or 0,
        "sha256": sha256,
    }
