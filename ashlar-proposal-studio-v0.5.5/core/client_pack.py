"""Client-delivery helpers for provider brochures and supporting source packs."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import zipfile

from .storage import (
    LibraryDocument,
    LibraryStorageError,
    create_document_signed_url,
    get_documents,
    read_document_bytes,
)


@dataclass
class ClientSourceDocument:
    provider_label: str
    plan_name: str
    document: LibraryDocument
    signed_url: str | None = None

    def as_report_dict(self) -> dict:
        return {
            "provider": self.provider_label,
            "plan_name": self.plan_name,
            "doc_type": self.document.doc_type,
            "filename": self.document.original_filename,
            "url": self.signed_url,
        }


def _safe_part(value: str, fallback: str = "document") -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "-", str(value or "").strip())
    value = re.sub(r"\s+", " ", value).strip(" .-_/")
    return value or fallback


def collect_client_source_documents(
    results: list[dict],
    *,
    include_wording: bool = False,
    include_supporting: bool = False,
    link_ttl_seconds: int = 30 * 24 * 60 * 60,
) -> tuple[list[ClientSourceDocument], list[str]]:
    """Resolve reusable provider documents attached to the plans in a case.

    Brochures and Tables of Benefits are always included. Policy wording/member
    guides and supporting documents are opt-in because those files can be large.
    Exact duplicates are removed by SHA-256 even if referenced by multiple plans.
    """
    allowed = {"brochure", "tob"}
    if include_wording:
        allowed |= {"wording", "underwriting"}
    if include_supporting:
        allowed |= {"supporting"}

    out: list[ClientSourceDocument] = []
    warnings: list[str] = []
    seen_sha: set[str] = set()

    for result in results or []:
        source = result.get("library_source") or {}
        if not source:
            continue
        provider = str(source.get("provider") or "").strip()
        product = str(source.get("product") or "").strip()
        version = str(source.get("version") or "").strip()
        if not (provider and product and version):
            continue
        try:
            docs = get_documents(provider, product, version)
        except LibraryStorageError as exc:
            warnings.append(f"{provider}: provider documents could not be loaded ({exc}).")
            continue

        provider_label = str(result.get("provider") or provider).strip() or provider
        analysis = result.get("analysis") or {}
        plan_name = str(analysis.get("plan_name") or result.get("target_plan") or product).strip()

        matching = [d for d in docs if d.doc_type in allowed and Path(d.original_filename).suffix.lower() == ".pdf"]
        for doc in matching:
            if doc.sha256 in seen_sha:
                continue
            seen_sha.add(doc.sha256)
            signed_url = None
            try:
                signed_url = create_document_signed_url(doc, link_ttl_seconds)
            except LibraryStorageError as exc:
                warnings.append(f"{doc.original_filename}: temporary link unavailable ({exc}).")
            out.append(ClientSourceDocument(provider_label, plan_name, doc, signed_url))

    return out, warnings


def build_source_manifest(source_documents: list[ClientSourceDocument], *, link_validity_days: int | None = None) -> str:
    lines = [
        "ASHLAR ASSURANCE - OFFICIAL PROVIDER DOCUMENTS",
        "",
        "The files below are the provider brochures / source documents used alongside the Ashlar comparative analysis.",
        "The insurer's governing policy documents and final underwriting terms remain controlling.",
    ]
    if link_validity_days:
        lines += ["", f"Temporary web links are intended to remain valid for approximately {link_validity_days} day(s)."]
    lines.append("")
    for item in source_documents:
        lines.append(f"{item.provider_label} - {item.plan_name}")
        lines.append(f"  {item.document.doc_type}: {item.document.original_filename}")
        if item.signed_url:
            lines.append(f"  Link: {item.signed_url}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_client_pack_zip(
    *,
    report_pdf_bytes: bytes,
    report_pdf_filename: str,
    source_documents: list[ClientSourceDocument],
    pptx_bytes: bytes | None = None,
    pptx_filename: str | None = None,
    link_validity_days: int | None = None,
) -> bytes:
    """Create one client-ready ZIP: Ashlar report + official provider PDFs."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_safe_part(report_pdf_filename, "Ashlar_Insurance_Analysis.pdf"), report_pdf_bytes)
        if pptx_bytes and pptx_filename:
            zf.writestr(_safe_part(pptx_filename, "Ashlar_Insurance_Analysis.pptx"), pptx_bytes)

        for item in source_documents:
            provider_folder = _safe_part(item.provider_label, "Provider")
            filename = _safe_part(item.document.original_filename, f"{item.document.id}.pdf")
            try:
                blob = read_document_bytes(item.document)
            except LibraryStorageError as exc:
                zf.writestr(
                    f"Provider Documents/{provider_folder}/ERROR_{filename}.txt",
                    f"Could not include {item.document.original_filename}: {exc}\n",
                )
                continue
            zf.writestr(f"Provider Documents/{provider_folder}/{filename}", blob)

        zf.writestr(
            "Provider Documents/README.txt",
            build_source_manifest(source_documents, link_validity_days=link_validity_days),
        )
    return buf.getvalue()
