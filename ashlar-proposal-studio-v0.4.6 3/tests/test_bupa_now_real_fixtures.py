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
