from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core.analyzer import analyze_target_plan
from core.brochure_tables import extract_target_plan_from_pdf
from core.extract import extract_document
from core.plan_selector import identify_selected_plan
from core.storage import (
    delete_document,
    get_documents,
    list_catalog,
    list_documents,
    save_provider_document,
    storage_status,
)


st.set_page_config(page_title="Ashlar Proposal Studio", page_icon="🛡️", layout="wide")

DOC_TYPES = {
    "Brochure / multi-plan Table of Benefits": "brochure",
    "Table of Benefits": "tob",
    "Policy Wording / Member Guide": "wording",
    "Underwriting guide": "underwriting",
    "Supporting document": "supporting",
}
TABLE_DOC_TYPES = {"brochure", "tob"}
WORDING_DOC_TYPES = {"wording", "underwriting", "supporting"}


def _extract_uploaded(files) -> tuple[str, list[tuple[str, bytes]]]:
    texts: list[str] = []
    pdf_blobs: list[tuple[str, bytes]] = []
    for f in files or []:
        suffix = Path(f.name).suffix.lower()
        data = f.getvalue()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            result = extract_document(tmp_path, f.name)
            if result.ok:
                texts.append(f"--- DOCUMENT: {f.name} ---\n{result.text}")
                if suffix == ".pdf":
                    pdf_blobs.append((f.name, data))
            else:
                st.warning(f"{f.name}: {result.error}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return "\n\n".join(texts), pdf_blobs


def _extract_library_documents(docs):
    brochure_texts: list[str] = []
    wording_texts: list[str] = []
    plan_pdf_paths: list[tuple[str, Path]] = []

    for doc in docs:
        result = extract_document(doc.path, doc.original_filename)
        if not result.ok:
            st.warning(f"Library document {doc.original_filename}: {result.error}")
            continue
        wrapped = (
            f"--- LIBRARY DOCUMENT: {doc.original_filename} "
            f"[{doc.provider} / {doc.product} / {doc.version} / {doc.doc_type}] ---\n"
            f"{result.text}"
        )
        if doc.doc_type in TABLE_DOC_TYPES:
            brochure_texts.append(wrapped)
            if doc.path.suffix.lower() == ".pdf":
                plan_pdf_paths.append((doc.original_filename, doc.path))
        else:
            wording_texts.append(wrapped)
            if doc.path.suffix.lower() == ".pdf":
                # Some wordings also contain plan comparison tables.
                plan_pdf_paths.append((doc.original_filename, doc.path))

    return "\n\n".join(brochure_texts), "\n\n".join(wording_texts), plan_pdf_paths


def provider_library_page():
    st.title("📚 Provider Document Library")
    st.caption(
        "Store provider-level source material once. On Railway, attach a persistent Volume at /app/data "
        "so the library survives code redeploys. Client quotations are handled separately in Case Workspace."
    )

    status = storage_status()
    st.info(f"Persistent data path: `{status['data_dir']}` · free space: {status['free_gb']} GB")

    with st.container(border=True):
        st.subheader("Add provider documents")
        c1, c2, c3 = st.columns(3)
        with c1:
            provider = st.text_input("Provider", placeholder="IMG")
        with c2:
            product = st.text_input("Product / product family", placeholder="Global Prima Medical Insurance")
        with c3:
            version = st.text_input("Version / year", value=str(date.today().year), placeholder="2026")

        c4, c5, c6 = st.columns(3)
        with c4:
            doc_type_label = st.selectbox("Document type", list(DOC_TYPES.keys()))
        with c5:
            effective_from = st.text_input("Effective from (optional)", placeholder="2026-01-01")
        with c6:
            effective_to = st.text_input("Effective to (optional)", placeholder="2026-12-31")

        notes = st.text_input("Notes (optional)", placeholder="Europe version / intermediary edition / etc.")
        files = st.file_uploader(
            "Provider documents",
            type=["pdf", "txt"],
            accept_multiple_files=True,
            key="library_upload",
        )

        if st.button("💾 Save to Provider Library", type="primary"):
            if not provider.strip() or not product.strip() or not version.strip() or not files:
                st.warning("Provider, product, version and at least one file are required.")
            else:
                created = 0
                duplicates = 0
                for f in files:
                    _, was_created = save_provider_document(
                        provider=provider,
                        product=product,
                        version=version,
                        doc_type=DOC_TYPES[doc_type_label],
                        filename=f.name,
                        content=f.getvalue(),
                        effective_from=effective_from,
                        effective_to=effective_to,
                        notes=notes,
                    )
                    if was_created:
                        created += 1
                    else:
                        duplicates += 1
                st.success(f"Saved {created} new document(s). {duplicates} exact duplicate(s) skipped.")
                st.rerun()

    catalog = list_catalog()
    st.subheader("Library catalog")
    if not catalog:
        st.info("No provider documents stored yet.")
        return

    st.dataframe(pd.DataFrame(catalog), use_container_width=True, hide_index=True)

    with st.expander("Manage individual documents"):
        docs = list_documents()
        for doc in docs:
            cols = st.columns([5, 1])
            with cols[0]:
                st.markdown(
                    f"**{doc.provider} — {doc.product} — {doc.version}**  \n"
                    f"`{doc.doc_type}` · {doc.original_filename}"
                )
            with cols[1]:
                if st.button("Delete", key=f"del_{doc.id}"):
                    delete_document(doc.id)
                    st.rerun()


def case_workspace_page():
    st.title("🛡️ Ashlar Proposal Studio")
    st.caption(
        "Upload the client's quotations. Proposal Studio combines each quote with the matching provider library, "
        "locks the selected plan, and mines only that plan from multi-plan brochures."
    )

    st.session_state.setdefault("n_providers", 2)
    st.session_state.setdefault("results", [])

    st.text_input("Case / client reference", key="case_reference", placeholder="e.g. Alexopoulou / Rogavopoulos")

    catalog = list_catalog()
    catalog_labels = {
        f"{r['provider']} — {r['product']} — {r['version']}": r for r in catalog
    }

    slots = []
    st.subheader("Providers in this case")
    for i in range(st.session_state["n_providers"]):
        with st.container(border=True):
            st.markdown(f"#### Option {i + 1}")
            if catalog_labels:
                library_choice = st.selectbox(
                    "Provider library source",
                    ["— None / manual documents —"] + list(catalog_labels.keys()),
                    key=f"library_choice_{i}",
                )
            else:
                library_choice = "— None / manual documents —"
                st.caption("Provider Library is empty — use manual documents or add sources in the Library page.")

            library_row = catalog_labels.get(library_choice)
            default_label = library_row["provider"] if library_row else f"Provider {i+1}"
            c1, c2 = st.columns(2)
            with c1:
                label = st.text_input("Provider / policy label", key=f"label_{i}", value=default_label)
            with c2:
                target_override = st.text_input(
                    "Selected plan override (optional)",
                    key=f"target_{i}",
                    placeholder="e.g. Silver",
                    help="Leave blank to infer the selected plan from the quotation/certificate.",
                )

            q = st.file_uploader(
                "Client quotation / certificate",
                type=["pdf", "txt"],
                accept_multiple_files=True,
                key=f"q_{i}",
                help="Applicant-specific source for selected plan, premium, area, excess and chosen options.",
            )
            manual_b = st.file_uploader(
                "Extra brochure / Table of Benefits for this case (optional)",
                type=["pdf", "txt"],
                accept_multiple_files=True,
                key=f"b_{i}",
            )
            manual_w = st.file_uploader(
                "Extra wording / endorsement / correspondence (optional)",
                type=["pdf", "txt"],
                accept_multiple_files=True,
                key=f"w_{i}",
            )

            slots.append({
                "label": label.strip() or default_label,
                "target_override": target_override.strip(),
                "quote": q or [],
                "manual_brochure": manual_b or [],
                "manual_wording": manual_w or [],
                "library_row": library_row,
            })

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        if st.button("➕ Add provider"):
            st.session_state["n_providers"] += 1
            st.rerun()
    with c2:
        if st.session_state["n_providers"] > 1 and st.button("➖ Remove last"):
            st.session_state["n_providers"] -= 1
            st.rerun()

    if st.button("🚀 Analyze case", type="primary"):
        active = [
            s for s in slots
            if s["quote"] or s["manual_brochure"] or s["manual_wording"] or s["library_row"]
        ]
        if not active:
            st.warning("Add at least one quote or provider-library source.")
        else:
            all_results = []
            progress = st.progress(0.0)
            for idx, slot in enumerate(active, start=1):
                st.write(f"Analyzing **{slot['label']}**…")

                quotation_text, _ = _extract_uploaded(slot["quote"])
                manual_brochure_text, manual_brochure_pdfs = _extract_uploaded(slot["manual_brochure"])
                manual_wording_text, manual_wording_pdfs = _extract_uploaded(slot["manual_wording"])

                lib_brochure_text = ""
                lib_wording_text = ""
                library_plan_pdfs: list[tuple[str, Path]] = []
                library_docs = []
                if slot["library_row"]:
                    row = slot["library_row"]
                    library_docs = get_documents(row["provider"], row["product"], row["version"])
                    lib_brochure_text, lib_wording_text, library_plan_pdfs = _extract_library_documents(library_docs)

                brochure_text = "\n\n".join(x for x in [lib_brochure_text, manual_brochure_text] if x)
                wording_text = "\n\n".join(x for x in [lib_wording_text, manual_wording_text] if x)

                selection = identify_selected_plan(
                    quotation_text,
                    provider_label=slot["label"],
                    manual_override=slot["target_override"],
                )
                target_plan = (selection.get("plan_name") or "").strip()

                focused_blocks: list[str] = []
                focused_rows: list[dict] = []
                if target_plan:
                    # Persistent library PDFs can be inspected in-place.
                    for filename, path in library_plan_pdfs:
                        focused = extract_target_plan_from_pdf(path, target_plan)
                        if focused.rows:
                            focused_blocks.append(
                                f"--- SOURCE FILE: {filename} ---\n{focused.to_prompt_context()}"
                            )
                            focused_rows.extend([
                                {"source_file": filename, **row.__dict__} for row in focused.rows
                            ])

                    # Case-specific PDFs are temporary blobs.
                    for filename, blob in manual_brochure_pdfs + manual_wording_pdfs:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp.write(blob)
                            tmp_path = tmp.name
                        try:
                            focused = extract_target_plan_from_pdf(tmp_path, target_plan)
                            if focused.rows:
                                focused_blocks.append(
                                    f"--- SOURCE FILE: {filename} ---\n{focused.to_prompt_context()}"
                                )
                                focused_rows.extend([
                                    {"source_file": filename, **row.__dict__} for row in focused.rows
                                ])
                        finally:
                            Path(tmp_path).unlink(missing_ok=True)

                analysis = analyze_target_plan(
                    provider_label=slot["label"],
                    target_plan=target_plan,
                    quotation_text=quotation_text,
                    brochure_text=brochure_text,
                    wording_text=wording_text,
                    focused_table_context="\n\n".join(focused_blocks),
                )

                all_results.append({
                    "provider": slot["label"],
                    "library_source": slot["library_row"],
                    "library_files": [d.original_filename for d in library_docs],
                    "plan_selection": selection,
                    "target_plan": target_plan,
                    "focused_rows": focused_rows,
                    "analysis": analysis,
                })
                progress.progress(idx / len(active))

            st.session_state["results"] = all_results
            progress.empty()

    results = st.session_state.get("results", [])
    if not results:
        return

    st.divider()
    st.subheader("Target-plan audit")
    for result in results:
        selection = result["plan_selection"]
        with st.expander(
            f"{result['provider']} — target: {result['target_plan'] or 'NOT IDENTIFIED'}",
            expanded=True,
        ):
            if result.get("library_source"):
                r = result["library_source"]
                st.caption(
                    f"Provider Library: {r['provider']} / {r['product']} / {r['version']} · "
                    f"{len(result['library_files'])} document(s)"
                )
            st.write(
                f"Selection method: **{selection.get('method', 'unknown')}** · "
                f"confidence: **{selection.get('confidence', 'unknown')}**"
            )
            st.caption(selection.get("evidence", ""))
            if not result["target_plan"]:
                st.error(
                    "No single plan could be locked. Enter a Selected plan override rather than allowing a guess."
                )
            if result["focused_rows"]:
                st.success(
                    f"Isolated {len(result['focused_rows'])} benefit rows from the "
                    f"{result['target_plan']} column before LLM analysis."
                )
                df_focus = pd.DataFrame(result["focused_rows"])[
                    ["source_file", "page", "section", "benefit", "value", "evidence_type"]
                ]
                st.dataframe(df_focus, use_container_width=True, hide_index=True)
            else:
                st.info("No multi-plan table was deterministically isolated from the available PDFs.")

    st.divider()
    st.subheader("Structured comparison")
    summary_rows = []
    for result in results:
        a = result["analysis"]
        premium = a.get("premium") or {}
        summary_rows.append({
            "Provider": a.get("provider") or result["provider"],
            "Plan": a.get("plan_name") or result["target_plan"] or "—",
            "Premium": " ".join(
                str(x) for x in [premium.get("currency"), premium.get("amount"), premium.get("frequency")]
                if x not in (None, "")
            ) or "—",
            "Annual limit": a.get("annual_limit", "—"),
            "Deductible / excess": a.get("deductible_or_excess", "—"),
            "Area": a.get("area_of_cover", "—"),
            "Confidence": a.get("confidence", "—"),
        })
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    for result in results:
        with st.expander(f"Full analysis — {result['provider']}"):
            st.json(result["analysis"])


with st.sidebar:
    st.markdown("## Ashlar Proposal Studio")
    page = st.radio("Navigation", ["Case Workspace", "Provider Library"])
    st.divider()
    st.caption(f"AI: {'configured' if os.getenv('ANTHROPIC_API_KEY') else 'not configured'}")

if page == "Provider Library":
    provider_library_page()
else:
    case_workspace_page()
