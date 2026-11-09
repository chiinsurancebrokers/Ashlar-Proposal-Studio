from core import travel_proposal as tp


def test_greek_content_and_figures():
    h = tp.render_html(tp.ARUBA_DEMO)
    for s in ("Ταξιδιωτική", "€73,74", "€10.000.000", "164521", "Cega Medical Assistance Team", "άρθρο 28", "60 μήνες"):
        assert s in h
    assert 'lang="el"' in h


def test_ashlar_system_only():
    h = tp.render_html(tp.ARUBA_DEMO)
    assert "border-radius" not in h and "#D97757" not in h and "#1B2432" in h and "#70181C" in h


def test_links_present():
    h = tp.render_html(tp.ARUBA_DEMO)
    assert "quote.europesuretravelinsurance.com/RetrieveQuote" in h and "ashlarassurance.com/travel-insurance" in h


def test_no_stray_latin_in_greek_benefits():
    names = [n for _, rows in tp.ARUBA_DEMO.benefits for n, _ in rows]
    assert all(not any(c.isascii() and c.isalpha() for c in n) for n in names)


def test_fonts_embedded_cover_greek():
    css = tp.embedded_fonts_css()
    assert "U+0370-03FF" in css and "Noto Serif" in css


def test_personal_version_has_no_demo_wording_and_new_number():
    h = tp.render_html(tp.ZENOVIA).lower()
    assert "δοκιμαστικ" not in h and "164521" not in h and "165318" in h
    assert "γουμένου" in h and "15.000" in h
