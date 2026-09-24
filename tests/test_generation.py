import json

import httpx
import pytest

from finrag.generation.rag import generate
from finrag.models import Chunk, Source


@pytest.fixture
def sources():
    return [
        Source(
            label="S1",
            score=0.8,
            chunk=Chunk(
                id="a",
                document_id="d",
                filename="a.pdf",
                page=3,
                content="Revenue was IDR 12,400 billion in 2025.",
            ),
        )
    ]


def respond(monkeypatch, completion):
    def post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://localhost/api/chat"),
            json={"message": {"content": json.dumps(completion)}},
        )

    monkeypatch.setattr(httpx, "post", post)


def test_grounded_generation(settings, sources, monkeypatch):
    settings.answer_mode = "ollama"
    respond(
        monkeypatch,
        {
            "insufficient_evidence": False,
            "claims": [
                {
                    "text": "Revenue was IDR 12,400 billion.",
                    "evidence": [{"source_id": "S1", "quote": "Revenue was IDR 12,400 billion"}],
                }
            ],
        },
    )
    answer = generate("Revenue?", sources, settings)
    assert answer.mode == "ollama"
    assert answer.answer.endswith("[S1]")


@pytest.mark.parametrize(
    "evidence",
    [
        {"source_id": "S99", "quote": "Revenue"},
        {"source_id": "S1", "quote": "Revenue was 999 billion"},
    ],
)
def test_invented_sources_or_quotes_are_rejected(settings, sources, monkeypatch, evidence):
    settings.answer_mode = "ollama"
    respond(
        monkeypatch,
        {
            "insufficient_evidence": False,
            "claims": [{"text": "Unsupported answer", "evidence": [evidence]}],
        },
    )
    answer = generate("Revenue?", sources, settings)
    assert answer.mode == "excerpts"
    assert "Unsupported answer" not in answer.answer
    assert answer.warnings


def test_abstention(settings, sources, monkeypatch):
    settings.answer_mode = "ollama"
    respond(monkeypatch, {"insufficient_evidence": True, "claims": []})
    assert generate("CEO's favorite color?", sources, settings).mode == "no_evidence"


def test_supported_claim_survives_an_invalid_claim(settings, sources, monkeypatch):
    settings.answer_mode = "ollama"
    respond(
        monkeypatch,
        {
            "insufficient_evidence": False,
            "claims": [
                {
                    "text": "An unsupported claim.",
                    "evidence": [{"source_id": "S99", "quote": "Invented evidence"}],
                },
                {
                    "text": "Revenue was IDR 12,400 billion.",
                    "evidence": [{"source_id": "S1", "quote": "Revenue was IDR 12,400 billion"}],
                },
            ],
        },
    )
    answer = generate("Revenue?", sources, settings)
    assert answer.mode == "ollama"
    assert answer.answer == "Revenue was IDR 12,400 billion. [S1]"
    assert any("Omitted 1 generated claim" in warning for warning in answer.warnings)


def test_connection_failure_preserves_evidence(settings, sources, monkeypatch):
    settings.answer_mode = "ollama"

    def fail(*args, **kwargs):
        raise httpx.ConnectError("not running")

    monkeypatch.setattr(httpx, "post", fail)
    answer = generate("Revenue?", sources, settings)
    assert answer.mode == "excerpts" and answer.sources == sources


def test_claim_number_must_appear_in_cited_passage(settings, sources, monkeypatch):
    settings.answer_mode = "ollama"
    respond(
        monkeypatch,
        {
            "insufficient_evidence": False,
            "claims": [
                {
                    "text": "Revenue was IDR 99,999 billion.",
                    "evidence": [{"source_id": "S1", "quote": "Revenue was IDR 12,400 billion"}],
                }
            ],
        },
    )
    assert generate("Revenue?", sources, settings).mode == "excerpts"


def test_year_can_come_from_cited_passage_header(settings, sources, monkeypatch):
    settings.answer_mode = "ollama"
    respond(
        monkeypatch,
        {
            "insufficient_evidence": False,
            "claims": [
                {
                    "text": "Revenue was IDR 12,400 billion in 2025.",
                    "evidence": [{"source_id": "S1", "quote": "Revenue was IDR 12,400 billion"}],
                }
            ],
        },
    )
    assert generate("Revenue?", sources, settings).mode == "ollama"
