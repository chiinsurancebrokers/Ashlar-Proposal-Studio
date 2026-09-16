import pytest

from core.client_analysis import (
    _complete_report_object,
    _recommended_report_max_tokens,
)
from core.report_schema import ClientReportValidationError


def test_four_plan_budget_is_larger_than_old_4500_limit():
    assert _recommended_report_max_tokens(4) >= 9000


def test_truncated_outer_json_does_not_accept_nested_plan_object():
    raw = '''{
      "report_title":"Comparison",
      "executive_summary":"Summary",
      "plans":[{"provider":"Bupa","plan_name":"SELECT","summary":"Text"}],
      "ashlar_assessment":{"headline":"View","reasoning":["Reason"]}
    '''
    with pytest.raises(ClientReportValidationError, match="complete client-report"):
        _complete_report_object(raw)


def test_complete_report_candidate_is_selected():
    raw = '''
    {"provider":"Bupa","plan_name":"SELECT"}
    {"report_title":"Comparison","executive_summary":"Summary","plans":[{"provider":"Bupa","plan_name":"SELECT","summary":"Text"}],"ashlar_assessment":{"headline":"View","reasoning":["Reason"]},"next_steps":["Apply"],"disclaimer":"Terms apply"}
    '''
    out = _complete_report_object(raw)
    assert out["report_title"] == "Comparison"
