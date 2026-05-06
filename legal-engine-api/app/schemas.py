from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AnswerMode(StrEnum):
    STRICT = "strict"
    ASSISTED = "assisted"
    EXPLORATION = "exploration"


class ValidatorVerdict(StrEnum):
    PASS = "pass"
    ABSTAIN = "abstain"
    FAIL = "fail"


class AnswerFeedbackRating(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AnswerFeedbackCategory(StrEnum):
    WRONG_SOURCE = "wrong_source"
    INCOMPLETE_ANSWER = "incomplete_answer"
    LEGAL_ERROR = "legal_error"
    TOO_VAGUE = "too_vague"
    OUTDATED_SOURCE = "outdated_source"
    OTHER = "other"


class IngestionJobStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"


class DocumentStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    CHAT_READY = "chat_ready"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ClassifyQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    mode: AnswerMode = AnswerMode.STRICT


class ClassifyQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jurisdiction: list[str]
    area: list[str]
    document_types: list[str]
    current_only: bool
    requires_case_law: bool = False
    requires_procurement_data: bool = False
    high_risk: bool = False
    query_rewrite: str


class RetrievalSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    jurisdiction: list[str] = Field(default_factory=list)
    area: list[str] = Field(default_factory=list)
    document_types: list[str] = Field(default_factory=list)
    current_only: bool = True
    as_of_date: str | None = None
    top_k_dense: int = Field(default=40, ge=1, le=200)
    top_k_sparse: int = Field(default=40, ge=1, le=200)
    mode: AnswerMode = AnswerMode.STRICT


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    source: str
    source_url: str
    text: str = Field(min_length=1)
    score: float = 0.0
    vector_id: str | None = None
    jurisdiction: str | None = None
    document_type: str | None = None
    area: list[str] = Field(default_factory=list)
    legal_metadata: dict[str, str] = Field(default_factory=dict)
    citation_label: str | None = None
    is_current: bool = True
    is_consolidated: bool = False
    version_label: str = "current"
    valid_from: str | None = None
    valid_until: str | None = None


class RetrievalSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[RetrievalResult]


class RerankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    results: list[RetrievalResult]
    top_n: int = Field(default=12, ge=1, le=100)


class RerankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[RetrievalResult]


class EvidenceBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    results: list[RetrievalResult]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str | None = None
    citation_label: str
    text: str = Field(min_length=1)
    source_url: str
    canonical_url: str | None = None
    source: str | None = None
    jurisdiction: str | None = None
    document_type: str | None = None
    legal_metadata: dict[str, str] = Field(default_factory=dict)
    is_current: bool = True
    is_consolidated: bool = False
    legal_value_warning: str = ""
    version_label: str = "current"
    valid_from: str | None = None
    valid_until: str | None = None


class EvidenceBuildResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceItem]
    warnings: list[str]


class AnswerGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    evidence: list[EvidenceItem]
    mode: AnswerMode = AnswerMode.STRICT


class AnswerGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_answer: str


class AnswerValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    draft_answer: str
    evidence: list[EvidenceItem]


class AnswerValidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: ValidatorVerdict
    final_safe_answer: str
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    wrong_version_risk: bool = False
    hallucinated_identifiers: list[str] = Field(default_factory=list)


class PipelineStepTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    status: str
    detail: str = ""


class ChatAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    session_id: str | None = None
    user_id: str | None = None
    mode: AnswerMode = AnswerMode.STRICT
    jurisdiction: list[str] = Field(default_factory=list)
    document_types: list[str] = Field(default_factory=list)
    current_only: bool | None = None
    as_of_date: str | None = None
    top_k_dense: int = Field(default=40, ge=1, le=200)
    top_k_sparse: int = Field(default=40, ge=1, le=200)
    top_n: int = Field(default=8, ge=1, le=100)


class ChatAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str | None = None
    answer: str
    verdict: ValidatorVerdict
    classification: ClassifyQueryResponse
    evidence: list[EvidenceItem]
    warnings: list[str] = Field(default_factory=list)
    retrieved_results: list[RetrievalResult] = Field(default_factory=list)
    reranked_results: list[RetrievalResult] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    wrong_version_risk: bool = False
    hallucinated_identifiers: list[str] = Field(default_factory=list)
    pipeline_trace: list[PipelineStepTrace] = Field(default_factory=list)


class AnswerAuditResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str | None = None
    user_id: str | None = None
    user_query: str
    normalized_query: str
    detected_area: list[str]
    detected_jurisdiction: list[str]
    detected_document_types: list[str]
    mode: AnswerMode
    retrieved_chunks: list[RetrievalResult]
    reranked_chunks: list[RetrievalResult]
    evidence: list[EvidenceItem]
    draft_answer: str
    validator_report: AnswerValidateResponse
    final_answer: str
    confidence: str
    abstained: bool
    verdict: ValidatorVerdict
    model_generator: str | None = None
    model_validator: str | None = None
    generator_prompt_version: str | None = None
    validator_prompt_version: str | None = None
    embedding_model: str | None = None
    reranker_model: str | None = None
    latency_ms: int
    estimated_cost_usd: float
    created_at: str


class LegalDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    area: list[str]
    legal_metadata: dict[str, str]
    version_label: str = "current"
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes_document_id: str | None = None
    archived_at: str | None = None
    change_note: str = ""
    created_at: str
    updated_at: str


class LegalDocumentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[LegalDocumentResponse]
    total: int


class AdminDocumentReviewQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: LegalDocumentResponse
    can_promote_to_chat_ready: bool
    promotion_blockers: list[str]


class AdminDocumentReviewQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AdminDocumentReviewQueueItem]
    total: int


class LegalChunkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document_id: str
    chunk_type: str
    structural_path: str | None = None
    citation_label: str | None = None
    text_content: str
    token_count: int | None = None
    created_at: str


class LegalChunkListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunks: list[LegalChunkResponse]
    total: int


class LegalDocumentRawTextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    raw_text: str


class AdminDocumentStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: DocumentStatus
    change_note: str = Field(default="", max_length=2000)


class AdminDocumentStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: LegalDocumentResponse


class AnswerAuditSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str | None = None
    user_id: str | None = None
    user_query: str
    verdict: ValidatorVerdict
    confidence: str
    abstained: bool
    latency_ms: int
    estimated_cost_usd: float
    created_at: str


class AnswerAuditListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audits: list[AnswerAuditSummaryResponse]
    total: int


class AnswerFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(min_length=1)
    rating: AnswerFeedbackRating
    category: AnswerFeedbackCategory | None = None
    comment: str | None = Field(default=None, max_length=2000)
    user_id: str | None = None
    session_id: str | None = None


class AnswerFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    audit_id: str
    rating: AnswerFeedbackRating
    category: AnswerFeedbackCategory | None = None
    comment: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    created_at: str


class AnswerFeedbackListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: list[AnswerFeedbackResponse]
    total: int


class AnswerFeedbackTriageItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: AnswerFeedbackResponse
    audit_id: str
    session_id: str | None = None
    user_id: str | None = None
    user_query: str
    final_answer: str
    verdict: ValidatorVerdict
    confidence: str
    abstained: bool
    evidence_count: int
    audit_created_at: str


class AnswerFeedbackTriageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AnswerFeedbackTriageItemResponse]
    total: int


class EvaluationRunSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    passed: bool
    total_cases: int
    successful_cases: int
    failed_cases_count: int
    evals_dir: str
    created_at: str


class EvaluationRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[EvaluationRunSummaryResponse]
    total: int


class InitialCorpusSeedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_seeds: int
    created_documents: int
    already_present_documents: int
    completed_jobs: int
    rejected_jobs: int
    chat_ready_documents: int
    pending_review_documents: int
    document_ids: list[str]
    rejected_source_urls: list[str]


class IngestionSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str = Field(min_length=1)
    raw_text: str | None = None
    source: str | None = None
    jurisdiction: str | None = None
    document_type: str | None = None
    area: list[str] = Field(default_factory=list)
    legal_metadata: dict[str, str] = Field(default_factory=dict)
    version_label: str = "current"
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes_document_id: str | None = None
    archive_existing_current: bool = False
    change_note: str = ""
    promote_if_valid: bool = False


class CrawlUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    limit: int = Field(default=1, ge=1, le=100)
    only_main_content: bool = True
    fetch_attempts: int = Field(default=1, ge=1, le=5)


class PromoteDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    target_status: str = "chat_ready"
    change_note: str = Field(default="", max_length=2000)


class PromoteDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    status: str


class ReindexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[str] = Field(default_factory=list)
    source: str | None = None
    jurisdiction: str | None = None
    force: bool = False


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: IngestionJobStatus


class IngestionJobDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    source_url: str
    requested_by: str | None = None
    mode: str
    status: IngestionJobStatus
    error_message: str | None = None
    document_id: str | None = None
    created_at: str
    updated_at: str


class IngestionJobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[IngestionJobDetailResponse]
    total: int


class AdminDiagnosticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    database_backend: str
    source_policy_name: str
    source_policy_version: int
    documents_total: int
    chat_ready_documents: int
    pending_review_documents: int
    archived_documents: int
    rejected_documents: int
    ingestion_jobs_total: int
    ingestion_jobs_completed: int
    ingestion_jobs_rejected: int
    ingestion_jobs_pending: int
    answer_audits_total: int
    answer_feedback_total: int
    evaluation_runs_total: int


class AdminMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: dict[str, int]
    ingestion_jobs: dict[str, int]
    answer_audits: dict[str, int]
    answer_feedback: dict[str, int]
    evaluation_runs: dict[str, int]


class ProviderReadinessItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: str
    required_for: str
    paid: bool
    configured: bool
    configured_env_vars: list[str]
    missing_env_vars: list[str]
    optional_env_vars: list[str]
    notes: str


class AdminProviderReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    providers_total: int
    configured_providers: int
    missing_providers: int
    paid_provider_blockers: list[str]
    providers: list[ProviderReadinessItem]
