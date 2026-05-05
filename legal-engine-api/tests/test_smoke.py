from pathlib import Path

from app.config import get_settings
from app.smoke import main, run_smoke


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"
EVALS_DIR = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "evals"


def test_run_smoke_generates_traceable_local_report(tmp_path: Path):
    result = run_smoke(
        database_path=tmp_path / "smoke.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
    )

    assert result.passed is True
    assert result.backend == "sqlite"
    assert result.seed.rejected_jobs == 0
    assert result.seed.chat_ready_documents > 0
    assert {case.id for case in result.chat_cases} == {"civil-liability", "rgpd-lawfulness", "insufficient-source"}
    assert all(case.audit_id for case in result.chat_cases)
    assert any(case.verdict == "abstain" for case in result.chat_cases)
    assert result.evaluation_run_id
    assert result.evaluation_passed is True
    assert result.diagnostics["chat_ready_documents"] == result.seed.chat_ready_documents
    assert result.diagnostics["answer_audits_total"] >= len(result.chat_cases)
    assert result.diagnostics["evaluation_runs_total"] == 1


def test_smoke_cli_prints_json_report(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-smoke",
            "--database-path",
            str(tmp_path / "smoke.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
            "--evals-dir",
            str(EVALS_DIR),
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert '"evaluation_run_id"' in captured.out
    assert '"audit_id"' in captured.out


def test_smoke_cli_uses_database_url_from_environment(tmp_path: Path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_smoke(
        *,
        database_path: Path,
        database_url: str | None,
        source_policy_path: Path,
        evals_dir: Path,
    ) -> object:
        captured["database_path"] = database_path
        captured["database_url"] = database_url
        captured["source_policy_path"] = source_policy_path
        captured["evals_dir"] = evals_dir
        return type(
            "SmokeResult",
            (),
            {
                "passed": True,
                "model_dump": lambda self, mode: {
                    "passed": True,
                    "backend": "postgresql",
                    "database_target": "postgresql://localhost/legal",
                    "seed": {},
                    "chat_cases": [],
                    "evaluation_run_id": "run-1",
                    "evaluation_passed": True,
                    "diagnostics": {},
                },
            },
        )()

    monkeypatch.setenv("LEGAL_ENGINE_DATABASE_URL", "postgresql://localhost/legal")
    get_settings.cache_clear()
    monkeypatch.setattr("app.smoke.run_smoke", fake_run_smoke)
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-smoke",
            "--database-path",
            str(tmp_path / "smoke.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
            "--evals-dir",
            str(EVALS_DIR),
            "--json",
        ],
    )

    try:
        exit_code = main()
    finally:
        get_settings.cache_clear()

    assert exit_code == 0
    assert captured["database_url"] == "postgresql://localhost/legal"
    assert captured["database_path"] == tmp_path / "smoke.sqlite3"
