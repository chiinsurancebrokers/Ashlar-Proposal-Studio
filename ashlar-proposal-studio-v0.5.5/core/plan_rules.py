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
        rules["network_tiered"] = bool(re.search(r"all hospitals worldwide.{0,80}?except those listed", t, re.I))
        rules["emergency_exempt"] = bool(re.search(r"except (?:in cases of )?(?:medical |life-threatening )?emergenc", t, re.I))
        if rules["network_tiered"]:
            countries = listed_network_countries(text)
            if countries:
                rules["network_listed_countries"] = countries

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

    # "Benefit may/will not be paid unless pre-authorisation has been provided" /
    # "If you don't get the following pre-authorised we will not cover the cost"
    # (Bupa): no fixed penalty, the claim itself is at risk.
    if not rules.get("hospital_prior_approval_penalty_pct") and re.search(
        r"benefits? (?:will|may) not be paid unless pre-?\s?authori[sz]ation"
        r"|(?:don.?t|do not) get the following pre-?\s?authori[sz]ed,? we will not (?:cover|pay)",
        t, re.I,
    ):
        rules["preauth_or_no_payment"] = True
        items = preauth_required_items(text)
        if items:
            rules["preauth_items"] = items
        stay = re.search(r"in-patient stays of (?P<n>\d+) nights or more need pre-?\s?authori[sz]ation", t, re.I)
        if stay:
            # A medical report before that night, on top of the admission pre-authorisation.
            rules["preauth_inpatient_nights"] = int(stay.group("n"))
        notice = re.search(r"contact us within (?P<h>\d{1,3}) hours of (?:your|the) admission", t, re.I)
        if notice:
            rules["emergency_notice_hours"] = int(notice.group("h"))

    if re.search(r"LIBRARY DOCUMENT: [^\n]*(?:providers?|hospitals?)[-_ ]list", str(text or ""), re.I):
        rules["provider_list_supplied"] = True
    return rules


def _document_sections(text: str, name_pattern: str) -> str:
    """The text of the library documents whose header matches ``name_pattern``
    (the whole text when the documents carry no headers)."""
    raw = str(text or "")
    headers = list(re.finditer(r"^--- LIBRARY DOCUMENT: [^\n]*---$", raw, re.M))
    if not headers:
        return raw
    parts = []
    for i, h in enumerate(headers):
        if re.search(name_pattern, h.group(0), re.I):
            end = headers[i + 1].start() if i + 1 < len(headers) else len(raw)
            parts.append(raw[h.start():end])
    return "\n".join(parts)


_COUNTRY_HEADING = re.compile(
    r"^[ \t]*(?P<name>[A-Z][A-Za-z .'&()-]{1,40}?)[ \t]*\n(?:[ \t]*\n)*[^\n]*\bHospital name\b", re.M
)


def listed_network_countries(text: str) -> list[str]:
    """Countries that have a hospital table in the providers list.

    APRIL's list names, country by country, the hospitals reserved for the
    higher plan tiers; every hospital in a country that is not listed is open
    to all tiers.
    """
    section = _document_sections(text, r"providers?[-_ ]list|hospitals?[-_ ]list")
    if not re.search(r"Hospital name", section):
        return []
    names: list[str] = []
    for m in _COUNTRY_HEADING.finditer(section):
        name = re.sub(r"\s+", " ", m.group("name")).strip()
        if name and name.casefold() not in {n.casefold() for n in names} and not re.search(r"\bhospital\b|\bcity\b", name, re.I):
            names.append(name)
    return names


_BULLET = re.compile(r"^\s*[¡•▪■●◦]\s+(?P<item>.+?)(?:\s{3,}|$)")


def preauth_required_items(text: str) -> list[str]:
    """The bulleted list after "If you don't get the following pre-authorised
    we will not cover the cost" (Bupa member guide)."""
    raw = str(text or "")
    start = re.search(r"(?:don.?t|do\s+not)\s+get\s+the\s+following\s+pre-?\s?authori[sz]ed", raw, re.I)
    if not start:
        return []
    items: list[str] = []
    gap = 0
    for line in raw[start.end():].splitlines()[1:60]:
        m = _BULLET.match(line)
        if not m:
            if items:
                gap += 1
                if gap > 6:
                    break
            continue
        gap = 0
        item = re.split(r",\s*(?:for example|e\.g\.|such as)\b", m.group("item"), maxsplit=1, flags=re.I)[0]
        item = re.sub(r"^having\s+", "", item.strip(" ;,.")).strip()
        if item and item.casefold() not in {i.casefold() for i in items}:
            items.append(item)
        if len(items) >= 12:
            break
    return items


