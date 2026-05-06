from __future__ import annotations

import importlib
import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast


SCHEMA_VERSION = "0005_answer_prompt_versions"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class DatabaseCursor(Protocol):
    def fetchone(self) -> tuple[object, ...] | None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...


class DatabaseConnection(Protocol):
    def execute(self, sql: str, parameters: Sequence[object] = ()) -> DatabaseCursor: ...

    def executemany(self, sql: str, parameters: Iterable[Sequence[object]]) -> object: ...

    def executescript(self, sql: str) -> object: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class _PsycopgCursor(Protocol):
    def execute(self, query: str, params: Sequence[object] | None = None) -> object: ...

    def executemany(self, query: str, params_seq: Iterable[Sequence[object]]) -> object: ...

    def fetchone(self) -> tuple[object, ...] | None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...


class _PsycopgConnection(Protocol):
    def cursor(self) -> _PsycopgCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class _PostgresConnection:
    def __init__(self, connection: _PsycopgConnection) -> None:
        self._connection = connection

    def execute(self, sql: str, parameters: Sequence[object] = ()) -> DatabaseCursor:
        cursor = self._connection.cursor()
        cursor.execute(_postgres_sql(sql), _postgres_parameters(parameters))
        return cast(DatabaseCursor, cursor)

    def executemany(self, sql: str, parameters: Iterable[Sequence[object]]) -> object:
        cursor = self._connection.cursor()
        return cursor.executemany(_postgres_sql(sql), tuple(_postgres_parameters(item) for item in parameters))

    def executescript(self, sql: str) -> object:
        for statement in _split_sql_script(sql):
            self.execute(statement)
        return None

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


@dataclass(frozen=True, slots=True)
class LegalDocumentRecord:
    id: str
    source: str
    jurisdiction: str
    document_type: str
    title: str
    source_url: str
    status: str
    sha256: str
    is_current: bool
    is_consolidated: bool
    legal_value_warning: str
    area: tuple[str, ...]
    legal_metadata: dict[str, str]
    created_at: str
    updated_at: str
    version_label: str = "current"
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes_document_id: str | None = None
    archived_at: str | None = None
    change_note: str = ""


@dataclass(frozen=True, slots=True)
class LegalChunkRecord:
    id: str
    document_id: str
    chunk_type: str
    structural_path: str | None
    citation_label: str | None
    text_content: str
    token_count: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class SearchableChunkRecord:
    chunk_id: str
    document_id: str
    source: str
    jurisdiction: str
    document_type: str
    area: tuple[str, ...]
    legal_metadata: dict[str, str]
    source_url: str
    is_current: bool
    is_consolidated: bool
    legal_value_warning: str
    chunk_type: str
    citation_label: str | None
    text_content: str
    token_count: int | None
    version_label: str = "current"
    valid_from: str | None = None
    valid_until: str | None = None


@dataclass(frozen=True, slots=True)
class LegalChunkEmbeddingRecord:
    chunk_id: str
    model: str
    dimensions: int
    vector: tuple[float, ...]
    vector_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IngestionJobRecord:
    id: str
    source: str
    source_url: str
    requested_by: str | None
    mode: str
    status: str
    error_message: str | None
    document_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AnswerAuditRecord:
    id: str
    session_id: str | None
    user_id: str | None
    user_query: str
    normalized_query: str
    detected_area_json: str
    detected_jurisdiction_json: str
    detected_document_types_json: str
    mode: str
    retrieved_chunks_json: str
    reranked_chunks_json: str
    evidence_json: str
    draft_answer: str
    validator_report_json: str
    final_answer: str
    confidence: str
    abstained: bool
    verdict: str
    model_generator: str | None
    model_validator: str | None
    generator_prompt_version: str | None
    validator_prompt_version: str | None
    embedding_model: str | None
    reranker_model: str | None
    latency_ms: int
    estimated_cost_usd: float
    created_at: str


@dataclass(frozen=True, slots=True)
class AnswerFeedbackRecord:
    id: str
    audit_id: str
    rating: str
    category: str | None
    comment: str | None
    user_id: str | None
    session_id: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class EvaluationRunRecord:
    id: str
    passed: bool
    total_cases: int
    successful_cases: int
    failed_cases: int
    metrics_json: str
    quality_gates_json: str
    failed_cases_json: str
    evals_dir: str
    created_at: str


