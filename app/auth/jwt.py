"""Verify Supabase Auth JWTs.

Supabase projects now sign with **asymmetric** keys (ES256 / RS256) published at
the project's JWKS endpoint; the signature is verified with the public key, and
keys can rotate without a redeploy. HS256 (the legacy shared secret) is still
supported as a fallback. The algorithm is always taken from the token header but
constrained to what we actually configured — an asymmetric token is only ever
verified against JWKS, never a shared secret, so there is no algorithm-confusion
path. Verification itself is delegated to PyJWT (with ``cryptography``).

``verify_supabase_jwt`` is synchronous (the JWKS fetch is blocking but cached);
callers in async code run it via ``asyncio.to_thread``.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import jwt
from jwt import PyJWK

_ASYMMETRIC = frozenset({"ES256", "RS256"})
_JWKS_TTL_SECONDS = 600.0

# jwks_url -> (monotonic_ts, jwks_dict)
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class AuthError(Exception):
    """Raised when a token is malformed, badly signed, or expired."""


def _clock() -> float:
    return time.monotonic()


def cache_clear() -> None:
    _jwks_cache.clear()


def _fetch_jwks(jwks_url: str) -> dict[str, Any]:
    """Network seam (patched in tests): GET the JWKS document."""
    with urllib.request.urlopen(jwks_url, timeout=5) as resp:  # noqa: S310 - fixed https URL
        return json.loads(resp.read().decode())


def _get_jwks(jwks_url: str, *, force: bool = False) -> dict[str, Any]:
    cached = _jwks_cache.get(jwks_url)
    if not force and cached and _clock() - cached[0] < _JWKS_TTL_SECONDS:
        return cached[1]
    jwks = _fetch_jwks(jwks_url)
    _jwks_cache[jwks_url] = (_clock(), jwks)
    return jwks


def _match_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    keys = jwks.get("keys", []) if isinstance(jwks, dict) else []
    if kid is not None:
        for k in keys:
            if k.get("kid") == kid:
                return k
        return None
    return keys[0] if len(keys) == 1 else None


def _resolve_public_key(jwks_url: str, kid: str | None, alg: str) -> Any:
    """Find the signing key by kid, refetching once on a miss (key rotation)."""
    for force in (False, True):
        jwk = _match_jwk(_get_jwks(jwks_url, force=force), kid)
        if jwk is not None:
            jwk.setdefault("alg", alg)
            return PyJWK.from_dict(jwk).key
    raise AuthError("no matching signing key")


def _decode(token: str, key: Any, algorithms: list[str], audience: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=audience or None,
            leeway=30,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc


def verify_supabase_jwt(
    token: str,
    hs256_secret: str | None = None,
    *,
    jwks_url: str | None = None,
    audience: str = "authenticated",
) -> dict[str, Any]:
    """Return the token's claims if valid; raise ``AuthError`` otherwise."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("malformed token") from exc
    alg = header.get("alg")

    if alg in _ASYMMETRIC:
        if not jwks_url:
            raise AuthError("asymmetric token but no JWKS configured")
        key = _resolve_public_key(jwks_url, header.get("kid"), alg)
        return _decode(token, key, [alg], audience)

    if alg == "HS256":
        if not hs256_secret:
            raise AuthError("HS256 token but no secret configured")
        return _decode(token, hs256_secret, ["HS256"], audience)

    raise AuthError(f"unsupported algorithm: {alg}")


def jwks_url_for(supabase_url: str) -> str:
    return f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
