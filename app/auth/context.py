"""Per-request current-user context.

The authenticated ``user_id`` is stashed in a ContextVar by the auth dependency
and read by the DB layer (``repo``) to set the ``app.current_user_id`` Postgres
GUC that RLS policies filter on. ContextVars are per-task, so concurrent
requests never see each other's user. Background jobs leave it unset and fall
back to the owner (see ``repo._apply_rls_user``).
"""

from __future__ import annotations

import contextvars
import uuid

_current_user_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "current_user_id", default=None
)


def set_current_user_id(user_id: uuid.UUID | None) -> None:
    _current_user_id.set(user_id)


def get_current_user_id() -> uuid.UUID | None:
    return _current_user_id.get()
