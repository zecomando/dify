from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.corpus import seed_initial_corpus
from app.repository import LegalRepository
from app.source_policy import SourcePolicy, get_default_source_policy_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Legal Engine initial deterministic demo corpus.")
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
    parser.add_argument("--json", action="store_true", help="Print the seed result as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    database_path = args.database_path or settings.database_path
    database_url = args.database_url or settings.database_url
    repository = LegalRepository(database_path, database_url)
    source_policy = SourcePolicy.from_file(args.source_policy)
    result = seed_initial_corpus(repository, source_policy)

    if args.json:
        print(json.dumps(_result_dict(result), ensure_ascii=False, indent=2))
    else:
        print(
            "seeded initial corpus: "
            f"created={result.created_documents}, "
            f"already_present={result.already_present_documents}, "
            f"chat_ready={result.chat_ready_documents}, "
            f"pending_review={result.pending_review_documents}, "
            f"rejected={result.rejected_jobs}"
        )
    return 0 if result.rejected_jobs == 0 else 1


def _result_dict(result: object) -> dict[str, object]:
    return {
        "total_seeds": getattr(result, "total_seeds"),
        "created_documents": getattr(result, "created_documents"),
        "already_present_documents": getattr(result, "already_present_documents"),
        "completed_jobs": getattr(result, "completed_jobs"),
        "rejected_jobs": getattr(result, "rejected_jobs"),
        "chat_ready_documents": getattr(result, "chat_ready_documents"),
        "pending_review_documents": getattr(result, "pending_review_documents"),
        "document_ids": list(getattr(result, "document_ids")),
        "rejected_source_urls": list(getattr(result, "rejected_source_urls")),
    }


if __name__ == "__main__":
    raise SystemExit(main())
