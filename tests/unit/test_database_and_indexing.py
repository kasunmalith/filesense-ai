import time
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from PIL import Image
from pypdf import PdfWriter

from filesense_ai.core.models import CancellationToken
from filesense_ai.core.paths import normalized_path
from filesense_ai.db.repositories import Repository
from filesense_ai.images.catalog import ImageCatalog
from filesense_ai.indexing.service import IndexingService
from filesense_ai.search.keyword import fts_query, keyword_search


def _pdf(path: Path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as stream:
        writer.write(stream)


def test_schema_version_and_foreign_keys(database):
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert database.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert database.connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_index_keyword_search_incremental_update_and_stale_cleanup(database, tmp_path):
    root = tmp_path / "資料" / "résumé"
    root.mkdir(parents=True)
    txt = root / "旅費 report.txt"
    txt.write_text("hotel receipt lodging", encoding="utf-8")
    docx_path = root / "minutes.docx"
    doc = Document()
    doc.add_paragraph("quarterly planning meeting")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "action"
    table.cell(0, 1).text = "approve travel budget"
    doc.save(docx_path)
    pdf_path = root / "blank.pdf"
    _pdf(pdf_path)
    repo = Repository(database.connection)
    root_id = repo.add_root(root)
    service = IndexingService(database.connection)

    first = service.index_root(root_id)
    assert first["indexed"] == 3
    assert (
        database.connection.execute("SELECT COUNT(*) FROM files WHERE status='ok'").fetchone()[0]
        == 3
    )
    assert (
        database.connection.execute(
            "SELECT COUNT(*) FROM segments WHERE file_id=(SELECT id FROM files WHERE path=?)",
            (str(docx_path),),
        ).fetchone()[0]
        >= 2
    )
    assert keyword_search(database.connection, "hotel receipt")[0].path == txt

    second = service.index_root(root_id)
    assert second["skipped"] == 3
    txt.write_text("travel reimbursement meal allowance", encoding="utf-8")
    changed = service.index_root(root_id)
    assert changed["indexed"] == 1
    assert keyword_search(database.connection, "hotel receipt") == []
    assert keyword_search(database.connection, "meal allowance")[0].path == txt

    pdf_path.unlink()
    deleted = service.index_root(root_id)
    assert deleted["status"] == "complete"
    assert (
        database.connection.execute(
            "SELECT COUNT(*) FROM files WHERE path=?", (str(pdf_path),)
        ).fetchone()[0]
        == 0
    )


def test_failed_or_cancelled_scan_never_purges_existing_records(database, tmp_path, monkeypatch):
    import filesense_ai.indexing.service as indexing

    root = tmp_path / "root"
    root.mkdir()
    (root / "keep.txt").write_text("retained record", encoding="utf-8")
    root_id = Repository(database.connection).add_root(root)
    service = IndexingService(database.connection)
    service.index_root(root_id)
    monkeypatch.setattr(
        indexing,
        "discover",
        lambda *args, **kwargs: type("Scan", (), {"files": [], "complete": False, "errors": 1})(),
    )
    result = service.index_root(root_id)
    assert result["status"] == "partial"
    assert database.connection.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1

    monkeypatch.undo()
    token = CancellationToken()
    token.cancel()
    cancelled = service.index_root(root_id, token)
    assert cancelled["status"] == "cancelled"
    assert database.connection.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1


def test_fts_special_characters_and_file_removal(database, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "quote.txt"
    file_path.write_text('needle " OR * MATCH', encoding="utf-8")
    root_id = Repository(database.connection).add_root(root)
    IndexingService(database.connection).index_root(root_id)
    assert fts_query('" OR * MATCH') == '"OR" AND "MATCH"'
    assert keyword_search(database.connection, '" OR * MATCH')
    Repository(database.connection).remove_root(root_id)
    assert database.connection.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0] == 0
    assert keyword_search(database.connection, '" OR * MATCH') == []


def test_root_path_identity_and_unicode(database, tmp_path):
    first = tmp_path / "same name"
    second = tmp_path / "same name 2"
    first.mkdir()
    second.mkdir()
    repo = Repository(database.connection)
    assert repo.add_root(first) != repo.add_root(second)
    assert normalized_path(first) == normalized_path(first.resolve())


def test_spreadsheet_and_corrupt_document_errors_are_bounded(database, tmp_path):
    root = tmp_path / "formats"
    root.mkdir()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Expenses"
    sheet.append(["type", "amount"])
    sheet.append(["lodging", 125])
    workbook.save(root / "table.xlsx")
    (root / "broken.pdf").write_bytes(b"not a PDF")
    (root / "broken.docx").write_bytes(b"not a ZIP document")
    (root / "broken.png").write_bytes(b"not an image")
    root_id = Repository(database.connection).add_root(root)
    stats = IndexingService(database.connection).index_root(root_id)
    assert stats["indexed"] == 1
    assert stats["errors"] == 3
    assert keyword_search(database.connection, "lodging")[0].filename == "table.xlsx"


def test_thumbnail_cache_repairs_corruption_and_prunes_stale_items(database, tmp_path):
    root = tmp_path / "images"
    root.mkdir()
    image_path = root / "small.png"
    Image.new("RGB", (40, 20), "red").save(image_path)
    root_id = Repository(database.connection).add_root(root)
    IndexingService(database.connection).index_root(root_id)
    catalog = ImageCatalog(database.connection)
    record = catalog.records()[0]
    target = catalog.create_thumbnail(record)
    target.write_bytes(b"corrupt cache")
    repaired = catalog.create_thumbnail(record)
    with Image.open(repaired) as thumbnail:
        thumbnail.verify()
    (target.parent / "orphan.jpg").write_bytes(b"orphan")
    assert catalog.prune_orphans() == 1


def test_image_exif_orientation_is_applied_and_recorded(tmp_path):
    from filesense_ai.indexing.extractors import extract

    source = tmp_path / "oriented.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (80, 120), "navy").save(source, exif=exif)
    item = extract(source)
    assert item.metadata["width"] == 120
    assert item.metadata["height"] == 80
    assert item.metadata["exif_orientation"] == 6


def test_scan_skips_symlinks_and_limits_file_size(database, tmp_path):
    root = tmp_path / "safe-root"
    child = root / "nested"
    child.mkdir(parents=True)
    (child / "small.txt").write_text("searchable small file", encoding="utf-8")
    (child / "large.txt").write_text("x" * 100, encoding="utf-8")
    try:
        (root / "loop").symlink_to(root, target_is_directory=True)
    except OSError:
        pass
    root_id = Repository(database.connection).add_root(root)
    result = IndexingService(database.connection, max_file_size=50).index_root(root_id)
    assert result["indexed"] == 1
    assert keyword_search(database.connection, "searchable")[0].filename == "small.txt"


def test_thousand_file_performance_smoke(database, tmp_path):
    root = tmp_path / "generated-library"
    root.mkdir()
    for number in range(1000):
        (root / f"sample-{number:04}.txt").write_text(
            f"Synthetic document {number} includes a local invoice sample.", encoding="utf-8"
        )
    root_id = Repository(database.connection).add_root(root)
    started = time.perf_counter()
    stats = IndexingService(database.connection).index_root(root_id)
    duration = time.perf_counter() - started
    assert stats["indexed"] == 1000
    assert keyword_search(database.connection, "invoice", limit=20)
    assert duration < 60
