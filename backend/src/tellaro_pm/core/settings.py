"""Hierarchical configuration loader for Tellaro PM backend.

Resolution order (highest priority first):
  1. Docker/Kubernetes Secrets (/run/secrets/{KEY})
  2. Environment Variables (loaded from .env via python-dotenv)
  3. Default values
"""

import logging
import os
import secrets
import string
from functools import lru_cache
from typing import Annotated, cast

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

load_dotenv()


def get_default_setting[T: (str, int, bool, None)](section: str, key: str, default: T) -> T:
    """Load a config value using the hierarchical resolution order.

    1. Docker/Kubernetes secret file at /run/secrets/{KEY}
    2. Environment variable {SECTION}_{KEY}
    3. Provided default
    """
    # 1. Docker/Kubernetes secrets
    secret_file_path = f"/run/secrets/{key.upper()}"
    if os.path.isfile(secret_file_path):
        try:
            with open(secret_file_path, encoding="UTF-8") as f:
                return cast("T", f.read().strip())
        except (PermissionError, OSError):
            pass

    # 2. Environment variables
    env_var_name = f"{section.upper()}_{key.upper()}"
    env_var = os.getenv(env_var_name)
    if env_var is not None:
        if isinstance(default, bool):
            return cast("T", env_var.lower() in ("true", "1", "yes"))
        if isinstance(default, int):
            return cast("T", int(env_var))
        return cast("T", env_var)

    # 3. Default
    return default


