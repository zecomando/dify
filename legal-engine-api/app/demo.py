from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.corpus import seed_initial_corpus
from app.pipeline import answer_chat
from app.repository import LegalRepository
from app.schemas import ChatAnswerRequest, ValidatorVerdict
from app.source_policy import SourcePolicy, get_default_source_policy_path


@dataclass(frozen=True, slots=True)
class DemoCase:
    id: str
    question: str
    expected_verdict: ValidatorVerdict


@dataclass(frozen=True, slots=True)
class DemoCaseResult:
    id: str
    question: str
    expected_verdict: str
    verdict: str
    success: bool
    audit_id: str | None
    evidence_count: int
    sources: tuple[str, ...]
    warnings: tuple[str, ...]
    answer: str


@dataclass(frozen=True, slots=True)
class DemoRunResult:
    passed: bool
    seed_created_documents: int
    seed_already_present_documents: int
    seed_chat_ready_documents: int
    seed_rejected_jobs: int
    cases: tuple[DemoCaseResult, ...]


def run_demo(
    *,
    database_path: Path,
    database_url: str | None = None,
    source_policy_path: Path,
    questions: tuple[str, ...] = (),
    seed_corpus: bool = True,
) -> DemoRunResult:
    repository = LegalRepository(database_path, database_url)
    source_policy = SourcePolicy.from_file(source_policy_path)
    seed_result = seed_initial_corpus(repository, source_policy) if seed_corpus else None
    cases = _custom_cases(questions) if questions else _default_cases()
    case_results = tuple(_run_case(case, repository, source_policy) for case in cases)
    return DemoRunResult(
        passed=all(result.success for result in case_results),
        seed_created_documents=seed_result.created_documents if seed_result is not None else 0,
        seed_already_present_documents=seed_result.already_present_documents if seed_result is not None else 0,
        seed_chat_ready_documents=seed_result.chat_ready_documents if seed_result is not None else 0,
        seed_rejected_jobs=seed_result.rejected_jobs if seed_result is not None else 0,
        cases=case_results,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local Legal Engine demo smoke without external providers.")
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
        "--question",
        action="append",
        default=[],
        help="Custom question to run. Can be repeated. Custom questions are expected to pass.",
    )
    parser.add_argument("--no-seed", action="store_true", help="Skip seeding before running the demo cases.")
    parser.add_argument("--json", action="store_true", help="Print the demo result as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    database_path = args.database_path or settings.database_path
    database_url = args.database_url or settings.database_url
    result = run_demo(
        database_path=database_path,
        database_url=database_url,
        source_policy_path=args.source_policy,
        questions=tuple(args.question),
        seed_corpus=not args.no_seed,
    )

    if args.json:
        print(json.dumps(_result_dict(result), ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0 if result.passed and result.seed_rejected_jobs == 0 else 1


def _run_case(case: DemoCase, repository: LegalRepository, source_policy: SourcePolicy) -> DemoCaseResult:
    response = answer_chat(ChatAnswerRequest(question=case.question), source_policy, repository)
    sources = tuple(sorted({evidence.source or evidence.source_url for evidence in response.evidence}))
    success = response.verdict == case.expected_verdict and (
        response.verdict != ValidatorVerdict.PASS or bool(response.evidence)
    )
    return DemoCaseResult(
        id=case.id,
        question=case.question,
        expected_verdict=case.expected_verdict.value,
        verdict=response.verdict.value,
        success=success,
        audit_id=response.audit_id,
        evidence_count=len(response.evidence),
        sources=sources,
        warnings=tuple(response.warnings),
        answer=response.answer,
    )


def _default_cases() -> tuple[DemoCase, ...]:
    return (
        DemoCase(
            id="civil-liability",
            question="Quais são os pressupostos da responsabilidade civil extracontratual?",
            expected_verdict=ValidatorVerdict.PASS,
        ),
        DemoCase(
            id="rgpd-lawfulness",
            question="No RGPD da União Europeia, quais são as bases de licitude para tratamento de dados pessoais?",
            expected_verdict=ValidatorVerdict.PASS,
        ),
        DemoCase(
            id="insufficient-source",
            question="Qual é a orientação dominante sobre uma questão jurídica local sem corpus indexado?",
            expected_verdict=ValidatorVerdict.ABSTAIN,
        ),
    )


def _custom_cases(questions: tuple[str, ...]) -> tuple[DemoCase, ...]:
    return tuple(
        DemoCase(id=f"custom-{index}", question=question, expected_verdict=ValidatorVerdict.PASS)
        for index, question in enumerate(questions, start=1)
    )


def _print_human_result(result: DemoRunResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(
        f"{status} legal-demo: "
        f"seed_created={result.seed_created_documents}, "
        f"seed_existing={result.seed_already_present_documents}, "
        f"seed_chat_ready={result.seed_chat_ready_documents}, "
        f"seed_rejected={result.seed_rejected_jobs}"
    )
    for case in result.cases:
        case_status = "PASS" if case.success else "FAIL"
        sources = ", ".join(case.sources) if case.sources else "none"
        print(
            f"{case_status} {case.id}: verdict={case.verdict}, "
            f"expected={case.expected_verdict}, evidence={case.evidence_count}, sources={sources}, audit={case.audit_id}"
        )


def _result_dict(result: DemoRunResult) -> dict[str, object]:
    return {
        "passed": result.passed,
        "seed_created_documents": result.seed_created_documents,
        "seed_already_present_documents": result.seed_already_present_documents,
        "seed_chat_ready_documents": result.seed_chat_ready_documents,
        "seed_rejected_jobs": result.seed_rejected_jobs,
        "cases": [
            {
                "id": case.id,
                "question": case.question,
                "expected_verdict": case.expected_verdict,
                "verdict": case.verdict,
                "success": case.success,
                "audit_id": case.audit_id,
                "evidence_count": case.evidence_count,
                "sources": list(case.sources),
                "warnings": list(case.warnings),
                "answer": case.answer,
            }
            for case in result.cases
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
