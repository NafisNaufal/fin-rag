from finrag.calculation import calculate_growth
from finrag.models import Block, Document, GrowthRequest


def report(content):
    return Document(
        id="apple",
        filename="apple.pdf",
        pages=1,
        parser="layout",
        blocks=[Block(page=1, kind="table", content=content)],
    )


TABLE = """The following table shows net sales (dollars in millions):
||**2025**|**Change**|**2024**|
|---|---|---|---|
|iPhone|$ 209,586|4 %|$ 201,183|
"""


def request(metric="iPhone", from_year=2024, to_year=2025):
    return GrowthRequest(document_id="apple", metric=metric, from_year=from_year, to_year=to_year)


def test_growth_uses_year_columns_and_cites_row():
    answer = calculate_growth(report(TABLE), request())
    assert answer.mode == "calculated"
    assert "4.18%" in answer.answer
    assert "201,183" in answer.answer and "209,586" in answer.answer
    assert "dollars in millions" in answer.answer
    assert answer.sources[0].chunk.page == 1


def test_growth_abstains_on_missing_or_conflicting_rows():
    assert calculate_growth(report(TABLE), request("Revenue")).mode == "no_evidence"
    conflicting = report(TABLE)
    conflicting.blocks.append(
        Block(
            page=2,
            kind="table",
            content="||2025|Change|2024|\n|---|---|---|---|\n|iPhone|100|4 %|50|",
        )
    )
    assert calculate_growth(conflicting, request()).mode == "no_evidence"


def test_growth_handles_zero_and_negative_base():
    zero = report("||2025|2024|\n|---|---|\n|Profit|10|0|")
    assert calculate_growth(zero, request("Profit")).mode == "no_evidence"
    negative = report("||2025|2024|\n|---|---|\n|Profit|10|(10)|")
    assert "200.00%" in calculate_growth(negative, request("Profit")).answer
