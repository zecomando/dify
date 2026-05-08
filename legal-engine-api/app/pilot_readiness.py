from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.repository import LegalRepository, utc_now_iso
from app.review_queue import list_review_queue
from app.schemas import AnswerFeedbackRating, DocumentStatus, IngestionJobStatus, ValidatorVerdict
from app.source_policy import SourcePolicy, get_default_source_policy_path


@dataclass(frozen=True, slots=True)
class PilotReadinessCheckResult:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class PilotFreezeMetadata:
    generated_at: str
    pilot_area: str | None
    pilot_scope: str | None
    freeze_note: str | None


@dataclass(frozen=True, slots=True)
class PilotCorpusSourceSummary:
    source: str
    total: int
    chat_ready: int
    pending_review: int
    rejected: int
    archived: int


@dataclass(frozen=True, slots=True)
class PilotCorpusSnapshot:
    documents: dict[str, int]
    ingestion_jobs: dict[str, int]
    answer_audits: dict[str, int]
    answer_feedback: dict[str, int]
    evaluation_runs: dict[str, int]
    sources: tuple[PilotCorpusSourceSummary, ...]
    review_queue_total: int
    review_queue_blocked: int


@dataclass(frozen=True, slots=True)
class PilotReadinessRunResult:
    passed: bool
    backend: str
    database_target: str
    freeze: PilotFreezeMetadata
    snapshot: PilotCorpusSnapshot
    checks: tuple[PilotReadinessCheckResult, ...]


def run_pilot_readiness(
    repository: LegalRepository,
    *,
    source_policy: SourcePolicy | None = None,
    require_postgresql: bool = False,
    require_admin_token: bool = False,
    admin_token: str | None = None,
    min_chat_ready_documents: int = 10,
    allow_pending_review: bool = False,
    allow_rejected_jobs: bool = False,
    require_passed_evaluation: bool = True,
    require_answer_audits: bool = True,
    generated_at: str | None = None,
    pilot_area: str | None = None,
    pilot_scope: str | None = None,
    freeze_note: str | None = None,
) -> PilotReadinessRunResult:
    resolved_source_policy = source_policy or SourcePolicy.from_file(get_default_source_policy_path())
    snapshot = build_pilot_corpus_snapshot(repository, resolved_source_policy)
    checks = (
        _database_backend_check(repository, require_postgresql),
        _admin_token_check(admin_token, require_admin_token),
        _chat_ready_corpus_check(snapshot, min_chat_ready_documents),
        _pending_review_queue_check(snapshot, allow_pending_review),
        _rejected_ingestion_jobs_check(snapshot, allow_rejected_jobs),
        _answer_audits_check(snapshot, require_answer_audits),
        _evaluation_runs_check(snapshot, require_passed_evaluation),
    )
    return PilotReadinessRunResult(
        passed=all(check.passed for check in checks),
        backend=repository.backend,
        database_target=repository.database_url or str(repository.database_path),
        freeze=PilotFreezeMetadata(
            generated_at=generated_at or utc_now_iso(),
            pilot_area=pilot_area,
            pilot_scope=pilot_scope,
            freeze_note=freeze_note,
        ),
        snapshot=snapshot,
        checks=checks,
    )


