"""Local paths and model settings. Values are read at call time so tests can point at a temp directory."""

from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return Path(os.environ.get("AUDIT_DATA_DIR", APP_ROOT / "data"))


def files_dir() -> Path:
    return data_dir() / "files"


def db_path() -> Path:
    return data_dir() / "audit.db"


def samples_dir() -> Path:
    return APP_ROOT / "samples"


def model_mode() -> str:
    return os.environ.get("AUDIT_MODEL_MODE", "heuristic").strip().lower()


def local_model_url() -> str:
    return os.environ.get("AUDIT_LOCAL_MODEL_URL", "http://127.0.0.1:11434/v1/chat/completions")


def azure_openai_endpoint() -> str:
    return os.environ.get("AUDIT_AZURE_OPENAI_ENDPOINT", "").strip()


def azure_openai_deployment() -> str:
    return os.environ.get("AUDIT_AZURE_OPENAI_DEPLOYMENT", "audit-explain").strip()


def azure_openai_api_key() -> str:
    return os.environ.get("AUDIT_AZURE_OPENAI_API_KEY", "")


def bootstrap_password() -> str:
    return os.environ.get("AUDIT_BOOTSTRAP_PASSWORD", "prototype-only")
