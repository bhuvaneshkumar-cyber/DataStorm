"""Multi-format statement ingestion: PDF, CSV, Excel, DOCX, plain text.

Ported from the IntelliCredit document pipeline and retargeted at gig-worker
bank and platform-payout statements. The parser cascade is the valuable part:
bordered tables, then borderless tables, then block-sorted text, then OCR for
scans -- Indian bank exports arrive in all four shapes.

The heavy parsers (pdfplumber, PyMuPDF, pytesseract, python-docx, openpyxl) are
OPTIONAL. They live in requirements-ingestion.txt, and every import is guarded,
so a deployment that only wants /predict-credit-score installs nothing extra and
this module reports itself unavailable instead of breaking service startup. That
mirrors how the ML pipeline already degrades to rules-only.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """A document could not be parsed into anything usable."""


class UnsupportedFormatError(IngestionError):
    """The file extension has no registered parser."""


class DependencyMissingError(IngestionError):
    """A parser for this format is not installed."""


# --------------------------------------------------------------------------- #
# Optional dependency probing
# --------------------------------------------------------------------------- #


def _try_import(module_name: str) -> Optional[Any]:
    """Imports a module, or returns None if it is not installed."""
    try:
        return __import__(module_name)
    except ImportError:
        logger.debug("Optional parser dependency %r is not installed", module_name)
        return None


_fitz = _try_import("fitz")            # PyMuPDF: block-sorted text + page rasterisation
_pdfplumber = _try_import("pdfplumber")  # table extraction
_pytesseract = _try_import("pytesseract")  # OCR for scanned pages
_PIL = _try_import("PIL")

try:
    from docx import Document as _DocxDocument
except ImportError:
    _DocxDocument = None


def available_formats() -> Dict[str, bool]:
    """Which formats this deployment can actually parse right now."""
    return {
        "pdf": _pdfplumber is not None or _fitz is not None,
        "pdf_ocr": all(m is not None for m in (_fitz, _pytesseract, _PIL)),
        "csv": True,      # pandas is a core dependency
        "excel": True,    # pandas + openpyxl
        "docx": _DocxDocument is not None,
        "txt": True,
    }


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

# Bordered tables: ruled lines are the strongest signal when they exist.
_TABLE_SETTINGS_BORDERED = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 10,
    "min_words_vertical": 3,
    "min_words_horizontal": 1,
}

# Borderless: most bank statement PDFs align columns with whitespace only.
_TABLE_SETTINGS_BORDERLESS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "edge_min_length": 10,
    "min_words_vertical": 3,
    "min_words_horizontal": 1,
}

# Mixed: vertical rules with text-aligned rows.
_TABLE_SETTINGS_MIXED = {
    "vertical_strategy": "lines_strict",
    "horizontal_strategy": "text",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 10,
}

# Below this much text, assume extraction failed and escalate to the next strategy.
_THIN_TEXT_CHARS = 500
_SCANNED_TEXT_CHARS = 200

# OCR tuning: 3x render (~216 DPI), contrast boost, binarize at mid-grey.
_OCR_ZOOM = 3.0
_OCR_CONTRAST = 2.0
_OCR_BINARIZE_THRESHOLD = 140
_OCR_CONFIG = r"--oem 3 --psm 6 -l eng"


def _words_to_lines(words: List[dict]) -> str:
    """Rebuilds reading order from word positions.

    A PDF's internal order interleaves multi-column layouts, which scrambles a
    statement's date/narration/amount columns into nonsense. Bucketing words by
    vertical position and sorting each bucket left-to-right recovers the rows.
    """
    if not words:
        return ""

    lines: Dict[int, List[dict]] = {}
    for word in words:
        bucket = round(word["top"] / 5) * 5  # 5pt bands tolerate baseline jitter
        lines.setdefault(bucket, []).append(word)

    return "\n".join(
        " ".join(w["text"] for w in sorted(lines[top], key=lambda w: w["x0"]))
        for top in sorted(lines)
    )


def _extract_pdfplumber(filepath: str) -> Tuple[List[dict], str]:
    """Tables plus column-aware text, page by page."""
    tables: List[dict] = []
    text_parts: List[str] = []

    with _pdfplumber.open(filepath) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            found = (
                page.extract_tables(_TABLE_SETTINGS_BORDERED)
                or page.extract_tables(_TABLE_SETTINGS_BORDERLESS)
                or page.extract_tables(_TABLE_SETTINGS_MIXED)
                or []
            )
            for table in found:
                if table and len(table) > 1:
                    tables.append(
                        {
                            "page": page_number,
                            "data": [
                                ["" if cell is None else str(cell).strip() for cell in row]
                                for row in table
                            ],
                        }
                    )

            words = page.extract_words(x_tolerance=3, y_tolerance=3, use_text_flow=False)
            page_text = _words_to_lines(words) if words else (page.extract_text(layout=True) or "")
            text_parts.append(f"--- PAGE {page_number} ---\n{page_text}")

    return tables, "\n\n".join(text_parts)


def _extract_pymupdf(filepath: str) -> str:
    """Block-sorted text; preserves spatial order better than a raw text dump."""
    parts: List[str] = []
    with _fitz.open(filepath) as doc:
        for page_number, page in enumerate(doc, start=1):
            blocks = page.get_text("blocks", sort=True)
            body = "\n".join(b[4].strip() for b in blocks if b[4].strip())
            parts.append(f"--- PAGE {page_number} ---\n{body}")
    return "\n\n".join(parts)


def _extract_ocr(filepath: str) -> str:
    """Last resort for scanned statements: rasterise, clean up, OCR."""
    if not all(m is not None for m in (_fitz, _pytesseract, _PIL)):
        raise DependencyMissingError(
            "OCR needs PyMuPDF, pytesseract and Pillow, plus the tesseract binary."
        )

    from PIL import Image, ImageEnhance

    parts: List[str] = []
    with _fitz.open(filepath) as doc:
        for page_number, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(matrix=_fitz.Matrix(_OCR_ZOOM, _OCR_ZOOM))
            image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("L")
            image = ImageEnhance.Contrast(image).enhance(_OCR_CONTRAST)
            image = image.point(lambda px: 0 if px < _OCR_BINARIZE_THRESHOLD else 255, "1")
            parts.append(
                f"--- PAGE {page_number} ---\n"
                f"{_pytesseract.image_to_string(image, config=_OCR_CONFIG)}"
            )
    return "\n\n".join(parts)


def extract_pdf(filepath: str) -> Dict[str, Any]:
    """Runs the parser cascade, escalating only when the previous stage came up thin.

    Never raises for a single failed strategy; each is recorded in `errors` and
    the next one is tried. Raises only when nothing produced usable text.
    """
    result: Dict[str, Any] = {"tables": [], "text": "", "extraction_method": None, "errors": []}

    if _pdfplumber is not None:
        try:
            result["tables"], result["text"] = _extract_pdfplumber(filepath)
            result["extraction_method"] = "pdfplumber"
        except Exception as exc:  # noqa: BLE001 - any parser fault must fall through
            logger.warning("pdfplumber failed on %s: %s", filepath, exc)
            result["errors"].append(f"pdfplumber: {exc}")

    if len(result["text"].strip()) < _THIN_TEXT_CHARS and _fitz is not None:
        try:
            text = _extract_pymupdf(filepath)
            if len(text) > len(result["text"]):
                result["text"], result["extraction_method"] = text, "pymupdf"
        except Exception as exc:  # noqa: BLE001
            logger.warning("PyMuPDF failed on %s: %s", filepath, exc)
            result["errors"].append(f"pymupdf: {exc}")

    if len(result["text"].strip()) < _SCANNED_TEXT_CHARS:
        try:
            result["text"], result["extraction_method"] = _extract_ocr(filepath), "ocr"
        except DependencyMissingError as exc:
            result["errors"].append(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR failed on %s: %s", filepath, exc)
            result["errors"].append(f"ocr: {exc}")

    if not result["text"].strip() and not result["tables"]:
        raise IngestionError(
            "No text or tables could be extracted from the PDF. "
            + ("; ".join(result["errors"]) or "No PDF parser is installed.")
        )
    return result


# --------------------------------------------------------------------------- #
# CSV / Excel
# --------------------------------------------------------------------------- #

# Indian bank portals export in all of these; try them in order of likelihood.
_ENCODING_CHAIN = ("utf-8", "utf-8-sig", "cp1252", "latin-1", "iso-8859-1")

_HEADER_SCAN_ROWS = 15
_SPARSE_SHEET_DENSITY = 0.10
_SHEET_MERGE_OVERLAP = 0.70


def dedupe_columns(columns: Sequence[Any]) -> List[str]:
    """Makes header labels unique and non-empty.

    Statement headers routinely repeat a label ("Amount", "Amount") or leave a
    cell blank. Duplicates are not cosmetic: `df["Credit"]` then returns a
    DataFrame instead of a Series and every downstream per-cell parse breaks with
    an opaque TypeError, so the labels are disambiguated at the one place they
    are established.
    """
    seen: Dict[str, int] = {}
    result: List[str] = []
    for index, column in enumerate(columns):
        name = str(column).strip() or f"column_{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        result.append(name)
    return result


def _promote_header(df: pd.DataFrame) -> pd.DataFrame:
    """Promotes the widest of the first rows to be the header.

    Statement exports lead with bank name, account number and address rows before
    the real column titles. The header row is reliably the one with the most
    populated cells.
    """
    if df.empty:
        return df

    scan = min(_HEADER_SCAN_ROWS, len(df))
    header_row = max(range(scan), key=lambda i: int(df.iloc[i].notna().sum()))

    df = df.copy()
    df.columns = dedupe_columns(df.iloc[header_row].tolist())
    return df.iloc[header_row + 1 :].reset_index(drop=True)


def extract_csv(filepath: str) -> pd.DataFrame:
    """Reads a CSV, walking the encoding chain until one succeeds."""
    last_error: Optional[Exception] = None
    for encoding in _ENCODING_CHAIN:
        try:
            df = pd.read_csv(
                filepath, encoding=encoding, on_bad_lines="skip", header=None, dtype=str
            )
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
            continue
        except OSError as exc:
            raise IngestionError(f"Could not open CSV: {exc}") from exc

        logger.info("Read CSV with encoding=%s, shape=%s", encoding, df.shape)
        return _promote_header(df)

    raise IngestionError(f"No supported encoding could read the CSV. Last error: {last_error}")


def _group_compatible_sheets(sheets: Dict[str, pd.DataFrame]) -> List[List[str]]:
    """Groups sheets whose column sets overlap enough to be the same table.

    Banks commonly split a long statement across one sheet per month.
    """
    names = list(sheets)
    used: set = set()
    groups: List[List[str]] = []

    for index, first in enumerate(names):
        if first in used:
            continue
        cols_first = set(sheets[first].columns.str.lower().str.strip())
        group = [first]

        for other in names[index + 1 :]:
            if other in used:
                continue
            cols_other = set(sheets[other].columns.str.lower().str.strip())
            union = cols_first | cols_other
            if union and len(cols_first & cols_other) / len(union) >= _SHEET_MERGE_OVERLAP:
                group.append(other)
                used.add(other)

        if len(group) > 1:
            groups.append(group)
            used.add(first)

    return groups


def extract_excel(filepath: str) -> pd.DataFrame:
    """Reads every sheet, drops the decorative ones, and merges the real table."""
    try:
        sheets = pd.read_excel(filepath, sheet_name=None, header=None, dtype=str)
    except Exception as exc:  # noqa: BLE001 - openpyxl/xlrd raise many types
        raise IngestionError(f"Could not open the Excel workbook: {exc}") from exc

    usable: Dict[str, pd.DataFrame] = {}
    for name, df in sheets.items():
        if df is None or df.empty or df.shape[0] < 2:
            continue
        density = df.notna().sum().sum() / max(df.shape[0] * df.shape[1], 1)
        if density < _SPARSE_SHEET_DENSITY:
            logger.debug("Skipping sparse sheet %r (density %.1f%%)", name, density * 100)
            continue
        usable[name] = _promote_header(df)

    if not usable:
        raise IngestionError("The workbook contains no sheet with tabular data.")

    for group in _group_compatible_sheets(usable):
        logger.info("Concatenating compatible sheets: %s", group)
        return pd.concat([usable[n] for n in group], ignore_index=True)

    return max(usable.values(), key=lambda d: d.shape[0])


# --------------------------------------------------------------------------- #
# DOCX / plain text
# --------------------------------------------------------------------------- #


def extract_docx(filepath: str) -> str:
    """Paragraphs and pipe-delimited table rows, in document order."""
    if _DocxDocument is None:
        raise DependencyMissingError("Reading .docx requires python-docx.")

    try:
        document = _DocxDocument(filepath)
    except Exception as exc:  # noqa: BLE001 - python-docx raises package-specific errors
        raise IngestionError(f"Could not open the Word document: {exc}") from exc

    parts: List[str] = []
    for block in document.element.body:
        tag = block.tag.split("}")[-1]
        if tag == "p":
            text = "".join(node.text or "" for node in block.iter() if hasattr(node, "text"))
            if text.strip():
                parts.append(text.strip())
        elif tag == "tbl":
            for row in block.iterchildren():
                cells = [
                    "".join(n.text or "" for n in cell.iter() if hasattr(n, "text")).strip()
                    for cell in row.iterchildren()
                ]
                if any(cells):
                    parts.append(" | ".join(cells))
    return "\n".join(parts)


def extract_text(filepath: str) -> str:
    """Plain text, walking the same encoding chain as CSV."""
    for encoding in _ENCODING_CHAIN:
        try:
            return Path(filepath).read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise IngestionError(f"Could not read the file: {exc}") from exc
    raise IngestionError("No supported encoding could read the text file.")


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #


def ingest(filepath: str) -> Dict[str, Any]:
    """Parses any supported statement into `{text, dataframe?, tables?, ...}`.

    Raises UnsupportedFormatError for an unknown extension, DependencyMissingError
    when the parser for a known format is not installed, and IngestionError when
    the file is present but unreadable.
    """
    path = Path(filepath)
    if not path.is_file():
        raise IngestionError(f"No such file: {filepath}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        if _pdfplumber is None and _fitz is None:
            raise DependencyMissingError(
                "Reading PDFs requires pdfplumber or PyMuPDF "
                "(pip install -r ml_service/requirements-ingestion.txt)."
            )
        result = extract_pdf(filepath)
        return {"source_format": "pdf", **result}

    if suffix == ".csv":
        df = extract_csv(filepath)
        return {"source_format": "csv", "dataframe": df, "text": df.to_string(index=False)}

    if suffix in (".xlsx", ".xls", ".xlsm"):
        df = extract_excel(filepath)
        return {"source_format": "excel", "dataframe": df, "text": df.to_string(index=False)}

    if suffix in (".docx", ".doc"):
        return {"source_format": "docx", "text": extract_docx(filepath)}

    if suffix == ".txt":
        return {"source_format": "txt", "text": extract_text(filepath)}

    raise UnsupportedFormatError(f"Unsupported file type: {suffix or '(no extension)'}")
