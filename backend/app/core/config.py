"""Central configuration: paths, CORS, freshness thresholds.

This module is dependency-free so the decision logic can import it.
No API keys or paid services are needed anywhere.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


def _load_env_file(path: Path) -> None:
    """Tiny .env reader (KEY=VALUE). Existing environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class FreshnessConfig:
    """Freshness thresholds, defined once and used everywhere."""

    recent_hours: float = 6.0            # age <= this -> "recent"; older -> "stale"
    future_tolerance_hours: float = 0.1  # timestamps further in the future -> "unknown"


FRESHNESS = FreshnessConfig()


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    cors_origins: tuple
    auto_seed: bool

    @staticmethod
    def from_env() -> "Settings":
        default_db = f"sqlite:///{(BACKEND_DIR / 'raktsetu.db').as_posix()}"
        origins = os.environ.get(
            "RAKTSETU_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
        return Settings(
            database_url=os.environ.get("RAKTSETU_DATABASE_URL", default_db),
            data_dir=Path(os.environ.get("RAKTSETU_DATA_DIR", PROJECT_ROOT / "data")),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            auto_seed=os.environ.get("RAKTSETU_AUTO_SEED", "true").lower() != "false",
        )


def get_settings() -> Settings:
    return Settings.from_env()
