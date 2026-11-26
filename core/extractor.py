"""Unified local evidence extraction for CERBERUS-X.

Supports PDF (PyMuPDF), images (Pillow + optional Tesseract OCR), CSV (Pandas)
and plain text. Everything runs locally; nothing is sent anywhere.

Public API:
    extract_file(path, enable_ocr=True) -> ExtractionResult
    extract_many(paths, enable_ocr=True) -> list[ExtractionResult]
    save_upload(filename, data, dest_dir) -> Path
    ocr_status() -> (available, message)

Failures never raise out of ``extract_file``: the result carries ``error`` and
a placeholder ``SourceDocument`` so a pipeline can keep processing other files.

Locators: PDF lines are "page N, line M"; CSV rows use spreadsheet numbering
(header = row 1, first data row = row 2); text lines are "line N".
"""
from __future__ import annotations

import codecs
import hashlib
import io
import json
import logging
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import pandas as pd
from PIL import Image
from pydantic import BaseModel, Field

from core.schemas import FileType, SourceDocument, SourceType, make_id

logger = logging.getLogger(__name__)

EXTENSION_TYPES: dict[str, FileType] = {
    ".pdf": FileType.PDF,
    ".png": FileType.IMAGE, ".jpg": FileType.IMAGE, ".jpeg": FileType.IMAGE,
    ".bmp": FileType.IMAGE, ".tif": FileType.IMAGE, ".tiff": FileType.IMAGE,
    ".gif": FileType.IMAGE, ".webp": FileType.IMAGE,
    ".csv": FileType.CSV,
    ".xlsx": FileType.EXCEL, ".xls": FileType.EXCEL,
    ".json": FileType.JSON,
    ".txt": FileType.TEXT, ".md": FileType.TEXT, ".log": FileType.TEXT,
}

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_CSV_ROWS = 100_000
TINY_FONT_PT = 4.0            # below this a span is "very small"
LOW_OCR_CONFIDENCE = 60.0     # mean Tesseract confidence (0-100) considered low
NEAR_WHITE = 0xF0             # every RGB channel >= this counts as near-white

_WINDOWS_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class SegmentKind(str, Enum):
    TEXT = "text"      # ordinary visible text
    HIDDEN = "hidden"  # not visible to a human reader (white-on-white, off-page, ...)
    TINY = "tiny"      # visible but very small; unusual, not necessarily malicious
    ROW = "row"        # CSV row
    OCR = "ocr"        # text recovered by OCR


