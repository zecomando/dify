from __future__ import annotations

from typing import Protocol

from app.schemas import RetrievalResult

LOCAL_RERANKER_MODEL = "legal-local-score-reranker-v1"


class RerankerProvider(Protocol):
    model_name: str

    def rerank(
        self,
        *,
        query: str,
        results: tuple[RetrievalResult, ...],
        top_n: int,
    ) -> tuple[RetrievalResult, ...]: ...


class LocalScoreRerankerProvider:
    model_name = LOCAL_RERANKER_MODEL

    def rerank(
        self,
        *,
        query: str,
        results: tuple[RetrievalResult, ...],
        top_n: int,
    ) -> tuple[RetrievalResult, ...]:
        ordered = sorted(results, key=lambda result: result.score, reverse=True)
        return tuple(ordered[:top_n])
