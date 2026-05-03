from __future__ import annotations

import hashlib
from uuid import uuid4

from app.chunking import chunk_text
from app.repository import IngestionJobRecord, LegalDocumentRecord, LegalRepository, utc_now_iso
from app.schemas import (
    CrawlUrlRequest,
    IngestionJobResponse,
    IngestionJobStatus,
    IngestionSourceRequest,
    PromoteDocumentRequest,
    PromoteDocumentResponse,
    ReindexRequest,
)
from app.source_policy import SourcePolicy, SourcePolicyStatus


def ingest_source(
    payload: IngestionSourceRequest,
    source_policy: SourcePolicy,
    repository: LegalRepository,
) -> IngestionJobResponse:
    policy_result = source_policy.check_url(payload.source_url)
    now = utc_now_iso()

    if policy_result.status != SourcePolicyStatus.OFFICIAL_AUTHORITY or not policy_result.may_ground_answer:
        job = IngestionJobRecord(
            id=str(uuid4()),
            source=payload.source or policy_result.domain or "unknown",
            source_url=payload.source_url,
            requested_by=None,
            mode="manual",
            status=IngestionJobStatus.REJECTED.value,
            error_message=policy_result.reason,
            document_id=None,
            created_at=now,
            updated_at=now,
        )
        repository.create_job(job)
        return IngestionJobResponse(job_id=job.id, status=IngestionJobStatus.REJECTED)

    authority = policy_result.authority
    source = payload.source or (authority.source if authority else "UNKNOWN")
    jurisdiction = payload.jurisdiction or (authority.jurisdiction if authority else "unknown")
    document_type = payload.document_type or _default_document_type(
        authority.allowed_document_types if authority else []
    )
    document_status = "chat_ready" if payload.promote_if_valid else "pending_review"
    legal_value_warning = _legal_value_warning(authority.requires_consolidation_warning if authority else False)
    document = LegalDocumentRecord(
        id=str(uuid4()),
        source=source,
        jurisdiction=jurisdiction,
        document_type=document_type,
        title=_document_title(source, payload.source_url),
        source_url=payload.source_url,
        status=document_status,
        sha256=_source_hash(payload.source_url, payload.raw_text),
        is_current=True,
        is_consolidated=bool(authority.requires_consolidation_warning if authority else False),
        legal_value_warning=legal_value_warning,
        area=tuple(payload.area),
        created_at=now,
        updated_at=now,
    )
    repository.create_document(document)
    for chunk in chunk_text(payload.raw_text or "", document_id=document.id, created_at=now):
        repository.create_chunk(chunk)

    job = IngestionJobRecord(
        id=str(uuid4()),
        source=source,
        source_url=payload.source_url,
        requested_by=None,
        mode="manual",
        status=IngestionJobStatus.COMPLETED.value,
        error_message=None,
        document_id=document.id,
        created_at=now,
        updated_at=now,
    )
    repository.create_job(job)
    return IngestionJobResponse(job_id=job.id, status=IngestionJobStatus.COMPLETED)


def crawl_url(
    payload: CrawlUrlRequest, source_policy: SourcePolicy, repository: LegalRepository
) -> IngestionJobResponse:
    policy_result = source_policy.check_url(payload.url)
    now = utc_now_iso()
    status = IngestionJobStatus.PENDING
    error_message = None
    if policy_result.status in {SourcePolicyStatus.BLOCKED, SourcePolicyStatus.INVALID_URL}:
        status = IngestionJobStatus.REJECTED
        error_message = policy_result.reason

    job = IngestionJobRecord(
        id=str(uuid4()),
        source=policy_result.domain or "unknown",
        source_url=payload.url,
        requested_by=None,
        mode="crawl",
        status=status.value,
        error_message=error_message,
        document_id=None,
        created_at=now,
        updated_at=now,
    )
    repository.create_job(job)
    return IngestionJobResponse(job_id=job.id, status=status)


def promote_document(payload: PromoteDocumentRequest, repository: LegalRepository) -> PromoteDocumentResponse | None:
    document = repository.promote_document(payload.document_id, payload.target_status)
    if document is None:
        return None
    return PromoteDocumentResponse(document_id=document.id, status=document.status)


def reindex_corpus(payload: ReindexRequest, repository: LegalRepository) -> IngestionJobResponse:
    now = utc_now_iso()
    job = IngestionJobRecord(
        id=str(uuid4()),
        source=payload.source or "all",
        source_url=",".join(payload.document_ids) if payload.document_ids else "all",
        requested_by=None,
        mode="reindex",
        status=IngestionJobStatus.PENDING.value,
        error_message=None,
        document_id=payload.document_ids[0] if len(payload.document_ids) == 1 else None,
        created_at=now,
        updated_at=now,
    )
    repository.create_job(job)
    return IngestionJobResponse(job_id=job.id, status=IngestionJobStatus.PENDING)


def _source_hash(source_url: str, raw_text: str | None) -> str:
    value = f"{source_url}\n{raw_text or ''}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _default_document_type(allowed_document_types: list[str]) -> str:
    if allowed_document_types:
        return allowed_document_types[0]
    return "legal_document"


def _document_title(source: str, source_url: str) -> str:
    return f"{source} source {source_url}"


def _legal_value_warning(requires_consolidation_warning: bool) -> str:
    if not requires_consolidation_warning:
        return ""
    return "Texto consolidado: confirmar atos originais antes de conclusão jurídica final."
