from pathlib import Path
import importlib


def test_provider_library_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import core.storage as storage
    importlib.reload(storage)

    doc, created = storage.save_provider_document(
        provider="IMG",
        product="GPMI",
        version="2026",
        doc_type="brochure",
        filename="gpmi.pdf",
        content=b"fake pdf content for storage test",
    )
    assert created is True
    assert Path(doc.stored_path).exists()

    docs = storage.get_documents("IMG", "GPMI", "2026")
    assert len(docs) == 1
    assert docs[0].sha256 == doc.sha256

    _, duplicate_created = storage.save_provider_document(
        provider="IMG",
        product="GPMI",
        version="2026",
        doc_type="brochure",
        filename="copy.pdf",
        content=b"fake pdf content for storage test",
    )
    assert duplicate_created is False
