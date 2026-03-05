"""Authentication service: local login, OAuth, OIDC, domain-based routing."""

import logging
import secrets
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import httpx

from tellaro_pm.core.auth import create_access_token, verify_password
from tellaro_pm.core.opensearch import AUTH_DOMAINS_INDEX, CRUDService
from tellaro_pm.core.settings import settings
from tellaro_pm.users.service import user_service

logger = logging.getLogger(__name__)

AuthProvider = Literal["local", "github", "oidc"]


class AuthService:
    def __init__(self) -> None:
        self._domains_crud = CRUDService(AUTH_DOMAINS_INDEX)
        self._oidc_config_cache: dict[str, dict[str, object]] = {}

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap_admin(self) -> None:
        """Create the default local admin if no admin user exists."""
        existing = user_service.get_by_username(settings.DEFAULT_ADMIN_USERNAME)
        if existing is not None:
            return

        user_service.create(
            {
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "email": settings.DEFAULT_ADMIN_EMAIL,
                "display_name": "Administrator",
                "password": settings.DEFAULT_ADMIN_PASSWORD,
                "role": "admin",
                "auth_provider": "local",
            }
        )
        logger.info("Default admin user '%s' created", settings.DEFAULT_ADMIN_USERNAME)

    # ------------------------------------------------------------------
    # Local auth
    # ------------------------------------------------------------------

    def authenticate_local(self, email: str, password: str) -> dict[str, object] | None:
        user = user_service.get_by_email(email.lower())
        if user is None:
            return None

        stored_hash = user.get("password_hash")
        if not isinstance(stored_hash, str):
            return None

        if not verify_password(password, stored_hash):
            return None

        if not user.get("is_active", False):
            return None

        return user

    def create_access_token_for_user(self, user: dict[str, object], session_id: str | None = None) -> str:
        user_id = str(user["id"])
        extra: dict[str, object] = {"role": user.get("role", "member"), "email": user.get("email", "")}
        if session_id:
            extra["sid"] = session_id
        return create_access_token(user_id, extra)

    # ------------------------------------------------------------------
    # OAuth user upsert
    # ------------------------------------------------------------------

    def get_or_create_oauth_user(self, provider: str, provider_user_info: dict[str, object]) -> dict[str, object]:
        """Find an existing user by email or create one from OAuth provider data."""
        email = str(provider_user_info.get("email", "")).lower()
        if not email:
            raise ValueError("OAuth provider did not return an email address")

        existing = user_service.get_by_email(email)
        if existing is not None:
            return existing

        username = str(
            provider_user_info.get("login") or provider_user_info.get("preferred_username") or email.split("@")[0]
        )
        display_name = str(provider_user_info.get("name") or username)
        avatar_url = str(provider_user_info.get("avatar_url") or provider_user_info.get("picture") or "")

        # Ensure unique username
        if user_service.get_by_username(username) is not None:
            username = f"{username}-{secrets.token_hex(3)}"

        return user_service.create(
            {
                "username": username,
                "email": email,
                "display_name": display_name,
                "avatar_url": avatar_url or None,
                "role": "member",
                "auth_provider": provider,
                "auth_provider_id": str(provider_user_info.get("id", "")),
            }
        )

    # ------------------------------------------------------------------
    # Domain-based auth discovery
    # ------------------------------------------------------------------

    async def discover_auth_provider(self, email: str) -> tuple[AuthProvider, str | None]:
        """Given an email, determine which auth provider handles that domain.

        Returns (provider_name, redirect_url_or_none).
        Falls back to the global AUTH_PROVIDER setting if no domain mapping exists.
        """
        domain = email.lower().rsplit("@", maxsplit=1)[-1]

        domain_config = self._get_domain_config(domain)
        raw = str(domain_config.get("provider", "local")) if domain_config is not None else settings.AUTH_PROVIDER
        provider: AuthProvider = raw if raw in ("local", "github", "oidc") else "local"

        redirect_url: str | None = None
        if provider == "github":
            redirect_url = self.github_authorize_url()
        elif provider == "oidc":
            redirect_url = await self.oidc_authorize_url_async()

        return provider, redirect_url

    # ------------------------------------------------------------------
    # Auth domain CRUD
    # ------------------------------------------------------------------

    def create_auth_domain(self, data: dict[str, object]) -> dict[str, object]:
        now = datetime.now(UTC).isoformat()
        domain_id = str(uuid4())
        doc: dict[str, object] = {
            "id": domain_id,
            "is_active": True,
            **data,
            "created_at": now,
            "updated_at": now,
        }
        self._domains_crud.create(domain_id, doc)
        return doc

    def list_auth_domains(self) -> list[dict[str, object]]:
        query: dict[str, object] = {"query": {"match_all": {}}}
        return self._domains_crud.search(query, size=200)

    def get_auth_domain(self, domain_id: str) -> dict[str, object] | None:
        return self._domains_crud.get(domain_id)

    def update_auth_domain(self, domain_id: str, data: dict[str, object]) -> dict[str, object] | None:
        existing = self._domains_crud.get(domain_id)
        if existing is None:
            return None
        update_fields = {k: v for k, v in data.items() if v is not None}
        update_fields["updated_at"] = datetime.now(UTC).isoformat()
        self._domains_crud.update(domain_id, update_fields)
        existing.update(update_fields)
        return existing

    def delete_auth_domain(self, domain_id: str) -> bool:
        return self._domains_crud.delete(domain_id)

    def _get_domain_config(self, domain: str) -> dict[str, object] | None:
        query: dict[str, object] = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"domain": domain}},
                        {"term": {"is_active": True}},
                    ]
                }
            }
        }
        return self._domains_crud.search_one(query)

    # ------------------------------------------------------------------
    # GitHub OAuth
    # ------------------------------------------------------------------

    def github_authorize_url(self, state: str | None = None) -> str:
        state = state or secrets.token_urlsafe(32)
        return (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={settings.AUTH_GITHUB_CLIENT_ID}"
            f"&redirect_uri={settings.FRONTEND_URL}/auth/github/callback"
            f"&scope=read:user%20user:email"
            f"&state={state}"
        )

    async def github_exchange_code(self, code: str) -> str:
        """Exchange a GitHub authorization code for an access token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": settings.AUTH_GITHUB_CLIENT_ID,
                    "client_secret": settings.AUTH_GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            token: str = data["access_token"]
            return token

    async def github_fetch_user_info(self, access_token: str) -> dict[str, object]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            resp.raise_for_status()
            user_data: dict[str, object] = resp.json()

            # GitHub may not include email in profile; fetch from emails endpoint
            if not user_data.get("email"):
                email_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                email_resp.raise_for_status()
                emails: list[dict[str, object]] = email_resp.json()
                primary = next((e for e in emails if e.get("primary")), None)
                if primary:
                    user_data["email"] = primary["email"]

            return user_data

    # ------------------------------------------------------------------
    # OIDC (Okta, Azure AD, Keycloak, etc.)
    # ------------------------------------------------------------------

    async def _get_oidc_discovery(self) -> dict[str, object]:
        """Fetch and cache the OIDC discovery document."""
        url = settings.AUTH_OIDC_DISCOVERY_URL
        if url in self._oidc_config_cache:
            return self._oidc_config_cache[url]

        async with httpx.AsyncClient() as client:
            # Append well-known path if not already present
            discovery_url = (
                url
                if url.endswith("/.well-known/openid-configuration")
                else f"{url.rstrip('/')}/.well-known/openid-configuration"
            )
            resp = await client.get(discovery_url)
            resp.raise_for_status()
            config: dict[str, object] = resp.json()
            self._oidc_config_cache[url] = config
            return config

    def oidc_authorize_url(self, state: str | None = None) -> str:
        """Build OIDC authorization URL synchronously using configured values.

        For the full dynamic discovery flow, use oidc_authorize_url_async instead.
        """
        state = state or secrets.token_urlsafe(32)
        base = settings.AUTH_OIDC_DISCOVERY_URL.rstrip("/")
        # Heuristic: strip well-known suffix if present, then append /authorize
        if base.endswith("/.well-known/openid-configuration"):
            base = base.rsplit("/.well-known", maxsplit=1)[0]
        authorize_endpoint = f"{base}/authorize"
        scopes = settings.AUTH_OIDC_SCOPES.replace(" ", "%20")
        return (
            f"{authorize_endpoint}"
            f"?client_id={settings.AUTH_OIDC_CLIENT_ID}"
            f"&redirect_uri={settings.FRONTEND_URL}/auth/oidc/callback"
            f"&response_type=code"
            f"&scope={scopes}"
            f"&state={state}"
        )

    async def oidc_authorize_url_async(self, state: str | None = None) -> str:
        """Build OIDC authorization URL from the discovery document."""
        state = state or secrets.token_urlsafe(32)
        config = await self._get_oidc_discovery()
        authorize_endpoint = str(config["authorization_endpoint"])
        scopes = settings.AUTH_OIDC_SCOPES.replace(" ", "%20")
        return (
            f"{authorize_endpoint}"
            f"?client_id={settings.AUTH_OIDC_CLIENT_ID}"
            f"&redirect_uri={settings.FRONTEND_URL}/auth/oidc/callback"
            f"&response_type=code"
            f"&scope={scopes}"
            f"&state={state}"
        )

    async def oidc_exchange_code(self, code: str) -> str:
        """Exchange an OIDC authorization code for an access token."""
        config = await self._get_oidc_discovery()
        token_endpoint = str(config["token_endpoint"])

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.AUTH_OIDC_CLIENT_ID,
                    "client_secret": settings.AUTH_OIDC_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": f"{settings.FRONTEND_URL}/auth/oidc/callback",
                },
            )
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            return str(data["access_token"])

    async def oidc_fetch_user_info(self, access_token: str) -> dict[str, object]:
        config = await self._get_oidc_discovery()
        userinfo_endpoint = str(config["userinfo_endpoint"])

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            user_info: dict[str, object] = resp.json()
            return user_info


auth_service = AuthService()
