import json
from types import SimpleNamespace

from core import plan_reader as pr, plan_quality
from core.family_bridge import offer_from_result, benefit_state

DOCS = {
    "quote.pdf": ("Generali Life On Hospital Premium Flexi. Monthly premium: EUR 132,49 including taxes.\n"
                  "Annual deductible per insured person: EUR 1.500,00. Annual limit EUR 1.000.000 for hospital treatment worldwide."),
    "tob.pdf": ("Cancer treatment: covered in full up to EUR 300.000 per year.\n"
                "Dental treatment: Not covered.\n"
                "Appendectomy: the first three (3) months of the first insurance year."),
}


def good():
    return {
        "provider": "Generali", "plan_name": "Hospital Premium Flexi", "currency": "EUR",
        "premium": {"amount": 132.49, "frequency": "monthly", "includes_tax": True,
                    "quote": "Monthly premium: EUR 132,49 including taxes", "source": "quote.pdf"},
        "deductible": {"amount": 1500, "quote": "Annual deductible per insured person: EUR 1.500,00", "source": "quote.pdf"},
        "limit": {"amount": 1000000, "quote": "Annual limit EUR 1.000.000 for hospital treatment worldwide", "source": "quote.pdf"},
        "area": {"value": "world", "quote": "for hospital treatment worldwide", "source": "quote.pdf"},
        "benefits": {
            "cancer": {"en": "Covered in full up to EUR 300,000", "el": "Καλύπτεται έως €300.000",
                       "quote": "Cancer treatment: covered in full up to EUR 300.000 per year", "source": "tob.pdf"},
            "dental": {"en": "Not covered", "el": "Δεν καλύπτεται",
                       "quote": "Dental treatment: Not covered", "source": "tob.pdf"},
        },
        "waiting": [{"condition_en": "Appendectomy", "condition_el": "Σκωληκοειδεκτομή",
                     "period_en": "The first three (3) months of the first insurance year",
                     "period_el": "Τους τρεις (3) πρώτους μήνες",
                     "quote": "Appendectomy: the first three (3) months of the first insurance year", "source": "tob.pdf"}],
    }


def test_good_reading_is_fully_verified():
    r = pr.verify(good(), DOCS)
    assert r.problems() == []
    assert r.premium.value == 132.49 and r.deductible.value == 1500.0 and r.limit.value == 1000000.0
    assert all(b.status == pr.VERIFIED for b in r.benefits)


def test_invented_quote_is_rejected_and_left_out_of_the_result():
    raw = good()
    raw["premium"]["quote"] = "Monthly premium: EUR 99,00 including taxes"
    raw["premium"]["amount"] = 99
    r = pr.verify(raw, DOCS)
    assert r.premium.status == pr.UNVERIFIED and not r.premium.usable
    assert "premium" not in pr.to_result(r)["analysis"]
    assert offer_from_result("x", pr.to_result(r), ["a"])[0] is None


def test_number_not_in_its_quote_is_rejected():
    raw = good()
    raw["limit"]["amount"] = 3000000          # the quote says 1.000.000
    assert pr.verify(raw, DOCS).limit.status == pr.UNVERIFIED


def test_benefit_amount_must_be_in_quote():
    raw = good()
    raw["benefits"]["cancer"]["en"] = "Covered in full up to EUR 500,000"
    cell = [b for b in pr.verify(raw, DOCS).benefits if b.key == "cancer"][0]
    assert cell.status == pr.UNVERIFIED


def test_quote_survives_line_breaks_and_case():
    assert pr.in_source("monthly  premium:\nEUR 132,49", DOCS["quote.pdf"])


def test_unreadable_waiting_period_is_unverified():
    raw = good()
    raw["waiting"][0]["period_en"] = "a while"
    assert pr.verify(raw, DOCS).waiting[0].status == pr.UNVERIFIED


def test_missing_frequency_blocks_premium():
    raw = good()
    raw["premium"]["frequency"] = ""
    assert not pr.verify(raw, DOCS).premium.usable


def test_broker_can_approve_an_unverified_item():
    raw = good()
    raw["limit"]["amount"] = 3000000
    r = pr.approve(pr.verify(raw, DOCS), ["limit"])
    assert r.limit.usable and pr.to_quality(r, key="t1").limit == 3000000.0


def test_to_result_feeds_the_bridge_with_classified_states():
    result = pr.to_result(pr.verify(good(), DOCS))
    offer, why = offer_from_result("o", result, ["katja"])
    assert offer is not None, why
    assert round(float(offer.yearly), 2) == round(132.49 * 12, 2) if hasattr(offer, "yearly") else True
    assert benefit_state(result["analysis"]["benefits"]["cancer"]) == "sub_limit"
    assert benefit_state(result["analysis"]["benefits"]["dental"]) == "not_covered"


def test_to_quality_registers_a_table_the_merit_score_can_read():
    q = pr.to_quality(pr.verify(good(), DOCS), key="gen_flexi", network=4)
    assert q.area == "world" and q.network == 4 and q.exclusions is None
    assert plan_quality.waiting_months(q.waiting_tables) == 3.0
    assert plan_quality.scores(q)["waiting"] is not None


def test_builtin_table_cannot_be_overwritten():
    import pytest
    from core import waiting_periods as wp
    with pytest.raises(ValueError):
        wp.register_table(wp.HOSPITAL, {"en": "x", "el": "x"}, {"en": "x", "el": "x"}, [])


class _Client:
    def __init__(self, text=None, exc=None):
        self.messages, self._t, self._e = self, text, exc

    def create(self, **kw):
        if self._e:
            raise self._e
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._t)])


def test_read_plan_with_fake_client():
    r, why = pr.read_plan(DOCS, client=_Client("Here:\n```json\n" + json.dumps(good()) + "\n```"))
    assert why == "" and r.label == "Generali Hospital Premium Flexi" and r.problems() == []


def test_read_plan_reports_model_failure_and_empty_input():
    r, why = pr.read_plan(DOCS, client=_Client(exc=RuntimeError("boom")))
    assert r is None and "plan reading" in why.lower()
    assert pr.read_plan({"a": "  "}, client=_Client("{}"))[0] is None


def test_garbage_reply_is_reported_not_raised():
    r, why = pr.read_plan(DOCS, client=_Client("no json at all"))
    assert r is None and why
