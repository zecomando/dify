from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.repository import LegalRepository


@dataclass(frozen=True, slots=True)
class DatabaseOperationResult:
    backend: str
    target: str
    message: str


def migrate_database(*, database_path: Path, database_url: str | None = None) -> DatabaseOperationResult:
    repository = LegalRepository(database_path, database_url)
    return DatabaseOperationResult(
        backend=repository.backend,
        target=database_url or str(database_path),
        message="schema initialized",
    )


def backup_database(
    *, output_path: Path, database_path: Path, database_url: str | None = None
) -> DatabaseOperationResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if database_url is not None:
        _run_postgres_command(("pg_dump", "--format=custom", "--file", str(output_path), database_url))
        return DatabaseOperationResult(
            backend="postgresql", target=str(output_path), message="backup created with pg_dump"
        )

    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {database_path}")
    shutil.copy2(database_path, output_path)
    return DatabaseOperationResult(backend="sqlite", target=str(output_path), message="backup copied")


def restore_database(
    *,
    input_path: Path,
    database_path: Path,
    database_url: str | None = None,
    overwrite: bool = False,
) -> DatabaseOperationResult:
    if not input_path.exists():
        raise FileNotFoundError(f"Backup file does not exist: {input_path}")

    if database_url is not None:
        _run_postgres_command(("pg_restore", "--clean", "--if-exists", "--dbname", database_url, str(input_path)))
        return DatabaseOperationResult(
            backend="postgresql", target=database_url, message="backup restored with pg_restore"
        )

    if database_path.exists() and not overwrite:
        raise FileExistsError(f"SQLite database already exists: {database_path}. Pass --overwrite to replace it.")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, database_path)
    return DatabaseOperationResult(backend="sqlite", target=str(database_path), message="backup restored")


def migrate_main() -> int:
    parser = argparse.ArgumentParser(description="Initialize or migrate the Legal Engine database schema.")
    _add_database_arguments(parser)
    args = parser.parse_args()
    settings = get_settings()
    result = migrate_database(
        database_path=args.database_path or settings.database_path,
        database_url=args.database_url or settings.database_url,
    )
    _print_result(result)
    return 0


def backup_main() -> int:
    parser = argparse.ArgumentParser(description="Create a Legal Engine database backup.")
    _add_database_arguments(parser)
    parser.add_argument("--output", type=Path, required=True, help="Backup output path.")
    args = parser.parse_args()
    settings = get_settings()
    result = backup_database(
        output_path=args.output,
        database_path=args.database_path or settings.database_path,
        database_url=args.database_url or settings.database_url,
    )
    _print_result(result)
    return 0


def restore_main() -> int:
    parser = argparse.ArgumentParser(description="Restore a Legal Engine database backup.")
    _add_database_arguments(parser)
    parser.add_argument("--input", type=Path, required=True, help="Backup input path.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing SQLite database.")
    args = parser.parse_args()
    settings = get_settings()
    result = restore_database(
        input_path=args.input,
        database_path=args.database_path or settings.database_path,
        database_url=args.database_url or settings.database_url,
        overwrite=args.overwrite,
    )
    _print_result(result)
    return 0


def _add_database_arguments(parser: argparse.ArgumentParser) -> None:
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


def _run_postgres_command(command: tuple[str, ...]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required PostgreSQL command not found: {command[0]}") from exc


def _print_result(result: DatabaseOperationResult) -> None:
    print(f"{result.message}: backend={result.backend}, target={result.target}")
