from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


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
    created_at: str
    updated_at: str


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
    source_url: str
    is_current: bool
    is_consolidated: bool
    legal_value_warning: str
    chunk_type: str
    citation_label: str | None
    text_content: str
    token_count: int | None


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
    embedding_model: str | None
    reranker_model: str | None
    latency_ms: int
    estimated_cost_usd: float
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
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def initialize_schema(self) -> None:
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
                """
            )

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
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    document.created_at,
                    document.updated_at,
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
                    embedding_model,
                    reranker_model,
                    latency_ms,
                    estimated_cost_usd,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    audit.embedding_model,
                    audit.reranker_model,
                    audit.latency_ms,
                    audit.estimated_cost_usd,
                    audit.created_at,
                ),
            )
        return audit

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
                    created_at,
                    updated_at
                FROM legal_documents
                WHERE id = ?
                """,
                (document_id,),
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
                    created_at,
                    updated_at
                FROM legal_documents
                {where_clause}
                ORDER BY updated_at DESC, created_at DESC, id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
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
                    d.source_url,
                    d.is_current,
                    d.is_consolidated,
                    d.legal_value_warning,
                    c.chunk_type,
                    c.citation_label,
                    c.text_content,
                    c.token_count
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

    def promote_document(self, document_id: str, target_status: str) -> LegalDocumentRecord | None:
        existing_document = self.get_document(document_id)
        if existing_document is None:
            return None

        updated_at = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE legal_documents
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (target_status, updated_at, document_id),
            )
        return self.get_document(document_id)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _document_from_row(row: sqlite3.Row | tuple[object, ...]) -> LegalDocumentRecord:
    area_value = row[11]
    area = tuple(json.loads(str(area_value))) if area_value else ()
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
        created_at=str(row[12]),
        updated_at=str(row[13]),
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
    return SearchableChunkRecord(
        chunk_id=str(row[0]),
        document_id=str(row[1]),
        source=str(row[2]),
        jurisdiction=str(row[3]),
        document_type=str(row[4]),
        source_url=str(row[5]),
        is_current=bool(row[6]),
        is_consolidated=bool(row[7]),
        legal_value_warning=str(row[8]),
        chunk_type=str(row[9]),
        citation_label=str(row[10]) if row[10] is not None else None,
        text_content=str(row[11]),
        token_count=int(row[12]) if row[12] is not None else None,
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
        embedding_model=str(row[20]) if row[20] is not None else None,
        reranker_model=str(row[21]) if row[21] is not None else None,
        latency_ms=int(row[22]),
        estimated_cost_usd=float(row[23]),
        created_at=str(row[24]),
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
