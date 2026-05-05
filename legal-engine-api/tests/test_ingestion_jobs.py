from pathlib import Path

from app.ingestion import ingest_source
from app.ingestion_jobs import list_ingestion_jobs, main
from app.repository import LegalRepository
from app.schemas import IngestionSourceRequest
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def _seed_jobs(repository: LegalRepository) -> tuple[str, str]:
    source_policy = _source_policy()
    completed_response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nTexto civil.",
            promote_if_valid=True,
        ),
        source_policy,
        repository,
    )
    rejected_response = ingest_source(
        IngestionSourceRequest(source_url="https://pt.wikipedia.org/wiki/Codigo_Civil"),
        source_policy,
        repository,
    )
    return completed_response.job_id, rejected_response.job_id


def test_list_ingestion_jobs_filters_jobs_with_error_and_document_id(tmp_path: Path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    completed_job_id, rejected_job_id = _seed_jobs(repository)

    result = list_ingestion_jobs(repository)
    rejected_result = list_ingestion_jobs(repository, status="rejected")

    assert result.total == 2
    jobs_by_id = {job.id: job for job in result.jobs}
    assert jobs_by_id[completed_job_id].document_id is not None
    assert jobs_by_id[completed_job_id].error_message is None
    assert jobs_by_id[rejected_job_id].document_id is None
    assert jobs_by_id[rejected_job_id].error_message is not None
    assert rejected_result.total == 1
    assert rejected_result.jobs[0].id == rejected_job_id


def test_ingestion_jobs_cli_prints_json_result(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    _, rejected_job_id = _seed_jobs(repository)
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-ingestion-jobs",
            "--database-path",
            str(tmp_path / "legal-engine.sqlite3"),
            "--status",
            "rejected",
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"total": 1' in captured.out
    assert f'"id": "{rejected_job_id}"' in captured.out
    assert '"status": "rejected"' in captured.out
    assert '"document_id": null' in captured.out
    assert '"error_message":' in captured.out


def test_ingestion_jobs_cli_prints_human_result(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    _seed_jobs(repository)
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-ingestion-jobs",
            "--database-path",
            str(tmp_path / "legal-engine.sqlite3"),
            "--status",
            "rejected",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ingestion jobs: total=1, shown=1" in captured.out
    assert "REJECTED" in captured.out
    assert "document_id=-" in captured.out
    assert "error:" in captured.out
