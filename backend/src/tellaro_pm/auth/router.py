"""Auth API router: login, OAuth, OIDC, domain discovery, domain CRUD."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from tellaro_pm.auth.schemas import (
    AuthDiscoveryRequest,
    AuthDiscoveryResponse,
    AuthDomainCreate,
    AuthDomainResponse,
    AuthDomainUpdate,
    LoginRequest,
    OAuthCallbackRequest,
    TokenResponse,
)
from tellaro_pm.auth.service import auth_service
from tellaro_pm.core.dependencies import get_current_user, require_admin
from tellaro_pm.users.schemas import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
AdminUser = Annotated[dict[str, object], Depends(require_admin)]

# ------------------------------------------------------------------
# Discovery
# ------------------------------------------------------------------


@router.post("/discover", response_model=AuthDiscoveryResponse)
async def discover_provider(body: AuthDiscoveryRequest) -> AuthDiscoveryResponse:
    """Given an email, return which auth provider handles this domain."""
    provider, redirect_url = auth_service.discover_auth_provider(body.email)
    return AuthDiscoveryResponse(provider=provider, redirect_url=redirect_url)


# ------------------------------------------------------------------
# Local login
# ------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    user = auth_service.authenticate_local(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = auth_service.create_token_for_user(user)
    return TokenResponse(access_token=token)


# ------------------------------------------------------------------
# GitHub OAuth
# ------------------------------------------------------------------


@router.get("/github/authorize")
async def github_authorize() -> dict[str, str]:
    url = auth_service.github_authorize_url()
    return {"authorize_url": url}


@router.post("/github/callback", response_model=TokenResponse)
async def github_callback(body: OAuthCallbackRequest) -> TokenResponse:
    try:
        access_token = await auth_service.github_exchange_code(body.code)
        user_info = await auth_service.github_fetch_user_info(access_token)
    except Exception as exc:
        logger.exception("GitHub OAuth callback failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to authenticate with GitHub"
        ) from exc

    user = auth_service.get_or_create_oauth_user("github", user_info)
    token = auth_service.create_token_for_user(user)
    return TokenResponse(access_token=token)


# ------------------------------------------------------------------
# OIDC
# ------------------------------------------------------------------


@router.get("/oidc/authorize")
async def oidc_authorize() -> dict[str, str]:
    url = await auth_service.oidc_authorize_url_async()
    return {"authorize_url": url}


@router.post("/oidc/callback", response_model=TokenResponse)
async def oidc_callback(body: OAuthCallbackRequest) -> TokenResponse:
    try:
        access_token = await auth_service.oidc_exchange_code(body.code)
        user_info = await auth_service.oidc_fetch_user_info(access_token)
    except Exception as exc:
        logger.exception("OIDC callback failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to authenticate with OIDC provider"
        ) from exc

    user = auth_service.get_or_create_oauth_user("oidc", user_info)
    token = auth_service.create_token_for_user(user)
    return TokenResponse(access_token=token)


# ------------------------------------------------------------------
# Current user
# ------------------------------------------------------------------


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> dict[str, object]:
    return user


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
