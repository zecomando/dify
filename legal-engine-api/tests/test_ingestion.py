from pathlib import Path
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_repository
from app.ingestion import crawl_url, ingest_source, promote_document, reindex_corpus
from app.remote_sources import PermanentRemoteFetchError, RemoteFetchError, RemoteFetchResult, UrllibRemoteFetcher
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


class FakeRemoteFetcher:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.text = text
        self.error = error

    def fetch(self, url: str) -> RemoteFetchResult:
        if self.error is not None:
            raise self.error
        assert self.text is not None
        return RemoteFetchResult(final_url=url, status_code=200, content_type="text/html", text=self.text)


class FlakyRemoteFetcher:
    def __init__(self, *, failures_before_success: int, text: str) -> None:
        self.failures_before_success = failures_before_success
        self.text = text
        self.calls = 0

    def fetch(self, url: str) -> RemoteFetchResult:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RemoteFetchError("Temporary remote fetch failure.")
        return RemoteFetchResult(final_url=url, status_code=200, content_type="text/html", text=self.text)


class PermanentErrorRemoteFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, url: str) -> RemoteFetchResult:
        self.calls += 1
        raise PermanentRemoteFetchError("Unsupported remote content type: application/pdf.")


class FakeUrlopenHeaders:
    def __init__(self, *, content_type: str, charset: str | None = "utf-8") -> None:
        self.content_type = content_type
        self.charset = charset

    def get_content_charset(self) -> str | None:
        return self.charset

    def get_content_type(self) -> str:
        return self.content_type


class FakeUrlopenResponse:
    def __init__(self, *, body: bytes, content_type: str = "text/html") -> None:
        self.body = body
        self.headers = FakeUrlopenHeaders(content_type=content_type)

    def __enter__(self) -> "FakeUrlopenResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.body[:size]

    def geturl(self) -> str:
        return "https://dre.pt/example"

    def getcode(self) -> int:
        return 200


def test_urllib_remote_fetcher_rejects_oversized_remote_response(monkeypatch):
    def fake_urlopen(request: object, timeout: int) -> FakeUrlopenResponse:
        return FakeUrlopenResponse(body=b"abcdef")

    monkeypatch.setattr("app.remote_sources.urlopen", fake_urlopen)

    with pytest.raises(RemoteFetchError, match="exceeded maximum size"):
        UrllibRemoteFetcher(max_bytes=5).fetch("https://dre.pt/example")


def test_urllib_remote_fetcher_rejects_non_text_remote_response(monkeypatch):
    def fake_urlopen(request: object, timeout: int) -> FakeUrlopenResponse:
        return FakeUrlopenResponse(body=b"%PDF-1.7", content_type="application/pdf")

    monkeypatch.setattr("app.remote_sources.urlopen", fake_urlopen)

    with pytest.raises(RemoteFetchError, match="Unsupported remote content type: application/pdf"):
        UrllibRemoteFetcher().fetch("https://dre.pt/example.pdf")


