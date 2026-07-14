import unittest
import zipfile
from io import BytesIO

from PIL import Image

from services.upload_validation import UploadPolicy, UploadValidationError, validate_upload


def _xlsx(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    defaults = {
        "[Content_Types].xml": b"<Types/>",
        "xl/workbook.xml": b"<workbook/>",
    }
    defaults.update(entries)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in defaults.items():
            archive.writestr(name, content)
    return output.getvalue()


class UploadValidationTests(unittest.TestCase):
    def test_rejects_archive_with_too_many_entries(self):
        content = _xlsx({
            "xl/worksheets/sheet1.xml": b"<worksheet/>",
            "xl/worksheets/sheet2.xml": b"<worksheet/>",
        })
        policy = UploadPolicy(
            extensions=frozenset({".xlsx"}),
            max_bytes=1024 * 1024,
            max_archive_entries=3,
        )

        with self.assertRaisesRegex(UploadValidationError, "文件项过多"):
            validate_upload("attack.xlsx", content, policy)

    def test_rejects_xlsx_rows_columns_and_cell_text_before_parser_runs(self):
        worksheet = (
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<sheetData><row r="11"><c r="C11" t="inlineStr"><is><t>'
            + b"x" * 21
            + b"</t></is></c></row></sheetData></worksheet>"
        )
        content = _xlsx({"xl/worksheets/sheet1.xml": worksheet})

        for field, value, message in (
            ("max_rows", 10, "行数"),
            ("max_columns", 2, "列数"),
            ("max_cell_characters", 20, "单元格"),
        ):
            with self.subTest(field=field):
                kwargs = {
                    "extensions": frozenset({".xlsx"}),
                    "max_bytes": 1024 * 1024,
                    "max_rows": 100,
                    "max_columns": 100,
                    "max_cell_characters": 100,
                }
                kwargs[field] = value
                with self.assertRaisesRegex(UploadValidationError, message):
                    validate_upload("attack.xlsx", content, UploadPolicy(**kwargs))

    def test_rejects_extension_magic_mismatch(self):
        policy = UploadPolicy(extensions=frozenset({".pdf"}), max_bytes=1024)

        with self.assertRaisesRegex(UploadValidationError, "实际格式"):
            validate_upload("fake.pdf", b"not a pdf", policy)

    def test_rejects_pdf_page_and_object_complexity_before_extraction(self):
        policy = UploadPolicy(
            extensions=frozenset({".pdf"}),
            max_bytes=1024 * 1024,
            max_pdf_pages=2,
            max_pdf_objects=10,
        )
        too_many_pages = b"%PDF-1.7\n" + b"/Type /Page\n" * 3 + b"%%EOF"
        too_many_objects = b"%PDF-1.7\n/Size 11\n%%EOF"

        with self.assertRaisesRegex(UploadValidationError, "页数"):
            validate_upload("pages.pdf", too_many_pages, policy)
        with self.assertRaisesRegex(UploadValidationError, "对象"):
            validate_upload("objects.pdf", too_many_objects, policy)

    def test_rejects_invalid_or_excessive_pixel_images(self):
        policy = UploadPolicy(
            extensions=frozenset({".png"}),
            max_bytes=1024 * 1024,
            max_image_pixels=100,
        )
        image = BytesIO()
        Image.new("RGB", (11, 10), "white").save(image, format="PNG")

        with self.assertRaisesRegex(UploadValidationError, "像素"):
            validate_upload("large.png", image.getvalue(), policy)
        with self.assertRaisesRegex(UploadValidationError, "解析失败"):
            validate_upload("broken.png", b"\x89PNG\r\n\x1a\ninvalid", policy)

    def test_valid_pdf_and_text_pass(self):
        pdf_policy = UploadPolicy(extensions=frozenset({".pdf"}), max_bytes=1024)
        text_policy = UploadPolicy(extensions=frozenset({".txt"}), max_bytes=1024)

        self.assertEqual(validate_upload("brief.pdf", b"%PDF-1.7\n%%EOF", pdf_policy), ".pdf")
        self.assertEqual(validate_upload("brief.txt", "活动方案".encode(), text_policy), ".txt")


if __name__ == "__main__":
    unittest.main()
