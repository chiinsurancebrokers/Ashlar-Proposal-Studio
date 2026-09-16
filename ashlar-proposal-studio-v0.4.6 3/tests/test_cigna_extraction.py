from pathlib import Path

import pytest

from core.brochure_tables import extract_target_plan_from_pdf
from core.analyzer import _apply_deterministic_facts
from core.extract import extract_document


CIGNA_BROCHURE = Path('/mnt/data/591050 CGHO Sales Brochure Broker EN 02_2026.pdf')
CIGNA_QUOTE = Path('/mnt/data/QQQ5349749-Ioannis_Konstantinidis.pdf')


@pytest.mark.skipif(not CIGNA_BROCHURE.exists(), reason='Cigna fixture not available')
def test_cigna_silver_continuation_tables():
    extracted = extract_target_plan_from_pdf(CIGNA_BROCHURE, 'Silver')
    labels = {row.benefit: row.value for row in extracted.rows}
    assert len(extracted.rows) >= 76
    assert any('Annual overall benefit maximum' in k and '€800,000' in v for k, v in labels.items())
    assert any('Annual International Outpatient benefit maximum' in k and '€12,000' in v for k, v in labels.items())
    assert any('Annual Dental benefit maximum' in k and '€930' in v for k, v in labels.items())


@pytest.mark.skipif(not (CIGNA_BROCHURE.exists() and CIGNA_QUOTE.exists()), reason='Cigna fixtures not available')
def test_cigna_headline_facts_are_locked_deterministically():
    focused = extract_target_plan_from_pdf(CIGNA_BROCHURE, 'Silver').to_prompt_context()
    quote = extract_document(CIGNA_QUOTE, CIGNA_QUOTE.name)
    assert quote.ok
    result = {
        'premium': {'amount': None, 'currency': None, 'frequency': None},
        'annual_limit': None,
        'deductible_or_excess': None,
        'area_of_cover': None,
        'benefits': {},
    }
    result = _apply_deterministic_facts(result, 'CIGNA', quote.text, focused)
    assert result['premium']['amount'] == '2389.83'
    assert result['premium']['currency'] == 'EUR'
    assert '€800,000' in result['annual_limit']
    assert '€0 deductible' in result['deductible_or_excess']
    assert result['area_of_cover'] == 'Worldwide excluding USA'
    assert '€12,000' in result['benefits']['outpatient']
    assert '€930' in result['benefits']['dental']
