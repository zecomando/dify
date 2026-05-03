from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import get_repository
from app.ingestion import crawl_url, ingest_source, promote_document, reindex_corpus
from app.main import app
from app.repository import LegalRepository
from app.schemas import (
    CrawlUrlRequest,
    IngestionJobStatus,
    IngestionSourceRequest,
    PromoteDocumentRequest,
    ReindexRequest,
)
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def _repository(tmp_path: Path) -> LegalRepository:
    return LegalRepository(tmp_path / "legal-engine.sqlite3")


def test_ingest_source_creates_completed_job_and_pending_review_document(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            area=["civil"],
        ),
        _source_policy(),
        repository,
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "DRE"
    assert document.jurisdiction == "portugal"
    assert document.status == "pending_review"
    assert document.area == ("civil",)
    assert len(document.sha256) == 64


def test_ingest_source_promotes_valid_document_when_requested(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-do-trabalho",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )

    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.status == "chat_ready"


def test_ingest_source_rejects_non_authoritative_source_without_document(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(source_url="https://pt.wikipedia.org/wiki/Codigo_Civil"),
        _source_policy(),
        repository,
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.REJECTED
    assert job is not None
    assert job.document_id is None
    assert job.error_message is not None


def test_crawl_url_rejects_blocked_url_but_keeps_discovery_url_pending(tmp_path: Path):
    repository = _repository(tmp_path)

    blocked_response = crawl_url(
        CrawlUrlRequest(url="https://pt.wikipedia.org/wiki/Direito"),
        _source_policy(),
        repository,
    )
    discovery_response = crawl_url(
        CrawlUrlRequest(url="https://www.gov.pt/noticias/exemplo"),
        _source_policy(),
        repository,
    )

    assert blocked_response.status == IngestionJobStatus.REJECTED
    assert discovery_response.status == IngestionJobStatus.PENDING


def test_promote_document_updates_existing_document_status(tmp_path: Path):
    repository = _repository(tmp_path)
    response = ingest_source(
        IngestionSourceRequest(source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil"),
        _source_policy(),
        repository,
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None

    promoted = promote_document(PromoteDocumentRequest(document_id=job.document_id), repository)

    assert promoted is not None
    assert promoted.document_id == job.document_id
    assert promoted.status == "chat_ready"


def test_reindex_corpus_creates_pending_job(tmp_path: Path):
    repository = _repository(tmp_path)

    response = reindex_corpus(ReindexRequest(source="DRE", force=True), repository)

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.PENDING
    assert job is not None
    assert job.mode == "reindex"
    assert job.source == "DRE"


def test_ingest_source_persists_chunks_from_raw_text(tmp_path: Path):
    repository = _repository(tmp_path)
    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nTexto do artigo.",
        ),
        _source_policy(),
        repository,
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None

    chunks = repository.list_chunks_by_document(job.document_id)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "article"
    assert chunks[0].citation_label == "Artigo 1.º"
    assert "Texto do artigo" in chunks[0].text_content


def test_ingestion_source_route_uses_repository_dependency_override(tmp_path: Path):
    repository = _repository(tmp_path)
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    try:
        response = client.post(
            "/ingestion/source",
            json={"source_url": "https://dre.pt/dre/legislacao-consolidada/codigo-civil"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    job = repository.get_job(response.json()["job_id"])
    assert job is not None
    assert job.document_id is not None


def test_promote_route_returns_404_for_missing_document(tmp_path: Path):
    repository = _repository(tmp_path)
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    try:
        response = client.post(
            "/ingestion/promote",
            json={"document_id": "missing-document"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
