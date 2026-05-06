from pathlib import Path

from app.provider_readiness import ProviderReadinessResult
from app.readiness import main, run_readiness


POLICY_PATH = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "source-policy.yml"
EVALS_DIR = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "evals"
N8N_DIR = Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "n8n"


def test_run_readiness_can_check_database_policy_seed_and_demo_without_external_providers(tmp_path: Path):
    result = run_readiness(
        database_path=tmp_path / "readiness.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        n8n_workflows_dir=N8N_DIR,
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
        "provider_readiness",
        "seed",
        "demo",
        "n8n_workflows",
    }
    assert all(check.passed for check in result.checks)


def test_run_readiness_fails_when_admin_token_is_required_but_missing(tmp_path: Path):
    result = run_readiness(
        database_path=tmp_path / "readiness.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        n8n_workflows_dir=N8N_DIR,
        require_admin_token=True,
        admin_token=None,
        run_seed=False,
        run_demo_check=False,
        run_eval_check=False,
        run_n8n_check=False,
        run_provider_check=False,
    )

    assert result.passed is False
    admin_token_check = next(check for check in result.checks if check.name == "admin_token")
    assert admin_token_check.passed is False


def test_run_readiness_fails_when_postgresql_is_required_but_sqlite_is_used(tmp_path: Path):
    result = run_readiness(
        database_path=tmp_path / "readiness.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        n8n_workflows_dir=N8N_DIR,
        require_admin_token=False,
        admin_token=None,
        require_postgresql=True,
        run_seed=False,
        run_demo_check=False,
        run_eval_check=False,
        run_n8n_check=False,
        run_provider_check=False,
    )

    assert result.passed is False
    postgresql_check = next(check for check in result.checks if check.name == "postgresql_required")
    assert postgresql_check.passed is False
    assert "LEGAL_ENGINE_DATABASE_URL" in postgresql_check.message


def test_run_readiness_fails_when_provider_readiness_is_required_and_blocked(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.readiness.get_provider_readiness",
        lambda: ProviderReadinessResult(
            status="blocked",
            providers_total=2,
            configured_providers=1,
            missing_providers=1,
            paid_provider_blockers=("OpenAI embeddings",),
            providers=(),
        ),
    )

    result = run_readiness(
        database_path=tmp_path / "readiness.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        n8n_workflows_dir=N8N_DIR,
        require_admin_token=False,
        admin_token=None,
        require_provider_readiness=True,
        run_seed=False,
        run_demo_check=False,
        run_eval_check=False,
        run_n8n_check=False,
    )

    assert result.passed is False
    provider_check = next(check for check in result.checks if check.name == "provider_readiness")
    assert provider_check.passed is False
    assert "missing=1" in provider_check.message
    assert "paid_blockers=1" in provider_check.message


def test_run_readiness_does_not_block_on_missing_providers_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.readiness.get_provider_readiness",
        lambda: ProviderReadinessResult(
            status="blocked",
            providers_total=2,
            configured_providers=1,
            missing_providers=1,
            paid_provider_blockers=("OpenAI embeddings",),
            providers=(),
        ),
    )

    result = run_readiness(
        database_path=tmp_path / "readiness.sqlite3",
        database_url=None,
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        n8n_workflows_dir=N8N_DIR,
        require_admin_token=False,
        admin_token=None,
        run_seed=False,
        run_demo_check=False,
        run_eval_check=False,
        run_n8n_check=False,
    )

    assert result.passed is True
    provider_check = next(check for check in result.checks if check.name == "provider_readiness")
    assert provider_check.passed is True


def test_run_readiness_passes_postgresql_requirement_when_backend_is_postgresql(tmp_path: Path, monkeypatch):
    class FakeRepository:
        backend = "postgresql"

        def __init__(self, database_path: Path, database_url: str | None) -> None:
            self.database_path = database_path
            self.database_url = database_url

    monkeypatch.setattr("app.readiness.LegalRepository", FakeRepository)

    result = run_readiness(
        database_path=tmp_path / "unused.sqlite3",
        database_url="postgresql://localhost/legal",
        source_policy_path=POLICY_PATH,
        evals_dir=EVALS_DIR,
        n8n_workflows_dir=N8N_DIR,
        require_admin_token=False,
        admin_token=None,
        require_postgresql=True,
        run_seed=False,
        run_demo_check=False,
        run_eval_check=False,
        run_n8n_check=False,
        run_provider_check=False,
    )

    assert result.passed is True
    postgresql_check = next(check for check in result.checks if check.name == "postgresql_required")
    assert postgresql_check.passed is True


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
            "--n8n-workflows-dir",
            str(N8N_DIR),
            "--skip-eval",
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert '"database_migration"' in captured.out
    assert '"provider_readiness"' in captured.out


def test_readiness_cli_fails_json_when_postgresql_is_required_with_sqlite(tmp_path: Path, monkeypatch, capsys):
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
            "--n8n-workflows-dir",
            str(N8N_DIR),
            "--require-postgresql",
            "--skip-seed",
            "--skip-demo",
            "--skip-eval",
            "--skip-n8n",
            "--skip-provider-readiness",
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"passed": false' in captured.out
    assert '"name": "postgresql_required"' in captured.out


def test_readiness_cli_fails_json_when_provider_readiness_is_required_and_blocked(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        "app.readiness.get_provider_readiness",
        lambda: ProviderReadinessResult(
            status="blocked",
            providers_total=2,
            configured_providers=1,
            missing_providers=1,
            paid_provider_blockers=("OpenAI embeddings",),
            providers=(),
        ),
    )
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
            "--n8n-workflows-dir",
            str(N8N_DIR),
            "--require-provider-readiness",
            "--skip-seed",
            "--skip-demo",
            "--skip-eval",
            "--skip-n8n",
            "--json",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"passed": false' in captured.out
    assert '"name": "provider_readiness"' in captured.out
    assert "paid_blockers=1" in captured.out
