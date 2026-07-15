"""Anomaly orchestrator: fan-out, cooldown, narration fallback, delivery.

Modeled on tests/test_macro.py. The global detector pass is monkeypatched at
app.agent.anomaly.orchestrator.scan_tickers (detector math has its own tests
in test_anomaly_scanner.py); the Anthropic client is the scripted fake.
"""

import json
import uuid

import app.agent.anomaly.orchestrator as orch
from app.agent.anomaly.scanner import AnomalyFlag
from app.agent.anomaly.synthesis import CATEGORY
from app.config import DEFAULT_USER_ID, Settings
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn

OWNER = uuid.UUID(DEFAULT_USER_ID)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _flag(ticker, detector="zscore", direction="down", severity=0.65, score=-3.9):
    return AnomalyFlag(
        ticker=ticker, detector=detector, direction=direction,
        severity=severity, score=score, explanation=f"|z|=3.9 > k=3.0 ({ticker})",
        last_close=100.0, day_change_pct=-4.5,
    )


def _patch_scan(monkeypatch, flags_by_ticker, settings=None):
    async def fake_scan(tickers, *, settings):
        return {t: f for t, f in flags_by_ticker.items() if t in tickers}

    monkeypatch.setattr(orch, "scan_tickers", fake_scan)
    monkeypatch.setattr(orch, "get_settings", lambda: settings or _settings())


def _narration(headline="Unusual moves in your holdings", body="NVDA fell 4.5% today."):
    return text_turn(json.dumps({"headline": headline, "body": body}))


async def _seed_positions(repo, user_id, tickers):
    for t in tickers:
        await repo.upsert_position(
            ticker=t, quantity=10, avg_cost=50, currency="CAD",
            account="TFSA", user_id=user_id,
        )


async def test_one_alert_covers_multiple_flagged_holdings(monkeypatch):
    repo = FakeRepo()
    await _seed_positions(repo, OWNER, ["NVDA", "RY.TO", "QUIET"])
    _patch_scan(monkeypatch, {
        "NVDA": [_flag("NVDA")],
        "RY.TO": [_flag("RY.TO", detector="cusum", severity=0.7)],
        "OTHER": [_flag("OTHER")],  # not held — must not leak into the alert
    })
    client = ScriptedAnthropic([_narration()])

    result = await orch.run_anomaly_scan(repo, client=client)

    assert result["status"] == "completed"
    assert len(result["alerts"]) == 1
    alert = next(iter(repo.alerts.values()))
    assert alert.category == CATEGORY
    assert alert.tickers == ["NVDA", "RY.TO"]
    assert len(repo.outbound) == 1
    assert alert.delivered
    # combined severity: noisy_or(0.65, 0.7) = 0.895 -> high
    assert alert.severity == "high"
    # narration payload contained only held tickers' flags
    payload = json.loads(client.calls[0]["messages"][0]["content"])
    assert {f["ticker"] for f in payload["flags"]} == {"NVDA", "RY.TO"}


async def test_same_day_rerun_dedups_by_fingerprint(monkeypatch):
    repo = FakeRepo()
    await _seed_positions(repo, OWNER, ["NVDA"])
    flags = {"NVDA": [_flag("NVDA")]}
    # cooldown 0 so the second run reaches the fingerprint check
    settings = _settings(ANOMALY_COOLDOWN_DAYS="0")
    _patch_scan(monkeypatch, flags, settings=settings)

    await orch.run_anomaly_scan(repo, client=ScriptedAnthropic([_narration()]))
    second = await orch.run_anomaly_scan(repo, client=ScriptedAnthropic([_narration()]))

    assert second["alerts"] == []  # same-day duplicate silently skipped
    assert len(repo.alerts) == 1
    assert len(repo.outbound) == 1


