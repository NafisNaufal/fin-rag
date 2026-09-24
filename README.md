# FinRAG

A local workspace for asking questions about financial reports and inspecting the evidence.
Upload a PDF, extract text and tables, search semantically, and open cited PDF pages. Optional
Ollama generation produces answers whose source IDs and supporting quotes are validated. A
deterministic calculation tool computes year-over-year changes from extracted table cells.

## Start

```sh
uv sync --python 3.12
cp .env.example .env
uv run finrag serve
```

Open http://127.0.0.1:8000. The default **evidence view** needs no LLM or API key.
The first upload downloads the configured FastEmbed model (internet required); subsequent
embedding inference and Qdrant storage run locally. Reports are not sent to a hosted AI API.

For generated answers, run Ollama with a model you have installed and set these in `.env`:

```dotenv
FINRAG_ANSWER_MODE=ollama
FINRAG_OLLAMA_MODEL=qwen2.5:3b
FINRAG_OLLAMA_URL=http://localhost:11434
```

If needed: `ollama pull qwen2.5:3b`, then start Ollama. Restart FinRAG after changing settings.
If generation fails or returns an invalid citation/quote, the app displays retrieved evidence
and an explicit warning. The workspace created for this machine already has the installed
`qwen2.5:3b` model selected in its untracked `.env`.

## Try the synthetic report

```sh
uv run python scripts/create_demo.py
uv run finrag ingest data/raw/demo_annual_report.pdf --company "Nusantara Demo Holdings" --year 2025
uv run finrag search "What was revenue in 2025?"
uv run finrag ask "What factors contributed to revenue growth?"
uv run finrag evaluate data/eval/demo.json --top-k 3
uv run finrag serve
```

The demo is explicitly fictional. Its five questions are a smoke test, **not a financial-report
quality benchmark**. Stop the web server before CLI ingestion/search/evaluation: embedded
Qdrant permits one process per data directory. The server itself serializes indexing operations.

## How it works

1. **Validate** PDF format, encryption, upload size (50 MB), and page count (500).
2. **Extract** native PDF text with PyMuPDF, detect tables as Markdown, and attempt Tesseract OCR
   on image-containing pages. Preserve physical PDF page numbers and detected section headings.
3. **Chunk** by page and section, keeping each table intact. Text uses a 220-word target with
   30-word overlap. Tables may exceed the target. Metadata retains company, year, and filename.
4. **Embed** with FastEmbed (`BAAI/bge-small-en-v1.5`) and store vectors/payloads in local Qdrant.
   Model and chunking configuration determine the collection, preventing incompatible reuse.
5. **Retrieve** the top passages across the indexed library or within a selected report.
6. **Generate**, optionally, using Ollama structured JSON. Validate cited source IDs and exact
   quoted evidence before rendering claims. Each source card links to its physical PDF page.
7. **Calculate** year-over-year change with a bounded arithmetic tool. It matches an exact table
   row and the requested year headers, computes with decimal arithmetic, and cites that table.
   Conflicting or missing values cause abstention.

Extracted Markdown and JSON live in `data/parsed/`; PDFs in `data/raw/`; the catalog and vector
index are also under `data/`. Data and secrets are ignored by Git. Re-uploading identical content
with identical metadata is idempotent. Changing embedding, parser, OCR, or chunking settings marks existing reports
as requiring reindexing; re-upload them to build the new collection.

### OCR and complex layouts

On macOS, install OCR languages with `brew install tesseract tesseract-lang` and set
`FINRAG_OCR_LANGUAGE=eng+ind` for English/Indonesian OCR with the default PyMuPDF parser. Missing
OCR support produces visible page warnings with that parser. OCR text extraction does not
reconstruct scanned table cells in the lightweight parser. Basic heading/reading-order heuristics
need manual review on multi-column reports, unusual fonts, and tables spanning multiple pages.

For borderless financial tables, use the optional PyMuPDF4LLM layout parser:

```sh
uv sync --extra layout
# Set FINRAG_PARSER=layout in .env, then restart and re-upload.
```

It keeps detected tables intact and attaches nearby captions, including units, to table blocks.
This parser was checked against Apple's 2025 Form 10-K: the default parser missed the product-sales
and income-statement tables on physical PDF pages 26 and 32, while the layout parser preserved
their rows and year columns. Table detection still needs visual review on each new document type.

An optional Docling adapter is included for richer layout/table extraction:

```sh
uv sync --extra docling
# Set FINRAG_PARSER=docling in .env, then restart and re-upload.
```

Docling downloads its own models. Its default converter manages OCR settings; the
`FINRAG_OCR_LANGUAGE` override currently applies only to the default PyMuPDF parser. The Docling
adapter is optional and requires a separate real-document validation pass before relying on its
output.

The default embedding model targets English and has a limited input window. Long intact tables
may be truncated by the embedding model, even though full tables are preserved for display and
answer generation. For Indonesian and bilingual reports, configure a supported multilingual
FastEmbed model and measure retrieval before claiming bilingual quality.

## API and CLI

Interactive API documentation: http://127.0.0.1:8000/docs

