"""Central configuration: paths, CORS, freshness thresholds.

This module is dependency-free so the decision logic can import it.
No API keys or paid services are needed anywhere.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

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


def parse_demo_tokens(raw: str) -> Dict[str, str]:
    """Parse RAKTSETU_DEMO_TOKENS from JSON or comma-separated token:bank_id pairs.

    Fails closed: returns an empty dict if missing, empty, or unparseable.
    """
    if not raw or not raw.strip():
        return {}
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {
                    str(k).strip(): str(v).strip()
                    for k, v in parsed.items()
                    if str(k).strip() and str(v).strip()
                }
        except Exception:
            return {}
    tokens: Dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        delim = ":" if ":" in item else "=" if "=" in item else None
        if delim:
            k, _, v = item.partition(delim)
            k, v = k.strip(), v.strip()
            if k and v:
                tokens[k] = v
    return tokens


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    cors_origins: tuple
    auto_seed: bool
    demo_tokens: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_env() -> "Settings":
        default_db = f"sqlite:///{(BACKEND_DIR / 'raktsetu.db').as_posix()}"
        origins = os.environ.get(
            "RAKTSETU_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
        tokens_raw = os.environ.get("RAKTSETU_DEMO_TOKENS", "")
        return Settings(
            database_url=os.environ.get("RAKTSETU_DATABASE_URL", default_db),
            data_dir=Path(os.environ.get("RAKTSETU_DATA_DIR", PROJECT_ROOT / "data")),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            auto_seed=os.environ.get("RAKTSETU_AUTO_SEED", "true").lower() != "false",
            demo_tokens=parse_demo_tokens(tokens_raw),
        )


def get_settings() -> Settings:
    return Settings.from_env()
