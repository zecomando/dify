import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_path: Path
    admin_token: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_path = os.environ.get("LEGAL_ENGINE_DATABASE_PATH")
    admin_token = os.environ.get("LEGAL_ENGINE_ADMIN_TOKEN", "").strip() or None
    if database_path:
        resolved_database_path = Path(database_path).expanduser().resolve()
    else:
        resolved_database_path = Path(__file__).resolve().parents[1] / ".data" / "legal_engine.sqlite3"
    return Settings(database_path=resolved_database_path, admin_token=admin_token)