class LegalRepository:
    def __init__(self, database_path: Path, database_url: str | None = None) -> None:
        self.database_path = database_path
        self.database_url = database_url
        if self.database_url is None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    @property
    def backend(self) -> str:
        return "postgresql" if self.database_url is not None else "sqlite"

    def initialize_schema(self) -> None:
        _validate_schema_migration_files()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS legal_documents (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    is_current INTEGER NOT NULL,
                    is_consolidated INTEGER NOT NULL,
                    legal_value_warning TEXT NOT NULL,
                    area_json TEXT NOT NULL,
                    legal_metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version_label TEXT NOT NULL DEFAULT 'current',
                    valid_from TEXT,
                    valid_until TEXT,
                    supersedes_document_id TEXT REFERENCES legal_documents(id),
                    archived_at TEXT,
                    change_note TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_legal_documents_source ON legal_documents(source);
                CREATE INDEX IF NOT EXISTS idx_legal_documents_jurisdiction ON legal_documents(jurisdiction);
                CREATE INDEX IF NOT EXISTS idx_legal_documents_type ON legal_documents(document_type);
                CREATE INDEX IF NOT EXISTS idx_legal_documents_status ON legal_documents(status);
                CREATE INDEX IF NOT EXISTS idx_legal_documents_sha256 ON legal_documents(sha256);

                CREATE TABLE IF NOT EXISTS legal_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES legal_documents(id),
                    chunk_type TEXT NOT NULL,
                    structural_path TEXT,
                    citation_label TEXT,
                    text_content TEXT NOT NULL,
                    token_count INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_legal_chunks_document_id ON legal_chunks(document_id);
                CREATE INDEX IF NOT EXISTS idx_legal_chunks_chunk_type ON legal_chunks(chunk_type);

                CREATE TABLE IF NOT EXISTS legal_chunk_embeddings (
                    chunk_id TEXT PRIMARY KEY REFERENCES legal_chunks(id) ON DELETE CASCADE,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    vector_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_legal_chunk_embeddings_model ON legal_chunk_embeddings(model);

                CREATE TABLE IF NOT EXISTS legal_document_raw_texts (
                    document_id TEXT PRIMARY KEY REFERENCES legal_documents(id) ON DELETE CASCADE,
                    raw_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS source_ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    requested_by TEXT,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    document_id TEXT REFERENCES legal_documents(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_source_ingestion_jobs_status ON source_ingestion_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_source_ingestion_jobs_source ON source_ingestion_jobs(source);

                CREATE TABLE IF NOT EXISTS answer_audits (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    user_id TEXT,
                    user_query TEXT NOT NULL,
                    normalized_query TEXT NOT NULL,
                    detected_area_json TEXT NOT NULL,
                    detected_jurisdiction_json TEXT NOT NULL,
                    detected_document_types_json TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    retrieved_chunks_json TEXT NOT NULL,
                    reranked_chunks_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    draft_answer TEXT NOT NULL,
                    validator_report_json TEXT NOT NULL,
                    final_answer TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    abstained INTEGER NOT NULL,
                    verdict TEXT NOT NULL,
                    model_generator TEXT,
                    model_validator TEXT,
                    generator_prompt_version TEXT,
                    validator_prompt_version TEXT,
                    embedding_model TEXT,
                    reranker_model TEXT,
                    latency_ms INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_answer_audits_session ON answer_audits(session_id);
                CREATE INDEX IF NOT EXISTS idx_answer_audits_user ON answer_audits(user_id);
                CREATE INDEX IF NOT EXISTS idx_answer_audits_created_at ON answer_audits(created_at);
                CREATE INDEX IF NOT EXISTS idx_answer_audits_verdict ON answer_audits(verdict);
                CREATE INDEX IF NOT EXISTS idx_answer_audits_abstained ON answer_audits(abstained);

                CREATE TABLE IF NOT EXISTS answer_feedback (
                    id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES answer_audits(id) ON DELETE CASCADE,
                    rating TEXT NOT NULL,
                    category TEXT,
                    comment TEXT,
                    user_id TEXT,
                    session_id TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_answer_feedback_audit ON answer_feedback(audit_id);
                CREATE INDEX IF NOT EXISTS idx_answer_feedback_rating ON answer_feedback(rating);
                CREATE INDEX IF NOT EXISTS idx_answer_feedback_created_at ON answer_feedback(created_at);

                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id TEXT PRIMARY KEY,
                    passed INTEGER NOT NULL,
                    total_cases INTEGER NOT NULL,
                    successful_cases INTEGER NOT NULL,
                    failed_cases INTEGER NOT NULL,
                    metrics_json TEXT NOT NULL,
                    quality_gates_json TEXT NOT NULL,
                    failed_cases_json TEXT NOT NULL,
                    evals_dir TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created_at ON evaluation_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_passed ON evaluation_runs(passed);

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )
            _validate_applied_schema_migrations(connection)
            _ensure_column(
                connection,
                self.backend,
                "legal_documents",
                "legal_metadata_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            _ensure_column(
                connection,
                self.backend,
                "legal_documents",
                "version_label",
                "TEXT NOT NULL DEFAULT 'current'",
            )
            _ensure_column(connection, self.backend, "legal_documents", "valid_from", "TEXT")
            _ensure_column(connection, self.backend, "legal_documents", "valid_until", "TEXT")
            _ensure_column(connection, self.backend, "legal_documents", "supersedes_document_id", "TEXT")
            _ensure_column(connection, self.backend, "legal_documents", "archived_at", "TEXT")
            _ensure_column(
                connection,
                self.backend,
                "legal_documents",
                "change_note",
                "TEXT NOT NULL DEFAULT ''",
            )
            _ensure_column(connection, self.backend, "answer_feedback", "category", "TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_answer_feedback_category ON answer_feedback(category)")
            _ensure_column(connection, self.backend, "legal_chunk_embeddings", "vector_id", "TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_legal_chunk_embeddings_vector_id ON legal_chunk_embeddings(vector_id)"
            )
            _ensure_column(connection, self.backend, "answer_audits", "generator_prompt_version", "TEXT")
            _ensure_column(connection, self.backend, "answer_audits", "validator_prompt_version", "TEXT")
            _record_schema_migrations_from_files(connection)
            _record_schema_migration(connection, SCHEMA_VERSION)

    def create_document(self, document: LegalDocumentRecord) -> LegalDocumentRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO legal_documents (
                    id,
                    source,
                    jurisdiction,
                    document_type,
                    title,
                    source_url,
                    status,
                    sha256,
                    is_current,
                    is_consolidated,
                    legal_value_warning,
                    area_json,
                    legal_metadata_json,
                    created_at,
                    updated_at,
                    version_label,
                    valid_from,
                    valid_until,
                    supersedes_document_id,
                    archived_at,
                    change_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.source,
                    document.jurisdiction,
                    document.document_type,
                    document.title,
                    document.source_url,
                    document.status,
                    document.sha256,
                    int(document.is_current),
                    int(document.is_consolidated),
                    document.legal_value_warning,
                    json.dumps(list(document.area), ensure_ascii=False),
                    json.dumps(document.legal_metadata, ensure_ascii=False),
                    document.created_at,
                    document.updated_at,
                    document.version_label,
                    document.valid_from,
                    document.valid_until,
                    document.supersedes_document_id,
                    document.archived_at,
                    document.change_note,
                ),
            )
        return document

    def create_chunk(self, chunk: LegalChunkRecord) -> LegalChunkRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO legal_chunks (
                    id,
                    document_id,
                    chunk_type,
                    structural_path,
                    citation_label,
                    text_content,
                    token_count,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.chunk_type,
                    chunk.structural_path,
                    chunk.citation_label,
                    chunk.text_content,
                    chunk.token_count,
                    chunk.created_at,
                ),
            )
        return chunk

    def save_chunk_embedding(
        self,
        *,
        chunk_id: str,
        model: str,
        dimensions: int,
        vector: tuple[float, ...],
        vector_id: str,
        timestamp: str,
    ) -> LegalChunkEmbeddingRecord:
        vector_json = json.dumps(list(vector), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO legal_chunk_embeddings (
                    chunk_id,
                    model,
                    dimensions,
                    vector_json,
                    vector_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    model = excluded.model,
                    dimensions = excluded.dimensions,
                    vector_json = excluded.vector_json,
                    vector_id = excluded.vector_id,
                    updated_at = excluded.updated_at
                """,
                (chunk_id, model, dimensions, vector_json, vector_id, timestamp, timestamp),
            )
        return LegalChunkEmbeddingRecord(
            chunk_id=chunk_id,
            model=model,
            dimensions=dimensions,
            vector=vector,
            vector_id=vector_id,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def get_chunk_embedding(self, chunk_id: str, *, model: str | None = None) -> LegalChunkEmbeddingRecord | None:
        clauses = ["chunk_id = ?"]
        params: list[object] = [chunk_id]
        if model is not None:
            clauses.append("model = ?")
            params.append(model)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT
                    chunk_id,
                    model,
                    dimensions,
                    vector_json,
                    vector_id,
                    created_at,
                    updated_at
                FROM legal_chunk_embeddings
                WHERE {" AND ".join(clauses)}
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if row is None:
            return None
        return _chunk_embedding_from_row(row)

    def count_chunk_embeddings(self, *, model: str | None = None) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if model is not None:
            clauses.append("model = ?")
            params.append(model)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM legal_chunk_embeddings
                {where_clause}
                """,
                tuple(params),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def save_document_raw_text(self, document_id: str, raw_text: str, timestamp: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO legal_document_raw_texts (
                    document_id,
                    raw_text,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    raw_text = excluded.raw_text,
                    updated_at = excluded.updated_at
                """,
                (document_id, raw_text, timestamp, timestamp),
            )

    def create_job(self, job: IngestionJobRecord) -> IngestionJobRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_ingestion_jobs (
                    id,
                    source,
                    source_url,
                    requested_by,
                    mode,
                    status,
                    error_message,
                    document_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.source,
                    job.source_url,
                    job.requested_by,
                    job.mode,
                    job.status,
                    job.error_message,
                    job.document_id,
                    job.created_at,
                    job.updated_at,
                ),
            )
        return job

    def create_answer_audit(self, audit: AnswerAuditRecord) -> AnswerAuditRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO answer_audits (
                    id,
                    session_id,
                    user_id,
                    user_query,
                    normalized_query,
                    detected_area_json,
                    detected_jurisdiction_json,
                    detected_document_types_json,
                    mode,
                    retrieved_chunks_json,
                    reranked_chunks_json,
                    evidence_json,
                    draft_answer,
                    validator_report_json,
                    final_answer,
                    confidence,
                    abstained,
                    verdict,
                    model_generator,
                    model_validator,
                    generator_prompt_version,
                    validator_prompt_version,
                    embedding_model,
                    reranker_model,
                    latency_ms,
                    estimated_cost_usd,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit.id,
                    audit.session_id,
                    audit.user_id,
                    audit.user_query,
                    audit.normalized_query,
                    audit.detected_area_json,
                    audit.detected_jurisdiction_json,
                    audit.detected_document_types_json,
                    audit.mode,
                    audit.retrieved_chunks_json,
                    audit.reranked_chunks_json,
                    audit.evidence_json,
                    audit.draft_answer,
                    audit.validator_report_json,
                    audit.final_answer,
                    audit.confidence,
                    int(audit.abstained),
                    audit.verdict,
                    audit.model_generator,
                    audit.model_validator,
                    audit.generator_prompt_version,
                    audit.validator_prompt_version,
                    audit.embedding_model,
                    audit.reranker_model,
                    audit.latency_ms,
                    audit.estimated_cost_usd,
                    audit.created_at,
                ),
            )
        return audit

    def create_answer_feedback(self, feedback: AnswerFeedbackRecord) -> AnswerFeedbackRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO answer_feedback (
                    id,
                    audit_id,
                    rating,
                    category,
                    comment,
                    user_id,
                    session_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.id,
                    feedback.audit_id,
                    feedback.rating,
                    feedback.category,
                    feedback.comment,
                    feedback.user_id,
                    feedback.session_id,
                    feedback.created_at,
                ),
            )
        return feedback

    def create_evaluation_run(self, run: EvaluationRunRecord) -> EvaluationRunRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_runs (
                    id,
                    passed,
                    total_cases,
                    successful_cases,
                    failed_cases,
                    metrics_json,
                    quality_gates_json,
                    failed_cases_json,
                    evals_dir,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    int(run.passed),
                    run.total_cases,
                    run.successful_cases,
                    run.failed_cases,
                    run.metrics_json,
                    run.quality_gates_json,
                    run.failed_cases_json,
                    run.evals_dir,
                    run.created_at,
                ),
            )
        return run

    def get_document(self, document_id: str) -> LegalDocumentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    source,
                    jurisdiction,
                    document_type,
                    title,
                    source_url,
                    status,
                    sha256,
                    is_current,
                    is_consolidated,
                    legal_value_warning,
                    area_json,
                    legal_metadata_json,
                    created_at,
                    updated_at,
                    version_label,
                    valid_from,
                    valid_until,
                    supersedes_document_id,
                    archived_at,
                    change_note
                FROM legal_documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return _document_from_row(row)

    def get_document_by_source_url(self, source_url: str) -> LegalDocumentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    source,
                    jurisdiction,
                    document_type,
                    title,
                    source_url,
                    status,
                    sha256,
                    is_current,
                    is_consolidated,
                    legal_value_warning,
                    area_json,
                    legal_metadata_json,
                    created_at,
                    updated_at,
                    version_label,
                    valid_from,
                    valid_until,
                    supersedes_document_id,
                    archived_at,
                    change_note
                FROM legal_documents
                WHERE source_url = ?
                ORDER BY is_current DESC, updated_at DESC, created_at DESC, id ASC
                LIMIT 1
                """,
                (source_url,),
            ).fetchone()
        if row is None:
            return None
        return _document_from_row(row)

    def list_documents(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        jurisdiction: str | None = None,
        document_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[LegalDocumentRecord, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if jurisdiction is not None:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction)
        if document_type is not None:
            clauses.append("document_type = ?")
            params.append(document_type)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    source,
                    jurisdiction,
                    document_type,
                    title,
                    source_url,
                    status,
                    sha256,
                    is_current,
                    is_consolidated,
                    legal_value_warning,
                    area_json,
                    legal_metadata_json,
                    created_at,
                    updated_at,
                    version_label,
                    valid_from,
                    valid_until,
                    supersedes_document_id,
                    archived_at,
                    change_note
                FROM legal_documents
                {where_clause}
                ORDER BY updated_at DESC, created_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return tuple(_document_from_row(row) for row in rows)

    def list_documents_by_ids(self, document_ids: tuple[str, ...]) -> tuple[LegalDocumentRecord, ...]:
        if not document_ids:
            return ()
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    source,
                    jurisdiction,
                    document_type,
                    title,
                    source_url,
                    status,
                    sha256,
                    is_current,
                    is_consolidated,
                    legal_value_warning,
                    area_json,
                    legal_metadata_json,
                    created_at,
                    updated_at,
                    version_label,
                    valid_from,
                    valid_until,
                    supersedes_document_id,
                    archived_at,
                    change_note
                FROM legal_documents
                WHERE id IN ({placeholders})
                ORDER BY updated_at DESC, created_at DESC, id ASC
                """,
                document_ids,
            ).fetchall()
        return tuple(_document_from_row(row) for row in rows)

    def count_documents(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        jurisdiction: str | None = None,
        document_type: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if jurisdiction is not None:
            clauses.append("jurisdiction = ?")
            params.append(jurisdiction)
        if document_type is not None:
            clauses.append("document_type = ?")
            params.append(document_type)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM legal_documents
                {where_clause}
                """,
                tuple(params),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def list_chunks_by_document(self, document_id: str) -> tuple[LegalChunkRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    document_id,
                    chunk_type,
                    structural_path,
                    citation_label,
                    text_content,
                    token_count,
                    created_at
                FROM legal_chunks
                WHERE document_id = ?
                ORDER BY created_at ASC
                """,
                (document_id,),
            ).fetchall()
        return tuple(_chunk_from_row(row) for row in rows)

    def count_chunks_by_document(self, document_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM legal_chunks
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def get_document_raw_text(self, document_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT raw_text
                FROM legal_document_raw_texts
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def replace_document_chunks(self, document_id: str, chunks: tuple[LegalChunkRecord, ...]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM legal_chunks
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.executemany(
                """
                INSERT INTO legal_chunks (
                    id,
                    document_id,
                    chunk_type,
                    structural_path,
                    citation_label,
                    text_content,
                    token_count,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.chunk_type,
                        chunk.structural_path,
                        chunk.citation_label,
                        chunk.text_content,
                        chunk.token_count,
                        chunk.created_at,
                    )
                    for chunk in chunks
                ),
            )

    def list_searchable_chunks(self, *, current_only: bool) -> tuple[SearchableChunkRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    c.id,
                    c.document_id,
                    d.source,
                    d.jurisdiction,
                    d.document_type,
                    d.area_json,
                    d.legal_metadata_json,
                    d.source_url,
                    d.is_current,
                    d.is_consolidated,
                    d.legal_value_warning,
                    c.chunk_type,
                    c.citation_label,
                    c.text_content,
                    c.token_count,
                    d.version_label,
                    d.valid_from,
                    d.valid_until
                FROM legal_chunks c
                INNER JOIN legal_documents d ON d.id = c.document_id
                WHERE d.status = 'chat_ready'
                  AND (? = 0 OR d.is_current = 1)
                ORDER BY c.created_at ASC, c.id ASC
                """,
                (int(current_only),),
            ).fetchall()
        return tuple(_searchable_chunk_from_row(row) for row in rows)

    def get_job(self, job_id: str) -> IngestionJobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    source,
                    source_url,
                    requested_by,
                    mode,
                    status,
                    error_message,
                    document_id,
                    created_at,
                    updated_at
                FROM source_ingestion_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return _job_from_row(row)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        mode: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[IngestionJobRecord, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if mode is not None:
            clauses.append("mode = ?")
            params.append(mode)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    source,
                    source_url,
                    requested_by,
                    mode,
                    status,
                    error_message,
                    document_id,
                    created_at,
                    updated_at
                FROM source_ingestion_jobs
                {where_clause}
                ORDER BY updated_at DESC, created_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return tuple(_job_from_row(row) for row in rows)

    def count_jobs(
        self,
        *,
        status: str | None = None,
        mode: str | None = None,
        source: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if mode is not None:
            clauses.append("mode = ?")
            params.append(mode)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM source_ingestion_jobs
                {where_clause}
                """,
                tuple(params),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def get_answer_audit(self, audit_id: str) -> AnswerAuditRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    session_id,
                    user_id,
                    user_query,
                    normalized_query,
                    detected_area_json,
                    detected_jurisdiction_json,
                    detected_document_types_json,
                    mode,
                    retrieved_chunks_json,
                    reranked_chunks_json,
                    evidence_json,
                    draft_answer,
                    validator_report_json,
                    final_answer,
                    confidence,
                    abstained,
                    verdict,
                    model_generator,
                    model_validator,
                    generator_prompt_version,
                    validator_prompt_version,
                    embedding_model,
                    reranker_model,
                    latency_ms,
                    estimated_cost_usd,
                    created_at
                FROM answer_audits
                WHERE id = ?
                """,
                (audit_id,),
            ).fetchone()
        if row is None:
            return None
        return _answer_audit_from_row(row)

    def list_answer_audits(
        self,
        *,
        verdict: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[AnswerAuditRecord, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if verdict is not None:
            clauses.append("verdict = ?")
            params.append(verdict)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    session_id,
                    user_id,
                    user_query,
                    normalized_query,
                    detected_area_json,
                    detected_jurisdiction_json,
                    detected_document_types_json,
                    mode,
                    retrieved_chunks_json,
                    reranked_chunks_json,
                    evidence_json,
                    draft_answer,
                    validator_report_json,
                    final_answer,
                    confidence,
                    abstained,
                    verdict,
                    model_generator,
                    model_validator,
                    generator_prompt_version,
                    validator_prompt_version,
                    embedding_model,
                    reranker_model,
                    latency_ms,
                    estimated_cost_usd,
                    created_at
                FROM answer_audits
                {where_clause}
                ORDER BY created_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return tuple(_answer_audit_from_row(row) for row in rows)

    def count_answer_audits(
        self,
        *,
        verdict: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if verdict is not None:
            clauses.append("verdict = ?")
            params.append(verdict)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM answer_audits
                {where_clause}
                """,
                tuple(params),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def list_answer_feedback(
        self,
        *,
        audit_id: str | None = None,
        rating: str | None = None,
        category: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[AnswerFeedbackRecord, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if audit_id is not None:
            clauses.append("audit_id = ?")
            params.append(audit_id)
        if rating is not None:
            clauses.append("rating = ?")
            params.append(rating)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    audit_id,
                    rating,
                    category,
                    comment,
                    user_id,
                    session_id,
                    created_at
                FROM answer_feedback
                {where_clause}
                ORDER BY created_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return tuple(_answer_feedback_from_row(row) for row in rows)

    def count_answer_feedback(
        self,
        *,
        audit_id: str | None = None,
        rating: str | None = None,
        category: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if audit_id is not None:
            clauses.append("audit_id = ?")
            params.append(audit_id)
        if rating is not None:
            clauses.append("rating = ?")
            params.append(rating)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM answer_feedback
                {where_clause}
                """,
                tuple(params),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def get_evaluation_run(self, run_id: str) -> EvaluationRunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    passed,
                    total_cases,
                    successful_cases,
                    failed_cases,
                    metrics_json,
                    quality_gates_json,
                    failed_cases_json,
                    evals_dir,
                    created_at
                FROM evaluation_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _evaluation_run_from_row(row)

    def list_evaluation_runs(
        self,
        *,
        passed: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[EvaluationRunRecord, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if passed is not None:
            clauses.append("passed = ?")
            params.append(int(passed))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    passed,
                    total_cases,
                    successful_cases,
                    failed_cases,
                    metrics_json,
                    quality_gates_json,
                    failed_cases_json,
                    evals_dir,
                    created_at
                FROM evaluation_runs
                {where_clause}
                ORDER BY created_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return tuple(_evaluation_run_from_row(row) for row in rows)

    def count_evaluation_runs(self, *, passed: bool | None = None) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if passed is not None:
            clauses.append("passed = ?")
            params.append(int(passed))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM evaluation_runs
                {where_clause}
                """,
                tuple(params),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def promote_document(
        self,
        document_id: str,
        target_status: str,
        *,
        change_note: str = "",
    ) -> LegalDocumentRecord | None:
        existing_document = self.get_document(document_id)
        if existing_document is None:
            return None

        updated_at = utc_now_iso()
        archived_at = updated_at if target_status == "archived" else existing_document.archived_at
        is_current = False if target_status in {"archived", "rejected"} else existing_document.is_current
        resolved_change_note = change_note or existing_document.change_note
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE legal_documents
                SET status = ?, is_current = ?, archived_at = ?, change_note = ?, updated_at = ?
                WHERE id = ?
                """,
                (target_status, int(is_current), archived_at, resolved_change_note, updated_at, document_id),
            )
        return self.get_document(document_id)

    def archive_current_document_version(
        self,
        *,
        source_url: str,
        valid_until: str | None,
        change_note: str,
    ) -> LegalDocumentRecord | None:
        existing_document = self.get_document_by_source_url(source_url)
        if existing_document is None or not existing_document.is_current:
            return None

        archived_at = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE legal_documents
                SET
                    status = ?,
                    is_current = ?,
                    valid_until = ?,
                    archived_at = ?,
                    change_note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                ("archived", 0, valid_until, archived_at, change_note, archived_at, existing_document.id),
            )
        return self.get_document(existing_document.id)

    @contextmanager
    def _connect(self) -> Iterator[DatabaseConnection]:
        connection = self._open_connection()
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _open_connection(self) -> DatabaseConnection:
        if self.database_url is None:
            connection = sqlite3.connect(self.database_path)
            connection.execute("PRAGMA foreign_keys = ON")
            return cast(DatabaseConnection, connection)
        try:
            psycopg = importlib.import_module("psycopg")
        except ModuleNotFoundError as exc:
            raise RuntimeError("PostgreSQL backend requires the optional psycopg package.") from exc
        return _PostgresConnection(cast(_PsycopgConnection, psycopg.connect(self.database_url)))


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _ensure_column(
    connection: DatabaseConnection,
    backend: str,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if backend == "postgresql":
        row = connection.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
              AND column_name = ?
            LIMIT 1
            """,
            (table_name, column_name),
        ).fetchone()
        if row is not None:
            return
    else:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(str(row[1]) == column_name for row in rows):
            return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _record_schema_migration(connection: DatabaseConnection, version: str) -> None:
    connection.execute(
        """
        INSERT INTO schema_migrations (version, applied_at)
        VALUES (?, ?)
        ON CONFLICT(version) DO NOTHING
        """,
        (version, utc_now_iso()),
    )


def _record_schema_migrations_from_files(connection: DatabaseConnection) -> None:
    for migration_path in _migration_paths():
        version = migration_path.stem
        row = connection.execute(
            """
            SELECT 1
            FROM schema_migrations
            WHERE version = ?
            LIMIT 1
            """,
            (version,),
        ).fetchone()
        if row is not None:
            continue
        connection.executescript(migration_path.read_text(encoding="utf-8"))
        _record_schema_migration(connection, version)


def _validate_applied_schema_migrations(connection: DatabaseConnection) -> None:
    known_versions = {path.stem for path in _migration_paths()}
    if not known_versions:
        known_versions = {SCHEMA_VERSION}
    rows = connection.execute(
        """
        SELECT version
        FROM schema_migrations
        ORDER BY version
        """
    ).fetchall()
    applied_versions = {str(row[0]) for row in rows}
    unknown_versions = sorted(applied_versions - known_versions)
    if unknown_versions:
        formatted_versions = ", ".join(unknown_versions)
        raise RuntimeError(f"Database contains an unknown applied migration: {formatted_versions}.")


def _validate_schema_migration_files() -> None:
    migration_paths = _migration_paths()
    if not migration_paths:
        return

    versions = tuple(path.stem for path in migration_paths)
    if SCHEMA_VERSION != versions[-1]:
        raise RuntimeError(
            f"SCHEMA_VERSION must match latest migration file: expected {versions[-1]}, got {SCHEMA_VERSION}."
        )

    version_numbers = tuple(_migration_version_number(version) for version in versions)
    expected_numbers = tuple(range(version_numbers[0], version_numbers[-1] + 1))
    if version_numbers != expected_numbers:
        missing_numbers = sorted(set(expected_numbers) - set(version_numbers))
        formatted_missing = ", ".join(f"{number:04d}" for number in missing_numbers)
        raise RuntimeError(f"Migration files contain a missing migration number: {formatted_missing}.")


def _migration_paths() -> tuple[Path, ...]:
    if not MIGRATIONS_DIR.exists():
        return ()
    return tuple(sorted(MIGRATIONS_DIR.glob("*.sql")))


def _migration_version_number(version: str) -> int:
    prefix, separator, _suffix = version.partition("_")
    if len(prefix) != 4 or separator != "_" or not prefix.isdecimal():
        raise RuntimeError(f"Migration file has invalid version prefix: {version}.")
    return int(prefix)


def _postgres_sql(sql: str) -> str:
    return sql.replace("?", "%s")


def _postgres_parameters(parameters: Sequence[object]) -> tuple[object, ...]:
    return tuple(int(parameter) if isinstance(parameter, bool) else parameter for parameter in parameters)


def _split_sql_script(sql: str) -> tuple[str, ...]:
    return tuple(statement.strip() for statement in sql.split(";") if statement.strip())


def _json_string_dict(value: object) -> dict[str, str]:
    if value is None:
        return {}
    loaded = json.loads(str(value))
    if not isinstance(loaded, dict):
        return {}
    return {str(key): str(item) for key, item in loaded.items() if item is not None}


def _optional_row_str(row: sqlite3.Row | tuple[object, ...], index: int) -> str | None:
    if len(row) <= index or row[index] is None:
        return None
    return str(row[index])


def _document_from_row(row: sqlite3.Row | tuple[object, ...]) -> LegalDocumentRecord:
    area_value = row[11]
    legal_metadata_value = row[12]
    area = tuple(json.loads(str(area_value))) if area_value else ()
    legal_metadata = _json_string_dict(legal_metadata_value)
    return LegalDocumentRecord(
        id=str(row[0]),
        source=str(row[1]),
        jurisdiction=str(row[2]),
        document_type=str(row[3]),
        title=str(row[4]),
        source_url=str(row[5]),
        status=str(row[6]),
        sha256=str(row[7]),
        is_current=bool(row[8]),
        is_consolidated=bool(row[9]),
        legal_value_warning=str(row[10]),
        area=area,
        legal_metadata=legal_metadata,
        created_at=str(row[13]),
        updated_at=str(row[14]),
        version_label=str(row[15]) if len(row) > 15 and row[15] is not None else "current",
        valid_from=_optional_row_str(row, 16),
        valid_until=_optional_row_str(row, 17),
        supersedes_document_id=_optional_row_str(row, 18),
        archived_at=_optional_row_str(row, 19),
        change_note=str(row[20]) if len(row) > 20 and row[20] is not None else "",
    )


def _chunk_from_row(row: sqlite3.Row | tuple[object, ...]) -> LegalChunkRecord:
    return LegalChunkRecord(
        id=str(row[0]),
        document_id=str(row[1]),
        chunk_type=str(row[2]),
        structural_path=str(row[3]) if row[3] is not None else None,
        citation_label=str(row[4]) if row[4] is not None else None,
        text_content=str(row[5]),
        token_count=int(row[6]) if row[6] is not None else None,
        created_at=str(row[7]),
    )


def _searchable_chunk_from_row(row: sqlite3.Row | tuple[object, ...]) -> SearchableChunkRecord:
    area_value = row[5]
    legal_metadata_value = row[6]
    area = tuple(json.loads(str(area_value))) if area_value else ()
    legal_metadata = _json_string_dict(legal_metadata_value)
    return SearchableChunkRecord(
        chunk_id=str(row[0]),
        document_id=str(row[1]),
        source=str(row[2]),
        jurisdiction=str(row[3]),
        document_type=str(row[4]),
        area=area,
        legal_metadata=legal_metadata,
        source_url=str(row[7]),
        is_current=bool(row[8]),
        is_consolidated=bool(row[9]),
        legal_value_warning=str(row[10]),
        chunk_type=str(row[11]),
        citation_label=str(row[12]) if row[12] is not None else None,
        text_content=str(row[13]),
        token_count=int(row[14]) if row[14] is not None else None,
        version_label=str(row[15]) if len(row) > 15 and row[15] is not None else "current",
        valid_from=_optional_row_str(row, 16),
        valid_until=_optional_row_str(row, 17),
    )


def _chunk_embedding_from_row(row: sqlite3.Row | tuple[object, ...]) -> LegalChunkEmbeddingRecord:
    vector_value = json.loads(str(row[3]))
    vector = tuple(float(value) for value in vector_value) if isinstance(vector_value, list) else ()
    return LegalChunkEmbeddingRecord(
        chunk_id=str(row[0]),
        model=str(row[1]),
        dimensions=int(row[2]),
        vector=vector,
        vector_id=str(row[4]) if row[4] is not None else None,
        created_at=str(row[5]),
        updated_at=str(row[6]),
    )


def _job_from_row(row: sqlite3.Row | tuple[object, ...]) -> IngestionJobRecord:
    return IngestionJobRecord(
        id=str(row[0]),
        source=str(row[1]),
        source_url=str(row[2]),
        requested_by=str(row[3]) if row[3] is not None else None,
        mode=str(row[4]),
        status=str(row[5]),
        error_message=str(row[6]) if row[6] is not None else None,
        document_id=str(row[7]) if row[7] is not None else None,
        created_at=str(row[8]),
        updated_at=str(row[9]),
    )


def _answer_audit_from_row(row: sqlite3.Row | tuple[object, ...]) -> AnswerAuditRecord:
    return AnswerAuditRecord(
        id=str(row[0]),
        session_id=str(row[1]) if row[1] is not None else None,
        user_id=str(row[2]) if row[2] is not None else None,
        user_query=str(row[3]),
        normalized_query=str(row[4]),
        detected_area_json=str(row[5]),
        detected_jurisdiction_json=str(row[6]),
        detected_document_types_json=str(row[7]),
        mode=str(row[8]),
        retrieved_chunks_json=str(row[9]),
        reranked_chunks_json=str(row[10]),
        evidence_json=str(row[11]),
        draft_answer=str(row[12]),
        validator_report_json=str(row[13]),
        final_answer=str(row[14]),
        confidence=str(row[15]),
        abstained=bool(row[16]),
        verdict=str(row[17]),
        model_generator=str(row[18]) if row[18] is not None else None,
        model_validator=str(row[19]) if row[19] is not None else None,
        generator_prompt_version=str(row[20]) if row[20] is not None else None,
        validator_prompt_version=str(row[21]) if row[21] is not None else None,
        embedding_model=str(row[22]) if row[22] is not None else None,
        reranker_model=str(row[23]) if row[23] is not None else None,
        latency_ms=int(row[24]),
        estimated_cost_usd=float(row[25]),
        created_at=str(row[26]),
    )


def _answer_feedback_from_row(row: sqlite3.Row | tuple[object, ...]) -> AnswerFeedbackRecord:
    return AnswerFeedbackRecord(
        id=str(row[0]),
        audit_id=str(row[1]),
        rating=str(row[2]),
        category=str(row[3]) if row[3] is not None else None,
        comment=str(row[4]) if row[4] is not None else None,
        user_id=str(row[5]) if row[5] is not None else None,
        session_id=str(row[6]) if row[6] is not None else None,
        created_at=str(row[7]),
    )


def _evaluation_run_from_row(row: sqlite3.Row | tuple[object, ...]) -> EvaluationRunRecord:
    return EvaluationRunRecord(
        id=str(row[0]),
        passed=bool(row[1]),
        total_cases=int(row[2]),
        successful_cases=int(row[3]),
        failed_cases=int(row[4]),
        metrics_json=str(row[5]),
        quality_gates_json=str(row[6]),
        failed_cases_json=str(row[7]),
        evals_dir=str(row[8]),
        created_at=str(row[9]),
    )
