"""Persistent provider document library for Ashlar Proposal Studio.

Designed for Railway with a Volume mounted at DATA_DIR (recommended: /app/data).
Metadata is stored in SQLite; uploaded documents are stored on disk next to it.
No client document is committed to GitHub.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import re
import shutil
import sqlite3
import uuid


def _default_data_dir() -> Path:
    configured = os.getenv("DATA_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data"


DATA_DIR = _default_data_dir()
DB_PATH = DATA_DIR / "proposal_studio.db"
DOCS_DIR = DATA_DIR / "provider_documents"


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip())
    return value.strip("-._") or "unknown"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_documents (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            product TEXT NOT NULL,
            version TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            effective_from TEXT,
            effective_to TEXT,
            notes TEXT,
            uploaded_at TEXT NOT NULL,
            UNIQUE(provider, product, version, doc_type, sha256)
        )
        """
    )
    return conn


@dataclass
class LibraryDocument:
    id: str
    provider: str
    product: str
    version: str
    doc_type: str
    original_filename: str
    stored_path: str
    sha256: str
    effective_from: str | None = None
    effective_to: str | None = None
    notes: str | None = None
    uploaded_at: str = ""

    @property
    def path(self) -> Path:
        return Path(self.stored_path)

    def as_dict(self) -> dict:
        return asdict(self)


def save_provider_document(
    *,
    provider: str,
    product: str,
    version: str,
    doc_type: str,
    filename: str,
    content: bytes,
    effective_from: str = "",
    effective_to: str = "",
    notes: str = "",
) -> tuple[LibraryDocument, bool]:
    """Persist a provider document. Returns (document, created_new)."""
    provider = provider.strip()
    product = product.strip()
    version = version.strip()
    doc_type = doc_type.strip().lower()
    if not provider or not product or not version or not doc_type:
        raise ValueError("provider, product, version and doc_type are required")
    if not content:
        raise ValueError("document is empty")

    digest = hashlib.sha256(content).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    conn = _connect()
    try:
        existing = conn.execute(
            """
            SELECT * FROM provider_documents
            WHERE provider = ? AND product = ? AND version = ? AND doc_type = ? AND sha256 = ?
            """,
            (provider, product, version, doc_type, digest),
        ).fetchone()
        if existing:
            return LibraryDocument(**dict(existing)), False

        doc_id = uuid.uuid4().hex
        suffix = Path(filename).suffix.lower() or ".bin"
        folder = DOCS_DIR / _slug(provider) / _slug(product) / _slug(version) / _slug(doc_type)
        folder.mkdir(parents=True, exist_ok=True)
        stored = folder / f"{doc_id}{suffix}"
        stored.write_bytes(content)

        record = LibraryDocument(
            id=doc_id,
            provider=provider,
            product=product,
            version=version,
            doc_type=doc_type,
            original_filename=filename,
            stored_path=str(stored),
            sha256=digest,
            effective_from=effective_from.strip() or None,
            effective_to=effective_to.strip() or None,
            notes=notes.strip() or None,
            uploaded_at=now,
        )
        conn.execute(
            """
            INSERT INTO provider_documents
            (id, provider, product, version, doc_type, original_filename, stored_path,
             sha256, effective_from, effective_to, notes, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id, record.provider, record.product, record.version, record.doc_type,
                record.original_filename, record.stored_path, record.sha256,
                record.effective_from, record.effective_to, record.notes, record.uploaded_at,
            ),
        )
        conn.commit()
        return record, True
    finally:
        conn.close()


def list_documents() -> list[LibraryDocument]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM provider_documents ORDER BY provider, product, version DESC, doc_type, uploaded_at DESC"
        ).fetchall()
        return [LibraryDocument(**dict(r)) for r in rows]
    finally:
        conn.close()


def list_catalog() -> list[dict]:
    """Return one row per provider/product/version with document count."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT provider, product, version, COUNT(*) AS document_count,
                   MAX(uploaded_at) AS last_updated
            FROM provider_documents
            GROUP BY provider, product, version
            ORDER BY provider, product, version DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_documents(provider: str, product: str, version: str) -> list[LibraryDocument]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM provider_documents
            WHERE provider = ? AND product = ? AND version = ?
            ORDER BY doc_type, uploaded_at DESC
            """,
            (provider, product, version),
        ).fetchall()
        docs = [LibraryDocument(**dict(r)) for r in rows]
        return [d for d in docs if d.path.exists()]
    finally:
        conn.close()


def delete_document(doc_id: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM provider_documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            return False
        path = Path(row["stored_path"])
        conn.execute("DELETE FROM provider_documents WHERE id = ?", (doc_id,))
        conn.commit()
        path.unlink(missing_ok=True)
        # Remove now-empty leaf folders, but never DATA_DIR itself.
        parent = path.parent
        while parent != DOCS_DIR.parent and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return True
    finally:
        conn.close()


def storage_status() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(DATA_DIR)
    return {
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "documents_dir": str(DOCS_DIR),
        "free_gb": round(usage.free / (1024**3), 2),
    }
