from pathlib import Path

from app.audit import answer_audit_to_response
from app.ingestion import ingest_source
from app.pipeline import answer_chat
from app.repository import LegalChunkRecord, LegalDocumentRecord, LegalRepository, utc_now_iso
from app.schemas import ChatAnswerRequest, IngestionSourceRequest, ValidatorVerdict
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def _repository(tmp_path: Path) -> LegalRepository:
    return LegalRepository(tmp_path / "legal-engine.sqlite3")


def test_answer_chat_passes_with_official_chat_ready_evidence(tmp_path: Path):
    repository = _repository(tmp_path)
    ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text=(
                "Artigo 1.º\nA responsabilidade civil depende da verificação dos pressupostos legais.\n\n"
                "Artigo 2.º\nO contrato deve ser cumprido pontualmente."
            ),
            promote_if_valid=True,
        ),
        _source_policy(),
        repository,
    )

    response = answer_chat(
        ChatAnswerRequest(question="responsabilidade civil", top_n=2),
        _source_policy(),
        repository,
    )

    assert response.verdict == ValidatorVerdict.PASS
    assert response.audit_id is not None
    assert response.evidence
    assert response.evidence[0].citation_label == "Artigo 1.º"
    assert "Artigo 1.º" in response.answer
    assert "responsabilidade civil" in response.answer.lower()
    assert [step.step for step in response.pipeline_trace] == [
        "classify",
        "retrieval",
        "rerank",
        "evidence",
        "generate",
        "validate",
    ]

    audit = repository.get_answer_audit(response.audit_id)
    assert audit is not None
    assert audit.user_query == "responsabilidade civil"
    assert audit.verdict == "pass"
    audit_response = answer_audit_to_response(audit)
    assert audit_response.final_answer == response.answer
    assert audit_response.evidence[0].citation_label == "Artigo 1.º"


def test_answer_chat_abstains_when_no_official_evidence_exists(tmp_path: Path):
    repository = _repository(tmp_path)

    response = answer_chat(
        ChatAnswerRequest(question="responsabilidade civil"),
        _source_policy(),
        repository,
    )

    assert response.verdict == ValidatorVerdict.ABSTAIN
    assert response.audit_id is not None
    assert response.evidence == []
    assert response.retrieved_results == []
    assert "não há evidência oficial suficiente" in response.answer.lower()
    assert response.unsupported_claims == ["No official evidence was provided."]


def test_answer_chat_abstains_when_retrieved_chunk_is_not_authoritative(tmp_path: Path):
    repository = _repository(tmp_path)
    now = utc_now_iso()
    document = LegalDocumentRecord(
        id="unsafe-doc",
        source="Unknown",
        jurisdiction="portugal",
        document_type="legislation",
        title="Unsafe source",
        source_url="https://example.com/legal",
        status="chat_ready",
        sha256="0" * 64,
        is_current=True,
        is_consolidated=False,
        legal_value_warning="",
        area=("civil",),
        legal_metadata={},
        created_at=now,
        updated_at=now,
    )
    repository.create_document(document)
    repository.create_chunk(
        LegalChunkRecord(
            id="unsafe-chunk",
            document_id=document.id,
            chunk_type="article",
            structural_path="Artigo 1.º",
            citation_label="Artigo 1.º",
            text_content="A responsabilidade civil aparece neste texto não oficial.",
            token_count=8,
            created_at=now,
        )
    )

    response = answer_chat(
        ChatAnswerRequest(question="responsabilidade civil"),
        _source_policy(),
        repository,
    )

    assert response.verdict == ValidatorVerdict.ABSTAIN
    assert response.audit_id is not None
    assert len(response.retrieved_results) == 1
    assert response.evidence == []
    assert any("Excluded non-authoritative source" in warning for warning in response.warnings)
