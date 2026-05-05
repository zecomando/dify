from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.repository import LegalDocumentRecord, LegalRepository
from app.schemas import DocumentStatus
from app.source_policy import (
    SourcePolicy,
    SourcePolicyStatus,
    get_default_source_policy_path,
    validate_source_requirements,
)


@dataclass(frozen=True, slots=True)
class ReviewQueueItem:
    document: LegalDocumentRecord
    can_promote_to_chat_ready: bool
    promotion_blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewQueueResult:
    items: tuple[ReviewQueueItem, ...]
    total: int


def chat_ready_promotion_blockers(
    document: LegalDocumentRecord,
    repository: LegalRepository,
    source_policy: SourcePolicy,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if repository.count_chunks_by_document(document.id) == 0:
        blockers.append("Document has no persisted chunks.")
    policy_result = source_policy.check_url(document.source_url)
    if policy_result.status != SourcePolicyStatus.OFFICIAL_AUTHORITY:
        blockers.append(policy_result.reason)
    elif not policy_result.may_ground_answer:
        blockers.append(policy_result.reason)
    elif policy_result.authority is None:
        blockers.append("Source policy authority is missing for official URL.")
    else:
        raw_text = repository.get_document_raw_text(document.id) or ""
        blockers.extend(
            validate_source_requirements(
                policy_result.authority,
                document_type=document.document_type,
                source_url=document.source_url,
                raw_text=raw_text,
                legal_metadata=document.legal_metadata,
            )
        )
    return tuple(blockers)


def build_review_queue_item(
    document: LegalDocumentRecord,
    repository: LegalRepository,
    source_policy: SourcePolicy,
) -> ReviewQueueItem:
    promotion_blockers = chat_ready_promotion_blockers(document, repository, source_policy)
    return ReviewQueueItem(
        document=document,
        can_promote_to_chat_ready=not promotion_blockers,
        promotion_blockers=promotion_blockers,
    )


def list_review_queue(
    repository: LegalRepository,
    source_policy: SourcePolicy,
    *,
    source: str | None = None,
    jurisdiction: str | None = None,
    document_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ReviewQueueResult:
    documents = repository.list_documents(
        status=DocumentStatus.PENDING_REVIEW.value,
        source=source,
        jurisdiction=jurisdiction,
        document_type=document_type,
        limit=limit,
        offset=offset,
    )
    total = repository.count_documents(
        status=DocumentStatus.PENDING_REVIEW.value,
        source=source,
        jurisdiction=jurisdiction,
        document_type=document_type,
    )
    return ReviewQueueResult(
        items=tuple(build_review_queue_item(document, repository, source_policy) for document in documents),
        total=total,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="List Legal Engine pending review documents with promotion blockers.")
    parser.add_argument(
        "--database-path",
        type=Path,
        default=None,
        help="SQLite database path. Defaults to LEGAL_ENGINE_DATABASE_PATH or the local .data database.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL database URL. Defaults to LEGAL_ENGINE_DATABASE_URL when set.",
    )
    parser.add_argument(
        "--source-policy",
        type=Path,
        default=get_default_source_policy_path(),
        help="Path to docs/legal-ai/source-policy.yml.",
    )
    parser.add_argument("--source", default=None)
    parser.add_argument("--jurisdiction", default=None)
    parser.add_argument("--document-type", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="Print the review queue as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    repository = LegalRepository(
        args.database_path or settings.database_path,
        args.database_url or settings.database_url,
    )
    source_policy = SourcePolicy.from_file(args.source_policy)
    result = list_review_queue(
        repository,
        source_policy,
        source=args.source,
        jurisdiction=args.jurisdiction,
        document_type=args.document_type,
        limit=args.limit,
        offset=args.offset,
    )

    if args.json:
        print(json.dumps(_result_dict(result), ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0


def _print_human_result(result: ReviewQueueResult) -> None:
    print(f"pending_review documents: total={result.total}, shown={len(result.items)}")
    for item in result.items:
        document = item.document
        status = "READY" if item.can_promote_to_chat_ready else "BLOCKED"
        print(
            f"{status} {document.id}: source={document.source}, type={document.document_type}, "
            f"title={document.title}, url={document.source_url}"
        )
        for blocker in item.promotion_blockers:
            print(f"  blocker: {blocker}")


def _result_dict(result: ReviewQueueResult) -> dict[str, object]:
    return {
        "total": result.total,
        "items": [_item_dict(item) for item in result.items],
    }


def _item_dict(item: ReviewQueueItem) -> dict[str, object]:
    document = item.document
    return {
        "document": {
            "id": document.id,
            "source": document.source,
            "jurisdiction": document.jurisdiction,
            "document_type": document.document_type,
            "title": document.title,
            "source_url": document.source_url,
            "status": document.status,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        },
        "can_promote_to_chat_ready": item.can_promote_to_chat_ready,
        "promotion_blockers": list(item.promotion_blockers),
    }


if __name__ == "__main__":
    raise SystemExit(main())
