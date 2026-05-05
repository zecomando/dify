from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.corpus import InitialCorpusSeedResult, seed_initial_corpus
from app.demo import DemoCaseResult, run_demo
from app.evaluation import get_default_evals_dir, persist_evaluation_run, run_evaluation
from app.repository import LegalRepository
from app.source_policy import SourcePolicy, get_default_source_policy_path


class SmokeSeedSummary(BaseModel):
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


class SmokeChatCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    expected_verdict: str
    verdict: str
    success: bool
    audit_id: str | None
    evidence_count: int
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SmokeRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    backend: str
    database_target: str
    seed: SmokeSeedSummary
    chat_cases: list[SmokeChatCase]
    evaluation_run_id: str
    evaluation_passed: bool
    evaluation_total_cases: int
    evaluation_successful_cases: int
    evaluation_failed_cases: int
    diagnostics: dict[str, int]


def run_smoke(
    *,
    database_path: Path,
    database_url: str | None,
    source_policy_path: Path,
    evals_dir: Path,
) -> SmokeRunResult:
    repository = LegalRepository(database_path, database_url)
    source_policy = SourcePolicy.from_file(source_policy_path)
    seed_result = seed_initial_corpus(repository, source_policy)
    demo_result = run_demo(
        database_path=database_path,
        database_url=database_url,
        source_policy_path=source_policy_path,
        seed_corpus=False,
    )
    evaluation_result = run_evaluation(evals_dir, source_policy_path, database_path, database_url)
    evaluation_run = persist_evaluation_run(evaluation_result, evals_dir, repository)
    diagnostics = _diagnostics(repository)
    passed = (
        seed_result.rejected_jobs == 0
        and seed_result.chat_ready_documents > 0
        and demo_result.passed
        and evaluation_result.passed
    )
    return SmokeRunResult(
        passed=passed,
        backend=repository.backend,
        database_target=database_url or str(database_path),
        seed=_seed_summary(seed_result),
        chat_cases=[_chat_case_summary(case) for case in demo_result.cases],
        evaluation_run_id=evaluation_run.id,
        evaluation_passed=evaluation_result.passed,
        evaluation_total_cases=evaluation_result.metrics.total_cases,
        evaluation_successful_cases=evaluation_result.metrics.successful_cases,
        evaluation_failed_cases=evaluation_result.metrics.failed_cases,
        diagnostics=diagnostics,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Legal Engine local/staging smoke and print a traceable report.")
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
    parser.add_argument(
        "--evals-dir",
        type=Path,
        default=get_default_evals_dir(),
        help="Path to docs/legal-ai/evals.",
    )
    parser.add_argument("--json", action="store_true", help="Print the smoke result as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    result = run_smoke(
        database_path=args.database_path or settings.database_path,
        database_url=args.database_url or settings.database_url,
        source_policy_path=args.source_policy,
        evals_dir=args.evals_dir,
    )
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0 if result.passed else 1


def _seed_summary(seed_result: InitialCorpusSeedResult) -> SmokeSeedSummary:
    return SmokeSeedSummary(
        total_seeds=seed_result.total_seeds,
        created_documents=seed_result.created_documents,
        already_present_documents=seed_result.already_present_documents,
        completed_jobs=seed_result.completed_jobs,
        rejected_jobs=seed_result.rejected_jobs,
        chat_ready_documents=seed_result.chat_ready_documents,
        pending_review_documents=seed_result.pending_review_documents,
        document_ids=list(seed_result.document_ids),
        rejected_source_urls=list(seed_result.rejected_source_urls),
    )


def _chat_case_summary(case: DemoCaseResult) -> SmokeChatCase:
    return SmokeChatCase(
        id=case.id,
        question=case.question,
        expected_verdict=case.expected_verdict,
        verdict=case.verdict,
        success=case.success,
        audit_id=case.audit_id,
        evidence_count=case.evidence_count,
        sources=list(case.sources),
        warnings=list(case.warnings),
    )


def _diagnostics(repository: LegalRepository) -> dict[str, int]:
    return {
        "documents_total": repository.count_documents(),
        "chat_ready_documents": repository.count_documents(status="chat_ready"),
        "pending_review_documents": repository.count_documents(status="pending_review"),
        "archived_documents": repository.count_documents(status="archived"),
        "rejected_documents": repository.count_documents(status="rejected"),
        "ingestion_jobs_total": repository.count_jobs(),
        "ingestion_jobs_completed": repository.count_jobs(status="completed"),
        "ingestion_jobs_rejected": repository.count_jobs(status="rejected"),
        "ingestion_jobs_pending": repository.count_jobs(status="pending"),
        "answer_audits_total": repository.count_answer_audits(),
        "answer_feedback_total": repository.count_answer_feedback(),
        "evaluation_runs_total": repository.count_evaluation_runs(),
    }


def _print_human_result(result: SmokeRunResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(f"{status} smoke: backend={result.backend}, target={result.database_target}")
    print(
        "seed: "
        f"chat_ready={result.seed.chat_ready_documents}, "
        f"created={result.seed.created_documents}, "
        f"already_present={result.seed.already_present_documents}, "
        f"rejected={result.seed.rejected_jobs}"
    )
    for case in result.chat_cases:
        case_status = "PASS" if case.success else "FAIL"
        print(
            f"{case_status} chat {case.id}: "
            f"verdict={case.verdict}, evidence={case.evidence_count}, audit_id={case.audit_id}"
        )
    evaluation_status = "PASS" if result.evaluation_passed else "FAIL"
    print(
        f"{evaluation_status} evaluation: "
        f"run_id={result.evaluation_run_id}, "
        f"successful={result.evaluation_successful_cases}/{result.evaluation_total_cases}"
    )
    print(
        "diagnostics: "
        f"documents={result.diagnostics['documents_total']}, "
        f"chat_ready={result.diagnostics['chat_ready_documents']}, "
        f"jobs={result.diagnostics['ingestion_jobs_total']}, "
        f"audits={result.diagnostics['answer_audits_total']}, "
        f"evaluation_runs={result.diagnostics['evaluation_runs_total']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