class TextSegment(BaseModel):
    """A located piece of extracted text (the unit of evidence and citation)."""
    text: str
    kind: SegmentKind = SegmentKind.TEXT
    locator: str
    page: Optional[int] = None
    row: Optional[int] = None
    line: Optional[int] = None
    fields: Optional[dict[str, str]] = None        # CSV rows only
    hidden_reasons: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Outcome of extracting one file. ``document`` is always present."""
    document: SourceDocument
    segments: list[TextSegment] = Field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class _ExtractionError(Exception):
    """Internal: a clear, user-facing reason a file could not be read."""


@dataclass
class _Parsed:
    text: str
    segments: list[TextSegment]
    metadata: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    method: str = "none"
    source_type: Optional[SourceType] = None


# --------------------------------------------------------------------------- #
# OCR availability (optional)
# --------------------------------------------------------------------------- #
_ocr_cache: Optional[tuple[bool, str]] = None


def _probe_ocr() -> tuple[bool, str]:
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract is not installed (pip install pytesseract)"
    override = os.environ.get("TESSERACT_CMD")
    if override:
        pytesseract.pytesseract.tesseract_cmd = override
    elif shutil.which("tesseract") is None:
        for candidate in _WINDOWS_TESSERACT_PATHS:
            if Path(candidate).exists():
                pytesseract.pytesseract.tesseract_cmd = candidate
                break
    try:
        version = pytesseract.get_tesseract_version()
    except Exception:
        return False, ("Tesseract OCR program not found. Install it (Windows: UB Mannheim "
                       "build) or set the TESSERACT_CMD environment variable")
    return True, f"Tesseract {version}"


def ocr_status(refresh: bool = False) -> tuple[bool, str]:
    """Return ``(available, message)`` for OCR; the probe result is cached."""
    global _ocr_cache
    if _ocr_cache is None or refresh:
        _ocr_cache = _probe_ocr()
    return _ocr_cache


def _run_ocr(img: Image.Image) -> tuple[str, Optional[float]]:
    """Run Tesseract; return ``(text, mean_confidence_0_to_100 or None)``."""
    import pytesseract
    text = pytesseract.image_to_string(img)
    confidence: Optional[float] = None
    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        confs = [float(c) for c, t in zip(data["conf"], data["text"])
                 if str(t).strip() and float(c) >= 0]
        if confs:
            confidence = sum(confs) / len(confs)
    except Exception:  # confidence is best-effort
        logger.debug("OCR confidence unavailable", exc_info=True)
    return text, confidence


def _ocr_segments(text: str, *, page: Optional[int] = None) -> list[TextSegment]:
    prefix = f"page {page}, " if page else ""
    segments = []
    for n, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            segments.append(TextSegment(text=line.strip(), kind=SegmentKind.OCR,
                                        locator=f"{prefix}ocr line {n}", page=page, line=n))
    return segments


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def detect_file_type(path: Path) -> FileType:
    """Classify a file by extension."""
    return EXTENSION_TYPES.get(Path(path).suffix.lower(), FileType.UNKNOWN)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_metadata(path: Path, stat: os.stat_result) -> dict[str, str]:
    meta = {
        "filename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": str(stat.st_size),
        "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }
    created = stat.st_ctime if os.name == "nt" else getattr(stat, "st_birthtime", None)
    if created:
        meta["created_time"] = datetime.fromtimestamp(created).isoformat(timespec="seconds")
    return meta


def _decode_bytes(data: bytes) -> tuple[str, str, list[str]]:
    """Decode text bytes: UTF-8 (with/without BOM), UTF-16 with BOM, cp1252, latin-1."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode("utf-16"), "utf-16", []
        except UnicodeDecodeError as exc:
            raise _ExtractionError(f"Could not decode UTF-16 text: {exc}") from exc
    if b"\x00" in data[:4096]:
        raise _ExtractionError("File appears to be binary, not text.")
    try:
        return data.decode("utf-8-sig"), "utf-8", []
    except UnicodeDecodeError:
        pass
    try:
        return (data.decode("cp1252"), "cp1252",
                ["Not valid UTF-8; decoded as Windows-1252 (cp1252)."])
    except UnicodeDecodeError:
        return (data.decode("latin-1"), "latin-1",
                ["Not valid UTF-8 or cp1252; decoded as latin-1 (some characters may be wrong)."])


# --------------------------------------------------------------------------- #
# Text and CSV
# --------------------------------------------------------------------------- #
def _parse_text(path: Path, enable_ocr: bool) -> _Parsed:
    text, encoding, warnings = _decode_bytes(path.read_bytes())
    segments = [
        TextSegment(text=line.strip(), kind=SegmentKind.TEXT, locator=f"line {n}", line=n)
        for n, line in enumerate(text.splitlines(), start=1) if line.strip()
    ]
    if not segments:
        warnings.append("File contains no text.")
    return _Parsed(text=text, segments=segments, metadata={"encoding": encoding},
                   warnings=warnings, method="text-decode")


