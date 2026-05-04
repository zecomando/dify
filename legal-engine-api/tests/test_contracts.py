from pathlib import Path

import yaml


OPENAPI_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "api-contracts.openapi.yml"


def _openapi_contract() -> dict[str, object]:
    loaded = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_openapi_contract_includes_initial_corpus_seed_endpoint():
    contract = _openapi_contract()
    paths = contract["paths"]
    components = contract["components"]

    assert "/admin/corpus/seed" in paths
    assert paths["/admin/corpus/seed"]["post"]["security"] == [{"AdminTokenAuth": []}]
    assert (
        paths["/admin/corpus/seed"]["post"]["responses"]["202"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/InitialCorpusSeedResponse"
    )
    assert "InitialCorpusSeedResponse" in components["schemas"]


def test_openapi_contract_includes_admin_ingestion_jobs_endpoints():
    contract = _openapi_contract()
    paths = contract["paths"]
    schemas = contract["components"]["schemas"]

    assert "/admin/ingestion/jobs" in paths
    assert "/admin/ingestion/jobs/{job_id}" in paths
    assert paths["/admin/ingestion/jobs"]["get"]["security"] == [{"AdminTokenAuth": []}]
    assert paths["/admin/ingestion/jobs/{job_id}"]["get"]["security"] == [{"AdminTokenAuth": []}]
    list_schema = paths["/admin/ingestion/jobs"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    detail_schema = paths["/admin/ingestion/jobs/{job_id}"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert list_schema["$ref"] == "#/components/schemas/IngestionJobListResponse"
    assert detail_schema["$ref"] == "#/components/schemas/IngestionJobDetailResponse"
    assert "IngestionJobListResponse" in schemas
    assert "IngestionJobDetailResponse" in schemas


def test_openapi_contract_exposes_legal_metadata_in_core_models():
    schemas = _openapi_contract()["components"]["schemas"]

    assert "legal_metadata" in schemas["RetrievalResult"]["properties"]
    assert "legal_metadata" in schemas["EvidenceItem"]["properties"]
    assert "legal_metadata" in schemas["IngestionSourceRequest"]["properties"]
    assert "legal_metadata" in schemas["LegalDocumentResponse"]["properties"]
    assert "legal_metadata" in schemas["LegalDocumentResponse"]["required"]


def test_openapi_contract_includes_answer_feedback_endpoints():
    contract = _openapi_contract()
    paths = contract["paths"]
    schemas = contract["components"]["schemas"]

    assert "/feedback/answer" in paths
    assert "/admin/feedback" in paths
    assert paths["/admin/feedback"]["get"]["security"] == [{"AdminTokenAuth": []}]
    create_schema = paths["/feedback/answer"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    list_schema = paths["/admin/feedback"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert create_schema["$ref"] == "#/components/schemas/AnswerFeedback"
    assert list_schema["$ref"] == "#/components/schemas/AnswerFeedbackListResponse"
    assert "AnswerFeedbackRequest" in schemas
    assert "AnswerFeedback" in schemas
    assert "AnswerFeedbackListResponse" in schemas
