import fitz
import pytest
from PIL import Image

from core import extractor
from core.extractor import SegmentKind, extract_file, save_upload
from core.schemas import FileType, SourceType
from generate_demo_data import generate


def test_text_extraction_keeps_line_numbers(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("First line\n\nSecond line\n", encoding="utf-8")
    r = extract_file(f)
    assert r.ok and r.document.file_type == FileType.TEXT
    assert r.document.source_type == SourceType.FREEFORM_NOTE
    assert [s.locator for s in r.segments] == ["line 1", "line 3"]
    assert "Second line" in r.document.text
    assert r.document.metadata["size_bytes"] == str(f.stat().st_size)
    assert len(r.document.sha256) == 64


def test_text_falls_back_to_cp1252(tmp_path):
    f = tmp_path / "latin.txt"
    f.write_bytes("Café ordered".encode("cp1252"))
    r = extract_file(f)
    assert r.ok and "Café" in r.document.text
    assert r.document.metadata["encoding"] == "cp1252"
    assert any("cp1252" in w for w in r.document.warnings)


def test_binary_file_named_txt_is_rejected(tmp_path):
    f = tmp_path / "fake.txt"
    f.write_bytes(b"\x00\x01\x02binary")
    r = extract_file(f)
    assert not r.ok and "binary" in r.error


def test_csv_rows_use_spreadsheet_numbering(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n,\n3,4\n", encoding="utf-8")
    r = extract_file(f)
    assert r.ok and r.document.source_type == SourceType.SYSTEM_EXPORT
    assert [s.locator for s in r.segments] == ["row 2", "row 4"]
    assert r.segments[0].fields == {"a": "1", "b": "2"}
    assert r.document.metadata["csv_rows"] == "2"


def test_empty_csv_reports_error(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("", encoding="utf-8")
    r = extract_file(f)
    assert not r.ok and "empty" in r.error


def test_unsupported_file_type(tmp_path):
    f = tmp_path / "report.docx"
    f.write_bytes(b"PK")
    r = extract_file(f)
    assert not r.ok and "Unsupported" in r.error
    assert r.document.warnings == [r.error]


def test_missing_file(tmp_path):
    r = extract_file(tmp_path / "nope.txt")
    assert not r.ok and "not found" in r.error.lower()
    assert r.segments == []


def test_ocr_unavailable_falls_back_gracefully(tmp_path, monkeypatch):
    img_path = tmp_path / "scan.png"
    Image.new("RGB", (80, 40), "white").save(img_path)
    monkeypatch.setattr(extractor, "ocr_status",
                        lambda refresh=False: (False, "Tesseract binary not found"))
    r = extract_file(img_path)
    assert r.ok and r.document.file_type == FileType.IMAGE
    assert r.document.text == "" and r.segments == []
    assert any("OCR unavailable" in w for w in r.document.warnings)
    assert r.document.extraction_method == "none"
    assert r.document.metadata["image_width_px"] == "80"


def test_pdf_hidden_text_is_separated_from_visible_text(tmp_path):
    pdf = next(p for p in generate(tmp_path)["cases"] if p.suffix == ".pdf")
    r = extract_file(pdf)
    assert r.ok and r.document.source_type == SourceType.OFFICIAL_DOCUMENT
    hidden = [s for s in r.segments if s.kind == SegmentKind.HIDDEN]
    assert len(hidden) == 1
    assert "Ignore all previous instructions" in hidden[0].text
    assert any("near-white" in reason for reason in hidden[0].hidden_reasons)
    assert hidden[0].page == 1
    visible = [s for s in r.segments if s.kind == SegmentKind.TEXT]
    assert any("60 units" in s.text and s.page == 1 for s in visible)
    assert r.document.metadata["page_count"] == "1"


def test_pdf_unusual_but_ordinary_text_is_not_flagged(tmp_path):
    path = tmp_path / "ordinary.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(50, 50, 400, 90), color=None, fill=(0, 0, 0))
    page.insert_text((60, 75), "Banner title", fontsize=14, color=(1, 1, 1))
    page.insert_text((60, 200), "Footnote text", fontsize=5, color=(0, 0, 0))
    page.insert_text((60, 150), "Body text", fontsize=12, color=(0, 0, 0))
    doc.save(str(path))
    doc.close()
    r = extract_file(path)
    assert r.ok
    assert {s.kind for s in r.segments} == {SegmentKind.TEXT}
    assert any("Banner title" in s.text for s in r.segments)


def test_corrupt_pdf_reports_error(tmp_path):
    f = tmp_path / "bad.pdf"
    f.write_bytes(b"not really a pdf")
    r = extract_file(f)
    assert not r.ok and "Could not open PDF" in r.error


def test_save_upload_is_safe_and_does_not_overwrite(tmp_path):
    dest = tmp_path / "uploads"
    first = save_upload("../../evil name?.txt", b"x", dest)
    second = save_upload("../../evil name?.txt", b"y", dest)
    assert first.parent == dest and ".." not in first.name
    assert second != first and second.read_bytes() == b"y"