"""List benefit families from active, authorized policies instead of a single RAG shortlist."""

from __future__ import annotations

import re
from datetime import date

from .access import allowed_audiences, can_see_passage, role_label, shares_audience, visible_passage
from .guardrails import contains_named_pay
from .models import Employee, Passage
from .sanitize import exposes_prompt
from .textutil import token_set

_OVERVIEW = re.compile(
    r"\b(?:facilit(?:y|ies)|benefits?|perks?|entitlements?|allowances?)\b", re.I
)
_BROAD = re.compile(r"\b(?:all|every|list|overview|what|which|available|eligible|qualify|avail)\b", re.I)
_SELF = re.compile(r"\b(?:my|i|for me|for myself)\b", re.I)
# Any other word names the benefit ("daily allowance", "hospitalization benefit"), so it is not an overview.
_OVERVIEW_WORDS = {
    "facility", "facilities", "benefit", "benefits", "perk", "perks", "entitlement", "entitlements",
    "allowance", "allowances", "all", "every", "list", "overview", "which", "available", "eligible",
    "qualify", "avail", "entitled", "am", "have", "any", "there", "myself",
}
_BENEFIT_TITLE = re.compile(
    r"\b(?:benefits?|facilities|allowances?|entitlements?|insurance|takaful|leave|reimbursement|"
    r"provident|loan|pension|retirement|advance salary|scholarship)\b", re.I
)
_HEADINGS = ["eligibility", "scope", "applicability", "coverage", "purpose", "benefits"]
_TRAVEL_HEADINGS = ["eligibility", "accommodation", "daily allowance", "fuel entitlement list",
                    "travel expense form", "mode of travel"]


def asks_for_benefit_overview(question: str) -> bool:
    return bool(_OVERVIEW.search(question) and _BROAD.search(question)
                and _SELF.search(question) and token_set(question) <= _OVERVIEW_WORDS)


def benefit_overview(store, employee: Employee, today: date) -> tuple[str, list[Passage]]:
    role = employee.designation
    audiences = set(allowed_audiences(role))
    items: list[str] = []
    sources: dict[str, Passage] = {}

    for policy in store.list_policies():
        if not shares_audience(policy.audience, audiences):
            continue
        title = policy.title.casefold()
        if "medical" not in title and "travel" not in title and not _BENEFIT_TITLE.search(title):
            continue
        travel = "travel" in title
        evidence = [
            p for p in store.heading_hits(_TRAVEL_HEADINGS if travel else _HEADINGS, audiences, today,
                                          policy_ids=[policy.id])
            if p.content_type in ({"section", "table"} if travel else {"section"})
            and shares_audience(p.audience, audiences)
            and visible_passage(role, p)
            and can_see_passage(role, p.title, p.heading, p.body, p.content_type, p.audience)
            and not contains_named_pay(f"{p.title}\n{p.body}")
            and not exposes_prompt(p.body)
        ]
        if not evidence:
            continue
        summary = _summary(policy.title, evidence)
        if summary and summary not in items:
            items.append(summary)
            sources.update((p.id, p) for p in evidence)

    if not items:
        return (f"I couldn't confirm any benefits from the policies available to your designation "
                f"({role_label(role)}). Ask HR to confirm what applies to you.", [])
    return (f"Based on your designation ({role_label(role)}), these are the benefits covered by the policies I can "
            "check. Some still depend on employment status, location, tenure, or other conditions I can't verify.\n\n"
            + "\n".join(f"- {item}" for item in items), list(sources.values()))


def _summary(title: str, evidence: list[Passage]) -> str:
    label = title.casefold()
    body = "\n".join(p.body for p in evidence).casefold()
    if "medical" in label and "permanent management employees" in body:
        options = ["inpatient care"] if re.search(r"\bin[- ]?patient\b", body) else ["medical coverage"]
        if "maternity" in body:
            options.append("maternity benefits if you meet the separate eligibility rules")
        return f"Medical coverage: {' and '.join(options)}. The policy covers permanent management employees."
    if "travel" in label and "permanent management employees" in body:
        distance = re.search(r"distance of ([\d,]+) kilometers or more round trip", body)
        trip = f" of at least {distance[1]} km round trip" if distance else ""
        headings = " ".join(p.heading.casefold() for p in evidence)
        options = [name for heading, name in (
            ("mode of travel", "transport"), ("accommodation", "hotel or self-stay"),
            ("daily allowance", "daily allowances"), ("fuel entitlement", "fuel rates"),
            ("travel expense form", "eligible expense claims"),
        ) if heading in headings]
        options_text = ", ".join(options[:-1]) + " and " + options[-1] if len(options) > 1 else (
            options[0] if options else "support"
        )
        return (f"Business travel: {options_text} for qualifying work trips{trip}. "
                "Permanent management employment is required.")
    if "provident fund" in label and "permanent head office" in body:
        tenure = re.search(r"\((\d+)\) months of continuous service", body)
        extra = f" with at least {int(tenure[1])} months of continuous service" if tenure else ""
        return f"Provident fund loan: available to permanent Head Office (RSC) employees{extra}, subject to policy and approval."
    if "advance salary" in label and re.search(r"\b(?:head office|ho\s*-\s*rsc)\b", label):
        max_pct = re.search(r"maximum\s+(\d+)% of gross salary", body)
        limit = f" up to {max_pct[1]}% of gross salary" if max_pct else ""
        window = re.search(r"application window:\s*(\d+(?:st|nd|rd|th)) to (\d+(?:st|nd|rd|th)) of the month", body)
        dates = f" Apply from the {window[1]} to the {window[2]} each month." if window else ""
        return f"Salary advance:{limit} for eligible Head Office (RSC) employees.{dates}" if limit else (
            f"Salary advance: available to eligible Head Office (RSC) employees.{dates}"
        )
    return f"{title}: a policy is available, but I can't confirm your eligibility from your designation alone."
