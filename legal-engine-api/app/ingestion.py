from __future__ import annotations

import hashlib
from uuid import uuid4

from app.chunking import chunk_text
from app.remote_sources import RemoteFetcher, RemoteFetchError, UrllibRemoteFetcher, parse_remote_legal_source
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
from app.source_policy import SourcePolicy, SourcePolicyCheckResult, SourcePolicyStatus, validate_source_requirements
from app.vector_index import index_chunk_embeddings


def ingest_source(
    payload: IngestionSourceRequest,
    source_policy: SourcePolicy,
    repository: LegalRepository,
) -> IngestionJobResponse:
    policy_result = source_policy.check_url(payload.source_url)
    return _ingest_source_payload(payload, policy_result, repository, mode="manual")


def _ingest_source_payload(
    payload: IngestionSourceRequest,
    policy_result: SourcePolicyCheckResult,
    repository: LegalRepository,
    *,
    mode: str,
) -> IngestionJobResponse:
    now = utc_now_iso()

    if policy_result.status != SourcePolicyStatus.OFFICIAL_AUTHORITY or not policy_result.may_ground_answer:
        job = IngestionJobRecord(
            id=str(uuid4()),
            source=payload.source or policy_result.domain or "unknown",
            source_url=payload.source_url,
            requested_by=None,
            mode=mode,
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
    raw_text = payload.raw_text or ""
    source_hash = _source_hash(payload.source_url, raw_text)
    legal_metadata = _normalize_legal_metadata(payload.legal_metadata)
    existing_current_document = repository.get_document_by_source_url(payload.source_url)
    supersedes_document_id = payload.supersedes_document_id
    if (
        existing_current_document is not None
        and existing_current_document.is_current
        and existing_current_document.sha256 == source_hash
        and not payload.archive_existing_current
    ):
        return _create_ingestion_job(
            source=source,
            source_url=payload.source_url,
            mode=mode,
            status=IngestionJobStatus.COMPLETED,
            error_message=None,
            document_id=existing_current_document.id,
            repository=repository,
        )
    source_requirement_violations = (
        validate_source_requirements(
            authority,
            document_type=document_type,
            source_url=payload.source_url,
            raw_text=raw_text,
            legal_metadata=legal_metadata,
        )
        if authority is not None
        else []
    )
    disallowed_type_violations = [
        violation for violation in source_requirement_violations if violation.startswith("Document type ")
    ]
    if disallowed_type_violations:
        job = IngestionJobRecord(
            id=str(uuid4()),
            source=source,
            source_url=payload.source_url,
            requested_by=None,
            mode=mode,
            status=IngestionJobStatus.REJECTED.value,
            error_message=disallowed_type_violations[0],
            document_id=None,
            created_at=now,
            updated_at=now,
        )
        repository.create_job(job)
        return IngestionJobResponse(job_id=job.id, status=IngestionJobStatus.REJECTED)
    should_archive_current_document = payload.archive_existing_current or (
        existing_current_document is not None
        and existing_current_document.is_current
        and existing_current_document.sha256 != source_hash
    )
    if should_archive_current_document:
        archived_document = repository.archive_current_document_version(
            source_url=payload.source_url,
            valid_until=payload.valid_from,
            change_note=payload.change_note or "Superseded by a newer ingested document version.",
        )
        if archived_document is not None and supersedes_document_id is None:
            supersedes_document_id = archived_document.id
    document_id = str(uuid4())
    chunks = chunk_text(raw_text, document_id=document_id, created_at=now)
    document_status = (
        "chat_ready" if payload.promote_if_valid and chunks and not source_requirement_violations else "pending_review"
    )
    legal_value_warning = _legal_value_warning(authority.requires_consolidation_warning if authority else False)
    document = LegalDocumentRecord(
        id=document_id,
        source=source,
        jurisdiction=jurisdiction,
        document_type=document_type,
        title=_document_title(source, payload.source_url),
        source_url=payload.source_url,
        status=document_status,
        sha256=source_hash,
        is_current=True,
        is_consolidated=bool(authority.requires_consolidation_warning if authority else False),
        legal_value_warning=legal_value_warning,
        area=tuple(payload.area),
        legal_metadata=legal_metadata,
        created_at=now,
        updated_at=now,
        version_label=payload.version_label,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        supersedes_document_id=supersedes_document_id,
        change_note=payload.change_note,
    )
    repository.create_document(document)
    if payload.raw_text is not None:
        repository.save_document_raw_text(document.id, payload.raw_text, now)
    for chunk in chunks:
        repository.create_chunk(chunk)
    index_chunk_embeddings(repository, chunks)

    job = IngestionJobRecord(
        id=str(uuid4()),
        source=source,
        source_url=payload.source_url,
        requested_by=None,
        mode=mode,
        status=IngestionJobStatus.COMPLETED.value,
        error_message=None,
        document_id=document.id,
        created_at=now,
        updated_at=now,
    )
    repository.create_job(job)
    return IngestionJobResponse(job_id=job.id, status=IngestionJobStatus.COMPLETED)


def crawl_url(
    payload: CrawlUrlRequest,
    source_policy: SourcePolicy,
    repository: LegalRepository,
    fetcher: RemoteFetcher | None = None,
) -> IngestionJobResponse:
    policy_result = source_policy.check_url(payload.url)
    if policy_result.status in {SourcePolicyStatus.BLOCKED, SourcePolicyStatus.INVALID_URL}:
        return _create_ingestion_job(
            source=policy_result.domain or "unknown",
            source_url=payload.url,
            mode="crawl",
            status=IngestionJobStatus.REJECTED,
            error_message=policy_result.reason,
            document_id=None,
            repository=repository,
        )
    if policy_result.status != SourcePolicyStatus.OFFICIAL_AUTHORITY or not policy_result.may_ground_answer:
        return _create_ingestion_job(
            source=policy_result.domain or "unknown",
            source_url=payload.url,
            mode="crawl",
            status=IngestionJobStatus.PENDING,
            error_message=None,
            document_id=None,
            repository=repository,
        )
    if policy_result.authority is None:
        return _create_ingestion_job(
            source=policy_result.domain or "unknown",
            source_url=payload.url,
            mode="crawl",
            status=IngestionJobStatus.REJECTED,
            error_message="Source policy authority is missing for official URL.",
            document_id=None,
            repository=repository,
        )

    remote_fetcher = fetcher or UrllibRemoteFetcher()
    fetch_error: RemoteFetchError | None = None
    try:
        fetched_source = None
        for _ in range(payload.fetch_attempts):
            try:
                fetched_source = remote_fetcher.fetch(payload.url)
                break
            except RemoteFetchError as exc:
                fetch_error = exc
        if fetched_source is None:
            if fetch_error is None:
                raise RemoteFetchError("Remote fetch failed.")
            raise fetch_error
        parsed_source = parse_remote_legal_source(
            source_url=payload.url,
            fetched_text=fetched_source.text,
            authority=policy_result.authority,
        )
    except (RemoteFetchError, ValueError) as exc:
        return _create_ingestion_job(
            source=policy_result.authority.source,
            source_url=payload.url,
            mode="crawl",
            status=IngestionJobStatus.REJECTED,
            error_message=str(exc),
            document_id=None,
            repository=repository,
        )

    return _ingest_source_payload(
        IngestionSourceRequest(
            source_url=parsed_source.source_url,
            raw_text=parsed_source.raw_text,
            source=parsed_source.source,
            jurisdiction=parsed_source.jurisdiction,
            document_type=parsed_source.document_type,
            area=list(parsed_source.area),
            legal_metadata=parsed_source.legal_metadata,
            promote_if_valid=parsed_source.promote_if_valid,
        ),
        policy_result,
        repository,
        mode="crawl",
    )


def promote_document(
    payload: PromoteDocumentRequest,
    repository: LegalRepository,
    source_policy: SourcePolicy | None = None,
) -> PromoteDocumentResponse | None:
    if payload.target_status == "chat_ready":
        document = repository.get_document(payload.document_id)
        if document is None:
            return None
        if repository.count_chunks_by_document(payload.document_id) == 0:
            return PromoteDocumentResponse(document_id=document.id, status=document.status)
        if source_policy is not None:
            policy_result = source_policy.check_url(document.source_url)
            raw_text = repository.get_document_raw_text(document.id) or ""
            violations = (
                validate_source_requirements(
                    policy_result.authority,
                    document_type=document.document_type,
                    source_url=document.source_url,
                    raw_text=raw_text,
                    legal_metadata=document.legal_metadata,
                )
                if policy_result.authority is not None
                else [policy_result.reason]
            )
            if (
                policy_result.status != SourcePolicyStatus.OFFICIAL_AUTHORITY
                or not policy_result.may_ground_answer
                or violations
            ):
                return PromoteDocumentResponse(document_id=document.id, status=document.status)
    document = repository.promote_document(
        payload.document_id,
        payload.target_status,
        change_note=payload.change_note,
    )
    if document is None:
        return None
    return PromoteDocumentResponse(document_id=document.id, status=document.status)


def reindex_corpus(payload: ReindexRequest, repository: LegalRepository) -> IngestionJobResponse:
    now = utc_now_iso()
    documents = _documents_for_reindex(payload, repository)
    reindexed_document_ids: list[str] = []
    skipped_document_ids: list[str] = []
    for document in documents:
        raw_text = repository.get_document_raw_text(document.id)
        if raw_text is None:
            skipped_document_ids.append(document.id)
            continue
        chunks = chunk_text(raw_text, document_id=document.id, created_at=now)
        if not chunks:
            skipped_document_ids.append(document.id)
            if document.status == "chat_ready":
                repository.promote_document(document.id, "pending_review")
            continue
        repository.replace_document_chunks(document.id, chunks)
        index_chunk_embeddings(repository, chunks)
        reindexed_document_ids.append(document.id)

    status = IngestionJobStatus.COMPLETED if reindexed_document_ids else IngestionJobStatus.REJECTED
    error_message = (
        _reindex_error_message(documents, skipped_document_ids) if status == IngestionJobStatus.REJECTED else None
    )
    job = IngestionJobRecord(
        id=str(uuid4()),
        source=payload.source or "all",
        source_url=",".join(payload.document_ids) if payload.document_ids else "all",
        requested_by=None,
        mode="reindex",
        status=status.value,
        error_message=error_message,
        document_id=payload.document_ids[0] if len(payload.document_ids) == 1 else None,
        created_at=now,
        updated_at=now,
    )
    repository.create_job(job)
    return IngestionJobResponse(job_id=job.id, status=status)


def _source_hash(source_url: str, raw_text: str | None) -> str:
    value = f"{source_url}\n{raw_text or ''}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _create_ingestion_job(
    *,
    source: str,
    source_url: str,
    mode: str,
    status: IngestionJobStatus,
    error_message: str | None,
    document_id: str | None,
    repository: LegalRepository,
) -> IngestionJobResponse:
    now = utc_now_iso()
    job = IngestionJobRecord(
        id=str(uuid4()),
        source=source,
        source_url=source_url,
        requested_by=None,
        mode=mode,
        status=status.value,
        error_message=error_message,
        document_id=document_id,
        created_at=now,
        updated_at=now,
    )
    repository.create_job(job)
    return IngestionJobResponse(job_id=job.id, status=status)


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


def _normalize_legal_metadata(legal_metadata: dict[str, str]) -> dict[str, str]:
    return {
        key.strip().lower(): value.strip() for key, value in legal_metadata.items() if key.strip() and value.strip()
    }


def _documents_for_reindex(payload: ReindexRequest, repository: LegalRepository) -> tuple[LegalDocumentRecord, ...]:
    if payload.document_ids:
        return repository.list_documents_by_ids(tuple(payload.document_ids))
    return repository.list_documents(
        source=payload.source,
        jurisdiction=payload.jurisdiction,
        limit=10000,
    )


def _reindex_error_message(documents: tuple[LegalDocumentRecord, ...], skipped_document_ids: list[str]) -> str:
    if not documents:
        return "No documents matched the reindex request."
    if skipped_document_ids:
        return f"No documents could be reindexed. Missing or empty raw text for: {', '.join(skipped_document_ids)}."
    return "No documents could be reindexed."
