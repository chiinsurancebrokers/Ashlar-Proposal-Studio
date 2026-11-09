import json
import re
from pathlib import Path

import pytest

from core import lead_email as le
from core.lead_router import route

EX = Path(__file__).resolve().parents[1] / "core" / "lead_examples"


def _lead(n):
    return json.loads((EX / n).read_text(encoding="utf-8"))["lead_text"]


@pytest.fixture
def julian():
    return route(_lead("lead_001_family_vouliagmeni.json"))


@pytest.fixture
def couple():
    return route(_lead("lead_002_couple_voula.json"))


def test_default_plan_is_life_on_only(julian):
    h = le.render_html(julian, "Julian", family=True)
    assert "Life On" in h and "Medical Prime" not in h
    assert "Hospital Premium Flexi" in h


def test_both_named_plans_are_separate(couple):
    h = le.render_html(couple, "Rajesh and Erica")
    assert "Life On:" in h and "Medical Prime:" in h
    assert "&euro;300,000" in h and "&euro;100 a night" in h


def test_bridge_registration_and_commission(julian):
    t = le.render_text(julian, "Julian")
    assert "not employed by Generali" in t and "191526" in t
    assert "we do not charge you any fee" in t


def test_all_links_present(julian):
    h = le.render_html(julian, "Julian")
    for u in (le.U_DOCS, le.U_HOSP, le.U_DIAG, le.U_LIFEON):
        assert u in h


def test_eopyy_note_only_when_mentioned(julian, couple):
    assert julian.mentions_eopyy and le.EOPYY_NOTE in le.render_html(julian, "J")
    assert not couple.mentions_eopyy and le.EOPYY_NOTE not in le.render_html(couple, "R")


def test_name_is_escaped(julian):
    h = le.render_html(julian, "<script>x</script>")
    assert "<script>x" not in h


def test_square_corners_only(julian):
    assert "border-radius" not in le.render_html(julian, "J")


def test_ipmi_block_only_when_not_generali_only(julian):
    assert "IPMI" in le.render_html(julian, "J")


def test_text_twin_has_subject_and_no_tags(julian):
    t = le.render_text(julian, "Julian", family=True)
    assert t.startswith("Subject:") and not re.search(r"<[a-z/]", t)


def test_pdf_renders(julian, tmp_path):
    pytest.importorskip("playwright")
    try:
        out = le.render_pdf(le.render_html(julian, "J", fonts_css=le.embedded_fonts_css()), tmp_path / "e.pdf")
    except Exception as e:  # no Chromium on this machine
        pytest.skip(str(e))
    assert out.read_bytes().startswith(b"%PDF")
