# Apple 2025 Form 10-K: targeted local check

Run on 2026-09-24 against the [public English filing](https://s2.q4cdn.com/470004039/files/doc_financials/2025/ar/_10-K-2025-As-Filed.pdf) (80 physical PDF pages). The source PDF and local index are intentionally excluded from Git. Reproduction commands are in [README.md](README.md).

Configuration: PyMuPDF4LLM layout parser, `BAAI/bge-small-en-v1.5` embeddings, local Qdrant, top K=3, Ollama `qwen2.5:3b`, temperature 0. The 12 hand-checked questions in `apple_2025.json` include direct figures and two qualitative explanations. Most name a report section; this is a targeted smoke check, **not** a blind or representative accuracy estimate.

| Measure | Result |
| --- | ---: |
| Expected physical page present in top three retrieved passages | 12/12 |
| Generated answer with a cited expected page | 10/12 |
| Generated answers matching the hand-checked reference in manual review | 10/12 |
| Evidence-view fallback after generated evidence validation failed | 2/12 |
| Median end-to-end answer time on this machine | 2.66 s |

The two fallbacks were Products gross margin percentage (36.8%, PDF page 27) and total term debt principal ($91,281 million, PDF page 47). The correct page was retrieved in both cases; the small model did not produce an answer that passed the citation/quote checks. The user sees the passages instead of an unsupported answer. A repeated run may vary despite temperature zero.

Manual review compared the generated figures, units, years, and two explanations against the report and the reference answers. The validator itself checks source IDs, exact quotes, and whether numeric tokens occur in the cited passage. Those automated checks alone do not establish that a claim is true. The two failed questions remain failures of the answer workflow even though retrieval succeeded. The 12 questions are too few and too targeted to generalize to other companies or report layouts.
