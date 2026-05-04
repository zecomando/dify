from __future__ import annotations

import re

from app.repository import LegalRepository, SearchableChunkRecord
from app.schemas import (
    AnswerGenerateRequest,
    AnswerGenerateResponse,
    AnswerValidateRequest,
    AnswerValidateResponse,
    ClassifyQueryRequest,
    ClassifyQueryResponse,
    EvidenceBuildRequest,
    EvidenceBuildResponse,
    EvidenceItem,
    RerankRequest,
    RerankResponse,
    RetrievalResult,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    ValidatorVerdict,
)
from app.source_policy import SourcePolicy, SourcePolicyStatus, validate_source_requirements
from app.vector_index import LocalHashEmbeddingProvider, cosine_similarity

ABSTENTION_MESSAGE = (
    "Não consigo responder com segurança porque não há evidência oficial suficiente validada pela política de fontes."
)
UNSUPPORTED_SOURCE_MESSAGE = "A resposta foi bloqueada porque contém evidência de fonte não autorizada."


def classify_query(payload: ClassifyQueryRequest) -> ClassifyQueryResponse:
    query = payload.query.strip()
    normalized = query.lower()
    jurisdictions = _detect_jurisdictions(normalized)
    areas = _detect_areas(normalized)
    document_types = _detect_document_types(normalized)
    return ClassifyQueryResponse(
        jurisdiction=jurisdictions,
        area=areas,
        document_types=document_types,
        current_only=not _contains_historical_marker(normalized),
        requires_case_law="case_law" in document_types,
        requires_procurement_data="public_contract" in document_types or "procurement_notice" in document_types,
        high_risk=_is_high_risk(normalized),
        query_rewrite=query,
    )


def search_retrieval(
    payload: RetrievalSearchRequest,
    repository: LegalRepository | None = None,
) -> RetrievalSearchResponse:
    if repository is None:
        return RetrievalSearchResponse(results=[])

    query_terms = _terms(payload.query)
    if not query_terms:
        return RetrievalSearchResponse(results=[])

    embedding_provider = LocalHashEmbeddingProvider()
    query_embedding = embedding_provider.embed(payload.query)
    scored_results: list[tuple[float, SearchableChunkRecord]] = []
    for chunk in repository.list_searchable_chunks(current_only=payload.current_only):
        if payload.jurisdiction and chunk.jurisdiction not in payload.jurisdiction:
            continue
        if payload.document_types and chunk.document_type not in payload.document_types:
            continue
        if payload.area and chunk.area and not set(payload.area).intersection(chunk.area):
            continue
        if payload.as_of_date is not None and not _is_version_valid_at(
            valid_from=chunk.valid_from,
            valid_until=chunk.valid_until,
            as_of_date=payload.as_of_date,
        ):
            continue

        sparse_score = _lexical_score(payload.query, query_terms, chunk)
        chunk_embedding = repository.get_chunk_embedding(chunk.chunk_id, model=embedding_provider.model_name)
        dense_score = cosine_similarity(query_embedding, chunk_embedding.vector) if chunk_embedding is not None else 0.0
        score = _hybrid_score(dense_score=dense_score, sparse_score=sparse_score)
        if score > 0:
            scored_results.append((score, chunk))

    scored_results.sort(key=lambda item: item[0], reverse=True)
    limit = max(payload.top_k_dense, payload.top_k_sparse)
    return RetrievalSearchResponse(
        results=[
            RetrievalResult(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                source=chunk.source,
                source_url=chunk.source_url,
                text=chunk.text_content,
                score=round(score, 6),
                jurisdiction=chunk.jurisdiction,
                document_type=chunk.document_type,
                area=list(chunk.area),
                legal_metadata=chunk.legal_metadata,
                citation_label=chunk.citation_label or chunk.chunk_id,
                is_current=chunk.is_current,
                is_consolidated=chunk.is_consolidated,
                version_label=chunk.version_label,
                valid_from=chunk.valid_from,
                valid_until=chunk.valid_until,
            )
            for score, chunk in scored_results[:limit]
        ]
    )


def rerank_results(payload: RerankRequest) -> RerankResponse:
    ordered = sorted(payload.results, key=lambda result: result.score, reverse=True)
    return RerankResponse(results=ordered[: payload.top_n])


