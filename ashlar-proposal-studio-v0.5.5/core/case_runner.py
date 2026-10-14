"""One insurance option, analysed end to end — shared by the app and the worker.

The Streamlit form and the background worker must produce identical results,
so the per-option pipeline lives here: library sources (with a guard against a
document filed under the wrong product), plan selection, multi-plan table
isolation, AI analysis and quality scoring.
"""
from __future__ import annotations

from pathlib import Path
import tempfile

from .analyzer import analyze_target_plan
from .brochure_tables import extract_target_plan_from_pdf
from .carriers import get_carrier_adapter
from .extract import extract_document
from .library_classify import product_mismatch, table_first
from .plan_selector import identify_selected_plan
from .quality import assess_result_quality
from .storage import (
    LibraryStorageError,
    cache_document_text,
    get_documents,
    list_catalog,
    materialize_document,
)

TABLE_DOC_TYPES = {"brochure", "tob"}


def _document_text(doc, warnings: list[str]) -> str:
    text = (doc.extracted_text or "").strip()
    if text:
        return text
    try:
        with materialize_document(doc) as path:
            result = extract_document(path, doc.original_filename)
    except LibraryStorageError as exc:
        warnings.append(f"Library document {doc.original_filename}: {exc}")
        return ""
    if not result.ok:
        warnings.append(f"Library document {doc.original_filename}: {result.error}")
        try:
            cache_document_text(doc.id, None, result.error)
        except LibraryStorageError:
            pass
        return ""
    try:
        cache_document_text(doc.id, result.text)
    except LibraryStorageError as exc:
        warnings.append(f"Could not persist extracted-text cache for {doc.original_filename}: {exc}")
    return result.text


def sibling_products(provider: str) -> list[str]:
    try:
        catalog = list_catalog()
    except LibraryStorageError:
        return []
    key = str(provider or "").strip().casefold()
    return sorted({c.get("product") for c in catalog if str(c.get("provider") or "").strip().casefold() == key} - {None})


def load_library_sources(library_row: dict | None) -> dict:
    """Library documents for one product/version, minus any filed under the wrong product."""
    out = {"docs": [], "excluded": [], "brochure_text": "", "wording_text": "", "plan_pdf_docs": [], "warnings": []}
    if not library_row:
        return out
    provider, product, version = library_row.get("provider"), library_row.get("product"), library_row.get("version")
    try:
        docs = get_documents(provider, product, version)
    except LibraryStorageError as exc:
        out["warnings"].append(f"Could not load {provider} Library sources: {exc}")
        return out

    siblings = sibling_products(provider)
    brochure_texts: list[str] = []
    wording_texts: list[str] = []
    for doc in table_first(list(docs)):
        text = _document_text(doc, out["warnings"])
        other = product_mismatch(product, text, siblings) if text else None
        if other:
            out["excluded"].append({"id": doc.id, "filename": doc.original_filename, "reason": f"title page is for {provider} {other}"})
            out["warnings"].append(f"{doc.original_filename} is filed under {product} but is the {other} document — not used.")
            continue
        out["docs"].append(doc)
        if not text:
            continue
        wrapped = (
            f"--- LIBRARY DOCUMENT: {doc.original_filename} "
            f"[{doc.provider} / {doc.product} / {doc.version} / {doc.doc_type}] ---\n{text}"
        )
        (brochure_texts if doc.doc_type in TABLE_DOC_TYPES else wording_texts).append(wrapped)
        if Path(doc.original_filename).suffix.lower() == ".pdf":
            out["plan_pdf_docs"].append(doc)
    out["brochure_text"] = "\n\n".join(brochure_texts)
    out["wording_text"] = "\n\n".join(wording_texts)
    return out


def analyze_option(
    *,
    label: str,
    quotation_text: str,
    library_row: dict | None = None,
    target_override: str = "",
    underwriting_override: str = "",
    manual_brochure_text: str = "",
    manual_wording_text: str = "",
    manual_pdfs: list[tuple[str, bytes]] | None = None,
) -> tuple[dict, list[str]]:
    """Return (result_row, warnings) for one option of a case."""
    library = load_library_sources(library_row)
    warnings = list(library["warnings"])
    brochure_text = "\n\n".join(x for x in [library["brochure_text"], manual_brochure_text] if x)
    wording_text = "\n\n".join(x for x in [library["wording_text"], manual_wording_text] if x)

    selection = identify_selected_plan(quotation_text, provider_label=label, manual_override=target_override)
    target_plan = (selection.get("plan_name") or "").strip()
    carrier_adapter = get_carrier_adapter(label, quotation_text)

    focused_blocks: list[str] = []
    focused_rows: list[dict] = []
    # Geometric target-column isolation is for true multi-plan tables (IMG, Cigna).
    if target_plan and carrier_adapter.benefit_strategy == "multi_plan_table":
        for library_doc in library["plan_pdf_docs"]:
            try:
                with materialize_document(library_doc) as path:
                    focused = extract_target_plan_from_pdf(path, target_plan)
            except LibraryStorageError as exc:
                warnings.append(f"Could not read {library_doc.original_filename}: {exc}")
                continue
            if focused.rows:
                focused_blocks.append(f"--- SOURCE FILE: {library_doc.original_filename} ---\n{focused.to_prompt_context()}")
                focused_rows.extend([{"source_file": library_doc.original_filename, **row.__dict__} for row in focused.rows])
        for filename, blob in manual_pdfs or []:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(blob)
                tmp_path = tmp.name
            try:
                focused = extract_target_plan_from_pdf(tmp_path, target_plan)
                if focused.rows:
                    focused_blocks.append(f"--- SOURCE FILE: {filename} ---\n{focused.to_prompt_context()}")
                    focused_rows.extend([{"source_file": filename, **row.__dict__} for row in focused.rows])
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    analysis = analyze_target_plan(
        provider_label=label,
        target_plan=target_plan,
        quotation_text=quotation_text,
        brochure_text=brochure_text,
        wording_text=wording_text,
        focused_table_context="\n\n".join(focused_blocks),
    )
    if underwriting_override:
        analysis.setdefault("underwriting", {})["basis"] = underwriting_override
        analysis.setdefault("broker_overrides", {})["underwriting_basis"] = underwriting_override

    docs = library["docs"]
    result_row = {
        "provider": label,
        "library_source": library_row,
        "library_files": [d.original_filename for d in docs],
        "library_documents": [
            {
                "id": d.id, "provider": d.provider, "product": d.product, "version": d.version,
                "doc_type": d.doc_type, "filename": d.original_filename, "sha256": d.sha256,
            }
            for d in docs
        ],
        "excluded_library_documents": library["excluded"],
        "plan_selection": selection,
        "target_plan": target_plan,
        "underwriting_override": underwriting_override or None,
        "focused_rows": focused_rows,
        "analysis": analysis,
        # Kept so a saved case can be re-analysed (e.g. after a library fix)
        # without uploading the quote again.
        "quotation_text": quotation_text,
    }
    result_row["quality"] = assess_result_quality(result_row)
    return result_row, warnings


def reanalysis_inputs(result: dict) -> dict:
    """Rebuild analyze_option() arguments from a saved result row."""
    selection = result.get("plan_selection") or {}
    target_override = selection.get("plan_name") if selection.get("method") == "broker_override" else ""
    return {
        "label": result.get("provider") or "",
        "quotation_text": result.get("quotation_text") or "",
        "library_row": result.get("library_source") or None,
        "target_override": target_override or "",
        "underwriting_override": result.get("underwriting_override") or "",
    }
