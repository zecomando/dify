from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.repository import AnswerAuditRecord, AnswerFeedbackRecord, LegalRepository
from app.schemas import AnswerFeedbackCategory


@dataclass(frozen=True, slots=True)
class FeedbackTriageItem:
    feedback: AnswerFeedbackRecord
    audit: AnswerAuditRecord
    evidence_count: int


@dataclass(frozen=True, slots=True)
class FeedbackTriageResult:
    items: tuple[FeedbackTriageItem, ...]
    total: int


def list_feedback_triage(
    repository: LegalRepository,
    *,
    category: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> FeedbackTriageResult:
    feedback_items = repository.list_answer_feedback(
        rating="negative",
        category=category,
        session_id=session_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    items: list[FeedbackTriageItem] = []
    for feedback in feedback_items:
        audit = repository.get_answer_audit(feedback.audit_id)
        if audit is None:
            continue
        items.append(FeedbackTriageItem(feedback=feedback, audit=audit, evidence_count=_evidence_count(audit)))
    total = repository.count_answer_feedback(
        rating="negative",
        category=category,
        session_id=session_id,
        user_id=user_id,
    )
    return FeedbackTriageResult(items=tuple(items), total=total)


def main() -> int:
    parser = argparse.ArgumentParser(description="List negative Legal Engine answer feedback with audit context.")
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
        "--category",
        choices=tuple(category.value for category in AnswerFeedbackCategory),
        default=None,
        help="Filter by negative feedback category.",
    )
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--user-id", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="Print feedback triage as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    repository = LegalRepository(
        args.database_path or settings.database_path,
        args.database_url or settings.database_url,
    )
    result = list_feedback_triage(
        repository,
        category=args.category,
        session_id=args.session_id,
        user_id=args.user_id,
        limit=args.limit,
        offset=args.offset,
    )

    if args.json:
        print(json.dumps(_result_dict(result), ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0


def _print_human_result(result: FeedbackTriageResult) -> None:
    print(f"negative feedback triage: total={result.total}, shown={len(result.items)}")
    for item in result.items:
        feedback = item.feedback
        audit = item.audit
        category = feedback.category or "-"
        print(
            f"NEGATIVE {feedback.id}: category={category}, audit_id={audit.id}, verdict={audit.verdict}, "
            f"confidence={audit.confidence}, query={audit.user_query}"
        )
        if feedback.comment:
            print(f"  comment: {feedback.comment}")
        print(f"  final_answer: {audit.final_answer}")


def _result_dict(result: FeedbackTriageResult) -> dict[str, object]:
    return {
        "total": result.total,
        "items": [_item_dict(item) for item in result.items],
    }


def _item_dict(item: FeedbackTriageItem) -> dict[str, object]:
    feedback = item.feedback
    audit = item.audit
    return {
        "feedback": {
            "id": feedback.id,
            "audit_id": feedback.audit_id,
            "rating": feedback.rating,
            "category": feedback.category,
            "comment": feedback.comment,
            "user_id": feedback.user_id,
            "session_id": feedback.session_id,
            "created_at": feedback.created_at,
        },
        "audit_id": audit.id,
        "session_id": audit.session_id,
        "user_id": audit.user_id,
        "user_query": audit.user_query,
        "final_answer": audit.final_answer,
        "verdict": audit.verdict,
        "confidence": audit.confidence,
        "abstained": audit.abstained,
        "evidence_count": item.evidence_count,
        "audit_created_at": audit.created_at,
    }


def _evidence_count(audit: AnswerAuditRecord) -> int:
    loaded = json.loads(audit.evidence_json)
    return len(loaded) if isinstance(loaded, list) else 0


if __name__ == "__main__":
    raise SystemExit(main())
