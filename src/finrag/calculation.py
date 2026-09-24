"""A narrow, auditable tool for year-over-year growth in extracted Markdown tables."""

import re
from decimal import Decimal

from finrag.models import Answer, Chunk, Document, GrowthRequest, Source


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [re.sub(r"<[^>]+>", "", cell).strip() for cell in line.split("|")]


def _number(cell: str) -> Decimal | None:
    cleaned = re.sub(r"[,$\s]", "", cell)
    if re.fullmatch(r"\(?-?\d+(?:\.\d+)?\)?", cleaned):
        if cleaned.startswith("("):
            cleaned = "-" + cleaned[1:-1]
        return Decimal(cleaned)
    return None


def _metric(cell: str) -> str:
    cell = re.sub(r"<[^>]+>|\[\^\d+\]|\(\d+\)", "", cell)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", cell.lower()).split())


def calculate_growth(document: Document, request: GrowthRequest) -> Answer:
    if request.from_year == request.to_year:
        raise ValueError("Choose two different years.")
    target = _metric(request.metric)
    if not target:
        raise ValueError("Enter a table row name, such as iPhone or Total net sales.")
    matches = []
    for block in document.blocks:
        if block.kind != "table":
            continue
        lines = [line for line in block.content.splitlines() if line.lstrip().startswith("|")]
        for header_index, header in enumerate(lines):
            headers = _cells(header)
            year_columns = {}
            for index, cell in enumerate(headers):
                normalized = re.sub(r"[*_\s]", "", cell)
                if re.fullmatch(r"(?:19|20)\d{2}", normalized):
                    year_columns[int(normalized)] = index
            if request.from_year not in year_columns or request.to_year not in year_columns:
                continue
            for row in lines[header_index + 1 :]:
                cells = _cells(row)
                if not cells or _metric(cells[0]) != target:
                    continue
                first_index, last_index = (
                    year_columns[request.from_year],
                    year_columns[request.to_year],
                )
                if max(first_index, last_index) >= len(cells):
                    continue
                first, last = _number(cells[first_index]), _number(cells[last_index])
                if first is None or last is None:
                    continue
                matches.append((block, header, row, first, last))
            break
    if not matches:
        return Answer(
            answer="I could not find that exact row and both year columns in a parsed table.",
            mode="no_evidence",
            sources=[],
        )
    values = {(first, last) for _, _, _, first, last in matches}
    if len(values) > 1:
        return Answer(
            answer="Matching tables disagree on the values. Specify a more precise row name "
            "or inspect the report before calculating.",
            mode="no_evidence",
            sources=[],
        )
    block, header, row, first, last = matches[0]
    if first == 0:
        return Answer(
            answer="Growth is undefined because the starting value is zero.",
            mode="no_evidence",
            sources=[],
        )
    percentage = (last - first) / abs(first) * 100
    source = Source(
        label="S1",
        score=0,
        chunk=Chunk(
            id=f"{document.id}:table:{block.page}",
            document_id=document.id,
            filename=document.filename,
            company=document.company,
            year=document.year,
            page=block.page,
            section=block.section,
            kind="table",
            content=block.content,
        ),
    )
    unit_sentence = "Check the table caption for units."
    unit_match = re.search(
        r"(?:dollars|amounts) in (millions|billions|thousands)", block.content, re.I
    )
    if unit_match:
        unit_sentence = f"The table's units are {unit_match.group(0).lower()}."
    return Answer(
        answer=(
            f"{request.metric}: {percentage:,.2f}% change from {request.from_year} to "
            f"{request.to_year}.\n\n"
            f"Formula: ({last:,} − {first:,}) ÷ |{first:,}| × 100 = {percentage:,.2f}%. "
            f"{unit_sentence} [S1]"
        ),
        mode="calculated",
        sources=[source],
        warnings=[
            "Computed from the exact matching table row and year columns shown below. "
            "Check the table caption for units and accounting context."
        ],
    )
