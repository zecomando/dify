from __future__ import annotations

import json
import statistics
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.corpus import seed_initial_corpus
from app.pipeline import answer_chat
from app.repository import EvaluationRunRecord, LegalRepository, utc_now_iso
from app.schemas import ChatAnswerRequest, ValidatorVerdict
from app.source_policy import SourcePolicy

JsonObject = dict[str, object]


class EvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dataset: str
    query: str
    expected_behavior: str
    verdict: ValidatorVerdict
    success: bool
    audit_id: str | None
    latency_ms: int
    evidence_count: int
    source_domains: list[str] = Field(default_factory=list)
    missing_expected_domains: list[str] = Field(default_factory=list)
    forbidden_identifier_found: list[str] = Field(default_factory=list)
    failure_reason: str = ""


class EvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cases: int
    successful_cases: int
    failed_cases: int
    benchmark_pass_rate: float
    source_precision: float
    official_domain_rate: float
    citation_coverage: float
    correct_abstention_on_no_source: float
    hallucination_guard_rate: float
    audit_coverage: float
    median_latency_ms: int


class QualityGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    actual: float
    threshold: str


class EvaluationRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    metrics: EvaluationMetrics
    quality_gates: list[QualityGateResult]
    cases: list[EvaluationCaseResult]


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evals_dir: str | None = None


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    passed: bool
    total_cases: int
    successful_cases: int
    failed_cases_count: int
    metrics: EvaluationMetrics
    quality_gates: list[QualityGateResult]
    failed_cases: list[EvaluationCaseResult]
    evals_dir: str
    created_at: str


def run_evaluation(
    evals_dir: Path,
    source_policy_path: Path,
    database_path: Path | None = None,
    database_url: str | None = None,
) -> EvaluationRunResult:
    source_policy = SourcePolicy.from_file(source_policy_path)
    if database_path is not None:
        return _run_evaluation_with_paths(
            evals_dir,
            source_policy,
            database_path,
            database_path.with_suffix(".empty.sqlite3"),
            database_url=database_url,
        )

    if database_url is not None:
        with tempfile.TemporaryDirectory(prefix="legal-engine-eval-empty-") as temporary_directory:
            return _run_evaluation_with_paths(
                evals_dir,
                source_policy,
                Path(":memory:"),
                Path(temporary_directory) / "empty.sqlite3",
                database_url=database_url,
            )

    with tempfile.TemporaryDirectory(prefix="legal-engine-eval-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        return _run_evaluation_with_paths(
            evals_dir,
            source_policy,
            temporary_path / "seeded.sqlite3",
            temporary_path / "empty.sqlite3",
        )


def _run_evaluation_with_paths(
    evals_dir: Path,
    source_policy: SourcePolicy,
    seeded_database_path: Path,
    empty_database_path: Path,
    database_url: str | None = None,
) -> EvaluationRunResult:
    seeded_repository = LegalRepository(seeded_database_path, database_url)
    empty_repository = LegalRepository(empty_database_path)
    seed_evaluation_corpus(seeded_repository, source_policy)

    expected_sources = _load_expected_sources(evals_dir / "expected_sources.jsonl")
    cases: list[EvaluationCaseResult] = []

    for raw_case in _load_jsonl(evals_dir / "benchmark_50_questions.jsonl"):
        cases.append(_run_benchmark_case(raw_case, expected_sources, source_policy, seeded_repository))
    for raw_case in _load_jsonl(evals_dir / "no_source_tests.jsonl"):
        cases.append(_run_no_source_case(raw_case, empty_repository, source_policy))
    for raw_case in _load_jsonl(evals_dir / "hallucination_tests.jsonl"):
        cases.append(_run_hallucination_case(raw_case, empty_repository, source_policy))

    metrics = _calculate_metrics(cases)
    quality_gates = _quality_gates(metrics)
    return EvaluationRunResult(
        passed=all(gate.passed for gate in quality_gates),
        metrics=metrics,
        quality_gates=quality_gates,
        cases=cases,
    )


def get_default_evals_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "evals"


def run_and_persist_evaluation(
    *,
    evals_dir: Path,
    source_policy_path: Path,
    repository: LegalRepository,
) -> EvaluationRunResponse:
    result = run_evaluation(evals_dir, source_policy_path)
    run = persist_evaluation_run(result, evals_dir, repository)
    return evaluation_run_to_response(run)


def persist_evaluation_run(
    result: EvaluationRunResult,
    evals_dir: Path,
    repository: LegalRepository,
) -> EvaluationRunRecord:
    failed_cases = [case for case in result.cases if not case.success]
    return repository.create_evaluation_run(
        EvaluationRunRecord(
            id=str(uuid4()),
            passed=result.passed,
            total_cases=result.metrics.total_cases,
            successful_cases=result.metrics.successful_cases,
            failed_cases=result.metrics.failed_cases,
            metrics_json=_json_dump(result.metrics.model_dump(mode="json")),
            quality_gates_json=_json_dump([gate.model_dump(mode="json") for gate in result.quality_gates]),
            failed_cases_json=_json_dump([case.model_dump(mode="json") for case in failed_cases]),
            evals_dir=str(evals_dir),
            created_at=utc_now_iso(),
        )
    )


