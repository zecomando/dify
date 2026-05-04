from functools import lru_cache
from pathlib import Path
from secrets import compare_digest
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict

from app.audit import answer_audit_to_response
from app.config import get_settings
from app.corpus import InitialCorpusSeedResult, seed_initial_corpus
from app.engine import (
    build_evidence,
    classify_query,
    generate_answer,
    rerank_results,
    search_retrieval,
    validate_answer,
)
from app.evaluation import (
    EvaluationRunRequest,
    EvaluationRunResponse,
    evaluation_run_to_response,
    get_default_evals_dir,
    run_and_persist_evaluation,
)
from app.ingestion import crawl_url, ingest_source, promote_document, reindex_corpus
from app.pipeline import answer_chat
from app.repository import (
    AnswerAuditRecord,
    AnswerFeedbackRecord,
    EvaluationRunRecord,
    IngestionJobRecord,
    LegalChunkRecord,
    LegalDocumentRecord,
    LegalRepository,
    utc_now_iso,
)
from app.schemas import (
    AdminDiagnosticsResponse,
    AdminDocumentStatusRequest,
    AdminDocumentStatusResponse,
    AdminMetricsResponse,
    AnswerGenerateRequest,
    AnswerGenerateResponse,
    AnswerAuditResponse,
    AnswerAuditListResponse,
    AnswerAuditSummaryResponse,
    AnswerFeedbackListResponse,
    AnswerFeedbackRating,
    AnswerFeedbackRequest,
    AnswerFeedbackResponse,
    AnswerValidateRequest,
    AnswerValidateResponse,
    ChatAnswerRequest,
    ChatAnswerResponse,
    ClassifyQueryRequest,
    ClassifyQueryResponse,
    CrawlUrlRequest,
    DocumentStatus,
    EvidenceBuildRequest,
    EvidenceBuildResponse,
    EvaluationRunListResponse,
    EvaluationRunSummaryResponse,
    InitialCorpusSeedResponse,
    IngestionJobDetailResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionJobStatus,
    IngestionSourceRequest,
    LegalChunkListResponse,
    LegalChunkResponse,
    LegalDocumentListResponse,
    LegalDocumentResponse,
    PromoteDocumentRequest,
    PromoteDocumentResponse,
    RerankRequest,
    RerankResponse,
    ReindexRequest,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    ValidatorVerdict,
)
from app.source_policy import (
    SourcePolicy,
    SourcePolicyCheckRequest,
    SourcePolicyCheckResult,
    get_default_source_policy_path,
)

router = APIRouter()
admin_token_header = APIKeyHeader(name="X-Admin-Token", scheme_name="AdminTokenAuth", auto_error=False)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    source_policy_name: str
    source_policy_version: int


@lru_cache(maxsize=1)
def get_source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(get_default_source_policy_path())


def get_repository() -> LegalRepository:
    settings = get_settings()
    return LegalRepository(settings.database_path, settings.database_url)


