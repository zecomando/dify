from pathlib import Path

from app.readiness import main, run_readiness


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"
EVALS_DIR = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "evals"


def test_run_readiness_can_check_database_policy_seed_and_demo_without_external_providers(tmp_path: Path):
    result = run_readiness(
        database_path=tmp_path / "readiness.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        require_admin_token=False,
        admin_token=None,
        run_eval_check=False,
    )

    assert result.passed is True
    assert result.backend == "sqlite"
    assert {check.name for check in result.checks} == {
        "database_migration",
        "source_policy",
        "admin_token",
        "seed",
        "demo",
    }
    assert all(check.passed for check in result.checks)


def test_run_readiness_fails_when_admin_token_is_required_but_missing(tmp_path: Path):
    result = run_readiness(
        database_path=tmp_path / "readiness.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        require_admin_token=True,
        admin_token=None,
        run_seed=False,
        run_demo_check=False,
        run_eval_check=False,
    )

    assert result.passed is False
    admin_token_check = next(check for check in result.checks if check.name == "admin_token")
    assert admin_token_check.passed is False


def test_readiness_cli_prints_json_result(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "legal-readiness",
            "--database-path",
            str(tmp_path / "readiness.sqlite3"),
            "--source-policy",
            str(POLICY_PATH),
            "--evals-dir",
            str(EVALS_DIR),
            "--skip-eval",
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert '"database_migration"' in captured.out