def build_evidence(payload: EvidenceBuildRequest, source_policy: SourcePolicy) -> EvidenceBuildResponse:
    evidence: list[EvidenceItem] = []
    warnings: list[str] = []
    seen_chunk_ids: set[str] = set()

    for result in sorted(payload.results, key=lambda item: item.score, reverse=True):
        if result.chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(result.chunk_id)

        policy_result = source_policy.check_url(result.source_url)
        if policy_result.status != SourcePolicyStatus.OFFICIAL_AUTHORITY or not policy_result.may_ground_answer:
            warnings.append(f"Excluded non-authoritative source for chunk {result.chunk_id}: {policy_result.reason}")
            continue
        if policy_result.authority is not None:
            source_requirement_violations = validate_source_requirements(
                policy_result.authority,
                document_type=result.document_type,
                source_url=result.source_url,
                raw_text=result.text,
                legal_metadata=result.legal_metadata,
            )
            if source_requirement_violations:
                warnings.extend(
                    f"Excluded source for chunk {result.chunk_id}: {violation}"
                    for violation in source_requirement_violations
                )
                continue

        warning = _legal_value_warning(
            result, policy_result.authority.source if policy_result.authority else result.source
        )
        evidence.append(
            EvidenceItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                citation_label=result.citation_label or result.chunk_id,
                text=result.text,
                source_url=result.source_url,
                canonical_url=result.source_url,
                source=policy_result.authority.source if policy_result.authority else result.source,
                jurisdiction=result.jurisdiction,
                document_type=result.document_type,
                legal_metadata=result.legal_metadata,
                is_current=result.is_current,
                is_consolidated=result.is_consolidated,
                legal_value_warning=warning,
                version_label=result.version_label,
                valid_from=result.valid_from,
                valid_until=result.valid_until,
            )
        )
        if warning:
            warnings.append(warning)
        if not result.is_current:
            warnings.append(f"Evidence chunk {result.chunk_id} is not marked as current.")

    return EvidenceBuildResponse(evidence=evidence, warnings=warnings)


def generate_answer(payload: AnswerGenerateRequest) -> AnswerGenerateResponse:
    if not payload.evidence:
        return AnswerGenerateResponse(draft_answer=ABSTENTION_MESSAGE)

    evidence_summaries = [
        f"{evidence.citation_label}: {_truncate_evidence_text(evidence.text)}" for evidence in payload.evidence
    ]
    warnings = [evidence.legal_value_warning for evidence in payload.evidence if evidence.legal_value_warning]
    return AnswerGenerateResponse(
        draft_answer=(
            "Resposta baseada apenas na evidência oficial recuperada. "
            f"Síntese: {' '.join(evidence_summaries)} "
            "Esta resposta não substitui aconselhamento jurídico individualizado."
            + (f" Avisos: {' '.join(dict.fromkeys(warnings))}" if warnings else "")
        )
    )


def validate_answer(payload: AnswerValidateRequest, source_policy: SourcePolicy) -> AnswerValidateResponse:
    if not payload.evidence:
        return AnswerValidateResponse(
            verdict=ValidatorVerdict.ABSTAIN,
            final_safe_answer=ABSTENTION_MESSAGE,
            unsupported_claims=["No official evidence was provided."],
        )

    invalid_evidence_reasons = _find_invalid_evidence(payload.evidence, source_policy)
    if invalid_evidence_reasons:
        return AnswerValidateResponse(
            verdict=ValidatorVerdict.FAIL,
            final_safe_answer=UNSUPPORTED_SOURCE_MESSAGE,
            unsupported_claims=invalid_evidence_reasons,
        )

    wrong_version_risk = any(not evidence.is_current for evidence in payload.evidence)
    if wrong_version_risk:
        return AnswerValidateResponse(
            verdict=ValidatorVerdict.ABSTAIN,
            final_safe_answer=(
                "Não devo fornecer uma conclusão jurídica porque a evidência disponível inclui versões não atuais."
            ),
            unsupported_claims=["At least one evidence item is not marked as current."],
            wrong_version_risk=True,
        )

    missing_citations = _find_missing_citations(payload.draft_answer, payload.evidence)
    hallucinated_urls = _find_unretrieved_urls(payload.draft_answer, payload.evidence)
    hallucinated_legal_identifiers = _find_unretrieved_legal_identifiers(payload.draft_answer, payload.evidence)
    hallucinated_identifiers = hallucinated_urls + hallucinated_legal_identifiers
    if hallucinated_identifiers:
        return AnswerValidateResponse(
            verdict=ValidatorVerdict.FAIL,
            final_safe_answer="A resposta foi bloqueada porque menciona identificadores jurídicos que não foram recuperados como evidência.",
            hallucinated_identifiers=hallucinated_identifiers,
            missing_citations=missing_citations,
        )

    if missing_citations:
        return AnswerValidateResponse(
            verdict=ValidatorVerdict.ABSTAIN,
            final_safe_answer="Não devo apresentar a resposta porque faltam citações para a evidência oficial disponível.",
            missing_citations=missing_citations,
        )

    return AnswerValidateResponse(verdict=ValidatorVerdict.PASS, final_safe_answer=payload.draft_answer)


