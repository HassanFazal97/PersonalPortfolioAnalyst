"""Tests for SnapTrade personal-key signature + mode detection."""

import hashlib
import hmac
import json
from base64 import b64encode

from app.config import Settings
from app.integrations.snaptrade.client import is_personal_key_mode
from app.integrations.snaptrade.personal_client import compute_request_signature


def test_compute_request_signature_matches_docs_shape():
    query = "clientId=PASSIVTEST&timestamp=1635790389"
    body = {"userId": "new_user_123"}
    sig = compute_request_signature(
        path="/snapTrade/registerUser",
        query=query,
        consumer_key="YOUR_CONSUMER_KEY",
        body=body,
    )
    expected_object = {
        "content": body,
        "path": "/api/v1/snapTrade/registerUser",
        "query": query,
    }
    expected_content = json.dumps(expected_object, separators=(",", ":"), sort_keys=True)
    expected = b64encode(
        hmac.new(
            b"YOUR_CONSUMER_KEY",
            expected_content.encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    assert sig == expected


def test_is_personal_key_mode_auto_without_secret():
    settings = Settings(
        SNAPTRADE_CLIENT_ID="x",
        SNAPTRADE_CONSUMER_KEY="y",
        SNAPTRADE_USER_SECRET="",
        SNAPTRADE_AUTH_MODE="auto",
    )
    assert is_personal_key_mode(settings) is True


def test_is_personal_key_mode_commercial_with_secret():
    settings = Settings(
        SNAPTRADE_CLIENT_ID="x",
        SNAPTRADE_CONSUMER_KEY="y",
        SNAPTRADE_USER_SECRET="secret",
        SNAPTRADE_AUTH_MODE="commercial",
    )
    assert is_personal_key_mode(settings) is False
