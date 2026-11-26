"""Backend configuration for CERBERUS-X."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


@dataclass(frozen=True)
class BackendSettings:
    """Runtime paths and CORS configuration (env-overridable for testing)."""

    db_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("CERBERUS_DB_PATH", str(DATA_DIR / "cerberus.db"))
        )
    )
    upload_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("CERBERUS_UPLOAD_DIR", str(DATA_DIR / "uploads"))
        )
    )
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )


def get_settings() -> BackendSettings:
    return BackendSettings()
