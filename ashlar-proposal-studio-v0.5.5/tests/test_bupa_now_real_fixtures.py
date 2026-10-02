from pathlib import Path

from core.analyzer import _apply_deterministic_facts
from core.carriers import get_carrier_adapter
from core.extract import extract_document
from core.plan_selector import identify_selected_plan
from core.quality import assess_result_quality

BUPA_QUOTE = Path('/mnt/data/Here’s your Bupa Global quote - xiatropoulos@gmail.com - Gmail.html')
NOW_QUOTE = Path('/mnt/data/Quotation-639245740311045530 (1) (1).pdf')


def test_bupa_real_email_quote_adapter():
    if not BUPA_QUOTE.exists():
        return
    extracted = extract_document(BUPA_QUOTE, BUPA_QUOTE.name)
    assert extracted.ok
    selection = identify_selected_plan(extracted.text, 'Bupa Global')
    facts = get_carrier_adapter('Bupa Global', extracted.text).extract_quote_facts(extracted.text)
    assert selection['plan_name'] == 'Select'
    assert facts['premium']['amount'] == '2165.08'
    assert facts['annual_limit'] == '€1,250,000'
    assert facts['area_of_cover'] == 'Worldwide excluding USA'
    assert '€0 outpatient deductible' in facts['deductible_or_excess']
    assert facts['benefit_hints']['dental'] == 'Not covered on this quotation.'


def test_now_real_quote_adapter():
    if not NOW_QUOTE.exists():
        return
    extracted = extract_document(NOW_QUOTE, NOW_QUOTE.name)
    assert extracted.ok
    selection = identify_selected_plan(extracted.text, 'NOW Health International')
    facts = get_carrier_adapter('NOW Health International', extracted.text).extract_quote_facts(extracted.text)
    assert selection['plan_name'] == 'SimpleCare 250'
    assert facts['premium']['amount'] == '1092.07'
    assert facts['annual_limit'] == '€1,200,000'
    assert facts['area_of_cover'] == 'Worldwide excluding USA'
    assert facts['underwriting_basis'] == 'Full Medical Underwriting'
    assert '€0 in/day-patient' in facts['deductible_or_excess']
    assert '€2,000' in facts['benefit_hints']['outpatient']
    assert '€80,000' in facts['benefit_hints']['evacuation_repatriation']
    assert '€320' in facts['benefit_hints']['mental_health']
    assert '€240' in facts['benefit_hints']['dental']


def test_bupa_and_now_quality_not_blocked_after_deterministic_lock():
    for path, label, target in [
        (BUPA_QUOTE, 'Bupa Global', 'Select'),
        (NOW_QUOTE, 'NOW Health International', 'SimpleCare 250'),
    ]:
        if not path.exists():
            continue
        extracted = extract_document(path, path.name)
        base = {
            'provider': label,
            'plan_name': target,
            'target_plan_found': True,
            'premium': {'amount': None},
            'annual_limit': 'Not specified',
            'deductible_or_excess': 'Not specified',
            'area_of_cover': 'Not specified',
            'underwriting': {'basis': 'Not specified', 'pre_existing_conditions': 'Not specified'},
            'benefits': {},
            'confidence': 'medium',
        }
        locked = _apply_deterministic_facts(base, label, extracted.text, '')
        result = {'provider': label, 'target_plan': target, 'focused_rows': [], 'library_source': {'provider': label}, 'analysis': locked}
        q = assess_result_quality(result)
        assert q['can_generate']
        assert 'premium' not in q['missing_fields']
        assert 'annual limit' not in q['missing_fields']
        assert 'deductible / excess' not in q['missing_fields']
        assert 'area of cover' not in q['missing_fields']


def test_bupa_renewal_pack_multi_component_extraction():
    text = """
    Your health plan renewal
    This is your Insurance Certificate
    Area of cover Worldwide excluding U.S.
    Contract Information
    Plan Annual deductible (EUR) Annual maximum (EUR)
    EEA Worldwide Medical Insurance 6,250.00 2,125,000.00
    EEA Worldwide Medical Plus 125.00 31,250.00
    Underwriting terms Maternity and childbirth is covered after 24 months' membership
    No personal exclusions apply
    Renewal invoice
    Total amount payable (gross) 8,727.32
    EEA Worldwide Medical Insurance 2,681.64 2,681.64
    EEA Worldwide Medical Plus 6,045.68 6,045.68
    Annual amount total in EUR 8,727.32 8,727.32
    Grand total in EUR 8,727.32 8,727.32
    """
    facts = get_carrier_adapter("Current policy", text).extract_quote_facts(text)
    assert facts["quoted_plan"] == "Bupa Global renewal package"
    assert facts["premium"] == {"amount": "8727.32", "currency": "EUR", "frequency": "Annual"}
    assert facts["area_of_cover"] == "Worldwide excluding U.S."
    assert len(facts["components"]) == 2
    assert "€6,250.00" in facts["deductible_or_excess"]
    assert "€2,125,000.00" in facts["annual_limit"]
    assert facts["benefit_hints"]["maternity"].startswith("Covered after 24 months")
    assert facts["pre_existing_conditions"] == "No personal exclusions apply."
    assert len(facts["component_premiums"]) == 2
