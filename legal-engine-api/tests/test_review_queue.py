from pathlib import Path

from app.ingestion import ingest_source
from app.repository import LegalRepository
from app.review_queue import list_review_queue, main
from app.schemas import IngestionSourceRequest
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def test_list_review_queue_returns_pending_documents_with_blockers(tmp_path: Path):
    repository = LegalRepository(tmp_path / "review-queue.sqlite3")
    source_policy = _source_policy()
    blocked_response = ingest_source(
        IngestionSourceRequest(source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil"),
        source_policy,
        repository,
    )
    ready_response = ingest_source(
        IngestionSourceRequest(
            source_url="https://www.dgsi.pt/jstj.nsf/example",
            document_type="case_law",
            raw_text="Acórdão sobre responsabilidade civil no processo 123/20.0T8LSB.",
            legal_metadata={
                "court": "Supremo Tribunal de Justiça",
                "decision_date": "2024-01-01",
                "process_number": "123/20.0T8LSB",
            },
        ),
        source_policy,
        repository,
    )
    chat_ready_response = ingest_source(
        IngestionSourceRequest(
            source_url="https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX:32016R0679",
            document_type="legislation",
            raw_text="Artigo 1.º\nTexto europeu com identificador CELEX:32016R0679.",
            legal_metadata={"CELEX": "32016R0679"},
            promote_if_valid=True,
        ),
        source_policy,
        repository,
    )
    blocked_job = repository.get_job(blocked_response.job_id)
    ready_job = repository.get_job(ready_response.job_id)
    chat_ready_job = repository.get_job(chat_ready_response.job_id)
    assert blocked_job is not None
    assert blocked_job.document_id is not None
    assert ready_job is not None
    assert ready_job.document_id is not None
    assert chat_ready_job is not None
    assert chat_ready_job.document_id is not None

    result = list_review_queue(repository, source_policy)

    assert result.total == 2
    items_by_id = {item.document.id: item for item in result.items}
    assert chat_ready_job.document_id not in items_by_id
    assert items_by_id[blocked_job.document_id].can_promote_to_chat_ready is False
    assert "Document has no persisted chunks." in items_by_id[blocked_job.document_id].promotion_blockers
    assert items_by_id[ready_job.document_id].can_promote_to_chat_ready is True
    assert items_by_id[ready_job.document_id].promotion_blockers == ()


def test_review_queue_cli_prints_json_result(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "review-queue.sqlite3")
    ingest_source(
        IngestionSourceRequest(source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil"),
        _source_policy(),
        repository,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-review-queue",
            "--database-path",
            str(tmp_path / "review-queue.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"total": 1' in captured.out
    assert '"can_promote_to_chat_ready": false' in captured.out
    assert "Document has no persisted chunks." in captured.out


def test_review_queue_cli_prints_human_result(tmp_path: Path, monkeypatch, capsys):
    repository = LegalRepository(tmp_path / "review-queue.sqlite3")
    ingest_source(
        IngestionSourceRequest(source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil"),
        _source_policy(),
        repository,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-review-queue",
            "--database-path",
            str(tmp_path / "review-queue.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "pending_review documents: total=1, shown=1" in captured.out
    assert "BLOCKED" in captured.out
    assert "blocker: Document has no persisted chunks." in captured.out
