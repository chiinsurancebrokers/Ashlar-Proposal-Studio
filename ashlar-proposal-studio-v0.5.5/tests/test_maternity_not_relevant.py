from core.client_analysis import maternity_relevant
from core.household import applicant_row, maternity_marked_irrelevant, normalise_members


def test_female_applicant_is_relevant_by_default():
    assert maternity_relevant(client_sex="Female", client_age=35, household_members=[]) is True


def test_broker_can_mark_maternity_not_relevant():
    members = [applicant_row(maternity_irrelevant=True)]
    assert maternity_marked_irrelevant(members)
    assert maternity_relevant(client_sex="Female", client_age=35, household_members=members) is False


def test_override_beats_family_signals_and_flagged_dependants():
    members = [applicant_row(maternity_irrelevant=True),
               {"relationship": "Spouse", "sex": "Female", "age": 30, "maternity": True}]
    assert maternity_relevant(client_sex="Female", client_priorities="family, pregnancy", household_members=members) is False


def test_marker_survives_a_save_round_trip_and_does_not_become_a_dependant():
    row = applicant_row(maternity_irrelevant=True)
    assert row == {"relationship": "Main applicant", "dob": "", "nationality": "", "maternity_irrelevant": True}
    dependants, _ = normalise_members([row])
    assert dependants == []


def test_automatic_is_unchanged_when_not_marked():
    assert applicant_row() is None
    assert not maternity_marked_irrelevant([applicant_row(nationality="Greek")])
