from core.case_runner import carry_over_manual_overrides


def _r(provider, plan, **analysis):
    return {"provider": provider, "target_plan": plan, "analysis": {"provider": provider, "plan_name": plan, **analysis}}


def test_corrections_survive_a_rerun_and_other_fields_refresh():
    old = [_r("NOW HEALTH", "SimpleCare 100",
              premium={"amount": "202.08", "currency": "EUR", "frequency": "Monthly"},
              deductible_or_excess="EUR 400, in-patient only", area_of_cover="Europe",
              manual_overrides=["premium", "deductible_or_excess"])]
    new = [_r("NOW HEALTH", "SimpleCare 100",
              premium={"amount": "202.08", "currency": "EUR", "frequency": "Annual"},
              deductible_or_excess="$500", area_of_cover="Europe", annual_limit="EUR 1,000,000")]
    out = carry_over_manual_overrides(old, new)[0]["analysis"]
    assert out["premium"]["frequency"] == "Monthly"
    assert out["deductible_or_excess"] == "EUR 400, in-patient only"
    assert out["annual_limit"] == "EUR 1,000,000"
    assert out["manual_overrides"] == ["deductible_or_excess", "premium"]


def test_other_options_are_not_touched():
    old = [_r("Bupa", "Select", area_of_cover="Europe", manual_overrides=["area_of_cover"])]
    new = [_r("IMG", "Bronze Plus", area_of_cover="Worldwide")]
    out = carry_over_manual_overrides(old, new)[0]["analysis"]
    assert out["area_of_cover"] == "Worldwide"
    assert "manual_overrides" not in out


def test_no_previous_results_is_a_noop():
    new = [_r("IMG", "Bronze Plus")]
    assert carry_over_manual_overrides([], new) == new
