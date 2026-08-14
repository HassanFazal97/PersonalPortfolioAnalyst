"""ExpoPushAdapter: ticket handling, permanence, and the dry-run guard."""

import httpx
import pytest

from app.delivery.adapters.expo_push import ExpoPushAdapter

TOKEN = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_dry_run_never_calls_expo():
    """The fan-out ships log-only first; a dry run that still hit the network
    would defeat the entire point of the flag."""

    def explode(request):  # pragma: no cover - must never run
        raise AssertionError("dry run must not make a request")

    adapter = ExpoPushAdapter(dry_run=True, transport=_transport(explode))
    result = await adapter.send(TOKEN, "body", {"kind": "digest"})

    assert result.ok
    assert result.provider_message_id == "dry-run"


@pytest.mark.asyncio
async def test_sends_title_body_and_data():
    seen = {}

    def handler(request):
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"data": {"status": "ok", "id": "ticket-1"}})

    adapter = ExpoPushAdapter(transport=_transport(handler))
    result = await adapter.send(
        TOKEN,
        "Portfolio down 0.6%",
        {"kind": "digest", "title": "Your digest", "deep_link": "cirvia://digest"},
    )

    assert result.ok
    assert result.provider_message_id == "ticket-1"
    assert seen["to"] == TOKEN
    assert seen["title"] == "Your digest"
    # The real payload rides in `data`, not the body — a push is a pointer.
    assert seen["data"]["deep_link"] == "cirvia://digest"
    assert seen["data"]["kind"] == "digest"


@pytest.mark.asyncio
async def test_body_is_truncated():
    seen = {}

    def handler(request):
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"data": {"status": "ok"}})

    adapter = ExpoPushAdapter(transport=_transport(handler))
    await adapter.send(TOKEN, "x" * 500, {"kind": "digest"})

    assert len(seen["body"]) <= 150


@pytest.mark.asyncio
async def test_device_not_registered_is_permanent():
    """Maps onto the dispatcher's permanent flag so the queue stops burning
    attempts on an uninstalled app."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "status": "error",
                    "message": "not a registered device",
                    "details": {"error": "DeviceNotRegistered"},
                }
            },
        )

    adapter = ExpoPushAdapter(transport=_transport(handler))
    result = await adapter.send(TOKEN, "body", {})

    assert not result.ok
    assert result.permanent


@pytest.mark.asyncio
async def test_a_200_with_an_error_ticket_is_not_success():
    """Expo answers 200 with a per-message ticket that can still have failed —
    treating the status code as delivery would silently drop notifications."""

    def handler(request):
        return httpx.Response(
            200,
            json={"data": {"status": "error", "message": "MessageTooBig", "details": {}}},
        )

    adapter = ExpoPushAdapter(transport=_transport(handler))
    result = await adapter.send(TOKEN, "body", {})

    assert not result.ok
    assert not result.permanent  # unknown code: worth a retry


@pytest.mark.asyncio
async def test_ticket_list_form_is_accepted():
    def handler(request):
        return httpx.Response(200, json={"data": [{"status": "ok", "id": "t-9"}]})

    adapter = ExpoPushAdapter(transport=_transport(handler))
    result = await adapter.send(TOKEN, "body", {})

    assert result.ok
    assert result.provider_message_id == "t-9"


@pytest.mark.asyncio
async def test_server_error_is_retryable_client_error_is_not():
    adapter5 = ExpoPushAdapter(
        transport=_transport(lambda r: httpx.Response(503, text="nope"))
    )
    assert not (await adapter5.send(TOKEN, "b", {})).permanent

    adapter4 = ExpoPushAdapter(
        transport=_transport(lambda r: httpx.Response(400, text="bad"))
    )
    assert (await adapter4.send(TOKEN, "b", {})).permanent


@pytest.mark.asyncio
async def test_non_expo_token_is_rejected_permanently():
    adapter = ExpoPushAdapter(
        transport=_transport(lambda r: httpx.Response(200, json={"data": {}}))
    )
    result = await adapter.send("+14165551234", "body", {})

    assert not result.ok
    assert result.permanent


@pytest.mark.asyncio
async def test_transport_failure_is_retryable():
    def boom(request):
        raise httpx.ConnectError("down")

    adapter = ExpoPushAdapter(transport=_transport(boom))
    result = await adapter.send(TOKEN, "body", {})

    assert not result.ok
    assert not result.permanent


@pytest.mark.asyncio
async def test_access_token_is_sent_when_configured():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": {"status": "ok"}})

    adapter = ExpoPushAdapter(access_token="secret", transport=_transport(handler))
    await adapter.send(TOKEN, "body", {})

    assert seen["auth"] == "Bearer secret"
