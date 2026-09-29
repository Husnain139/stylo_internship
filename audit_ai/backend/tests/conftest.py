from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PASSWORD = "prototype-only"
SENIOR = "senior.auditor@stylo.local"
JUNIOR = "junior.auditor@stylo.local"
ADMIN = "admin.auditor@stylo.local"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AUDIT_MODEL_MODE", "heuristic")
    monkeypatch.setenv("AUDIT_BOOTSTRAP_PASSWORD", PASSWORD)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client, tmp_path / "data"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(test_client: TestClient, email: str) -> str:
    response = test_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def samples() -> Path:
    return Path(__file__).resolve().parents[2] / "samples"