def _dataframe_to_segments(
    df: pd.DataFrame,
    *,
    sheet_name: Optional[str] = None,
    warnings: Optional[list[str]] = None,
) -> list[TextSegment]:
    """Convert a DataFrame into ROW TextSegments using spreadsheet row numbering."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    if len(df) > MAX_CSV_ROWS:
        df = df.iloc[:MAX_CSV_ROWS]
        if warnings is not None:
            warnings.append(f"Table truncated to the first {MAX_CSV_ROWS} rows.")
    prefix = f"sheet '{sheet_name}', " if sheet_name else ""
    segments: list[TextSegment] = []
    for idx, record in enumerate(df.to_dict(orient="records")):
        fields = {str(k).strip(): str(v).strip() for k, v in record.items()}
        if not any(fields.values()):
            continue
        row_no = idx + 2  # header is row 1
        row_text = "; ".join(f"{k}={v}" for k, v in fields.items() if v)
        segments.append(TextSegment(
            text=row_text,
            kind=SegmentKind.ROW,
            locator=f"{prefix}row {row_no}",
            row=row_no,
            fields=fields,
        ))
    return segments


def _parse_csv(path: Path, enable_ocr: bool) -> _Parsed:
    text, encoding, warnings = _decode_bytes(path.read_bytes())
    if not text.strip():
        raise _ExtractionError("CSV file is empty.")
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False,
                         nrows=MAX_CSV_ROWS + 1)
    except pd.errors.EmptyDataError as exc:
        raise _ExtractionError("CSV file is empty.") from exc
    except pd.errors.ParserError as exc:
        raise _ExtractionError(f"CSV could not be parsed: {exc}") from exc
    df.columns = [str(c).strip() for c in df.columns]
    segments = _dataframe_to_segments(df, warnings=warnings)
    if not segments:
        warnings.append("CSV has a header but no data rows.")
    meta = {"encoding": encoding, "csv_columns": ", ".join(df.columns),
            "csv_rows": str(len(segments))}
    return _Parsed(text="\n".join(s.text for s in segments), segments=segments,
                   metadata=meta, warnings=warnings, method="pandas")


def _col_ref_to_index(ref: str) -> int:
    """Convert an Excel cell reference such as 'AB12' into a 0-based column index."""
    col = 0
    for ch in ref:
        if ch.isalpha():
            col = col * 26 + (ord(ch.upper()) - ord("A") + 1)
        else:
            break
    return max(0, col - 1)


def _read_xlsx_sheets_stdlib(path: Path) -> dict[str, pd.DataFrame]:
    """Minimal pure-stdlib .xlsx reader when openpyxl is not installed."""
    try:
        zf_ctx = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as exc:
        raise _ExtractionError(f"Could not open Excel file (invalid .xlsx archive): {exc}") from exc

    with zf_ctx as zf:
        names = set(zf.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            sst = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst:
                if si.tag.endswith("}si") or si.tag == "si":
                    parts = [t.text or "" for t in si.iter() if t.tag.endswith("}t") or t.tag == "t"]
                    shared.append("".join(parts))

        # Map workbook sheet names to worksheet XML paths via workbook.xml + rels.
        sheet_entries: list[tuple[str, str]] = []
        if "xl/workbook.xml" in names:
            wb = ET.fromstring(zf.read("xl/workbook.xml"))
            rel_map: dict[str, str] = {}
            if "xl/_rels/workbook.xml.rels" in names:
                rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                for rel in rels:
                    rid = rel.attrib.get("Id")
                    target = rel.attrib.get("Target", "")
                    if rid and target:
                        clean = target.lstrip("/")
                        if not clean.startswith("xl/"):
                            clean = f"xl/{clean}"
                        rel_map[rid] = clean
            for elem in wb.iter():
                if elem.tag.endswith("}sheet") or elem.tag == "sheet":
                    sname = elem.attrib.get("name", "Sheet1")
                    rid = next((v for k, v in elem.attrib.items() if k.endswith("}id") or k == "r:id"), "")
                    target = rel_map.get(rid, "")
                    if target in names:
                        sheet_entries.append((sname, target))

        if not sheet_entries:
            worksheets = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            sheet_entries = [(Path(w).stem, w) for w in worksheets]

        if not sheet_entries:
            raise _ExtractionError("Excel workbook contains no readable worksheets.")

        sheets: dict[str, pd.DataFrame] = {}
        for sname, spath in sheet_entries:
            root = ET.fromstring(zf.read(spath))
            rows_data: list[list[str]] = []
            for row_el in root.iter():
                if not (row_el.tag.endswith("}row") or row_el.tag == "row"):
                    continue
                row_vals: dict[int, str] = {}
                next_col = 0
                for cell in row_el:
                    if not (cell.tag.endswith("}c") or cell.tag == "c"):
                        continue
                    ref = cell.attrib.get("r", "")
                    col_idx = _col_ref_to_index(ref) if ref else next_col
                    next_col = col_idx + 1
                    ctype = cell.attrib.get("t", "")
                    val = ""
                    if ctype == "inlineStr":
                        val = "".join(t.text or "" for t in cell.iter()
                                      if t.tag.endswith("}t") or t.tag == "t")
                    else:
                        v_el = next((ch for ch in cell if ch.tag.endswith("}v") or ch.tag == "v"), None)
                        if v_el is not None and v_el.text is not None:
                            raw_val = v_el.text
                            if ctype == "s":
                                try:
                                    val = shared[int(raw_val)]
                                except (ValueError, IndexError):
                                    val = raw_val
                            elif ctype == "b":
                                val = "TRUE" if raw_val == "1" else "FALSE"
                            else:
                                val = raw_val
                    row_vals[col_idx] = val
                if row_vals:
                    width = max(row_vals) + 1
                    rows_data.append([row_vals.get(i, "") for i in range(width)])

            if not rows_data:
                sheets[sname] = pd.DataFrame()
                continue
            width = max(len(r) for r in rows_data)
            padded = [r + [""] * (width - len(r)) for r in rows_data]
            headers = [h.strip() or f"col_{i + 1}" for i, h in enumerate(padded[0])]
            sheets[sname] = pd.DataFrame(padded[1:], columns=headers, dtype=str)
        return sheets


def _parse_excel(path: Path, enable_ocr: bool) -> _Parsed:
    ext = path.suffix.lower()
    method = "pandas-excel"
    try:
        sheets = pd.read_excel(path, sheet_name=None, dtype=str, keep_default_na=False)
    except ImportError:
        if ext == ".xlsx":
            sheets = _read_xlsx_sheets_stdlib(path)
            method = "xlsx-xml"
        else:
            raise _ExtractionError(
                "Reading legacy .xls files requires xlrd (pip install xlrd) or conversion to .xlsx/.csv."
            )
    except _ExtractionError:
        raise
    except Exception as exc:
        raise _ExtractionError(f"Could not read Excel workbook: {exc}") from exc

    if not sheets:
        raise _ExtractionError("Excel workbook contains no sheets.")

    warnings: list[str] = []
    segments: list[TextSegment] = []
    sheet_names: list[str] = []
    for sheet_name, df in sheets.items():
        sheet_names.append(str(sheet_name))
        if df.empty and len(df.columns) == 0:
            continue
        sheet_label = str(sheet_name) if len(sheets) > 1 else None
        segs = _dataframe_to_segments(df, sheet_name=sheet_label, warnings=warnings)
        segments.extend(segs)

    if not segments:
        warnings.append("Excel workbook has no data rows.")
    meta = {
        "excel_sheets": ", ".join(sheet_names),
        "excel_rows": str(len(segments)),
    }
    return _Parsed(
        text="\n".join(s.text for s in segments),
        segments=segments,
        metadata=meta,
        warnings=warnings,
        method=method,
    )


def _json_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value).strip()
    return json.dumps(value, ensure_ascii=False)


def _extract_json_records(data: Any) -> list[dict[str, str]]:
    """Normalise common structured JSON shapes into a list of flat string dicts."""
    if isinstance(data, list):
        if all(isinstance(item, dict) for item in data):
            return [{str(k).strip(): _json_scalar(v) for k, v in item.items()} for item in data]
        return [{"value": _json_scalar(item)} for item in data if item is not None]
    if isinstance(data, dict):
        # Look for a primary collection key such as {"records": [...]} or {"data": [...]}.
        for preferred in ("records", "rows", "items", "data", "entries", "events", "claims"):
            val = data.get(preferred)
            if isinstance(val, list) and val and all(isinstance(x, dict) for x in val):
                return [{str(k).strip(): _json_scalar(v) for k, v in item.items()} for item in val]
        list_keys = [k for k, v in data.items()
                     if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if len(list_keys) == 1:
            return [{str(k).strip(): _json_scalar(v) for k, v in item.items()}
                    for item in data[list_keys[0]]]
        return [{str(k).strip(): _json_scalar(v) for k, v in data.items()}]
    return [{"value": _json_scalar(data)}]


def _parse_json(path: Path, enable_ocr: bool) -> _Parsed:
    text, encoding, warnings = _decode_bytes(path.read_bytes())
    if not text.strip():
        raise _ExtractionError("JSON file is empty.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _ExtractionError(f"JSON could not be parsed: {exc}") from exc

    records = _extract_json_records(data)
    if len(records) > MAX_CSV_ROWS:
        records = records[:MAX_CSV_ROWS]
        warnings.append(f"JSON records truncated to the first {MAX_CSV_ROWS} items.")

    segments: list[TextSegment] = []
    for idx, fields in enumerate(records, start=1):
        if not any(fields.values()):
            continue
        row_text = "; ".join(f"{k}={v}" for k, v in fields.items() if v)
        segments.append(TextSegment(
            text=row_text,
            kind=SegmentKind.ROW,
            locator=f"record {idx}",
            row=idx,
            fields=fields,
        ))
    if not segments:
        warnings.append("JSON file contains no non-empty records.")

    meta = {
        "encoding": encoding,
        "json_records": str(len(segments)),
    }
    return _Parsed(
        text="\n".join(s.text for s in segments),
        segments=segments,
        metadata=meta,
        warnings=warnings,
        method="json",
    )


# --------------------------------------------------------------------------- #
# Image
# --------------------------------------------------------------------------- #
def _parse_image(path: Path, enable_ocr: bool) -> _Parsed:
    try:
        with Image.open(path) as img:
            img.load()
            meta = {"image_format": img.format or "", "image_mode": img.mode,
                    "image_width_px": str(img.width), "image_height_px": str(img.height)}
            frames = getattr(img, "n_frames", 1)
            rgb = img.convert("RGB")
    except Exception as exc:
        raise _ExtractionError(f"Could not open image: {exc}") from exc

    warnings: list[str] = []
    if frames > 1:
        warnings.append(f"Image has {frames} frames; only the first was processed.")
    text, method = "", "none"
    segments: list[TextSegment] = []
    if not enable_ocr:
        warnings.append("OCR disabled; image ingested without text extraction.")
    else:
        available, message = ocr_status()
        if not available:
            warnings.append(f"OCR unavailable: {message}. Image was ingested without extracted "
                            "text; other files are unaffected.")
        else:
            try:
                text, confidence = _run_ocr(rgb)
                method = "tesseract"
                meta["ocr_engine"] = message
                if confidence is not None:
                    meta["ocr_mean_confidence"] = f"{confidence:.1f}"
                segments = _ocr_segments(text)
                if not segments:
                    warnings.append("OCR ran but found no text in the image.")
            except Exception as exc:
                logger.warning("OCR failed for %s: %s", path.name, exc)
                warnings.append(f"OCR failed: {exc}")
    return _Parsed(text=text, segments=segments, metadata=meta, warnings=warnings,
                   method=method, source_type=SourceType.OCR_IMAGE)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _import_fitz() -> Any:
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # type: ignore[no-redef]
        except ImportError as exc:
            raise _ExtractionError("PyMuPDF is not installed (pip install PyMuPDF).") from exc
    return fitz


def _near_white(color: int) -> bool:
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return min(r, g, b) >= NEAR_WHITE


def _invisible_texts(page: Any) -> list[str]:
    """Text drawn with an invisible render mode (3) or zero opacity, if detectable."""
    try:
        traces = page.get_texttrace()
    except Exception:
        return []
    found: list[str] = []
    for item in traces:
        if item.get("type") == 3 or item.get("opacity", 1.0) == 0:
            try:
                text = "".join(chr(ch[0]) for ch in item.get("chars", ())).strip()
            except Exception:
                continue
            if text:
                found.append(text)
    return found


def _dark_fill_rects(fitz: Any, page: Any) -> list[Any]:
    """Rectangles of dark filled shapes; white text on these is normal design."""
    rects = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return rects
    for drawing in drawings:
        fill = drawing.get("fill")
        if not fill:
            continue
        if len(fill) == 3:
            luminance = 0.299 * fill[0] + 0.587 * fill[1] + 0.114 * fill[2]
        elif len(fill) == 1:
            luminance = fill[0]
        else:
            continue
        if luminance < 0.6:
            rects.append(fitz.Rect(drawing["rect"]))
    return rects


def _classify_span(fitz: Any, span: dict, invisible: list[str], page_rect: Any,
                   dark_rects: list[Any]) -> tuple[SegmentKind, list[str]]:
    """Return (kind, reasons) for one PDF text span.

    Strong reasons (white-on-light, invisible mode, off-page) -> HIDDEN.
    Only a very small font -> TINY. Otherwise TEXT.
    """
    strong: list[str] = []
    weak: list[str] = []
    text = span.get("text", "").strip()
    size = float(span.get("size", 0) or 0)
    color = int(span.get("color", 0) or 0)
    bbox = fitz.Rect(span["bbox"])

    if text and any(text in t for t in invisible):
        strong.append("text drawn in an invisible render mode or with zero opacity")
    if _near_white(color):
        center = fitz.Point((bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2)
        if not any(rect.contains(center) for rect in dark_rects):
            strong.append(f"near-white text (#{color:06X}) on a light page")
    if not bbox.is_empty and not bbox.intersects(page_rect):
        strong.append("positioned outside the visible page area")
    if size < TINY_FONT_PT:
        weak.append(f"very small font ({size:.1f} pt)")

    if strong:
        return SegmentKind.HIDDEN, strong + weak
    if weak:
        return SegmentKind.TINY, weak
    return SegmentKind.TEXT, []


def _pdf_page_segments(fitz: Any, page: Any, page_no: int) -> list[TextSegment]:
    # No TEXT_MEDIABOX_CLIP flag, so text positioned off the page is still returned.
    flags = fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
    page_dict = page.get_text("dict", flags=flags)
    invisible = _invisible_texts(page)
    page_rect = page.rect
    dark_rects: Optional[list[Any]] = None
    segments: list[TextSegment] = []
    line_no = 0
    odd_no = 0

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            groups: list[tuple[SegmentKind, list[str], list[str]]] = []
            for span in line.get("spans", []):
                raw = span.get("text", "")
                if not raw.strip():
                    if groups:
                        groups[-1][2].append(raw)
                    continue
                if dark_rects is None:
                    dark_rects = _dark_fill_rects(fitz, page)
                kind, reasons = _classify_span(fitz, span, invisible, page_rect, dark_rects)
                if groups and groups[-1][0] == kind and groups[-1][1] == reasons:
                    groups[-1][2].append(raw)
                else:
                    groups.append((kind, reasons, [raw]))
            for kind, reasons, texts in groups:
                joined = "".join(texts).strip()
                if not joined:
                    continue
                if kind == SegmentKind.TEXT:
                    line_no += 1
                    segments.append(TextSegment(
                        text=joined, kind=kind, page=page_no, line=line_no,
                        locator=f"page {page_no}, line {line_no}"))
                else:
                    odd_no += 1
                    label = "hidden text" if kind == SegmentKind.HIDDEN else "small text"
                    segments.append(TextSegment(
                        text=joined, kind=kind, page=page_no, hidden_reasons=reasons,
                        locator=f"page {page_no}, {label} #{odd_no}"))
    return segments


def _ocr_pdf(fitz: Any, pdf: Any, n_pages: int, enable_ocr: bool
             ) -> tuple[list[TextSegment], list[str], Optional[float]]:
    """OCR rendered pages of a PDF that has no text layer."""
    if not enable_ocr:
        return [], ["PDF has no text layer and OCR is disabled; no text extracted."], None
    available, message = ocr_status()
    if not available:
        return [], [f"PDF has no text layer and OCR is unavailable: {message}."], None
    segments: list[TextSegment] = []
    confidences: list[float] = []
    warnings: list[str] = []
    for i in range(n_pages):
        try:
            pix = pdf[i].get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            text, conf = _run_ocr(img)
        except Exception as exc:
            warnings.append(f"OCR failed on page {i + 1}: {exc}")
            continue
        segments.extend(_ocr_segments(text, page=i + 1))
        if conf is not None:
            confidences.append(conf)
    mean = sum(confidences) / len(confidences) if confidences else None
    return segments, warnings, mean


def _parse_pdf(path: Path, enable_ocr: bool) -> _Parsed:
    fitz = _import_fitz()
    try:
        pdf = fitz.open(str(path))
    except Exception as exc:
        raise _ExtractionError(f"Could not open PDF (corrupt or not a PDF): {exc}") from exc
    try:
        if pdf.needs_pass:
            raise _ExtractionError("PDF is password-protected; decrypt it locally and re-upload.")
        meta = {"page_count": str(pdf.page_count)}
        for key, value in (pdf.metadata or {}).items():
            if value:
                meta[f"pdf_{key}"] = str(value)
        warnings: list[str] = []
        n_pages = min(pdf.page_count, MAX_PDF_PAGES)
        if pdf.page_count > MAX_PDF_PAGES:
            warnings.append(f"PDF has {pdf.page_count} pages; only the first {MAX_PDF_PAGES} were read.")
        segments: list[TextSegment] = []
        for index in range(n_pages):
            segments.extend(_pdf_page_segments(fitz, pdf[index], index + 1))

        method, source_type = "pymupdf", None
        if not any(s.kind in (SegmentKind.TEXT, SegmentKind.TINY) for s in segments):
            ocr_segs, ocr_warnings, conf = _ocr_pdf(fitz, pdf, n_pages, enable_ocr)
            warnings.extend(ocr_warnings)
            if ocr_segs:
                segments.extend(ocr_segs)
                method, source_type = "pymupdf+tesseract", SourceType.OCR_IMAGE
                if conf is not None:
                    meta["ocr_mean_confidence"] = f"{conf:.1f}"
        return _Parsed(text="\n".join(s.text for s in segments), segments=segments,
                       metadata=meta, warnings=warnings, method=method,
                       source_type=source_type)
    finally:
        pdf.close()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
_HANDLERS = {
    FileType.PDF: (_parse_pdf, SourceType.OFFICIAL_DOCUMENT),
    FileType.IMAGE: (_parse_image, SourceType.OCR_IMAGE),
    FileType.CSV: (_parse_csv, SourceType.SYSTEM_EXPORT),
    FileType.EXCEL: (_parse_excel, SourceType.SYSTEM_EXPORT),
    FileType.JSON: (_parse_json, SourceType.SYSTEM_EXPORT),
    FileType.TEXT: (_parse_text, SourceType.FREEFORM_NOTE),
}


def _failure(path: Path, file_type: FileType, message: str, sha: str = "") -> ExtractionResult:
    document = SourceDocument(
        id=make_id("doc", path.name, sha or "unreadable"),
        filename=path.name, file_type=file_type, source_type=SourceType.UNKNOWN,
        sha256=sha, stored_path=str(path), warnings=[message], extraction_method="none",
    )
    return ExtractionResult(document=document, segments=[], error=message)


def extract_file(path: Union[str, Path], *, enable_ocr: bool = True) -> ExtractionResult:
    """Extract text, segments and metadata from one file.

    Never raises for bad input: check ``result.ok`` / ``result.error``.
    """
    path = Path(path)
    file_type = detect_file_type(path)
    if not path.exists() or not path.is_file():
        return _failure(path, file_type, f"File not found: {path}")
    if file_type == FileType.UNKNOWN:
        supported = ", ".join(sorted(EXTENSION_TYPES))
        return _failure(path, file_type,
                        f"Unsupported file type '{path.suffix or '(no extension)'}'. "
                        f"Supported: {supported}")
    try:
        stat = path.stat()
        if stat.st_size > MAX_FILE_BYTES:
            return _failure(path, file_type,
                            f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")
        sha = _sha256(path)
    except OSError as exc:
        return _failure(path, file_type, f"Could not read file: {exc}")

    handler, default_source = _HANDLERS[file_type]
    try:
        parsed = handler(path, enable_ocr)
    except _ExtractionError as exc:
        return _failure(path, file_type, str(exc), sha)
    except Exception as exc:  # last-resort guard so one bad file cannot stop a batch
        logger.exception("Unexpected extraction failure for %s", path)
        return _failure(path, file_type, f"Unexpected error while reading {path.name}: {exc}", sha)

    document = SourceDocument(
        id=make_id("doc", path.name, sha),
        filename=path.name, file_type=file_type,
        source_type=parsed.source_type or default_source,
        sha256=sha, stored_path=str(path), text=parsed.text,
        metadata={**_file_metadata(path, stat), **parsed.metadata},
        extraction_method=parsed.method, warnings=parsed.warnings,
    )
    return ExtractionResult(document=document, segments=parsed.segments)


def extract_many(paths: Iterable[Union[str, Path]], *, enable_ocr: bool = True
                 ) -> list[ExtractionResult]:
    """Extract several files; a failing file never stops the others."""
    return [extract_file(p, enable_ocr=enable_ocr) for p in paths]


def safe_filename(name: str) -> str:
    """Strip directories and unsafe characters from an uploaded filename."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    if not base:
        base = "upload"
    if Path(base).stem.upper() in _WINDOWS_RESERVED:
        base = f"_{base}"
    return base


def save_upload(filename: str, data: bytes, dest_dir: Union[str, Path]) -> Path:
    """Save uploaded bytes locally under a safe, non-clobbering name; return the path."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / safe_filename(filename)
    stem, suffix, counter = target.stem, target.suffix, 1
    while target.exists():
        target = dest / f"{stem}_{counter}{suffix}"
        counter += 1
    target.write_bytes(data)
    return target