def evaluation_run_to_response(run: EvaluationRunRecord) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        id=run.id,
        passed=run.passed,
        total_cases=run.total_cases,
        successful_cases=run.successful_cases,
        failed_cases_count=run.failed_cases,
        metrics=EvaluationMetrics(**_json_load_dict(run.metrics_json)),
        quality_gates=[QualityGateResult(**item) for item in _json_load_list(run.quality_gates_json)],
        failed_cases=[EvaluationCaseResult(**item) for item in _json_load_list(run.failed_cases_json)],
        evals_dir=run.evals_dir,
        created_at=run.created_at,
    )


def seed_evaluation_corpus(repository: LegalRepository, source_policy: SourcePolicy) -> None:
    seed_initial_corpus(repository, source_policy)


def _run_benchmark_case(
    raw_case: JsonObject,
    expected_sources: dict[str, list[str]],
    source_policy: SourcePolicy,
    repository: LegalRepository,
) -> EvaluationCaseResult:
    case_id = _string_value(raw_case, "id")
    query = _string_value(raw_case, "query")
    expected_domains = expected_sources.get(case_id) or _string_list(raw_case.get("expected_source_domains"))
    response = answer_chat(
        ChatAnswerRequest(
            question=query,
            jurisdiction=_jurisdiction_override(expected_domains),
            document_types=_benchmark_document_types(),
        ),
        source_policy,
        repository,
    )
    source_domains = _source_domains(response.evidence)
    missing_expected_domains = _missing_expected_domains(source_domains, expected_domains)
    success = response.verdict == ValidatorVerdict.PASS and not missing_expected_domains and bool(response.evidence)
    return _case_result(
        case_id=case_id,
        dataset="benchmark",
        query=query,
        expected_behavior="pass",
        success=success,
        response=response,
        repository=repository,
        source_domains=source_domains,
        missing_expected_domains=missing_expected_domains,
        failure_reason="" if success else "Expected pass with at least one expected official source domain.",
    )


def _run_no_source_case(
    raw_case: JsonObject,
    repository: LegalRepository,
    source_policy: SourcePolicy,
) -> EvaluationCaseResult:
    case_id = _string_value(raw_case, "id")
    query = _string_value(raw_case, "query")
    response = answer_chat(ChatAnswerRequest(question=query), source_policy, repository)
    success = response.verdict == ValidatorVerdict.ABSTAIN
    return _case_result(
        case_id=case_id,
        dataset="no_source",
        query=query,
        expected_behavior="abstain",
        success=success,
        response=response,
        repository=repository,
        source_domains=_source_domains(response.evidence),
        missing_expected_domains=[],
        failure_reason="" if success else "Expected abstention without local corpus evidence.",
    )


def _run_hallucination_case(
    raw_case: JsonObject,
    repository: LegalRepository,
    source_policy: SourcePolicy,
) -> EvaluationCaseResult:
    case_id = _string_value(raw_case, "id")
    query = _string_value(raw_case, "query")
    forbidden_identifiers = _string_list(raw_case.get("forbidden_identifiers"))
    response = answer_chat(ChatAnswerRequest(question=query), source_policy, repository)
    forbidden_found = [identifier for identifier in forbidden_identifiers if identifier in response.answer]
    success = response.verdict in {ValidatorVerdict.ABSTAIN, ValidatorVerdict.FAIL} and not forbidden_found
    return _case_result(
        case_id=case_id,
        dataset="hallucination",
        query=query,
        expected_behavior="fail_or_abstain",
        success=success,
        response=response,
        repository=repository,
        source_domains=_source_domains(response.evidence),
        missing_expected_domains=[],
        forbidden_identifier_found=forbidden_found,
        failure_reason="" if success else "Expected fail/abstain without forbidden identifiers in the answer.",
    )


def _case_result(
    *,
    case_id: str,
    dataset: str,
    query: str,
    expected_behavior: str,
    success: bool,
    response: object,
    repository: LegalRepository,
    source_domains: list[str],
    missing_expected_domains: list[str],
    failure_reason: str,
    forbidden_identifier_found: list[str] | None = None,
) -> EvaluationCaseResult:
    audit_id = getattr(response, "audit_id", None)
    audit = repository.get_answer_audit(audit_id) if audit_id else None
    return EvaluationCaseResult(
        id=case_id,
        dataset=dataset,
        query=query,
        expected_behavior=expected_behavior,
        verdict=getattr(response, "verdict"),
        success=success,
        audit_id=audit_id,
        latency_ms=audit.latency_ms if audit else 0,
        evidence_count=len(getattr(response, "evidence")),
        source_domains=source_domains,
        missing_expected_domains=missing_expected_domains,
        forbidden_identifier_found=forbidden_identifier_found or [],
        failure_reason=failure_reason,
    )


