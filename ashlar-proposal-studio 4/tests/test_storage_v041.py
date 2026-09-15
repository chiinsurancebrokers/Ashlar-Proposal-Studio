from pathlib import Path
import importlib


def _load_local_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARY_BACKEND", "local")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    import core.storage as storage
    return importlib.reload(storage)


def test_local_backend_status_and_text_cache(tmp_path, monkeypatch):
    storage = _load_local_storage(tmp_path, monkeypatch)
    assert storage.library_backend() == "local"

    doc, created = storage.save_provider_document(
        provider="IMG",
        product="GPMI",
        version="2026",
        doc_type="brochure",
        filename="gpmi.txt",
        content=b"Silver plan benefits",
    )
    assert created
    storage.cache_document_text(doc.id, "Silver plan benefits parsed")

    refreshed = storage.get_documents("IMG", "GPMI", "2026")
    assert refreshed[0].extracted_text == "Silver plan benefits parsed"
    assert storage.read_document_bytes(refreshed[0]) == b"Silver plan benefits"
    assert storage.storage_status()["backend"] == "local"


def test_auto_backend_falls_back_local_without_supabase(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARY_BACKEND", "auto")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    import core.storage as storage
    storage = importlib.reload(storage)
    assert storage.library_backend() == "local"


def test_forced_supabase_requires_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARY_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    import core.storage as storage
    storage = importlib.reload(storage)
    try:
        storage.library_backend()
    except storage.LibraryStorageError as exc:
        assert "SUPABASE_URL" in str(exc)
    else:
        raise AssertionError("Expected LibraryStorageError")
