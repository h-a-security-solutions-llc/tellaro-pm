"""Auth API router: login, OAuth, OIDC, refresh, device sessions, domain discovery."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from tellaro_pm.auth.schemas import (
    AuthDiscoveryRequest,
    AuthDiscoveryResponse,
    AuthDomainCreate,
    AuthDomainResponse,
    AuthDomainUpdate,
    DeviceSessionResponse,
    LoginRequest,
    OAuthCallbackRequest,
    RefreshRequest,
    TokenResponse,
)
from tellaro_pm.auth.service import auth_service
from tellaro_pm.auth.sessions import (
    check_rate_limit,
    create_session,
    get_rate_limit_remaining,
    list_user_sessions,
    refresh_session,
    revoke_all_sessions,
    revoke_session,
)
from tellaro_pm.core.dependencies import get_current_user, require_admin
from tellaro_pm.core.settings import settings
from tellaro_pm.users.schemas import UserResponse
from tellaro_pm.users.service import user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
AdminUser = Annotated[dict[str, object], Depends(require_admin)]


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


_DEVICE_COOKIE = "tellaro_device_id"
_DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


def _build_token_response(user: dict[str, object], request: Request, response: Response) -> TokenResponse:
    """Create a device session and return access + refresh tokens.

    Reads the tellaro_device_id cookie to identify the device. If no cookie
    exists, a new device ID is generated and set as a persistent HTTP-only cookie.
    """
    ua = request.headers.get("user-agent", "")
    ip = _get_client_ip(request)
    device_id = request.cookies.get(_DEVICE_COOKIE)
    session_doc, raw_refresh = create_session(str(user["id"]), ua, ip, device_id)

    # Set/refresh the device cookie
    actual_device_id = str(session_doc.get("device_id", ""))
    response.set_cookie(
        key=_DEVICE_COOKIE,
        value=actual_device_id,
        max_age=_DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )

    session_id = str(session_doc["id"])
    access_token = auth_service.create_access_token_for_user(user, session_id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _enforce_rate_limit(request: Request) -> None:
    ip = _get_client_ip(request)
    if not check_rate_limit(ip):
        remaining = get_rate_limit_remaining(ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again later. ({remaining} remaining)",
            headers={"Retry-After": str(settings.AUTH_RATE_LIMIT_WINDOW)},
        )


# ------------------------------------------------------------------
# Discovery
# ------------------------------------------------------------------


@router.post("/discover", response_model=AuthDiscoveryResponse)
async def discover_provider(body: AuthDiscoveryRequest) -> AuthDiscoveryResponse:
    """Given an email, return which auth provider handles this domain."""
    provider, redirect_url = await auth_service.discover_auth_provider(body.email)
    return AuthDiscoveryResponse(provider=provider, redirect_url=redirect_url)


# ------------------------------------------------------------------
# Local login
# ------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> TokenResponse:
    _enforce_rate_limit(request)
    user = auth_service.authenticate_local(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return _build_token_response(user, request, response)


# ------------------------------------------------------------------
# Token refresh
# ------------------------------------------------------------------


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, request: Request) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    ip = _get_client_ip(request)
    session = refresh_session(body.refresh_token, ip)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user_id = str(session["user_id"])
    user = user_service.get_by_id(user_id)
    if user is None or not user.get("is_active", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    new_refresh = str(session["_new_refresh_token"])
    access_token = auth_service.create_access_token_for_user(user, str(session["id"]))
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ------------------------------------------------------------------
# GitHub OAuth
# ------------------------------------------------------------------


@router.get("/github/authorize")
async def github_authorize() -> dict[str, str]:
    url = auth_service.github_authorize_url()
    return {"authorize_url": url}


@router.post("/github/callback", response_model=TokenResponse)
async def github_callback(body: OAuthCallbackRequest, request: Request, response: Response) -> TokenResponse:
    try:
        access_token = await auth_service.github_exchange_code(body.code)
        user_info = await auth_service.github_fetch_user_info(access_token)
    except Exception as exc:
        logger.exception("GitHub OAuth callback failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to authenticate with GitHub"
        ) from exc

    user = auth_service.get_or_create_oauth_user("github", user_info)
    return _build_token_response(user, request, response)


# ------------------------------------------------------------------
# OIDC
# ------------------------------------------------------------------


@router.get("/oidc/authorize")
async def oidc_authorize() -> dict[str, str]:
    url = await auth_service.oidc_authorize_url_async()
    return {"authorize_url": url}


@router.post("/oidc/callback", response_model=TokenResponse)
async def oidc_callback(body: OAuthCallbackRequest, request: Request, response: Response) -> TokenResponse:
    try:
        access_token = await auth_service.oidc_exchange_code(body.code)
        user_info = await auth_service.oidc_fetch_user_info(access_token)
    except Exception as exc:
        logger.exception("OIDC callback failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to authenticate with OIDC provider"
        ) from exc

    user = auth_service.get_or_create_oauth_user("oidc", user_info)
    return _build_token_response(user, request, response)


# ------------------------------------------------------------------
# Current user
# ------------------------------------------------------------------


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> dict[str, object]:
    return user


# ------------------------------------------------------------------
# Device sessions
# ------------------------------------------------------------------


@router.get("/sessions", response_model=list[DeviceSessionResponse])
async def list_sessions(user: CurrentUser, request: Request) -> list[dict[str, object]]:
    """List all device sessions for the current user."""
    sessions = list_user_sessions(str(user["id"]))
    # Mark which session is current (from JWT sid claim)
    from tellaro_pm.core.auth import decode_access_token

    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    current_sid = None
    if token:
        payload = decode_access_token(token)
        if payload:
            current_sid = payload.get("sid")

    result: list[dict[str, object]] = []
    for s in sessions:
        if not s.get("is_active"):
            continue
        entry = {
            "id": s["id"],
            "device_name": s.get("device_name", "Unknown"),
            "browser": s.get("browser", ""),
            "browser_version": s.get("browser_version", ""),
            "os": s.get("os", ""),
            "os_version": s.get("os_version", ""),
            "device_type": s.get("device_type", ""),
            "ip_address": s.get("ip_address", ""),
            "last_ip": s.get("last_ip", ""),
            "is_current": str(s["id"]) == str(current_sid) if current_sid else False,
            "last_used_at": s.get("last_used_at", ""),
            "created_at": s.get("created_at", ""),
        }
        result.append(entry)
    return result


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, user: CurrentUser) -> None:
    """Revoke a specific device session."""
    if not revoke_session(session_id, str(user["id"])):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")


@router.post("/sessions/revoke-all", status_code=status.HTTP_200_OK)
async def revoke_all(user: CurrentUser, request: Request) -> dict[str, object]:
    """Revoke all sessions except the current one."""
    from tellaro_pm.core.auth import decode_access_token

    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    current_sid = None
    if token:
        payload = decode_access_token(token)
        if payload:
            current_sid = str(payload.get("sid", ""))

    count = revoke_all_sessions(str(user["id"]), except_session_id=current_sid)
    return {"revoked": count}


# ------------------------------------------------------------------
# Logout (revoke current session)
# ------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser, request: Request) -> None:
    """Revoke the current device session."""
    from tellaro_pm.core.auth import decode_access_token

    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if token:
        payload = decode_access_token(token)
        if payload:
            sid = payload.get("sid")
            if isinstance(sid, str):
                revoke_session(sid, str(user["id"]))


# ------------------------------------------------------------------
# Auth domain configuration (admin only)
# ------------------------------------------------------------------


@router.get("/domains", response_model=list[AuthDomainResponse])
async def list_auth_domains(_admin: AdminUser) -> list[dict[str, object]]:
    return auth_service.list_auth_domains()


@router.post("/domains", response_model=AuthDomainResponse, status_code=status.HTTP_201_CREATED)
async def create_auth_domain(body: AuthDomainCreate, _admin: AdminUser) -> dict[str, object]:
    return auth_service.create_auth_domain(body.model_dump())


@router.get("/domains/{domain_id}", response_model=AuthDomainResponse)
async def get_auth_domain(domain_id: str, _admin: AdminUser) -> dict[str, object]:
    domain = auth_service.get_auth_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auth domain not found")
    return domain


@router.patch("/domains/{domain_id}", response_model=AuthDomainResponse)
async def update_auth_domain(domain_id: str, body: AuthDomainUpdate, _admin: AdminUser) -> dict[str, object]:
    updated = auth_service.update_auth_domain(domain_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auth domain not found")
    return updated


@router.delete("/domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_auth_domain(domain_id: str, _admin: AdminUser) -> None:
    if not auth_service.delete_auth_domain(domain_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auth domain not found")
