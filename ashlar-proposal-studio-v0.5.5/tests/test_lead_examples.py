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
