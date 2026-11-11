from core.benefit_state import COVERED, NOT_COVERED, SUB_LIMIT, classify


def test_not_covered_with_an_accident_exception_is_not_shown_as_covered():
    cell = ("Not covered. Dental treatment is listed as not covered (quote p.4). Exception: accident-related "
            "dental treatment needed in hospital after a serious accident is paid in full (Membership Guide p.12).")
    assert classify(cell) == SUB_LIMIT


def test_routine_not_covered_with_emergency_exception():
    cell = "Not covered for routine dental care (Quotation p6). In-patient emergency dental treatment is a full refund (Quotation p4)."
    assert classify(cell) == SUB_LIMIT


def test_emergency_only_is_a_condition():
    assert classify("Emergency dental treatment only, at 100% UCR (p5). Routine dental is not mentioned.") == SUB_LIMIT


def test_plain_absence_and_plain_cover_are_unchanged():
    assert classify("Not covered") == NOT_COVERED
    assert classify("Included. Paid in full with a standard private room.") == COVERED
    assert classify("Included. Paid in full, no limit. Orthodontics are not covered.") == COVERED
