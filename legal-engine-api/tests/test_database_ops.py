from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.config import get_settings
from app.database_ops import backup_database, migrate_database, restore_database
from app.repository import LegalRepository, SCHEMA_VERSION


def test_settings_reads_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database_path = tmp_path / "legal.sqlite3"
    monkeypatch.setenv("LEGAL_ENGINE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("LEGAL_ENGINE_DATABASE_URL", "postgresql://user:pass@localhost:5432/legal")
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.database_path == database_path.resolve()
    assert settings.database_url == "postgresql://user:pass@localhost:5432/legal"


def test_migrate_database_initializes_sqlite_schema_and_records_version(tmp_path: Path) -> None:
    database_path = tmp_path / "legal.sqlite3"

    result = migrate_database(database_path=database_path)

    assert result.backend == "sqlite"
    assert result.target == str(database_path)
    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        migration = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
    assert "legal_documents" in tables
    assert "answer_feedback" in tables
    assert migration == (SCHEMA_VERSION,)


def test_backup_and_restore_sqlite_database(tmp_path: Path) -> None:
    database_path = tmp_path / "legal.sqlite3"
    backup_path = tmp_path / "backups" / "legal.backup.sqlite3"
    restored_path = tmp_path / "restored.sqlite3"
    LegalRepository(database_path)

    backup_result = backup_database(output_path=backup_path, database_path=database_path)
    restore_result = restore_database(input_path=backup_path, database_path=restored_path)

    assert backup_result.backend == "sqlite"
    assert backup_path.exists()
    assert restore_result.backend == "sqlite"
    assert restored_path.exists()
    with sqlite3.connect(restored_path) as connection:
        migration = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
    assert migration == (SCHEMA_VERSION,)


def test_restore_sqlite_database_requires_overwrite_flag(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    LegalRepository(source_path)
    LegalRepository(target_path)

    with pytest.raises(FileExistsError):
        restore_database(input_path=source_path, database_path=target_path)

    result = restore_database(input_path=source_path, database_path=target_path, overwrite=True)

    assert result.backend == "sqlite"
    assert target_path.exists()


def test_postgresql_backup_and_restore_use_pg_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], *, check: bool) -> object:
        calls.append(command)
        assert check is True
        return object()

    monkeypatch.setattr("app.database_ops.subprocess.run", fake_run)
    backup_path = tmp_path / "legal.dump"
    database_url = "postgresql://user:pass@localhost:5432/legal"

    backup_result = backup_database(
        output_path=backup_path,
        database_path=tmp_path / "unused.sqlite3",
        database_url=database_url,
    )
    backup_path.write_bytes(b"postgres dump")
    restore_result = restore_database(
        input_path=backup_path,
        database_path=tmp_path / "unused.sqlite3",
        database_url=database_url,
    )

    assert backup_result.backend == "postgresql"
    assert restore_result.backend == "postgresql"
    assert calls == [
        ("pg_dump", "--format=custom", "--file", str(backup_path), database_url),
        ("pg_restore", "--clean", "--if-exists", "--dbname", database_url, str(backup_path)),
    ]


def test_postgresql_repository_uses_psycopg_placeholders_and_integer_booleans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_connection = FakePsycopgConnection()
    fake_module = ModuleType("psycopg")
    fake_module.connect = lambda database_url: fake_connection
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)

    repository = LegalRepository(tmp_path / "unused.sqlite3", "postgresql://localhost/legal")
    with repository._connect() as connection:
        connection.execute("SELECT ? WHERE active = ?", ("ok", True))

    assert repository.backend == "postgresql"
    assert ("SELECT %s WHERE active = %s", ("ok", 1)) in fake_connection.cursor_instance.executed
    assert all("?" not in sql for sql, _params in fake_connection.cursor_instance.executed)


class FakePsycopgCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> object:
        self.executed.append((query, params or ()))
        return object()

    def executemany(self, query: str, params_seq: tuple[tuple[object, ...], ...]) -> object:
        for params in params_seq:
            self.execute(query, params)
        return object()

    def fetchone(self) -> tuple[object, ...] | None:
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        return []


class FakePsycopgConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakePsycopgCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> FakePsycopgCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True
