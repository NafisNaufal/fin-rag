"""Keep tables intact, and never mix physical pages or sections within a chunk."""

from uuid import NAMESPACE_URL, uuid5

from finrag.models import Chunk, Document


def chunk_document(doc: Document, max_words=220, overlap=30) -> list[Chunk]:
    if max_words <= 0 or not 0 <= overlap < max_words:
        raise ValueError("Require max_words > overlap >= 0.")
    chunks: list[Chunk] = []
    words: list[str] = []
    group = None

    def emit(content, page, section, kind="text"):
        chunks.append(
            Chunk(
                id=str(uuid5(NAMESPACE_URL, f"{doc.id}:{len(chunks)}:{content}")),
                document_id=doc.id,
                filename=doc.filename,
                company=doc.company,
                year=doc.year,
                page=page,
                section=section,
                kind=kind,
                content=content,
            )
        )

    def flush():
        if words and group:
            emit(" ".join(words), *group)
        words.clear()

    for block in doc.blocks:
        key = (block.page, block.section)
        if key != group or block.kind == "table":
            flush()
        group = key
        if block.kind == "table":
            emit(block.content, *key, kind="table")
            continue
        words.extend(block.content.split())
        while len(words) > max_words:
            emit(" ".join(words[:max_words]), *key)
            words = words[max_words - overlap :]
    flush()
    return chunks