def build_pilot_corpus_snapshot(repository: LegalRepository, source_policy: SourcePolicy) -> PilotCorpusSnapshot:
    review_queue = list_review_queue(repository, source_policy, limit=10_000)
    return PilotCorpusSnapshot(
        documents=_document_counts(repository),
        ingestion_jobs=_ingestion_job_counts(repository),
        answer_audits=_answer_audit_counts(repository),
        answer_feedback=_answer_feedback_counts(repository),
        evaluation_runs=_evaluation_run_counts(repository),
        sources=_source_summaries(repository),
        review_queue_total=review_queue.total,
        review_queue_blocked=sum(1 for item in review_queue.items if not item.can_promote_to_chat_ready),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Legal Engine closed-pilot readiness gates and corpus snapshot.")
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
    parser.add_argument("--require-admin-token", action="store_true")
    parser.add_argument("--require-postgresql", action="store_true")
    parser.add_argument("--min-chat-ready-documents", type=int, default=10)
    parser.add_argument("--allow-pending-review", action="store_true")
    parser.add_argument("--allow-rejected-jobs", action="store_true")
    parser.add_argument("--skip-answer-audit-check", action="store_true")
    parser.add_argument("--skip-evaluation-check", action="store_true")
    parser.add_argument("--pilot-area", default=None)
    parser.add_argument("--pilot-scope", default=None)
    parser.add_argument("--freeze-note", default=None)
    parser.add_argument("--freeze-output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print pilot readiness result as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    repository = LegalRepository(
        args.database_path or settings.database_path,
        args.database_url or settings.database_url,
    )
    result = run_pilot_readiness(
        repository,
        source_policy=SourcePolicy.from_file(args.source_policy),
        require_postgresql=args.require_postgresql,
        require_admin_token=args.require_admin_token,
        admin_token=settings.admin_token,
        min_chat_ready_documents=args.min_chat_ready_documents,
        allow_pending_review=args.allow_pending_review,
        allow_rejected_jobs=args.allow_rejected_jobs,
        require_passed_evaluation=not args.skip_evaluation_check,
        require_answer_audits=not args.skip_answer_audit_check,
        pilot_area=args.pilot_area,
        pilot_scope=args.pilot_scope,
        freeze_note=args.freeze_note,
    )
    result_payload = _result_dict(result)
    if args.freeze_output is not None and result.passed:
        args.freeze_output.parent.mkdir(parents=True, exist_ok=True)
        args.freeze_output.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result_payload, ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0 if result.passed else 1


def _document_counts(repository: LegalRepository) -> dict[str, int]:
    return {
        "total": repository.count_documents(),
        "chat_ready": repository.count_documents(status=DocumentStatus.CHAT_READY.value),
        "pending_review": repository.count_documents(status=DocumentStatus.PENDING_REVIEW.value),
        "rejected": repository.count_documents(status=DocumentStatus.REJECTED.value),
        "archived": repository.count_documents(status=DocumentStatus.ARCHIVED.value),
    }


def _ingestion_job_counts(repository: LegalRepository) -> dict[str, int]:
    return {
        "total": repository.count_jobs(),
        "completed": repository.count_jobs(status=IngestionJobStatus.COMPLETED.value),
        "pending": repository.count_jobs(status=IngestionJobStatus.PENDING.value),
        "rejected": repository.count_jobs(status=IngestionJobStatus.REJECTED.value),
    }


def _answer_audit_counts(repository: LegalRepository) -> dict[str, int]:
    return {
        "total": repository.count_answer_audits(),
        "pass": repository.count_answer_audits(verdict=ValidatorVerdict.PASS.value),
        "abstain": repository.count_answer_audits(verdict=ValidatorVerdict.ABSTAIN.value),
        "fail": repository.count_answer_audits(verdict=ValidatorVerdict.FAIL.value),
        "abstained": repository.count_answer_audits(abstained=True),
    }


def _answer_feedback_counts(repository: LegalRepository) -> dict[str, int]:
    return {
        "total": repository.count_answer_feedback(),
        "positive": repository.count_answer_feedback(rating=AnswerFeedbackRating.POSITIVE.value),
        "negative": repository.count_answer_feedback(rating=AnswerFeedbackRating.NEGATIVE.value),
        "neutral": repository.count_answer_feedback(rating=AnswerFeedbackRating.NEUTRAL.value),
    }


def _evaluation_run_counts(repository: LegalRepository) -> dict[str, int]:
    return {
        "total": repository.count_evaluation_runs(),
        "passed": repository.count_evaluation_runs(passed=True),
        "failed": repository.count_evaluation_runs(passed=False),
    }


def _source_summaries(repository: LegalRepository) -> tuple[PilotCorpusSourceSummary, ...]:
    documents = repository.list_documents(limit=10_000)
    summaries: dict[str, dict[str, int]] = {}
    for document in documents:
        summary = summaries.setdefault(
            document.source,
            {"total": 0, "chat_ready": 0, "pending_review": 0, "rejected": 0, "archived": 0},
        )
        summary["total"] += 1
        if document.status in summary:
            summary[document.status] += 1
    return tuple(
        PilotCorpusSourceSummary(
            source=source,
            total=counts["total"],
            chat_ready=counts["chat_ready"],
            pending_review=counts["pending_review"],
            rejected=counts["rejected"],
            archived=counts["archived"],
        )
        for source, counts in sorted(summaries.items())
    )


def _database_backend_check(repository: LegalRepository, require_postgresql: bool) -> PilotReadinessCheckResult:
    passed = repository.backend == "postgresql" or not require_postgresql
    message = (
        "postgresql configured"
        if repository.backend == "postgresql"
        else "sqlite accepted for this run"
        if passed
        else "requires LEGAL_ENGINE_DATABASE_URL or --database-url for closed-pilot staging"
    )
    return PilotReadinessCheckResult("database_backend", passed, message)


def _admin_token_check(admin_token: str | None, require_admin_token: bool) -> PilotReadinessCheckResult:
    passed = bool(admin_token) or not require_admin_token
    message = (
        "configured" if admin_token else "not required for this run" if passed else "required for closed-pilot staging"
    )
    return PilotReadinessCheckResult("admin_token", passed, message)


def _chat_ready_corpus_check(snapshot: PilotCorpusSnapshot, min_chat_ready_documents: int) -> PilotReadinessCheckResult:
    chat_ready_documents = snapshot.documents["chat_ready"]
    passed = chat_ready_documents >= min_chat_ready_documents
    return PilotReadinessCheckResult(
        "chat_ready_corpus",
        passed,
        f"chat_ready={chat_ready_documents}, min={min_chat_ready_documents}",
    )


def _pending_review_queue_check(snapshot: PilotCorpusSnapshot, allow_pending_review: bool) -> PilotReadinessCheckResult:
    pending_review_documents = snapshot.documents["pending_review"]
    passed = pending_review_documents == 0 or allow_pending_review
    promotable = snapshot.review_queue_total - snapshot.review_queue_blocked
    return PilotReadinessCheckResult(
        "pending_review_queue",
        passed,
        f"pending_review={pending_review_documents}, promotable={promotable}, blocked={snapshot.review_queue_blocked}",
    )


def _rejected_ingestion_jobs_check(
    snapshot: PilotCorpusSnapshot, allow_rejected_jobs: bool
) -> PilotReadinessCheckResult:
    rejected_jobs = snapshot.ingestion_jobs["rejected"]
    passed = rejected_jobs == 0 or allow_rejected_jobs
    return PilotReadinessCheckResult("rejected_ingestion_jobs", passed, f"rejected={rejected_jobs}")


def _answer_audits_check(snapshot: PilotCorpusSnapshot, required: bool) -> PilotReadinessCheckResult:
    audit_total = snapshot.answer_audits["total"]
    passed = audit_total > 0 or not required
    message = f"total={audit_total}, pass={snapshot.answer_audits['pass']}, abstain={snapshot.answer_audits['abstain']}"
    return PilotReadinessCheckResult("answer_audits", passed, message)


def _evaluation_runs_check(snapshot: PilotCorpusSnapshot, required: bool) -> PilotReadinessCheckResult:
    passed_runs = snapshot.evaluation_runs["passed"]
    passed = passed_runs > 0 or not required
    message = (
        f"passed={passed_runs}, failed={snapshot.evaluation_runs['failed']}, total={snapshot.evaluation_runs['total']}"
    )
    return PilotReadinessCheckResult("evaluation_runs", passed, message)


def _print_human_result(result: PilotReadinessRunResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(f"{status} closed-pilot readiness: backend={result.backend}, target={result.database_target}")
    print(f"freeze: generated_at={result.freeze.generated_at}, pilot_area={result.freeze.pilot_area or '-'}")
    print(
        "snapshot: "
        f"documents={result.snapshot.documents['total']}, "
        f"chat_ready={result.snapshot.documents['chat_ready']}, "
        f"pending_review={result.snapshot.documents['pending_review']}, "
        f"rejected_jobs={result.snapshot.ingestion_jobs['rejected']}, "
        f"audits={result.snapshot.answer_audits['total']}, "
        f"evaluation_runs={result.snapshot.evaluation_runs['total']}"
    )
    for source in result.snapshot.sources:
        print(
            f"source {source.source}: total={source.total}, chat_ready={source.chat_ready}, "
            f"pending_review={source.pending_review}, rejected={source.rejected}, archived={source.archived}"
        )
    for check in result.checks:
        check_status = "PASS" if check.passed else "FAIL"
        print(f"{check_status} {check.name}: {check.message}")


def _result_dict(result: PilotReadinessRunResult) -> dict[str, object]:
    return {
        "passed": result.passed,
        "backend": result.backend,
        "database_target": result.database_target,
        "freeze": _freeze_dict(result.freeze),
        "snapshot": _snapshot_dict(result.snapshot),
        "checks": [{"name": check.name, "passed": check.passed, "message": check.message} for check in result.checks],
    }


def _freeze_dict(freeze: PilotFreezeMetadata) -> dict[str, object]:
    return {
        "generated_at": freeze.generated_at,
        "pilot_area": freeze.pilot_area,
        "pilot_scope": freeze.pilot_scope,
        "freeze_note": freeze.freeze_note,
    }


def _snapshot_dict(snapshot: PilotCorpusSnapshot) -> dict[str, object]:
    return {
        "documents": snapshot.documents,
        "ingestion_jobs": snapshot.ingestion_jobs,
        "answer_audits": snapshot.answer_audits,
        "answer_feedback": snapshot.answer_feedback,
        "evaluation_runs": snapshot.evaluation_runs,
        "sources": [_source_dict(source) for source in snapshot.sources],
        "review_queue_total": snapshot.review_queue_total,
        "review_queue_blocked": snapshot.review_queue_blocked,
    }


def _source_dict(source: PilotCorpusSourceSummary) -> dict[str, object]:
    return {
        "source": source.source,
        "total": source.total,
        "chat_ready": source.chat_ready,
        "pending_review": source.pending_review,
        "rejected": source.rejected,
        "archived": source.archived,
    }


if __name__ == "__main__":
    raise SystemExit(main())
