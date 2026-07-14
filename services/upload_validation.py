"""Central validation for uploaded documents and Office containers."""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from defusedxml import ElementTree as ET


@dataclass(frozen=True)
class UploadPolicy:
    extensions: frozenset[str]
    max_bytes: int
    max_archive_entries: int = 2_000
    max_uncompressed_bytes: int = 64 * 1024 * 1024
    max_rows: int = 20_000
    max_columns: int = 200
    max_cell_characters: int = 100_000
    max_pdf_pages: int = 300
    max_pdf_objects: int = 100_000
    max_image_pixels: int = 40_000_000
    require_ooxml_manifest: bool = True


class UploadValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


ATTACHMENT_POLICY = UploadPolicy(
    extensions=frozenset({
        ".txt", ".md", ".json", ".csv", ".pdf", ".docx", ".xlsx",
        ".jpg", ".jpeg", ".png", ".webp",
    }),
    max_bytes=12 * 1024 * 1024,
    max_uncompressed_bytes=64 * 1024 * 1024,
    max_rows=5_000,
)
QIANCHUAN_WORKBOOK_POLICY = UploadPolicy(
    extensions=frozenset({".xlsx"}),
    max_bytes=10 * 1024 * 1024,
    max_uncompressed_bytes=50 * 1024 * 1024,
    max_rows=20_000,
    # The Qianchuan parser intentionally supports worksheet-only ZIP exports.
    require_ooxml_manifest=False,
)
LARGE_WORKBOOK_POLICY = UploadPolicy(
    extensions=frozenset({".xlsx"}),
    max_bytes=100 * 1024 * 1024,
    max_archive_entries=10_000,
    max_uncompressed_bytes=512 * 1024 * 1024,
    max_rows=100_000,
    max_columns=500,
    max_cell_characters=200_000,
)


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Za-z]+", reference or "")
    if not letters:
        return 0
    value = 0
    for char in letters.group(0).upper():
        value = value * 26 + ord(char) - 64
    return value


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _validate_xml_limits(archive: zipfile.ZipFile, name: str, policy: UploadPolicy) -> None:
    row_count = 0
    try:
        with archive.open(name) as source:
            for event, element in ET.iterparse(source, events=("start", "end")):
                tag = _local_name(element.tag)
                if event == "start" and tag == "row":
                    row_count += 1
                    declared_row = int(element.attrib.get("r", "0") or 0)
                    if max(row_count, declared_row) > policy.max_rows:
                        raise UploadValidationError("Excel 数据行数超过限制")
                elif event == "start" and tag == "c":
                    column = _column_index(element.attrib.get("r", ""))
                    if column > policy.max_columns:
                        raise UploadValidationError("Excel 列数超过限制")
                elif event == "end" and tag in {"t", "v"}:
                    if len(element.text or "") > policy.max_cell_characters:
                        raise UploadValidationError("Excel 单元格内容过长")
                if event == "end":
                    element.clear()
    except UploadValidationError:
        raise
    except (ET.ParseError, OSError, ValueError) as exc:
        raise UploadValidationError("Office 文件包含无效 XML") from exc


def _validate_office_container(data: bytes, ext: str, policy: UploadPolicy) -> None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > policy.max_archive_entries:
                raise UploadValidationError("Office 压缩包文件项过多")
            expanded = 0
            names = set()
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise UploadValidationError("Office 压缩包包含不安全路径")
                if info.flag_bits & 0x1:
                    raise UploadValidationError("不支持加密的 Office 文件")
                expanded += max(0, info.file_size)
                if expanded > policy.max_uncompressed_bytes:
                    raise UploadValidationError("Office 文件解压后体积过大")
                names.add(info.filename)

            if policy.require_ooxml_manifest and "[Content_Types].xml" not in names:
                raise UploadValidationError("Office 文件实际格式与扩展名不一致")
            required_prefix = "xl/" if ext == ".xlsx" else "word/"
            if not any(name.startswith(required_prefix) for name in names):
                raise UploadValidationError("Office 文件实际格式与扩展名不一致")

            if ext == ".xlsx":
                xml_names = [
                    name for name in names
                    if name.startswith("xl/worksheets/") and name.endswith(".xml")
                ]
                if "xl/sharedStrings.xml" in names:
                    xml_names.append("xl/sharedStrings.xml")
                for name in xml_names:
                    _validate_xml_limits(archive, name, policy)
            else:
                for name in names:
                    if name.startswith("word/") and name.endswith(".xml"):
                        _validate_xml_limits(archive, name, policy)
    except UploadValidationError:
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        raise UploadValidationError("Office 文件不是有效的 ZIP 容器") from exc


def _validate_pdf_complexity(data: bytes, policy: UploadPolicy) -> None:
    page_markers = len(re.findall(rb"/Type\s*/Page\b", data))
    object_markers = len(re.findall(rb"(?m)^\s*\d+\s+\d+\s+obj\b", data))
    declared_sizes = [int(value) for value in re.findall(rb"/Size\s+(\d+)", data)]
    if page_markers > policy.max_pdf_pages:
        raise UploadValidationError("PDF 页数超过限制")
    if object_markers > policy.max_pdf_objects or (
        declared_sizes and max(declared_sizes) > policy.max_pdf_objects
    ):
        raise UploadValidationError("PDF 对象数量超过限制")


def _validate_image_complexity(data: bytes, policy: UploadPolicy) -> None:
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > policy.max_image_pixels:
                raise UploadValidationError("图片像素数量超过限制")
            image.verify()
    except UploadValidationError:
        raise
    except Exception as exc:
        raise UploadValidationError("图片文件解析失败") from exc


def _validate_magic(ext: str, data: bytes, policy: UploadPolicy) -> None:
    if ext in {".xlsx", ".docx"}:
        _validate_office_container(data, ext, policy)
        return
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadValidationError("文件扩展名与实际格式不一致")
        _validate_pdf_complexity(data, policy)
    if ext in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff"):
        raise UploadValidationError("图片文件扩展名与实际格式不一致")
    if ext == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UploadValidationError("图片文件扩展名与实际格式不一致")
    if ext == ".webp" and not (
        len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    ):
        raise UploadValidationError("图片文件扩展名与实际格式不一致")
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        _validate_image_complexity(data, policy)
    if ext in {".txt", ".md", ".json", ".csv"} and b"\x00" in data[:8192]:
        raise UploadValidationError("文本文件实际格式不正确")
    if ext in {".txt", ".md", ".json", ".csv"}:
        text = data.decode("utf-8-sig", errors="replace")
        lines = text.splitlines()
        if len(lines) > policy.max_rows:
            raise UploadValidationError("文本数据行数超过限制")
        if any(len(line) > policy.max_cell_characters for line in lines):
            raise UploadValidationError("文本单行内容过长")


def validate_upload(filename: str, data: bytes, policy: UploadPolicy) -> str:
    """Validate name, size, magic and decompressed document complexity."""

    safe_name = Path(filename or "").name
    ext = Path(safe_name).suffix.lower()
    if ext not in policy.extensions:
        allowed = "、".join(sorted(policy.extensions))
        raise UploadValidationError(f"不支持该文件类型，仅允许 {allowed}", 415)
    if not data:
        raise UploadValidationError("文件为空")
    if len(data) > policy.max_bytes:
        raise UploadValidationError("文件过大", 413)
    _validate_magic(ext, data, policy)
    return ext