def _calculate_metrics(cases: list[EvaluationCaseResult]) -> EvaluationMetrics:
    successful_cases = sum(1 for case in cases if case.success)
    benchmark_cases = [case for case in cases if case.dataset == "benchmark"]
    no_source_cases = [case for case in cases if case.dataset == "no_source"]
    hallucination_cases = [case for case in cases if case.dataset == "hallucination"]
    pass_cases = [case for case in cases if case.verdict == ValidatorVerdict.PASS]
    evidence_cases = [case for case in cases if case.evidence_count > 0]
    latencies = [case.latency_ms for case in cases if case.audit_id]
    return EvaluationMetrics(
        total_cases=len(cases),
        successful_cases=successful_cases,
        failed_cases=len(cases) - successful_cases,
        benchmark_pass_rate=_rate(sum(1 for case in benchmark_cases if case.success), len(benchmark_cases)),
        source_precision=_rate(
            sum(1 for case in benchmark_cases if not case.missing_expected_domains and case.source_domains),
            len(benchmark_cases),
        ),
        official_domain_rate=_rate(sum(1 for case in evidence_cases if case.source_domains), len(evidence_cases)),
        citation_coverage=_rate(sum(1 for case in pass_cases if case.evidence_count > 0), len(pass_cases)),
        correct_abstention_on_no_source=_rate(sum(1 for case in no_source_cases if case.success), len(no_source_cases)),
        hallucination_guard_rate=_rate(
            sum(1 for case in hallucination_cases if case.success), len(hallucination_cases)
        ),
        audit_coverage=_rate(sum(1 for case in cases if case.audit_id), len(cases)),
        median_latency_ms=int(statistics.median(latencies)) if latencies else 0,
    )


def _quality_gates(metrics: EvaluationMetrics) -> list[QualityGateResult]:
    return [
        _gate("source_precision", metrics.source_precision, 0.90, ">= 0.90"),
        _gate("official_domain_rate", metrics.official_domain_rate, 1.0, ">= 1.00"),
        _gate("citation_coverage", metrics.citation_coverage, 1.0, ">= 1.00"),
        _gate("correct_abstention_on_no_source", metrics.correct_abstention_on_no_source, 0.90, ">= 0.90"),
        _gate("hallucination_guard_rate", metrics.hallucination_guard_rate, 0.95, ">= 0.95"),
        _gate("audit_coverage", metrics.audit_coverage, 1.0, ">= 1.00"),
        QualityGateResult(
            name="median_latency_ms",
            passed=metrics.median_latency_ms <= 12000,
            actual=float(metrics.median_latency_ms),
            threshold="<= 12000",
        ),
    ]


def _gate(name: str, actual: float, minimum: float, threshold: str) -> QualityGateResult:
    return QualityGateResult(name=name, passed=actual >= minimum, actual=actual, threshold=threshold)


def _load_expected_sources(path: Path) -> dict[str, list[str]]:
    expected_sources: dict[str, list[str]] = {}
    for item in _load_jsonl(path):
        question_id = _string_value(item, "question_id")
        domains: list[str] = []
        for source in _object_list(item.get("expected_sources")):
            domains.extend(_string_list(source.get("domain_any")))
        expected_sources[question_id] = domains
    return expected_sources


def _load_jsonl(path: Path) -> list[JsonObject]:
    if not path.exists():
        return []
    items: list[JsonObject] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            items.append(loaded)
    return items


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load_dict(value: str) -> JsonObject:
    loaded = json.loads(value)
    if isinstance(loaded, dict):
        return loaded
    return {}


def _json_load_list(value: str) -> list[JsonObject]:
    loaded = json.loads(value)
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    return []


def _jurisdiction_override(expected_domains: list[str]) -> list[str]:
    if any(domain.endswith("europa.eu") or "echr" in domain or "curia" in domain for domain in expected_domains):
        return ["europa"]
    return ["portugal"]


def _benchmark_document_types() -> list[str]:
    return [
        "legislation",
        "case_law",
        "treaty",
        "procurement_notice",
        "public_contract",
        "official_guidance",
    ]


def _source_domains(evidence_items: object) -> list[str]:
    domains: list[str] = []
    for evidence in evidence_items if isinstance(evidence_items, list) else []:
        domain = _domain(getattr(evidence, "source_url", ""))
        if domain:
            domains.append(domain)
    return sorted(set(domains))


def _missing_expected_domains(actual_domains: list[str], expected_domains: list[str]) -> list[str]:
    if not expected_domains:
        return []
    if any(_domain_matches(actual, expected) for actual in actual_domains for expected in expected_domains):
        return []
    return expected_domains


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _domain_matches(actual: str, expected: str) -> bool:
    normalized_expected = expected.lower().removeprefix("www.")
    return actual == normalized_expected or actual.endswith(f".{normalized_expected}")


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 6)


def _string_value(item: JsonObject, key: str) -> str:
    value = item.get(key)
    return str(value) if value is not None else ""


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _object_list(value: object) -> list[JsonObject]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []
