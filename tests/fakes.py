"""Shared test doubles: an in-memory Repo and a scripted Anthropic client.

The FakeRepo records the same rows the real Repo would write, so the loop's
observability behavior is asserted without a live Postgres. When a DATABASE_URL
is available, the same assertions can be re-run against the real Repo.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any


class FakeRepo:
    def __init__(self, positions: list[Any] | None = None) -> None:
        self.runs: dict[uuid.UUID, dict[str, Any]] = {}
        self.model_calls: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.digests: dict[date, SimpleNamespace] = {}
        self._digests_by_user: dict[tuple[Any, date], SimpleNamespace] = {}
        self.outbound: list[str] = []
        self._outbox: dict[uuid.UUID, SimpleNamespace] = {}
        self._positions = positions or []
        self.alerts: dict[str, SimpleNamespace] = {}
        self._snaptrade: dict[uuid.UUID, SimpleNamespace] = {}
        self._users_by_auth: dict[uuid.UUID, uuid.UUID] = {}
        self._users_by_id: dict[uuid.UUID, Any] = {}
        self._cost_override: dict[uuid.UUID, float] = {}
        self._chats_override: dict[uuid.UUID, int] = {}
        self._notification_channels: dict[tuple[Any, str], SimpleNamespace] = {}
        self._verification_codes: dict[uuid.UUID, SimpleNamespace] = {}
        self._news_items: list[SimpleNamespace] = []
        self._news_fingerprints: set[tuple] = set()
        self.job_heartbeats: dict[str, SimpleNamespace] = {}
        self.ticker_fundamentals: dict[str, SimpleNamespace] = {}

    def seed_user(self, user_id, *, plan="free", digest_enabled=True, email=None,
                  digest_tickers=None):
        self._users_by_id[user_id] = SimpleNamespace(
            id=user_id, auth_id=None, email=email, plan=plan,
            digest_enabled=digest_enabled, timezone="America/Toronto",
            digest_send_time="07:45", preferred_channel=None,
            digest_tickers=list(digest_tickers or []),
        )

    async def create_run(self, *, trigger, user_message, model, prompt_version,
                         user_id=None):
        run_id = uuid.uuid4()
        self.runs[run_id] = {
            "trigger": trigger,
            "user_message": user_message,
            "model": model,
            "prompt_version": prompt_version,
            "status": "running",
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
        }
        return run_id

    async def list_chat_runs(self, user_id, *, limit=10):
        rows = [
            SimpleNamespace(id=rid, **{
                "user_message": r.get("user_message"),
                "final_answer": r.get("final_answer"),
                "status": r.get("status"),
                "created_at": r.get("created_at"),
            })
            for rid, r in self.runs.items()
            if r.get("user_id") == user_id and r.get("trigger") == "chat"
        ]
        rows.sort(
            key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return rows[:limit]

    async def get_or_create_user(self, *, auth_id, email=None):
        if auth_id not in self._users_by_auth:
            uid = uuid.uuid4()
            self._users_by_auth[auth_id] = uid
            self._users_by_id[uid] = SimpleNamespace(
                id=uid, auth_id=auth_id, email=email, plan="free", digest_enabled=True,
                timezone="America/Toronto", digest_send_time="07:45",
                preferred_channel=None, digest_tickers=[],
            )
        return self._users_by_auth[auth_id]

    async def get_user(self, user_id):
        return self._users_by_id.get(user_id)

    async def update_user_preferences(self, user_id, *, timezone=None,
                                      digest_send_time=None, digest_enabled=None,
                                      digest_tickers=None):
        user = self._users_by_id.get(user_id)
        if user is None:
            return
        if timezone is not None:
            user.timezone = timezone
        if digest_send_time is not None:
            user.digest_send_time = digest_send_time
        if digest_enabled is not None:
            user.digest_enabled = digest_enabled
        if digest_tickers is not None:
            user.digest_tickers = list(digest_tickers)

    async def get_digest_tickers(self, user_id):
        user = self._users_by_id.get(user_id)
        if user is None:
            return []
        return list(getattr(user, "digest_tickers", []) or [])

    async def set_digest_tickers(self, user_id, tickers):
        user = self._users_by_id.get(user_id)
        if user is not None:
            user.digest_tickers = list(tickers)

    async def list_digest_recipients(self):
        from app.config import DEFAULT_USER_ID

        owner = uuid.UUID(DEFAULT_USER_ID)
        ids: list[uuid.UUID] = []
        for u in self._users_by_id.values():
            if not getattr(u, "digest_enabled", True):
                continue
            if any(p.user_id == u.id for p in getattr(self, "_position_rows", {}).values()):
                ids.append(u.id)
        if not ids and (self._positions or getattr(self, "_position_rows", {})):
            return [owner]
        return sorted(ids) if ids else []

    async def list_macro_recipients(self):
        return sorted(
            u.id for u in self._users_by_id.values()
            if getattr(u, "plan", "free") == "pro" and getattr(u, "digest_enabled", True)
        )

    async def list_anomaly_recipients(self):
        return sorted(await self.list_macro_recipients())

    async def monthly_cost_usd(self, user_id):
        if user_id in self._cost_override:
            return self._cost_override[user_id]
        return sum(
            float(r["cost_usd"])
            for r in self.runs.values()
            if r.get("user_id") == user_id and r.get("cost_usd") is not None
        )

    async def count_chats_today(self, user_id):
        if user_id in self._chats_override:
            return self._chats_override[user_id]
        return sum(
            1 for r in self.runs.values()
            if r.get("user_id") == user_id and r.get("trigger") == "chat"
        )

    async def finalize_run(self, run_id, **kwargs):
        self.runs[run_id].update(kwargs)

    def _run_ns(self, rid):
        r = self.runs[rid]
        return SimpleNamespace(
            id=rid,
            **{
                k: r.get(k)
                for k in (
                    "trigger", "user_message", "final_answer", "status",
                    "iterations", "input_tokens", "output_tokens", "cost_usd",
                    "latency_ms", "model", "prompt_version", "error_detail",
                    "created_at", "user_id",
                )
            },
        )

    async def list_runs(self, *, trigger=None, limit=50, user_id=None):
        rows = [
            self._run_ns(rid)
            for rid, r in self.runs.items()
            if (trigger is None or r.get("trigger") == trigger)
            and (user_id is None or r.get("user_id") == user_id)
        ]
        rows.sort(
            key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return rows[:limit]

    async def get_run_trajectory(self, run_id):
        if run_id not in self.runs:
            return None, [], []
        return self._run_ns(run_id), [], []

    async def log_model_call(self, *, run_id, iteration, request, response, usage):
        self.model_calls.append(
            {"run_id": run_id, "iteration": iteration, "request": request,
             "response": response, "usage": usage}
        )

    async def log_tool_call(self, *, run_id, iteration, tool_name, input, output,
                            is_error, latency_ms):
        self.tool_calls.append(
            {"run_id": run_id, "iteration": iteration, "tool_name": tool_name,
             "input": input, "output": output, "is_error": is_error,
             "latency_ms": latency_ms}
        )

    async def upsert_position(self, *, ticker, quantity, avg_cost, currency, account, user_id=None):
        from decimal import Decimal

        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        if not hasattr(self, "_position_rows"):
            self._position_rows: dict[tuple[Any, str, str], Any] = {}
        key = (uid, ticker, account)
        self._position_rows[key] = SimpleNamespace(
            ticker=ticker,
            quantity=Decimal(str(quantity)),
            avg_cost=Decimal(str(avg_cost)),
            currency=currency,
            account=account,
            user_id=uid,
        )

    async def prune_positions_except(self, keep: set[tuple[str, str]], *, user_id=None) -> int:
        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        if not hasattr(self, "_position_rows"):
            self._position_rows = {}
        stale = [
            k for k in self._position_rows
            if (k[1], k[2]) not in keep and k[0] == uid
        ]
        for k in stale:
            del self._position_rows[k]
        return len(stale)

    async def list_positions(self, *, user_id=None):
        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        if hasattr(self, "_position_rows") and self._position_rows:
            return [p for p in self._position_rows.values() if p.user_id == uid]
        if uid == uuid.UUID(DEFAULT_USER_ID):
            return self._positions
        return []

    async def list_distinct_tickers(self, user_ids=None):
        rows = list(getattr(self, "_position_rows", {}).values()) or self._positions
        return sorted({
            p.ticker for p in rows
            if user_ids is None or getattr(p, "user_id", None) in user_ids
        })

    async def upsert_digest(self, *, run_id, body, digest_date, user_id=None):
        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        row = SimpleNamespace(
            id=uuid.uuid4(),
            run_id=run_id, body=body, digest_date=digest_date,
            created_at=datetime.now(timezone.utc),
        )
        self._digests_by_user[(uid, digest_date)] = row
        if uid == uuid.UUID(DEFAULT_USER_ID):
            self.digests[digest_date] = row

    async def list_recent_digests(self, *, user_id=None, since=None, limit=50):
        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        rows = [
            r for (u, _), r in self._digests_by_user.items() if u == uid
        ]
        if since is not None:
            rows = [r for r in rows if r.created_at and r.created_at >= since]
        rows.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return rows[:limit]

    @staticmethod
    def news_fingerprint(url, headline):
        key = f"{url or ''}|{headline}".encode()
        return hashlib.sha256(key).hexdigest()

    async def insert_news_items_if_new(self, user_id, items, *, run_id=None):
        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        inserted = 0
        for item in items:
            fp = item.get("fingerprint") or self.news_fingerprint(
                item.get("url"), item["headline"]
            )
            if (uid, fp) in self._news_fingerprints:
                continue
            self._news_fingerprints.add((uid, fp))
            self._news_items.append(SimpleNamespace(
                id=uuid.uuid4(),
                user_id=uid,
                ticker=item["ticker"],
                headline=item["headline"],
                source=item.get("source"),
                url=item.get("url"),
                published_at=item.get("published_at"),
                summary=item.get("summary"),
                run_id=run_id,
                fingerprint=fp,
                created_at=datetime.now(timezone.utc),
            ))
            inserted += 1
        return inserted

    async def list_news_items(self, *, user_id=None, ticker=None, since=None, limit=50):
        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        rows = [n for n in self._news_items if n.user_id == uid]
        if ticker is not None:
            rows = [n for n in rows if n.ticker == ticker]
        if since is not None:
            rows = [n for n in rows if n.created_at >= since]
        rows.sort(key=lambda n: n.created_at, reverse=True)
        return rows[:limit]

    async def list_stored_news(
        self, user_id, *, ticker=None, kind="all", since=None,
        severity=None, category=None, limit=50,
    ):
        kinds = {k.strip() for k in kind.split(",") if k.strip()} or {"all"}
        if "all" in kinds:
            kinds = {"all"}
        out = []
        include_digest = ("all" in kinds or "digest" in kinds) and ticker is None
        include_alert = "all" in kinds or "alert" in kinds
        include_holding = "all" in kinds or "holding" in kinds

        if include_digest:
            for d in await self.list_recent_digests(user_id=user_id, since=since, limit=limit):
                out.append({
                    "id": str(d.id),
                    "kind": "digest",
                    "ticker": None,
                    "tickers": [],
                    "headline": f"Morning digest — {d.digest_date.isoformat()}",
                    "body": d.body,
                    "source": None,
                    "url": None,
                    "severity": None,
                    "category": None,
                    "published_at": None,
                    "created_at": d.created_at.isoformat(),
                })

        if include_alert:
            for a in await self.recent_alerts(limit=limit * 2, user_id=user_id):
                if since and a.created_at and a.created_at < since:
                    continue
                if severity and a.severity != severity:
                    continue
                if category and a.category != category:
                    continue
                tickers = a.tickers if isinstance(a.tickers, list) else []
                if ticker is not None and ticker not in tickers:
                    continue
                created = a.created_at or datetime.now(timezone.utc)
                out.append({
                    "id": str(a.id),
                    "kind": "alert",
                    "ticker": tickers[0] if len(tickers) == 1 else None,
                    "tickers": tickers,
                    "headline": a.headline,
                    "body": a.body,
                    "source": None,
                    "url": None,
                    "severity": a.severity,
                    "category": a.category,
                    "published_at": None,
                    "created_at": created.isoformat(),
                })

        if include_holding:
            for n in await self.list_news_items(
                user_id=user_id, ticker=ticker, since=since, limit=limit
            ):
                out.append({
                    "id": str(n.id),
                    "kind": "holding",
                    "ticker": n.ticker,
                    "tickers": [n.ticker],
                    "headline": n.headline,
                    "body": n.summary or "",
                    "source": n.source,
                    "url": n.url,
                    "severity": None,
                    "category": None,
                    "published_at": n.published_at.isoformat() if n.published_at else None,
                    "created_at": n.created_at.isoformat(),
                })

        out.sort(key=lambda x: x["created_at"], reverse=True)
        return out[:limit]

    async def get_digest(self, digest_date, *, user_id=None):
        from app.config import DEFAULT_USER_ID

        uid = user_id or uuid.UUID(DEFAULT_USER_ID)
        return self._digests_by_user.get((uid, digest_date))

    async def list_active_user_ids(self):
        from app.config import DEFAULT_USER_ID
        return [uuid.UUID(DEFAULT_USER_ID)]

    async def get_snaptrade_credentials(self, user_id):
        return self._snaptrade.get(user_id)

    async def save_snaptrade_credentials(self, *, user_id, snaptrade_user_id, user_secret_enc):
        self._snaptrade[user_id] = SimpleNamespace(
            user_id=user_id,
            snaptrade_user_id=snaptrade_user_id,
            user_secret_enc=user_secret_enc,
            connected_at=None,
            last_sync_at=None,
            last_sync_error=None,
        )

    async def delete_snaptrade_credentials(self, user_id):
        return self._snaptrade.pop(user_id, None) is not None

    async def delete_user_data(self, user_id):
        self.deleted_users = getattr(self, "deleted_users", [])
        self.deleted_users.append(user_id)
        run_ids = {
            rid for rid, r in self.runs.items() if r.get("user_id") == user_id
        }
        for rid in run_ids:
            del self.runs[rid]
        self.model_calls = [m for m in self.model_calls if m["run_id"] not in run_ids]
        self.tool_calls = [t for t in self.tool_calls if t["run_id"] not in run_ids]
        self._digests_by_user = {
            k: v for k, v in self._digests_by_user.items() if k[0] != user_id
        }
        self._news_items = [n for n in self._news_items if n.user_id != user_id]
        self._news_fingerprints = {
            k for k in self._news_fingerprints if k[0] != user_id
        }
        if hasattr(self, "_position_rows"):
            self._position_rows = {
                k: v for k, v in self._position_rows.items() if k[0] != user_id
            }
        self._notification_channels = {
            k: v for k, v in self._notification_channels.items() if k[0] != user_id
        }
        self._verification_codes = {
            k: v for k, v in self._verification_codes.items()
            if v.user_id != user_id
        }
        self._snaptrade.pop(user_id, None)
        user = self._users_by_id.pop(user_id, None)
        if user is not None and getattr(user, "auth_id", None) is not None:
            self._users_by_auth.pop(user.auth_id, None)

    async def update_snaptrade_status(self, user_id, *, connected_at=None, last_sync_at=None, last_sync_error=None):
        row = self._snaptrade.get(user_id)
        if row is None:
            return
        if connected_at is not None:
            row.connected_at = connected_at
        if last_sync_at is not None:
            row.last_sync_at = last_sync_at
        row.last_sync_error = last_sync_error

    async def create_alert_if_new(self, *, run_id, category, severity, headline,
                                  body, tickers, fingerprint, user_id=None):
        key = (user_id, fingerprint)
        if not hasattr(self, "_alert_keys"):
            self._alert_keys: set[tuple] = set()
        if key in self._alert_keys:
            return None
        self._alert_keys.add(key)
        alert_id = uuid.uuid4()
        self.alerts[fingerprint] = SimpleNamespace(
            id=alert_id, run_id=run_id, category=category, severity=severity,
            headline=headline, body=body, tickers=tickers, fingerprint=fingerprint,
            delivered=False, created_at=datetime.now(timezone.utc), user_id=user_id,
        )
        return alert_id

    async def recent_alerts_by_category(self, user_id, *, category, since):
        return [
            a for a in self.alerts.values()
            if a.category == category
            and getattr(a, "user_id", None) == user_id
            and a.created_at is not None
            and a.created_at >= since
        ]

    async def recent_alerts(self, *, limit=20, user_id=None):
        return list(self.alerts.values())[:limit]

    async def mark_alert_delivered(self, alert_id):
        for a in self.alerts.values():
            if a.id == alert_id:
                a.delivered = True

    async def enqueue_outbound(self, body, *, user_id=None, kind="message", subject=None):
        msg_id = uuid.uuid4()
        self.outbound.append(body)
        self._outbox[msg_id] = SimpleNamespace(
            id=msg_id,
            body=body,
            status="queued",
            attempts=0,
            channel=None,
            destination=None,
            payload={"kind": kind, **({"subject": subject} if subject else {})},
        )
        return msg_id

    # ---- job heartbeats (mirrors app/db/repo.py) -------------------------

    def _heartbeat(self, job_name):
        row = self.job_heartbeats.get(job_name)
        if row is None:
            row = SimpleNamespace(
                job_name=job_name, last_attempt_at=None, last_success_at=None,
                last_error=None, consecutive_failures=0,
            )
            self.job_heartbeats[job_name] = row
        return row

    async def record_job_attempt(self, job_name):
        self._heartbeat(job_name).last_attempt_at = datetime.now(timezone.utc)

    async def record_job_result(self, job_name, *, ok, error=None):
        row = self._heartbeat(job_name)
        if ok:
            row.last_success_at = datetime.now(timezone.utc)
            row.last_error = None
            row.consecutive_failures = 0
        else:
            row.last_error = error
            row.consecutive_failures += 1

    async def get_job_heartbeats(self):
        return list(self.job_heartbeats.values())

    # ---- ticker fundamentals (mirrors app/db/repo.py) --------------------

    async def get_ticker_fundamentals(self, tickers):
        return {
            t: row for t, row in self.ticker_fundamentals.items() if t in tickers
        }

    async def upsert_ticker_fundamentals(
        self, *, ticker, quote_type, data, fetch_error=None
    ):
        self.ticker_fundamentals[ticker] = SimpleNamespace(
            ticker=ticker,
            quote_type=quote_type,
            data=data,
            fetched_at=datetime.now(timezone.utc),
            fetch_error=fetch_error,
        )

    # ---- notification channels (mirrors app/db/repo.py) -----------------

    async def get_notification_channels(self, user_id):
        return sorted(
            (
                row
                for (uid, _), row in self._notification_channels.items()
                if uid == user_id
            ),
            key=lambda r: r.channel,
        )

    async def get_notification_channel(self, user_id, channel):
        return self._notification_channels.get((user_id, channel))

    async def set_opt_out_by_destination(self, *, channel, destination, opted_out):
        now = datetime.now(timezone.utc)
        updated = 0
        for (_, ch), row in self._notification_channels.items():
            if ch == channel and row.destination == destination:
                row.opted_out_at = now if opted_out else None
                row.updated_at = now
                updated += 1
        return updated

    async def upsert_notification_channel(
        self, user_id, *, channel, destination, consent=False
    ):
        now = datetime.now(timezone.utc)
        key = (user_id, channel)
        row = self._notification_channels.get(key)
        if row is None:
            row = SimpleNamespace(
                user_id=user_id,
                channel=channel,
                destination=destination,
                verified_at=None,
                opted_out_at=None,
                consent_at=None,
                updated_at=now,
            )
            self._notification_channels[key] = row
        elif row.destination != destination:
            row.destination = destination
            row.verified_at = None
            row.opted_out_at = None
        if consent:
            row.consent_at = now
        row.updated_at = now
        return row

    async def mark_channel_verified(self, user_id, channel):
        row = self._notification_channels.get((user_id, channel))
        if row is None:
            return False
        now = datetime.now(timezone.utc)
        row.verified_at = now
        row.opted_out_at = None
        row.updated_at = now
        return True

    async def set_preferred_channel(self, user_id, channel):
        user = self._users_by_id.get(user_id)
        if user is None:
            return False
        if channel is not None:
            row = self._notification_channels.get((user_id, channel))
            if row is None or row.verified_at is None or row.opted_out_at is not None:
                return False
        user.preferred_channel = channel
        return True

    async def count_verification_codes_since(
        self, since, *, destination=None, user_id=None
    ):
        return sum(
            1
            for c in self._verification_codes.values()
            if c.created_at >= since
            and (destination is None or c.destination == destination)
            and (user_id is None or c.user_id == user_id)
        )

    async def create_verification_code(
        self, user_id, *, channel, destination, code_hash, ttl_seconds=600
    ):
        now = datetime.now(timezone.utc)
        for c in self._verification_codes.values():
            if (
                c.user_id == user_id
                and c.channel == channel
                and c.consumed_at is None
                and c.expires_at > now
            ):
                c.consumed_at = now
        code_id = uuid.uuid4()
        self._verification_codes[code_id] = SimpleNamespace(
            id=code_id,
            user_id=user_id,
            channel=channel,
            destination=destination,
            code_hash=code_hash,
            expires_at=now + timedelta(seconds=ttl_seconds),
            attempts=0,
            consumed_at=None,
            created_at=now,
        )
        return code_id

    async def latest_verification_code(self, user_id, channel):
        now = datetime.now(timezone.utc)
        live = [
            c
            for c in self._verification_codes.values()
            if c.user_id == user_id
            and c.channel == channel
            and c.consumed_at is None
            and c.expires_at > now
        ]
        return max(live, key=lambda c: c.created_at) if live else None

    async def record_code_attempt(self, code_id):
        self._verification_codes[code_id].attempts += 1
        return self._verification_codes[code_id].attempts

    async def consume_verification_code(self, code_id):
        self._verification_codes[code_id].consumed_at = datetime.now(timezone.utc)

    @staticmethod
    def verification_code_from_sent(body: str) -> str:
        """Extract the 6-digit code from a fake adapter send body."""
        import re

        match = re.search(r"\b(\d{6})\b", body)
        assert match is not None, body
        return match.group(1)

    @staticmethod
    def hash_verification_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()


class ScriptedAnthropic:
    """Returns pre-canned responses from ``messages.create`` in sequence."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    @property
    def messages(self):
        return self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def tool_use_turn(tool_id, name, tool_input, *, in_tok=100, out_tok=20):
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }


def text_turn(text, *, in_tok=100, out_tok=20):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }
