import json
from pathlib import Path
from types import FunctionType

import yaml


DIFY_WORKFLOW_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "dify-chat-answer.yml"


def _workflow() -> dict[str, object]:
    loaded = yaml.safe_load(DIFY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _format_answer(response: dict[str, object], status_code: int = 200) -> str:
    workflow = _workflow()["workflow"]
    graph = workflow["graph"]
    code_node = next(node for node in graph["nodes"] if node["id"] == "format_legal_answer")
    namespace: dict[str, object] = {}
    exec(code_node["data"]["code"], namespace)
    main = namespace["main"]
    assert isinstance(main, FunctionType)
    result = main(json.dumps(response), status_code)
    return result["formatted_answer"]


def test_dify_workflow_uses_legal_engine_as_canonical_backend():
    workflow = _workflow()["workflow"]
    features = workflow["features"]
    graph = workflow["graph"]
    http_node = next(node for node in graph["nodes"] if node["id"] == "legal_chat_answer_http")

    assert "Uso experimental" in features["opening_statement"]
    assert "não substitui" in features["opening_statement"]
    assert http_node["data"]["method"] == "POST"
    assert http_node["data"]["url"].endswith("/chat/answer")
    assert '"mode": "strict"' in http_node["data"]["body"]["data"][0]["value"]


def test_dify_formatter_presents_valid_answer_with_sources_warnings_and_feedback():
    formatted = _format_answer(
        {
            "audit_id": "audit-1",
            "answer": "A responsabilidade civil extracontratual exige facto, ilicitude, culpa, dano e nexo causal.",
            "verdict": "pass",
            "classification": {},
            "evidence": [
                {
                    "chunk_id": "chunk-1",
                    "document_id": "document-1",
                    "citation_label": "Código Civil, artigo 483.º",
                    "text": "Aquele que, com dolo ou mera culpa, violar ilicitamente o direito de outrem...",
                    "source_url": "https://dre.pt/dre/legislacao-consolidada/decreto-lei/1966-34509075-49748275",
                    "canonical_url": "https://dre.pt/dre/legislacao-consolidada/decreto-lei/1966-34509075-49748275",
                    "source": "DRE",
                    "jurisdiction": "PT",
                    "document_type": "legislation",
                    "legal_metadata": {"eli": "eli/dec-lei/47344/1966/11/25/p/dre/pt/html", "article": "483"},
                    "is_current": True,
                    "is_consolidated": True,
                    "legal_value_warning": "Texto consolidado do DRE: instrumento documental/de consulta sem valor legal autónomo.",
                    "version_label": "current",
                }
            ],
            "warnings": ["Confirmar sempre a versão aplicável ao caso concreto."],
            "unsupported_claims": [],
            "missing_citations": [],
            "wrong_version_risk": False,
            "hallucinated_identifiers": [],
        }
    )

    assert "## Resposta jurídica validada" in formatted
    assert "## Base legal, jurisprudência e fontes oficiais" in formatted
    assert "[Código Civil, artigo 483.º](https://dre.pt" in formatted
    assert "ELI: eli/dec-lei/47344/1966/11/25/p/dre/pt/html" in formatted
    assert "Artigo: 483" in formatted
    assert "## Limites e confiança" in formatted
    assert "Confiança operacional: alta" in formatted
    assert "Audit ID: audit-1" in formatted
    assert "não substitui a análise de um advogado" in formatted
    assert "## Feedback e revisão" in formatted
    assert "fonte errada" in formatted
    assert "## Avisos visíveis" in formatted
    assert "Texto consolidado do DRE" in formatted


def test_dify_formatter_presents_abstention_as_safe_outcome():
    formatted = _format_answer(
        {
            "audit_id": "audit-2",
            "answer": "Não encontrei fontes oficiais suficientes no corpus para responder com segurança.",
            "verdict": "abstain",
            "classification": {},
            "evidence": [],
            "warnings": [],
            "unsupported_claims": [],
            "missing_citations": [],
            "wrong_version_risk": False,
            "hallucinated_identifiers": [],
        }
    )

    assert "## Abstenção segura" in formatted
    assert "Nenhuma fonte oficial utilizável foi encontrada." in formatted
    assert "Confiança operacional: segura por abstenção" in formatted
    assert "Audit ID: audit-2" in formatted
    assert "## Feedback e revisão" in formatted


def test_dify_formatter_blocks_invalid_or_failed_backend_response():
    assert "Serviço temporariamente indisponível" in _format_answer({}, status_code=503)

    formatted = _format_answer(
        {
            "audit_id": "audit-3",
            "answer": "A resposta foi bloqueada por falta de suporte suficiente.",
            "verdict": "fail",
            "classification": {},
            "evidence": [],
            "warnings": [],
            "unsupported_claims": ["Conclusão sem fonte oficial."],
            "missing_citations": ["Artigo sem citação."],
            "wrong_version_risk": True,
            "hallucinated_identifiers": ["CELEX:9999X0000"],
        }
    )

    assert "## Resposta bloqueada pelo validador" in formatted
    assert "Confiança operacional: bloqueada" in formatted
    assert "## Validação" in formatted
    assert "Conclusão sem fonte oficial." in formatted
    assert "CELEX:9999X0000" in formatted
    assert "Risco temporal ou de versão" in formatted
