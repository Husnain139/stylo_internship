import pytest

from app.provider import PerimeterError, build_provider


def test_public_openai_host_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIT_MODEL_MODE", "local")
    monkeypatch.setenv("AUDIT_LOCAL_MODEL_URL", "https://api.openai.com/v1/chat/completions")
    with pytest.raises(PerimeterError):
        build_provider()


def test_gemini_host_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIT_MODEL_MODE", "local")
    monkeypatch.setenv(
        "AUDIT_LOCAL_MODEL_URL",
        "https://generativelanguage.googleapis.com/v1beta/models",
    )
    with pytest.raises(PerimeterError):
        build_provider()


def test_localhost_and_azure_hosts_are_allowed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIT_MODEL_MODE", "local")
    monkeypatch.setenv("AUDIT_LOCAL_MODEL_URL", "http://127.0.0.1:11434/v1/chat/completions")
    assert build_provider().name == "local"

    monkeypatch.setenv("AUDIT_MODEL_MODE", "azure")
    monkeypatch.setenv("AUDIT_AZURE_OPENAI_ENDPOINT", "https://audit.openai.azure.com")
    monkeypatch.setenv("AUDIT_AZURE_OPENAI_API_KEY", "local-test-only")
    assert build_provider().name == "azure"


def test_non_azure_remote_host_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIT_MODEL_MODE", "azure")
    monkeypatch.setenv("AUDIT_AZURE_OPENAI_ENDPOINT", "https://example.com")
    with pytest.raises(PerimeterError):
        build_provider()


def test_heuristic_mode_does_not_require_a_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUDIT_MODEL_MODE", "heuristic")
    provider = build_provider()
    assert provider.name == "heuristic"
    assert provider.uses_network is False
