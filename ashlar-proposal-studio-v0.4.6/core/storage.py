"""Persistent Provider Library for Ashlar Proposal Studio.

Production mode uses Supabase:
- Postgres table: provider_documents
- private Storage bucket: provider-library (configurable)

If Supabase is not configured, the app falls back to the original local
SQLite + filesystem backend. This makes local development easy while keeping
production provider knowledge independent from Railway redeploys.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import hashlib
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import uuid


class LibraryStorageError(RuntimeError):
    """Raised when the configured persistent library cannot be reached."""


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


def _supabase_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _supabase_key() -> str:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _supabase_key_kind() -> str:
    """Best-effort classification for diagnostics without exposing the key."""
    key = _supabase_key()
    if not key:
        return "missing"
    if key.startswith("sb_secret_"):
        return "secret"
    if key.startswith("sb_publishable_"):
        return "publishable"
    if key.startswith("eyJ"):
        # Legacy Supabase JWT keys (anon/service_role). We cannot decode/print the
        # secret here, but the API permission checks below will tell us whether it
        # behaves as a service-role credential.
        return "legacy_jwt"
    return "unknown"


def _supabase_bucket() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET", "provider-library").strip() or "provider-library"


def _supabase_table_name() -> str:
    return os.getenv("SUPABASE_LIBRARY_TABLE", "provider_documents").strip() or "provider_documents"


def supabase_configured() -> bool:
    return bool(_supabase_url() and _supabase_key())


def library_backend() -> str:
    """Return 'supabase' in production when credentials are present, else local."""
    requested = os.getenv("LIBRARY_BACKEND", "auto").strip().lower()
    if requested == "local":
        return "local"
    if requested == "supabase":
        if not supabase_configured():
            raise LibraryStorageError(
                "LIBRARY_BACKEND=supabase but SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing."
            )
        return "supabase"
    return "supabase" if supabase_configured() else "local"


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
    extracted_text: str | None = None
    extracted_at: str | None = None
    extraction_error: str | None = None
    backend: str = "local"

    @property
    def path(self) -> Path:
        """Local path compatibility. Remote callers should use materialize_document."""
        return Path(self.stored_path)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Local fallback backend
# ---------------------------------------------------------------------------

def _connect_local() -> sqlite3.Connection:
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
            extracted_text TEXT,
            extracted_at TEXT,
            extraction_error TEXT,
            UNIQUE(provider, product, version, doc_type, sha256)
        )
        """
    )
    # Upgrade older v0.4 SQLite libraries in-place.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(provider_documents)").fetchall()}
    for name, sql_type in (
        ("extracted_text", "TEXT"),
        ("extracted_at", "TEXT"),
        ("extraction_error", "TEXT"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE provider_documents ADD COLUMN {name} {sql_type}")
    conn.commit()
    return conn


def _row_to_doc(row, backend: str) -> LibraryDocument:
    data = dict(row)
    allowed = {f.name for f in LibraryDocument.__dataclass_fields__.values()}
    clean = {k: v for k, v in data.items() if k in allowed and k != "backend"}
    return LibraryDocument(**clean, backend=backend)


def _save_local(**kwargs) -> tuple[LibraryDocument, bool]:
    provider = kwargs["provider"].strip()
    product = kwargs["product"].strip()
    version = kwargs["version"].strip()
    doc_type = kwargs["doc_type"].strip().lower()
    filename = kwargs["filename"]
    content = kwargs["content"]
    if not provider or not product or not version or not doc_type:
        raise ValueError("provider, product, version and doc_type are required")
    if not content:
        raise ValueError("document is empty")

    digest = hashlib.sha256(content).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect_local()
    try:
        existing = conn.execute(
            """SELECT * FROM provider_documents
               WHERE provider=? AND product=? AND version=? AND doc_type=? AND sha256=?""",
            (provider, product, version, doc_type, digest),
        ).fetchone()
        if existing:
            return _row_to_doc(existing, "local"), False

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
            effective_from=(kwargs.get("effective_from") or "").strip() or None,
            effective_to=(kwargs.get("effective_to") or "").strip() or None,
            notes=(kwargs.get("notes") or "").strip() or None,
            uploaded_at=now,
            backend="local",
        )
        conn.execute(
            """INSERT INTO provider_documents
               (id,provider,product,version,doc_type,original_filename,stored_path,sha256,
                effective_from,effective_to,notes,uploaded_at,extracted_text,extracted_at,extraction_error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.id, record.provider, record.product, record.version, record.doc_type,
                record.original_filename, record.stored_path, record.sha256,
                record.effective_from, record.effective_to, record.notes, record.uploaded_at,
                None, None, None,
            ),
        )
        conn.commit()
        return record, True
    finally:
        conn.close()


def _list_local() -> list[LibraryDocument]:
    conn = _connect_local()
    try:
        rows = conn.execute(
            "SELECT * FROM provider_documents ORDER BY provider, product, version DESC, doc_type, uploaded_at DESC"
        ).fetchall()
        return [_row_to_doc(r, "local") for r in rows]
    finally:
        conn.close()


def _get_local(provider: str, product: str, version: str) -> list[LibraryDocument]:
    conn = _connect_local()
    try:
        rows = conn.execute(
            """SELECT * FROM provider_documents WHERE provider=? AND product=? AND version=?
               ORDER BY doc_type, uploaded_at DESC""",
            (provider, product, version),
        ).fetchall()
        return [d for d in (_row_to_doc(r, "local") for r in rows) if d.path.exists()]
    finally:
        conn.close()


def _delete_local(doc_id: str) -> bool:
    conn = _connect_local()
    try:
        row = conn.execute("SELECT * FROM provider_documents WHERE id=?", (doc_id,)).fetchone()
        if not row:
            return False
        path = Path(row["stored_path"])
        conn.execute("DELETE FROM provider_documents WHERE id=?", (doc_id,))
        conn.commit()
        path.unlink(missing_ok=True)
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


# ---------------------------------------------------------------------------
# Supabase production backend
# ---------------------------------------------------------------------------
@lru_cache(maxsize=2)
def _supabase_client(url: str, key: str):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise LibraryStorageError(
            "Supabase is configured but the 'supabase' Python package is not installed."
        ) from exc
    return create_client(url, key)


def _sb():
    if not supabase_configured():
        raise LibraryStorageError("Supabase credentials are not configured.")
    return _supabase_client(_supabase_url(), _supabase_key())


@lru_cache(maxsize=8)
def _ensure_bucket(url: str, key: str, bucket: str) -> None:
    client = _supabase_client(url, key)
    try:
        client.storage.get_bucket(bucket)
        return
    except Exception:
        pass
    try:
        client.storage.create_bucket(
            bucket,
            options={
                "public": False,
                "allowed_mime_types": ["application/pdf", "text/plain", "application/octet-stream"],
                "file_size_limit": 200 * 1024 * 1024,
            },
        )
    except Exception as exc:
        raise LibraryStorageError(
            f"Could not access/create Supabase Storage bucket '{bucket}': {exc}"
        ) from exc


def _sb_table():
    return _sb().table(_supabase_table_name())


def _save_supabase(**kwargs) -> tuple[LibraryDocument, bool]:
    provider = kwargs["provider"].strip()
    product = kwargs["product"].strip()
    version = kwargs["version"].strip()
    doc_type = kwargs["doc_type"].strip().lower()
    filename = kwargs["filename"]
    content = kwargs["content"]
    if not provider or not product or not version or not doc_type:
        raise ValueError("provider, product, version and doc_type are required")
    if not content:
        raise ValueError("document is empty")

    digest = hashlib.sha256(content).hexdigest()
    try:
        existing = (
            _sb_table().select("*")
            .eq("provider", provider).eq("product", product).eq("version", version)
            .eq("doc_type", doc_type).eq("sha256", digest).execute()
        ).data or []
    except Exception as exc:
        raise LibraryStorageError(
            "Could not query Supabase Provider Library. Run supabase/schema.sql in the Supabase SQL Editor first. "
            f"Technical detail: {exc}"
        ) from exc
    if existing:
        return _row_to_doc(existing[0], "supabase"), False

    doc_id = uuid.uuid4().hex
    suffix = Path(filename).suffix.lower() or ".bin"
    object_path = "/".join(
        [_slug(provider), _slug(product), _slug(version), _slug(doc_type), f"{doc_id}{suffix}"]
    )
    now = datetime.now(timezone.utc).isoformat()
    _ensure_bucket(_supabase_url(), _supabase_key(), _supabase_bucket())
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        _sb().storage.from_(_supabase_bucket()).upload(
            path=object_path,
            file=content,
            file_options={"content-type": mime, "upsert": "false"},
        )
    except Exception as exc:
        raise LibraryStorageError(f"Could not upload '{filename}' to Supabase Storage: {exc}") from exc

    row = {
        "id": doc_id,
        "provider": provider,
        "product": product,
        "version": version,
        "doc_type": doc_type,
        "original_filename": filename,
        "stored_path": object_path,
        "sha256": digest,
        "effective_from": (kwargs.get("effective_from") or "").strip() or None,
        "effective_to": (kwargs.get("effective_to") or "").strip() or None,
        "notes": (kwargs.get("notes") or "").strip() or None,
        "uploaded_at": now,
        "extracted_text": None,
        "extracted_at": None,
        "extraction_error": None,
    }
    try:
        inserted = _sb_table().insert(row).execute().data or [row]
    except Exception as exc:
        try:
            _sb().storage.from_(_supabase_bucket()).remove([object_path])
        except Exception:
            pass
        raise LibraryStorageError(f"Document uploaded but metadata insert failed; upload was rolled back: {exc}") from exc
    return _row_to_doc(inserted[0], "supabase"), True


def _list_supabase() -> list[LibraryDocument]:
    try:
        rows = _sb_table().select("*").execute().data or []
    except Exception as exc:
        raise LibraryStorageError(
            "Could not read the Supabase Provider Library. Run supabase/schema.sql once in the SQL Editor. "
            f"Technical detail: {exc}"
        ) from exc
    docs = [_row_to_doc(r, "supabase") for r in rows]
    return sorted(docs, key=lambda d: (d.provider.lower(), d.product.lower(), d.version), reverse=False)


def _get_supabase(provider: str, product: str, version: str) -> list[LibraryDocument]:
    try:
        rows = (
            _sb_table().select("*")
            .eq("provider", provider).eq("product", product).eq("version", version)
            .execute()
        ).data or []
    except Exception as exc:
        raise LibraryStorageError(f"Could not load provider documents from Supabase: {exc}") from exc
    docs = [_row_to_doc(r, "supabase") for r in rows]
    return sorted(docs, key=lambda d: (d.doc_type, d.uploaded_at), reverse=False)


def _delete_supabase(doc_id: str) -> bool:
    try:
        rows = _sb_table().select("*").eq("id", doc_id).execute().data or []
    except Exception as exc:
        raise LibraryStorageError(f"Could not locate document in Supabase: {exc}") from exc
    if not rows:
        return False
    doc = _row_to_doc(rows[0], "supabase")
    try:
        _sb().storage.from_(_supabase_bucket()).remove([doc.stored_path])
        _sb_table().delete().eq("id", doc_id).execute()
        return True
    except Exception as exc:
        raise LibraryStorageError(f"Could not delete document from Supabase: {exc}") from exc


# ---------------------------------------------------------------------------
# Public storage API used by the Streamlit application
# ---------------------------------------------------------------------------
def save_provider_document(**kwargs) -> tuple[LibraryDocument, bool]:
    return _save_supabase(**kwargs) if library_backend() == "supabase" else _save_local(**kwargs)


def list_documents() -> list[LibraryDocument]:
    return _list_supabase() if library_backend() == "supabase" else _list_local()


def list_catalog() -> list[dict]:
    docs = list_documents()
    groups: dict[tuple[str, str, str], dict] = {}
    for d in docs:
        key = (d.provider, d.product, d.version)
        row = groups.setdefault(
            key,
            {
                "provider": d.provider,
                "product": d.product,
                "version": d.version,
                "document_count": 0,
                "last_updated": d.uploaded_at,
            },
        )
        row["document_count"] += 1
        if (d.uploaded_at or "") > (row["last_updated"] or ""):
            row["last_updated"] = d.uploaded_at
    return sorted(groups.values(), key=lambda r: (r["provider"].lower(), r["product"].lower(), r["version"]), reverse=False)


def get_documents(provider: str, product: str, version: str) -> list[LibraryDocument]:
    return _get_supabase(provider, product, version) if library_backend() == "supabase" else _get_local(provider, product, version)


def delete_document(doc_id: str) -> bool:
    return _delete_supabase(doc_id) if library_backend() == "supabase" else _delete_local(doc_id)


def read_document_bytes(doc: LibraryDocument) -> bytes:
    if doc.backend == "supabase":
        try:
            return _sb().storage.from_(_supabase_bucket()).download(doc.stored_path)
        except Exception as exc:
            raise LibraryStorageError(f"Could not download {doc.original_filename} from Supabase: {exc}") from exc
    return Path(doc.stored_path).read_bytes()


@contextmanager
def materialize_document(doc: LibraryDocument):
    """Yield a real local Path for parsers that require random-access PDF files."""
    if doc.backend == "local":
        yield Path(doc.stored_path)
        return
    suffix = Path(doc.original_filename).suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(read_document_bytes(doc))
        tmp.close()
        yield Path(tmp.name)
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass


def cache_document_text(doc_id: str, text: str | None, error: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    if library_backend() == "supabase":
        try:
            _sb_table().update(
                {
                    "extracted_text": text,
                    "extracted_at": now,
                    "extraction_error": error or None,
                }
            ).eq("id", doc_id).execute()
        except Exception as exc:
            raise LibraryStorageError(f"Could not cache document text in Supabase: {exc}") from exc
        return
    conn = _connect_local()
    try:
        conn.execute(
            "UPDATE provider_documents SET extracted_text=?, extracted_at=?, extraction_error=? WHERE id=?",
            (text, now, error or None, doc_id),
        )
        conn.commit()
    finally:
        conn.close()


def supabase_health_check() -> dict:
    """Verify that Supabase is not only configured, but actually readable/writable enough
    for the Provider Library. This deliberately avoids creating test rows or objects.

    Returns a dict suitable for the Admin diagnostics panel.
    """
    result = {
        "ok": False,
        "table_ok": False,
        "bucket_ok": False,
        "key_kind": _supabase_key_kind(),
        "table": _supabase_table_name(),
        "bucket": _supabase_bucket(),
        "errors": [],
    }
    if not supabase_configured():
        result["errors"].append("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing.")
        return result
    if result["key_kind"] == "publishable":
        result["errors"].append(
            "SUPABASE_SERVICE_ROLE_KEY contains a publishable key. Use a server Secret key (sb_secret_...) "
            "or the legacy service_role key; a publishable/anon key cannot write this private Library."
        )
    try:
        # A tiny read proves that the table exists and the credential can access it.
        _sb_table().select("id").limit(1).execute()
        result["table_ok"] = True
    except Exception as exc:
        result["errors"].append(f"Database table check failed: {exc}")
    try:
        _sb().storage.get_bucket(_supabase_bucket())
        result["bucket_ok"] = True
    except Exception as exc:
        result["errors"].append(
            f"Storage bucket check failed: {exc}. Create a PRIVATE bucket named '{_supabase_bucket()}' "
            "in Supabase Storage, or use a server secret/service-role key that can create/access it."
        )
    result["ok"] = result["table_ok"] and result["bucket_ok"] and result["key_kind"] != "publishable"
    return result


def storage_status() -> dict:
    backend = library_backend()
    if backend == "supabase":
        project = _supabase_url().replace("https://", "").replace("http://", "")
        return {
            "backend": "supabase",
            "backend_label": "Supabase Cloud",
            "location": project,
            "bucket": _supabase_bucket(),
            "table": _supabase_table_name(),
            "persistent_across_redeploys": True,
            "data_dir": str(DATA_DIR),
            "free_gb": None,
        }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(DATA_DIR)
    return {
        "backend": "local",
        "backend_label": "Local / Railway Volume",
        "location": str(DATA_DIR),
        "bucket": None,
        "table": None,
        "persistent_across_redeploys": bool(os.getenv("DATA_DIR", "").startswith("/app/")),
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "documents_dir": str(DOCS_DIR),
        "free_gb": round(usage.free / (1024**3), 2),
    }


def local_library_count() -> int:
    """Count legacy/local documents even when Supabase is the active backend."""
    if not DB_PATH.exists():
        return 0
    try:
        return len(_list_local())
    except Exception:
        return 0


def migrate_local_library_to_supabase() -> dict:
    """One-click migration for documents already stored on a Railway volume."""
    if not supabase_configured():
        raise LibraryStorageError("Configure Supabase before migrating the local library.")
    docs = _list_local() if DB_PATH.exists() else []
    created = duplicates = failed = 0
    errors: list[str] = []
    for doc in docs:
        try:
            path = Path(doc.stored_path)
            if not path.exists():
                failed += 1
                errors.append(f"Missing local file: {doc.original_filename}")
                continue
            remote, was_created = _save_supabase(
                provider=doc.provider,
                product=doc.product,
                version=doc.version,
                doc_type=doc.doc_type,
                filename=doc.original_filename,
                content=path.read_bytes(),
                effective_from=doc.effective_from or "",
                effective_to=doc.effective_to or "",
                notes=doc.notes or "",
            )
            if was_created:
                created += 1
            else:
                duplicates += 1
            if doc.extracted_text:
                try:
                    _sb_table().update(
                        {
                            "extracted_text": doc.extracted_text,
                            "extracted_at": doc.extracted_at,
                            "extraction_error": doc.extraction_error,
                        }
                    ).eq("id", remote.id).execute()
                except Exception:
                    pass
        except Exception as exc:
            failed += 1
            errors.append(f"{doc.original_filename}: {exc}")
    return {
        "total": len(docs),
        "created": created,
        "duplicates": duplicates,
        "failed": failed,
        "errors": errors,
    }
