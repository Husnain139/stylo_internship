"""Salted password hashes. The plain password is never stored."""

from __future__ import annotations

import hashlib
import secrets

_N = 2**14
_R = 8
_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt}${digest.hex()}"


def burn_password_check(password: str) -> None:
    """Spend the same work when the account has no password, so missing accounts are not faster."""
    verify_password(password, _dummy_hash())


def _dummy_hash() -> str:
    global _DUMMY
    if not _DUMMY:
        _DUMMY = hash_password("not-a-real-password")
    return _DUMMY


_DUMMY = ""


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt" or not salt or not digest:
        return False
    check = hashlib.scrypt(password.encode(), salt=salt.encode(), n=_N, r=_R, p=_P, dklen=32)
    return secrets.compare_digest(check.hex(), digest)
