"""Provisioning token management for agent daemons.

Provisioning tokens are one-time-use tokens that allow an agent binary to
authenticate and register itself. The flow:
  1. User generates a provisioning token in the UI
  2. User provides it to the agent binary at startup
  3. Agent exchanges the token for a short-lived agent JWT
  4. Agent uses the JWT for WebSocket connection and API calls
"""

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import uuid4

from tellaro_pm.core.opensearch import PROVISIONING_TOKENS_INDEX, CRUDService

_tokens_crud = CRUDService(PROVISIONING_TOKENS_INDEX)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_provisioning_token(
    user_id: str,
    label: str = "",
    expires_hours: int = 24,
) -> tuple[dict[str, object], str]:
    """Create a provisioning token. Returns (doc, raw_token)."""
    raw_token = secrets.token_urlsafe(48)
    token_id = str(uuid4())
    now = datetime.now(UTC).isoformat()

    doc: dict[str, object] = {
        "id": token_id,
        "user_id": user_id,
        "label": label,
        "token_hash": _hash_token(raw_token),
        "expires_hours": expires_hours,
        "is_used": False,
        "is_revoked": False,
        "created_at": now,
    }
    _tokens_crud.create(token_id, doc)
    return doc, raw_token


def exchange_provisioning_token(raw_token: str) -> dict[str, object] | None:
    """Validate and consume a provisioning token. Returns the token doc or None."""
    token_hash = _hash_token(raw_token)
    query: dict[str, object] = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"token_hash": token_hash}},
                    {"term": {"is_used": False}},
                    {"term": {"is_revoked": False}},
                ]
            }
        }
    }
    doc = _tokens_crud.search_one(query)
    if doc is None:
        return None

    # Check expiry
    created_at = doc.get("created_at")
    raw_expires = doc.get("expires_hours", 24)
    expires_hours = int(raw_expires) if isinstance(raw_expires, (int, str, float)) else 24
    if isinstance(created_at, str):
        try:
            created = datetime.fromisoformat(created_at)
            from datetime import timedelta

            if datetime.now(UTC) - created > timedelta(hours=expires_hours):
                # Expired
                _tokens_crud.update(str(doc["id"]), {"is_revoked": True})
                return None
        except ValueError:
            pass

    # Mark as used
    _tokens_crud.update(
        str(doc["id"]),
        {
            "is_used": True,
            "used_at": datetime.now(UTC).isoformat(),
        },
    )
    return doc


def list_provisioning_tokens(user_id: str) -> list[dict[str, object]]:
    """List all provisioning tokens for a user."""
    query: dict[str, object] = {
        "query": {"term": {"user_id": user_id}},
        "sort": [{"created_at": {"order": "desc"}}],
    }
    return _tokens_crud.search(query, size=100)


def revoke_provisioning_token(token_id: str, user_id: str) -> bool:
    """Revoke a provisioning token (must belong to user)."""
    doc = _tokens_crud.get(token_id)
    if doc is None or str(doc.get("user_id")) != user_id:
        return False
    _tokens_crud.update(token_id, {"is_revoked": True})
    return True
