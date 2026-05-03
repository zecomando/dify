from __future__ import annotations

from time import perf_counter

from app.audit import build_answer_audit_record
from app.engine import (
    build_evidence,
    classify_query,
    generate_answer,
    rerank_results,
    search_retrieval,
    validate_answer,
)
from app.repository import LegalRepository
from app.schemas import (
    AnswerGenerateRequest,
    AnswerValidateRequest,
    ChatAnswerRequest,
    ChatAnswerResponse,
    ClassifyQueryRequest,
    EvidenceBuildRequest,
    PipelineStepTrace,
    RerankRequest,
    RetrievalSearchRequest,
)
from app.source_policy import SourcePolicy


def answer_chat(
    payload: ChatAnswerRequest,
    source_policy: SourcePolicy,
    repository: LegalRepository,
) -> ChatAnswerResponse:
    started_at = perf_counter()
    trace: list[PipelineStepTrace] = []

    classification = classify_query(ClassifyQueryRequest(query=payload.question, mode=payload.mode))
    trace.append(
        PipelineStepTrace(
            step="classify",
            status="completed",
            detail=f"jurisdiction={classification.jurisdiction}; document_types={classification.document_types}",
        )
    )

    search_request = RetrievalSearchRequest(
        query=classification.query_rewrite,
        jurisdiction=payload.jurisdiction or classification.jurisdiction,
        area=classification.area,
        document_types=payload.document_types or classification.document_types,
        current_only=classification.current_only if payload.current_only is None else payload.current_only,
        top_k_dense=payload.top_k_dense,
        top_k_sparse=payload.top_k_sparse,
        mode=payload.mode,
    )
    retrieval = search_retrieval(search_request, repository)
    trace.append(
        PipelineStepTrace(
            step="retrieval",
            status="completed",
            detail=f"retrieved={len(retrieval.results)}",
        )
    )

    reranked = rerank_results(
        RerankRequest(query=classification.query_rewrite, results=retrieval.results, top_n=payload.top_n)
    )
    trace.append(
        PipelineStepTrace(
            step="rerank",
            status="completed",
            detail=f"reranked={len(reranked.results)}",
        )
    )

    evidence_response = build_evidence(
        EvidenceBuildRequest(query=classification.query_rewrite, results=reranked.results),
        source_policy,
    )
    trace.append(
        PipelineStepTrace(
            step="evidence",
            status="completed",
            detail=f"evidence={len(evidence_response.evidence)}; warnings={len(evidence_response.warnings)}",
        )
    )

    draft = generate_answer(
        AnswerGenerateRequest(question=payload.question, evidence=evidence_response.evidence, mode=payload.mode)
    )
    trace.append(
        PipelineStepTrace(
            step="generate",
            status="completed",
            detail="draft_created",
        )
    )

    validation = validate_answer(
        AnswerValidateRequest(
            question=payload.question,
            draft_answer=draft.draft_answer,
            evidence=evidence_response.evidence,
        ),
        source_policy,
    )
    trace.append(
        PipelineStepTrace(
            step="validate",
            status=validation.verdict.value,
            detail=f"unsupported={len(validation.unsupported_claims)}; missing_citations={len(validation.missing_citations)}",
        )
    )

    latency_ms = int((perf_counter() - started_at) * 1000)
    audit = repository.create_answer_audit(
        build_answer_audit_record(
            payload=payload,
            classification=classification,
            retrieval=retrieval,
            reranked=reranked,
            evidence_response=evidence_response,
            draft=draft,
            validation=validation,
            latency_ms=latency_ms,
        )
    )

    return ChatAnswerResponse(
        audit_id=audit.id,
        answer=validation.final_safe_answer,
        verdict=validation.verdict,
        classification=classification,
        evidence=evidence_response.evidence,
        warnings=evidence_response.warnings,
        retrieved_results=retrieval.results,
        reranked_results=reranked.results,
        unsupported_claims=validation.unsupported_claims,
        missing_citations=validation.missing_citations,
        wrong_version_risk=validation.wrong_version_risk,
        hallucinated_identifiers=validation.hallucinated_identifiers,
        pipeline_trace=trace,
    )
