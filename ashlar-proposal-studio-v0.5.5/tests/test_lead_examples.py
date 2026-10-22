import json
import pathlib

import pytest

from core.lead_router import draft_reply, route

FILES = sorted(pathlib.Path(__file__).resolve().parent.parent.joinpath("core/lead_examples").glob("*.json"))


def test_examples_exist():
    assert len(FILES) >= 2


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_router_reproduces_saved_example(path):
    ex = json.loads(path.read_text(encoding="utf-8"))
    r = route(ex["lead_text"])
    assert r.track == ex["expected"]["track"]
    assert r.afm == ex["expected"]["afm"]
    assert sorted(h.rule for h in r.gaps) == ex["expected"]["gaps"]
    assert sorted(h.rule for h in r.reviews) == ex["expected"]["reviews"]
    assert draft_reply(r) == ex["reply_draft"]


def test_generated_questions_include_every_question_in_the_approved_reply():
    ex = json.loads(next(p for p in FILES if "lead_001" in p.name).read_text(encoding="utf-8"))
    assert ex["status"] in ("broker_draft", "approved")
    sent = [ln.split(". ", 1)[1] for ln in ex.get("approved_reply") or ex["broker_draft_reply"].splitlines() if ln[:2].rstrip(".").isdigit() and ". " in ln]
    assert len(sent) == 7
    draft = draft_reply(route(ex["lead_text"])).lower()
    for q in sent:
        assert q[:25].lower() in draft, q
