import json
import re
import statistics
import time
from pathlib import Path

from finrag.models import Question


def evaluate(library, dataset: Path, top_k: int):
    rows = json.loads(dataset.read_text())
    if not rows:
        raise ValueError("Evaluation dataset is empty.")
    results = []
    for row in rows:
        expected = {(s["filename"], s["page"]) for s in row["expected_sources"]}
        if not expected:
            raise ValueError("Every evaluation question needs expected_sources.")
        start = time.perf_counter()
        sources = library.search(Question(question=row["question"], top_k=top_k))
        elapsed = time.perf_counter() - start
        retrieved = {(s.chunk.filename, s.chunk.page) for s in sources}
        results.append(
            {
                "question": row["question"],
                "page_recall": len(expected & retrieved) / len(expected),
                "hit": bool(expected & retrieved),
                "seconds": elapsed,
            }
        )
    return {
        "questions": len(rows),
        "top_k": top_k,
        "mean_page_recall": statistics.mean(r["page_recall"] for r in results),
        "hit_rate": statistics.mean(r["hit"] for r in results),
        "median_seconds": statistics.median(r["seconds"] for r in results),
        "results": results,
        "note": "Retrieval-only evaluation; does not measure answer faithfulness or correctness.",
    }


def evaluate_answers(library, dataset: Path, top_k: int):
    """Run the live answer path and emit records for human correctness review."""
    rows = json.loads(dataset.read_text())
    if not rows:
        raise ValueError("Evaluation dataset is empty.")
    documents = library.documents()
    results = []
    for row in rows:
        filenames = {item["filename"] for item in row["expected_sources"]}
        if len(filenames) != 1:
            raise ValueError("Answer evaluation requires one report per question.")
        filename = filenames.pop()
        matches = [d for d in documents if d["filename"] == filename and d["indexed"]]
        if len(matches) != 1:
            raise ValueError(f"Expected one indexed report named {filename}.")
        start = time.perf_counter()
        answer = library.ask(
            Question(question=row["question"], document_id=matches[0]["id"], top_k=top_k)
        )
        elapsed = time.perf_counter() - start
        expected_pages = {s["page"] for s in row["expected_sources"]}
        source_pages = {s.chunk.page for s in answer.sources}
        cited_labels = set(re.findall(r"\[(S\d+)\]", answer.answer))
        cited_pages = {s.chunk.page for s in answer.sources if s.label in cited_labels}
        results.append(
            {
                "question": row["question"],
                "expected_answer": row.get("expected_answer", ""),
                "answer": answer.answer,
                "mode": answer.mode,
                "retrieved_page_hit": bool(expected_pages & source_pages),
                "cited_page_hit": bool(expected_pages & cited_pages),
                "source_pages": sorted(source_pages),
                "cited_pages": sorted(cited_pages),
                "warnings": answer.warnings,
                "seconds": elapsed,
                "human_review": "pending",
            }
        )
    return {
        "questions": len(results),
        "top_k": top_k,
        "modes": {
            mode: sum(r["mode"] == mode for r in results)
            for mode in sorted({r["mode"] for r in results})
        },
        "retrieved_page_hit_rate": statistics.mean(r["retrieved_page_hit"] for r in results),
        "cited_page_hit_rate": statistics.mean(r["cited_page_hit"] for r in results),
        "median_seconds": statistics.median(r["seconds"] for r in results),
        "results": results,
        "note": (
            "Expected answers are reference text for human review. Page hits and quote "
            "validation do not prove answer correctness."
        ),
    }
