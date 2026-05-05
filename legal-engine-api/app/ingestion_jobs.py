from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.repository import IngestionJobRecord, LegalRepository
from app.schemas import IngestionJobStatus


@dataclass(frozen=True, slots=True)
class IngestionJobsResult:
    jobs: tuple[IngestionJobRecord, ...]
    total: int


def list_ingestion_jobs(
    repository: LegalRepository,
    *,
    status: str | None = None,
    mode: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> IngestionJobsResult:
    jobs = repository.list_jobs(
        status=status,
        mode=mode,
        source=source,
        limit=limit,
        offset=offset,
    )
    total = repository.count_jobs(status=status, mode=mode, source=source)
    return IngestionJobsResult(jobs=jobs, total=total)


def main() -> int:
    parser = argparse.ArgumentParser(description="List Legal Engine ingestion jobs with errors and document links.")
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
        "--status",
        choices=tuple(status.value for status in IngestionJobStatus),
        default=None,
        help="Filter by ingestion job status.",
    )
    parser.add_argument("--mode", default=None, help="Filter by ingestion job mode, for example manual or crawl.")
    parser.add_argument("--source", default=None, help="Filter by source code or domain.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="Print ingestion jobs as JSON.")
    args = parser.parse_args()

    settings = get_settings()
    repository = LegalRepository(
        args.database_path or settings.database_path,
        args.database_url or settings.database_url,
    )
    result = list_ingestion_jobs(
        repository,
        status=args.status,
        mode=args.mode,
        source=args.source,
        limit=args.limit,
        offset=args.offset,
    )

    if args.json:
        print(json.dumps(_result_dict(result), ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0


def _print_human_result(result: IngestionJobsResult) -> None:
    print(f"ingestion jobs: total={result.total}, shown={len(result.jobs)}")
    for job in result.jobs:
        document_id = job.document_id or "-"
        print(
            f"{job.status.upper()} {job.id}: mode={job.mode}, source={job.source}, "
            f"document_id={document_id}, updated_at={job.updated_at}, url={job.source_url}"
        )
        if job.error_message:
            print(f"  error: {job.error_message}")


def _result_dict(result: IngestionJobsResult) -> dict[str, object]:
    return {
        "total": result.total,
        "jobs": [_job_dict(job) for job in result.jobs],
    }


def _job_dict(job: IngestionJobRecord) -> dict[str, object]:
    return {
        "id": job.id,
        "source": job.source,
        "source_url": job.source_url,
        "requested_by": job.requested_by,
        "mode": job.mode,
        "status": job.status,
        "error_message": job.error_message,
        "document_id": job.document_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


if __name__ == "__main__":
    raise SystemExit(main())
