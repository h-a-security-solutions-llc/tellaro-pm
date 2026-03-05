"""Tests for hierarchical configuration loader."""

import os
from unittest.mock import patch

from tellaro_pm.core.settings import Settings, get_default_setting


class TestGetDefaultSetting:
    def test_returns_default_when_no_override(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
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

        with patch.dict(os.environ, {"TEST_ENABLED": "false"}):
            result = get_default_setting("test", "enabled", True)
            assert result is False

    def test_env_var_int_parsing(self) -> None:
        with patch.dict(os.environ, {"TEST_PORT": "9999"}):
            result = get_default_setting("test", "port", 8000)
            assert result == 9999


class TestSettings:
    def test_settings_loads(self) -> None:
        s = Settings()  # type: ignore[call-arg]
        assert s.API_VERSION_STR == "v1"
        assert s.API_SERVER_PORT == 8000

    def test_cors_origins_parsed(self) -> None:
        s = Settings()  # type: ignore[call-arg]
        assert isinstance(s.API_BACKEND_CORS_ORIGINS, list)

    def test_opensearch_hosts_parsed(self) -> None:
        s = Settings()  # type: ignore[call-arg]
        assert isinstance(s.OPENSEARCH_HOSTS, list)
        assert len(s.OPENSEARCH_HOSTS) >= 1


class TestHealthEndpoint:
    def test_health(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_api_health(self, client) -> None:  # type: ignore[no-untyped-def]
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
