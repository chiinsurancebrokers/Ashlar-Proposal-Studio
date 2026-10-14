"""Deterministic access rules: hospital network, prior approval, pre-approval threshold.

These rules decide whether a claim is paid in full, so they must reach the
client's "Points to consider" every time a plan's documents state them, not only
when the extraction model happens to mention them. They are read from the full
Table of Benefits / wording / providers-list text, never from a length-capped excerpt.
"""
from __future__ import annotations

import re

_MONEY = r"(?:€\s*/\s*US\$|€|EUR|US\$|USD|\$|£|GBP)\s*"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or ""))


def _first(patterns: tuple[str, ...], text: str) -> re.Match | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return m
    return None


def extract_access_rules(text: str) -> dict:
    """Return the network / approval rules stated anywhere in the plan documents."""
    t = _flat(text)
    rules: dict = {}

    network = _first((
        r"outside (?:this|the|our) network[^.]{0,220}?co-?payment of (?P<pct>\d{1,2})\s*%",
        r"not part of the network[^.]{0,260}?(?P<pct>\d{1,2})\s*%\s*co-?payment",
        r"(?P<pct>\d{1,2})\s*%\s*of the (?:expenses incurred|incurred expenses) will remain at your charge",
    ), t)
    if network:
        rules["network_copayment_pct"] = int(network.group("pct"))
        rules["network_tiered"] = bool(re.search(r"all hospitals worldwide except those listed", t, re.I))
        rules["emergency_exempt"] = bool(re.search(r"except (?:in cases of )?(?:medical |life-threatening )?emergenc", t, re.I))

    approval = _first((
        r"hospitali[sz]ations? (?:are|is) subject to prior approval\.?\s*A (?P<pct>\d{1,2})\s*% penalty",
        r"before you are admitted to hospital[^.]{0,200}?pre-?\s?approval\.?\s*A penalty of (?P<pct>\d{1,2})\s*%",
    ), t)
    if approval:
        rules["hospital_prior_approval_penalty_pct"] = int(approval.group("pct"))

    threshold = _first((
        rf"treatments?[^.]{{0,40}}?(?:exceeding|costing more than|over)\s*{_MONEY}(?P<amt>\d[\d,.]*)[^.]{{0,140}}?(?:subject to|requires?)[^.]{{0,30}}?pre-?\s?approval",
        rf"(?:procedures|treatments?)\s+costing more than\s*{_MONEY}(?P<amt>\d[\d,.]*)\s+are subject to (?:our )?pre-?\s?approval",
    ), t)
    if threshold:
        rules["pre_approval_threshold"] = threshold.group("amt").rstrip(".,")
        lead = re.search(r"(?:at least|at the latest) (?P<days>\d{1,2}) days before", t, re.I)
        if lead:
            rules["pre_approval_lead_days"] = int(lead.group("days"))

    if re.search(r"LIBRARY DOCUMENT: [^\n]*(?:providers?|hospitals?)[-_ ]list", str(text or ""), re.I):
        rules["provider_list_supplied"] = True
    return rules


def access_rule_limitations(rules: dict) -> list[dict]:
    """Client-facing limitation rows for the rules found."""
    out: list[dict] = []
    pct = rules.get("network_copayment_pct")
    if pct:
        where = (
            "at hospitals the providers list reserves for higher plan tiers"
            if rules.get("network_tiered") else "outside the plan's hospital network"
        )
        detail = f"Non-emergency hospitalisation {where}: {pct}% of the cost stays with you."
        if rules.get("provider_list_supplied"):
            detail += " Check the hospital in the providers list (included with this analysis) before any planned admission."
        else:
            detail += " Check the hospital is in the plan's network before any planned admission."
        out.append({"topic": "Hospital network", "detail": detail, "source": "plan documents"})
    penalty = rules.get("hospital_prior_approval_penalty_pct")
    if penalty:
        out.append({
            "topic": "Prior approval for hospitalisation",
            "detail": f"Every hospitalisation needs the insurer's prior approval; without it the reimbursement is reduced by {penalty}%.",
            "source": "plan documents",
        })
    amount = rules.get("pre_approval_threshold")
    if amount:
        detail = f"Any treatment costing more than €{amount} needs pre-approval"
        if rules.get("pre_approval_lead_days"):
            detail += f", requested at least {rules['pre_approval_lead_days']} days before treatment"
        detail += "; otherwise a penalty is deducted from the reimbursement."
        out.append({"topic": f"Pre-approval above €{amount}", "detail": detail, "source": "plan documents"})
    return out


def apply_access_rules(result: dict, plan_text: str) -> dict:
    """Store the rules and put them at the top of the plan's critical limitations."""
    rules = extract_access_rules(plan_text)
    if not rules:
        return result
    result["access_rules"] = rules
    rows = access_rule_limitations(rules)
    # Drop the model's own paraphrase of the same rule so it is not listed twice.
    duplicates = []
    if rules.get("network_copayment_pct"):
        duplicates.append(r"(?:network|tier|listed)[^.;]{0,160}\b\d{1,2}\s*%|\b\d{1,2}\s*%[^.;]{0,160}(?:network|tier|remain at)")
    if rules.get("hospital_prior_approval_penalty_pct"):
        duplicates.append(r"hospitali[sz]\w*[^.;]{0,80}prior approval|prior approval[^.;]{0,80}hospitali[sz]")
    if rules.get("pre_approval_threshold"):
        duplicates.append(r"pre-?\s?approval[^.;]{0,80}(?:€|eur|\$)\s*\d|(?:€|eur|\$)\s*\d[\d,.]*[^.;]{0,80}pre-?\s?approval")

    def is_duplicate(item) -> bool:
        if isinstance(item, dict):
            text = f"{item.get('topic') or ''}: {item.get('detail') or ''}"
        else:
            text = str(item or "")
        return any(re.search(p, text, re.I) for p in duplicates)

    kept = [x for x in (result.get("critical_limitations") or []) if not is_duplicate(x)]
    result["critical_limitations"] = rows + kept
    return result
