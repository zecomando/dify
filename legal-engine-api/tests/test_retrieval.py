from pathlib import Path

from app.engine import search_retrieval
from app.ingestion import ingest_source, reindex_corpus
from app.repository import LegalRepository
from app.schemas import IngestionSourceRequest, ReindexRequest, RetrievalSearchRequest
from app.source_policy import SourcePolicy
from app.vector_index import LOCAL_EMBEDDING_MODEL


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def _repository(tmp_path: Path) -> LegalRepository:
    return LegalRepository(tmp_path / "legal-engine.sqlite3")


def test_search_retrieval_returns_matching_chat_ready_chunks(tmp_path: Path):
    repository = _repository(tmp_path)
    ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text=(
                "Artigo 1.º\nO contrato de trabalho tem regime próprio.\n\n"
                "Artigo 2.º\nA responsabilidade civil depende dos pressupostos legais."
            ),
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )

    response = search_retrieval(
        RetrievalSearchRequest(query="responsabilidade civil", top_k_dense=1, top_k_sparse=1),
        repository,
    )

    assert len(response.results) == 1
    assert response.results[0].source == "DRE"
    assert response.results[0].citation_label == "Artigo 2.º"
    assert "responsabilidade civil" in response.results[0].text.lower()
    assert response.results[0].score > 0


def test_search_retrieval_ignores_pending_review_documents(tmp_path: Path):
    repository = _repository(tmp_path)
    ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nA responsabilidade civil está prevista na lei.",
        ),
        _source_policy(),
        repository,
    )

    response = search_retrieval(RetrievalSearchRequest(query="responsabilidade civil"), repository)

    assert response.results == []


def test_search_retrieval_filters_by_jurisdiction_and_document_type(tmp_path: Path):
    repository = _repository(tmp_path)
    ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nA responsabilidade civil está prevista na lei.",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )

    mismatched_jurisdiction = search_retrieval(
        RetrievalSearchRequest(query="responsabilidade civil", jurisdiction=["europa"]),
        repository,
    )
    mismatched_document_type = search_retrieval(
        RetrievalSearchRequest(query="responsabilidade civil", document_types=["case_law"]),
        repository,
    )

    assert mismatched_jurisdiction.results == []
    assert mismatched_document_type.results == []


def test_ingest_source_persists_local_chunk_embeddings(tmp_path: Path):
    repository = _repository(tmp_path)
    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text=(
                "Artigo 1.º\nA responsabilidade civil está prevista na lei.\n\n"
                "Artigo 2.º\nO contrato de trabalho tem regime próprio."
            ),
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None

    chunks = repository.list_chunks_by_document(job.document_id)
    assert len(chunks) == 2
    assert repository.count_chunk_embeddings(model=LOCAL_EMBEDDING_MODEL) == 2
    assert repository.get_chunk_embedding(chunks[0].id, model=LOCAL_EMBEDDING_MODEL) is not None


def test_search_retrieval_uses_dense_embedding_when_lexical_terms_do_not_match(tmp_path: Path):
    repository = _repository(tmp_path)
    ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nA responsabilidade civil depende dos pressupostos legais.",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )

    response = search_retrieval(
        RetrievalSearchRequest(query="indemnização", top_k_dense=1, top_k_sparse=1),
        repository,
    )

    assert len(response.results) == 1
    assert response.results[0].citation_label == "Artigo 1.º"
    assert "responsabilidade civil" in response.results[0].text.lower()
    assert response.results[0].score > 0


def test_reindex_corpus_refreshes_local_chunk_embeddings(tmp_path: Path):
    repository = _repository(tmp_path)
    response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nA responsabilidade civil está prevista na lei.",
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )
    job = repository.get_job(response.job_id)
    assert job is not None
    assert job.document_id is not None
    repository.save_document_raw_text(
        job.document_id,
        "Artigo 1.º\nO contrato de trabalho tem regime próprio.",
        "2026-01-01T00:00:00+00:00",
    )

    reindex_response = reindex_corpus(ReindexRequest(document_ids=[job.document_id], force=True), repository)

    chunks = repository.list_chunks_by_document(job.document_id)
    assert reindex_response.status == "completed"
    assert len(chunks) == 1
    assert repository.count_chunk_embeddings(model=LOCAL_EMBEDDING_MODEL) == 1
    assert repository.get_chunk_embedding(chunks[0].id, model=LOCAL_EMBEDDING_MODEL) is not None
    refreshed_search = search_retrieval(RetrievalSearchRequest(query="trabalho"), repository)
    stale_search = search_retrieval(RetrievalSearchRequest(query="responsabilidade civil"), repository)
    assert refreshed_search.results
    assert stale_search.results == []
