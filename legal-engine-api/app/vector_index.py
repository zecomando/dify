from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from app.repository import LegalChunkRecord, LegalRepository, SearchableChunkRecord, utc_now_iso

LOCAL_EMBEDDING_MODEL = "legal-local-hash-embedding-v1"
LOCAL_EMBEDDING_DIMENSIONS = 64


class EmbeddingProvider(Protocol):
    model_name: str
    dimensions: int

    def embed(self, text: str) -> tuple[float, ...]: ...


class VectorStore(Protocol):
    def search(
        self,
        *,
        query_embedding: tuple[float, ...],
        embedding_model: str,
        current_only: bool,
    ) -> tuple["VectorSearchResult", ...]: ...


class LocalHashEmbeddingProvider:
    model_name = LOCAL_EMBEDDING_MODEL
    dimensions = LOCAL_EMBEDDING_DIMENSIONS

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in _expanded_tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize_vector(tuple(vector))


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    chunk: SearchableChunkRecord
    dense_score: float
    vector_id: str | None


class LocalVectorStore:
    def __init__(self, repository: LegalRepository) -> None:
        self.repository = repository

    def search(
        self,
        *,
        query_embedding: tuple[float, ...],
        embedding_model: str,
        current_only: bool,
    ) -> tuple[VectorSearchResult, ...]:
        results: list[VectorSearchResult] = []
        for chunk in self.repository.list_searchable_chunks(current_only=current_only):
            embedding = self.repository.get_chunk_embedding(chunk.chunk_id, model=embedding_model)
            dense_score = cosine_similarity(query_embedding, embedding.vector) if embedding is not None else 0.0
            results.append(
                VectorSearchResult(
                    chunk=chunk,
                    dense_score=dense_score,
                    vector_id=embedding.vector_id if embedding is not None else None,
                )
            )
        return tuple(results)


def index_chunk_embedding(
    repository: LegalRepository,
    chunk: LegalChunkRecord,
    provider: EmbeddingProvider | None = None,
) -> None:
    embedding_provider = provider or LocalHashEmbeddingProvider()
    vector = embedding_provider.embed(chunk.text_content)
    repository.save_chunk_embedding(
        chunk_id=chunk.id,
        model=embedding_provider.model_name,
        dimensions=embedding_provider.dimensions,
        vector=vector,
        vector_id=_vector_id(embedding_provider.model_name, chunk.id),
        timestamp=utc_now_iso(),
    )


def index_chunk_embeddings(
    repository: LegalRepository,
    chunks: tuple[LegalChunkRecord, ...],
    provider: EmbeddingProvider | None = None,
) -> None:
    embedding_provider = provider or LocalHashEmbeddingProvider()
    timestamp = utc_now_iso()
    for chunk in chunks:
        repository.save_chunk_embedding(
            chunk_id=chunk.id,
            model=embedding_provider.model_name,
            dimensions=embedding_provider.dimensions,
            vector=embedding_provider.embed(chunk.text_content),
            vector_id=_vector_id(embedding_provider.model_name, chunk.id),
            timestamp=timestamp,
        )


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    score = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    return max(score, 0.0)


def _expanded_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in _tokens(text):
        tokens.append(token)
        tokens.extend(_SYNONYMS.get(token, ()))
    return tuple(tokens)


def _tokens(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    return tuple(token for token in re.findall(r"\w+", without_accents) if len(token) > 2)


def _normalize_vector(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return tuple(value / norm for value in vector)


def _vector_id(model_name: str, chunk_id: str) -> str:
    return f"{model_name}:{chunk_id}"


_SYNONYMS: dict[str, tuple[str, ...]] = {
    "indemnizacao": ("responsabilidade", "civil", "dano", "danos"),
    "indenizacao": ("responsabilidade", "civil", "dano", "danos"),
    "dano": ("danos", "responsabilidade", "civil"),
    "danos": ("dano", "responsabilidade", "civil"),
    "responsabilidade": ("civil", "dano", "danos", "indemnizacao"),
    "rgpd": ("dados", "pessoais", "protecao", "privacidade"),
    "privacidade": ("rgpd", "dados", "pessoais"),
    "laboral": ("trabalho", "trabalhador", "despedimento"),
    "despedimento": ("laboral", "trabalho", "trabalhador"),
    "contratacao": ("publica", "concurso", "adjudicacao"),
    "concurso": ("contratacao", "publica", "adjudicacao"),
    "adjudicacao": ("contratacao", "publica", "concurso"),
}