def _detect_jurisdictions(normalized_query: str) -> list[str]:
    jurisdictions: list[str] = []
    if any(marker in normalized_query for marker in ("portugal", "portugu", "dre", "código", "codigo")):
        jurisdictions.append("portugal")
    if any(
        marker in normalized_query
        for marker in (
            "união europeia",
            "uniao europeia",
            "ue",
            "eur-lex",
            "tjue",
            "cedh",
            "tedh",
            "direitos humanos",
            "europeu dos direitos humanos",
        )
    ):
        jurisdictions.append("europa")
    return jurisdictions or ["portugal"]


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"\w+", text.lower()) if len(term) > 2}


def _lexical_score(query: str, query_terms: set[str], chunk: SearchableChunkRecord) -> float:
    text = chunk.text_content.lower()
    chunk_terms = _terms(text)
    if not chunk_terms:
        return 0

    matched_terms = query_terms.intersection(chunk_terms)
    term_score = len(matched_terms) / len(query_terms)
    phrase_bonus = 0.25 if query.lower().strip() in text else 0
    citation_bonus = (
        0.05 if chunk.citation_label and any(term in chunk.citation_label.lower() for term in query_terms) else 0
    )
    return term_score + phrase_bonus + citation_bonus


def _hybrid_score(*, dense_score: float, sparse_score: float) -> float:
    if dense_score == 0 and sparse_score == 0:
        return 0.0
    return (0.6 * dense_score) + (0.4 * sparse_score)


def _truncate_evidence_text(text: str, max_length: int = 260) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1].rstrip()}…"


def _detect_areas(normalized_query: str) -> list[str]:
    area_markers = {
        "civil": ("civil", "contrato", "responsabilidade"),
        "laboral": ("trabalho", "laboral", "trabalhador", "despedimento"),
        "administrativo": ("administrativo", "procedimento administrativo", "audiência prévia", "audiencia previa"),
        "contratacao_publica": (
            "contratação pública",
            "contratacao publica",
            "base.gov",
            "concurso público",
            "proposta",
            "preço anormalmente baixo",
            "preco anormalmente baixo",
        ),
        "proteccao_dados": ("rgpd", "dados pessoais", "proteção de dados", "protecao de dados"),
        "fiscal": ("iva", "irc", "irs", "fiscal", "tribut"),
        "constitucional": ("constitucional", "constituição", "constituicao"),
        "uniao_europeia": ("união europeia", "uniao europeia", "primado", "direito da união", "direito da uniao"),
        "cedh": ("cedh", "tedh", "processo equitativo", "direitos humanos"),
    }
    areas = [area for area, markers in area_markers.items() if any(marker in normalized_query for marker in markers)]
    return areas or ["geral"]


def _detect_document_types(normalized_query: str) -> list[str]:
    document_types: list[str] = ["legislation"]
    if any(marker in normalized_query for marker in ("acórdão", "acordao", "jurisprud", "tribunal", "processo")):
        document_types.append("case_law")
    if any(
        marker in normalized_query
        for marker in ("contratação pública", "contratacao publica", "concurso", "adjudicação")
    ):
        document_types.extend(["procurement_notice", "public_contract"])
    return list(dict.fromkeys(document_types))


def _contains_historical_marker(normalized_query: str) -> bool:
    return any(marker in normalized_query for marker in ("em 2019", "em 2020", "à data", "a data", "histórico"))


