from __future__ import annotations

import json
from uuid import uuid4

from app.repository import AnswerAuditRecord, utc_now_iso
from app.schemas import (
    AnswerAuditResponse,
    AnswerGenerateResponse,
    AnswerValidateResponse,
    ChatAnswerRequest,
    ClassifyQueryResponse,
    EvidenceBuildResponse,
    EvidenceItem,
    RetrievalResult,
    RetrievalSearchResponse,
    RerankResponse,
    ValidatorVerdict,
)


def build_answer_audit_record(
    *,
    payload: ChatAnswerRequest,
    classification: ClassifyQueryResponse,
    retrieval: RetrievalSearchResponse,
    reranked: RerankResponse,
    evidence_response: EvidenceBuildResponse,
    draft: AnswerGenerateResponse,
    validation: AnswerValidateResponse,
    latency_ms: int,
) -> AnswerAuditRecord:
    return AnswerAuditRecord(
        id=str(uuid4()),
        session_id=payload.session_id,
        user_id=payload.user_id,
        user_query=payload.question,
        normalized_query=classification.query_rewrite,
        detected_area_json=_json_dump(classification.area),
        detected_jurisdiction_json=_json_dump(classification.jurisdiction),
        detected_document_types_json=_json_dump(classification.document_types),
        mode=payload.mode.value,
        retrieved_chunks_json=_json_dump([result.model_dump(mode="json") for result in retrieval.results]),
        reranked_chunks_json=_json_dump([result.model_dump(mode="json") for result in reranked.results]),
        evidence_json=_json_dump([evidence.model_dump(mode="json") for evidence in evidence_response.evidence]),
        draft_answer=draft.draft_answer,
        validator_report_json=_json_dump(validation.model_dump(mode="json")),
        final_answer=validation.final_safe_answer,
        confidence=_confidence(validation.verdict, len(evidence_response.evidence)),
        abstained=validation.verdict != ValidatorVerdict.PASS,
        verdict=validation.verdict.value,
        model_generator="deterministic-evidence-summarizer",
        model_validator="deterministic-source-validator",
        embedding_model=None,
        reranker_model="deterministic-score-sort",
        latency_ms=latency_ms,
        estimated_cost_usd=0.0,
        created_at=utc_now_iso(),
    )


def answer_audit_to_response(record: AnswerAuditRecord) -> AnswerAuditResponse:
    return AnswerAuditResponse(
        id=record.id,
        session_id=record.session_id,
        user_id=record.user_id,
        user_query=record.user_query,
        normalized_query=record.normalized_query,
        detected_area=_json_load_list(record.detected_area_json),
        detected_jurisdiction=_json_load_list(record.detected_jurisdiction_json),
        detected_document_types=_json_load_list(record.detected_document_types_json),
        mode=record.mode,
        retrieved_chunks=[RetrievalResult(**item) for item in _json_load_list(record.retrieved_chunks_json)],
        reranked_chunks=[RetrievalResult(**item) for item in _json_load_list(record.reranked_chunks_json)],
        evidence=[EvidenceItem(**item) for item in _json_load_list(record.evidence_json)],
        draft_answer=record.draft_answer,
        validator_report=AnswerValidateResponse(**_json_load_dict(record.validator_report_json)),
        final_answer=record.final_answer,
        confidence=record.confidence,
        abstained=record.abstained,
        verdict=record.verdict,
        model_generator=record.model_generator,
        model_validator=record.model_validator,
        embedding_model=record.embedding_model,
        reranker_model=record.reranker_model,
        latency_ms=record.latency_ms,
        estimated_cost_usd=record.estimated_cost_usd,
        created_at=record.created_at,
    )


def _confidence(verdict: ValidatorVerdict, evidence_count: int) -> str:
    if verdict == ValidatorVerdict.PASS and evidence_count >= 2:
        return "high"
    if verdict == ValidatorVerdict.PASS and evidence_count == 1:
        return "medium"
    return "none"


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load_list(value: str) -> list[dict[str, object] | str]:
    loaded = json.loads(value)
    if isinstance(loaded, list):
        return loaded
    return []


def _json_load_dict(value: str) -> dict[str, object]:
    loaded = json.loads(value)
    if isinstance(loaded, dict):
        return loaded
    return {}
