from core.claim_cost import claim_cost_rows, has_claim_costs, parse_deductible, ranking_note


def _opt(provider, plan, amount, freq, deductible, currency="EUR"):
    return {"analysis": {"provider": provider, "plan_name": plan,
                         "premium": {"amount": amount, "currency": currency, "frequency": freq},
                         "deductible_or_excess": deductible}}


def test_parses_the_wordings_the_extractors_produce():
    d = parse_deductible("€2,500 deductible/excess Out-patient deductible €330")
    assert (d["main"], d["outpatient"]) == (2500.0, 330.0)
    d = parse_deductible("€400 annual deductible, applies to in-patient and day-patient care only; no deductible is stated for out-patient care")
    assert (d["main"], d["outpatient"]) == (400.0, None)
    d = parse_deductible("€2.500 One deductible applies per person per policy year, with a maximum of two deductibles per family policy per year")
    assert d["main"] == 2500.0 and d["per_person"] is True and d["family_max"] == 2


def test_no_deductible_is_zero_and_unreadable_is_none():
    assert parse_deductible("No deductible")["main"] == 0.0
    assert parse_deductible("Not specified")["main"] is None
    assert parse_deductible("Choice of €500, €1,000 or €2,500")["main"] is None


def test_total_is_premium_plus_one_deductible():
    rows = claim_cost_rows([
        _opt("Bupa", "Select", "1077.06", "Monthly", "€2,500 deductible/excess Out-patient deductible €330"),
        _opt("IMG", "Bronze Plus", "456.72", "Monthly", "€300 deductible/excess"),
    ])
    bupa, img = rows
    assert bupa["premium"] == 12924.72 and bupa["total"] == 15424.72 and bupa["total_with_outpatient"] == 15754.72
    assert img["total"] == 5780.64 and img["total_with_outpatient"] is None


def test_family_maximum_only_when_stated():
    rows = claim_cost_rows([
        _opt("VUMI", "Priority", "3878.95", "Annual", "€2.500 One deductible applies per person per policy year, with a maximum of two deductibles per family"),
        _opt("Other", "Plan", "100", "Monthly", "€500 deductible"),
    ])
    assert rows[0]["total"] == 6378.95 and rows[0]["total_family_max"] == 8878.95
    assert rows[1]["total_family_max"] is None


def test_no_total_when_currencies_differ_or_parts_are_missing():
    rows = claim_cost_rows([
        _opt("A", "x", "100", "Monthly", "$500 deductible"),
        _opt("B", "y", "100", "Monthly", "Not specified"),
        {"analysis": {"provider": "C", "plan_name": "z", "deductible_or_excess": "€300"}},
    ])
    assert [r["total"] for r in rows] == [None, None, None]
    assert not has_claim_costs(rows)


def test_ranking_changes_once_the_deductible_is_added():
    rows = claim_cost_rows([
        _opt("VUMI", "Priority", "3878.95", "Annual", "€2,500 deductible"),
        _opt("IMG", "Bronze", "456.72", "Monthly", "€300 deductible"),
    ])
    note = ranking_note(rows)
    assert note["changed"] and note["by_premium"].startswith("VUMI") and note["by_total"].startswith("IMG")
