"""Apply numbered SQL migrations in ``app/db/migrations/`` in order.

Tracks applied versions in a ``schema_migrations`` table so re-runs are
idempotent. Uses asyncpg directly (not SQLAlchemy) because migration files
contain multiple statements per file.

Usage:  python scripts/migrate.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "app" / "db" / "migrations"


def _asyncpg_dsn(database_url: str) -> str:
    """Strip the SQLAlchemy driver suffix for a raw asyncpg connection."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def _applied_versions(conn: asyncpg.Connection) -> set[str]:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version    text PRIMARY KEY,
          applied_at timestamptz DEFAULT now()
        )
        """
    )
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in rows}


async def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set. Populate .env first.")

    ssl = "require" if settings.db_ssl else None
    conn = await asyncpg.connect(_asyncpg_dsn(settings.database_url), ssl=ssl)
    try:
        applied = await _applied_versions(conn)
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not files:
            print("No migration files found.")
            return

        for path in files:
            version = path.stem  # e.g. "001_init"
            if version in applied:
                print(f"skip  {version} (already applied)")
                continue
            sql = path.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )
            print(f"apply {version}")
        print("Migrations up to date.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
