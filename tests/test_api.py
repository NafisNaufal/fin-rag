from conftest import FakeEmbeddings

from finrag.models import Question
from finrag.service import Library


def upload(client, pdf, filename="demo.pdf"):
    return client.post(
        "/api/documents", files={"file": (filename, pdf.read_bytes(), "application/pdf")}
    )


def test_upload_search_and_citation_links(client, pdf):
    response = upload(client, pdf)
    assert response.status_code == 201
    doc = response.json()
    assert doc["chunk_count"] >= 3
    assert len(client.get("/api/documents").json()) == 1
    result = client.post("/api/ask", json={"question": "revenue", "document_id": doc["id"]})
    assert result.status_code == 200
    assert result.json()["mode"] == "excerpts"
    assert result.json()["sources"]
    for source in result.json()["sources"]:
        assert source["chunk"]["document_id"] == doc["id"]
        assert source["chunk"]["page"] in (1, 2)
    assert client.get(f"/api/documents/{doc['id']}/pdf").content.startswith(b"%PDF")
    assert "PDF page 2" in client.get(f"/api/documents/{doc['id']}/markdown").text


def test_deduplication_and_document_filter(client, pdf):
    first = upload(client, pdf).json()
    assert upload(client, pdf).json()["id"] == first["id"]
    second = upload(client, pdf, "second.pdf").json()
    assert len(client.get("/api/documents").json()) == 2
    sources = client.post(
        "/api/search", json={"question": "net income", "document_id": second["id"]}
    ).json()
    assert sources and all(s["chunk"]["document_id"] == second["id"] for s in sources)


def test_empty_library_and_bad_questions(client):
    assert client.post("/api/ask", json={"question": "Revenue?"}).json()["mode"] == "no_evidence"
    assert client.post("/api/ask", json={"question": " "}).status_code == 400
    assert client.post("/api/ask", json={"question": "Revenue?", "top_k": 99}).status_code == 422
    assert client.get("/api/documents/unknown/pdf").status_code == 404
    assert (
        client.post(
            "/api/search", json={"question": "Revenue?", "document_id": "unknown"}
        ).status_code
        == 404
    )


def test_bad_upload_and_path_sanitization(client, pdf):
    assert (
        client.post("/api/documents", files={"file": ("fake.pdf", b"not pdf")}).status_code == 400
    )
    assert upload(client, pdf, "a.exe").status_code == 400
    good = upload(client, pdf, "../../demo.pdf")
    assert good.status_code == 201 and good.json()["filename"] == "demo.pdf"


def test_limits_and_temp_cleanup(client, settings):
    settings.max_upload_mb = 1
    response = client.post("/api/documents", files={"file": ("big.pdf", b"x" * (1024 * 1024 + 1))})
    assert response.status_code == 413
    assert list((settings.data_dir / "tmp").iterdir()) == []


def test_persistence_after_reopen(settings, pdf):
    library = Library(settings, FakeEmbeddings())
    doc = library.ingest(pdf, "demo.pdf")
    library.close()
    reopened = Library(settings, FakeEmbeddings())
    try:
        assert reopened.documents()[0]["id"] == doc.id
        assert reopened.search(Question(question="revenue"))
    finally:
        reopened.close()


def test_failed_embedding_does_not_publish_document(library, pdf, monkeypatch):
    import pytest

    def fail(texts):
        raise RuntimeError("download failed")

    monkeypatch.setattr(library.embeddings, "documents", fail)
    with pytest.raises(RuntimeError):
        library.ingest(pdf, "demo.pdf")
    assert library.documents() == []


def test_model_change_requires_reindex(settings, pdf):
    library = Library(settings, FakeEmbeddings())
    library.ingest(pdf, "demo.pdf")
    library.close()
    settings.embedding_model = "different-test-model"
    library = Library(settings, FakeEmbeddings())
    try:
        assert not library.documents()[0]["indexed"]
        assert library.search(Question(question="revenue")) == []
        library.ingest(pdf, "demo.pdf")
        assert library.documents()[0]["indexed"]
        assert library.search(Question(question="revenue"))
    finally:
        library.close()


def test_parser_change_requires_reindex(settings, pdf):
    library = Library(settings, FakeEmbeddings())
    library.ingest(pdf, "demo.pdf")
    library.close()
    settings.parser = "layout"
    library = Library(settings, FakeEmbeddings())
    try:
        assert not library.documents()[0]["indexed"]
        assert library.search(Question(question="revenue")) == []
    finally:
        library.close()


def test_partial_vector_failure_does_not_publish(library, pdf, monkeypatch):
    import pytest

    original = library.store.add

    def partial(chunks, vectors):
        original(chunks[:1], vectors[:1])
        raise RuntimeError("interrupted indexing")

    monkeypatch.setattr(library.store, "add", partial)
    with pytest.raises(RuntimeError):
        library.ingest(pdf, "demo.pdf")
    assert library.documents() == []
    assert library.store.client.count(library.store.collection).count == 0


def test_growth_api_needs_known_report(client, pdf):
    doc = upload(client, pdf).json()
    response = client.post(
        "/api/calculate/growth",
        json={"document_id": doc["id"], "metric": "not a row", "from_year": 2024, "to_year": 2025},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "no_evidence"
    missing = client.post(
        "/api/calculate/growth",
        json={"document_id": "missing", "metric": "Revenue", "from_year": 2024, "to_year": 2025},
    )
    assert missing.status_code == 404