async def test_cooldown_suppresses_recent_ticker(monkeypatch):
    repo = FakeRepo()
    await _seed_positions(repo, OWNER, ["NVDA"])
    # NVDA alerted yesterday (FakeRepo stamps created_at=now)
    await repo.create_alert_if_new(
        run_id=None, category=CATEGORY, severity="medium",
        headline="prior", body="prior", tickers=["NVDA"],
        fingerprint=f"{CATEGORY}:2026-07-12:aaaa", user_id=OWNER,
    )
    _patch_scan(monkeypatch, {"NVDA": [_flag("NVDA")]})
    client = ScriptedAnthropic([])  # must not be called at all

    result = await orch.run_anomaly_scan(repo, client=client)

    assert result["status"] == "no_anomalies"
    assert client.calls == []
    assert len(repo.outbound) == 0


async def test_narration_failure_falls_back_and_still_alerts(monkeypatch):
    repo = FakeRepo()
    await _seed_positions(repo, OWNER, ["NVDA"])
    _patch_scan(monkeypatch, {"NVDA": [_flag("NVDA")]})
    client = ScriptedAnthropic([text_turn("not json at all")])

    result = await orch.run_anomaly_scan(repo, client=client)

    assert result["status"] == "completed"
    assert len(result["alerts"]) == 1
    alert = next(iter(repo.alerts.values()))
    assert alert.headline == "Unusual move in NVDA"  # deterministic template
    assert len(repo.outbound) == 1


async def test_client_exception_falls_back_and_still_alerts(monkeypatch):
    repo = FakeRepo()
    await _seed_positions(repo, OWNER, ["NVDA"])
    _patch_scan(monkeypatch, {"NVDA": [_flag("NVDA")]})
    client = ScriptedAnthropic([])  # .create pops from empty list -> raises

    result = await orch.run_anomaly_scan(repo, client=client)

    assert result["status"] == "completed"
    assert len(result["alerts"]) == 1
    assert len(repo.outbound) == 1


async def test_fanout_includes_owner_and_pro_skips_free_and_capped(monkeypatch):
    repo = FakeRepo()
    pro = uuid.uuid4()
    capped = uuid.uuid4()
    free = uuid.uuid4()
    repo.seed_user(pro, plan="pro")
    repo.seed_user(capped, plan="pro")
    repo.seed_user(free, plan="free")
    repo._cost_override[capped] = 99.0
    await _seed_positions(repo, OWNER, ["NVDA"])
    await _seed_positions(repo, pro, ["NVDA"])
    await _seed_positions(repo, capped, ["NVDA"])
    await _seed_positions(repo, free, ["NVDA"])
    _patch_scan(monkeypatch, {"NVDA": [_flag("NVDA")]})
    client = ScriptedAnthropic([_narration(), _narration()])  # owner + pro

    results = await orch.run_anomaly_scans_for_all(repo, client=client)

    by_user = {r["user_id"]: r for r in results if "user_id" in r}
    assert by_user[str(OWNER)]["status"] == "completed"
    assert by_user[str(pro)]["status"] == "completed"
    assert by_user[str(capped)]["status"] == "skipped_cost_cap"
    assert str(free) not in by_user  # free tier is not a recipient
    assert len(repo.outbound) == 2


async def test_no_flags_skips_synthesis_entirely(monkeypatch):
    repo = FakeRepo()
    await _seed_positions(repo, OWNER, ["NVDA"])
    _patch_scan(monkeypatch, {})
    client = ScriptedAnthropic([])

    results = await orch.run_anomaly_scans_for_all(repo, client=client)

    assert len(results) == 1  # just the scan summary row
    assert results[0]["tickers_flagged"] == 0
    assert client.calls == []


async def test_scan_run_is_recorded_with_zero_cost(monkeypatch):
    repo = FakeRepo()
    await _seed_positions(repo, OWNER, ["NVDA"])
    _patch_scan(monkeypatch, {"NVDA": [_flag("NVDA")]})

    await orch.run_anomaly_scan(repo, client=ScriptedAnthropic([_narration()]))

    scan_runs = [r for r in repo.runs.values()
                 if r["trigger"] == "anomaly" and r["model"] == "none"]
    assert len(scan_runs) == 1
    assert scan_runs[0]["status"] == "completed"
    assert scan_runs[0]["cost_usd"] == 0.0
