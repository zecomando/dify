from pathlib import Path

from app.corpus import initial_corpus_seeds, seed_initial_corpus
from app.engine import search_retrieval
from app.pipeline import answer_chat
from app.repository import LegalRepository
from app.schemas import ChatAnswerRequest, RetrievalSearchRequest, ValidatorVerdict
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def test_seed_initial_corpus_creates_chat_ready_documents_and_chunks(tmp_path: Path):
    repository = LegalRepository(tmp_path / "seed.sqlite3")

    result = seed_initial_corpus(repository, _source_policy())

    assert result.total_seeds == len(initial_corpus_seeds())
    assert result.created_documents == result.total_seeds
    assert result.already_present_documents == 0
    assert result.rejected_jobs == 0
    assert result.pending_review_documents == 0
    assert result.chat_ready_documents == result.total_seeds
    assert len(result.document_ids) == result.total_seeds
    assert repository.count_documents(status="chat_ready") == result.total_seeds
    assert repository.list_searchable_chunks(current_only=True)


def test_seed_initial_corpus_is_idempotent_by_source_url(tmp_path: Path):
    repository = LegalRepository(tmp_path / "seed.sqlite3")

    first_result = seed_initial_corpus(repository, _source_policy())
    second_result = seed_initial_corpus(repository, _source_policy())

    assert first_result.created_documents == first_result.total_seeds
    assert second_result.created_documents == 0
    assert second_result.already_present_documents == first_result.total_seeds
    assert second_result.document_ids == first_result.document_ids
    assert repository.count_documents() == first_result.total_seeds


def test_seed_initial_corpus_preserves_required_legal_metadata(tmp_path: Path):
    repository = LegalRepository(tmp_path / "seed.sqlite3")

    seed_initial_corpus(repository, _source_policy())

    eurlex = repository.get_document_by_source_url(
        "https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX:32016R0679"
    )
    dgsi = repository.get_document_by_source_url("https://www.dgsi.pt/jstj.nsf/-/demo-123-20.0T8LSB")
    assert eurlex is not None
    assert eurlex.status == "chat_ready"
    assert eurlex.legal_metadata == {"celex": "32016R0679"}
    assert dgsi is not None
    assert dgsi.status == "chat_ready"
    assert dgsi.legal_metadata["court"] == "Supremo Tribunal de Justiça"
    assert dgsi.legal_metadata["process_number"] == "123/20.0T8LSB"


def test_seed_initial_corpus_supports_retrieval_for_demo_questions(tmp_path: Path):
    repository = LegalRepository(tmp_path / "seed.sqlite3")
    seed_initial_corpus(repository, _source_policy())

    civil_response = search_retrieval(
        RetrievalSearchRequest(query="responsabilidade civil nexo causal", jurisdiction=["portugal"]),
        repository,
    )
    rgpd_response = search_retrieval(
        RetrievalSearchRequest(
            query="RGPD bases de licitude dados pessoais",
            jurisdiction=["europa"],
            document_types=["legislation"],
        ),
        repository,
    )

    assert civil_response.results
    assert any(result.source == "DRE" for result in civil_response.results)
    assert any("responsabilidade civil" in result.text.lower() for result in civil_response.results)
    assert rgpd_response.results
    assert rgpd_response.results[0].source == "EURLEX"
    assert rgpd_response.results[0].legal_metadata == {"celex": "32016R0679"}


def test_seed_initial_corpus_allows_chat_answer_with_official_evidence(tmp_path: Path):
    repository = LegalRepository(tmp_path / "seed.sqlite3")
    source_policy = _source_policy()
    seed_initial_corpus(repository, source_policy)

    response = answer_chat(
        ChatAnswerRequest(question="Quais são os pressupostos da responsabilidade civil extracontratual?"),
        source_policy,
        repository,
    )

    assert response.verdict == ValidatorVerdict.PASS
    assert response.evidence
    assert any(evidence.source == "DRE" for evidence in response.evidence)
    assert "responsabilidade civil" in response.answer.lower()
