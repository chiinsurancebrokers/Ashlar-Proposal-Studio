import json

from core.json_utils import parse_first_json_object


def test_plain_json():
    assert parse_first_json_object('{"plan":"Silver"}') == {"plan": "Silver"}


def test_markdown_fence():
    raw = '```json\n{"plan":"Silver","limit":3000000}\n```'
    assert parse_first_json_object(raw)["plan"] == "Silver"


def test_trailing_text_does_not_raise_extra_data():
    raw = '{"plan":"Silver"}\nI have also checked the source table.'
    assert parse_first_json_object(raw) == {"plan": "Silver"}


def test_second_json_object_is_ignored():
    raw = '{"plan":"Silver"}\n{"note":"duplicate accidental output"}'
    assert parse_first_json_object(raw) == {"plan": "Silver"}


def test_preamble_before_json():
    raw = 'Here is the requested structured result:\n{"plan":"Silver"}'
    assert parse_first_json_object(raw) == {"plan": "Silver"}


def test_invalid_output_still_raises():
    try:
        parse_first_json_object('not json at all')
    except json.JSONDecodeError:
        return
    raise AssertionError('Expected JSONDecodeError')


def test_parse_best_json_object_prefers_report_schema_over_small_object():
    from core.json_utils import parse_best_json_object

    raw = '''
    {"provider":"Bupa Global","client_age":18}
    {"report_title":"Comparison","executive_summary":"Summary","plans":[{"provider":"Bupa Global","plan_name":"SELECT"}],"ashlar_assessment":{"headline":"View","reasoning":["Reason"]},"next_steps":["Apply"],"disclaimer":"Terms apply"}
    '''
    out = parse_best_json_object(
        raw,
        required_keys=("report_title","executive_summary","plans","ashlar_assessment","next_steps","disclaimer"),
    )
    assert out["report_title"] == "Comparison"
    assert out["plans"][0]["plan_name"] == "SELECT"
