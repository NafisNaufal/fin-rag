The five demo questions are smoke checks against a synthetic two-page fixture. They are not a
real-world benchmark. Add manually verified questions from real annual reports before reporting
quality metrics. Expected sources include filenames AND physical PDF page numbers to avoid
crediting the same page number from a different report. Filenames must be unique in an evaluation
corpus. Multiple relevant chunks on one page count once. Answer correctness and faithfulness need
separate human review; retrieval recall does not measure either.

`apple_2025.json` is the first real-report smoke set. Its 12 answers and physical source pages were
checked against [Apple's 2025 Form 10-K PDF](https://s2.q4cdn.com/470004039/files/doc_financials/2025/ar/_10-K-2025-As-Filed.pdf).
The source PDF is intentionally not committed. To reproduce it with the layout parser, stop the
FinRAG server first, then run:

```sh
curl -L --fail -o data/raw/apple_2025_form_10k.pdf \
  https://s2.q4cdn.com/470004039/files/doc_financials/2025/ar/_10-K-2025-As-Filed.pdf
uv sync --extra layout
FINRAG_PARSER=layout uv run --extra layout finrag ingest \
  data/raw/apple_2025_form_10k.pdf --company "Apple Inc." --year 2025
FINRAG_PARSER=layout uv run --extra layout finrag evaluate data/eval/apple_2025.json --top-k 3
```

`finrag evaluate` checks source pages and latency. To inspect generated answers as well, set
`FINRAG_ANSWER_MODE=ollama` and run `finrag evaluate-answers data/eval/apple_2025.json --top-k 3`.
Its output includes expected text and a `human_review: pending` field for each answer; review
the figures, units, and meaning manually. These questions name their sections and are not a blind
benchmark. PDF page 32, for example, shows the printed report page number 29; the evaluation
uses 32 to match the app's PDF viewer link.
