"""Create a clearly fictional report for smoke testing. No company data is implied."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def create_demo(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Nusantara Demo Holdings", styles["Title"]),
        Paragraph("Annual Report 2025 - SYNTHETIC TEST DATA", styles["Heading2"]),
        Spacer(1, 24),
        Paragraph("Financial performance", styles["Heading1"]),
        Paragraph(
            "Revenue increased to IDR 12,400 billion in 2025 from IDR 10,800 billion "
            "in 2024. Management attributed the increase to higher domestic sales "
            "and the opening of three distribution centers.",
            styles["BodyText"],
        ),
        Spacer(1, 18),
        Paragraph("Figures in IDR billion, except where stated.", styles["BodyText"]),
        Spacer(1, 10),
    ]
    table = Table(
        [
            ["Metric (IDR billion)", "2025", "2024"],
            ["Revenue", "12,400", "10,800"],
            ["Net income", "1,800", "1,300"],
            ["Total debt", "4,200", "4,500"],
        ],
        colWidths=[260, 100, 100],
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.6, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5eee7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story += [
        table,
        PageBreak(),
        Paragraph("Risk and operations", styles["Heading1"]),
        Paragraph(
            "The primary operating risk was imported raw material price volatility. "
            "The company mitigated this risk through fixed-price supplier contracts. "
            "Employee headcount was 2,450 at year-end 2025.",
            styles["BodyText"],
        ),
        Spacer(1, 20),
        Paragraph(
            "This report is fictional and exists only to test FinRAG. "
            "It must not be used as real financial evidence.",
            styles["BodyText"],
        ),
    ]

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 9)
        canvas.drawString(72, 35, f"SYNTHETIC TEST DATA | PDF page {doc.page}")

    SimpleDocTemplate(str(path)).build(story, onFirstPage=footer, onLaterPages=footer)
    return path


if __name__ == "__main__":
    print(create_demo(Path("data/raw/demo_annual_report.pdf")))
