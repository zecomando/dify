import json
from pathlib import Path

from app.n8n_workflows import main, validate_n8n_workflows


N8N_DIR = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "n8n"


def test_validate_n8n_workflows_accepts_exported_workflows_without_embedded_secrets():
    summary = validate_n8n_workflows(N8N_DIR)

    assert summary.passed is True
    assert {Path(result.path).name for result in summary.workflows} == {
        "evaluation-run.json",
        "local-staging-seed-smoke.json",
        "manual-url-ingestion.json",
        "reindex-schedule.json",
    }
    assert all(result.errors == () for result in summary.workflows)


def test_validate_n8n_workflows_rejects_hardcoded_admin_url_and_token(tmp_path: Path):
    workflows_dir = tmp_path / "n8n"
    workflows_dir.mkdir()
    (workflows_dir / "unsafe.json").write_text(
        json.dumps(
            {
                "name": "Unsafe workflow",
                "versionId": "unsafe-v1",
                "nodes": [
                    {
                        "id": "unsafe-http",
                        "name": "Unsafe Admin Call",
                        "type": "n8n-nodes-base.httpRequest",
                        "typeVersion": 4.2,
                        "parameters": {
                            "url": "https://legal-engine.example.com/admin/documents",
                            "headerParameters": {
                                "parameters": [{"name": "X-Admin-Token", "value": "plain-secret-token"}]
                            },
                        },
                    }
                ],
                "connections": {},
            }
        ),
        encoding="utf-8",
    )

    summary = validate_n8n_workflows(workflows_dir)

    assert summary.passed is False
    assert summary.workflows[0].passed is False
    assert any("LEGAL_ENGINE_BASE_URL" in error for error in summary.workflows[0].errors)
    assert any("LEGAL_ENGINE_ADMIN_TOKEN" in error for error in summary.workflows[0].errors)


def test_n8n_workflows_cli_prints_json_result(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-n8n-validate",
            "--workflows-dir",
            str(N8N_DIR),
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert "manual-url-ingestion.json" in captured.out
