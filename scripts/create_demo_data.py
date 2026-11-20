from __future__ import annotations

import argparse
import csv
from pathlib import Path

from docx import Document
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas


def create_demo_data(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "travel-notes.txt").write_text(
        "Synthetic example: a hotel receipt records lodging, breakfast, and a local train fare.\n"
        "Use FileSense AI to search for an accommodation expense.\n",
        encoding="utf-8",
    )
    with (destination / "expenses.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["date", "category", "amount", "note"])
        writer.writerow(["2026-01-12", "lodging", "125.00", "synthetic sample entry"])
        writer.writerow(["2026-01-13", "rail", "18.50", "synthetic sample entry"])
    document = Document()
    document.add_heading("Sample project meeting", level=1)
    document.add_paragraph(
        "Synthetic content: the team approved the next milestone and travel budget."
    )
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Action"
    table.cell(0, 1).text = "Review sample schedule"
    document.save(destination / "meeting-notes.docx")
    pdf = canvas.Canvas(str(destination / "sample-receipt.pdf"))
    pdf.drawString(72, 760, "SYNTHETIC SAMPLE RECEIPT")
    pdf.drawString(72, 730, "Lodging: 125.00")
    pdf.drawString(72, 708, "This file contains generated demo data only.")
    pdf.save()
    for filename, shift, color in (
        ("synthetic-sunset.png", 0, "#eb7c37"),
        ("synthetic-sunset-near.png", 3, "#e97938"),
    ):
        image = Image.new("RGB", (480, 300), "#183352")
        draw = ImageDraw.Draw(image)
        draw.ellipse((130 + shift, 54, 290 + shift, 214), fill=color)
        draw.rectangle((0, 210, 480, 300), fill="#315b55")
        draw.polygon([(0, 235), (150, 140), (265, 235)], fill="#58756a")
        image.save(destination / filename)
    (destination / "exact-copy.png").write_bytes(
        (destination / "synthetic-sunset.png").read_bytes()
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create clearly synthetic FileSense AI sample files."
    )
    parser.add_argument("destination", nargs="?", type=Path, default=Path("demo-data"))
    args = parser.parse_args()
    path = create_demo_data(args.destination)
    print(f"Created synthetic demo files in: {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
