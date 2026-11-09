"""Plan-table extraction on a synthetic IMG-style grid:
header spelled "GoldPlus", an enumerator column, wrapped multi-line labels and
a shaded (not-applicable) target cell."""
import fitz

from core.brochure_tables import extract_target_plan_from_pdf

COLS = [32, 50, 167, 232, 297, 363, 428, 493, 558]  # enum, label, Bronze..Platinum
HEADERS = ["", "Benefit", "Bronze", "Silver", "Gold", "GoldPlus", "Platinum"]
ROWS = [
    # (enumerator, label lines, {plan col index: text})
    ("1", ["Surgery, Surgeons,", "Consultants and", "Ancillary Charges"], {3: "Full Cover"}),
    ("2", ["Hospitalisation", "/ Room & Board"], {3: "Up $600/day", 5: "Up $900/day"}),
    ("3", ["Intensive Care Unit"], {5: "Up $1,500/day"}),
]


def _build(path):
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    y = 100
    hdr_h = 24
    # header cells: label column spans enum+label
    heads = [(32, 167, "Benefit"), (167, 232, "Bronze"), (232, 297, "Silver"),
             (297, 363, "Gold"), (363, 428, "GoldPlus"), (428, 493, "Platinum")]
    for x0, x1, t in heads:
        page.draw_rect(fitz.Rect(x0, y, x1, y + hdr_h), color=(0, 0, 0), width=0.8)
        page.insert_text((x0 + 4, y + 15), t, fontsize=9)
    y += hdr_h
    for enum, lines, vals in ROWS:
        h = 12 * max(len(lines), 2) + 14
        for i in range(len(COLS) - 1):
            r = fitz.Rect(COLS[i], y, COLS[i + 1], y + h)
            fill = None
            if i == 5 and i not in vals:
                fill = (0.58, 0.70, 0.85)  # shaded n/a cell under GoldPlus
            page.draw_rect(r, color=(0, 0, 0), width=0.8, fill=fill)
        page.insert_text((COLS[0] + 5, y + h / 2 + 3), enum, fontsize=8)
        for k, line in enumerate(lines):
            page.insert_text((COLS[1] + 4, y + 12 + 11 * k), line, fontsize=8)
        for col, text in vals.items():
            page.insert_text((COLS[col] + 4, y + h / 2 + 3), text, fontsize=7)
        y += h
    doc.save(path)
    doc.close()


def test_goldplus_header_matches_spaced_target(tmp_path):
    p = tmp_path / "t.pdf"
    _build(str(p))
    ex = extract_target_plan_from_pdf(p, "Gold Plus")
    assert ex.rows, "header 'GoldPlus' must match target 'Gold Plus'"
    benefits = [r.benefit for r in ex.rows]
    assert not any(b.startswith("Bench") for b in benefits)


def test_wrapped_labels_are_one_row_each(tmp_path):
    p = tmp_path / "t.pdf"
    _build(str(p))
    ex = extract_target_plan_from_pdf(p, "Gold Plus")
    assert len(ex.rows) == 3
    assert "Surgery" in ex.rows[0].benefit and "Ancillary" in ex.rows[0].benefit
    assert "Hospitalisation" in ex.rows[1].benefit and "Room" in ex.rows[1].benefit
    assert ex.rows[2].benefit.startswith("Intensive Care")


def test_values_come_from_target_column_only(tmp_path):
    p = tmp_path / "t.pdf"
    _build(str(p))
    ex = extract_target_plan_from_pdf(p, "Gold Plus")
    vals = [r.value for r in ex.rows]
    assert "Full Cover" not in vals[0]   # Silver's value must not leak in
    assert "900" in vals[1]
    assert "1,500" in vals[2]


def test_shaded_empty_target_cell_is_labelled_not_plain_blank(tmp_path):
    p = tmp_path / "t.pdf"
    _build(str(p))
    ex = extract_target_plan_from_pdf(p, "Gold Plus")
    assert ex.rows[0].evidence_type == "shaded_blank"
    assert "Shaded" in ex.rows[0].value
    assert ex.rows[1].evidence_type != "shaded_blank"


def test_vertically_merged_filled_cell_gives_its_text_to_every_row(tmp_path):
    """'Full Cover' printed once, centred in a tall shaded cell that spans several benefits."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    y0 = 100
    for x0, x1, t in [(32, 167, "Benefit"), (167, 232, "Silver"), (232, 297, "Gold Plus")]:
        page.draw_rect(fitz.Rect(x0, y0, x1, y0 + 24), color=(0, 0, 0), width=0.8)
        page.insert_text((x0 + 4, y0 + 15), t, fontsize=9)
    top = y0 + 24
    names = ["Surgery", "Hospital", "Intensive Care", "Anaesthetist"]
    h = 40
    for i, n in enumerate(names):
        for x0, x1 in [(32, 50), (50, 167), (167, 232)]:
            page.draw_rect(fitz.Rect(x0, top + i * h, x1, top + (i + 1) * h), color=(0, 0, 0), width=0.8)
        page.insert_text((54, top + i * h + 20), n, fontsize=8)
        page.insert_text((36, top + i * h + 20), str(i + 1), fontsize=8)
        # per-row strips of the shaded column, no borders between them
        page.draw_rect(fitz.Rect(232, top + i * h, 297, top + (i + 1) * h),
                       color=None, fill=(0.58, 0.70, 0.85))
    page.insert_text((245, top + 2 * h + 3), "Full Cover", fontsize=8)  # centre of the block
    path = tmp_path / "m.pdf"
    doc.save(str(path))
    ex = extract_target_plan_from_pdf(path, "Gold Plus")
    assert len(ex.rows) == 4
    assert all(r.value == "Full Cover" for r in ex.rows), [r.value for r in ex.rows]
    assert sum(r.evidence_type == "merged_cell" for r in ex.rows) >= 2  # the row holding the text reads it directly
