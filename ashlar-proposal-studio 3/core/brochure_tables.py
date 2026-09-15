"""
Plan-aware table extraction for carrier brochures that contain several plans
side-by-side (e.g. Bronze / Bronze Plus / Silver / Gold / Platinum).

The goal is to build a deterministic "target-plan lens" BEFORE an LLM sees
the document. PyMuPDF gives us the table header cell geometry. Even when
the body is represented as one merged cell across all plan columns, we can
crop each row using the selected plan header's x-coordinates. Small vector
icons inside the crop are treated as coverage checkmarks when there is no
text in the cell.

This module never decides which plan the client bought. It only isolates
the requested target plan from a multi-plan table.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re

import fitz  # PyMuPDF


_LABEL_HEADERS = {
    "benefit", "benefits", "plan details", "coverage", "cover", "service",
    "services", "feature", "features",
}


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _norm_key(value: str | None) -> str:
    return _norm(value).casefold()


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

    def to_prompt_context(self, max_rows: int = 220) -> str:
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


def _find_label_column(headers: list[str], target_idx: int) -> int:
    for i, h in enumerate(headers[:target_idx]):
        if _norm_key(h) in _LABEL_HEADERS:
            return i
    nonempty = [i for i, h in enumerate(headers[:target_idx]) if _norm(h)]
    if nonempty:
        return nonempty[0]
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
                if target_idx is None:
                    continue
                if target_idx >= len(table.header.cells) or not table.header.cells[target_idx]:
                    continue

                if page_number not in pages:
                    pages.append(page_number)
                for header in headers:
                    if header and header not in plan_headers:
                        plan_headers.append(header)

                label_idx = _find_label_column(headers, target_idx)
                if label_idx >= len(table.header.cells) or not table.header.cells[label_idx]:
                    continue

                tx0, _, tx1, _ = table.header.cells[target_idx]
                lx0, _, lx1, _ = table.header.cells[label_idx]

                for table_row in table.rows[1:]:
                    first_cell = next((c for c in table_row.cells if c), None)
                    if first_cell is None:
                        continue
                    y0, y1 = first_cell[1], first_cell[3]

                    label_rect = fitz.Rect(lx0, y0, lx1, y1)
                    target_rect = fitz.Rect(tx0, y0, tx1, y1)
                    label = _norm(page.get_text("text", clip=label_rect, sort=True))
                    value = _norm(page.get_text("text", clip=target_rect, sort=True))

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

                    evidence_type = "text"
                    icons = _small_vector_icons(page, target_rect)
                    if not value and icons:
                        value = "Covered (table checkmark)"
                        evidence_type = "vector_checkmark"
                    elif not value:
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
