"""IDP settings. OpenAI gpt-4o-mini with hard token caps."""

from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    path = APP_ROOT / ".env"
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


_load_dotenv()


def data_dir() -> Path:
    return Path(os.environ.get("IDP_DATA_DIR", APP_ROOT / "data"))


def uploads_dir() -> Path:
    return data_dir() / "uploads"


def exports_dir() -> Path:
    return data_dir() / "exports"


def db_path() -> Path:
    return data_dir() / "idp.db"


def max_upload_bytes() -> int:
    """Default 10 GiB. Set IDP_MAX_UPLOAD_BYTES=0 for no soft cap."""
    raw = os.environ.get("IDP_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024 * 1024))
    try:
        value = int(raw)
    except ValueError:
        return 10 * 1024 * 1024 * 1024
    if value <= 0:
        return 0
    return value


def max_non_tabular_bytes() -> int:
    """PDF/Word/images still need extract/OCR — tighter default guard."""
    try:
        return max(1_000_000, int(os.environ.get("IDP_MAX_NON_TABULAR_BYTES", str(100 * 1024 * 1024))))
    except ValueError:
        return 100 * 1024 * 1024


def idp_sample_rows() -> int:
    try:
        return max(3, min(50, int(os.environ.get("IDP_SAMPLE_ROWS", "8"))))
    except ValueError:
        return 8


def openai_api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def openai_model() -> str:
    # Cost-efficient multimodal model for structure analysis + light vision OCR.
    return (os.environ.get("IDP_OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"


def openai_max_output_tokens() -> int:
    try:
        return max(64, min(1024, int(os.environ.get("IDP_OPENAI_MAX_OUTPUT_TOKENS", "512"))))
    except ValueError:
        return 512


def openai_max_input_chars() -> int:
    try:
        return max(500, min(12_000, int(os.environ.get("IDP_OPENAI_MAX_INPUT_CHARS", "4000"))))
    except ValueError:
        return 4000


def openai_temperature() -> float:
    try:
        return max(0.0, min(1.0, float(os.environ.get("IDP_OPENAI_TEMPERATURE", "0"))))
    except ValueError:
        return 0.0


def openai_timeout_seconds() -> int:
    try:
        return max(5, min(60, int(os.environ.get("IDP_OPENAI_TIMEOUT_SECONDS", "30"))))
    except ValueError:
        return 30


def openai_max_sample_rows() -> int:
    try:
        return max(5, min(40, int(os.environ.get("IDP_OPENAI_MAX_SAMPLE_ROWS", "15"))))
    except ValueError:
        return 15


def cors_origins() -> list[str]:
    raw = os.environ.get("IDP_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


def temp_dir() -> Path:
    """DuckDB spill / scratch files (under data/tmp by default)."""
    raw = os.environ.get("IDP_TEMP_DIR")
    path = Path(raw) if raw else data_dir() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def system_ram_gb() -> float:
    """Total physical RAM in GiB (best-effort; 0 if unknown)."""
    # Windows
    try:
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return max(0.0, stat.ullTotalPhys / (1024**3))
    except Exception:  # noqa: BLE001
        pass
    # Unix
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return max(0.0, (pages * page_size) / (1024**3))
    except (AttributeError, OSError, ValueError):
        pass
    return 0.0


def system_cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def recommend_duckdb_memory_gb(total_ram_gb: float | None = None) -> float:
    """
    Size DuckDB from desk RAM.

    Leaves headroom for OS + Next.js + FastAPI (~25% of RAM, min 4 GiB),
    and never takes more than half of total RAM. Clamped to 1–48 GiB.
    """
    total = system_ram_gb() if total_ram_gb is None else float(total_ram_gb)
    if total <= 0:
        return 8.0  # assume 16 GB desk when undetectable
    reserve = max(4.0, total * 0.25)
    budget = total - reserve
    budget = min(budget, total * 0.5)
    return round(max(1.0, min(48.0, budget)), 2)


def recommend_duckdb_threads(cpu_count: int | None = None) -> int:
    """Use about half the cores, between 2 and 8 (desk-friendly)."""
    cpus = system_cpu_count() if cpu_count is None else max(1, int(cpu_count))
    return max(2, min(8, cpus // 2 or 1))


def duckdb_memory_gb() -> float:
    """Explicit IDP_DUCKDB_MEMORY_GB wins; otherwise auto from PC RAM."""
    raw = os.environ.get("IDP_DUCKDB_MEMORY_GB")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(1.0, min(48.0, float(raw)))
        except ValueError:
            pass
    return recommend_duckdb_memory_gb()


def duckdb_threads() -> int:
    """Explicit IDP_DUCKDB_THREADS wins; otherwise auto from CPU count."""
    raw = os.environ.get("IDP_DUCKDB_THREADS")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(1, min(32, int(raw)))
        except ValueError:
            pass
    return recommend_duckdb_threads()


def xlsx_max_rows() -> int:
    """XLSX export only when cleaned rows are at or below this cap."""
    try:
        return max(1, min(1_048_576, int(os.environ.get("IDP_XLSX_MAX_ROWS", "200000"))))
    except ValueError:
        return 200_000


def duckdb_sizing_report() -> dict[str, float | int | str]:
    """Human-readable sizing snapshot for health/docs."""
    total = system_ram_gb()
    cpus = system_cpu_count()
    return {
        "total_ram_gb": round(total, 2) if total else 0,
        "cpu_count": cpus,
        "recommended_memory_gb": recommend_duckdb_memory_gb(total or None),
        "recommended_threads": recommend_duckdb_threads(cpus),
        "active_memory_gb": duckdb_memory_gb(),
        "active_threads": duckdb_threads(),
        "memory_source": "env" if os.environ.get("IDP_DUCKDB_MEMORY_GB") else "auto",
        "threads_source": "env" if os.environ.get("IDP_DUCKDB_THREADS") else "auto",
    }
