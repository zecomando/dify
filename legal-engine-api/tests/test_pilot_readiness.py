import json
from pathlib import Path

from app.corpus import seed_initial_corpus
from app.ingestion import ingest_source
from app.pilot_readiness import main, run_pilot_readiness
from app.repository import LegalRepository
from app.schemas import IngestionSourceRequest
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def test_run_pilot_readiness_reports_closed_pilot_snapshot_for_seeded_corpus(tmp_path: Path):
    repository = LegalRepository(tmp_path / "pilot-readiness.sqlite3")
    seed_initial_corpus(repository, _source_policy())

    result = run_pilot_readiness(
        repository,
        require_postgresql=False,
        require_admin_token=False,
        admin_token=None,
        min_chat_ready_documents=10,
        allow_pending_review=False,
        allow_rejected_jobs=False,
        require_passed_evaluation=False,
        require_answer_audits=False,
    )

    assert result.passed is True
    assert result.backend == "sqlite"
    assert result.snapshot.documents["chat_ready"] >= 10
    assert result.snapshot.documents["pending_review"] == 0
    assert result.snapshot.ingestion_jobs["rejected"] == 0
    assert result.snapshot.sources
    assert any(source.source == "DRE" for source in result.snapshot.sources)
    assert {check.name for check in result.checks} == {
        "database_backend",
        "admin_token",
        "chat_ready_corpus",
        "pending_review_queue",
        "rejected_ingestion_jobs",
        "answer_audits",
        "evaluation_runs",
    }


def test_run_pilot_readiness_includes_freeze_metadata(tmp_path: Path):
    repository = LegalRepository(tmp_path / "pilot-readiness.sqlite3")
    seed_initial_corpus(repository, _source_policy())

    result = run_pilot_readiness(
        repository,
        require_postgresql=False,
        require_admin_token=False,
        admin_token=None,
        min_chat_ready_documents=10,
        allow_pending_review=False,
        allow_rejected_jobs=False,
        require_passed_evaluation=False,
        require_answer_audits=False,
        generated_at="2026-05-07T20:00:00+00:00",
        pilot_area="Contratação pública",
        pilot_scope="Perguntas canónicas do piloto fechado.",
        freeze_note="Freeze editorial aprovado.",
    )

    assert result.freeze.generated_at == "2026-05-07T20:00:00+00:00"
    assert result.freeze.pilot_area == "Contratação pública"
    assert result.freeze.pilot_scope == "Perguntas canónicas do piloto fechado."
    assert result.freeze.freeze_note == "Freeze editorial aprovado."


def test_run_pilot_readiness_blocks_pending_review_documents_by_default(tmp_path: Path):
    repository = LegalRepository(tmp_path / "pilot-readiness.sqlite3")
    ingest_source(
        IngestionSourceRequest(source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil"),
        _source_policy(),
        repository,
    )

    result = run_pilot_readiness(
        repository,
        require_postgresql=False,
        require_admin_token=False,
        admin_token=None,
        min_chat_ready_documents=0,
        allow_pending_review=False,
        allow_rejected_jobs=False,
        require_passed_evaluation=False,
        require_answer_audits=False,
    )

    assert result.passed is False
    pending_check = next(check for check in result.checks if check.name == "pending_review_queue")
    assert pending_check.passed is False
    assert "pending_review=1" in pending_check.message
    assert result.snapshot.review_queue_total == 1
    assert result.snapshot.review_queue_blocked == 1


def test_pilot_readiness_cli_prints_json_snapshot(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "pilot-readiness.sqlite3")
    seed_initial_corpus(repository, _source_policy())
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-pilot-readiness",
            "--database-path",
            str(tmp_path / "pilot-readiness.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
            "--min-chat-ready-documents",
            "10",
            "--skip-answer-audit-check",
            "--skip-evaluation-check",
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert '"documents"' in captured.out
    assert '"chat_ready"' in captured.out
    assert '"sources"' in captured.out


def test_pilot_readiness_cli_writes_freeze_artifact_when_gate_passes(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "pilot-readiness.sqlite3")
    seed_initial_corpus(repository, _source_policy())
    freeze_output = tmp_path / "pilot-freeze.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-pilot-readiness",
            "--database-path",
            str(tmp_path / "pilot-readiness.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
            "--min-chat-ready-documents",
            "10",
            "--skip-answer-audit-check",
            "--skip-evaluation-check",
            "--pilot-area",
            "Contratação pública",
            "--pilot-scope",
            "Perguntas canónicas do piloto fechado.",
            "--freeze-note",
            "Freeze editorial aprovado.",
            "--freeze-output",
            str(freeze_output),
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    artifact = json.loads(freeze_output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert artifact["passed"] is True
    assert artifact["freeze"]["pilot_area"] == "Contratação pública"
    assert artifact["freeze"]["pilot_scope"] == "Perguntas canónicas do piloto fechado."
    assert artifact["freeze"]["freeze_note"] == "Freeze editorial aprovado."
    assert artifact["snapshot"]["documents"]["chat_ready"] >= 10