def _random_secret(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Settings(BaseSettings):
    """Application settings for Tellaro PM backend."""

    # Environment
    ENV: str = get_default_setting("env", "environment", "development")

    # API Server
    API_VERSION_STR: str = get_default_setting("api", "version_str", "v1")
    API_SERVER_HOST: str = get_default_setting("api", "server_host", "127.0.0.1")
    API_SERVER_PORT: int = get_default_setting("api", "server_port", 8000)
    API_SERVER_RELOAD: bool = get_default_setting("api", "server_reload", False)
    API_SERVER_WORKERS: int = get_default_setting("api", "workers", 4)
    API_BACKEND_CORS_ORIGINS: Annotated[list[str] | str, NoDecode] = get_default_setting(
        "api", "backend_cors_origins", "*"
    )

    # OpenSearch
    OPENSEARCH_HOSTS: Annotated[list[str] | str, NoDecode] = get_default_setting(
        "opensearch", "host", "http://localhost:9200"
    )
    OPENSEARCH_USERNAME: str | None = get_default_setting("opensearch", "username", None)
    OPENSEARCH_PASSWORD: str | None = get_default_setting("opensearch", "password", None)
    OPENSEARCH_USE_SSL: bool = get_default_setting("opensearch", "use_ssl", False)
    OPENSEARCH_VERIFY_SSL: bool = get_default_setting("opensearch", "verify_ssl", False)
    OPENSEARCH_CA_CERTS: str | None = get_default_setting("opensearch", "ca_certs", None)
    OPENSEARCH_INDEX_PREFIX: str = get_default_setting("opensearch", "index_prefix", "")
    OPENSEARCH_NUMBER_OF_SHARDS: int = get_default_setting("opensearch", "number_of_shards", 2)
    OPENSEARCH_NUMBER_OF_REPLICAS: int = get_default_setting("opensearch", "number_of_replicas", 1)
    OPENSEARCH_TIMEOUT: int = get_default_setting("opensearch", "timeout", 60)

    # Redis
    REDIS_HOST: str = get_default_setting("redis", "host", "localhost")
    REDIS_PORT: int = get_default_setting("redis", "port", 6379)
    REDIS_DB: int = get_default_setting("redis", "db", 0)
    REDIS_PASSWORD: str | None = get_default_setting("redis", "password", None)
    REDIS_ENABLED: bool = get_default_setting("redis", "enabled", True)

    # Authentication - Provider (local, github, oidc)
    AUTH_PROVIDER: str = get_default_setting("auth", "provider", "local")

    # Authentication - OAuth (GitHub)
    AUTH_GITHUB_CLIENT_ID: str = get_default_setting("auth", "github_client_id", "")
    AUTH_GITHUB_CLIENT_SECRET: str = get_default_setting("auth", "github_client_secret", "")
    AUTH_GITHUB_ORG: str = get_default_setting("auth", "github_org", "")

    # GitHub App (server-to-server operations)
    GITHUB_APP_ID: str = get_default_setting("github", "app_id", "")
    GITHUB_APP_PRIVATE_KEY_PATH: str = get_default_setting("github", "app_private_key_path", "")
    GITHUB_APP_INSTALLATION_ID: str = get_default_setting("github", "app_installation_id", "")
    GITHUB_WEBHOOK_SECRET: str = get_default_setting("github", "webhook_secret", "")

    # Authentication - OIDC (Okta, Azure AD, Keycloak, etc.)
    AUTH_OIDC_DISCOVERY_URL: str = get_default_setting("auth", "oidc_discovery_url", "")
    AUTH_OIDC_CLIENT_ID: str = get_default_setting("auth", "oidc_client_id", "")
    AUTH_OIDC_CLIENT_SECRET: str = get_default_setting("auth", "oidc_client_secret", "")
    AUTH_OIDC_SCOPES: str = get_default_setting("auth", "oidc_scopes", "openid profile email")

    # Authentication - JWT
    JWT_SECRET_KEY: str = get_default_setting("auth", "jwt_secret_key", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = get_default_setting("auth", "access_token_expire_minutes", 15)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = get_default_setting("auth", "refresh_token_expire_days", 30)
    MAX_DEVICE_SESSIONS: int = get_default_setting("auth", "max_device_sessions", 10)
    AUTH_RATE_LIMIT_WINDOW: int = get_default_setting("auth", "rate_limit_window", 900)
    AUTH_RATE_LIMIT_MAX: int = get_default_setting("auth", "rate_limit_max", 15)

    # Default local admin (bootstrap — always available regardless of auth provider)
    DEFAULT_ADMIN_USERNAME: str = get_default_setting("auth", "default_admin_username", "admin")
    DEFAULT_ADMIN_EMAIL: str = get_default_setting("auth", "default_admin_email", "admin@localhost.dev")
    DEFAULT_ADMIN_PASSWORD: str = get_default_setting("auth", "default_admin_password", "Admin1234!")

    # Logging
    LOG_LEVEL: str = get_default_setting("log", "log_level", "INFO")
    LOG_TO_STDOUT: bool = get_default_setting("log", "log_to_stdout", True)

    # Frontend
    FRONTEND_URL: str = get_default_setting("frontend", "url", "http://localhost:5173")

    # --- Validators ---

    @field_validator("API_BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def decode_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",")]
        return v if isinstance(v, list) else [str(v)]  # pyright: ignore[reportUnnecessaryIsInstance]

    @field_validator("OPENSEARCH_HOSTS", mode="before")
    @classmethod
    def decode_opensearch_hosts(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",")]
        return v if isinstance(v, list) else [str(v)]  # pyright: ignore[reportUnnecessaryIsInstance]

    @model_validator(mode="after")
    def ensure_jwt_secret(self) -> "Settings":
        if not self.JWT_SECRET_KEY:
            generated = _random_secret(64)
            object.__setattr__(self, "JWT_SECRET_KEY", generated)
            logging.getLogger("tellaro_pm.settings").warning(
                "AUTH_JWT_SECRET_KEY is not set — generated a random key. "
                "Sessions will NOT survive backend restarts. "
                "Set AUTH_JWT_SECRET_KEY in .env for persistent sessions."
            )
        return self

    @model_validator(mode="after")
    def adjust_opensearch_replicas(self) -> "Settings":
        object.__setattr__(
            self,
            "OPENSEARCH_NUMBER_OF_REPLICAS",
            min(
                int(self.OPENSEARCH_NUMBER_OF_REPLICAS),
                len(self.OPENSEARCH_HOSTS),
            ),
        )
        return self

    model_config = SettingsConfigDict(case_sensitive=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
