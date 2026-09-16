"""
Plan-aware table extraction for carrier brochures that contain several plans
side-by-side (e.g. Bronze / Bronze Plus / Silver / Gold / Platinum).

The extractor builds a deterministic target-plan lens BEFORE an LLM sees the
document. It supports three common carrier layouts:

1. plan names in the detected table header;
2. plan names in an internal table row (common in quote/product-comparison PDFs);
3. continuation tables where the plan headings are not repeated (common for
   Cigna benefit tables split into sub-sections such as Dental Treatment).

Only the selected plan column is exposed to the analysis model.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re

import fitz  # PyMuPDF


_LABEL_HEADERS = {
    "benefit", "benefits", "plan details", "coverage", "cover", "service",
    "services", "feature", "features", "benefit / term", "benefit/term",
}
_CHECKMARKS = {"\uf0fc", "", "✓", "✔", "☑"}


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _norm_key(value: str | None) -> str:
    return _norm(value).casefold()


def _cell_text(page: fitz.Page, cell) -> str:
    if not cell:
        return ""
    try:
        return _norm(page.get_text("text", clip=fitz.Rect(cell), sort=True))
    except Exception:
        return ""


def _normalise_value(value: str) -> tuple[str, str]:
    """Normalise embedded symbol-font checkmarks into explicit evidence."""
    value = _norm(value)
    if not value:
        return value, "text"
    first = value[0]
    if first in _CHECKMARKS:
        rest = _norm(value[1:])
        if rest:
            return f"Covered (table checkmark); {rest}", "embedded_checkmark"
        return "Covered (table checkmark)", "embedded_checkmark"
    if value in _CHECKMARKS:
        return "Covered (table checkmark)", "embedded_checkmark"
    return value, "text"


@dataclass
class PlanTableRow:
    page: int
    table_index: int
    section: str
    benefit: str
    value: str
    target_plan: str
    evidence_type: str = "text"


@dataclass
class PlanTableExtraction:
    target_plan: str
    rows: list[PlanTableRow]
    pages_with_target_tables: list[int]
    available_plan_headers: list[str]

    def as_dict(self) -> dict:
        return {
            "target_plan": self.target_plan,
            "rows": [asdict(r) for r in self.rows],
            "pages_with_target_tables": self.pages_with_target_tables,
            "available_plan_headers": self.available_plan_headers,
        }

    def to_prompt_context(self, max_rows: int = 260) -> str:
        lines = [
            f"TARGET PLAN TABLE EVIDENCE — {self.target_plan}",
            "This evidence was isolated geometrically from the selected plan column.",
            "Treat a line marked 'Covered (table checkmark)' as a visual checkmark in that plan's cell.",
            "Do not use values from neighbouring plan columns.",
            "",
        ]
        current_section = None
        for row in self.rows[:max_rows]:
            if row.section and row.section != current_section:
                current_section = row.section
                lines.append(f"[Page {row.page}] SECTION: {current_section}")
            lines.append(f"[Page {row.page}] {row.benefit} => {row.value}")
        return "\n".join(lines)


def _find_target_header_index(headers: list[str], target_plan: str) -> int | None:
    target = _norm_key(target_plan)
    exact = [i for i, h in enumerate(headers) if _norm_key(h) == target]
    if exact:
        return exact[0]

    target_words = target.split()
    for i, h in enumerate(headers):
        hkey = _norm_key(h)
        hwords = hkey.split()
        if target_words and hwords[: len(target_words)] == target_words:
            if len(hwords) == len(target_words):
                return i
    return None


def _infer_label_index(page: fitz.Page, table, target_idx: int, start_row: int = 0) -> int:
    """Choose the most likely benefit-label column before the target plan column.

    This is more robust than always choosing the first column because some carrier
    tables use column 0 for section names and column 1 for the actual benefit label.
    """
    if target_idx <= 0:
        return 0

    header_names = [_norm(h) for h in table.header.names]
    for i in range(min(target_idx, len(header_names)) - 1, -1, -1):
        if _norm_key(header_names[i]) in _LABEL_HEADERS:
            return i

    scores: list[tuple[int, int, int]] = []
    scan_rows = table.rows[start_row : min(len(table.rows), start_row + 14)]
    for i in range(target_idx):
        nonempty = 0
        chars = 0
        for row in scan_rows:
            if i >= len(row.cells):
                continue
            txt = _cell_text(page, row.cells[i])
            if txt:
                nonempty += 1
                chars += len(txt)
        scores.append((nonempty, chars, i))
    if scores:
        scores.sort(reverse=True)
        return scores[0][2]
    return max(0, target_idx - 1)


def _small_vector_icons(page: fitz.Page, rect: fitz.Rect) -> list[fitz.Rect]:
    """Return compact vector drawings substantially contained in a plan cell."""
    icons: list[fitz.Rect] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return icons

    for drawing in drawings:
        r = fitz.Rect(drawing.get("rect", (0, 0, 0, 0)))
        if r.is_empty or not r.intersects(rect):
            continue
        if not (1 < r.width <= 20 and 1 < r.height <= 20):
            continue
        intersection = r & rect
        if r.get_area() and intersection.get_area() >= 0.60 * r.get_area():
            icons.append(r)
    return icons


def _row_texts(page: fitz.Page, table_row) -> list[str]:
    return [_cell_text(page, c) for c in table_row.cells]


def _detect_internal_plan_row(page: fitz.Page, table, target_plan: str) -> tuple[int, int] | None:
    """Return (row_index, target_column_index) when plan headings live inside the table body."""
    target = _norm_key(target_plan)
    for row_index, row in enumerate(table.rows[:6]):
        texts = _row_texts(page, row)
        for col_index, text in enumerate(texts):
            if _norm_key(text) == target:
                return row_index, col_index
    return None


def _table_compatible_with_geometry(table, geometry: dict, page_number: int) -> bool:
    if not geometry:
        return False
    if page_number - geometry.get("page", page_number) > 1:
        return False
    bbox = table.bbox
    prior = geometry.get("table_bbox")
    if prior:
        if abs(bbox[0] - prior[0]) > 14 or abs(bbox[2] - prior[2]) > 14:
            return False
    tx0, tx1 = geometry["target_x"]
    lx0, lx1 = geometry["label_x"]
    return bbox[0] - 2 <= lx0 < lx1 <= bbox[2] + 2 and bbox[0] - 2 <= tx0 < tx1 <= bbox[2] + 2


def extract_target_plan_from_pdf(
    pdf_path: str | Path,
    target_plan: str,
    *,
    max_rows: int = 300,
) -> PlanTableExtraction:
    """Extract only `target_plan` values from multi-plan benefit tables."""
    pdf_path = Path(pdf_path)
    rows: list[PlanTableRow] = []
    pages: list[int] = []
    plan_headers: list[str] = []
    current_section = ""
    last_geometry: dict | None = None

    doc = fitz.open(str(pdf_path))
    try:
        for page_number, page in enumerate(doc, start=1):
            try:
                tables = page.find_tables().tables
            except Exception:
                tables = []

            for table_index, table in enumerate(tables):
                headers = [_norm(h) for h in table.header.names]
                target_idx = _find_target_header_index(headers, target_plan)
                start_row = 1
                header_source = "table_header"
                label_idx: int | None = None
                target_x: tuple[float, float] | None = None
                label_x: tuple[float, float] | None = None

                if target_idx is not None and target_idx < len(table.header.cells) and table.header.cells[target_idx]:
                    target_cell = table.header.cells[target_idx]
                    target_x = (target_cell[0], target_cell[2])
                    label_idx = _infer_label_index(page, table, target_idx, start_row=1)
                    if label_idx < len(table.header.cells) and table.header.cells[label_idx]:
                        label_cell = table.header.cells[label_idx]
                        label_x = (label_cell[0], label_cell[2])
                    section_candidate = headers[label_idx] if label_idx is not None and label_idx < len(headers) else ""
                    if section_candidate and _norm_key(section_candidate) not in _LABEL_HEADERS:
                        current_section = section_candidate
                else:
                    internal = _detect_internal_plan_row(page, table, target_plan)
                    if internal:
                        plan_row_idx, target_idx = internal
                        row = table.rows[plan_row_idx]
                        if target_idx < len(row.cells) and row.cells[target_idx]:
                            target_cell = row.cells[target_idx]
                            target_x = (target_cell[0], target_cell[2])
                            label_idx = _infer_label_index(page, table, target_idx, start_row=plan_row_idx + 1)
                            # Prefer the actual cell geometry from the internal header row when present;
                            # otherwise infer it from data cells in that column.
                            label_cell = row.cells[label_idx] if label_idx < len(row.cells) else None
                            if not label_cell:
                                for probe in table.rows[plan_row_idx + 1 :]:
                                    if label_idx < len(probe.cells) and probe.cells[label_idx]:
                                        label_cell = probe.cells[label_idx]
                                        break
                            if label_cell:
                                label_x = (label_cell[0], label_cell[2])
                            start_row = plan_row_idx + 1
                            header_source = "internal_plan_row"
                            # Collect all plan names from the same internal row.
                            for text in _row_texts(page, row):
                                if text and text not in plan_headers:
                                    plan_headers.append(text)
                    elif _table_compatible_with_geometry(table, last_geometry or {}, page_number):
                        # Continuation table: carrier omitted repeated Silver/Gold/Platinum headings.
                        target_x = last_geometry["target_x"]
                        label_x = last_geometry["label_x"]
                        target_idx = last_geometry.get("target_idx")
                        label_idx = last_geometry.get("label_idx")
                        start_row = 0
                        header_source = "continuation_geometry"

                        first_texts = _row_texts(page, table.rows[0]) if table.rows else []
                        nonempty = [x for x in first_texts if x]
                        if len(nonempty) == 1 and len(nonempty[0]) <= 180:
                            current_section = nonempty[0]
                            start_row = 1

                if not target_x or not label_x:
                    continue

                if page_number not in pages:
                    pages.append(page_number)
                for header in headers:
                    if header and header not in plan_headers:
                        plan_headers.append(header)

                last_geometry = {
                    "page": page_number,
                    "target_x": target_x,
                    "label_x": label_x,
                    "target_idx": target_idx,
                    "label_idx": label_idx,
                    "table_bbox": table.bbox,
                    "source": header_source,
                }

                tx0, tx1 = target_x
                lx0, lx1 = label_x

                for table_row in table.rows[start_row:]:
                    first_cell = next((c for c in table_row.cells if c), None)
                    if first_cell is None:
                        continue
                    y0, y1 = first_cell[1], first_cell[3]

                    label_rect = fitz.Rect(lx0, y0, lx1, y1)
                    target_rect = fitz.Rect(tx0, y0, tx1, y1)
                    label = _norm(page.get_text("text", clip=label_rect, sort=True))
                    raw_value = _norm(page.get_text("text", clip=target_rect, sort=True))
                    value, evidence_type = _normalise_value(raw_value)

                    if not label:
                        full_row = _norm(
                            page.get_text(
                                "text",
                                clip=fitz.Rect(table.bbox[0], y0, table.bbox[2], y1),
                                sort=True,
                            )
                        )
                        if full_row and len(full_row) <= 180:
                            current_section = full_row
                        continue

                    if not value:
                        icons = _small_vector_icons(page, target_rect)
                        if icons:
                            value = "Covered (table checkmark)"
                            evidence_type = "vector_checkmark"
                        else:
                            value = "Not stated / blank cell"
                            evidence_type = "blank"

                    rows.append(
                        PlanTableRow(
                            page=page_number,
                            table_index=table_index,
                            section=current_section,
                            benefit=label,
                            value=value,
                            target_plan=target_plan,
                            evidence_type=evidence_type,
                        )
                    )
                    if len(rows) >= max_rows:
                        return PlanTableExtraction(
                            target_plan=target_plan,
                            rows=rows,
                            pages_with_target_tables=pages,
                            available_plan_headers=plan_headers,
                        )
    finally:
        doc.close()

    return PlanTableExtraction(
        target_plan=target_plan,
        rows=rows,
        pages_with_target_tables=pages,
        available_plan_headers=plan_headers,
    )
