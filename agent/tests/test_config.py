"""Tests for agent hierarchical configuration loader."""

import os
from unittest.mock import patch

from tellaro_agent.config import AgentSettings, get_default_setting


class TestGetDefaultSetting:
    def test_returns_default_when_no_override(self) -> None:
        result = get_default_setting("test", "nonexistent_key", "fallback")
        assert result == "fallback"

    def test_env_var_overrides_default(self) -> None:
        with patch.dict(os.environ, {"TEST_MY_KEY": "from_env"}):
            result = get_default_setting("test", "my_key", "fallback")
            assert result == "from_env"

    def test_env_var_bool_parsing(self) -> None:
        with patch.dict(os.environ, {"TEST_ENABLED": "true"}):
            result = get_default_setting("test", "enabled", False)
            assert result is True

    def test_env_var_int_parsing(self) -> None:
        with patch.dict(os.environ, {"TEST_PORT": "9999"}):
            result = get_default_setting("test", "port", 8000)
            assert result == 9999


class TestAgentSettings:
    def test_settings_loads(self) -> None:
        s = AgentSettings()  # type: ignore[call-arg]
        assert s.BACKEND_URL == "ws://localhost:8000/ws/agent"
        assert s.HEARTBEAT_INTERVAL_SECONDS == 30

    def test_cli_override(self) -> None:
        s = AgentSettings()  # type: ignore[call-arg]
        overridden = s.override_from_cli(backend_url="ws://other:9000/ws/agent")
        assert overridden.BACKEND_URL == "ws://other:9000/ws/agent"
        # Original unchanged
        assert s.BACKEND_URL == "ws://localhost:8000/ws/agent"

    def test_cli_override_skips_none(self) -> None:
        s = AgentSettings()  # type: ignore[call-arg]
        overridden = s.override_from_cli(backend_url=None)
        assert overridden.BACKEND_URL == s.BACKEND_URL
