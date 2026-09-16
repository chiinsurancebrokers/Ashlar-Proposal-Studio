"""Optional client email delivery through Resend.

The Proposal Studio remains fully usable without Resend. When configured, the
server can send the Ashlar analysis together with either brochure links or the
provider PDFs themselves.
"""
from __future__ import annotations

import base64
import html
import os

import httpx

from .client_pack import ClientSourceDocument
from .storage import LibraryStorageError, read_document_bytes


class EmailDeliveryError(RuntimeError):
    pass


def email_delivery_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY", "").strip() and os.getenv("ASHLAR_EMAIL_FROM", "").strip())


def email_delivery_status() -> dict:
    return {
        "configured": email_delivery_configured(),
        "from": os.getenv("ASHLAR_EMAIL_FROM", "").strip(),
        "reply_to": os.getenv("ASHLAR_EMAIL_REPLY_TO", "").strip(),
    }


def _source_links_html(source_documents: list[ClientSourceDocument]) -> str:
    rows = []
    for item in source_documents:
        if not item.signed_url:
            continue
        label = f"{item.provider_label} - {item.plan_name}: {item.document.original_filename}"
        rows.append(f'<li><a href="{html.escape(item.signed_url, quote=True)}">{html.escape(label)}</a></li>')
    if not rows:
        return ""
    return "<p><strong>Official provider documents:</strong></p><ul>" + "".join(rows) + "</ul>"


def send_client_email(
    *,
    recipient: str,
    subject: str,
    body_text: str,
    report_pdf_filename: str,
    report_pdf_bytes: bytes,
    source_documents: list[ClientSourceDocument],
    attach_brochures: bool = False,
    max_attachment_bytes: int = 18 * 1024 * 1024,
) -> dict:
    if not email_delivery_configured():
        raise EmailDeliveryError("Email delivery is not configured. Set RESEND_API_KEY and ASHLAR_EMAIL_FROM in Railway.")
    recipient = (recipient or "").strip()
    if "@" not in recipient:
        raise EmailDeliveryError("Enter a valid recipient email address.")

    escaped_body = html.escape(body_text or "").replace("\n", "<br>")
    links_html = _source_links_html(source_documents)
    html_body = f"<p>{escaped_body}</p>{links_html}<p style='color:#6C768A;font-size:12px'>Provider documents remain subject to the insurer's governing terms and current versions.</p>"

    attachments = [
        {
            "filename": report_pdf_filename,
            "content": base64.b64encode(report_pdf_bytes).decode("ascii"),
        }
    ]
    total_bytes = len(report_pdf_bytes)
    if attach_brochures:
        for item in source_documents:
            try:
                blob = read_document_bytes(item.document)
            except LibraryStorageError as exc:
                raise EmailDeliveryError(f"Could not attach {item.document.original_filename}: {exc}") from exc
            total_bytes += len(blob)
            if total_bytes > max_attachment_bytes:
                raise EmailDeliveryError(
                    "The report plus brochure attachments exceed the safe email-size limit. "
                    "Use 'PDF + secure brochure links' or download the Client Pack ZIP instead."
                )
            attachments.append(
                {
                    "filename": item.document.original_filename,
                    "content": base64.b64encode(blob).decode("ascii"),
                }
            )

    payload = {
        "from": os.getenv("ASHLAR_EMAIL_FROM", "").strip(),
        "to": [recipient],
        "subject": subject,
        "html": html_body,
        "attachments": attachments,
    }
    reply_to = os.getenv("ASHLAR_EMAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {os.getenv('RESEND_API_KEY', '').strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
    except Exception as exc:
        raise EmailDeliveryError(f"Email service could not be reached: {exc}") from exc
    if response.status_code >= 300:
        detail = response.text[:800]
        raise EmailDeliveryError(f"Email delivery failed ({response.status_code}): {detail}")
    try:
        return response.json()
    except Exception:
        return {"ok": True, "status_code": response.status_code}
