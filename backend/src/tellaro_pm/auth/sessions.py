"""Device session management: refresh tokens, user-agent parsing, rate limiting."""

import hashlib
import logging
import re
import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from tellaro_pm.core.opensearch import DEVICE_SESSIONS_INDEX, CRUDService
from tellaro_pm.core.settings import settings

logger = logging.getLogger(__name__)

_sessions_crud = CRUDService(DEVICE_SESSIONS_INDEX)

# In-memory rate limiting store: ip -> list of timestamps
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


# ---------------------------------------------------------------------------
# User-Agent Parsing
# ---------------------------------------------------------------------------

_BROWSER_PATTERNS: list[tuple[str, str]] = [
    (r"Edg[eA]?/([\d.]+)", "Edge"),
    (r"OPR/([\d.]+)", "Opera"),
    (r"Vivaldi/([\d.]+)", "Vivaldi"),
    (r"Brave", "Brave"),
    (r"Chrome/([\d.]+)", "Chrome"),
    (r"Firefox/([\d.]+)", "Firefox"),
    (r"Version/([\d.]+).*Safari", "Safari"),
    (r"MSIE ([\d.]+)", "IE"),
    (r"Trident/.*rv:([\d.]+)", "IE"),
]

_OS_PATTERNS: list[tuple[str, str, str | None]] = [
    (r"Windows NT 10\.0", "Windows", "10/11"),
    (r"Windows NT 6\.3", "Windows", "8.1"),
    (r"Windows NT 6\.2", "Windows", "8"),
    (r"Windows NT 6\.1", "Windows", "7"),
    (r"Mac OS X ([\d_]+)", "macOS", None),
    (r"Android ([\d.]+)", "Android", None),
    (r"iPhone OS ([\d_]+)", "iOS", None),
    (r"iPad.*OS ([\d_]+)", "iPadOS", None),
    (r"CrOS", "ChromeOS", None),
    (r"Linux", "Linux", None),
]


def parse_user_agent(ua: str) -> dict[str, str]:
    """Extract browser, OS, and device type from a User-Agent string."""
    if not ua:
        return {
            "browser": "Unknown",
            "browser_version": "",
            "os": "Unknown",
            "os_version": "",
            "device_type": "unknown",
            "device_name": "Unknown Device",
        }

    # Browser
    browser = "Unknown"
    browser_version = ""
    for pattern, name in _BROWSER_PATTERNS:
        m = re.search(pattern, ua)
        if m:
            browser = name
            browser_version = m.group(1) if m.lastindex else ""
            break

    # OS
    os_name = "Unknown"
    os_version = ""
    for pattern, name, static_ver in _OS_PATTERNS:
        m = re.search(pattern, ua)
        if m:
            os_name = name
            if static_ver:
                os_version = static_ver
            elif m.lastindex:
                os_version = m.group(1).replace("_", ".")
            break

    # Device type
    if re.search(r"Mobile|Android.*Mobile|iPhone", ua):
        device_type = "mobile"
    elif re.search(r"iPad|Android(?!.*Mobile)|Tablet", ua):
        device_type = "tablet"
    else:
        device_type = "desktop"

    # Human-readable device name like "Chrome on Windows"
    device_name = f"{browser} on {os_name} {os_version}" if os_version else f"{browser} on {os_name}"

    return {
        "browser": browser,
        "browser_version": browser_version,
        "os": os_name,
        "os_version": os_version,
        "device_type": device_type,
        "device_name": device_name,
    }


# ---------------------------------------------------------------------------
# Refresh Token Helpers
# ---------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


# ---------------------------------------------------------------------------
# Device Session CRUD
# ---------------------------------------------------------------------------


def _find_session_by_device_id(user_id: str, device_id: str) -> dict[str, object] | None:
    """Find an existing active session for the same user and device ID."""
    query: dict[str, object] = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"user_id": user_id}},
                    {"term": {"device_id": device_id}},
                    {"term": {"is_active": True}},
                ]
            }
        }
    }
    return _sessions_crud.search_one(query)