- `POST /api/documents`: multipart `file`, optional `company`, `year`
- `GET /api/documents`: library and indexing status
- `GET /api/documents/{id}`: structured blocks and warnings
- `GET /api/documents/{id}/pdf` and `/markdown`: original/exported sources
- `POST /api/search` and `/api/ask`: `{"question":"...","document_id":null,"top_k":5}`
- `POST /api/calculate/growth`: `{"document_id":"...","metric":"iPhone","from_year":2024,"to_year":2025}`
- `GET /api/status`: configured parser, embedding model, and answer mode

CLI: `finrag ingest`, `finrag search`, `finrag ask`, `finrag growth`, `finrag evaluate`,
`finrag evaluate-answers`, `finrag serve`.
Use `--help` for options. Configuration is read from `.env` and `FINRAG_` environment variables.
For Apple, select the indexed report in the web app, enter the table row `iPhone`, and calculate
from 2024 to 2025. The equivalent CLI call is `finrag growth <document-id> iPhone 2024 2025`;
the document ID is printed by `finrag ingest`.

## Validation

```sh
uv run pytest
uv run ruff check .
```

Tests cover native extraction, tables and numbers, page boundaries, overlap, encrypted/malformed
files, upload limits, deduplication, filtering, persistence, model changes, failed indexing,
source validation, model failure, and abstention. Unit/integration tests use deterministic test
embeddings and mocked generation; real model smoke tests are run separately.

Retrieval evaluation computes document/page recall@K, hit rate, and latency. The separate
`evaluate-answers` command runs the configured generation mode and records every answer, expected
answer, retrieved/cited page hit, fallback mode, warning, and latency for **human review**. Neither
page overlap nor a matching quote proves that a numerical interpretation is correct. Change
`FINRAG_OLLAMA_MODEL` or `FINRAG_ANSWER_MODE` and rerun the same file to compare configurations;
retain the outputs as experiment artifacts.

### First real-report check (2026-09-24)

The 80-page [Apple 2025 Form 10-K](https://s2.q4cdn.com/470004039/files/doc_financials/2025/ar/_10-K-2025-As-Filed.pdf)
was checked on physical PDF pages 26, 27, 32, and 47. The hand-checked
[`data/eval/apple_2025.json`](data/eval/apple_2025.json) contains 12 lookup and explanation
questions with expected pages and answers. Both parsers retrieved the expected page within the top
three for all 12 questions. This small, section-specific set is a reproducible smoke check, not a
general accuracy estimate. The layout parser additionally preserved the two inspected borderless
tables that the default parser missed. See [`data/eval/README.md`](data/eval/README.md) for the
download and reproduction commands.

With the layout parser and local `qwen2.5:3b`, the answer audit found the expected page for all
12 questions at K=3. Ten generated answers cited the expected page and matched the hand-checked
reference on manual review; two fell back to evidence passages after validation failed. Median
answer time was 2.66 seconds on this machine. See the [review and limits](data/eval/apple_2025_review.md).

The exact-row calculator yields 4.18% iPhone net-sales growth from 2024 to 2025, using 201,183
and 209,586 (dollars in millions) from physical PDF page 26. This is independent of Ollama. The
app keeps individually supported claims when another claim has an invalid citation, and warns
about omitted claims. Generated numerical answers still require human checking for units and
interpretation.

### Local verification (2026-09-24)

- 31 automated tests passed; lint and formatting checks passed.
- Real FastEmbed retrieval found the expected PDF page for all 5 synthetic questions at K=3.
  This tiny fixture checks integration only and is not evidence of real-report accuracy.
- The installed Ollama `qwen2.5:3b` model returned the synthetic revenue figures with valid
  source references and matching evidence quotes.
- Native table extraction preserved the fixture's figures and year columns. Real Tesseract OCR
  recovered `12,400` and `10,800` from a rasterized version of the report page.
- Demo PDF pages were rendered and visually inspected. Browser UI inspection was blocked by
  an unavailable browser security-policy check; no browser visual verification is claimed.
- Optional Docling integration has not been exercised with downloaded Docling models.

## Scope and limits

This is a single-user local MVP, bound to loopback. It has no authentication, public deployment,
background job queue, or open-ended calculator agent. The growth tool supports only exact table-row
year-over-year changes; it does not infer arbitrary financial ratios. Uploads process
synchronously; large reports can take time. Do not expose the service publicly without adding
access control, request limits at the ingress, and isolated PDF processing. Model timeouts fall
back to evidence view. Retrieval scores are similarities, not calibrated confidence.

## Code map

- `src/finrag/ingestion/`: native/optional layout/Docling parsing, Markdown export, page-aware chunking
- `src/finrag/retrieval/`: FastEmbed and persistent Qdrant
- `src/finrag/generation/`: grounded prompting and quote/source validation
- `src/finrag/calculation.py`: deterministic table-row arithmetic and abstention
- `src/finrag/service.py`: ingestion/catalog and retrieval orchestration
- `src/finrag/api.py`, `static/`: FastAPI and dependency-free web interface
- `src/finrag/evaluation.py`: retrieval metrics and answer-review records
- `scripts/create_demo.py`, `tests/`: synthetic fixture and regression tests

API references: [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/page.html),
[Qdrant client](https://github.com/qdrant/qdrant-client),
[Ollama chat](https://docs.ollama.com/api/chat).