def require_admin_token(x_admin_token: str | None = Security(admin_token_header)) -> None:
    admin_token = get_settings().admin_token
    if admin_token is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin token is not configured.")
    if x_admin_token is None or not compare_digest(x_admin_token, admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token.")


admin_dependencies = [Depends(require_admin_token)]


def _legal_document_to_response(document: LegalDocumentRecord) -> LegalDocumentResponse:
    return LegalDocumentResponse(
        id=document.id,
        source=document.source,
        jurisdiction=document.jurisdiction,
        document_type=document.document_type,
        title=document.title,
        source_url=document.source_url,
        status=document.status,
        sha256=document.sha256,
        is_current=document.is_current,
        is_consolidated=document.is_consolidated,
        legal_value_warning=document.legal_value_warning,
        area=list(document.area),
        legal_metadata=document.legal_metadata,
        version_label=document.version_label,
        valid_from=document.valid_from,
        valid_until=document.valid_until,
        supersedes_document_id=document.supersedes_document_id,
        archived_at=document.archived_at,
        change_note=document.change_note,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _initial_corpus_seed_to_response(result: InitialCorpusSeedResult) -> InitialCorpusSeedResponse:
    return InitialCorpusSeedResponse(
        total_seeds=result.total_seeds,
        created_documents=result.created_documents,
        already_present_documents=result.already_present_documents,
        completed_jobs=result.completed_jobs,
        rejected_jobs=result.rejected_jobs,
        chat_ready_documents=result.chat_ready_documents,
        pending_review_documents=result.pending_review_documents,
        document_ids=list(result.document_ids),
        rejected_source_urls=list(result.rejected_source_urls),
    )


def _legal_chunk_to_response(chunk: LegalChunkRecord) -> LegalChunkResponse:
    return LegalChunkResponse(
        id=chunk.id,
        document_id=chunk.document_id,
        chunk_type=chunk.chunk_type,
        structural_path=chunk.structural_path,
        citation_label=chunk.citation_label,
        text_content=chunk.text_content,
        token_count=chunk.token_count,
        created_at=chunk.created_at,
    )


def _ingestion_job_to_response(job: IngestionJobRecord) -> IngestionJobDetailResponse:
    return IngestionJobDetailResponse(
        id=job.id,
        source=job.source,
        source_url=job.source_url,
        requested_by=job.requested_by,
        mode=job.mode,
        status=job.status,
        error_message=job.error_message,
        document_id=job.document_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _answer_audit_to_summary_response(audit: AnswerAuditRecord) -> AnswerAuditSummaryResponse:
    return AnswerAuditSummaryResponse(
        id=audit.id,
        session_id=audit.session_id,
        user_id=audit.user_id,
        user_query=audit.user_query,
        verdict=audit.verdict,
        confidence=audit.confidence,
        abstained=audit.abstained,
        latency_ms=audit.latency_ms,
        estimated_cost_usd=audit.estimated_cost_usd,
        created_at=audit.created_at,
    )


def _answer_feedback_to_response(feedback: AnswerFeedbackRecord) -> AnswerFeedbackResponse:
    return AnswerFeedbackResponse(
        id=feedback.id,
        audit_id=feedback.audit_id,
        rating=feedback.rating,
        comment=feedback.comment,
        user_id=feedback.user_id,
        session_id=feedback.session_id,
        created_at=feedback.created_at,
    )


def _evaluation_run_to_summary_response(run: EvaluationRunRecord) -> EvaluationRunSummaryResponse:
    return EvaluationRunSummaryResponse(
        id=run.id,
        passed=run.passed,
        total_cases=run.total_cases,
        successful_cases=run.successful_cases,
        failed_cases_count=run.failed_cases,
        evals_dir=run.evals_dir,
        created_at=run.created_at,
    )


@router.get("/health", response_model=HealthResponse)
def health(source_policy: SourcePolicy = Depends(get_source_policy)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        source_policy_name=source_policy.name,
        source_policy_version=source_policy.version,
    )


@router.post("/source-policy/check-url", response_model=SourcePolicyCheckResult)
def check_source_policy_url(
    payload: SourcePolicyCheckRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
) -> SourcePolicyCheckResult:
    return source_policy.check_url(payload.url)


@router.get("/admin/diagnostics", response_model=AdminDiagnosticsResponse, dependencies=admin_dependencies)
def get_admin_diagnostics(
    source_policy: SourcePolicy = Depends(get_source_policy),
    repository: LegalRepository = Depends(get_repository),
) -> AdminDiagnosticsResponse:
    return AdminDiagnosticsResponse(
        status="ok",
        database_backend=repository.backend,
        source_policy_name=source_policy.name,
        source_policy_version=source_policy.version,
        documents_total=repository.count_documents(),
        chat_ready_documents=repository.count_documents(status=DocumentStatus.CHAT_READY.value),
        pending_review_documents=repository.count_documents(status=DocumentStatus.PENDING_REVIEW.value),
        archived_documents=repository.count_documents(status=DocumentStatus.ARCHIVED.value),
        rejected_documents=repository.count_documents(status=DocumentStatus.REJECTED.value),
        ingestion_jobs_total=repository.count_jobs(),
        ingestion_jobs_completed=repository.count_jobs(status=IngestionJobStatus.COMPLETED.value),
        ingestion_jobs_rejected=repository.count_jobs(status=IngestionJobStatus.REJECTED.value),
        ingestion_jobs_pending=repository.count_jobs(status=IngestionJobStatus.PENDING.value),
        answer_audits_total=repository.count_answer_audits(),
        answer_feedback_total=repository.count_answer_feedback(),
        evaluation_runs_total=repository.count_evaluation_runs(),
    )


@router.get("/admin/metrics", response_model=AdminMetricsResponse, dependencies=admin_dependencies)
def get_admin_metrics(repository: LegalRepository = Depends(get_repository)) -> AdminMetricsResponse:
    return AdminMetricsResponse(
        documents={
            "total": repository.count_documents(),
            "chat_ready": repository.count_documents(status=DocumentStatus.CHAT_READY.value),
            "pending_review": repository.count_documents(status=DocumentStatus.PENDING_REVIEW.value),
            "archived": repository.count_documents(status=DocumentStatus.ARCHIVED.value),
            "rejected": repository.count_documents(status=DocumentStatus.REJECTED.value),
        },
        ingestion_jobs={
            "total": repository.count_jobs(),
            "completed": repository.count_jobs(status=IngestionJobStatus.COMPLETED.value),
            "rejected": repository.count_jobs(status=IngestionJobStatus.REJECTED.value),
            "pending": repository.count_jobs(status=IngestionJobStatus.PENDING.value),
        },
        answer_audits={"total": repository.count_answer_audits()},
        answer_feedback={"total": repository.count_answer_feedback()},
        evaluation_runs={"total": repository.count_evaluation_runs()},
    )


@router.post("/query/classify", response_model=ClassifyQueryResponse)
def classify_legal_query(payload: ClassifyQueryRequest) -> ClassifyQueryResponse:
    return classify_query(payload)


@router.post("/retrieval/search", response_model=RetrievalSearchResponse)
def search_legal_corpus(
    payload: RetrievalSearchRequest,
    repository: LegalRepository = Depends(get_repository),
) -> RetrievalSearchResponse:
    return search_retrieval(payload, repository)


@router.post("/retrieval/rerank", response_model=RerankResponse)
def rerank_legal_results(payload: RerankRequest) -> RerankResponse:
    return rerank_results(payload)


@router.post("/evidence/build", response_model=EvidenceBuildResponse)
def build_legal_evidence(
    payload: EvidenceBuildRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
) -> EvidenceBuildResponse:
    return build_evidence(payload, source_policy)


@router.post("/answer/generate", response_model=AnswerGenerateResponse)
def generate_legal_answer(payload: AnswerGenerateRequest) -> AnswerGenerateResponse:
    return generate_answer(payload)


@router.post("/answer/validate", response_model=AnswerValidateResponse)
def validate_legal_answer(
    payload: AnswerValidateRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
) -> AnswerValidateResponse:
    return validate_answer(payload, source_policy)


@router.post("/chat/answer", response_model=ChatAnswerResponse)
def answer_legal_chat(
    payload: ChatAnswerRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
    repository: LegalRepository = Depends(get_repository),
) -> ChatAnswerResponse:
    return answer_chat(payload, source_policy, repository)


@router.post("/feedback/answer", response_model=AnswerFeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_answer_feedback(
    payload: AnswerFeedbackRequest,
    repository: LegalRepository = Depends(get_repository),
) -> AnswerFeedbackResponse:
    audit = repository.get_answer_audit(payload.audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer audit not found.")
    feedback = repository.create_answer_feedback(
        AnswerFeedbackRecord(
            id=str(uuid4()),
            audit_id=payload.audit_id,
            rating=payload.rating.value,
            comment=payload.comment,
            user_id=payload.user_id,
            session_id=payload.session_id,
            created_at=utc_now_iso(),
        )
    )
    return _answer_feedback_to_response(feedback)


@router.get("/admin/documents", response_model=LegalDocumentListResponse, dependencies=admin_dependencies)
def list_legal_documents(
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    source: str | None = None,
    jurisdiction: str | None = None,
    document_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: LegalRepository = Depends(get_repository),
) -> LegalDocumentListResponse:
    status_value = status_filter.value if status_filter is not None else None
    documents = repository.list_documents(
        status=status_value,
        source=source,
        jurisdiction=jurisdiction,
        document_type=document_type,
        limit=limit,
        offset=offset,
    )
    total = repository.count_documents(
        status=status_value,
        source=source,
        jurisdiction=jurisdiction,
        document_type=document_type,
    )
    return LegalDocumentListResponse(
        documents=[_legal_document_to_response(document) for document in documents],
        total=total,
    )


@router.get("/admin/documents/{document_id}", response_model=LegalDocumentResponse, dependencies=admin_dependencies)
def get_legal_document(
    document_id: str,
    repository: LegalRepository = Depends(get_repository),
) -> LegalDocumentResponse:
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return _legal_document_to_response(document)


@router.get(
    "/admin/documents/{document_id}/chunks",
    response_model=LegalChunkListResponse,
    dependencies=admin_dependencies,
)
def list_legal_document_chunks(
    document_id: str,
    repository: LegalRepository = Depends(get_repository),
) -> LegalChunkListResponse:
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    chunks = repository.list_chunks_by_document(document_id)
    return LegalChunkListResponse(
        chunks=[_legal_chunk_to_response(chunk) for chunk in chunks],
        total=len(chunks),
    )


@router.post(
    "/admin/documents/{document_id}/status",
    response_model=AdminDocumentStatusResponse,
    dependencies=admin_dependencies,
)
def update_legal_document_status(
    document_id: str,
    payload: AdminDocumentStatusRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
    repository: LegalRepository = Depends(get_repository),
) -> AdminDocumentStatusResponse:
    response = promote_document(
        PromoteDocumentRequest(document_id=document_id, target_status=payload.target_status.value),
        repository,
        source_policy,
    )
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return AdminDocumentStatusResponse(document=_legal_document_to_response(document))


@router.get("/admin/audits", response_model=AnswerAuditListResponse, dependencies=admin_dependencies)
def list_answer_audits(
    verdict: ValidatorVerdict | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: LegalRepository = Depends(get_repository),
) -> AnswerAuditListResponse:
    verdict_value = verdict.value if verdict is not None else None
    audits = repository.list_answer_audits(
        verdict=verdict_value,
        session_id=session_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    total = repository.count_answer_audits(
        verdict=verdict_value,
        session_id=session_id,
        user_id=user_id,
    )
    return AnswerAuditListResponse(
        audits=[_answer_audit_to_summary_response(audit) for audit in audits],
        total=total,
    )


@router.get("/admin/audit/{answer_id}", response_model=AnswerAuditResponse, dependencies=admin_dependencies)
def get_answer_audit(
    answer_id: str,
    repository: LegalRepository = Depends(get_repository),
) -> AnswerAuditResponse:
    audit = repository.get_answer_audit(answer_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer audit not found.")
    return answer_audit_to_response(audit)


@router.get("/admin/feedback", response_model=AnswerFeedbackListResponse, dependencies=admin_dependencies)
def list_answer_feedback(
    audit_id: str | None = None,
    rating: AnswerFeedbackRating | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: LegalRepository = Depends(get_repository),
) -> AnswerFeedbackListResponse:
    rating_value = rating.value if rating is not None else None
    feedback = repository.list_answer_feedback(
        audit_id=audit_id,
        rating=rating_value,
        session_id=session_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    total = repository.count_answer_feedback(
        audit_id=audit_id,
        rating=rating_value,
        session_id=session_id,
        user_id=user_id,
    )
    return AnswerFeedbackListResponse(
        feedback=[_answer_feedback_to_response(item) for item in feedback],
        total=total,
    )


@router.get("/admin/ingestion/jobs", response_model=IngestionJobListResponse, dependencies=admin_dependencies)
def list_ingestion_jobs(
    job_status: IngestionJobStatus | None = Query(default=None, alias="status"),
    mode: str | None = None,
    source: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: LegalRepository = Depends(get_repository),
) -> IngestionJobListResponse:
    status_value = job_status.value if job_status is not None else None
    jobs = repository.list_jobs(
        status=status_value,
        mode=mode,
        source=source,
        limit=limit,
        offset=offset,
    )
    total = repository.count_jobs(status=status_value, mode=mode, source=source)
    return IngestionJobListResponse(
        jobs=[_ingestion_job_to_response(job) for job in jobs],
        total=total,
    )


@router.get(
    "/admin/ingestion/jobs/{job_id}",
    response_model=IngestionJobDetailResponse,
    dependencies=admin_dependencies,
)
def get_ingestion_job(
    job_id: str,
    repository: LegalRepository = Depends(get_repository),
) -> IngestionJobDetailResponse:
    job = repository.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")
    return _ingestion_job_to_response(job)


@router.post("/admin/evaluation/run", response_model=EvaluationRunResponse, dependencies=admin_dependencies)
def run_legal_evaluation(
    payload: EvaluationRunRequest,
    repository: LegalRepository = Depends(get_repository),
) -> EvaluationRunResponse:
    evals_dir = get_default_evals_dir() if payload.evals_dir is None else Path(payload.evals_dir)
    return run_and_persist_evaluation(
        evals_dir=evals_dir,
        source_policy_path=get_default_source_policy_path(),
        repository=repository,
    )


@router.get("/admin/evaluation/runs", response_model=EvaluationRunListResponse, dependencies=admin_dependencies)
def list_legal_evaluation_runs(
    passed: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: LegalRepository = Depends(get_repository),
) -> EvaluationRunListResponse:
    runs = repository.list_evaluation_runs(passed=passed, limit=limit, offset=offset)
    total = repository.count_evaluation_runs(passed=passed)
    return EvaluationRunListResponse(
        runs=[_evaluation_run_to_summary_response(run) for run in runs],
        total=total,
    )


@router.post(
    "/admin/corpus/seed",
    response_model=InitialCorpusSeedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=admin_dependencies,
)
def seed_legal_initial_corpus(
    source_policy: SourcePolicy = Depends(get_source_policy),
    repository: LegalRepository = Depends(get_repository),
) -> InitialCorpusSeedResponse:
    return _initial_corpus_seed_to_response(seed_initial_corpus(repository, source_policy))


@router.get("/admin/evaluation/runs/{run_id}", response_model=EvaluationRunResponse, dependencies=admin_dependencies)
def get_legal_evaluation_run(
    run_id: str,
    repository: LegalRepository = Depends(get_repository),
) -> EvaluationRunResponse:
    evaluation_run = repository.get_evaluation_run(run_id)
    if evaluation_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found.")
    return evaluation_run_to_response(evaluation_run)


@router.post("/ingestion/source", response_model=IngestionJobResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_legal_source(
    payload: IngestionSourceRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
    repository: LegalRepository = Depends(get_repository),
) -> IngestionJobResponse:
    return ingest_source(payload, source_policy, repository)


@router.post("/ingestion/crawl-url", response_model=IngestionJobResponse, status_code=status.HTTP_202_ACCEPTED)
def crawl_legal_url(
    payload: CrawlUrlRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
    repository: LegalRepository = Depends(get_repository),
) -> IngestionJobResponse:
    return crawl_url(payload, source_policy, repository)


@router.post("/ingestion/promote", response_model=PromoteDocumentResponse)
def promote_legal_document(
    payload: PromoteDocumentRequest,
    source_policy: SourcePolicy = Depends(get_source_policy),
    repository: LegalRepository = Depends(get_repository),
) -> PromoteDocumentResponse:
    response = promote_document(payload, repository, source_policy)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return response


@router.post(
    "/admin/reindex",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=admin_dependencies,
)
def reindex_legal_corpus(
    payload: ReindexRequest,
    repository: LegalRepository = Depends(get_repository),
) -> IngestionJobResponse:
    return reindex_corpus(payload, repository)