def create_session(
    user_id: str,
    user_agent: str,
    ip_address: str,
    device_id: str | None = None,
) -> tuple[dict[str, object], str]:
    """Create or reuse a device session. Returns (session_doc, raw_refresh_token).

    Uses a persistent device_id cookie to identify the browser instance.
    If an active session exists for the same device_id, reuses it with a
    rotated refresh token. Otherwise creates a new session, enforcing the
    max device session limit by evicting the least recently used.
    """
    ua_info = parse_user_agent(user_agent)

    # Check for an existing active session from the same device
    if device_id:
        existing_session = _find_session_by_device_id(user_id, device_id)
        if existing_session is not None:
            # Reuse: rotate refresh token and update metadata
            refresh_token = generate_refresh_token()
            now = datetime.now(UTC).isoformat()
            update_fields: dict[str, object] = {
                "refresh_token_hash": _hash_token(refresh_token),
                "browser": ua_info["browser"],
                "browser_version": ua_info["browser_version"],
                "os": ua_info["os"],
                "os_version": ua_info["os_version"],
                "device_name": ua_info["device_name"],
                "device_type": ua_info["device_type"],
                "last_ip": ip_address,
                "last_used_at": now,
            }
            _sessions_crud.update(str(existing_session["id"]), update_fields)
            existing_session.update(update_fields)
            return existing_session, refresh_token

    # No matching session — create a new one
    if not device_id:
        device_id = str(uuid4())

    existing = list_user_sessions(user_id)
    active = [s for s in existing if s.get("is_active")]
    if len(active) >= settings.MAX_DEVICE_SESSIONS:
        # Evict the oldest (least recently used)
        active.sort(key=lambda s: str(s.get("last_used_at", "")))
        to_evict = active[0]
        revoke_session(str(to_evict["id"]), user_id)

    refresh_token = generate_refresh_token()
    now = datetime.now(UTC).isoformat()
    session_id = str(uuid4())

    doc: dict[str, object] = {
        "id": session_id,
        "user_id": user_id,
        "device_id": device_id,
        "refresh_token_hash": _hash_token(refresh_token),
        "device_name": ua_info["device_name"],
        "browser": ua_info["browser"],
        "browser_version": ua_info["browser_version"],
        "os": ua_info["os"],
        "os_version": ua_info["os_version"],
        "device_type": ua_info["device_type"],
        "ip_address": ip_address,
        "last_ip": ip_address,
        "is_active": True,
        "last_used_at": now,
        "created_at": now,
    }
    _sessions_crud.create(session_id, doc)
    return doc, refresh_token


def refresh_session(
    refresh_token: str,
    ip_address: str,
) -> dict[str, object] | None:
    """Validate a refresh token, rotate it, and return the updated session.

    Returns None if the token is invalid or the session is revoked.
    The new raw refresh token is added to the returned dict as '_new_refresh_token'.
    """
    token_hash = _hash_token(refresh_token)
    query: dict[str, object] = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"refresh_token_hash": token_hash}},
                    {"term": {"is_active": True}},
                ]
            }
        }
    }
    session = _sessions_crud.search_one(query)
    if session is None:
        return None

    # Check refresh token expiry
    created_at = session.get("last_used_at") or session.get("created_at")
    if isinstance(created_at, str):
        try:
            last_used = datetime.fromisoformat(created_at)
            if datetime.now(UTC) - last_used > timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS):
                # Expired — revoke
                revoke_session(str(session["id"]), str(session["user_id"]))
                return None
        except ValueError:
            pass

    # Rotate refresh token
    new_refresh_token = generate_refresh_token()
    now = datetime.now(UTC).isoformat()
    update_fields: dict[str, object] = {
        "refresh_token_hash": _hash_token(new_refresh_token),
        "last_used_at": now,
        "last_ip": ip_address,
    }
    _sessions_crud.update(str(session["id"]), update_fields)
    session.update(update_fields)
    session["_new_refresh_token"] = new_refresh_token
    return session


def list_user_sessions(user_id: str) -> list[dict[str, object]]:
    """List all sessions for a user, sorted by last_used_at descending."""
    query: dict[str, object] = {
        "query": {"term": {"user_id": user_id}},
        "sort": [{"last_used_at": {"order": "desc"}}],
    }
    return _sessions_crud.search(query, size=50)


def revoke_session(session_id: str, user_id: str) -> bool:
    """Revoke a specific device session (must belong to the user)."""
    session = _sessions_crud.get(session_id)
    if session is None or str(session.get("user_id")) != user_id:
        return False
    _sessions_crud.update(session_id, {"is_active": False})
    return True


def revoke_all_sessions(user_id: str, except_session_id: str | None = None) -> int:
    """Revoke all sessions for a user, optionally keeping one."""
    sessions = list_user_sessions(user_id)
    count = 0
    for s in sessions:
        sid = str(s["id"])
        if s.get("is_active") and sid != except_session_id:
            _sessions_crud.update(sid, {"is_active": False})
            count += 1
    return count


# ---------------------------------------------------------------------------
# IP Rate Limiting (in-memory, per-process)
# ---------------------------------------------------------------------------


def check_rate_limit(ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = datetime.now(UTC).timestamp()
    window = settings.AUTH_RATE_LIMIT_WINDOW
    max_attempts = settings.AUTH_RATE_LIMIT_MAX

    # Clean old entries
    timestamps = _rate_limit_store[ip]
    cutoff = now - window
    _rate_limit_store[ip] = [t for t in timestamps if t > cutoff]

    if len(_rate_limit_store[ip]) >= max_attempts:
        return False

    _rate_limit_store[ip].append(now)
    return True


def get_rate_limit_remaining(ip: str) -> int:
    """Return how many attempts remain in the current window."""
    now = datetime.now(UTC).timestamp()
    cutoff = now - settings.AUTH_RATE_LIMIT_WINDOW
    recent = [t for t in _rate_limit_store.get(ip, []) if t > cutoff]
    return max(0, settings.AUTH_RATE_LIMIT_MAX - len(recent))
