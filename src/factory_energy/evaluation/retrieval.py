"""Retrieval quality on its own, without a model: does the right document come back?

For every question that names expected sources, the question text is searched and the rank of
the first expected document is recorded. Reported as hit@1, hit@3, hit@5 and mean reciprocal
rank per embedder, so a change of embedder or chunking is measured, not guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

from factory_energy.evaluation.questions import Question
from factory_energy.rag.store import KnowledgeStore

DEPTH = 5


@dataclass(frozen=True)
class RetrievalResult:
    question_id: str
    rank: int | None  # 1-based rank of the first expected document, None if not in the top DEPTH
    top: str  # source of the best passage


def evaluate_retrieval(store: KnowledgeStore, questions: list[Question]) -> list[RetrievalResult]:
    results = []
    for question in questions:
        if not question.sources:
            continue
        passages = store.search(question.question, k=DEPTH)
        rank = next((i for i, p in enumerate(passages, 1) if p.source in question.sources), None)
        results.append(RetrievalResult(question.id, rank, passages[0].source if passages else ""))
    return results


def metrics(results: list[RetrievalResult]) -> dict[str, float]:
    n = len(results) or 1
    return {
        "questions": float(len(results)),
        "hit@1": sum(r.rank == 1 for r in results) / n,
        "hit@3": sum(r.rank is not None and r.rank <= 3 for r in results) / n,
        "hit@5": sum(r.rank is not None for r in results) / n,
        "mrr": sum(1 / r.rank for r in results if r.rank) / n,
    }
