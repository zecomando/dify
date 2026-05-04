from pathlib import Path
from types import SimpleNamespace

from app.config import get_settings
from app.evaluate import main as evaluate_main
from app.evaluation import evaluation_run_to_response, persist_evaluation_run, run_evaluation, seed_evaluation_corpus
from app.repository import LegalRepository
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _write_jsonl(path: Path, rows: list[str]) -> None:
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def test_seed_evaluation_corpus_creates_chat_ready_chunks(tmp_path: Path):
    repository = LegalRepository(tmp_path / "seed.sqlite3")

    seed_evaluation_corpus(repository, _source_policy())

    chunks = repository.list_searchable_chunks(current_only=True)
    assert chunks
    assert any("responsabilidade civil" in chunk.text_content.lower() for chunk in chunks)


def test_run_evaluation_passes_quality_gates_with_minimal_dataset(tmp_path: Path):
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    _write_jsonl(
        evals_dir / "benchmark_50_questions.jsonl",
        [
            '{"id":"q004","area":"Civil","query":"Quais são os requisitos gerais da responsabilidade civil extracontratual?","expected_document_hints":["Código Civil"],"expected_source_domains":["dre.pt"],"must_abstain":false}'
        ],
    )
    _write_jsonl(
        evals_dir / "expected_sources.jsonl",
        [
            '{"question_id":"q004","expected_sources":[{"document_hint":"Código Civil","domain_any":["dre.pt"],"required_metadata":["source_url","is_current"]}]}'
        ],
    )
    _write_jsonl(
        evals_dir / "no_source_tests.jsonl",
        [
            '{"id":"n001","query":"Qual é a orientação jurisprudencial dominante de todos os tribunais portugueses sobre questão não indexada?","expected_behavior":"abstain"}'
        ],
    )
    _write_jsonl(
        evals_dir / "hallucination_tests.jsonl",
        [
            '{"id":"h001","query":"Explica o artigo 999.º do Código dos Contratos Públicos.","expected_behavior":"fail_or_abstain","forbidden_identifiers":["CCP, art. 999.º"]}'
        ],
    )

    result = run_evaluation(evals_dir, POLICY_PATH)

    assert result.passed is True
    assert result.metrics.total_cases == 3
    assert result.metrics.audit_coverage == 1.0
    assert result.metrics.source_precision == 1.0
    assert result.metrics.correct_abstention_on_no_source == 1.0
    assert result.metrics.hallucination_guard_rate == 1.0
    assert all(gate.passed for gate in result.quality_gates)


def test_run_evaluation_reports_failed_expected_source_gate(tmp_path: Path):
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    _write_jsonl(
        evals_dir / "benchmark_50_questions.jsonl",
        [
            '{"id":"q004","area":"Civil","query":"Quais são os requisitos gerais da responsabilidade civil extracontratual?","expected_document_hints":["Código Civil"],"expected_source_domains":["eur-lex.europa.eu"],"must_abstain":false}'
        ],
    )
    _write_jsonl(evals_dir / "expected_sources.jsonl", [])
    _write_jsonl(evals_dir / "no_source_tests.jsonl", [])
    _write_jsonl(evals_dir / "hallucination_tests.jsonl", [])

    result = run_evaluation(evals_dir, POLICY_PATH)

    assert result.passed is False
    assert result.metrics.source_precision == 0.0
    assert result.cases[0].missing_expected_domains == ["eur-lex.europa.eu"]
    assert any(gate.name == "source_precision" and not gate.passed for gate in result.quality_gates)


def test_persist_evaluation_run_stores_failed_cases(tmp_path: Path):
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    _write_jsonl(
        evals_dir / "benchmark_50_questions.jsonl",
        [
            '{"id":"q004","area":"Civil","query":"Quais são os requisitos gerais da responsabilidade civil extracontratual?","expected_source_domains":["eur-lex.europa.eu"],"must_abstain":false}'
        ],
    )
    _write_jsonl(evals_dir / "expected_sources.jsonl", [])
    _write_jsonl(evals_dir / "no_source_tests.jsonl", [])
    _write_jsonl(evals_dir / "hallucination_tests.jsonl", [])
    repository = LegalRepository(tmp_path / "runs.sqlite3")
    result = run_evaluation(evals_dir, POLICY_PATH)

    run = persist_evaluation_run(result, evals_dir, repository)
    loaded_run = repository.get_evaluation_run(run.id)

    assert loaded_run is not None
    response = evaluation_run_to_response(loaded_run)
    assert response.id == run.id
    assert response.passed is False
    assert response.failed_cases_count == 1
    assert response.failed_cases[0].id == "q004"


def test_evaluate_cli_uses_database_url_from_environment(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()

    def fake_run_evaluation(
        evals_dir: Path,
        source_policy_path: Path,
        database_path: Path | None = None,
        database_url: str | None = None,
    ) -> object:
        captured["evals_dir"] = evals_dir
        captured["source_policy_path"] = source_policy_path
        captured["database_path"] = database_path
        captured["database_url"] = database_url
        return SimpleNamespace(
            passed=True,
            quality_gates=[],
            metrics=SimpleNamespace(total_cases=0, successful_cases=0, failed_cases=0, audit_coverage=1.0),
        )

    monkeypatch.setenv("LEGAL_ENGINE_DATABASE_URL", "postgresql://localhost/legal")
    get_settings.cache_clear()
    monkeypatch.setattr("app.evaluate.run_evaluation", fake_run_evaluation)
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-eval",
            "--evals-dir",
            str(evals_dir),
            "--source-policy",
            str(POLICY_PATH),
        ],
    )

    try:
        exit_code = evaluate_main()
    finally:
        get_settings.cache_clear()

    assert exit_code == 0
    assert captured["database_url"] == "postgresql://localhost/legal"
    assert captured["database_path"] is None
