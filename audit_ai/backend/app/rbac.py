"""Role permissions and password hashing for prototype sessions."""

from __future__ import annotations

import hashlib
import hmac
import secrets

JUNIOR = "junior_auditor"
SENIOR = "senior_auditor"
ADMIN = "administrator"

JUNIOR_PERMISSIONS = frozenset(
    {
        "engagement:create",
        "engagement:read",
        "document:upload",
        "document:read",
        "evidence:read",
        "finding:read",
    }
)

SENIOR_PERMISSIONS = JUNIOR_PERMISSIONS | frozenset(
    {
        "scope:confirm",
        "analysis:run",
        "finding:review",
        "finding:export",
        "audit:read",
    }
)

ADMIN_PERMISSIONS = frozenset(
    {
        "engagement:read",
        "user:manage",
        "member:assign",
        "settings:manage",
        "audit:read",
    }
)

PERMISSIONS = {
    JUNIOR: JUNIOR_PERMISSIONS,
    SENIOR: SENIOR_PERMISSIONS,
    ADMIN: ADMIN_PERMISSIONS,
}


def permissions_for(role: str) -> frozenset[str]:
    try:
        return PERMISSIONS[role]
    except KeyError as exc:
        raise PermissionError(role) from exc


def allows(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$", 1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 120_000)
    return hmac.compare_digest(digest.hex(), digest_hex)
