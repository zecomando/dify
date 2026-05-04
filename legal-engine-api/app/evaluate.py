from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.evaluation import run_evaluation
from app.source_policy import get_default_source_policy_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Legal Engine deterministic evaluation quality gates.")
    parser.add_argument(
        "--evals-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "docs" / "legal-ai" / "evals",
    )
    parser.add_argument(
        "--source-policy",
        type=Path,
        default=get_default_source_policy_path(),
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL database URL. Defaults to LEGAL_ENGINE_DATABASE_URL when set.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full evaluation result as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    database_url = args.database_url or settings.database_url
    result = run_evaluation(args.evals_dir, args.source_policy, args.database_path, database_url)
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(f"passed={result.passed}")
        for gate in result.quality_gates:
            status = "PASS" if gate.passed else "FAIL"
            print(f"{status} {gate.name}: actual={gate.actual} threshold={gate.threshold}")
        print(
            "metrics: "
            f"total={result.metrics.total_cases}, "
            f"successful={result.metrics.successful_cases}, "
            f"failed={result.metrics.failed_cases}, "
            f"audit_coverage={result.metrics.audit_coverage}"
        )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