def test_urllib_remote_fetcher_treats_http_404_as_permanent_error(monkeypatch):
    def fake_urlopen(request: object, timeout: int) -> FakeUrlopenResponse:
        raise HTTPError("https://dre.pt/missing", 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr("app.remote_sources.urlopen", fake_urlopen)

    with pytest.raises(PermanentRemoteFetchError, match="Remote fetch failed with HTTP 404"):
        UrllibRemoteFetcher().fetch("https://dre.pt/missing")


def test_urllib_remote_fetcher_treats_http_503_as_transient_error(monkeypatch):
    def fake_urlopen(request: object, timeout: int) -> FakeUrlopenResponse:
        raise HTTPError("https://dre.pt/unavailable", 503, "Service Unavailable", hdrs=None, fp=None)

    monkeypatch.setattr("app.remote_sources.urlopen", fake_urlopen)

    with pytest.raises(RemoteFetchError, match="Remote fetch failed with HTTP 503") as exc_info:
        UrllibRemoteFetcher().fetch("https://dre.pt/unavailable")
    assert not isinstance(exc_info.value, PermanentRemoteFetchError)


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
            raw_text="Artigo 1.º\nTexto laboral.",
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


def test_ingest_source_reuses_current_document_when_hash_is_unchanged(tmp_path: Path):
    repository = _repository(tmp_path)
    payload = IngestionSourceRequest(
        source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
        raw_text="Artigo 1.º\nTexto oficial.",
        promote_if_valid=True,
    )

    first_response = ingest_source(payload, _source_policy(), repository)
    second_response = ingest_source(payload, _source_policy(), repository)

    first_job = repository.get_job(first_response.job_id)
    second_job = repository.get_job(second_response.job_id)
    assert first_job is not None
    assert second_job is not None
    assert first_job.document_id is not None
    assert second_job.document_id == first_job.document_id
    assert repository.count_documents() == 1


def test_ingest_source_archives_current_version_when_hash_changes(tmp_path: Path):
    repository = _repository(tmp_path)
    source_url = "https://dre.pt/dre/legislacao-consolidada/codigo-civil"
    first_response = ingest_source(
        IngestionSourceRequest(
            source_url=source_url,
            raw_text="Artigo 1.º\nTexto inicial.",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )
    first_job = repository.get_job(first_response.job_id)
    assert first_job is not None
    assert first_job.document_id is not None
    first_document = repository.get_document(first_job.document_id)
    assert first_document is not None

    second_response = ingest_source(
        IngestionSourceRequest(
            source_url=source_url,
            raw_text="Artigo 1.º\nTexto atualizado.",
            valid_from="2026-01-01",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )

    second_job = repository.get_job(second_response.job_id)
    archived_document = repository.get_document(first_document.id)
    assert second_job is not None
    assert second_job.document_id is not None
    second_document = repository.get_document(second_job.document_id)
    assert archived_document is not None
    assert second_document is not None
    assert second_document.id != first_document.id
    assert second_document.supersedes_document_id == first_document.id
    assert second_document.is_current is True
    assert second_document.sha256 != first_document.sha256
    assert archived_document.status == "archived"
    assert archived_document.is_current is False
    assert archived_document.valid_until == "2026-01-01"
    assert archived_document.archived_at is not None
    assert repository.get_document_by_source_url(source_url).id == second_document.id
    assert repository.count_documents() == 2
    assert repository.list_chunks_by_document(first_document.id)


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


def test_ingest_source_rejects_disallowed_document_type_for_authority(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            document_type="case_law",
            raw_text="Artigo 1.º\nTexto oficial.",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.REJECTED
    assert job is not None
    assert job.document_id is None
    assert job.error_message == "Document type case_law is not allowed for DRE."


def test_ingest_source_keeps_eurlex_without_required_identifier_pending_review(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://eur-lex.europa.eu/legal-content/PT/TXT/",
            document_type="legislation",
            raw_text="Artigo 1.º\nTexto europeu sem identificador.",
            promote_if_valid=True,
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
    assert document.status == "pending_review"


def test_ingest_source_promotes_eurlex_with_required_identifier(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX:32016R0679",
            document_type="legislation",
            raw_text="Artigo 1.º\nTexto europeu com identificador CELEX:32016R0679.",
            legal_metadata={"CELEX": "32016R0679"},
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
    assert document.legal_metadata == {"celex": "32016R0679"}


def test_ingest_source_keeps_case_law_without_required_metadata_pending_review(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://www.dgsi.pt/jstj.nsf/example",
            document_type="case_law",
            raw_text="Acórdão sobre responsabilidade civil.",
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
    assert document.status == "pending_review"


def test_ingest_source_promotes_case_law_with_required_metadata(tmp_path: Path):
    repository = _repository(tmp_path)

    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://www.dgsi.pt/jstj.nsf/example",
            document_type="case_law",
            raw_text="Acórdão sobre responsabilidade civil no processo 123/20.0T8LSB.",
            legal_metadata={
                "court": "STJ",
                "decision_date": "2024-01-01",
                "process_number": "123/20.0T8LSB",
            },
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
    assert document.legal_metadata["court"] == "STJ"


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


def test_crawl_url_fetches_and_ingests_dre_source(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://dre.pt/dre/legislacao-consolidada/codigo-civil"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Código Civil</h1>
            <h2>Artigo 1.º</h2>
            <p>A responsabilidade civil depende de facto, ilicitude, culpa, dano e nexo causal.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.mode == "crawl"
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "DRE"
    assert document.status == "chat_ready"
    assert document.document_type == "legislation"
    assert document.area == ("civil",)
    assert document.legal_value_warning
    assert "responsabilidade civil" in (repository.get_document_raw_text(document.id) or "")
    chunks = repository.list_chunks_by_document(document.id)
    assert any(chunk.citation_label == "Artigo 1.º" for chunk in chunks)


def test_crawl_url_extracts_dre_eli_metadata(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://diariodarepublica.pt/dr/detalhe/decreto-lei/47344-1966"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Decreto-Lei n.º 47344</h1>
            <p>ELI: https://data.dre.pt/eli/dec-lei/47344/1966/11/25/p/dre/pt/html</p>
            <h2>Artigo 1.º</h2>
            <p>Texto oficial.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.legal_metadata["eli"] == "https://data.dre.pt/eli/dec-lei/47344/1966/11/25/p/dre/pt/html"
    assert document.legal_metadata["diploma"] == "Decreto-Lei n.º 47344"


def test_crawl_url_retries_transient_remote_fetch_errors(tmp_path: Path):
    repository = _repository(tmp_path)
    fetcher = FlakyRemoteFetcher(
        failures_before_success=1,
        text="""
        <html><body>
        <h1>Código Civil</h1>
        <h2>Artigo 1.º</h2>
        <p>A responsabilidade civil depende dos pressupostos legais.</p>
        </body></html>
        """,
    )

    response = crawl_url(
        CrawlUrlRequest(url="https://dre.pt/dre/legislacao-consolidada/codigo-civil", fetch_attempts=2),
        _source_policy(),
        repository,
        fetcher,
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert fetcher.calls == 2
    assert job is not None
    assert job.error_message is None


def test_crawl_url_does_not_retry_permanent_remote_fetch_errors(tmp_path: Path):
    repository = _repository(tmp_path)
    fetcher = PermanentErrorRemoteFetcher()

    response = crawl_url(
        CrawlUrlRequest(url="https://dre.pt/dre/legislacao-consolidada/codigo-civil", fetch_attempts=3),
        _source_policy(),
        repository,
        fetcher,
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.REJECTED
    assert fetcher.calls == 1
    assert job is not None
    assert job.error_message == "Unsupported remote content type: application/pdf."


def test_crawl_url_fetches_and_ingests_eurlex_source_with_celex(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX:32016R0679"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Regulamento Geral sobre a Proteção de Dados</h1>
            <h2>Artigo 6.º</h2>
            <p>O RGPD, CELEX:32016R0679, define bases de licitude para dados pessoais.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.mode == "crawl"
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "EURLEX"
    assert document.jurisdiction == "europa"
    assert document.status == "chat_ready"
    assert document.document_type == "legislation"
    assert document.area == ("proteccao_dados",)
    assert document.legal_metadata == {"celex": "32016R0679"}
    chunks = repository.list_chunks_by_document(document.id)
    assert any(chunk.citation_label == "Artigo 6.º" for chunk in chunks)


def test_crawl_url_fetches_and_ingests_dgsi_case_law_with_required_metadata(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://www.dgsi.pt/jstj.nsf/954f0ce6ad9dd8b980256b5f003fa814/example"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Acórdão do Supremo Tribunal de Justiça</h1>
            <p>Tribunal: Supremo Tribunal de Justiça</p>
            <p>Processo: 123/20.0T8LSB.L1.S1</p>
            <p>Data do Acórdão: 2024-01-11</p>
            <p>Responsabilidade civil extracontratual.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "DGSI"
    assert document.status == "pending_review"
    assert document.document_type == "case_law"
    assert document.legal_metadata["court"] == "Supremo Tribunal de Justiça"
    assert document.legal_metadata["process_number"] == "123/20.0T8LSB.L1.S1"
    assert document.legal_metadata["decision_date"] == "2024-01-11"


def test_crawl_url_case_law_can_be_promoted_after_human_review(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://www.dgsi.pt/jstj.nsf/954f0ce6ad9dd8b980256b5f003fa814/example"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Acórdão do Supremo Tribunal de Justiça</h1>
            <p>Tribunal: Supremo Tribunal de Justiça</p>
            <p>Processo: 123/20.0T8LSB.L1.S1</p>
            <p>Data do Acórdão: 2024-01-11</p>
            <p>Responsabilidade civil extracontratual.</p>
            </body></html>
            """
        ),
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None

    promoted = promote_document(
        PromoteDocumentRequest(
            document_id=job.document_id,
            change_note="Approved during human legal review.",
        ),
        repository,
        _source_policy(),
    )

    assert promoted is not None
    assert promoted.status == "chat_ready"
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.status == "chat_ready"
    assert document.change_note == "Approved during human legal review."


def test_crawl_url_fetches_and_ingests_csm_case_law_with_required_metadata(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://jurisprudencia.csm.org.pt/ecli/ECLI:PT:TRL:2024:123.20.0T8LSB.L1"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Acórdão do Tribunal da Relação de Lisboa</h1>
            <p>Tribunal: Tribunal da Relação de Lisboa</p>
            <p>Processo n.º: 123/20.0T8LSB.L1</p>
            <p>Data do Acórdão: 2024-04-18</p>
            <p>Responsabilidade civil e contrato de prestação de serviços.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "CSM_JURISPRUDENCE"
    assert document.status == "pending_review"
    assert document.document_type == "case_law"
    assert document.area == ("civil",)
    assert document.legal_metadata["court"] == "Tribunal da Relação de Lisboa"
    assert document.legal_metadata["process_number"] == "123/20.0T8LSB.L1"
    assert document.legal_metadata["decision_date"] == "2024-04-18"
    assert (
        document.legal_metadata["source_url"]
        == "https://jurisprudencia.csm.org.pt/ecli/ECLI:PT:TRL:2024:123.20.0T8LSB.L1"
    )


def test_crawl_url_fetches_and_ingests_tribunal_constitucional_case_law(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://www.tribunalconstitucional.pt/tc/acordaos/20240123.html"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Acórdão n.º 123/2024</h1>
            <p>Tribunal Constitucional</p>
            <p>Processo n.º 456/23</p>
            <p>Data: 2024-02-08</p>
            <p>Fiscalização concreta da constitucionalidade.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "TRIBUNAL_CONSTITUCIONAL"
    assert document.status == "pending_review"
    assert document.document_type == "case_law"
    assert document.area == ("constitucional",)
    assert document.legal_metadata["court"] == "Tribunal Constitucional"
    assert document.legal_metadata["process_number"] == "456/23"
    assert document.legal_metadata["decision_date"] == "2024-02-08"


def test_crawl_url_fetches_and_ingests_curia_case_law(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://curia.europa.eu/juris/document/document.jsf?text=&docid=123456"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Judgment of the Court</h1>
            <p>Court: Court of Justice</p>
            <p>Case C-311/18</p>
            <p>Date: 2020-07-16</p>
            <p>Protection of personal data and transfers to third countries.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "CURIA"
    assert document.status == "pending_review"
    assert document.document_type == "case_law"
    assert document.legal_metadata["court"] == "Court of Justice"
    assert document.legal_metadata["case_number"] == "C-311/18"
    assert document.legal_metadata["decision_date"] == "2020-07-16"


def test_crawl_url_fetches_and_ingests_infocuria_case_law(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://infocuria.curia.europa.eu/juris/document/document.jsf?docid=654321"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>Judgment of the General Court</h1>
            <p>Court: General Court</p>
            <p>Case T-123/21</p>
            <p>Date: 2023-11-09</p>
            <p>Public procurement and transparency obligations.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "INFOCURIA"
    assert document.status == "pending_review"
    assert document.document_type == "case_law"
    assert document.area == ("contratacao_publica",)
    assert document.legal_metadata["court"] == "General Court"
    assert document.legal_metadata["case_number"] == "T-123/21"
    assert document.legal_metadata["decision_date"] == "2023-11-09"
    assert (
        document.legal_metadata["source_url"]
        == "https://infocuria.curia.europa.eu/juris/document/document.jsf?docid=654321"
    )


def test_crawl_url_fetches_and_ingests_hudoc_case_law(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://hudoc.echr.coe.int/eng?i=001-123456"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(
            """
            <html><body>
            <h1>European Court of Human Rights judgment</h1>
            <p>Court: European Court of Human Rights</p>
            <p>Application no. 12345/20</p>
            <p>Date: 2023-03-14</p>
            <p>Article 6 and fair trial guarantees.</p>
            </body></html>
            """
        ),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.COMPLETED
    assert job is not None
    assert job.document_id is not None
    document = repository.get_document(job.document_id)
    assert document is not None
    assert document.source == "HUDOC"
    assert document.status == "pending_review"
    assert document.document_type == "case_law"
    assert document.legal_metadata["court"] == "European Court of Human Rights"
    assert document.legal_metadata["application_number"] == "12345/20"
    assert document.legal_metadata["decision_date"] == "2023-03-14"


def test_crawl_url_rejects_when_remote_fetch_fails(tmp_path: Path):
    repository = _repository(tmp_path)
    response = crawl_url(
        CrawlUrlRequest(url="https://dre.pt/dre/legislacao-consolidada/codigo-civil"),
        _source_policy(),
        repository,
        FakeRemoteFetcher(error=RemoteFetchError("Remote fetch failed.")),
    )

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.REJECTED
    assert job is not None
    assert job.mode == "crawl"
    assert job.document_id is None
    assert job.error_message == "Remote fetch failed."


def test_promote_document_updates_existing_document_status(tmp_path: Path):
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

    promoted = promote_document(PromoteDocumentRequest(document_id=job.document_id), repository)

    assert promoted is not None
    assert promoted.document_id == job.document_id
    assert promoted.status == "chat_ready"


def test_promote_document_keeps_empty_document_pending_review(tmp_path: Path):
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
    assert promoted.status == "pending_review"


def test_promote_document_with_policy_keeps_missing_required_metadata_pending_review(tmp_path: Path):
    repository = _repository(tmp_path)
    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://www.dgsi.pt/jstj.nsf/example",
            document_type="case_law",
            raw_text="Acórdão sobre responsabilidade civil.",
        ),
        _source_policy(),
        repository,
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None

    promoted = promote_document(PromoteDocumentRequest(document_id=job.document_id), repository, _source_policy())

    assert promoted is not None
    assert promoted.document_id == job.document_id
    assert promoted.status == "pending_review"


def test_promote_document_with_policy_updates_when_required_metadata_exists(tmp_path: Path):
    repository = _repository(tmp_path)
    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://www.dgsi.pt/jstj.nsf/example",
            document_type="case_law",
            raw_text="Acórdão sobre responsabilidade civil.",
            legal_metadata={
                "court": "STJ",
                "decision_date": "2024-01-01",
                "process_number": "123/20.0T8LSB",
            },
        ),
        _source_policy(),
        repository,
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None

    promoted = promote_document(PromoteDocumentRequest(document_id=job.document_id), repository, _source_policy())

    assert promoted is not None
    assert promoted.document_id == job.document_id
    assert promoted.status == "chat_ready"


def test_reindex_corpus_rejects_when_no_documents_match(tmp_path: Path):
    repository = _repository(tmp_path)

    response = reindex_corpus(ReindexRequest(source="DRE", force=True), repository)

    job = repository.get_job(response.job_id)
    assert response.status == IngestionJobStatus.REJECTED
    assert job is not None
    assert job.mode == "reindex"
    assert job.source == "DRE"
    assert job.error_message == "No documents matched the reindex request."


def test_reindex_corpus_rebuilds_chunks_from_raw_text(tmp_path: Path):
    repository = _repository(tmp_path)
    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nTexto inicial.\n\nArtigo 2.º\nTexto adicional.",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None

    reindex_response = reindex_corpus(ReindexRequest(document_ids=[job.document_id], force=True), repository)

    reindex_job = repository.get_job(reindex_response.job_id)
    chunks = repository.list_chunks_by_document(job.document_id)
    assert reindex_response.status == IngestionJobStatus.COMPLETED
    assert reindex_job is not None
    assert reindex_job.status == "completed"
    assert len(chunks) == 2
    assert [chunk.citation_label for chunk in chunks] == ["Artigo 1.º", "Artigo 2.º"]


def test_reindex_corpus_reports_documents_skipped_without_raw_text(tmp_path: Path):
    repository = _repository(tmp_path)
    reindexable_response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nTexto inicial.",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )
    skipped_response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-do-trabalho",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )
    reindexable_job = repository.get_job(reindexable_response.job_id)
    skipped_job = repository.get_job(skipped_response.job_id)
    assert reindexable_job is not None
    assert reindexable_job.document_id is not None
    assert skipped_job is not None
    assert skipped_job.document_id is not None

    reindex_response = reindex_corpus(
        ReindexRequest(document_ids=[reindexable_job.document_id, skipped_job.document_id], force=True),
        repository,
    )

    reindex_job = repository.get_job(reindex_response.job_id)
    assert reindex_response.status == IngestionJobStatus.COMPLETED
    assert reindex_job is not None
    assert reindex_job.error_message == f"Skipped documents without raw text: {skipped_job.document_id}."


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
    raw_text = repository.get_document_raw_text(job.document_id)
    assert len(chunks) == 1
    assert raw_text == "Artigo 1.º\nTexto do artigo."
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