def _is_version_valid_at(*, valid_from: str | None, valid_until: str | None, as_of_date: str) -> bool:
    if valid_from is not None and valid_from > as_of_date:
        return False
    if valid_until is not None and valid_until <= as_of_date:
        return False
    return True


def _is_high_risk(normalized_query: str) -> bool:
    return any(marker in normalized_query for marker in ("prazo", "coima", "sanção", "sancao", "crime", "despedimento"))


def _legal_value_warning(result: RetrievalResult, source: str) -> str:
    if not result.is_consolidated:
        return ""
    if source in {"DRE"}:
        return "Texto consolidado do DRE: instrumento documental/de consulta sem valor legal autónomo."
    if source in {"EURLEX"}:
        return "Texto consolidado do EUR-Lex: instrumento documental sem valor jurídico autónomo."
    return "Texto consolidado: confirmar atos originais antes de conclusão jurídica final."


def _find_invalid_evidence(evidence_items: list[EvidenceItem], source_policy: SourcePolicy) -> list[str]:
    reasons: list[str] = []
    for evidence in evidence_items:
        policy_result = source_policy.check_url(evidence.source_url)
        if policy_result.status != SourcePolicyStatus.OFFICIAL_AUTHORITY or not policy_result.may_ground_answer:
            reasons.append(f"Evidence {evidence.chunk_id} is not an official authority: {policy_result.reason}")
            continue
        if policy_result.authority is not None:
            reasons.extend(
                f"Evidence {evidence.chunk_id} violates source policy: {violation}"
                for violation in validate_source_requirements(
                    policy_result.authority,
                    document_type=evidence.document_type,
                    source_url=evidence.source_url,
                    raw_text=evidence.text,
                    legal_metadata=evidence.legal_metadata,
                )
            )
    return reasons


def _find_missing_citations(draft_answer: str, evidence_items: list[EvidenceItem]) -> list[str]:
    if not draft_answer.strip():
        return [evidence.citation_label for evidence in evidence_items]
    return [evidence.citation_label for evidence in evidence_items if evidence.citation_label not in draft_answer]


def _find_unretrieved_urls(draft_answer: str, evidence_items: list[EvidenceItem]) -> list[str]:
    evidence_urls = {evidence.source_url for evidence in evidence_items}
    mentioned_urls = set(re.findall(r"https?://[^\s)\]]+", draft_answer))
    return sorted(mentioned_urls - evidence_urls)


def _find_unretrieved_legal_identifiers(draft_answer: str, evidence_items: list[EvidenceItem]) -> list[str]:
    evidence_text = "\n".join(_evidence_identifier_text(evidence) for evidence in evidence_items)
    evidence_identifiers = set(_legal_identifiers(evidence_text))
    hallucinated_identifiers: list[str] = []
    for identifier in _legal_identifiers(draft_answer):
        if identifier not in evidence_identifiers:
            hallucinated_identifiers.append(identifier)
    return list(dict.fromkeys(hallucinated_identifiers))


def _evidence_identifier_text(evidence: EvidenceItem) -> str:
    values = [
        evidence.citation_label,
        evidence.text,
        evidence.source_url,
        evidence.canonical_url or "",
    ]
    return "\n".join(values)


def _legal_identifiers(text: str) -> list[str]:
    return [
        *_article_identifiers(text),
        *_celex_identifiers(text),
        *_ecli_identifiers(text),
        *_process_identifiers(text),
    ]


def _article_identifiers(text: str) -> list[str]:
    return re.findall(r"\b[Aa]rtigo\s+\d+(?:\.\s*[ºª])?", text)


def _celex_identifiers(text: str) -> list[str]:
    return re.findall(r"\bCELEX:[0-9A-Z]{5,}\b", text)


def _ecli_identifiers(text: str) -> list[str]:
    return re.findall(r"\bECLI:[A-Z]{2}:[A-Z0-9]+:\d{4}:[A-Z0-9._-]+\b", text)


def _process_identifiers(text: str) -> list[str]:
    return re.findall(r"\b[Pp]rocesso\s+(?:[A-Z]-)?\d+[-/]\d+(?:\.\d+[A-Z0-9]+)?\b", text)
