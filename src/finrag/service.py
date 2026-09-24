import json
from pathlib import Path
from threading import RLock

from finrag.calculation import calculate_growth
from finrag.config import Settings
from finrag.generation.rag import generate
from finrag.ingestion.chunker import chunk_document
from finrag.ingestion.parser import export_markdown, parse_pdf
from finrag.models import Document, GrowthRequest, Question
from finrag.retrieval.embeddings import Embeddings
from finrag.retrieval.vector_store import VectorStore


class Library:
    def __init__(self, settings: Settings, embeddings=None):
        self.settings = settings
        settings.prepare()
        self.lock = RLock()
        self.embeddings = embeddings or Embeddings(
            settings.embedding_model, str(settings.data_dir / "models")
        )
        self.fingerprint = (
            f"v2:{settings.embedding_model}:{settings.chunk_words}:{settings.overlap_words}:"
            f"{settings.parser}:{settings.ocr_language}"
        )
        self.store = VectorStore(str(settings.data_dir / "index"), self.fingerprint)
        self.catalog_path = settings.data_dir / "catalog.json"
        self.catalog = (
            json.loads(self.catalog_path.read_text()) if self.catalog_path.exists() else {}
        )

    def close(self):
        self.store.close()

    def _save(self):
        temp = self.catalog_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.catalog, indent=2), encoding="utf-8")
        temp.replace(self.catalog_path)

    def documents(self):
        with self.lock:
            return [
                {
                    **{k: v for k, v in entry["document"].items() if k != "blocks"},
                    "indexed": entry["fingerprint"] == self.fingerprint,
                }
                for entry in self.catalog.values()
            ]

    def document(self, document_id: str) -> Document:
        with self.lock:
            if document_id not in self.catalog:
                raise KeyError(document_id)
            return Document.model_validate(self.catalog[document_id]["document"])

    def ingest(self, path: Path, filename: str, company="", year=None) -> Document:
        with self.lock:
            doc = parse_pdf(
                path,
                filename,
                company=company,
                year=year,
                backend=self.settings.parser,
                ocr_language=self.settings.ocr_language,
                max_pages=self.settings.max_pages,
            )
            existing = self.catalog.get(doc.id)
            if existing and existing["fingerprint"] == self.fingerprint:
                return Document.model_validate(existing["document"])
            chunks = chunk_document(doc, self.settings.chunk_words, self.settings.overlap_words)
            vectors = self.embeddings.documents(
                [f"{c.company}\n{c.section}\n{c.content}" for c in chunks]
            )
            doc.chunk_count = len(chunks)
            try:
                self.store.add(chunks, vectors)
                root = self.settings.data_dir
                (root / "raw" / f"{doc.id}.pdf").write_bytes(path.read_bytes())
                (root / "parsed" / f"{doc.id}.md").write_text(
                    export_markdown(doc), encoding="utf-8"
                )
                (root / "parsed" / f"{doc.id}.json").write_text(doc.model_dump_json(indent=2))
                self.catalog[doc.id] = {
                    "document": doc.model_dump(),
                    "fingerprint": self.fingerprint,
                }
                self._save()
            except Exception:
                self.store.delete(doc.id)
                if existing:
                    self.catalog[doc.id] = existing
                else:
                    self.catalog.pop(doc.id, None)
                raise
            return doc

    def search(self, request: Question):
        if not request.question.strip():
            raise ValueError("Enter a question.")
        with self.lock:
            if request.document_id and request.document_id not in self.catalog:
                raise KeyError(request.document_id)
            ids = [
                key
                for key, entry in self.catalog.items()
                if entry["fingerprint"] == self.fingerprint
                and (not request.document_id or request.document_id == key)
            ]
            if not ids:
                return []
            return self.store.search(self.embeddings.query(request.question), request.top_k, ids)

    def ask(self, request: Question):
        return generate(request.question, self.search(request), self.settings)

    def growth(self, request: GrowthRequest):
        return calculate_growth(self.document(request.document_id), request)
