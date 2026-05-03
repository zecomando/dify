from functools import lru_cache
from pathlib import Path
from secrets import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict

from app.audit import answer_audit_to_response
from app.config import get_settings
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
    EvaluationRunRecord,
    LegalChunkRecord,
    LegalDocumentRecord,
    LegalRepository,
)
from app.schemas import (
    AdminDocumentStatusRequest,
    AdminDocumentStatusResponse,
    AnswerGenerateRequest,
    AnswerGenerateResponse,
    AnswerAuditResponse,
    AnswerAuditListResponse,
    AnswerAuditSummaryResponse,
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
    IngestionJobResponse,
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
    return LegalRepository(get_settings().database_path)


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
        created_at=document.created_at,
        updated_at=document.updated_at,
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
    repository: LegalRepository = Depends(get_repository),
) -> AdminDocumentStatusResponse:
    document = repository.promote_document(document_id, payload.target_status.value)
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
    repository: LegalRepository = Depends(get_repository),
) -> PromoteDocumentResponse:
    response = promote_document(payload, repository)
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
