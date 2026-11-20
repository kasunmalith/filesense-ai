from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path

from filesense_ai.core.errors import OptionalDependencyError
from filesense_ai.core.models import ExtractedSegment

logger = logging.getLogger("filesense_ai.indexing")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_ARCHIVE_EXPANSION = 200 * 1024 * 1024


def _check_office_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        total = 0
        for member in archive.infolist():
            total += member.file_size
            if total > MAX_ARCHIVE_EXPANSION:
                raise ValueError("Office document exceeds the safe expanded-size limit")
            if member.file_size > 10_000_000 and (
                member.compress_size == 0 or member.file_size / member.compress_size > 200
            ):
                raise ValueError("Office document has an unsafe compression ratio")


@dataclass(frozen=True)
class Extraction:
    kind: str
    segments: tuple[ExtractedSegment, ...]
    mime: str
    metadata: dict


def decode_text(data: bytes) -> str:
    try:
        from charset_normalizer import from_bytes

        match = from_bytes(data).best()
        if match and match.encoding:
            return str(match)
    except ImportError:
        pass
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract(path: Path, max_chars: int = 2_000_000) -> Extraction:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        from PIL import Image, ImageOps

        with Image.open(path) as source:
            if source.width * source.height > 50_000_000:
                raise ValueError("Image exceeds the safe pixel limit")
            image = ImageOps.exif_transpose(source)
            exif = source.getexif()
            return Extraction(
                "image",
                (),
                f"image/{'jpeg' if suffix in {'.jpg', '.jpeg'} else suffix[1:]}",
                {
                    "width": image.width,
                    "height": image.height,
                    "exif_orientation": exif.get(274),
                    "date_taken": exif.get(36867),
                },
            )
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install the base PDF dependencies to read PDF files"
            ) from exc
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise ValueError("Encrypted PDF requires a password; it was not indexed")
            except Exception as exc:
                raise ValueError("Encrypted PDF requires a password; it was not indexed") from exc
        segments = []
        total = 0
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "")[: max(0, max_chars - total)]
            total += len(text)
            if text.strip():
                segments.append(ExtractedSegment(f"Page {number}", number, text))
            if total >= max_chars:
                break
        return Extraction(
            "document",
            tuple(segments),
            "application/pdf",
            {"pages": len(reader.pages), "scanned_pdf": not segments},
        )
    if suffix == ".docx":
        _check_office_archive(path)
        from docx import Document

        doc = Document(path)
        values = [
            (f"Paragraph {i}", i, p.text) for i, p in enumerate(doc.paragraphs, 1) if p.text.strip()
        ]
        position = len(doc.paragraphs)
        for table_no, table in enumerate(doc.tables, 1):
            for row_no, row in enumerate(table.rows, 1):
                text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if text:
                    position += 1
                    values.append((f"Table {table_no}, row {row_no}", position, text))
        return _text_result(
            values,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            max_chars,
        )
    if suffix in {".txt", ".md", ".csv", ".log"}:
        raw = path.read_bytes()[: max_chars * 4]
        text = decode_text(raw)[:max_chars]
        if suffix == ".csv":
            rows = []
            for line, row in enumerate(csv.reader(io.StringIO(text)), start=1):
                rows.append((f"Line {line}", line, " | ".join(row)))
        else:
            rows = [(f"Line {i}", i, line) for i, line in enumerate(text.splitlines(), 1)]
        return _text_result(rows, "text/csv" if suffix == ".csv" else "text/plain", max_chars)
    if suffix == ".xlsx":
        _check_office_archive(path)
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install FileSense AI with the spreadsheet extra to index XLSX"
            ) from exc
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            rows = []
            count = 0
            for sheet in workbook.worksheets:
                for row_no, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    text = " | ".join(str(v) for v in row if v is not None)
                    if text:
                        rows.append((f"{sheet.title}, row {row_no}", row_no, text))
                        count += len(text)
                    if count >= max_chars:
                        break
                if count >= max_chars:
                    break
        finally:
            workbook.close()
        return _text_result(
            rows, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", max_chars
        )
    raise ValueError("Unsupported file type")


def _text_result(rows: list[tuple[str, int, str]], mime: str, max_chars: int) -> Extraction:
    result = []
    remaining = max_chars
    for locator, pos, text in rows:
        if remaining <= 0:
            break
        value = text[:remaining]
        remaining -= len(value)
        if value.strip():
            result.append(ExtractedSegment(locator, pos, value))
    return Extraction("document", tuple(result), mime, {})
