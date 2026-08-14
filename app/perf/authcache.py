"""In-process caches for the per-request auth hot path.

Every authenticated API call used to pay (a) full JWT signature verification
and (b) a ``get_or_create_user`` DB query. Both results are stable for the
lifetime of a token / an account, so we cache them in module-level dicts —
the same single-process pattern as the quote caches in app/tools/market.py.
When the deployment goes multi-process these swap for a shared backend
behind the same three functions.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import OrderedDict
from time import time as _now

# auth_id -> user_id. The mapping is insert-only (get_or_create_user never
# reassigns), so entries need no TTL — only account deletion removes one.
_user_ids: OrderedDict[uuid.UUID, uuid.UUID] = OrderedDict()
_USER_IDS_MAX = 2048

# sha256(token) -> (auth_id, email, exp). Valid until the token's own expiry,
# so a browser session verifies each ~1h token once instead of per API call.
_verified_tokens: OrderedDict[str, tuple[uuid.UUID, str | None, float]] = OrderedDict()
_VERIFIED_MAX = 4096


def get_user_id(auth_id: uuid.UUID) -> uuid.UUID | None:
    return _user_ids.get(auth_id)


def put_user_id(auth_id: uuid.UUID, user_id: uuid.UUID) -> None:
    _user_ids[auth_id] = user_id
    _user_ids.move_to_end(auth_id)
    while len(_user_ids) > _USER_IDS_MAX:
        _user_ids.popitem(last=False)


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_verified(token: str) -> tuple[uuid.UUID, str | None] | None:
    entry = _verified_tokens.get(_token_key(token))
    if entry is None:
        return None
    auth_id, email, exp = entry
    if _now() >= exp:
        _verified_tokens.pop(_token_key(token), None)
        return None
    return auth_id, email


def put_verified(token: str, auth_id: uuid.UUID, email: str | None, exp: float) -> None:
    # Refuse tokens without a sane expiry (verify_supabase_jwt enforces exp,
    # but belt-and-braces: never cache something we can't age out).
    if exp <= _now():
        return
    key = _token_key(token)
    _verified_tokens[key] = (auth_id, email, exp)
    _verified_tokens.move_to_end(key)
    while len(_verified_tokens) > _VERIFIED_MAX:
        _verified_tokens.popitem(last=False)


def evict_user(auth_id: uuid.UUID | None) -> None:
    """Drop cached identity on account deletion (tokens age out on exp)."""
    if auth_id is not None:
        _user_ids.pop(auth_id, None)


def evict_tokens_for(auth_id: uuid.UUID | None) -> None:
    """Drop every cached verification for an auth uid, on account deletion.

    Without this, a token verified before the delete keeps serving cached claims
    for its remaining ~1h and never re-enters full verification — which is where
    the token's ``iat`` comes from, and ``iat`` is what lets provisioning tell a
    pre-delete token from a genuine new sign-in (migration 029). Evicting forces
    the next request to re-verify and produce one. A linear scan is fine: the
    dict is capped at ``_VERIFIED_MAX`` and deletion is rare."""
    if auth_id is None:
        return
    for key in [k for k, (aid, _, _) in _verified_tokens.items() if aid == auth_id]:
        _verified_tokens.pop(key, None)


def cache_clear() -> None:
    """Test hook, mirroring app/tools/market.py's cache_clear()."""
    _user_ids.clear()
    _verified_tokens.clear()
