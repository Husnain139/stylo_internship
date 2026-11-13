"""Who can see which policies. Compartments, not a ladder. HR sees every policy."""

from __future__ import annotations

import hashlib

AUDIENCES = ("everyone", "intern", "employee", "manager", "hr", "executive")

ROLE_LABELS = {
    "intern": "Intern",
    "employee": "Employee",
    "manager": "Manager",
    "hr": "HR",
    "executive": "Executive",
}

AUDIENCE_LABELS = {
    "everyone": "Everyone",
    "intern": "Interns",
    "employee": "Employees",
    "manager": "Managers",
    "hr": "HR",
    "executive": "Executives",
}

PEOPLE = (
    ("sara.intern@stylo.example", "Sara", "intern"),
    ("ali.employee@stylo.example", "Ali", "employee"),
    ("noor.manager@stylo.example", "Noor", "manager"),
    ("insrah.hr@stylo.example", "Insrah", "hr"),
    ("omar.executive@stylo.example", "Omar", "executive"),
)


def allowed_audiences(designation: str) -> tuple[str, ...]:
    if designation == "hr":
        return AUDIENCES
    if designation in AUDIENCES and designation != "everyone":
        return ("everyone", designation)
    return ("everyone",)


def access_key(designation: str) -> str:
    raw = "|".join(allowed_audiences(designation))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def role_label(designation: str) -> str:
    return ROLE_LABELS.get(designation, designation)
