"""Attachment text extraction for the Inspiration chat."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import os
import tempfile


MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024
MAX_EXTRACTED_CHARS = 24000

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx", ".xlsx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


class AttachmentExtractionError(Exception):
    """Raised when an uploaded attachment cannot be converted into text."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ExtractedAttachment:
    filename: str
    file_type: str
    text: str
    char_count: int


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _trim_text(text: str) -> str:
    text = (text or "").replace("\x00", "").strip()
    return text[:MAX_EXTRACTED_CHARS]


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text
    except Exception as exc:
        raise AttachmentExtractionError("PDF 解析组件未安装，暂时无法读取 PDF。", 500) from exc

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            handle.write(data)
            temp_path = handle.name
        return extract_text(temp_path) or ""
    except Exception as exc:
        raise AttachmentExtractionError("PDF 解析失败，请换一个可复制文字的 PDF。", 400) from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _extract_docx_text(data: bytes) -> str:
    try:
        from docx import Document
    except Exception as exc:
        raise AttachmentExtractionError("Word 解析组件未安装，暂时无法读取 Word。", 500) from exc

    try:
        document = Document(BytesIO(data))
    except Exception as exc:
        raise AttachmentExtractionError("Word 文件解析失败，请上传 .docx 文件。", 400) from exc

    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_xlsx_text(data: bytes) -> str:
    try:
        import pandas as pd
    except Exception as exc:
        raise AttachmentExtractionError("表格解析组件未安装，暂时无法读取 Excel。", 500) from exc

    try:
        sheets = pd.read_excel(BytesIO(data), sheet_name=None, nrows=80)
    except Exception as exc:
        raise AttachmentExtractionError("Excel 解析失败，请上传 .xlsx 文件。", 400) from exc

    parts = []
    for sheet_name, frame in sheets.items():
        if frame.empty:
            continue
        parts.append(f"【{sheet_name}】")
        parts.append(frame.fillna("").to_csv(index=False))
    return "\n".join(parts)


def extract_attachment_text(filename: str, content_type: str, data: bytes) -> ExtractedAttachment:
    ext = _extension(filename)
    if ext in IMAGE_EXTENSIONS or (content_type or "").startswith("image/"):
        raise AttachmentExtractionError("图片上传先不做，当前请上传 PDF、Word、文本或表格文件。", 415)
    if ext not in SUPPORTED_EXTENSIONS:
        raise AttachmentExtractionError("暂不支持该文件类型，请上传 PDF、Word、TXT、Markdown、JSON、CSV 或 XLSX。", 415)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise AttachmentExtractionError("文件过大，请控制在 12MB 以内。", 413)
    if not data:
        raise AttachmentExtractionError("文件为空，请重新选择。", 400)

    if ext in TEXT_EXTENSIONS:
        text = _decode_text(data)
    elif ext == ".pdf":
        text = _extract_pdf_text(data)
    elif ext == ".docx":
        text = _extract_docx_text(data)
    elif ext == ".xlsx":
        text = _extract_xlsx_text(data)
    else:
        text = ""

    text = _trim_text(text)
    if not text:
        raise AttachmentExtractionError("没有从文件中提取到可用文字。", 400)
    return ExtractedAttachment(
        filename=Path(filename or "attachment").name,
        file_type=ext.lstrip("."),
        text=text,
        char_count=len(text),
    )
