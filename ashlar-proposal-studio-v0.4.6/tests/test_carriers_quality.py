from pathlib import Path

from core.carriers import get_carrier_adapter
from core.extract import extract_document
from core.quality import assess_result_quality


CIGNA_QUOTE = Path('/mnt/data/QQQ5349749-Ioannis_Konstantinidis.pdf')


def test_adapter_registry_detects_carriers():
    assert get_carrier_adapter('CIGNA').carrier_id == 'cigna'
    assert get_carrier_adapter('IMG (International Medical Group)').carrier_id == 'img'
    assert get_carrier_adapter('Bupa Global').carrier_id == 'bupa'
    assert get_carrier_adapter('NOW Health International').carrier_id == 'now_health'
    assert get_carrier_adapter('Unknown Carrier').carrier_id == 'generic'


def test_generic_bupa_style_quote_facts():
    text = '''Bupa Global\nAnnual premium EUR 4,250.00\nExcess EUR 500\nArea of cover Worldwide excluding USA\n'''
    facts = get_carrier_adapter('Bupa Global').extract_quote_facts(text)
    assert facts['premium']['amount'] == '4250.00'
    assert facts['premium']['currency'] == 'EUR'
    assert '€500' in facts['deductible_or_excess']
    assert facts['area_of_cover'] == 'Worldwide excluding USA'


def test_generic_now_health_style_quote_facts():
    text = '''NOW Health International\nTotal annual premium EUR 1,920.50\nAnnual deductible EUR 250\nCoverage area Worldwide excluding USA\n'''
    facts = get_carrier_adapter('NOW Health').extract_quote_facts(text)
    assert facts['premium']['amount'] == '1920.50'
    assert '€250' in facts['deductible_or_excess']
    assert facts['area_of_cover'] == 'Worldwide excluding USA'


def test_cigna_quote_adapter_on_real_fixture():
    if not CIGNA_QUOTE.exists():
        return
    extracted = extract_document(CIGNA_QUOTE, CIGNA_QUOTE.name)
    assert extracted.ok
    facts = get_carrier_adapter('CIGNA').extract_quote_facts(extracted.text)
    assert facts['premium']['amount'] == '2389.83'
    assert facts['quoted_plan'] == 'Silver'
    assert facts['area_of_cover'] == 'Worldwide excluding USA'
    assert {'outpatient', 'evacuation', 'wellbeing', 'vision_dental'}.issubset(facts['selected_modules'])


def test_quality_gate_blocks_materially_empty_analysis():
    result = {
        'provider': 'Bupa',
        'target_plan': '',
        'focused_rows': [],
        'analysis': {
            'premium': {'amount': None},
            'annual_limit': None,
            'deductible_or_excess': None,
            'area_of_cover': None,
            'benefits': {},
            'confidence': 'low',
        },
    }
    q = assess_result_quality(result)
    assert q['status'] == 'blocked'
    assert not q['can_generate']


def test_quality_gate_allows_complete_evidence():
    result = {
        'provider': 'Cigna',
        'target_plan': 'Silver',
        'focused_rows': [{'benefit': 'x', 'value': 'y'} for _ in range(10)],
        'analysis': {
            'premium': {'amount': '2389.83', 'currency': 'EUR', 'frequency': 'Annual'},
            'annual_limit': '€800,000',
            'deductible_or_excess': '€0 deductible; 0% cost share',
            'area_of_cover': 'Worldwide excluding USA',
            'benefits': {
                'inpatient': 'Covered',
                'outpatient': '€12,000',
                'cancer': 'Covered',
                'chronic_conditions': 'Covered subject to terms',
                'mental_health': '€3,700',
                'evacuation_repatriation': 'Selected',
            },
            'confidence': 'high',
        },
    }
    q = assess_result_quality(result)
    assert q['status'] == 'ready'
    assert q['can_generate']
