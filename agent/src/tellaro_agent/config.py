"""Hierarchical configuration loader for Tellaro Agent.

Resolution order (highest priority first):
  1. CLI arguments (applied via override_from_cli)
  2. Docker/Kubernetes Secrets (/run/secrets/{KEY})
  3. Environment Variables (loaded from .env via python-dotenv)
  4. Default values
"""

import os
from functools import lru_cache
from typing import cast

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class AgentSettings(BaseSettings):
    """Agent daemon settings."""

    # Backend connection
    BACKEND_URL: str = get_default_setting("backend", "url", "ws://localhost:8000/ws/agent")
    BACKEND_API_URL: str = get_default_setting("backend", "api_url", "http://localhost:8000")

    # Agent identity
    AGENT_NAME: str = get_default_setting("agent", "name", "")
    AGENT_TOKEN: str = get_default_setting("agent", "token", "")

    # Claude Code
    CLAUDE_EXECUTABLE: str = get_default_setting("claude", "executable", "claude")

    # Logging
    LOG_LEVEL: str = get_default_setting("log", "log_level", "INFO")
    LOG_TO_STDOUT: bool = get_default_setting("log", "log_to_stdout", True)

    # Heartbeat
    HEARTBEAT_INTERVAL_SECONDS: int = get_default_setting("heartbeat", "interval_seconds", 30)

    def override_from_cli(self, **kwargs: str | int | bool | None) -> "AgentSettings":
        """Apply CLI argument overrides (highest priority). Returns a new instance."""
        overrides: dict[str, str | int | bool | None] = {}
        for key, value in kwargs.items():
            field_name = key.upper()
            if value is not None and hasattr(self, field_name):
                overrides[field_name] = value
        if overrides:
            return self.model_copy(update=overrides)
        return self

    model_config = SettingsConfigDict(case_sensitive=True)


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()  # type: ignore[call-arg]
