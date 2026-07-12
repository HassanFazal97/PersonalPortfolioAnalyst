"""RLS policies verified against a real Postgres (throwaway Docker container).

This is the test that would have caught the July 2026 production incident:
migration 011 assumed the app connects as table owner (RLS bypassed), but
production runs a restricted role, so the strict users policy broke
auth-time provisioning. Here the full migration chain is applied to a
scratch Postgres 16 and every access pattern the app actually uses is
exercised as a NON-owner role:

  * service context (owner GUC): auth_id lookup + user provisioning,
    cross-tenant scheduler fan-out
  * tenant context: sees only its own rows
  * no context (the Data API / anon-key shape): sees nothing
  * every public table has RLS enabled — a new table without a policy
    fails here before it ships

Skipped when Docker isn't available (e.g. minimal CI runners).
"""

import asyncio
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parent.parent

OWNER_GUC = "00000000-0000-0000-0000-000000000001"
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
AUTH_A = "aaaa1111-0000-0000-0000-000000000001"

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not available"
)


def _docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture(scope="module")
def pg_dsn():
    """Scratch Postgres 16 with the full migration chain applied."""
    name = f"pa-rls-test-{uuid.uuid4().hex[:8]}"
    try:
        _docker(
            "run", "-d", "--rm", "--name", name,
            "-e", "POSTGRES_PASSWORD=test",
            "-p", "127.0.0.1:0:5432", "postgres:16-alpine",
        )
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"could not start postgres container: {exc.stderr}")
    try:
        host_port = _docker("port", name, "5432/tcp").splitlines()[0].rsplit(":", 1)[1]
        dsn = f"postgresql://postgres:test@127.0.0.1:{host_port}/postgres"
        for attempt in range(30):
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres", "-q"]
            )
            if ready.returncode == 0:
                break
            asyncio.run(asyncio.sleep(0.5))
        else:
            pytest.fail("postgres container never became ready")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "migrate.py")],
            env={
                "PATH": "/usr/bin:/bin",
                "DATABASE_URL": dsn,
                "MIGRATION_DATABASE_URL": "",
                "DB_SSL": "false",
                # Neutralize the developer's .env (pydantic reads it directly).
                "API_TOKEN": "x", "SUPABASE_URL": "", "SUPABASE_JWT_SECRET": "",
            },
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        yield dsn
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True)


async def _seed_and_connect_restricted(dsn: str) -> asyncpg.Connection:
    """Seed two tenants as owner, then connect as a fresh non-owner role."""
    owner = await asyncpg.connect(dsn)
    try:
        await owner.execute(
            """
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_restricted')
              THEN CREATE ROLE app_restricted LOGIN PASSWORD 'test'; END IF;
            END $$;
            GRANT USAGE ON SCHEMA public TO app_restricted;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON ALL TABLES IN SCHEMA public TO app_restricted;
            """
        )
        await owner.execute(
            """
            INSERT INTO users (id, auth_id, email) VALUES
              ($1, $3, 'a@test'), ($2, NULL, 'b@test')
            ON CONFLICT (id) DO NOTHING
            """,
            uuid.UUID(TENANT_A), uuid.UUID(TENANT_B), uuid.UUID(AUTH_A),
        )
        await owner.execute(
            """
            INSERT INTO positions (user_id, ticker, quantity, avg_cost, currency, account)
            VALUES ($1, 'VFV', 1, 1, 'CAD', 'TFSA'), ($2, 'NVDA', 1, 1, 'CAD', 'TFSA')
            ON CONFLICT (user_id, ticker, account) DO NOTHING
            """,
            uuid.UUID(TENANT_A), uuid.UUID(TENANT_B),
        )
    finally:
        await owner.close()
    return await asyncpg.connect(dsn.replace("postgres:test@", "app_restricted:test@"))


async def _set_guc(conn: asyncpg.Connection, value: str) -> None:
    await conn.execute("SELECT set_config('app.current_user_id', $1, false)", value)


@pytest.mark.asyncio
async def test_every_public_table_has_rls_enabled(pg_dsn):
    conn = await asyncpg.connect(pg_dsn)
    try:
        rows = await conn.fetch(
            """
            SELECT relname FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND NOT c.relrowsecurity
            """
        )
        assert not rows, f"tables without RLS: {[r['relname'] for r in rows]}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_service_context_can_provision_and_fan_out(pg_dsn):
    # The exact flow that broke in production: get_or_create_user runs before
    # the request user is bound, i.e. under the owner-GUC fallback.
    conn = await _seed_and_connect_restricted(pg_dsn)
    try:
        await _set_guc(conn, OWNER_GUC)
        found = await conn.fetchval(
            "SELECT count(*) FROM users WHERE auth_id = $1", uuid.UUID(AUTH_A)
        )
        assert found == 1, "service context must find users by auth_id"
        new_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users (id, auth_id, email) VALUES ($1, $2, 'new@test')",
            new_id, uuid.uuid4(),
        )
        assert await conn.fetchval(
            "SELECT count(*) FROM users WHERE id = $1", new_id
        ) == 1
        # Scheduler fan-out reads across all tenants.
        assert await conn.fetchval("SELECT count(*) FROM positions") >= 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_tenant_context_sees_only_own_rows(pg_dsn):
    conn = await _seed_and_connect_restricted(pg_dsn)
    try:
        await _set_guc(conn, TENANT_A)
        users = await conn.fetch("SELECT id FROM users")
        assert [str(r["id"]) for r in users] == [TENANT_A]
        positions = await conn.fetch("SELECT user_id FROM positions")
        assert {str(r["user_id"]) for r in positions} == {TENANT_A}
        # Writing another tenant's row must be rejected.
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                """
                INSERT INTO positions (user_id, ticker, quantity, avg_cost, currency, account)
                VALUES ($1, 'SPY', 1, 1, 'CAD', 'TFSA')
                """,
                uuid.UUID(TENANT_B),
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_no_context_sees_nothing(pg_dsn):
    # The Data API shape: a role with grants but no way to set the GUC.
    conn = await _seed_and_connect_restricted(pg_dsn)
    try:
        for table in ("users", "positions", "agent_runs", "model_calls",
                      "schema_migrations", "snaptrade_credentials"):
            assert await conn.fetchval(f"SELECT count(*) FROM {table}") == 0, (
                f"{table} leaked rows without a user context"
            )
    finally:
        await conn.close()
