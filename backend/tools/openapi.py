"""Writes the backend OpenAPI to `backend/openapi.json` (gitignored), the contract for types."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    # Placeholder values only so the settings load; nothing here opens a connection.
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    os.environ.setdefault("SECRET_KEY", "openapi-placeholder-not-a-secret")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    from app.main import create_app

    target = ROOT / "openapi.json"
    target.write_text(
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{target.relative_to(ROOT)} written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
