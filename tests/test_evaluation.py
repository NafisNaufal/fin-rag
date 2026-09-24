import json

from finrag.evaluation import evaluate, evaluate_answers
from finrag.models import Answer, Chunk, Source


def test_same_page_from_wrong_document_not_credited(tmp_path):
    class WrongReport:
        def search(self, request):
            return [
                Source(
                    label="S1",
                    score=0.9,
                    chunk=Chunk(
                        id="x", document_id="x", filename="wrong.pdf", page=1, content="Revenue"
                    ),
                )
            ]

    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps(
            [{"question": "Revenue?", "expected_sources": [{"filename": "correct.pdf", "page": 1}]}]
        )
    )
    result = evaluate(WrongReport(), path, 5)
    assert result["hit_rate"] == 0
    assert result["mean_page_recall"] == 0


def test_answer_evaluation_keeps_reference_for_human_review(tmp_path):
    class Report:
        def documents(self):
            return [{"id": "apple", "filename": "apple.pdf", "indexed": True}]

        def ask(self, request):
            assert request.document_id == "apple"
            return Answer(
                answer="Revenue was 100. [S1]",
                mode="ollama",
                sources=[
                    Source(
                        label="S1",
                        score=0.8,
                        chunk=Chunk(
                            id="a",
                            document_id="apple",
                            filename="apple.pdf",
                            page=2,
                            content="Revenue 100",
                        ),
                    )
                ],
            )

    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps(
            [
                {
                    "question": "Revenue?",
                    "expected_answer": "$100 million",
                    "expected_sources": [{"filename": "apple.pdf", "page": 2}],
                }
            ]
        )
    )
    result = evaluate_answers(Report(), path, 3)
    assert result["cited_page_hit_rate"] == 1
    assert result["results"][0]["human_review"] == "pending"
    assert result["results"][0]["expected_answer"] == "$100 million"
