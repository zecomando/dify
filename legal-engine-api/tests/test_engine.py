from pathlib import Path

from app.engine import build_evidence, classify_query, generate_answer, rerank_results, validate_answer
from app.schemas import (
    AnswerGenerateRequest,
    AnswerValidateRequest,
    ClassifyQueryRequest,
    EvidenceBuildRequest,
    EvidenceItem,
    RerankRequest,
    RetrievalResult,
    ValidatorVerdict,
)
from app.source_policy import SourcePolicy


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def _source_policy() -> SourcePolicy:
    return SourcePolicy.from_file(POLICY_PATH)


def _official_result(chunk_id: str = "chunk-1", score: float = 0.9) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="doc-1",
        source="DRE",
        source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
        text="Artigo de teste com conteúdo jurídico oficial.",
        score=score,
        jurisdiction="portugal",
        document_type="legislation",
        citation_label=f"[{chunk_id}]",
        is_current=True,
        is_consolidated=True,
    )


def test_classify_query_detects_case_law_and_high_risk():
    result = classify_query(ClassifyQueryRequest(query="Há acórdãos sobre prazo de despedimento em Portugal?"))

    assert result.jurisdiction == ["portugal"]
    assert "laboral" in result.area
    assert "case_law" in result.document_types
    assert result.requires_case_law is True
    assert result.high_risk is True


def test_rerank_results_orders_by_score_and_limits_top_n():
    low_score = _official_result(chunk_id="low", score=0.1)
    high_score = _official_result(chunk_id="high", score=0.9)

    result = rerank_results(RerankRequest(query="teste", results=[low_score, high_score], top_n=1))

    assert [item.chunk_id for item in result.results] == ["high"]


def test_build_evidence_keeps_only_official_authorities_and_warns():
    official = _official_result()
    blocked = RetrievalResult(
        chunk_id="blocked",
        document_id="doc-2",
        source="Wikipedia",
        source_url="https://pt.wikipedia.org/wiki/Codigo_Civil",
        text="Texto não oficial.",
        score=0.8,
        citation_label="[blocked]",
    )

    result = build_evidence(EvidenceBuildRequest(query="teste", results=[blocked, official]), _source_policy())

    assert [item.chunk_id for item in result.evidence] == ["chunk-1"]
    assert result.evidence[0].source == "DRE"
    assert result.evidence[0].legal_value_warning
    assert any("Excluded non-authoritative source" in warning for warning in result.warnings)


def test_generate_answer_abstains_without_evidence():
    result = generate_answer(AnswerGenerateRequest(question="teste", evidence=[]))

    assert "não há evidência oficial suficiente" in result.draft_answer.lower()


def test_validate_answer_abstains_without_evidence():
    result = validate_answer(
        AnswerValidateRequest(question="teste", draft_answer="Resposta sem fonte.", evidence=[]),
        _source_policy(),
    )

    assert result.verdict == ValidatorVerdict.ABSTAIN
    assert result.unsupported_claims == ["No official evidence was provided."]


def test_validate_answer_fails_when_evidence_source_is_not_official():
    evidence = EvidenceItem(
        chunk_id="bad-source",
        citation_label="[bad-source]",
        text="Texto não oficial.",
        source_url="https://example.com/legal",
    )

    result = validate_answer(
        AnswerValidateRequest(question="teste", draft_answer="Resposta [bad-source]", evidence=[evidence]),
        _source_policy(),
    )

    assert result.verdict == ValidatorVerdict.FAIL
    assert result.unsupported_claims


def test_validate_answer_abstains_when_citation_is_missing():
    evidence = EvidenceItem(
        chunk_id="chunk-1",
        citation_label="[chunk-1]",
        text="Texto oficial.",
        source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
    )

    result = validate_answer(
        AnswerValidateRequest(question="teste", draft_answer="Resposta sem citar a fonte.", evidence=[evidence]),
        _source_policy(),
    )

    assert result.verdict == ValidatorVerdict.ABSTAIN
    assert result.missing_citations == ["[chunk-1]"]


def test_validate_answer_fails_when_draft_mentions_unretrieved_url():
    evidence = EvidenceItem(
        chunk_id="chunk-1",
        citation_label="[chunk-1]",
        text="Texto oficial.",
        source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
    )

    result = validate_answer(
        AnswerValidateRequest(
            question="teste",
            draft_answer="Resposta [chunk-1] com https://example.com/fonte-inventada",
            evidence=[evidence],
        ),
        _source_policy(),
    )

    assert result.verdict == ValidatorVerdict.FAIL
    assert result.hallucinated_identifiers == ["https://example.com/fonte-inventada"]


def test_validate_answer_fails_when_draft_mentions_unretrieved_article():
    evidence = EvidenceItem(
        chunk_id="chunk-1",
        citation_label="Artigo 1.º",
        text="Artigo 1.º\nTexto oficial.",
        source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
    )

    result = validate_answer(
        AnswerValidateRequest(
            question="teste",
            draft_answer="O Artigo 999.º permite essa conclusão. Artigo 1.º",
            evidence=[evidence],
        ),
        _source_policy(),
    )

    assert result.verdict == ValidatorVerdict.FAIL
    assert result.hallucinated_identifiers == ["Artigo 999.º"]


def test_validate_answer_fails_when_draft_mentions_unretrieved_celex_ecli_or_process():
    evidence = EvidenceItem(
        chunk_id="chunk-1",
        citation_label="[chunk-1]",
        text="O processo C-311/18 é referido no texto oficial com CELEX:32016R0679 e ECLI:EU:C:2020:559.",
        source_url="https://eur-lex.europa.eu/legal-content/PT/TXT/?uri=CELEX:32016R0679",
    )

    result = validate_answer(
        AnswerValidateRequest(
            question="teste",
            draft_answer=(
                "A resposta cita CELEX:32016R0679, ECLI:EU:C:2020:559 e processo C-311/18, "
                "mas também CELEX:99999X9999, ECLI:PT:STA:2099:FAKE e processo 999/99.9FAKE. [chunk-1]"
            ),
            evidence=[evidence],
        ),
        _source_policy(),
    )

    assert result.verdict == ValidatorVerdict.FAIL
    assert result.hallucinated_identifiers == [
        "CELEX:99999X9999",
        "ECLI:PT:STA:2099:FAKE",
        "processo 999/99.9FAKE",
    ]


def test_validate_answer_passes_when_official_evidence_is_cited():
    evidence = EvidenceItem(
        chunk_id="chunk-1",
        citation_label="[chunk-1]",
        text="Texto oficial.",
        source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
    )

    result = validate_answer(
        AnswerValidateRequest(question="teste", draft_answer="Resposta validada [chunk-1]", evidence=[evidence]),
        _source_policy(),
    )

    assert result.verdict == ValidatorVerdict.PASS
    assert result.final_safe_answer == "Resposta validada [chunk-1]"
