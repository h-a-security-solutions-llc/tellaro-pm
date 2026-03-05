"""Shared test fixtures for Tellaro PM backend."""

import pytest
from fastapi.testclient import TestClient

from tellaro_pm.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
