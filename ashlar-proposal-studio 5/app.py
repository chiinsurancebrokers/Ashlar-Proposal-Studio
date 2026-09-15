from __future__ import annotations

import html
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
from core.chat import ask_case_agent
from core.client_analysis import build_comparison_matrix, generate_client_analysis, plan_display_name
from core.presentation import build_pptx_bytes
from core.report_pdf import build_pdf_bytes
from core.extract import extract_document
from core.plan_selector import identify_selected_plan
from core.storage import (
    LibraryStorageError,
    cache_document_text,
    delete_document,
    get_documents,
    library_backend,
    list_catalog,
    list_documents,
    local_library_count,
    materialize_document,
    migrate_local_library_to_supabase,
    read_document_bytes,
    save_provider_document,
    storage_status,
)


st.set_page_config(
    page_title="Ashlar Proposal Studio",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DOC_TYPES = {
    "Brochure / multi-plan Table of Benefits": "brochure",
    "Table of Benefits": "tob",
    "Policy Wording / Member Guide": "wording",
    "Underwriting guide": "underwriting",
    "Supporting document": "supporting",
}
TABLE_DOC_TYPES = {"brochure", "tob"}


# -----------------------------------------------------------------------------
# Visual system
# -----------------------------------------------------------------------------

def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --ashlar-navy: #0C1A2A;
          --ashlar-navy-2: #12243A;
          --ashlar-ink: #172033;
          --ashlar-muted: #6C768A;
          --ashlar-border: #E3E8F0;
          --ashlar-bg: #F5F7FB;
          --ashlar-card: #FFFFFF;
          --ashlar-purple: #6C4CF5;
          --ashlar-gold: #E7AD43;
          --ashlar-green: #15966A;
          --ashlar-red: #D9534F;
        }

        html, body, [class*="css"] { font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
        .stApp { background: var(--ashlar-bg); color: var(--ashlar-ink); }
        header[data-testid="stHeader"] { background: transparent; }
        footer { visibility: hidden; }
        #MainMenu { visibility: hidden; }

        .block-container {
          max-width: 1480px;
          padding-top: 2.2rem;
          padding-bottom: 4rem;
        }

        section[data-testid="stSidebar"] {
          background: linear-gradient(180deg, #0A1726 0%, #0E2033 100%);
          border-right: 1px solid rgba(255,255,255,.06);
          min-width: 285px !important;
          width: 285px !important;
        }
        section[data-testid="stSidebar"] > div { padding-top: 1.2rem; }
        section[data-testid="stSidebar"] * { color: #EAF0F7; }
        section[data-testid="stSidebar"] .stCaptionContainer,
        section[data-testid="stSidebar"] small { color: #92A2B7 !important; }
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
          background: transparent;
          border-radius: 12px;
          padding: .55rem .7rem;
          margin: .18rem 0;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
          background: rgba(255,255,255,.07);
        }
        section[data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p {
          font-weight: 650;
          font-size: .96rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
          background: #FFFFFF;
          border: 1px solid var(--ashlar-border) !important;
          border-radius: 18px !important;
          box-shadow: 0 10px 30px rgba(24, 35, 52, .045);
        }
        div[data-testid="stExpander"] {
          background: #FFFFFF;
          border: 1px solid var(--ashlar-border);
          border-radius: 14px;
        }
        div[data-testid="stFileUploader"] section {
          border-radius: 14px;
          border: 1px dashed #C7D0DD;
          background: #F8FAFD;
          padding: .55rem;
        }
        div[data-testid="stFileUploader"] section:hover { border-color: var(--ashlar-purple); }

        .stButton > button, .stFormSubmitButton > button {
          border-radius: 12px;
          min-height: 42px;
          font-weight: 700;
          border: 1px solid #D6DDE8;
        }
        .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
          background: linear-gradient(135deg, #6C4CF5, #5638DD);
          border: none;
          color: #fff;
          box-shadow: 0 8px 20px rgba(108,76,245,.22);
        }
        .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
          background: linear-gradient(135deg, #6043E9, #4E31D1);
        }

        .stTextInput input, .stTextArea textarea, div[data-baseweb="select"] > div {
          border-radius: 11px !important;
          border-color: #DCE3EC !important;
          background: #FBFCFE !important;
        }

        .aps-eyebrow {
          color: var(--ashlar-gold);
          font-size: .72rem;
          font-weight: 800;
          letter-spacing: .13em;
          text-transform: uppercase;
          margin-bottom: .5rem;
        }
        .aps-title {
          color: var(--ashlar-ink);
          font-weight: 820;
          font-size: 2.45rem;
          letter-spacing: -.045em;
          line-height: 1.04;
          margin: 0;
        }
        .aps-subtitle {
          color: var(--ashlar-muted);
          font-size: 1rem;
          line-height: 1.55;
          margin-top: .8rem;
          max-width: 900px;
        }
        .aps-rule { height: 1px; background: #E5EAF1; margin: 1.3rem 0 1.45rem; }
        .aps-chip-row { display:flex; gap:.5rem; flex-wrap:wrap; margin-top:.9rem; }
        .aps-chip {
          display:inline-flex; align-items:center; gap:.35rem;
          padding:.36rem .62rem; border-radius:999px;
          border:1px solid #DDE4EE; background:#FFF;
          font-size:.76rem; font-weight:700; color:#4C586C;
        }
        .aps-chip.good { color:#137655; background:#ECF8F3; border-color:#CAEBDD; }
        .aps-chip.warn { color:#8A5D12; background:#FFF7E7; border-color:#F1DEB5; }
        .aps-chip.purple { color:#5137CD; background:#F1EEFF; border-color:#DDD6FF; }

        .aps-kpi {
          background:#FFF; border:1px solid var(--ashlar-border); border-radius:16px;
          padding:1rem 1.05rem; min-height:102px;
          box-shadow:0 8px 22px rgba(25,35,50,.035);
        }
        .aps-kpi-label { color:#7A8496; font-size:.72rem; text-transform:uppercase; font-weight:800; letter-spacing:.08em; }
        .aps-kpi-value { color:#192238; font-size:1.55rem; font-weight:820; margin-top:.3rem; letter-spacing:-.03em; }
        .aps-kpi-note { color:#8993A5; font-size:.74rem; margin-top:.2rem; }

        .aps-section-title { font-size:1.28rem; font-weight:800; color:#212A3C; letter-spacing:-.02em; }
        .aps-section-copy { font-size:.88rem; color:#7A8496; margin-top:.2rem; }

        .aps-provider-head {
          display:flex; justify-content:space-between; align-items:center; gap:1rem;
          margin-bottom:.25rem;
        }
        .aps-provider-index {
          width:30px; height:30px; display:inline-flex; align-items:center; justify-content:center;
          border-radius:9px; background:#F1EEFF; color:#5B42D4; font-weight:800; font-size:.84rem;
          margin-right:.55rem;
        }
        .aps-provider-name { font-weight:800; font-size:1.05rem; color:#202A3C; }
        .aps-helper { color:#8993A5; font-size:.78rem; }

        .aps-chat-shell {
          background: #0E1D2E;
          border-radius:18px;
          padding:1rem;
          color:#EAF0F7;
          min-height:510px;
          box-shadow:0 16px 34px rgba(8,20,34,.16);
        }
        .aps-chat-title { font-weight:800; font-size:1.05rem; color:white; }
        .aps-chat-copy { color:#9FB0C3; font-size:.78rem; margin:.25rem 0 .8rem; }
        .aps-chat-empty {
          border:1px solid rgba(255,255,255,.10); border-radius:13px;
          padding:.75rem; color:#B9C6D4; background:rgba(255,255,255,.035); font-size:.82rem;
        }
        .aps-source {
          border-left:3px solid var(--ashlar-gold); padding:.55rem .7rem; background:#FFF8EA;
          border-radius:0 10px 10px 0; color:#6D5524; font-size:.80rem; margin:.4rem 0;
        }

        .aps-report-hero {
          background:linear-gradient(135deg,#0C1A2A 0%,#122B45 100%); color:white;
          padding:1.35rem 1.5rem; border-radius:18px; box-shadow:0 14px 34px rgba(8,20,34,.14);
        }
        .aps-report-kicker { color:#E7AD43; font-size:.72rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }
        .aps-report-title { font-size:1.65rem; line-height:1.15; font-weight:820; margin-top:.35rem; }
        .aps-report-copy { color:#C2D0DE; font-size:.88rem; line-height:1.5; margin-top:.55rem; max-width:950px; }
        .aps-assessment { background:#F1EEFF; border:1px solid #DDD6FF; border-radius:16px; padding:1rem 1.1rem; }
        .aps-assessment-title { color:#5137CD; font-size:.75rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
        .aps-assessment-head { color:#202A3C; font-size:1.25rem; font-weight:820; margin-top:.35rem; }
        .aps-diff-card { background:white; border:1px solid #E3E8F0; border-radius:14px; padding:.85rem 1rem; margin-bottom:.55rem; }
        .aps-diff-title { font-weight:800; color:#202A3C; }
        .aps-diff-impact { color:#6C4CF5; font-weight:700; font-size:.82rem; margin-top:.25rem; }

        div[data-testid="stChatMessage"] { background:#FFFFFF; border:1px solid #E4E9F1; border-radius:14px; padding:.3rem .6rem; }
        .stTabs [data-baseweb="tab-list"] { gap:.4rem; }
        .stTabs [data-baseweb="tab"] { border-radius:9px 9px 0 0; padding:.55rem .8rem; font-weight:700; }

        @media (max-width: 900px) {
          section[data-testid="stSidebar"] { min-width: 235px !important; width: 235px !important; }
          .aps-title { font-size:1.95rem; }
          .block-container { padding-top:1.3rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, subtitle: str, chips: list[tuple[str, str]] | None = None) -> None:
    chips = chips or []
    chip_html = "".join(
        f'<span class="aps-chip {html.escape(kind)}">{html.escape(text)}</span>' for text, kind in chips
    )
    st.markdown(
        f"""
        <div class="aps-eyebrow">{html.escape(eyebrow)}</div>
        <div class="aps-title">{html.escape(title)}</div>
        <div class="aps-subtitle">{html.escape(subtitle)}</div>
        <div class="aps-chip-row">{chip_html}</div>
        <div class="aps-rule"></div>
        """,
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f"""
        <div class="aps-kpi">
          <div class="aps-kpi-label">{html.escape(label)}</div>
          <div class="aps-kpi-value">{html.escape(str(value))}</div>
          <div class="aps-kpi-note">{html.escape(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Document helpers
# -----------------------------------------------------------------------------

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
    """Load persistent provider knowledge, reusing cached parsed text when available.

    The returned PDF entries are LibraryDocument objects rather than filesystem
    paths, because Supabase objects are materialized only for the few seconds a
    table parser needs them.
    """
    brochure_texts: list[str] = []
    wording_texts: list[str] = []
    plan_pdf_docs = []

    for doc in docs:
        text = (doc.extracted_text or "").strip()
        if not text:
            try:
                with materialize_document(doc) as path:
                    result = extract_document(path, doc.original_filename)
            except LibraryStorageError as exc:
                st.warning(f"Library document {doc.original_filename}: {exc}")
                continue
            if not result.ok:
                st.warning(f"Library document {doc.original_filename}: {result.error}")
                try:
                    cache_document_text(doc.id, None, result.error)
                except LibraryStorageError:
                    pass
                continue
            text = result.text
            try:
                cache_document_text(doc.id, text)
            except LibraryStorageError as exc:
                st.caption(f"Could not persist extracted-text cache for {doc.original_filename}: {exc}")

        wrapped = (
            f"--- LIBRARY DOCUMENT: {doc.original_filename} "
            f"[{doc.provider} / {doc.product} / {doc.version} / {doc.doc_type}] ---\n"
            f"{text}"
        )
        if doc.doc_type in TABLE_DOC_TYPES:
            brochure_texts.append(wrapped)
        else:
            wording_texts.append(wrapped)
        if Path(doc.original_filename).suffix.lower() == ".pdf":
            plan_pdf_docs.append(doc)

    return "\n\n".join(brochure_texts), "\n\n".join(wording_texts), plan_pdf_docs


def _premium_display(analysis: dict) -> str:
    p = analysis.get("premium") or {}
    bits = [p.get("currency"), p.get("amount"), p.get("frequency")]
    return " ".join(str(x) for x in bits if x not in (None, "")) or "—"


# -----------------------------------------------------------------------------
# Admin Library
# -----------------------------------------------------------------------------

def _compact_card_value(value, max_chars: int = 46) -> str:
    text = str(value or "—").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    for sep in [";", ". ", " / ", ", "]:
        first = text.split(sep, 1)[0].strip()
        if 4 <= len(first) <= max_chars:
            return first + ("…" if first != text else "")
    return text[: max_chars - 1].rstrip() + "…"


def _admin_gate() -> bool:
    configured = os.getenv("ADMIN_PASSWORD", "")
    if not configured:
        st.warning("ADMIN_PASSWORD is not configured. The Library is open in this environment.")
        return True
    if st.session_state.get("admin_authenticated"):
        return True

    with st.container(border=True):
        st.markdown("### 🔐 Admin access")
        st.caption("Provider documents are restricted to the Proposal Studio administrator.")
        with st.form("admin_login", enter_to_submit=False):
            pwd = st.text_input("Password", type="password", key="admin_password_input")
            submitted = st.form_submit_button("Unlock Library", type="primary", use_container_width=True)
        if submitted:
            if pwd == configured:
                st.session_state["admin_authenticated"] = True
                st.session_state.pop("admin_password_input", None)
                st.rerun()
            st.error("Incorrect password.")
    return False


def provider_library_page() -> None:
    page_header(
        "ADMIN / KNOWLEDGE BASE",
        "Provider Library",
        "Upload provider-level source documents once. In production the Library lives in Supabase, independently from Railway deployments and GitHub.",
        [("Persistent source library", "purple"), ("Broker controlled", "good")],
    )
    if not _admin_gate():
        return

    try:
        status = storage_status()
        catalog = list_catalog()
        docs = list_documents()
    except LibraryStorageError as exc:
        st.error("Provider Library is configured but cannot be opened.")
        st.code(str(exc), language=None)
        st.info("For a new Supabase project: run `supabase/schema.sql` once in Supabase → SQL Editor, then redeploy/restart the app.")
        return
    providers = len({r["provider"] for r in catalog})
    products = len(catalog)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Providers", providers, "Stored in library")
    with c2:
        kpi("Products / versions", products, "Provider-product-version sets")
    with c3:
        kpi("Documents", len(docs), "PDF / TXT sources")
    with c4:
        kpi("Library backend", status["backend_label"], "Independent from deploys" if status["backend"] == "supabase" else "Local fallback")

    st.write("")
    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<div class="aps-section-title">Add source documents</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="aps-section-copy">Use one product family/version per upload. Multi-plan brochures are expected and supported.</div>',
                unsafe_allow_html=True,
            )
            st.write("")
            c1, c2 = st.columns(2)
            with c1:
                provider = st.text_input("Provider", placeholder="IMG")
                version = st.text_input("Version / year", value=str(date.today().year), placeholder="2026")
            with c2:
                product = st.text_input("Product / product family", placeholder="Global Prima Medical Insurance")
                doc_type_label = st.selectbox("Document type", list(DOC_TYPES.keys()))

            with st.expander("Version details and notes", expanded=False):
                d1, d2 = st.columns(2)
                with d1:
                    effective_from = st.text_input("Effective from", placeholder="2026-01-01")
                with d2:
                    effective_to = st.text_input("Effective to", placeholder="2026-12-31")
                notes = st.text_input("Notes", placeholder="Europe version / intermediary edition / etc.")

            files = st.file_uploader(
                "Drop provider documents here",
                type=["pdf", "txt"],
                accept_multiple_files=True,
                key="library_upload",
                help="Brochures, Tables of Benefits, policy wording, underwriting guides and endorsements.",
            )

            if st.button("Save to Provider Library", type="primary", use_container_width=True):
                if not provider.strip() or not product.strip() or not version.strip() or not files:
                    st.warning("Provider, product, version and at least one file are required.")
                else:
                    created = 0
                    duplicates = 0
                    for f in files:
                        blob = f.getvalue()
                        try:
                            doc, was_created = save_provider_document(
                                provider=provider,
                                product=product,
                                version=version,
                                doc_type=DOC_TYPES[doc_type_label],
                                filename=f.name,
                                content=blob,
                                effective_from=effective_from,
                                effective_to=effective_to,
                                notes=notes,
                            )
                        except LibraryStorageError as exc:
                            st.error(f"Could not save {f.name}: {exc}")
                            continue
                        created += int(was_created)
                        duplicates += int(not was_created)

                        # Index source text once at library-ingestion time. This cache lives
                        # in Supabase too, so routine case analysis does not re-parse the
                        # same provider PDF after each Railway redeploy.
                        if was_created:
                            suffix = Path(f.name).suffix or ".bin"
                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                tmp.write(blob)
                                tmp_path = tmp.name
                            try:
                                indexed = extract_document(tmp_path, f.name)
                                if indexed.ok:
                                    cache_document_text(doc.id, indexed.text)
                                else:
                                    cache_document_text(doc.id, None, indexed.error)
                            except LibraryStorageError as exc:
                                st.caption(f"Saved {f.name}, but text-cache indexing could not be persisted: {exc}")
                            finally:
                                Path(tmp_path).unlink(missing_ok=True)
                    st.success(f"Saved {created} new document(s). {duplicates} exact duplicate(s) skipped.")
                    st.rerun()

    with right:
        with st.container(border=True):
            st.markdown('<div class="aps-section-title">Library status</div>', unsafe_allow_html=True)
            if status["backend"] == "supabase":
                st.markdown(
                    '<div class="aps-section-copy">Permanent provider documents are stored in Supabase Postgres + private Storage and survive every Railway redeploy.</div>',
                    unsafe_allow_html=True,
                )
                st.write("")
                st.markdown(f"**Supabase project**  \n`{status['location']}`")
                st.markdown(f"**Private bucket**  \n`{status['bucket']}`")
                st.success("Persistent cloud library active", icon="✅")
            else:
                st.markdown(
                    '<div class="aps-section-copy">Supabase is not configured, so the app is using local/volume storage.</div>',
                    unsafe_allow_html=True,
                )
                st.write("")
                st.code(status["data_dir"], language=None)
                st.caption("Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to make the Library deploy-independent.")
            st.markdown("**Document policy**")
            st.markdown("• One source is stored once and reused across cases.\n\n• Exact duplicates are detected by SHA-256.\n\n• Parsed document text is cached persistently after first use.\n\n• Client quotations are not added to the permanent provider library automatically.")

    if status["backend"] == "supabase":
        legacy_count = local_library_count()
        if legacy_count:
            st.write("")
            with st.container(border=True):
                st.markdown("### ↗ Migrate existing Railway Library")
                st.caption(f"Found {legacy_count} document(s) in the old local/volume library. Copy them once to Supabase; originals are left untouched.")
                if st.button("Migrate local Library to Supabase", key="migrate_library", use_container_width=True):
                    with st.spinner("Copying provider documents to Supabase…"):
                        try:
                            migration = migrate_local_library_to_supabase()
                        except LibraryStorageError as exc:
                            st.error(str(exc))
                        else:
                            st.success(
                                f"Migration finished: {migration['created']} copied, "
                                f"{migration['duplicates']} duplicates skipped, {migration['failed']} failed."
                            )
                            if migration["errors"]:
                                with st.expander("Migration details"):
                                    for err in migration["errors"]:
                                        st.write("•", err)
                            st.rerun()

    st.write("")
    st.markdown('<div class="aps-section-title">Catalog</div>', unsafe_allow_html=True)
    st.markdown('<div class="aps-section-copy">Current provider/product/version sets available to Case Studio.</div>', unsafe_allow_html=True)
    if not catalog:
        st.info("The Provider Library is empty. Upload the first provider brochure above.")
        return

    catalog_df = pd.DataFrame(catalog).rename(
        columns={
            "provider": "Provider",
            "product": "Product",
            "version": "Version",
            "document_count": "Documents",
            "last_updated": "Last updated",
        }
    )
    st.dataframe(catalog_df, use_container_width=True, hide_index=True)

    with st.expander("Manage individual documents", expanded=False):
        for doc in docs:
            cols = st.columns([5, 1.2, 1])
            with cols[0]:
                st.markdown(f"**{doc.provider} · {doc.product} · {doc.version}**")
                st.caption(f"{doc.doc_type} · {doc.original_filename}")
            with cols[1]:
                try:
                    st.download_button(
                        "Download",
                        data=read_document_bytes(doc),
                        file_name=doc.original_filename,
                        key=f"download_{doc.id}",
                        use_container_width=True,
                    )
                except (OSError, LibraryStorageError) as exc:
                    st.caption(f"Unavailable: {exc}")
            with cols[2]:
                if st.button("Delete", key=f"del_{doc.id}", use_container_width=True):
                    try:
                        delete_document(doc.id)
                    except LibraryStorageError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()


# -----------------------------------------------------------------------------
# Case Studio + grounded chat
# -----------------------------------------------------------------------------

def render_provider_result(result: dict) -> None:
    analysis = result.get("analysis") or {}
    selection = result.get("plan_selection") or {}

    if analysis.get("error"):
        st.error(f"Analysis could not be completed: {analysis.get('error')}")
        if analysis.get("error_detail"):
            st.caption(analysis.get("error_detail"))
        with st.expander("Technical diagnostic", expanded=False):
            if analysis.get("raw_response_excerpt"):
                st.code(analysis.get("raw_response_excerpt"), language="text")
            st.json(analysis)
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Premium", _premium_display(analysis), "Applicant-specific quote")
    with c2:
        kpi("Annual limit", _compact_card_value(analysis.get("annual_limit", "—")), "Target plan")
    with c3:
        kpi("Deductible / excess", _compact_card_value(analysis.get("deductible_or_excess", "—")), "Quoted structure")
    with c4:
        kpi("Area", _compact_card_value(analysis.get("area_of_cover", "—")), f"Confidence: {analysis.get('confidence', '—')}")

    st.write("")
    tab_summary, tab_benefits, tab_evidence, tab_raw = st.tabs(
        ["Summary", "Benefits", "Evidence audit", "Raw extraction"]
    )

    with tab_summary:
        c_left, c_right = st.columns([1.2, .8])
        with c_left:
            st.markdown("#### Plan lock")
            st.markdown(f"**{result.get('target_plan') or 'No plan identified'}**")
            st.caption(
                f"Method: {selection.get('method', 'unknown')} · confidence: {selection.get('confidence', 'unknown')}"
            )
            if selection.get("evidence"):
                st.markdown(f'<div class="aps-source">{html.escape(str(selection.get("evidence")))}</div>', unsafe_allow_html=True)
            if result.get("focused_rows"):
                st.success(f"{len(result['focused_rows'])} target-plan benefit rows were isolated before AI analysis.")
            else:
                st.warning("No deterministic table rows were isolated. Review plan-specific values carefully.")

        with c_right:
            st.markdown("#### Underwriting")
            underwriting = analysis.get("underwriting") or {}
            st.write(underwriting.get("basis", "Not specified"))
            st.caption(underwriting.get("pre_existing_conditions", "Not specified"))

        limitations = analysis.get("critical_limitations") or []
        if limitations:
            st.markdown("#### Important limitations")
            for item in limitations:
                page = item.get("source_page")
                suffix = f" · p.{page}" if page else ""
                st.warning(f"**{item.get('topic', 'Limitation')}** — {item.get('detail', '')}{suffix}")

        optional = analysis.get("optional_benefits") or []
        optional = [x for x in optional if x.get("benefit")]
        if optional:
            st.markdown("#### Optional benefits")
            for item in optional:
                st.info(
                    f"**{item.get('benefit')}** — {item.get('status', 'Optional')}"
                    + (f" · {item.get('limit')}" if item.get('limit') else "")
                    + (f" · waiting: {item.get('waiting_period')}" if item.get('waiting_period') else "")
                )

    with tab_benefits:
        benefits = analysis.get("benefits") or {}
        if benefits:
            benefit_df = pd.DataFrame(
                [{"Benefit": k.replace("_", " ").title(), "Target-plan position": v} for k, v in benefits.items()]
            )
            st.dataframe(benefit_df, use_container_width=True, hide_index=True)
        waiting = analysis.get("waiting_periods") or []
        if waiting:
            st.markdown("**Waiting periods**")
            for w in waiting:
                st.markdown(f"- {w}")

    with tab_evidence:
        if result.get("library_source"):
            r = result["library_source"]
            st.caption(
                f"Library source: {r['provider']} / {r['product']} / {r['version']} · "
                f"{len(result.get('library_files') or [])} document(s)"
            )
        if result.get("focused_rows"):
            df_focus = pd.DataFrame(result["focused_rows"])
            cols = [c for c in ["source_file", "page", "section", "benefit", "value", "evidence_type"] if c in df_focus.columns]
            st.dataframe(df_focus[cols], use_container_width=True, hide_index=True, height=430)
        else:
            st.info("No multi-plan table evidence was isolated from the supplied PDFs.")

        source_evidence = analysis.get("source_evidence") or []
        source_evidence = [x for x in source_evidence if x.get("field") or x.get("evidence")]
        if source_evidence:
            st.markdown("#### AI source map")
            st.dataframe(pd.DataFrame(source_evidence), use_container_width=True, hide_index=True)

    with tab_raw:
        st.json(analysis)


def render_case_chat(results: list[dict]) -> None:
    st.markdown(
        """
        <div class="aps-chat-shell">
          <div class="aps-chat-title">◉ Ask HAL</div>
          <div class="aps-chat-copy">Interrogate this case. HAL is grounded in the analyzed plans and target-plan evidence.</div>
          <div class="aps-chat-empty">Try: “What is the biggest practical difference in chronic-condition cover?” or “Which clauses should I verify before presenting this to the client?”</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.session_state.setdefault("case_chat", [])
    for msg in st.session_state["case_chat"][-8:]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    q1, q2 = st.columns(2)
    with q1:
        if st.button("Key differences", key="quick_diff", use_container_width=True):
            st.session_state["chat_prefill"] = "What are the most important practical differences between these plans for the client?"
    with q2:
        if st.button("Risk flags", key="quick_risk", use_container_width=True):
            st.session_state["chat_prefill"] = "What are the most important limitations, uncertainties or clauses I should verify before presenting these options?"

    prefill = st.session_state.pop("chat_prefill", "")
    with st.form("case_chat_form", clear_on_submit=True):
        question = st.text_area(
            "Ask about the analysis",
            value=prefill,
            placeholder="Ask HAL to compare, explain or challenge the analysis…",
            height=90,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Send to HAL", type="primary", use_container_width=True)

    if submitted and question.strip():
        st.session_state["case_chat"].append({"role": "user", "content": question.strip()})
        with st.spinner("HAL is reviewing the case evidence…"):
            answer = ask_case_agent(
                question=question.strip(),
                case_reference=st.session_state.get("case_reference", ""),
                results=results,
                history=st.session_state["case_chat"],
            )
        st.session_state["case_chat"].append({"role": "assistant", "content": answer})
        st.rerun()

    if st.session_state.get("case_chat") and st.button("Clear chat", key="clear_chat", use_container_width=True):
        st.session_state["case_chat"] = []
        st.rerun()


def render_client_deliverable(results: list[dict]) -> None:
    st.write("")
    st.markdown(
        """
        <div class="aps-report-hero">
          <div class="aps-report-kicker">CLIENT DELIVERABLE</div>
          <div class="aps-report-title">Turn the case analysis into a client-ready Ashlar report.</div>
          <div class="aps-report-copy">The final document presents each plan, compares the material terms, explains the differences that matter, and concludes with a reasoned Ashlar Assessment grounded only in the case evidence.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    reviewed = st.checkbox(
        "I have reviewed the material extracted facts and plan locks before generating the client analysis.",
        key="client_report_reviewed",
    )
    c1, c2 = st.columns([1.1, 3.9])
    with c1:
        generate = st.button(
            "Generate Client Analysis →",
            type="primary",
            use_container_width=True,
            disabled=not reviewed,
        )
    with c2:
        st.caption("The narrative is regenerated only when you press the button. Existing plan facts remain unchanged.")

    if generate:
        with st.spinner("Building the client-facing comparison and Ashlar Assessment…"):
            generated = generate_client_analysis(
                case_reference=st.session_state.get("case_reference", ""),
                client_name=st.session_state.get("client_name", ""),
                client_profile=st.session_state.get("client_profile", ""),
                client_priorities=st.session_state.get("client_priorities", ""),
                results=results,
                language=st.session_state.get("report_language", "English"),
            )
        st.session_state["client_analysis"] = generated
        st.rerun()

    report = st.session_state.get("client_analysis")
    if not report:
        return

    if report.get("generation_warning"):
        st.warning(report["generation_warning"])

    st.write("")
    preview, compare, export = st.tabs(["Client preview", "Comparison matrix", "Export PDF / PPTX"])

    with preview:
        st.markdown(f"## {report.get('report_title') or 'Insurance Comparative Analysis'}")
        if report.get("executive_summary"):
            st.markdown(report["executive_summary"])

        st.markdown("### The plans")
        for plan in report.get("plans") or []:
            with st.container(border=True):
                st.markdown(f"#### {plan.get('provider','')} · {plan.get('plan_name','')}")
                if plan.get("positioning"):
                    st.caption(plan["positioning"])
                st.write(plan.get("summary") or "")
                left, right = st.columns(2)
                with left:
                    if plan.get("strengths"):
                        st.markdown("**Strengths**")
                        for x in plan["strengths"]:
                            st.markdown(f"- {x}")
                with right:
                    if plan.get("considerations"):
                        st.markdown("**Points to consider**")
                        for x in plan["considerations"]:
                            st.markdown(f"- {x}")

        diffs = report.get("key_differences") or []
        if diffs:
            st.markdown("### Key differences that matter")
            for d in diffs:
                title = html.escape(str(d.get("title") or "Difference"))
                analysis_text = html.escape(str(d.get("analysis") or ""))
                impact = html.escape(str(d.get("client_impact") or ""))
                st.markdown(
                    f'<div class="aps-diff-card"><div class="aps-diff-title">{title}</div><div>{analysis_text}</div><div class="aps-diff-impact">Client impact: {impact}</div></div>',
                    unsafe_allow_html=True,
                )

        ass = report.get("ashlar_assessment") or {}
        st.markdown("### Ashlar Assessment")
        headline = html.escape(str(ass.get("headline") or ""))
        st.markdown(
            f'<div class="aps-assessment"><div class="aps-assessment-title">OUR VIEW</div><div class="aps-assessment-head">{headline}</div></div>',
            unsafe_allow_html=True,
        )
        if ass.get("recommended_provider") or ass.get("recommended_plan"):
            st.success(f"Preferred fit: **{ass.get('recommended_provider','')} {ass.get('recommended_plan','')}**")
        for reason in ass.get("reasoning") or []:
            st.markdown(f"- {reason}")
        if ass.get("alternative_provider") or ass.get("alternative_plan"):
            st.info(
                f"**Alternative:** {ass.get('alternative_provider','')} {ass.get('alternative_plan','')} — "
                f"{ass.get('alternative_reason','')}"
            )

        if report.get("important_considerations"):
            st.markdown("### Important considerations")
            for x in report["important_considerations"]:
                st.markdown(f"- {x}")

    with compare:
        matrix = report.get("comparison_matrix") or build_comparison_matrix(results)
        names = [plan_display_name(r) for r in results]
        comp_rows = []
        for row in matrix:
            item = {"Benefit / term": row.get("topic")}
            item.update({name: (row.get("values") or {}).get(name, "—") for name in names})
            comp_rows.append(item)
        if comp_rows:
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True, height=620)

    with export:
        language = st.session_state.get("report_language", "English")
        client_name = st.session_state.get("client_name") or st.session_state.get("case_reference") or "Client"
        safe_name = "".join(c if c.isalnum() else "_" for c in client_name).strip("_") or "Client"
        try:
            pptx_bytes = build_pptx_bytes(client_analysis=report, results=results, language=language)
            pdf_bytes = build_pdf_bytes(client_analysis=report, results=results, language=language)
            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    "Download Ashlar PPTX",
                    data=pptx_bytes,
                    file_name=f"{safe_name}_Ashlar_Insurance_Analysis.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )
            with d2:
                st.download_button(
                    "Download Ashlar PDF",
                    data=pdf_bytes,
                    file_name=f"{safe_name}_Ashlar_Insurance_Analysis.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            st.caption("Both files use the same grounded client analysis and comparison matrix.")
        except Exception as exc:
            st.error(f"Could not build the client files: {exc}")
            with st.expander("Technical diagnostic", expanded=False):
                st.exception(exc)


def case_workspace_page() -> None:
    ai_online = bool(os.getenv("ANTHROPIC_API_KEY"))
    page_header(
        "INSURANCE INTELLIGENCE, WITH EVIDENCE",
        "Build a proposal from the evidence — not from guesswork.",
        "Upload the client's quotations, connect each option to the permanent provider library, isolate the exact plan from multi-plan brochures, and interrogate the analysis with HAL before creating the client presentation.",
        [
            ("AI online" if ai_online else "AI not configured", "good" if ai_online else "warn"),
            ("Target-plan locked", "purple"),
            ("Client report", "good"),
        ],
    )

    st.session_state.setdefault("n_providers", 2)
    st.session_state.setdefault("results", [])

    with st.container(border=True):
        h1, h2 = st.columns([1.5, .5])
        with h1:
            st.markdown('<div class="aps-section-title">Case</div>', unsafe_allow_html=True)
            st.markdown('<div class="aps-section-copy">Give the case a private internal reference. This is not sent to the provider library.</div>', unsafe_allow_html=True)
        with h2:
            st.caption("CASE WORKSPACE")
        case_cols = st.columns([1.25, 1.25, .7])
        with case_cols[0]:
            st.text_input(
                "Case / client reference",
                key="case_reference",
                placeholder="Internal reference — e.g. Alexopoulou / Rogavopoulos",
            )
        with case_cols[1]:
            st.text_input(
                "Client name for the report",
                key="client_name",
                placeholder="Name shown on PDF / PPTX",
            )
        with case_cols[2]:
            st.selectbox(
                "Report language",
                ["English", "Greek"],
                key="report_language",
            )
        profile_cols = st.columns(2)
        with profile_cols[0]:
            st.text_area(
                "Client profile / context",
                key="client_profile",
                placeholder="e.g. family of 3, resident in Greece, moving from existing international cover…",
                height=86,
            )
        with profile_cols[1]:
            st.text_area(
                "What matters most to the client",
                key="client_priorities",
                placeholder="e.g. continuity for existing conditions, nil excess, strong outpatient, worldwide excluding USA…",
                height=86,
            )

    try:
        catalog = list_catalog()
    except LibraryStorageError as exc:
        st.warning(f"Provider Library unavailable: {exc}")
        catalog = []
    catalog_labels = {f"{r['provider']} — {r['product']} — {r['version']}": r for r in catalog}

    st.write("")
    st.markdown('<div class="aps-section-title">Insurance options</div>', unsafe_allow_html=True)
    st.markdown('<div class="aps-section-copy">Each option combines the applicant-specific quote with reusable provider knowledge.</div>', unsafe_allow_html=True)

    slots = []
    for i in range(st.session_state["n_providers"]):
        with st.container(border=True):
            st.markdown(
                f'<div class="aps-provider-head"><div><span class="aps-provider-index">{i+1}</span><span class="aps-provider-name">Option {i+1}</span></div><div class="aps-helper">Quote + verified provider sources</div></div>',
                unsafe_allow_html=True,
            )
            st.write("")
            c1, c2 = st.columns([1.25, .75])
            with c1:
                if catalog_labels:
                    library_choice = st.selectbox(
                        "Provider library source",
                        ["— Manual / no library source —"] + list(catalog_labels.keys()),
                        key=f"library_choice_{i}",
                    )
                else:
                    library_choice = "— Manual / no library source —"
                    st.info("Provider Library is empty. Add provider sources from Admin Library or use case-specific documents.")
            library_row = catalog_labels.get(library_choice)
            with c2:
                target_override = st.text_input(
                    "Selected plan override",
                    key=f"target_{i}",
                    placeholder="Optional — e.g. Silver",
                    help="Leave blank to infer the selected plan from the quotation/certificate.",
                )

            default_label = library_row["provider"] if library_row else f"Provider {i+1}"
            label = st.text_input(
                "Display label",
                key=f"label_{i}",
                placeholder=default_label,
                help="Used in the comparison and presentation.",
            )
            label = label.strip() or default_label

            st.markdown("**Client quotation / certificate**")
            q = st.file_uploader(
                "Upload client quote",
                type=["pdf", "txt"],
                accept_multiple_files=True,
                key=f"q_{i}",
                label_visibility="collapsed",
                help="Applicant-specific source for selected plan, premium, area, excess and chosen options.",
            )

            with st.expander("Add case-specific brochure, wording or endorsement", expanded=False):
                b1, b2 = st.columns(2)
                with b1:
                    manual_b = st.file_uploader(
                        "Brochure / Table of Benefits",
                        type=["pdf", "txt"],
                        accept_multiple_files=True,
                        key=f"b_{i}",
                    )
                with b2:
                    manual_w = st.file_uploader(
                        "Wording / endorsement / correspondence",
                        type=["pdf", "txt"],
                        accept_multiple_files=True,
                        key=f"w_{i}",
                    )

            slots.append(
                {
                    "label": label,
                    "target_override": target_override.strip(),
                    "quote": q or [],
                    "manual_brochure": manual_b or [],
                    "manual_wording": manual_w or [],
                    "library_row": library_row,
                }
            )

    c1, c2, c3 = st.columns([1, 1, 4])
    with c1:
        if st.button("＋ Add option", use_container_width=True):
            st.session_state["n_providers"] += 1
            st.rerun()
    with c2:
        if st.session_state["n_providers"] > 1 and st.button("− Remove last", use_container_width=True):
            st.session_state["n_providers"] -= 1
            st.rerun()
    with c3:
        analyze_clicked = st.button("Analyze case →", type="primary", use_container_width=True)

    if analyze_clicked:
        active = [
            s for s in slots
            if s["quote"] or s["manual_brochure"] or s["manual_wording"] or s["library_row"]
        ]
        if not active:
            st.warning("Add at least one quote or provider-library source.")
        else:
            all_results = []
            progress = st.progress(0.0, text="Preparing case evidence…")
            for idx, slot in enumerate(active, start=1):
                progress.progress((idx - 1) / len(active), text=f"Analyzing {slot['label']}…")

                quotation_text, _ = _extract_uploaded(slot["quote"])
                manual_brochure_text, manual_brochure_pdfs = _extract_uploaded(slot["manual_brochure"])
                manual_wording_text, manual_wording_pdfs = _extract_uploaded(slot["manual_wording"])

                lib_brochure_text = ""
                lib_wording_text = ""
                library_plan_docs = []
                library_docs = []
                if slot["library_row"]:
                    row = slot["library_row"]
                    try:
                        library_docs = get_documents(row["provider"], row["product"], row["version"])
                    except LibraryStorageError as exc:
                        st.error(f"Could not load {row['provider']} Library sources: {exc}")
                        library_docs = []
                    lib_brochure_text, lib_wording_text, library_plan_docs = _extract_library_documents(library_docs)

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
                    for library_doc in library_plan_docs:
                        try:
                            with materialize_document(library_doc) as path:
                                focused = extract_target_plan_from_pdf(path, target_plan)
                        except LibraryStorageError as exc:
                            st.warning(f"Could not read {library_doc.original_filename}: {exc}")
                            continue
                        if focused.rows:
                            focused_blocks.append(
                                f"--- SOURCE FILE: {library_doc.original_filename} ---\n{focused.to_prompt_context()}"
                            )
                            focused_rows.extend([
                                {"source_file": library_doc.original_filename, **row.__dict__}
                                for row in focused.rows
                            ])

                    for filename, blob in manual_brochure_pdfs + manual_wording_pdfs:
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
                    provider_label=slot["label"],
                    target_plan=target_plan,
                    quotation_text=quotation_text,
                    brochure_text=brochure_text,
                    wording_text=wording_text,
                    focused_table_context="\n\n".join(focused_blocks),
                )

                all_results.append(
                    {
                        "provider": slot["label"],
                        "library_source": slot["library_row"],
                        "library_files": [d.original_filename for d in library_docs],
                        "plan_selection": selection,
                        "target_plan": target_plan,
                        "focused_rows": focused_rows,
                        "analysis": analysis,
                    }
                )
                progress.progress(idx / len(active), text=f"Completed {slot['label']}")

            st.session_state["results"] = all_results
            st.session_state["case_chat"] = []
            st.session_state["client_analysis"] = None
            progress.empty()
            st.rerun()

    results = st.session_state.get("results", [])
    if not results:
        st.write("")
        with st.container(border=True):
            st.markdown("### How Proposal Studio will work")
            steps = pd.DataFrame(
                [
                    ["1", "Quote", "Read applicant-specific premium, selected plan, area and excess."],
                    ["2", "Library", "Load the matching brochure, Table of Benefits and policy wording."],
                    ["3", "Plan lock", "Isolate only the selected plan from a multi-plan brochure."],
                    ["4", "Analyze", "Build structured, source-aware comparison evidence."],
                    ["5", "Ask HAL", "Interrogate differences, limitations and uncertainties before presentation."],
                ],
                columns=["Step", "Stage", "What happens"],
            )
            st.dataframe(steps, use_container_width=True, hide_index=True)
        return

    st.write("")
    st.markdown('<div class="aps-section-title">Case analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="aps-section-copy">Structured comparison on the left, grounded HAL conversation on the right.</div>', unsafe_allow_html=True)

    evidence_count = sum(len(r.get("focused_rows") or []) for r in results)
    plans_locked = sum(bool(r.get("target_plan")) for r in results)
    k1, k2, k3 = st.columns(3)
    with k1:
        kpi("Options analyzed", str(len(results)), "Current case")
    with k2:
        kpi("Plans locked", f"{plans_locked}/{len(results)}", "Selected tier identified")
    with k3:
        kpi("Evidence rows", str(evidence_count), "Deterministically isolated")

    st.write("")
    summary_rows = []
    for result in results:
        a = result.get("analysis") or {}
        summary_rows.append(
            {
                "Provider": a.get("provider") or result["provider"],
                "Plan": a.get("plan_name") or result.get("target_plan") or "—",
                "Premium": _premium_display(a),
                "Annual limit": a.get("annual_limit", "—"),
                "Deductible / excess": a.get("deductible_or_excess", "—"),
                "Area": a.get("area_of_cover", "—"),
                "Confidence": a.get("confidence", "—"),
            }
        )
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.write("")
    analysis_col, chat_col = st.columns([1.62, .78], gap="large")
    with analysis_col:
        provider_tabs = st.tabs([f"{r['provider']} · {r.get('target_plan') or 'Plan not locked'}" for r in results])
        for tab, result in zip(provider_tabs, results):
            with tab:
                render_provider_result(result)

    with chat_col:
        render_case_chat(results)

    render_client_deliverable(results)


# -----------------------------------------------------------------------------
# Navigation
# -----------------------------------------------------------------------------

inject_styles()

with st.sidebar:
    st.markdown("### ASHLAR ASSURANCE")
    st.markdown("# Proposal Studio")
    st.caption("Evidence-first insurance proposal intelligence")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["◈ Case Studio", "▣ Admin Library"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    ai_online = bool(os.getenv("ANTHROPIC_API_KEY"))
    status = "● AI online" if ai_online else "○ AI not configured"
    st.caption(status)
    st.caption("Target-plan extraction · Provider library · Grounded case chat")

if page == "▣ Admin Library":
    provider_library_page()
else:
    case_workspace_page()
