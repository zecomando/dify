from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import get_repository
from app.ingestion import ingest_source
from app.main import app
from app.repository import LegalRepository
from app.schemas import IngestionSourceRequest
from app.source_policy import SourcePolicy, SourcePolicyStatus


client = TestClient(app)
POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"


def test_health_endpoint_returns_policy_metadata():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "source_policy_name": "legal_ai_source_policy",
        "source_policy_version": 1,
    }


def test_check_url_endpoint_returns_official_authority():
    response = client.post(
        "/source-policy/check-url",
        json={"url": "https://dre.pt/dre/legislacao-consolidada"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == SourcePolicyStatus.OFFICIAL_AUTHORITY
    assert payload["may_ground_answer"] is True
    assert payload["authority"]["source"] == "DRE"


def test_check_url_endpoint_rejects_extra_fields():
    response = client.post(
        "/source-policy/check-url",
        json={"url": "https://dre.pt", "unexpected": True},
    )

    assert response.status_code == 422


def test_classify_endpoint_returns_minimum_legal_metadata():
    response = client.post(
        "/query/classify",
        json={"query": "Qual é o prazo de despedimento em Portugal?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jurisdiction"] == ["portugal"]
    assert "laboral" in payload["area"]
    assert payload["current_only"] is True
    assert payload["high_risk"] is True


def test_retrieval_search_endpoint_returns_empty_results_until_index_exists(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.post(
            "/retrieval/search",
            json={"query": "Código Civil"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_retrieval_search_endpoint_returns_persisted_chunks(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nA responsabilidade civil depende dos pressupostos legais.",
            promote_if_valid=True,
        ),
        SourcePolicy.from_file(POLICY_PATH),
        repository,
    )
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.post(
            "/retrieval/search",
            json={"query": "responsabilidade civil"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 1
    assert payload["results"][0]["citation_label"] == "Artigo 1.º"


def test_rerank_endpoint_orders_results_by_score():
    response = client.post(
        "/retrieval/rerank",
        json={
            "query": "teste",
            "top_n": 1,
            "results": [
                {
                    "chunk_id": "low",
                    "document_id": "doc",
                    "source": "DRE",
                    "source_url": "https://dre.pt/dre/legislacao-consolidada",
                    "text": "baixo",
                    "score": 0.1,
                },
                {
                    "chunk_id": "high",
                    "document_id": "doc",
                    "source": "DRE",
                    "source_url": "https://dre.pt/dre/legislacao-consolidada",
                    "text": "alto",
                    "score": 0.9,
                },
            ],
        },
    )

    assert response.status_code == 200
    assert [item["chunk_id"] for item in response.json()["results"]] == ["high"]


def test_evidence_build_endpoint_excludes_non_official_sources():
    response = client.post(
        "/evidence/build",
        json={
            "query": "teste",
            "results": [
                {
                    "chunk_id": "official",
                    "document_id": "doc-1",
                    "source": "DRE",
                    "source_url": "https://dre.pt/dre/legislacao-consolidada",
                    "text": "texto oficial",
                    "score": 0.9,
                    "citation_label": "[official]",
                },
                {
                    "chunk_id": "blocked",
                    "document_id": "doc-2",
                    "source": "Wikipedia",
                    "source_url": "https://pt.wikipedia.org/wiki/Direito",
                    "text": "texto bloqueado",
                    "score": 0.8,
                    "citation_label": "[blocked]",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["chunk_id"] for item in payload["evidence"]] == ["official"]
    assert payload["warnings"]


def test_answer_generate_endpoint_abstains_without_evidence():
    response = client.post(
        "/answer/generate",
        json={"question": "teste", "evidence": []},
    )

    assert response.status_code == 200
    assert "evidência oficial suficiente" in response.json()["draft_answer"]


def test_answer_validate_endpoint_abstains_without_evidence():
    response = client.post(
        "/answer/validate",
        json={"question": "teste", "draft_answer": "sem fontes", "evidence": []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "abstain"
    assert payload["unsupported_claims"]


def test_answer_validate_endpoint_passes_with_cited_official_evidence():
    response = client.post(
        "/answer/validate",
        json={
            "question": "teste",
            "draft_answer": "Resposta validada [official]",
            "evidence": [
                {
                    "chunk_id": "official",
                    "citation_label": "[official]",
                    "text": "texto oficial",
                    "source_url": "https://dre.pt/dre/legislacao-consolidada",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] == "pass"


def test_chat_answer_endpoint_returns_validated_answer_from_persisted_chunks(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nA responsabilidade civil depende dos pressupostos legais.",
            promote_if_valid=True,
        ),
        SourcePolicy.from_file(POLICY_PATH),
        repository,
    )
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.post(
            "/chat/answer",
            json={"question": "responsabilidade civil", "session_id": "session-1", "user_id": "user-1"},
        )
        assert response.status_code == 200
        payload = response.json()
        audit_response = client.get(f"/admin/audit/{payload['audit_id']}")
    finally:
        app.dependency_overrides.clear()

    assert payload["verdict"] == "pass"
    assert payload["audit_id"]
    assert payload["evidence"][0]["citation_label"] == "Artigo 1.º"
    assert "Artigo 1.º" in payload["answer"]
    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert audit_payload["id"] == payload["audit_id"]
    assert audit_payload["session_id"] == "session-1"
    assert audit_payload["user_id"] == "user-1"
    assert audit_payload["verdict"] == "pass"
    assert audit_payload["evidence"][0]["citation_label"] == "Artigo 1.º"


def test_admin_document_endpoints_list_get_chunks_and_update_status(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    ingestion_response = ingest_source(
        IngestionSourceRequest(
            source_url="https://dre.pt/dre/legislacao-consolidada/codigo-civil",
            raw_text="Artigo 1.º\nA responsabilidade civil depende dos pressupostos legais.",
        ),
        SourcePolicy.from_file(POLICY_PATH),
        repository,
    )
    job = repository.get_job(ingestion_response.job_id)
    assert job is not None
    assert job.document_id is not None
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        list_response = client.get("/admin/documents")
        filtered_response = client.get("/admin/documents", params={"status": "pending_review"})
        get_response = client.get(f"/admin/documents/{job.document_id}")
        chunks_response = client.get(f"/admin/documents/{job.document_id}/chunks")
        status_response = client.post(
            f"/admin/documents/{job.document_id}/status",
            json={"target_status": "rejected"},
        )
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["documents"][0]["id"] == job.document_id
    assert filtered_response.status_code == 200
    assert filtered_response.json()["total"] == 1
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "pending_review"
    assert chunks_response.status_code == 200
    assert chunks_response.json()["total"] == 1
    assert chunks_response.json()["chunks"][0]["citation_label"] == "Artigo 1.º"
    assert status_response.status_code == 200
    assert status_response.json()["document"]["status"] == "rejected"


def test_admin_document_endpoints_return_404_for_missing_document(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        get_response = client.get("/admin/documents/missing-document")
        chunks_response = client.get("/admin/documents/missing-document/chunks")
        status_response = client.post(
            "/admin/documents/missing-document/status",
            json={"target_status": "archived"},
        )
    finally:
        app.dependency_overrides.clear()

    assert get_response.status_code == 404
    assert chunks_response.status_code == 404
    assert status_response.status_code == 404


def test_chat_answer_endpoint_abstains_without_evidence(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.post(
            "/chat/answer",
            json={"question": "responsabilidade civil"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "abstain"
    assert payload["audit_id"]
    assert payload["evidence"] == []


def test_admin_audits_endpoint_lists_and_filters_answer_audits(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        answer_response = client.post(
            "/chat/answer",
            json={"question": "responsabilidade civil", "session_id": "session-2", "user_id": "user-2"},
        )
        assert answer_response.status_code == 200
        list_response = client.get("/admin/audits")
        filtered_response = client.get("/admin/audits", params={"verdict": "abstain", "session_id": "session-2"})
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["audits"][0]["id"] == answer_response.json()["audit_id"]
    assert list_response.json()["audits"][0]["verdict"] == "abstain"
    assert filtered_response.status_code == 200
    assert filtered_response.json()["total"] == 1
    assert filtered_response.json()["audits"][0]["session_id"] == "session-2"


def test_admin_audit_endpoint_returns_404_for_missing_audit(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.get("/admin/audit/missing-audit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_admin_evaluation_run_endpoint_persists_and_returns_run(tmp_path):
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    (evals_dir / "benchmark_50_questions.jsonl").write_text(
        '{"id":"q004","area":"Civil","query":"Quais são os requisitos gerais da responsabilidade civil extracontratual?","expected_source_domains":["dre.pt"],"must_abstain":false}\n',
        encoding="utf-8",
    )
    (evals_dir / "expected_sources.jsonl").write_text("", encoding="utf-8")
    (evals_dir / "no_source_tests.jsonl").write_text(
        '{"id":"n001","query":"Qual é a orientação jurisprudencial dominante sobre questão não indexada?","expected_behavior":"abstain"}\n',
        encoding="utf-8",
    )
    (evals_dir / "hallucination_tests.jsonl").write_text(
        '{"id":"h001","query":"Explica o artigo 999.º do Código dos Contratos Públicos.","expected_behavior":"fail_or_abstain","forbidden_identifiers":["CCP, art. 999.º"]}\n',
        encoding="utf-8",
    )
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.post("/admin/evaluation/run", json={"evals_dir": str(evals_dir)})
        assert response.status_code == 200
        payload = response.json()
        list_response = client.get("/admin/evaluation/runs", params={"passed": "true"})
        get_response = client.get(f"/admin/evaluation/runs/{payload['id']}")
    finally:
        app.dependency_overrides.clear()

    assert payload["passed"] is True
    assert payload["total_cases"] == 3
    assert payload["failed_cases_count"] == 0
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["runs"][0]["id"] == payload["id"]
    assert get_response.status_code == 200
    assert get_response.json()["id"] == payload["id"]


def test_admin_evaluation_run_endpoint_returns_404_for_missing_run(tmp_path):
    repository = LegalRepository(tmp_path / "legal-engine.sqlite3")
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.get("/admin/evaluation/runs/missing-run")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_openapi_smoke_includes_chat_and_admin_endpoints():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/chat/answer" in paths
    assert "/admin/documents" in paths
    assert "/admin/documents/{document_id}" in paths
    assert "/admin/documents/{document_id}/chunks" in paths
    assert "/admin/documents/{document_id}/status" in paths
    assert "/admin/audits" in paths
    assert "/admin/evaluation/run" in paths
    assert "/admin/evaluation/runs" in paths