def _join_items(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def destination_country(client_profile: str, listed: list[str] | None = None) -> str:
    """The country the client lives in or is moving to, from the case profile."""
    text = str(client_profile or "")
    for name in listed or []:
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            return name
    m = re.search(
        r"\b(?:moving|relocating|relocate|move|moved|living|lives|live|based|resident|residing|settling)\s+"
        r"(?:back\s+)?(?:to|in)\s+(?:the\s+)?(?P<c>[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})",
        text,
    )
    return m.group("c").strip() if m else ""


def access_rule_limitations(rules: dict, destination: str = "") -> list[dict]:
    """Client-facing limitation rows for the rules found."""
    out: list[dict] = []
    pct = rules.get("network_copayment_pct")
    if pct:
        listed = rules.get("network_listed_countries") or []
        if rules.get("network_tiered"):
            detail = f"Non-emergency stays at hospitals the providers list reserves for higher plan tiers leave {pct}% of the cost with you."
        else:
            detail = f"Non-emergency hospitalisation outside the plan's hospital network: {pct}% of the cost stays with you."
        in_list = destination and any(destination.casefold() == n.casefold() for n in listed)
        if rules.get("network_tiered") and listed and destination and not in_list:
            detail += (
                f" {destination} is not on that list, so every hospital in {destination} is covered"
                " in full (reasonable and customary costs)."
            )
        elif rules.get("provider_list_supplied"):
            where = f"{destination} is on that list: check" if in_list else "Check"
            detail += f" {where} the hospital in the providers list (included with this analysis) before any planned admission."
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
    if rules.get("preauth_or_no_payment"):
        items = rules.get("preauth_items") or []
        if items:
            detail = f"Without pre-authorisation the cost is not covered for: {_join_items(items)}."
        else:
            nights = rules.get("preauth_inpatient_nights")
            stays = f"hospital stays of {nights}+ nights" if nights else "hospital stays"
            detail = (
                f"Treatment the guide marks for pre-authorisation (such as {stays}, advanced imaging"
                " and cancer treatment) may not be paid at all if it was not pre-authorised."
            )
        if rules.get("emergency_notice_hours"):
            detail += f" In an emergency, ask the hospital to contact the insurer within {rules['emergency_notice_hours']} hours of admission."
        out.append({"topic": "Pre-authorisation", "detail": detail, "source": "plan documents"})
    amount = rules.get("pre_approval_threshold")
    if amount:
        detail = f"Any treatment costing more than €{amount} needs pre-approval"
        if rules.get("pre_approval_lead_days"):
            detail += f", requested at least {rules['pre_approval_lead_days']} days before treatment"
        detail += "; otherwise a penalty is deducted from the reimbursement."
        out.append({"topic": f"Pre-approval above €{amount}", "detail": detail, "source": "plan documents"})
    return out


def localise_access_rows(results: list[dict], client_profile: str) -> list[dict]:
    """Rewrite each plan's rule rows for the country the client lives in.

    Telling a family moving to France that French hospitals are all covered in
    full (because France has no restricted hospitals on the list) is more useful
    than "check the providers list".
    """
    out = []
    for result in results or []:
        analysis = result.get("analysis") or {}
        rules = analysis.get("access_rules") or {}
        listed = rules.get("network_listed_countries") or []
        destination = destination_country(client_profile, listed) if listed else ""
        if not destination:
            out.append(result)
            continue
        fresh = {row["topic"]: row for row in access_rule_limitations(rules, destination)}
        rows = [
            fresh.get(item.get("topic"), item)
            if isinstance(item, dict) and item.get("source") == "plan documents" else item
            for item in analysis.get("critical_limitations") or []
        ]
        out.append({**result, "analysis": {**analysis, "critical_limitations": rows}})
    return out


def apply_access_rules(result: dict, plan_text: str) -> dict:
    """Store the rules and put them at the top of the plan's critical limitations."""
    normalise_inpatient_scope(result, plan_text)
    drop_contradicted_limitations(result)
    ground_benefit_amounts(result, plan_text)
    ground_shared_limits(result, plan_text)
    rules = extract_access_rules(plan_text)
    if not rules:
        return result
    result["access_rules"] = rules
    rows = access_rule_limitations(rules)
    # Drop the model's own paraphrase of the same rule so it is not listed twice.
    duplicates, duplicate_topics = [], []
    if rules.get("network_copayment_pct"):
        duplicates.append(r"(?:network|tier|listed)[^.;]{0,160}\b\d{1,2}\s*%|\b\d{1,2}\s*%[^.;]{0,160}(?:network|tier|remain at)")
        duplicate_topics.append(r"\bnetwork\b|\btier\b|hospital access|providers? list")
    if rules.get("hospital_prior_approval_penalty_pct"):
        duplicates.append(r"hospitali[sz]\w*[^.;]{0,80}(?:prior|pre-?)\s?approval|(?:prior|pre-?)\s?approval[^.;]{0,80}hospitali[sz]")
    if rules.get("preauth_or_no_payment"):
        duplicates.append(r"^pre-?\s?authori[sz]ation(?! limit)")
        duplicate_topics.append(r"pre-?\s?authori[sz]ation(?! limit)")
    if rules.get("pre_approval_threshold"):
        duplicates.append(r"pre-?\s?approval[^.;]{0,80}(?:€|eur|\$)\s*\d|(?:€|eur|\$)\s*\d[\d,.]*[^.;]{0,80}pre-?\s?approval")

    def is_duplicate(item) -> bool:
        if isinstance(item, dict):
            topic = str(item.get("topic") or "")
            text = f"{topic}: {item.get('detail') or ''}"
        else:
            topic, text = "", str(item or "")
        return any(re.search(p, text, re.I) for p in duplicates) or any(re.search(p, topic, re.I) for p in duplicate_topics)

    kept = [x for x in (result.get("critical_limitations") or []) if not is_duplicate(x)]
    result["critical_limitations"] = rows + kept
    return result


# The APRIL quote labels its hospital row "Hospitalisation Services in case of
# Accident or Emergency", while the Table of Benefits covers all in-patient and
# day-patient treatment (planned or emergency) subject to prior approval.
_ACCIDENT_ONLY = re.compile(r"hospitali[sz]ation services in case of accident or emergency", re.I)


def normalise_inpatient_scope(result: dict, plan_text: str) -> dict:
    benefits = result.get("benefits") or {}
    inpatient = str(benefits.get("inpatient") or "")
    t = _flat(plan_text)
    if (
        _ACCIDENT_ONLY.search(inpatient)
        and re.search(r"hospital services or day-patient treatment", t, re.I)
        and re.search(r"hospitali[sz]ations? (?:are|is) subject to prior approval", t, re.I)
    ):
        benefits["inpatient"] = _ACCIDENT_ONLY.sub(
            "Hospital services and day-patient treatment (planned or emergency; prior approval required)", inpatient
        )
    return result


_SELECTED_BENEFIT_WORDS = {"maternity": r"maternity|pregnan", "dental": r"\bdental\b", "optical": r"\boptical\b"}


def drop_contradicted_limitations(result: dict) -> dict:
    """Remove a 'not selected / not covered' limitation for a benefit the same
    extraction shows as included with an amount (a misread quote column)."""
    benefits = result.get("benefits") or {}
    covered = {
        key for key, value in benefits.items()
        if key in _SELECTED_BENEFIT_WORDS
        and re.search(r"(?:€|eur|\$|£)\s?\d|\d\s?%", str(value or ""), re.I)
        and not re.match(r"\s*not (?:covered|selected)", str(value or ""), re.I)
    }
    if not covered:
        return result
    kept = []
    for item in result.get("critical_limitations") or []:
        topic = str(item.get("topic") if isinstance(item, dict) else item or "")
        detail = str(item.get("detail") if isinstance(item, dict) else "")
        whole = f"{topic} {detail}"
        contradicted = any(
            re.search(_SELECTED_BENEFIT_WORDS[k], topic, re.I) and re.search(r"not selected|not (?:been )?included", whole, re.I)
            for k in covered
        )
        if not contradicted:
            kept.append(item)
    result["critical_limitations"] = kept
    return result


_SHARED_CLAIM = re.compile(r",?\s*\b(?:shared|combined)\s+(?:across|between|by|among|for)\s+", re.I)
_COUNT_BEFORE = re.compile(r"\b(?P<n>\d{1,3})\s*(?:visits?|consultations?|sessions?|treatments?|per (?:policy |insurance )?year|a year|each (?:policy )?year)", re.I)


def ground_shared_limits(result: dict, plan_text: str) -> dict:
    """A visit limit is per benefit unless the documents say it is shared.

    Summary documents (Bupa IPID: "15 visits: specialists' consultations,
    doctors' fees, qualified nurses, mental health, ...") list several benefits
    after one number; the member guide gives each benefit its own 15. A
    "shared across" claim is kept only when the documents use shared/combined/
    in total near that number.
    """
    t = _flat(plan_text)
    if not t:
        return result

    def supported(n: str) -> bool:
        for m in re.finditer(rf"\b{n}\s*(?:visits?|consultations?|sessions?|treatments?)\b", t, re.I):
            window = t[max(0, m.start() - 250): m.end() + 250]
            if re.search(r"\bshared\b|\bcombined\b|\bin total\b|\baltogether\b", window, re.I):
                return True
        return False

    def fix(text: str) -> str:
        out, last = [], 0
        for m in _SHARED_CLAIM.finditer(text):
            before = text[max(0, m.start() - 90): m.start()]
            counts = list(_COUNT_BEFORE.finditer(before))
            if not counts or supported(counts[-1].group("n")):
                continue
            out.append(text[last:m.start()] + " for each of ")
            last = m.end()
        if not out:
            return text
        fixed = "".join(out) + text[last:]
        result.setdefault("extraction_warnings", []).append(
            f"Visit limit is per benefit in the documents, not shared: {text[:160]}"
        )
        return fixed

    for item in result.get("critical_limitations") or []:
        if isinstance(item, dict) and item.get("detail"):
            item["detail"] = fix(str(item["detail"]))
    benefits = result.get("benefits") or {}
    for key, value in list(benefits.items()):
        if isinstance(value, str) and _SHARED_CLAIM.search(value):
            benefits[key] = fix(value)
    return result


_MONEY_IN_CLAUSE = re.compile(r"(?:€|eur|usd|us\$|\$|£|gbp)\s?(\d[\d,.]*\d|\d)", re.I)
_GROUNDING_KEYWORDS = {"evacuation_repatriation": r"evacuat|repatriat|transport"}


def ground_benefit_amounts(result: dict, plan_text: str, window: int = 800) -> dict:
    """Drop a money figure the model attached to the wrong benefit.

    A clause is kept only if its amount appears in the plan documents within
    ``window`` characters of that benefit's own wording. (Bupa: the transplant
    limit "each condition up to EUR 250,000" sits above the transport section
    and was read as an evacuation limit.)
    """
    benefits = result.get("benefits") or {}
    text = str(plan_text or "")
    if not text:
        return result

    def grounded(clause: str, anchors: list[int]) -> bool:
        for amount in (a.replace(",", "").replace(".", "") for a in _MONEY_IN_CLAUSE.findall(clause)):
            # Some PDFs extract every glyph twice ("EUREUR 125125"); accept that form too.
            spots = [
                m.start() for m in re.finditer(r"\d[\d,.]*", text)
                if m.group(0).replace(",", "").replace(".", "") in (amount, amount * 2)
            ]
            if not any(abs(s - a) <= window for s in spots for a in anchors):
                return False
        return True

    for key, keyword in _GROUNDING_KEYWORDS.items():
        anchors = [m.start() for m in re.finditer(keyword, text, re.I)]
        kept_rows = []
        for item in result.get("critical_limitations") or []:
            topic = str(item.get("topic") or "") if isinstance(item, dict) else ""
            detail = str(item.get("detail") or "") if isinstance(item, dict) else str(item or "")
            if re.search(keyword, topic, re.I) and _MONEY_IN_CLAUSE.search(detail) and not grounded(detail, anchors):
                result.setdefault("extraction_warnings", []).append(f"Removed limitation not found in the documents: {topic}: {detail[:160]}")
                continue
            kept_rows.append(item)
        if "critical_limitations" in result:
            result["critical_limitations"] = kept_rows

    for key, keyword in _GROUNDING_KEYWORDS.items():
        value = str(benefits.get(key) or "")
        if not _MONEY_IN_CLAUSE.search(value):
            continue
        anchors = [m.start() for m in re.finditer(keyword, text, re.I)]
        kept, dropped = [], []
        for clause in re.split(r"(?<=[.;])\s+", value):
            amounts = [a.replace(",", "").replace(".", "") for a in _MONEY_IN_CLAUSE.findall(clause)]
            ok = True
            for amount in amounts:
                # Some PDFs extract every glyph twice ("EUREUR 125125"); accept that form too.
                spots = [
                    m.start() for m in re.finditer(r"\d[\d,.]*", text)
                    if m.group(0).replace(",", "").replace(".", "") in (amount, amount * 2)
                ]
                if not any(abs(s - a) <= window for s in spots for a in anchors):
                    ok = False
                    break
            (kept if ok else dropped).append(clause)
        if dropped and kept:
            benefits[key] = " ".join(kept).strip()
            result.setdefault("extraction_warnings", []).append(
                f"{key}: removed a figure not found near this benefit in the documents — " + " ".join(dropped)[:200]
            )
    return result
