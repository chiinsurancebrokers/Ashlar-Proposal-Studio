"""Guard rails for Provider Library uploads.

Two mistakes reached a client report through the library:

* a batch of four APRIL files was saved with one document type ("brochure"),
  so the General Conditions and the Table of Benefits were treated as brochures;
* the Bupa *Select* entry held the *Premier* Membership Guide, so the Select
  analysis read another plan's terms.

``guess_doc_type`` classifies each file on its own, and ``product_mismatch``
flags a document whose title page names a different product of the same
provider than the one it is being filed under.
"""
from __future__ import annotations

import re

# Ordered: the first matching rule wins. Filename and the first page are both checked.
_DOC_TYPE_RULES: tuple[tuple[str, str], ...] = (
    ("tob", r"benefits?[-_ ]?table|table[-_ ]of[-_ ]benefits|benefits?[-_ ]schedule|schedule[-_ ]of[-_ ]benefits|\btob\b"),
    ("underwriting", r"underwriting[-_ ]guide"),
    ("supporting", r"providers?[-_ ]list|hospital[-_ ]list|\bipid\b|insurance product information document"),
    ("wording", r"general[-_ ]conditions|terms[-_ ]and[-_ ]conditions|membership[-_ ]guide|member[-_ ]guide|guide to your|[-_ ]memb[-_ ]|policy[-_ ]wording|\bwording\b"),
    ("brochure", r"brochure"),
)


def guess_doc_type(filename: str, text: str = "") -> str | None:
    """Best-guess library doc_type for one file, or ``None`` when unsure."""
    name = str(filename or "").casefold()
    # Title page only: a guide's contents page lists "Table of benefits" too.
    first_page = re.split(r"(?:-{3}|={3,})\s*PAGE\s*2\b|\f", str(text or ""), maxsplit=1, flags=re.I)[0]
    head = re.sub(r"\s+", " ", first_page[:800]).casefold()
    for source in (name, head):
        for doc_type, pattern in _DOC_TYPE_RULES:
            if re.search(pattern, source):
                return doc_type
    return None


def _title_area(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")[:1500]).casefold()


def product_mismatch(product: str, text: str, sibling_products: list[str]) -> str | None:
    """Name the other product a document is about, if its title page says so.

    Only fires when the title area names a sibling product of the same provider
    and does not name the product the file is being saved under.
    """
    head = _title_area(text)
    if not head:
        return None
    target = str(product or "").strip().casefold()
    if target and re.search(rf"\b{re.escape(target)}\b", head):
        return None
    for sibling in sibling_products or []:
        key = str(sibling or "").strip().casefold()
        if not key or key == target:
            continue
        if re.search(rf"\b{re.escape(key)}\b", head):
            return sibling
    return None


TABLE_FIRST_ORDER = {"tob": 0, "brochure": 1}


def table_first(docs: list) -> list:
    """Put Tables of Benefits ahead of brochures so a length cap never cuts them."""
    return sorted(docs, key=lambda d: TABLE_FIRST_ORDER.get(getattr(d, "doc_type", ""), 2))
