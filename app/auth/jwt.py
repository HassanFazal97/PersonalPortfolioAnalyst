"""Minimal, safe verification of Supabase Auth JWTs (HS256).

No third-party dependency — HS256 is HMAC-SHA256 over ``header.payload``. The
algorithm is hard-pinned so a token cannot downgrade us to ``none`` or trick us
into RS/HS confusion; the signature is compared in constant time; and exp/nbf/
aud/sub are validated. Supabase signs project JWTs with the project JWT secret
(Settings → API → JWT Secret) by default, which is the ``secret`` here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class AuthError(Exception):
    """Raised when a token is malformed, unsigned-correctly, or expired."""


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_supabase_jwt(
    token: str,
    secret: str,
    *,
    audience: str = "authenticated",
    leeway_seconds: int = 30,
) -> dict[str, Any]:
    """Return the token's claims if valid; raise ``AuthError`` otherwise."""
    if not secret:
        raise AuthError("JWT secret not configured")
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("malformed token")
    header_b64, payload_b64, sig_b64 = parts

    try:
        header = json.loads(_b64url_decode(header_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("bad header") from exc
    # Hard-pin the algorithm — never trust the header to select the scheme.
    if header.get("alg") != "HS256":
        raise AuthError("unsupported algorithm")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        actual = _b64url_decode(sig_b64)
    except ValueError as exc:
        raise AuthError("bad signature encoding") from exc
    if not hmac.compare_digest(expected, actual):
        raise AuthError("signature mismatch")

    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("bad payload") from exc

    now = int(time.time())
    exp = claims.get("exp")
    if exp is not None and now > int(exp) + leeway_seconds:
        raise AuthError("token expired")
    nbf = claims.get("nbf")
    if nbf is not None and now + leeway_seconds < int(nbf):
        raise AuthError("token not yet valid")
    if audience:
        aud = claims.get("aud")
        auds = aud if isinstance(aud, list) else [aud]
        if audience not in auds:
            raise AuthError("bad audience")
    if not claims.get("sub"):
        raise AuthError("missing subject")

    return claims
