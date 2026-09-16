from pathlib import Path

from core.analyzer import _apply_deterministic_facts
from core.brochure_tables import extract_target_plan_from_pdf
from core.carriers import get_carrier_adapter
from core.extract import extract_document

CIGNA_BROCHURE = Path('/mnt/data/591050 CGHO Sales Brochure Broker EN 02_2026.pdf')
CIGNA_QUOTE = Path('/mnt/data/QQQ5349749-Ioannis_Konstantinidis.pdf')
NOW_QUOTE = Path('/mnt/data/Quotation-639245740311045530 (1) (1).pdf')


def test_cigna_silver_diagnostics_uses_exact_row_not_private_room():
    if not (CIGNA_BROCHURE.exists() and CIGNA_QUOTE.exists()):
        return
    focused = extract_target_plan_from_pdf(CIGNA_BROCHURE, 'Silver').to_prompt_context()
    quote = extract_document(CIGNA_QUOTE, CIGNA_QUOTE.name)
    result = {
        'benefits': {'diagnostics_imaging': 'Covered (table checkmark); Private room.'},
        'underwriting': {},
    }
    locked = _apply_deterministic_facts(result, 'CIGNA', quote.text, focused)
    value = locked['benefits']['diagnostics_imaging']
    assert '€7,400' in value
    assert 'Private room' not in value


def test_now_health_preventive_is_explicitly_not_wellness():
    if not NOW_QUOTE.exists():
        return
    quote = extract_document(NOW_QUOTE, NOW_QUOTE.name)
    facts = get_carrier_adapter('NOW Health International', quote.text).extract_quote_facts(quote.text)
    value = facts['benefit_hints']['preventive']
    assert value.startswith('Not covered')
    assert 'routine examinations' in value.lower()
    assert 'health screening' in value.lower()
    assert 'no separate wellness benefit' in value.lower()


def test_now_health_preventive_hint_overrides_not_mentioned():
    if not NOW_QUOTE.exists():
        return
    quote = extract_document(NOW_QUOTE, NOW_QUOTE.name)
    result = {'benefits': {'preventive': 'Not mentioned'}, 'underwriting': {}}
    locked = _apply_deterministic_facts(result, 'NOW Health International', quote.text, '')
    assert locked['benefits']['preventive'].startswith('Not covered')
