from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.corpus import seed_initial_corpus
from app.demo import run_demo
from app.evaluation import get_default_evals_dir, run_evaluation
from app.n8n_workflows import get_default_n8n_workflows_dir, validate_n8n_workflows
from app.provider_readiness import get_provider_readiness
from app.repository import LegalRepository
from app.source_policy import SourcePolicy, get_default_source_policy_path


@dataclass(frozen=True, slots=True)
class ReadinessCheckResult:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class ReadinessRunResult:
    passed: bool
    backend: str
    database_target: str
    checks: tuple[ReadinessCheckResult, ...]


def run_readiness(
    *,
    database_path: Path,
    database_url: str | None,
    source_policy_path: Path,
    evals_dir: Path,
    n8n_workflows_dir: Path,
    require_admin_token: bool,
    admin_token: str | None,
    run_seed: bool = True,
    run_demo_check: bool = True,
    run_eval_check: bool = True,
    run_n8n_check: bool = True,
    run_provider_check: bool = True,
) -> ReadinessRunResult:
    checks: list[ReadinessCheckResult] = []
    repository = LegalRepository(database_path, database_url)
    source_policy = SourcePolicy.from_file(source_policy_path)
    checks.append(ReadinessCheckResult("database_migration", True, f"schema ready on {repository.backend}"))
    checks.append(
        ReadinessCheckResult(
            "source_policy",
            bool(source_policy.authorities),
            f"loaded {source_policy.name} v{source_policy.version} with {len(source_policy.authorities)} authorities",
        )
    )
    checks.append(
        ReadinessCheckResult(
            "admin_token",
            bool(admin_token) or not require_admin_token,
            "configured" if admin_token else "not required for this run",
        )
    )
    if run_provider_check:
        provider_result = get_provider_readiness()
        checks.append(
            ReadinessCheckResult(
                "provider_readiness",
                True,
                (
                    f"configured={provider_result.configured_providers}/{provider_result.providers_total}, "
                    f"missing={provider_result.missing_providers}, "
                    f"paid_blockers={len(provider_result.paid_provider_blockers)}"
                ),
            )
        )

    if run_seed:
        seed_result = seed_initial_corpus(repository, source_policy)
        checks.append(
            ReadinessCheckResult(
                "seed",
                seed_result.rejected_jobs == 0 and seed_result.chat_ready_documents > 0,
                f"chat_ready={seed_result.chat_ready_documents}, rejected={seed_result.rejected_jobs}",
            )
        )

    if run_demo_check:
        demo_result = run_demo(
            database_path=database_path,
            database_url=database_url,
            source_policy_path=source_policy_path,
            seed_corpus=False,
        )
        checks.append(
            ReadinessCheckResult(
                "demo",
                demo_result.passed,
                f"cases={len(demo_result.cases)}, rejected_seed_jobs={demo_result.seed_rejected_jobs}",
            )
        )

    if run_eval_check:
        evaluation_result = run_evaluation(evals_dir, source_policy_path, database_path, database_url)
        checks.append(
            ReadinessCheckResult(
                "evaluation",
                evaluation_result.passed,
                f"successful={evaluation_result.metrics.successful_cases}/{evaluation_result.metrics.total_cases}",
            )
        )

    if run_n8n_check:
        n8n_result = validate_n8n_workflows(n8n_workflows_dir)
        failed_workflows = [workflow for workflow in n8n_result.workflows if not workflow.passed]
        checks.append(
            ReadinessCheckResult(
                "n8n_workflows",
                n8n_result.passed,
                f"validated={len(n8n_result.workflows)}, failed={len(failed_workflows)}",
            )
        )

    return ReadinessRunResult(
        passed=all(check.passed for check in checks),
        backend=repository.backend,
        database_target=database_url or str(database_path),
        checks=tuple(checks),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Legal Engine local/staging readiness gates without paid providers."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=None,
        help="SQLite database path. Defaults to LEGAL_ENGINE_DATABASE_PATH or the local .data database.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL database URL. Defaults to LEGAL_ENGINE_DATABASE_URL when set.",
    )
    parser.add_argument(
        "--source-policy",
        type=Path,
        default=get_default_source_policy_path(),
        help="Path to docs/legal-ai/source-policy.yml.",
    )
    parser.add_argument(
        "--evals-dir",
        type=Path,
        default=get_default_evals_dir(),
        help="Path to docs/legal-ai/evals.",
    )
    parser.add_argument(
        "--n8n-workflows-dir",
        type=Path,
        default=get_default_n8n_workflows_dir(),
        help="Path to docs/legal-ai/n8n workflow exports.",
    )
    parser.add_argument("--require-admin-token", action="store_true")
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument("--skip-demo", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--skip-n8n", action="store_true")
    parser.add_argument("--skip-provider-readiness", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print readiness result as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    result = run_readiness(
        database_path=args.database_path or settings.database_path,
        database_url=args.database_url or settings.database_url,
        source_policy_path=args.source_policy,
        evals_dir=args.evals_dir,
        n8n_workflows_dir=args.n8n_workflows_dir,
        require_admin_token=args.require_admin_token,
        admin_token=settings.admin_token,
        run_seed=not args.skip_seed,
        run_demo_check=not args.skip_demo,
        run_eval_check=not args.skip_eval,
        run_n8n_check=not args.skip_n8n,
        run_provider_check=not args.skip_provider_readiness,
    )
    if args.json:
        print(json.dumps(_result_dict(result), ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0 if result.passed else 1


def _result_dict(result: ReadinessRunResult) -> dict[str, object]:
    return {
        "passed": result.passed,
        "backend": result.backend,
        "database_target": result.database_target,
        "checks": [{"name": check.name, "passed": check.passed, "message": check.message} for check in result.checks],
    }


def _print_human_result(result: ReadinessRunResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(f"{status} readiness: backend={result.backend}, target={result.database_target}")
    for check in result.checks:
        check_status = "PASS" if check.passed else "FAIL"
        print(f"{check_status} {check.name}: {check.message}")


if __name__ == "__main__":
    raise SystemExit(main())
