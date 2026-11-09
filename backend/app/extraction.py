import html
import io
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image

from .config import MAX_FILE_MB, MIN_RESUME_CHARS, OCR_MAX_PAGES, TESSERACT_CMD


class ResumeError(Exception):
    pass


@dataclass
class Extracted:
    text: str
    ocr_used: bool = False


ALLOWED_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    ".jpeg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    ".webp": {"image/webp"},
}
GENERIC_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def safe_filename(name: str | None) -> str:
    base = PurePosixPath((name or "").replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return base[:150] or "resume"


def file_extension(name: str) -> str:
    return PurePosixPath(name.lower()).suffix


def validate_upload(name: str, content_type: str | None, data: bytes) -> str:
    ext = file_extension(name)
    if ext not in ALLOWED_TYPES:
        raise ResumeError(f"Unsupported file type '{ext or 'none'}'. Allowed: PDF, DOCX, TXT, PNG, JPG, JPEG, WEBP.")
    if not data:
        raise ResumeError("The file is empty.")
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise ResumeError(f"File exceeds the {MAX_FILE_MB} MB limit.")
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in GENERIC_TYPES and ctype not in ALLOWED_TYPES[ext]:
        raise ResumeError(f"Content type '{ctype}' does not match a {ext} file.")
    if not _signature_ok(ext, data):
        raise ResumeError(f"The file content is not a valid {ext[1:].upper()} document.")
    return ext


def _signature_ok(ext: str, data: bytes) -> bool:
    if ext == ".pdf":
        return b"%PDF-" in data[:1024]
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                return "word/document.xml" in zf.namelist()
        except zipfile.BadZipFile:
            return False
    if ext == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if ext == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if ext == ".txt":
        return b"\x00" not in data[:4096]
    return False


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


WINDOWS_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _tesseract_command() -> str | None:
    if TESSERACT_CMD:
        return TESSERACT_CMD if Path(TESSERACT_CMD).exists() or shutil.which(TESSERACT_CMD) else None
    found = shutil.which("tesseract")
    if found:
        return found
    return next((p for p in WINDOWS_TESSERACT_PATHS if Path(p).exists()), None)


def configure_tesseract() -> bool:
    try:
        import pytesseract
    except ImportError:
        return False
    command = _tesseract_command()
    if not command:
        return False
    pytesseract.pytesseract.tesseract_cmd = command
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def ocr_available() -> bool:
    return configure_tesseract()


def _ocr_array(gray: np.ndarray) -> str:
    import cv2
    import pytesseract

    h, w = gray.shape[:2]
    if w < 1400:
        scale = 1400 / w
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return pytesseract.image_to_string(binary, config="--oem 3 --psm 3")


def _require_ocr() -> None:
    if not configure_tesseract():
        raise ResumeError(
            "This resume needs OCR but the Tesseract engine is not installed or not reachable. "
            "Install Tesseract and set TESSERACT_CMD if it is not on PATH."
        )


def _ocr_image_bytes(data: bytes) -> str:
    _require_ocr()
    try:
        img = Image.open(io.BytesIO(data)).convert("L")
        gray = np.array(img)
    except Exception as exc:
        raise ResumeError("The image could not be read.") from exc
    return _ocr_array(gray)


def _extract_pdf(data: bytes) -> Extracted:
    import pymupdf as fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ResumeError("The PDF is corrupted or unreadable.") from exc
    try:
        if doc.needs_pass:
            raise ResumeError("The PDF is password-protected.")
        if doc.page_count == 0:
            raise ResumeError("The PDF has no pages.")
        text = normalize_text("\n".join(page.get_text() for page in doc))
        if len(text) >= MIN_RESUME_CHARS:
            return Extracted(text)
        _require_ocr()
        parts = []
        for page in list(doc)[:OCR_MAX_PAGES]:
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), colorspace=fitz.csGRAY)
            gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            parts.append(_ocr_array(gray))
        return Extracted(normalize_text("\n".join(parts)), ocr_used=True)
    except ResumeError:
        raise
    except Exception as exc:
        raise ResumeError("The PDF could not be processed.") from exc
    finally:
        doc.close()


def _extract_docx(data: bytes) -> Extracted:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ResumeError("The DOCX file is corrupted or unreadable.") from exc
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            seen = []
            for cell in row.cells:
                if cell.text not in seen:
                    seen.append(cell.text)
            lines.append(" | ".join(seen))
    return Extracted(normalize_text("\n".join(lines)))


def _extract_txt(data: bytes) -> Extracted:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return Extracted(normalize_text(data.decode(enc)))
        except UnicodeDecodeError:
            continue
    raise ResumeError("The text file could not be decoded.")


def extract_text(data: bytes, ext: str) -> Extracted:
    if ext == ".pdf":
        result = _extract_pdf(data)
    elif ext == ".docx":
        result = _extract_docx(data)
    elif ext == ".txt":
        result = _extract_txt(data)
    elif ext in IMAGE_EXTS:
        result = Extracted(normalize_text(_ocr_image_bytes(data)), ocr_used=True)
    else:
        raise ResumeError("Unsupported file type.")
    if len(result.text) < MIN_RESUME_CHARS:
        hint = " OCR found no readable text." if result.ocr_used else ""
        raise ResumeError(f"Not enough readable text could be extracted.{hint}")
    return result


def docx_to_html(data: bytes, title: str, download_href: str) -> str:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ResumeError("The DOCX file is corrupted or unreadable.") from exc
    blocks = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            text = Paragraph(child, document).text.strip()
            if text:
                blocks.append(f"<p>{html.escape(text)}</p>")
        elif child.tag.endswith("}tbl"):
            rows = []
            for row in Table(child, document).rows:
                cells, seen = [], []
                for cell in row.cells:
                    if cell._tc not in seen:
                        seen.append(cell._tc)
                        cells.append(f"<td>{html.escape(cell.text.strip())}</td>")
                rows.append(f"<tr>{''.join(cells)}</tr>")
            blocks.append(f"<table>{''.join(rows)}</table>")
    safe_title = html.escape(title)
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{safe_title}</title><meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:820px;margin:0 auto;padding:24px;line-height:1.6;color:#1f2937}"
        "header{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #e5e7eb;"
        "padding-bottom:12px;margin-bottom:20px}h1{font-size:1rem;margin:0}a{color:#2563eb;font-size:.9rem}"
        "table{border-collapse:collapse;width:100%;margin:12px 0}td{border:1px solid #e5e7eb;padding:6px 8px;vertical-align:top}"
        "p{margin:0 0 8px}</style></head><body>"
        f"<header><h1>{safe_title}</h1><a href='{html.escape(download_href)}'>Download the original .docx file</a></header>"
        f"{''.join(blocks) or '<p>This document contains no readable text.</p>'}</body></html>"
    )