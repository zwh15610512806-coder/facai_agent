import hashlib
import io
import json
import os
import struct
import subprocess
import tempfile
import threading
import unittest
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


ASSET_TYPES = {
    "source",
    "working",
    "preview",
    "cutout",
    "generated_background",
    "composed",
    "export",
}


def _normalized_sql(value: str | None) -> str:
    return "".join((value or "").lower().split()).replace('"', "").replace("`", "")


def _image_bytes(
    image_format: str,
    *,
    mode: str = "RGB",
    size: tuple[int, int] = (3, 2),
    color: object = (12, 34, 56),
) -> bytes:
    image = Image.new(mode, size, color)
    output = io.BytesIO()
    options = {"lossless": True} if image_format == "WEBP" else {}
    image.save(output, format=image_format, **options)
    return output.getvalue()


def _png_with_reported_dimensions(width: int, height: int) -> bytes:
    payload = bytearray(_image_bytes("PNG", size=(1, 1)))
    payload[16:24] = struct.pack(">II", width, height)
    payload[29:33] = struct.pack(">I", zlib.crc32(payload[12:29]) & 0xFFFFFFFF)
    return bytes(payload)


def _padded_png_over_upload_limit() -> bytes:
    png = _image_bytes("PNG")
    return png + b"padding" * (((12_582_912 - len(png)) // 7) + 2)


class CanvasImageValidationTests(unittest.TestCase):
    def _inspect(self, data: bytes, *, filename: str, declared_mime: str):
        from services.canvas.image_validation import inspect_image

        return inspect_image(data, filename=filename, declared_mime=declared_mime)

    def _assert_rejected(
        self,
        expected_code: str,
        data: object,
        *,
        filename: str = "asset.png",
        declared_mime: str = "image/png",
    ) -> None:
        from services.canvas.image_validation import CanvasImageValidationError

        with self.assertRaises(CanvasImageValidationError) as raised:
            self._inspect(data, filename=filename, declared_mime=declared_mime)
        self.assertEqual(expected_code, raised.exception.code)

    def test_accepts_jpeg_png_and_static_webp_with_original_sha_and_alpha_channel(self):
        fixtures = (
            ("JPEG", "photo.JPG", "image/jpeg", "RGB", False),
            ("PNG", "photo.png", "image/png", "RGBA", True),
            ("WEBP", "photo.WeBp", "image/webp", "RGB", False),
        )
        for image_format, filename, mime_type, mode, expected_alpha in fixtures:
            with self.subTest(image_format=image_format):
                color = (12, 34, 56, 255) if mode == "RGBA" else (12, 34, 56)
                data = _image_bytes(image_format, mode=mode, color=color)
                inspected = self._inspect(
                    data,
                    filename=filename,
                    declared_mime=mime_type,
                )
                self.assertEqual(image_format, inspected.format)
                self.assertEqual(mime_type, inspected.mime_type)
                self.assertEqual((3, 2), (inspected.width, inspected.height))
                self.assertEqual(hashlib.sha256(data).hexdigest(), inspected.sha256)
                self.assertIs(expected_alpha, inspected.has_alpha)

    def test_rejects_non_bytes_empty_and_over_12_mib_before_format_checks(self):
        self._assert_rejected("canvas_image_invalid_bytes", bytearray(b"not-bytes"))
        self._assert_rejected("canvas_image_empty", b"")
        self._assert_rejected("canvas_image_too_large", b"x" * (12_582_912 + 1))

    def test_rejects_unsupported_extension_and_declared_mime_in_fixed_order(self):
        png = _image_bytes("PNG")
        self._assert_rejected(
            "canvas_image_extension_unsupported",
            png,
            filename="asset.gif",
        )
        self._assert_rejected(
            "canvas_image_mime_unsupported",
            png,
            filename="asset.png",
            declared_mime="image/gif",
        )

    def test_rejects_extension_mime_magic_disagreement_and_corrupt_decode(self):
        jpeg = _image_bytes("JPEG")
        self._assert_rejected(
            "canvas_image_signature_mismatch",
            jpeg,
            filename="asset.png",
            declared_mime="image/png",
        )
        self._assert_rejected(
            "canvas_image_signature_mismatch",
            jpeg,
            filename="asset.jpg",
            declared_mime="image/png",
        )
        self._assert_rejected(
            "canvas_image_decode_failed",
            b"\x89PNG\r\n\x1a\ncorrupt",
        )

    def test_rejects_animated_webp_before_verify(self):
        first = Image.new("RGB", (2, 2), "red")
        second = Image.new("RGB", (2, 2), "blue")
        output = io.BytesIO()
        first.save(
            output,
            format="WEBP",
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0,
            lossless=True,
        )
        self._assert_rejected(
            "canvas_image_animated",
            output.getvalue(),
            filename="animated.webp",
            declared_mime="image/webp",
        )

    def test_rejects_edge_then_pixel_limits_using_reported_dimensions(self):
        self._assert_rejected(
            "canvas_image_edge_exceeded",
            _png_with_reported_dimensions(16_385, 1),
        )
        self._assert_rejected(
            "canvas_image_pixels_exceeded",
            _png_with_reported_dimensions(8_000, 5_001),
        )

    def test_decompression_bomb_warning_and_error_fail_closed(self):
        png = _image_bytes("PNG", size=(10, 10))
        for threshold in (75, 40):
            with self.subTest(max_image_pixels=threshold):
                with patch("PIL.Image.MAX_IMAGE_PIXELS", threshold):
                    self._assert_rejected("canvas_image_decompression_bomb", png)

    def test_verify_or_full_decode_failure_is_rejected(self):
        png = _image_bytes("PNG", size=(8, 8))
        self._assert_rejected("canvas_image_decode_failed", png[:-10])

        jpeg = _image_bytes("JPEG", size=(64, 64))
        self._assert_rejected(
            "canvas_image_decode_failed",
            jpeg[:-20],
            filename="asset.jpeg",
            declared_mime="image/jpeg",
        )

    def test_rechecks_format_size_and_animation_after_full_load(self):
        from services.canvas import image_validation

        class MutableDecoder:
            def __init__(self, mutation: str | None = None):
                self.format = "PNG"
                self.size = (3, 2)
                self.is_animated = False
                self.n_frames = 1
                self.info = {}
                self._mutation = mutation

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def verify(self):
                return None

            def load(self):
                if self._mutation == "format":
                    self.format = "JPEG"
                elif self._mutation == "size":
                    self.size = (4, 2)
                elif self._mutation == "animation":
                    self.is_animated = True
                    self.n_frames = 2

            def getbands(self):
                return ("R", "G", "B")

        expected_codes = {
            "format": "canvas_image_format_mismatch",
            "size": "canvas_image_format_mismatch",
            "animation": "canvas_image_animated",
        }
        for mutation, expected_code in expected_codes.items():
            with self.subTest(mutation=mutation):
                decoders = [MutableDecoder(), MutableDecoder(mutation)]
                with patch.object(image_validation.Image, "open", side_effect=decoders):
                    self._assert_rejected(
                        expected_code,
                        _image_bytes("PNG"),
                    )

    def test_palette_transparency_reports_alpha_without_classifying_opaque_palette_as_alpha(self):
        transparent = Image.new("P", (2, 2), 0)
        transparent.info["transparency"] = 0
        transparent_bytes = io.BytesIO()
        transparent.save(transparent_bytes, format="PNG")

        opaque = Image.new("P", (2, 2), 0)
        opaque_bytes = io.BytesIO()
        opaque.save(opaque_bytes, format="PNG")

        self.assertTrue(
            self._inspect(
                transparent_bytes.getvalue(),
                filename="palette.png",
                declared_mime="image/png",
            ).has_alpha
        )
        self.assertFalse(
            self._inspect(
                opaque_bytes.getvalue(),
                filename="palette.png",
                declared_mime="image/png",
            ).has_alpha
        )

    def test_multiple_faults_preserve_the_documented_validation_priority(self):
        cases = (
            (b"", "asset.gif", "image/gif", "canvas_image_empty"),
            (b"x" * (12_582_912 + 1), "asset.gif", "image/gif", "canvas_image_too_large"),
            (_image_bytes("PNG"), "asset.gif", "image/gif", "canvas_image_extension_unsupported"),
            (_image_bytes("PNG"), "asset.png", "image/gif", "canvas_image_mime_unsupported"),
        )
        for data, filename, mime_type, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                self._assert_rejected(
                    expected_code,
                    data,
                    filename=filename,
                    declared_mime=mime_type,
                )

    def test_unexpected_decoder_exception_is_still_a_stable_decode_failure(self):
        from services.canvas import image_validation

        with patch.object(
            image_validation.Image,
            "open",
            side_effect=RuntimeError("decoder internals must not escape"),
        ):
            self._assert_rejected(
                "canvas_image_decode_failed",
                _image_bytes("PNG"),
            )

    def test_trusted_inspection_skips_only_upload_byte_limit(self):
        from services.canvas.image_validation import inspect_trusted_image

        data = _padded_png_over_upload_limit()
        self._assert_rejected("canvas_image_too_large", data)
        inspected = inspect_trusted_image(
            data,
            filename="derived.png",
            declared_mime="image/png",
        )
        self.assertEqual("PNG", inspected.format)
        self.assertEqual((3, 2), (inspected.width, inspected.height))
        self.assertEqual(hashlib.sha256(data).hexdigest(), inspected.sha256)


class CanvasTransparencyTests(unittest.TestCase):
    def _detect(self, image: Image.Image, **kwargs) -> bool:
        try:
            from services.canvas.transparency import (
                has_effective_transparent_background,
            )
        except ModuleNotFoundError:
            self.fail("canvas transparency detector is not implemented")
        return has_effective_transparent_background(image, **kwargs)

    @staticmethod
    def _rgba(
        size: tuple[int, int],
        pixels: tuple[tuple[int, int, int], ...],
    ) -> Image.Image:
        image = Image.new("RGBA", size, (20, 40, 60, 255))
        for x, y, alpha in pixels:
            image.putpixel((x, y), (20, 40, 60, alpha))
        return image

    def test_exact_half_percent_alpha_250_region_is_detected_from_each_edge(self):
        edge_pixels = (
            ("top", (10, 0, 250)),
            ("bottom", (10, 9, 250)),
            ("left", (0, 5, 250)),
            ("right", (19, 5, 250)),
        )
        for edge, pixel in edge_pixels:
            with self.subTest(edge=edge):
                self.assertTrue(self._detect(self._rgba((20, 10), (pixel,))))

    def test_alpha_251_below_threshold_and_duplicate_corner_seed_are_false(self):
        self.assertFalse(
            self._detect(self._rgba((20, 10), ((10, 0, 251),)))
        )
        self.assertFalse(
            self._detect(self._rgba((20, 20), ((10, 0, 0),)))
        )
        self.assertFalse(
            self._detect(self._rgba((20, 20), ((0, 0, 0),)))
        )

    def test_center_hole_and_opaque_images_are_false(self):
        center_hole = self._rgba((10, 10), ((5, 5, 0),))
        opaque_png = Image.new("RGBA", (20, 10), (0, 0, 0, 255))
        white_png = Image.open(
            io.BytesIO(_image_bytes("PNG", color=(255, 255, 255)))
        )
        white_jpeg = Image.open(
            io.BytesIO(_image_bytes("JPEG", color=(255, 255, 255)))
        )
        complex_opaque = Image.new("RGBA", (20, 10))
        complex_opaque.putdata(
            [
                (
                    (index * 17) % 256,
                    (index * 37) % 256,
                    (index * 67) % 256,
                    255,
                )
                for index in range(200)
            ]
        )

        for label, image in (
            ("center-hole", center_hole),
            ("opaque-png", opaque_png),
            ("white-png", white_png),
            ("white-jpeg", white_jpeg),
            ("complex-opaque", complex_opaque),
        ):
            with self.subTest(label=label):
                self.assertFalse(self._detect(image))

    def test_diagonal_edge_connection_uses_eight_neighbors(self):
        image = self._rgba(
            (20, 20),
            (
                (0, 0, 250),
                (1, 1, 250),
            ),
        )
        self.assertTrue(self._detect(image))

    def test_invalid_threshold_and_fraction_parameters_are_rejected(self):
        image = self._rgba((20, 10), ((0, 0, 0),))
        for alpha_threshold in (True, -1, 256, 250.0):
            with self.subTest(alpha_threshold=alpha_threshold):
                with self.assertRaises(ValueError):
                    self._detect(image, alpha_threshold=alpha_threshold)
        for min_edge_fraction in (
            True,
            0,
            -0.01,
            1.01,
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with self.subTest(min_edge_fraction=min_edge_fraction):
                with self.assertRaises(ValueError):
                    self._detect(image, min_edge_fraction=min_edge_fraction)

    def test_fraction_boundary_uses_an_exact_unique_pixel_comparison(self):
        image = self._rgba((5, 1), ((0, 0, 0),))
        self.assertTrue(self._detect(image, min_edge_fraction=0.2))
        self.assertFalse(self._detect(image, min_edge_fraction=0.2000001))

    def test_forty_megapixel_transparent_image_returns_at_the_threshold(self):
        class LimitedAlphaValues:
            def __init__(self):
                self.read_count = 0

            def __len__(self):
                return 40_000_000

            def __getitem__(self, _index):
                self.read_count += 1
                if self.read_count > 300_000:
                    raise AssertionError(
                        "detector scanned beyond the effective threshold"
                    )
                return 0

        class LimitedAlpha:
            def __init__(self, values):
                self.values = values

            def tobytes(self):
                return self.values

        class FortyMegapixelImage:
            size = (8_000, 5_000)
            info: dict[str, object] = {}

            def __init__(self):
                self.alpha_values = LimitedAlphaValues()

            @staticmethod
            def getbands():
                return ("R", "G", "B", "A")

            def getchannel(self, _channel):
                return LimitedAlpha(self.alpha_values)

        image = FortyMegapixelImage()
        self.assertTrue(self._detect(image))
        self.assertLessEqual(image.alpha_values.read_count, 300_000)


class CanvasStoragePrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "canvas-data"
        self.project_id = str(uuid4())

    def tearDown(self):
        self.tmp.cleanup()

    def _asset(
        self,
        *,
        asset_type: str,
        relative_path: str,
        project_id: str | None = None,
        asset_id: str | None = None,
        mime_type: str = "image/png",
    ):
        from canvas_models import CanvasAsset

        return CanvasAsset(
            id=asset_id or str(uuid4()),
            project_id=project_id or self.project_id,
            asset_type=asset_type,
            relative_path=relative_path,
            original_filename="asset.png",
            mime_type=mime_type,
            byte_count=1,
            width=1,
            height=1,
            sha256="0" * 64,
            metadata_json="{}",
        )

    def _assert_storage_error(self, expected_code: str, callback) -> None:
        from services.canvas.storage import CanvasStorageError

        with self.assertRaises(CanvasStorageError) as raised:
            callback()
        self.assertEqual(expected_code, raised.exception.code)

    def _make_directory_link(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except OSError as symlink_error:
            if os.name != "nt":
                self.skipTest(f"directory symlinks are unavailable: {symlink_error}")
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            self.skipTest("directory symlinks and junctions are unavailable")

    def test_resolve_asset_path_uses_exact_type_directories_and_uuid_disk_names(self):
        from services.canvas import storage

        directory_by_type = {
            "source": "source",
            "working": "working",
            "preview": "preview",
            "cutout": "cutout",
            "generated_background": "generated",
            "composed": "composed",
            "export": "exports",
        }
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
            for asset_type, directory in directory_by_type.items():
                with self.subTest(asset_type=asset_type):
                    asset_id = str(uuid4())
                    asset_path = root / directory / f"{asset_id}.png"
                    asset_path.write_bytes(b"asset")
                    asset = self._asset(
                        asset_type=asset_type,
                        relative_path=f"{directory}/{asset_id}.png",
                        asset_id=asset_id,
                    )
                    resolved = storage.resolve_asset_path(asset, project_id=self.project_id)
                    self.assertEqual(asset_path, resolved)

            mismatched = self._asset(
                asset_type="generated_background",
                relative_path=f"generated_background/{uuid4()}.png",
            )
            self._assert_storage_error(
                "canvas_storage_path_invalid",
                lambda: storage.resolve_asset_path(
                    mismatched,
                    project_id=self.project_id,
                ),
            )

    def test_resolve_asset_path_requires_matching_id_existing_regular_file_and_safe_extension(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
            asset_id = str(uuid4())

            missing = self._asset(
                asset_type="source",
                relative_path=f"source/{asset_id}.png",
                asset_id=asset_id,
            )
            self._assert_storage_error(
                "canvas_storage_asset_missing",
                lambda: storage.resolve_asset_path(missing, project_id=self.project_id),
            )

            directory_target = root / "source" / f"{asset_id}.png"
            directory_target.mkdir()
            self._assert_storage_error(
                "canvas_storage_asset_not_regular",
                lambda: storage.resolve_asset_path(
                    missing,
                    project_id=self.project_id,
                ),
            )
            directory_target.rmdir()

            actual_id = str(uuid4())
            mismatched_id = self._asset(
                asset_type="source",
                relative_path=f"source/{actual_id}.png",
                asset_id=asset_id,
            )
            (root / "source" / f"{actual_id}.png").write_bytes(b"other")
            self._assert_storage_error(
                "canvas_storage_path_invalid",
                lambda: storage.resolve_asset_path(
                    mismatched_id,
                    project_id=self.project_id,
                ),
            )

            invalid_extension = self._asset(
                asset_type="working",
                relative_path=f"working/{asset_id}.jpg",
                asset_id=asset_id,
                mime_type="image/jpeg",
            )
            (root / "working" / f"{asset_id}.jpg").write_bytes(b"jpeg")
            self._assert_storage_error(
                "canvas_storage_path_invalid",
                lambda: storage.resolve_asset_path(
                    invalid_extension,
                    project_id=self.project_id,
                ),
            )

    def test_resolve_asset_path_rejects_windows_traversal_ads_devices_and_ambiguous_segments(self):
        from services.canvas import storage

        asset_id = str(uuid4())
        invalid_paths = (
            "../escape.png",
            f"/source/{asset_id}.png",
            f"C:/source/{asset_id}.png",
            f"C:\\source\\{asset_id}.png",
            f"\\\\server\\share\\{asset_id}.png",
            f"source\\{asset_id}.png",
            f"source/{asset_id}.png:stream",
            f"source/{asset_id}.png\x00tail",
            f"source//{asset_id}.png",
            f"source/./{asset_id}.png",
            f"source/../{asset_id}.png",
            "source/CON.png",
            "source/com1.png",
            f"source/{asset_id}.png.",
            f"source/{asset_id}.png ",
        )
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            storage.ensure_project_tree(self.project_id)
            for relative_path in invalid_paths:
                with self.subTest(relative_path=repr(relative_path)):
                    asset = self._asset(
                        asset_type="source",
                        relative_path=relative_path,
                    )
                    self._assert_storage_error(
                        "canvas_storage_path_invalid",
                        lambda asset=asset: storage.resolve_asset_path(
                            asset,
                            project_id=self.project_id,
                        ),
                    )

    def test_resolve_and_usage_reject_existing_reparse_points_without_touching_outside(self):
        from services.canvas import storage

        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")
        project = self.data_root / self.project_id
        project.mkdir(parents=True)
        self._make_directory_link(project / "source", outside)
        asset_id = str(uuid4())
        (outside / f"{asset_id}.png").write_bytes(b"outside-asset")
        asset = self._asset(
            asset_type="source",
            relative_path=f"source/{asset_id}.png",
            asset_id=asset_id,
        )

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            self._assert_storage_error(
                "canvas_storage_reparse_point",
                lambda: storage.resolve_asset_path(asset, project_id=self.project_id),
            )
            self._assert_storage_error(
                "canvas_storage_reparse_point",
                lambda: storage.canvas_usage_bytes(project_id=self.project_id),
            )

        self.assertEqual(b"keep", sentinel.read_bytes())

    def test_usage_counts_all_projects_and_optionally_tmp_and_uploading_files(self):
        from services.canvas import storage

        other_project_id = str(uuid4())
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
            other_root = storage.ensure_project_tree(other_project_id)
            (root / "source" / f"{uuid4()}.png").write_bytes(b"abc")
            (root / "tmp" / "pending.bin").write_bytes(b"12345")
            (root / "working" / f"{uuid4()}.png.uploading").write_bytes(b"1234567")
            (other_root / "source" / f"{uuid4()}.png").write_bytes(b"other-bytes")

            self.assertEqual(15, storage.canvas_usage_bytes(project_id=self.project_id))
            self.assertEqual(
                3,
                storage.canvas_usage_bytes(
                    project_id=self.project_id,
                    include_temporary=False,
                ),
            )
            self.assertEqual(26, storage.canvas_usage_bytes())

    def test_usage_fails_closed_for_unexpected_root_files(self):
        from services.canvas import storage

        self.data_root.mkdir()
        (self.data_root / "unexpected.bin").write_bytes(b"unsafe")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            self._assert_storage_error(
                "canvas_storage_unsafe_entry",
                storage.canvas_usage_bytes,
            )

    def test_usage_fails_closed_for_non_uuid_project_directories(self):
        from services.canvas import storage

        unsafe_directory = self.data_root / "not-a-project"
        unsafe_directory.mkdir(parents=True)
        (unsafe_directory / "asset.bin").write_bytes(b"unsafe")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            self._assert_storage_error(
                "canvas_storage_unsafe_entry",
                storage.canvas_usage_bytes,
            )

    def test_capacity_combines_usage_reservations_additional_bytes_and_exact_free_boundary(self):
        from services.canvas import storage

        other_project_id = str(uuid4())
        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(storage, "CANVAS_PROJECT_QUOTA_BYTES", 10),
            patch.object(storage, "CANVAS_TOTAL_QUOTA_BYTES", 20),
            patch.object(storage, "CANVAS_MIN_FREE_BYTES", 5),
        ):
            root = storage.ensure_project_tree(self.project_id)
            other_root = storage.ensure_project_tree(other_project_id)
            (root / "source" / f"{uuid4()}.png").write_bytes(b"1234")
            (other_root / "source" / f"{uuid4()}.png").write_bytes(b"123")

            with patch.object(
                storage.shutil,
                "disk_usage",
                return_value=SimpleNamespace(free=12),
            ):
                storage.assert_canvas_capacity(
                    project_id=self.project_id,
                    additional_bytes=3,
                    reserved_project_bytes=3,
                    reserved_total_bytes=4,
                )

            self._assert_storage_error(
                "canvas_storage_project_quota_exceeded",
                lambda: storage.assert_canvas_capacity(
                    project_id=self.project_id,
                    additional_bytes=4,
                    reserved_project_bytes=3,
                ),
            )
            self._assert_storage_error(
                "canvas_storage_total_quota_exceeded",
                lambda: storage.assert_canvas_capacity(
                    project_id=self.project_id,
                    additional_bytes=5,
                    reserved_total_bytes=9,
                ),
            )
            with patch.object(
                storage.shutil,
                "disk_usage",
                return_value=SimpleNamespace(free=11),
            ):
                self._assert_storage_error(
                    "canvas_storage_low_disk",
                    lambda: storage.assert_canvas_capacity(
                        project_id=self.project_id,
                        additional_bytes=3,
                        reserved_total_bytes=4,
                    ),
                )

    def test_capacity_rejects_bool_negative_and_non_integer_inputs(self):
        from services.canvas import storage

        argument_names = (
            "additional_bytes",
            "reserved_project_bytes",
            "reserved_total_bytes",
        )
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            storage.ensure_project_tree(self.project_id)
            for argument_name in argument_names:
                for invalid_value in (True, -1, 1.5):
                    with self.subTest(
                        argument_name=argument_name,
                        invalid_value=invalid_value,
                    ):
                        arguments = {
                            "project_id": self.project_id,
                            "additional_bytes": 0,
                            "reserved_project_bytes": 0,
                            "reserved_total_bytes": 0,
                        }
                        arguments[argument_name] = invalid_value
                        self._assert_storage_error(
                            "canvas_storage_invalid_capacity",
                            lambda arguments=arguments: storage.assert_canvas_capacity(
                                **arguments
                            ),
                        )

    def test_remove_project_tree_accepts_safe_partial_and_legacy_regular_contents(self):
        from services.canvas import storage

        root = self.data_root / self.project_id
        (root / "source" / "legacy-nested").mkdir(parents=True)
        (root / "source" / "legacy-nested" / "asset.bin").write_bytes(b"asset")
        (root / "legacy.bin").write_bytes(b"legacy")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            storage.remove_project_tree(self.project_id)
        self.assertFalse(root.exists())

    def test_disk_usage_oserror_is_wrapped_with_stable_code_without_path_leak(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            storage.ensure_project_tree(self.project_id)
            with patch.object(
                storage.shutil,
                "disk_usage",
                side_effect=PermissionError(f"denied {self.data_root}"),
            ):
                with self.assertRaises(storage.CanvasStorageError) as raised:
                    storage.assert_canvas_capacity(
                        project_id=self.project_id,
                        additional_bytes=0,
                    )
        self.assertEqual("canvas_storage_io_failed", raised.exception.code)
        self.assertNotIn(str(self.data_root), str(raised.exception))
        self.assertNotIn(self.tmp.name, str(raised.exception))

    def test_lstat_oserror_is_wrapped_with_stable_code_without_path_leak(self):
        from services.canvas import storage

        self.data_root.mkdir()
        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(
                storage.Path,
                "lstat",
                side_effect=PermissionError(f"denied {self.data_root}"),
            ),
        ):
            with self.assertRaises(storage.CanvasStorageError) as raised:
                storage.project_root(self.project_id)
        self.assertEqual("canvas_storage_io_failed", raised.exception.code)
        self.assertNotIn(str(self.data_root), str(raised.exception))
        self.assertNotIn(self.tmp.name, str(raised.exception))

    def test_lexists_oserror_is_wrapped_with_stable_code_without_path_leak(self):
        from services.canvas import storage

        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(
                storage.os.path,
                "lexists",
                side_effect=PermissionError(f"denied {self.data_root}"),
            ),
        ):
            with self.assertRaises(storage.CanvasStorageError) as raised:
                storage.project_root(self.project_id)
        self.assertEqual("canvas_storage_io_failed", raised.exception.code)
        self.assertNotIn(str(self.data_root), str(raised.exception))
        self.assertNotIn(self.tmp.name, str(raised.exception))

    def test_usage_scan_never_follows_a_directory_swapped_after_entry_stat(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        source_directory = root / "source"
        original_source_directory = root / "source-original"
        owned_file = source_directory / "owned.bin"
        owned_file.write_bytes(b"x" * 101)
        outside = Path(self.tmp.name) / "usage-outside"
        outside.mkdir()
        sentinel = outside / "keep.bin"
        sentinel.write_bytes(b"outside")
        real_open_record = storage._open_record
        swapped = False
        rename_blocked = False

        def swap_before_child_pin(parent, record, *, delete=False):
            nonlocal swapped, rename_blocked
            if parent.path == root and record.name == "source" and not swapped:
                try:
                    source_directory.rename(original_source_directory)
                except OSError:
                    rename_blocked = True
                else:
                    swapped = True
                    self._make_directory_link(source_directory, outside)
            return real_open_record(parent, record, delete=delete)

        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
                patch.object(
                    storage,
                    "_open_record",
                    side_effect=swap_before_child_pin,
                ),
            ):
                usage = storage.canvas_usage_bytes(project_id=self.project_id)
            self.assertTrue(rename_blocked)
            self.assertFalse(swapped)
            self.assertEqual(101, usage)
            self.assertEqual(b"outside", sentinel.read_bytes())
        finally:
            if original_source_directory.exists():
                if storage._lexists(source_directory):
                    source_directory.rmdir()
                original_source_directory.rename(source_directory)

    def test_remove_project_tree_pins_each_child_before_recursive_delete(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        source_directory = root / "source"
        original_source_directory = root / "source-original"
        (source_directory / "owned.bin").write_bytes(b"owned")
        outside = Path(self.tmp.name) / "delete-outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")
        real_open_record = storage._open_record
        attempted = False
        rename_blocked = False

        def attack_after_child_pin(parent, record, *, delete=False):
            nonlocal attempted, rename_blocked
            child = real_open_record(parent, record, delete=delete)
            if parent.path == root and record.name == "source" and not attempted:
                attempted = True
                try:
                    source_directory.rename(original_source_directory)
                except OSError:
                    rename_blocked = True
                else:
                    self._make_directory_link(source_directory, outside)
            return child

        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
                patch.object(
                    storage,
                    "_open_record",
                    side_effect=attack_after_child_pin,
                ),
            ):
                storage.remove_project_tree(self.project_id)
            self.assertTrue(attempted)
            self.assertTrue(rename_blocked)
            self.assertFalse(root.exists())
            self.assertEqual(b"keep", sentinel.read_bytes())
        finally:
            if original_source_directory.exists():
                if storage._lexists(source_directory):
                    try:
                        source_directory.rmdir()
                    except OSError:
                        pass
                if root.exists() and not source_directory.exists():
                    original_source_directory.rename(source_directory)

    def test_remove_project_tree_rejects_source_swapped_before_child_pin(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        source_directory = root / "source"
        original_source_directory = root / "source-original"
        owned = source_directory / "owned.bin"
        owned.write_bytes(b"owned")
        outside = Path(self.tmp.name) / "delete-pre-pin-outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")
        real_open_record = storage._open_record
        swapped = False
        rename_blocked = False

        def swap_before_delete_child_pin(parent, record, *, delete=False):
            nonlocal swapped, rename_blocked
            if (
                delete
                and parent.path == root
                and record.name == "source"
                and not swapped
            ):
                try:
                    source_directory.rename(original_source_directory)
                except OSError:
                    rename_blocked = True
                else:
                    swapped = True
                    self._make_directory_link(source_directory, outside)
            return real_open_record(parent, record, delete=delete)

        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
                patch.object(
                    storage,
                    "_open_record",
                    side_effect=swap_before_delete_child_pin,
                ),
            ):
                storage.remove_project_tree(self.project_id)
            self.assertTrue(rename_blocked)
            self.assertFalse(swapped)
            self.assertFalse(root.exists())
            self.assertEqual(b"keep", sentinel.read_bytes())
        finally:
            if original_source_directory.exists():
                if storage._lexists(source_directory):
                    source_directory.rmdir()
                original_source_directory.rename(source_directory)

    def test_usage_rejects_regular_file_alternate_data_streams(self):
        from services.canvas import storage

        if os.name != "nt":
            self.skipTest("NTFS alternate data streams are Windows-specific")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        owned = root / "source" / "owned.bin"
        owned.write_bytes(b"x")
        try:
            Path(f"{owned}:extra").write_bytes(b"y" * 4096)
        except OSError as exc:
            self.skipTest(f"alternate data streams are unavailable: {exc}")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            self._assert_storage_error(
                "canvas_storage_unsafe_entry",
                lambda: storage.canvas_usage_bytes(project_id=self.project_id),
            )

    def test_usage_rejects_directory_alternate_data_streams(self):
        from services.canvas import storage

        if os.name != "nt":
            self.skipTest("NTFS alternate data streams are Windows-specific")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        source = root / "source"
        try:
            Path(f"{source}:extra").write_bytes(b"z" * 4096)
        except OSError as exc:
            self.skipTest(f"directory alternate data streams are unavailable: {exc}")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            self._assert_storage_error(
                "canvas_storage_unsafe_entry",
                lambda: storage.canvas_usage_bytes(project_id=self.project_id),
            )

    def test_pin_chain_attempts_every_close_and_keeps_failed_handle_retryable(self):
        from services.canvas import storage

        if os.name != "nt":
            self.skipTest("CloseHandle behavior is Windows-specific")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)

        chain = storage._pin_directory_chain(root)
        pins = chain.__enter__()
        failed_pin = pins[-1]
        real_close = storage._CloseHandle
        close_calls: list[int] = []
        failed_once = False

        def fail_one_close(handle):
            nonlocal failed_once
            close_calls.append(int(handle))
            if int(handle) == failed_pin.handle and not failed_once:
                failed_once = True
                storage.ctypes.set_last_error(5)
                return 0
            return real_close(handle)

        try:
            with patch.object(storage, "_CloseHandle", side_effect=fail_one_close):
                self._assert_storage_error(
                    "canvas_storage_io_failed",
                    lambda: chain.__exit__(None, None, None),
                )
            self.assertEqual({pin.handle for pin in pins}, set(close_calls))
            self.assertFalse(failed_pin.closed)
        finally:
            failed_pin.close()
        self.assertTrue(failed_pin.closed)

    def test_ensure_project_tree_rejects_project_swapped_before_relative_create(self):
        from services.canvas import storage

        root = self.data_root / self.project_id
        root.mkdir(parents=True)
        original_root = self.data_root / f"{self.project_id}-original"
        outside = Path(self.tmp.name) / "create-outside"
        outside.mkdir()
        real_open_directory = storage._open_pinned_directory
        swapped = False
        rename_blocked = False

        def swap_before_project_open(path, **kwargs):
            nonlocal swapped, rename_blocked
            if (
                kwargs.get("create")
                and kwargs.get("parent") is not None
                and kwargs["parent"].path == self.data_root
                and kwargs.get("name") == self.project_id
                and not swapped
            ):
                try:
                    root.rename(original_root)
                except OSError:
                    rename_blocked = True
                else:
                    swapped = True
                    self._make_directory_link(root, outside)
            return real_open_directory(path, **kwargs)

        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
                patch.object(
                    storage,
                    "_open_pinned_directory",
                    side_effect=swap_before_project_open,
                ),
            ):
                ensured = storage.ensure_project_tree(self.project_id)
            self.assertTrue(rename_blocked)
            self.assertFalse(swapped)
            self.assertEqual(root, ensured)
            self.assertEqual([], list(outside.iterdir()))
            self.assertEqual(
                set(storage.PROJECT_SUBDIRECTORIES),
                {path.name for path in root.iterdir()},
            )
        finally:
            if original_root.exists():
                if storage._lexists(root):
                    root.rmdir()
                original_root.rename(root)

    def test_ensure_project_tree_supports_first_existing_and_concurrent_creation(self):
        from services.canvas import storage

        def ensure(_index):
            return storage.ensure_project_tree(self.project_id)

        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            ThreadPoolExecutor(max_workers=4) as executor,
        ):
            roots = list(executor.map(ensure, range(4)))
            existing = storage.ensure_project_tree(self.project_id)
        expected = self.data_root / self.project_id
        self.assertEqual([expected] * 4, roots)
        self.assertEqual(expected, existing)
        self.assertEqual(
            set(storage.PROJECT_SUBDIRECTORIES),
            {path.name for path in expected.iterdir()},
        )
        self.assertTrue(all(path.is_dir() for path in expected.iterdir()))

    def test_usage_entry_limit_has_exact_boundary_and_releases_all_handles(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        (root / "source" / "one.bin").write_bytes(b"1")
        (root / "source" / "two.bin").write_bytes(b"2")

        if os.name == "nt":
            get_current_process = storage._kernel32.GetCurrentProcess
            get_current_process.restype = storage.wintypes.HANDLE
            get_process_handle_count = storage._kernel32.GetProcessHandleCount
            get_process_handle_count.argtypes = [
                storage.wintypes.HANDLE,
                storage.ctypes.POINTER(storage.wintypes.DWORD),
            ]
            get_process_handle_count.restype = storage.wintypes.BOOL

            def handle_count():
                count = storage.wintypes.DWORD()
                self.assertTrue(
                    get_process_handle_count(get_current_process(), storage.ctypes.byref(count))
                )
                return int(count.value)

        else:
            handle_count = lambda: 0

        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(storage, "CANVAS_MAX_TREE_ENTRIES", 10),
        ):
            self.assertEqual(2, storage.canvas_usage_bytes(project_id=self.project_id))
            (root / "source" / "three.bin").write_bytes(b"3")
            before = handle_count()
            self._assert_storage_error(
                "canvas_storage_entry_limit_exceeded",
                lambda: storage.canvas_usage_bytes(project_id=self.project_id),
            )
            after = handle_count()
        self.assertLessEqual(after, before + 2)
        (root / "source" / "three.bin").rename(root / "source" / "renamed.bin")

    def test_usage_entry_limit_stops_wide_native_enumeration_before_materializing_all(self):
        from services.canvas import storage

        if os.name != "nt":
            self.skipTest("native enumeration observer is Windows-specific")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        source = root / "source"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        for index in range(5000):
            descriptor = os.open(source / f"{index:04d}.bin", flags, 0o600)
            os.close(descriptor)

        get_current_process = storage._kernel32.GetCurrentProcess
        get_current_process.restype = storage.wintypes.HANDLE
        get_process_handle_count = storage._kernel32.GetProcessHandleCount
        get_process_handle_count.argtypes = [
            storage.wintypes.HANDLE,
            storage.ctypes.POINTER(storage.wintypes.DWORD),
        ]
        get_process_handle_count.restype = storage.wintypes.BOOL

        def handle_count():
            count = storage.wintypes.DWORD()
            self.assertTrue(
                get_process_handle_count(get_current_process(), storage.ctypes.byref(count))
            )
            return int(count.value)

        real_record = storage._DirectoryRecord
        constructed = 0

        def observe_record(*args, **kwargs):
            nonlocal constructed
            constructed += 1
            return real_record(*args, **kwargs)

        before = handle_count()
        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(storage, "CANVAS_MAX_TREE_ENTRIES", 32),
            patch.object(storage, "_DirectoryRecord", side_effect=observe_record),
        ):
            self._assert_storage_error(
                "canvas_storage_entry_limit_exceeded",
                lambda: storage.canvas_usage_bytes(project_id=self.project_id),
            )
        after = handle_count()
        self.assertLessEqual(constructed, 34)
        self.assertLess(constructed, 5000)
        self.assertLessEqual(after, before + 2)

    def test_disk_free_query_keeps_target_chain_pinned_during_query(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            storage.ensure_project_tree(self.project_id)
        original_root = Path(self.tmp.name) / "canvas-data-original"
        outside_tmp = tempfile.TemporaryDirectory(dir=Path.cwd())
        outside = Path(outside_tmp.name)
        if outside.drive.casefold() == self.data_root.drive.casefold():
            outside_tmp.cleanup()
            self.skipTest("a second filesystem volume is unavailable")
        real_disk_usage = storage.shutil.disk_usage
        attempted = False
        rename_blocked = False

        def attack_during_disk_query(target):
            nonlocal attempted, rename_blocked
            attempted = True
            try:
                self.data_root.rename(original_root)
            except OSError:
                rename_blocked = True
            else:
                self._make_directory_link(self.data_root, outside)
            return real_disk_usage(target)

        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
                patch.object(storage, "CANVAS_MIN_FREE_BYTES", 0),
                patch.object(storage.shutil, "disk_usage", side_effect=attack_during_disk_query),
            ):
                storage.assert_canvas_capacity(
                    project_id=self.project_id,
                    additional_bytes=0,
                )
            self.assertTrue(attempted)
            self.assertTrue(rename_blocked)
            self.assertEqual([], list(outside.iterdir()))
        finally:
            if original_root.exists():
                if storage._lexists(self.data_root):
                    self.data_root.rmdir()
                original_root.rename(self.data_root)
            outside_tmp.cleanup()

    def test_project_usage_revalidates_after_counting(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        late_file = root / "source" / "late.bin"
        real_count = storage._count_project_tree
        injected = False

        def inject_during_count(tree, *, include_temporary):
            nonlocal injected
            if not injected:
                injected = True
                late_file.write_bytes(b"x" * 123)
            return real_count(tree, include_temporary=include_temporary)

        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(storage, "_count_project_tree", side_effect=inject_during_count),
        ):
            self._assert_storage_error(
                "canvas_storage_unsafe_entry",
                lambda: storage.canvas_usage_bytes(project_id=self.project_id),
            )
        self.assertTrue(injected)
        self.assertEqual(123, late_file.stat().st_size)

    def test_stream_revalidation_oserror_is_wrapped_without_path_leak(self):
        from services.canvas import storage

        if os.name != "nt":
            self.skipTest("Windows stream metadata is platform-specific")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            storage.ensure_project_tree(self.project_id)
        real_revalidate = storage._revalidate_pinned_tree
        real_streams = storage._windows_streams
        armed = False

        def arm_then_revalidate(tree, **kwargs):
            nonlocal armed
            armed = True
            return real_revalidate(tree, **kwargs)

        def denied_streams(handle, **kwargs):
            if armed:
                raise PermissionError(f"denied {self.data_root}")
            return real_streams(handle, **kwargs)

        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(storage, "_revalidate_pinned_tree", side_effect=arm_then_revalidate),
            patch.object(storage, "_windows_streams", side_effect=denied_streams),
        ):
            with self.assertRaises(storage.CanvasStorageError) as raised:
                storage.canvas_usage_bytes(project_id=self.project_id)
        self.assertEqual("canvas_storage_io_failed", raised.exception.code)
        self.assertNotIn(str(self.data_root), str(raised.exception))
        self.assertNotIn(self.tmp.name, str(raised.exception))

    def test_usage_blocks_in_place_junction_conversion_after_final_revalidation(self):
        from services.canvas import storage

        if os.name != "nt":
            self.skipTest("Windows reparse controls are platform-specific")
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        preview = root / "preview"
        outside = Path(self.tmp.name) / "reparse-outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")

        create_file = storage._kernel32.CreateFileW
        device_io = storage._kernel32.DeviceIoControl
        device_io.argtypes = [
            storage.wintypes.HANDLE,
            storage.wintypes.DWORD,
            storage.wintypes.LPVOID,
            storage.wintypes.DWORD,
            storage.wintypes.LPVOID,
            storage.wintypes.DWORD,
            storage.ctypes.POINTER(storage.wintypes.DWORD),
            storage.wintypes.LPVOID,
        ]
        device_io.restype = storage.wintypes.BOOL

        def set_junction(path, target):
            handle = create_file(
                str(path),
                0x40000000,
                1 | 2 | 4,
                None,
                3,
                0x00200000 | 0x02000000,
                None,
            )
            if handle in (None, storage._INVALID_HANDLE_VALUE):
                return False, storage.ctypes.get_last_error()
            try:
                substitute = ("\\??\\" + str(target)).encode("utf-16-le")
                printable = str(target).encode("utf-16-le")
                names = substitute + b"\0\0" + printable + b"\0\0"
                raw = struct.pack(
                    "<IHHHHHH",
                    0xA0000003,
                    8 + len(names),
                    0,
                    0,
                    len(substitute),
                    len(substitute) + 2,
                    len(printable),
                ) + names
                buffer = storage.ctypes.create_string_buffer(raw)
                returned = storage.wintypes.DWORD()
                ok = device_io(
                    handle,
                    0x000900A4,
                    buffer,
                    len(raw),
                    None,
                    0,
                    storage.ctypes.byref(returned),
                    None,
                )
                return bool(ok), storage.ctypes.get_last_error()
            finally:
                storage._CloseHandle(handle)

        real_revalidate = storage._revalidate_pinned_tree
        depth = 0
        attempted = False
        attack_result: tuple[bool, int] | None = None

        def attack_after_outermost_revalidation(tree, **kwargs):
            nonlocal depth, attempted, attack_result
            depth += 1
            try:
                result = real_revalidate(tree, **kwargs)
            finally:
                depth -= 1
            if depth == 0 and not attempted:
                attempted = True
                attack_result = set_junction(preview, outside)
            return result

        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
                patch.object(
                    storage,
                    "_revalidate_pinned_tree",
                    side_effect=attack_after_outermost_revalidation,
                ),
            ):
                self.assertEqual(0, storage.canvas_usage_bytes(project_id=self.project_id))
            self.assertTrue(attempted)
            self.assertIsNotNone(attack_result)
            self.assertFalse(attack_result[0])
            self.assertIn(attack_result[1], {5, 32})
            self.assertFalse(preview.is_junction())
            self.assertEqual(b"keep", sentinel.read_bytes())
            self.assertEqual([], list(preview.iterdir()))
        finally:
            if preview.is_junction():
                preview.rmdir()
                preview.mkdir()


class CanvasAssetPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "canvas-data"
        self.db_path = Path(self.tmp.name) / "canvas-assets.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import database

        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        try:
            database.init_db()
        finally:
            database.engine, database.DATABASE_URL = original

        self.project_id = str(uuid4())
        self.other_project_id = str(uuid4())
        with self.engine.begin() as connection:
            for project_id, name in (
                (self.project_id, "Assets"),
                (self.other_project_id, "Other"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO canvas_projects "
                        "(id, name, status, semantic_state, layout_state, schema_version, revision) "
                        "VALUES (:id, :name, 'active', '{}', '{}', 1, 1)"
                    ),
                    {"id": project_id, "name": name},
                )

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _upload(self, db, *, data: bytes, filename: str, mime_type: str):
        from services.canvas import assets, storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            return assets.persist_uploaded_source(
                db,
                project_id=self.project_id,
                filename=filename,
                declared_mime=mime_type,
                data=data,
            )

    def _asset_paths(self, uploaded):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            return (
                storage.resolve_asset_path(uploaded.source, project_id=self.project_id),
                storage.resolve_asset_path(uploaded.working, project_id=self.project_id),
            )

    def _assert_asset_error(self, expected_code: str, callback) -> None:
        from services.canvas.assets import CanvasAssetPersistenceError

        with self.assertRaises(CanvasAssetPersistenceError) as raised:
            callback()
        self.assertEqual(expected_code, raised.exception.code)

    def _make_directory_link(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except OSError as symlink_error:
            if os.name != "nt":
                self.skipTest(f"directory symlinks are unavailable: {symlink_error}")
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            self.skipTest("directory symlinks and junctions are unavailable")

    @staticmethod
    def _oriented_jpeg() -> bytes:
        image = Image.new("RGB", (3, 2))
        image.putdata(
            [
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255),
                (255, 255, 0),
                (255, 0, 255),
                (0, 255, 255),
            ]
        )
        exif = Image.Exif()
        exif[274] = 6
        output = io.BytesIO()
        image.save(
            output,
            format="JPEG",
            exif=exif,
            icc_profile=b"untrusted-profile-bytes",
            quality=95,
        )
        return output.getvalue()

    def test_upload_preserves_source_bytes_and_creates_oriented_metadata_stripped_png_without_commit(self):
        from canvas_models import CanvasAsset

        data = self._oriented_jpeg()
        db = self.Session()
        commit_count = 0
        rollback_count = 0

        @event.listens_for(db, "after_commit")
        def _record_commit(_session):
            nonlocal commit_count
            if not _session.in_nested_transaction():
                commit_count += 1

        @event.listens_for(db, "after_rollback")
        def _record_rollback(_session):
            nonlocal rollback_count
            rollback_count += 1

        try:
            uploaded = self._upload(
                db,
                data=data,
                filename="oriented.jpeg",
                mime_type="image/jpeg",
            )
            self.assertEqual((0, 0), (commit_count, rollback_count))
            self.assertEqual(2, len(db.scalars(select(CanvasAsset)).all()))
            source_path, working_path = self._asset_paths(uploaded)

            self.assertEqual(data, source_path.read_bytes())
            self.assertEqual("source", uploaded.source.asset_type)
            self.assertEqual("source/" + uploaded.source.id + ".jpeg", uploaded.source.relative_path)
            self.assertEqual("oriented.jpeg", uploaded.source.original_filename)
            self.assertEqual("image/jpeg", uploaded.source.mime_type)
            self.assertEqual(len(data), uploaded.source.byte_count)
            self.assertEqual((3, 2), (uploaded.source.width, uploaded.source.height))
            self.assertEqual(hashlib.sha256(data).hexdigest(), uploaded.source.sha256)
            self.assertIsNone(uploaded.source.source_asset_id)
            self.assertEqual(
                {"format": "JPEG", "has_alpha": False},
                json.loads(uploaded.source.metadata_json),
            )

            working_bytes = working_path.read_bytes()
            self.assertEqual("working", uploaded.working.asset_type)
            self.assertEqual("working/" + uploaded.working.id + ".png", uploaded.working.relative_path)
            self.assertEqual("oriented.jpeg", uploaded.working.original_filename)
            self.assertEqual("image/png", uploaded.working.mime_type)
            self.assertEqual(len(working_bytes), uploaded.working.byte_count)
            self.assertEqual((2, 3), (uploaded.working.width, uploaded.working.height))
            self.assertEqual(hashlib.sha256(working_bytes).hexdigest(), uploaded.working.sha256)
            self.assertEqual(uploaded.source.id, uploaded.working.source_asset_id)
            self.assertEqual("canvas-working-v1", uploaded.working.processor_version)
            self.assertEqual(
                {
                    "canonical_mode": "RGB",
                    "exif_transposed": True,
                    "source_format": "JPEG",
                },
                json.loads(uploaded.working.metadata_json),
            )
            with Image.open(working_path) as working_image:
                working_image.load()
                self.assertEqual("PNG", working_image.format)
                self.assertEqual("RGB", working_image.mode)
                self.assertEqual((2, 3), working_image.size)
                self.assertNotIn("icc_profile", working_image.info)
                self.assertEqual(0, len(working_image.getexif()))

            db.rollback()
            self.assertFalse(source_path.exists())
            self.assertFalse(working_path.exists())
        finally:
            db.close()

        with self.Session() as verification:
            self.assertEqual(0, len(verification.scalars(select(CanvasAsset)).all()))

    def test_cmyk_upload_converts_to_deterministic_rgb_working_png(self):
        image = Image.new("CMYK", (4, 3), (1, 2, 3, 4))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=95)
        data = output.getvalue()
        db = self.Session()
        try:
            first = self._upload(
                db,
                data=data,
                filename="cmyk.jpg",
                mime_type="image/jpeg",
            )
            second = self._upload(
                db,
                data=data,
                filename="cmyk.jpg",
                mime_type="image/jpeg",
            )
            first_paths = self._asset_paths(first)
            second_paths = self._asset_paths(second)
            self.assertEqual(first.working.sha256, second.working.sha256)
            self.assertEqual(first_paths[1].read_bytes(), second_paths[1].read_bytes())
            with Image.open(first_paths[1]) as working_image:
                working_image.load()
                self.assertEqual("RGB", working_image.mode)
            db.rollback()
        finally:
            db.close()

    def test_caller_commit_preserves_files_and_rows_and_clears_only_the_ledger(self):
        from canvas_models import CanvasAsset

        db = self.Session()
        try:
            uploaded = self._upload(
                db,
                data=_image_bytes("PNG"),
                filename="committed.png",
                mime_type="image/png",
            )
            paths = self._asset_paths(uploaded)
            db.commit()
            self.assertTrue(all(path.is_file() for path in paths))
            self.assertFalse(db.info.get("canvas_file_rollback_ledger"))
        finally:
            db.close()

        with self.Session() as verification:
            self.assertEqual(2, len(verification.scalars(select(CanvasAsset)).all()))
        self.assertTrue(all(path.is_file() for path in paths))

    def test_parent_asset_missing_deleted_or_cross_project_is_rejected_before_filesystem_writes(self):
        from canvas_models import CanvasAsset
        from services.canvas import assets, storage

        deleted_id = str(uuid4())
        cross_project_id = str(uuid4())
        with self.Session.begin() as seed:
            seed.add_all(
                [
                    CanvasAsset(
                        id=deleted_id,
                        project_id=self.project_id,
                        asset_type="source",
                        relative_path=f"source/{deleted_id}.png",
                        original_filename="deleted.png",
                        mime_type="image/png",
                        byte_count=1,
                        width=1,
                        height=1,
                        sha256="1" * 64,
                        metadata_json="{}",
                        deleted_at=datetime.now(),
                    ),
                    CanvasAsset(
                        id=cross_project_id,
                        project_id=self.other_project_id,
                        asset_type="source",
                        relative_path=f"source/{cross_project_id}.png",
                        original_filename="other.png",
                        mime_type="image/png",
                        byte_count=1,
                        width=1,
                        height=1,
                        sha256="2" * 64,
                        metadata_json="{}",
                    ),
                ]
            )

        cases = (
            (str(uuid4()), "canvas_asset_source_not_found"),
            (deleted_id, "canvas_asset_source_deleted"),
            (cross_project_id, "canvas_asset_source_project_mismatch"),
        )
        for source_asset_id, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                db = self.Session()
                try:
                    with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                        self._assert_asset_error(
                            expected_code,
                            lambda: assets.persist_derived_image(
                                db,
                                project_id=self.project_id,
                                asset_type="preview",
                                data=_image_bytes("PNG"),
                                mime_type="image/png",
                                source_asset_id=source_asset_id,
                                metadata={},
                            ),
                        )
                    self.assertFalse(self.data_root.exists())
                finally:
                    db.rollback()
                    db.close()

    def test_second_atomic_publish_failure_rolls_back_and_cleans_only_new_files(self):
        from canvas_models import CanvasAsset
        from services.canvas import assets, storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        sentinel = root / "source" / "preexisting.txt"
        sentinel.write_bytes(b"keep")
        real_publish = storage._rename_pinned_file_no_replace
        publish_count = 0

        def fail_second_publish(file_pin, destination_parent, name):
            nonlocal publish_count
            publish_count += 1
            if publish_count == 2:
                raise OSError("simulated second publish failure")
            return real_publish(file_pin, destination_parent, name)

        db = self.Session()
        try:
            with patch.object(
                storage,
                "_rename_pinned_file_no_replace",
                side_effect=fail_second_publish,
            ):
                self._assert_asset_error(
                    "canvas_storage_atomic_write_failed",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="replace.png",
                        mime_type="image/png",
                    ),
                )
            self.assertEqual(b"keep", sentinel.read_bytes())
            self.assertEqual([], list((root / "tmp").iterdir()))
            self.assertEqual([sentinel], list((root / "source").iterdir()))
            self.assertEqual([], list((root / "working").iterdir()))
            self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
        finally:
            db.close()

    def test_flush_failure_rolls_back_rows_and_files_without_deleting_preexisting_file(self):
        from canvas_models import CanvasAsset
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        sentinel = root / "source" / "preexisting.txt"
        sentinel.write_bytes(b"keep")
        db = self.Session()
        try:
            with patch.object(db, "flush", side_effect=IntegrityError("flush", {}, Exception())):
                self._assert_asset_error(
                    "canvas_asset_database_failed",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="flush.png",
                        mime_type="image/png",
                    ),
                )
            self.assertEqual(b"keep", sentinel.read_bytes())
            self.assertEqual([], list((root / "tmp").iterdir()))
            self.assertEqual([sentinel], list((root / "source").iterdir()))
            self.assertEqual([], list((root / "working").iterdir()))
            self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
        finally:
            db.close()

    def test_uuid_collision_never_overwrites_existing_file(self):
        from canvas_models import CanvasAsset
        from services.canvas import assets, storage

        collision_id = uuid4()
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        collision = root / "source" / f"{collision_id}.png"
        collision.write_bytes(b"preexisting")
        db = self.Session()
        try:
            with patch.object(assets, "uuid4", return_value=collision_id):
                self._assert_asset_error(
                    "canvas_storage_collision",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="collision.png",
                        mime_type="image/png",
                    ),
                )
            self.assertEqual(b"preexisting", collision.read_bytes())
            self.assertEqual([], list((root / "tmp").iterdir()))
            self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
        finally:
            db.rollback()
            db.close()

    def test_atomic_writes_use_pinned_temp_flush_no_replace_publish_and_cleanup(self):
        from services.canvas import storage

        expected_identities: dict[tuple[tuple[object, object], str], tuple[object, object]] = {}
        reopened_identities: list[
            tuple[tuple[object, object], tuple[object, object]]
        ] = []
        real_publish = storage._rename_pinned_file_no_replace
        real_verifier = storage._open_published_file_verifier

        def observed_publish(file_pin, destination_parent, name):
            expected_identities[(destination_parent.identity, name)] = file_pin.identity
            return real_publish(file_pin, destination_parent, name)

        def observed_verifier(destination_parent, name):
            verifier = real_verifier(destination_parent, name)
            reopened_identities.append(
                (
                    expected_identities[(destination_parent.identity, name)],
                    verifier.identity,
                )
            )
            return verifier

        db = self.Session()
        try:
            with (
                patch.object(
                    storage,
                    "_create_pinned_file",
                    wraps=storage._create_pinned_file,
                ) as create_mock,
                patch.object(
                    storage,
                    "_flush_pinned_file",
                    wraps=storage._flush_pinned_file,
                ) as flush_mock,
                patch.object(
                    storage,
                    "_rename_pinned_file_no_replace",
                    side_effect=observed_publish,
                ) as publish_mock,
                patch.object(
                    storage,
                    "_open_published_file_verifier",
                    side_effect=observed_verifier,
                ) as verifier_mock,
            ):
                uploaded = self._upload(
                    db,
                    data=_image_bytes("PNG"),
                    filename="atomic.png",
                    mime_type="image/png",
                )
            self.assertEqual(2, create_mock.call_count)
            self.assertEqual(2, flush_mock.call_count)
            self.assertEqual(2, publish_mock.call_count)
            self.assertEqual(2, verifier_mock.call_count)
            self.assertEqual(2, len(reopened_identities))
            self.assertTrue(
                all(expected == reopened for expected, reopened in reopened_identities)
            )
            source_path, working_path = self._asset_paths(uploaded)
            self.assertEqual([], list((source_path.parents[1] / "tmp").glob("*.uploading")))
            db.rollback()
            self.assertFalse(source_path.exists())
            self.assertFalse(working_path.exists())
        finally:
            db.close()

    def test_multiple_uploads_in_one_transaction_are_all_removed_on_root_rollback(self):
        db = self.Session()
        try:
            first = self._upload(
                db,
                data=_image_bytes("PNG", color=(1, 2, 3)),
                filename="first.png",
                mime_type="image/png",
            )
            second = self._upload(
                db,
                data=_image_bytes("PNG", color=(4, 5, 6)),
                filename="second.png",
                mime_type="image/png",
            )
            paths = (*self._asset_paths(first), *self._asset_paths(second))
            self.assertTrue(all(path.is_file() for path in paths))
            db.rollback()
            self.assertTrue(all(not path.exists() for path in paths))
        finally:
            db.close()

    def test_nested_rollback_removes_only_savepoint_files_and_nested_commit_transfers_ledger(self):
        from canvas_models import CanvasAsset

        db = self.Session()
        try:
            outer = self._upload(
                db,
                data=_image_bytes("PNG", color=(1, 1, 1)),
                filename="outer.png",
                mime_type="image/png",
            )
            outer_paths = self._asset_paths(outer)

            rolled_back_savepoint = db.begin_nested()
            rolled_back = self._upload(
                db,
                data=_image_bytes("PNG", color=(2, 2, 2)),
                filename="nested-rollback.png",
                mime_type="image/png",
            )
            rolled_back_paths = self._asset_paths(rolled_back)
            rolled_back_savepoint.rollback()
            self.assertTrue(all(path.is_file() for path in outer_paths))
            self.assertTrue(all(not path.exists() for path in rolled_back_paths))

            committed_savepoint = db.begin_nested()
            transferred = self._upload(
                db,
                data=_image_bytes("PNG", color=(3, 3, 3)),
                filename="nested-commit.png",
                mime_type="image/png",
            )
            transferred_paths = self._asset_paths(transferred)
            committed_savepoint.commit()
            self.assertTrue(all(path.is_file() for path in (*outer_paths, *transferred_paths)))

            db.commit()
            self.assertTrue(all(path.is_file() for path in (*outer_paths, *transferred_paths)))
            self.assertTrue(all(not path.exists() for path in rolled_back_paths))
        finally:
            db.close()

        with self.Session() as verification:
            self.assertEqual(4, len(verification.scalars(select(CanvasAsset)).all()))

    def test_failed_caller_commit_then_rollback_removes_pending_files(self):
        db = self.Session()
        try:
            uploaded = self._upload(
                db,
                data=_image_bytes("PNG"),
                filename="commit-fails.png",
                mime_type="image/png",
            )
            paths = self._asset_paths(uploaded)

            def fail_commit(_session):
                raise RuntimeError("simulated caller commit failure")

            event.listen(db, "before_commit", fail_commit, once=True)
            with self.assertRaisesRegex(RuntimeError, "commit failure"):
                db.commit()
            self.assertTrue(all(path.is_file() for path in paths))
            db.rollback()
            self.assertTrue(all(not path.exists() for path in paths))
        finally:
            db.close()

    def test_session_close_without_explicit_rollback_removes_pending_files(self):
        db = self.Session()
        uploaded = self._upload(
            db,
            data=_image_bytes("PNG"),
            filename="close.png",
            mime_type="image/png",
        )
        paths = self._asset_paths(uploaded)
        self.assertTrue(all(path.is_file() for path in paths))
        db.close()
        self.assertTrue(all(not path.exists() for path in paths))

    def test_nested_commit_then_outer_rollback_removes_transferred_files(self):
        from canvas_models import CanvasAsset

        db = self.Session()
        try:
            nested = db.begin_nested()
            uploaded = self._upload(
                db,
                data=_image_bytes("PNG"),
                filename="nested-transfer.png",
                mime_type="image/png",
            )
            paths = self._asset_paths(uploaded)
            nested.commit()
            self.assertTrue(all(path.is_file() for path in paths))
            db.rollback()
            self.assertTrue(all(not path.exists() for path in paths))
            self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
        finally:
            db.close()

    def test_pre_materialized_legacy_sqlite_nested_transaction_fails_closed(self):
        from services.canvas import assets

        db = self.Session()
        try:
            caller_nested = db.begin_nested()
            db.execute(text("SELECT 1"))
            self.assertTrue(db.connection().in_nested_transaction())
            self._assert_asset_error(
                "canvas_asset_database_failed",
                lambda: self._upload(
                    db,
                    data=_image_bytes("PNG"),
                    filename="legacy-savepoint.png",
                    mime_type="image/png",
                ),
            )
            self.assertFalse(self.data_root.exists())
            self.assertTrue(caller_nested.is_active)
        finally:
            db.rollback()
            db.close()

    def test_destination_directory_rename_is_blocked_after_temp_flush(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")
        source_directory = root / "source"
        original_source_directory = root / "source-original"
        real_flush = storage._flush_pinned_file
        rename_attempted = False
        rename_blocked = False

        def flush_then_try_directory_rename(file_pin):
            nonlocal rename_attempted, rename_blocked
            result = real_flush(file_pin)
            if not rename_attempted:
                rename_attempted = True
                try:
                    source_directory.rename(original_source_directory)
                except OSError:
                    rename_blocked = True
                else:
                    original_source_directory.rename(source_directory)
            return result

        db = self.Session()
        try:
            with patch.object(
                storage,
                "_flush_pinned_file",
                side_effect=flush_then_try_directory_rename,
            ):
                uploaded = self._upload(
                    db,
                    data=_image_bytes("PNG"),
                    filename="rename-check.png",
                    mime_type="image/png",
                )
            paths = self._asset_paths(uploaded)
            self.assertTrue(rename_attempted)
            self.assertTrue(rename_blocked)
            self.assertEqual(b"keep", sentinel.read_bytes())
            self.assertEqual([sentinel], list(outside.iterdir()))
            self.assertEqual([], list((root / "tmp").iterdir()))
            self.assertTrue(all(path.is_file() for path in paths))
            db.rollback()
            self.assertTrue(all(not path.exists() for path in paths))
        finally:
            db.rollback()
            db.close()

    def test_committed_asset_files_survive_a_later_failed_upload(self):
        from services.canvas import storage

        first_session = self.Session()
        try:
            committed = self._upload(
                first_session,
                data=_image_bytes("PNG", color=(9, 8, 7)),
                filename="old.png",
                mime_type="image/png",
            )
            committed_paths = self._asset_paths(committed)
            committed_bytes = tuple(path.read_bytes() for path in committed_paths)
            first_session.commit()
        finally:
            first_session.close()

        real_publish = storage._rename_pinned_file_no_replace
        publish_count = 0

        def fail_second_publish(file_pin, destination_parent, name):
            nonlocal publish_count
            publish_count += 1
            if publish_count == 2:
                raise OSError("simulated later upload failure")
            return real_publish(file_pin, destination_parent, name)

        second_session = self.Session()
        try:
            with patch.object(
                storage,
                "_rename_pinned_file_no_replace",
                side_effect=fail_second_publish,
            ):
                self._assert_asset_error(
                    "canvas_storage_atomic_write_failed",
                    lambda: self._upload(
                        second_session,
                        data=_image_bytes("PNG", color=(6, 5, 4)),
                        filename="new.png",
                        mime_type="image/png",
                    ),
                )
        finally:
            second_session.close()

        self.assertEqual(committed_bytes, tuple(path.read_bytes() for path in committed_paths))

    def test_persist_derived_png_flushes_metadata_and_rolls_back_only_derived_file(self):
        from canvas_models import CanvasAsset
        from services.canvas import assets, storage

        source_session = self.Session()
        try:
            uploaded = self._upload(
                source_session,
                data=_image_bytes("PNG"),
                filename="parent.png",
                mime_type="image/png",
            )
            source_paths = self._asset_paths(uploaded)
            source_session.commit()
        finally:
            source_session.close()

        derived_data = _image_bytes("PNG", mode="RGBA", color=(1, 2, 3, 128))
        db = self.Session()
        commit_count = 0

        @event.listens_for(db, "after_commit")
        def _record_commit(_session):
            nonlocal commit_count
            if not _session.in_nested_transaction():
                commit_count += 1

        try:
            with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                derived = assets.persist_derived_image(
                    db,
                    project_id=self.project_id,
                    asset_type="preview",
                    data=derived_data,
                    mime_type="image/png",
                    source_asset_id=uploaded.source.id,
                    metadata={"purpose": "test", "version": 1},
                )
                derived_path = storage.resolve_asset_path(
                    derived,
                    project_id=self.project_id,
                )
            self.assertEqual(0, commit_count)
            self.assertEqual("preview", derived.asset_type)
            self.assertEqual(f"preview/{derived.id}.png", derived.relative_path)
            self.assertEqual("image/png", derived.mime_type)
            self.assertEqual(uploaded.source.id, derived.source_asset_id)
            self.assertEqual({"purpose": "test", "version": 1}, json.loads(derived.metadata_json))
            self.assertEqual(hashlib.sha256(derived_data).hexdigest(), derived.sha256)
            self.assertEqual((3, 2), (derived.width, derived.height))
            self.assertEqual(derived_data, derived_path.read_bytes())
            self.assertIn(derived, db.scalars(select(CanvasAsset)).all())
            db.rollback()
            self.assertFalse(derived_path.exists())
            self.assertTrue(all(path.is_file() for path in source_paths))
        finally:
            db.close()

    def test_persist_derived_rejects_source_unknown_type_non_png_and_mime_data_mismatch(self):
        from services.canvas import assets, storage

        cases = (
            (
                "source",
                _image_bytes("PNG"),
                "image/png",
                "canvas_asset_type_invalid",
            ),
            (
                "thumbnail",
                _image_bytes("PNG"),
                "image/png",
                "canvas_asset_type_invalid",
            ),
            (
                "preview",
                _image_bytes("JPEG"),
                "image/jpeg",
                "canvas_asset_derived_format_invalid",
            ),
            (
                "preview",
                _image_bytes("JPEG"),
                "image/png",
                "canvas_image_signature_mismatch",
            ),
        )
        for asset_type, data, mime_type, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                db = self.Session()
                try:
                    with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                        self._assert_asset_error(
                            expected_code,
                            lambda: assets.persist_derived_image(
                                db,
                                project_id=self.project_id,
                                asset_type=asset_type,
                                data=data,
                                mime_type=mime_type,
                                source_asset_id=None,
                                metadata={},
                            ),
                        )
                    self.assertFalse(self.data_root.exists())
                finally:
                    db.rollback()
                    db.close()

    def test_project_lookup_failure_is_stable_and_happens_before_filesystem_writes(self):
        db = self.Session()
        try:
            with patch.object(
                db,
                "execute",
                side_effect=RuntimeError(f"database detail {self.db_path}"),
            ):
                self._assert_asset_error(
                    "canvas_asset_database_failed",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="db-error.png",
                        mime_type="image/png",
                    ),
                )
            self.assertFalse(self.data_root.exists())
        finally:
            db.rollback()
            db.close()

    def test_inactive_projects_are_rejected_before_filesystem_writes(self):
        from services.canvas import storage

        for status in ("archived", "deleting"):
            with self.subTest(status=status):
                with self.engine.begin() as connection:
                    connection.execute(
                        text("UPDATE canvas_projects SET status = :status WHERE id = :id"),
                        {"status": status, "id": self.project_id},
                    )
                db = self.Session()
                try:
                    self._assert_asset_error(
                        "canvas_asset_project_inactive",
                        lambda: self._upload(
                            db,
                            data=_image_bytes("PNG"),
                            filename="inactive.png",
                            mime_type="image/png",
                        ),
                    )
                    self.assertFalse(self.data_root.exists())
                finally:
                    db.rollback()
                    db.close()
                with self.engine.begin() as connection:
                    connection.execute(
                        text("UPDATE canvas_projects SET status = 'active' WHERE id = :id"),
                        {"id": self.project_id},
                    )

    def test_original_filename_is_cross_platform_basename_and_rejects_oversize_or_nul(self):
        filenames = (
            r"C:\private\customer\photo.png",
            "/private/customer/photo.png",
        )
        for filename in filenames:
            with self.subTest(filename=filename):
                db = self.Session()
                try:
                    uploaded = self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename=filename,
                        mime_type="image/png",
                    )
                    self.assertEqual("photo.png", uploaded.source.original_filename)
                    self.assertEqual("photo.png", uploaded.working.original_filename)
                    db.rollback()
                finally:
                    db.close()

        for filename in ("a" * 500 + ".png", "nul\x00name.png"):
            with self.subTest(rejected=repr(filename)):
                db = self.Session()
                try:
                    self._assert_asset_error(
                        "canvas_asset_filename_invalid",
                        lambda filename=filename: self._upload(
                            db,
                            data=_image_bytes("PNG"),
                            filename=filename,
                            mime_type="image/png",
                        ),
                    )
                finally:
                    db.rollback()
                    db.close()

    def test_working_and_trusted_derived_pngs_can_exceed_upload_byte_limit_under_quota(self):
        from services.canvas import assets, storage

        large_png = _padded_png_over_upload_limit()
        upload_session = self.Session()
        try:
            with patch.object(
                assets,
                "_canonical_working_png",
                return_value=(large_png, "RGB", False),
            ):
                uploaded = self._upload(
                    upload_session,
                    data=_image_bytes("PNG"),
                    filename="small-source.png",
                    mime_type="image/png",
                )
            _, working_path = self._asset_paths(uploaded)
            self.assertGreater(uploaded.working.byte_count, 12_582_912)
            self.assertEqual(large_png, working_path.read_bytes())
            upload_session.rollback()
        finally:
            upload_session.close()

        derived_session = self.Session()
        try:
            with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                derived = assets.persist_derived_image(
                    derived_session,
                    project_id=self.project_id,
                    asset_type="generated_background",
                    data=large_png,
                    mime_type="image/png",
                    source_asset_id=None,
                    metadata={},
                )
                derived_path = storage.resolve_asset_path(
                    derived,
                    project_id=self.project_id,
                )
            self.assertGreater(derived.byte_count, 12_582_912)
            self.assertEqual(large_png, derived_path.read_bytes())
            derived_session.rollback()
            self.assertFalse(derived_path.exists())
        finally:
            derived_session.close()

    def test_concurrent_uploads_serialize_capacity_and_allocation_so_only_one_fits_quota(self):
        from services.canvas import assets, storage

        source_data = _image_bytes("PNG", size=(8, 8))
        _inspected, loaded_source = assets._inspect_upload_with_loaded_pixels(
            source_data,
            filename="quota.png",
            declared_mime="image/png",
        )
        working_data, _mode, _transposed = assets._canonical_working_png(loaded_source)
        one_upload_bytes = len(source_data) + len(working_data)
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            storage.ensure_project_tree(self.project_id)

        start = threading.Barrier(2)
        state_lock = threading.Lock()
        second_atomic_entered = threading.Event()
        active_atomic_writes = 0
        max_active_atomic_writes = 0
        first_waiter_claimed = False
        real_atomic_write = assets._atomic_write

        def observed_atomic_write(**kwargs):
            nonlocal active_atomic_writes, max_active_atomic_writes, first_waiter_claimed
            with state_lock:
                active_atomic_writes += 1
                max_active_atomic_writes = max(
                    max_active_atomic_writes,
                    active_atomic_writes,
                )
                should_wait = not first_waiter_claimed
                if should_wait:
                    first_waiter_claimed = True
                else:
                    second_atomic_entered.set()
            if should_wait:
                second_atomic_entered.wait(timeout=0.25)
            try:
                return real_atomic_write(**kwargs)
            finally:
                with state_lock:
                    active_atomic_writes -= 1

        def run_upload(index: int) -> str:
            db = self.Session()
            try:
                start.wait(timeout=5)
                assets.persist_uploaded_source(
                    db,
                    project_id=self.project_id,
                    filename=f"concurrent-{index}.png",
                    declared_mime="image/png",
                    data=source_data,
                )
                db.commit()
                return "success"
            except assets.CanvasAssetPersistenceError as exc:
                db.rollback()
                return exc.code
            finally:
                db.close()

        with (
            patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
            patch.object(storage, "CANVAS_PROJECT_QUOTA_BYTES", one_upload_bytes),
            patch.object(storage, "CANVAS_TOTAL_QUOTA_BYTES", one_upload_bytes * 10),
            patch.object(storage, "CANVAS_MIN_FREE_BYTES", 0),
            patch.object(assets, "_atomic_write", side_effect=observed_atomic_write),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            results = sorted(executor.map(run_upload, range(2)))
            usage = storage.canvas_usage_bytes(project_id=self.project_id)

        self.assertEqual(
            ["canvas_storage_project_quota_exceeded", "success"],
            results,
        )
        self.assertEqual(1, max_active_atomic_writes)
        self.assertLessEqual(usage, one_upload_bytes)

    def test_project_and_parent_lookups_refresh_stale_identity_map_state(self):
        from canvas_models import CanvasAsset, CanvasProject
        from services.canvas import assets, storage

        project_session = self.Session()
        try:
            cached_project = project_session.get(CanvasProject, self.project_id)
            self.assertEqual("active", cached_project.status)
            with self.engine.begin() as connection:
                connection.execute(
                    text("UPDATE canvas_projects SET status = 'archived' WHERE id = :id"),
                    {"id": self.project_id},
                )
            self._assert_asset_error(
                "canvas_asset_project_inactive",
                lambda: self._upload(
                    project_session,
                    data=_image_bytes("PNG"),
                    filename="stale-project.png",
                    mime_type="image/png",
                ),
            )
            self.assertFalse(self.data_root.exists())
        finally:
            project_session.rollback()
            project_session.close()

        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE canvas_projects SET status = 'active' WHERE id = :id"),
                {"id": self.project_id},
            )

        cases = (
            ("deleted", "canvas_asset_source_deleted"),
            ("cross-project", "canvas_asset_source_project_mismatch"),
        )
        for mutation, expected_code in cases:
            with self.subTest(mutation=mutation):
                parent_id = str(uuid4())
                with self.Session.begin() as seed:
                    seed.add(
                        CanvasAsset(
                            id=parent_id,
                            project_id=self.project_id,
                            asset_type="source",
                            relative_path=f"source/{parent_id}.png",
                            original_filename="parent.png",
                            mime_type="image/png",
                            byte_count=1,
                            width=1,
                            height=1,
                            sha256="3" * 64,
                            metadata_json="{}",
                        )
                    )

                parent_session = self.Session()
                try:
                    cached_parent = parent_session.get(CanvasAsset, parent_id)
                    self.assertIsNone(cached_parent.deleted_at)
                    self.assertEqual(self.project_id, cached_parent.project_id)
                    with self.engine.begin() as connection:
                        if mutation == "deleted":
                            connection.execute(
                                text(
                                    "UPDATE canvas_assets SET deleted_at = :deleted_at "
                                    "WHERE id = :id"
                                ),
                                {"deleted_at": datetime.now(), "id": parent_id},
                            )
                        else:
                            connection.execute(
                                text(
                                    "UPDATE canvas_assets SET project_id = :project_id "
                                    "WHERE id = :id"
                                ),
                                {
                                    "project_id": self.other_project_id,
                                    "id": parent_id,
                                },
                            )
                    with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                        self._assert_asset_error(
                            expected_code,
                            lambda: assets.persist_derived_image(
                                parent_session,
                                project_id=self.project_id,
                                asset_type="preview",
                                data=_image_bytes("PNG"),
                                mime_type="image/png",
                                source_asset_id=parent_id,
                                metadata={},
                            ),
                        )
                    self.assertFalse(self.data_root.exists())
                finally:
                    parent_session.rollback()
                    parent_session.close()

    def test_rollback_does_not_delete_a_competitor_that_replaced_an_owned_file(self):
        db = self.Session()
        try:
            uploaded = self._upload(
                db,
                data=_image_bytes("PNG"),
                filename="owned.png",
                mime_type="image/png",
            )
            source_path, working_path = self._asset_paths(uploaded)
            competitor = source_path.with_name("competitor.tmp")
            competitor.write_bytes(b"competitor")
            os.replace(competitor, source_path)

            db.rollback()

            self.assertEqual(b"competitor", source_path.read_bytes())
            self.assertFalse(working_path.exists())
        finally:
            db.close()

    def test_delayed_cleanup_preserves_same_identity_file_after_content_change(self):
        from canvas_models import CanvasAsset

        cases = ("same-size", "different-size")
        for change_kind in cases:
            with self.subTest(change_kind=change_kind):
                db = self.Session()
                try:
                    uploaded = self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename=f"changed-{change_kind}.png",
                        mime_type="image/png",
                    )
                    source_path, working_path = self._asset_paths(uploaded)
                    original = source_path.read_bytes()
                    changed = (
                        bytes([original[0] ^ 0x01]) + original[1:]
                        if change_kind == "same-size"
                        else original + b"changed"
                    )
                    source_path.write_bytes(changed)

                    db.rollback()

                    self.assertEqual(changed, source_path.read_bytes())
                    self.assertFalse(working_path.exists())
                    self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
                    self.assertFalse(db.info.get("canvas_file_cleanup_retry"))
                    source_path.unlink()
                finally:
                    db.close()

    def test_atomic_publish_fails_closed_if_a_competitor_wins_the_final_name(self):
        from services.canvas import storage

        real_publish = storage._rename_pinned_file_no_replace
        competitor_paths: list[Path] = []

        def publish_after_competitor(file_pin, destination_parent, name):
            competitor_pin = storage._create_pinned_file(destination_parent, name)
            try:
                storage._write_pinned_file(competitor_pin, b"competitor")
                storage._flush_pinned_file(competitor_pin)
            finally:
                competitor_pin.close()
            competitor_paths.append(destination_parent.path / name)
            return real_publish(file_pin, destination_parent, name)

        db = self.Session()
        try:
            with patch.object(
                storage,
                "_rename_pinned_file_no_replace",
                side_effect=publish_after_competitor,
            ):
                self._assert_asset_error(
                    "canvas_storage_collision",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="publication-race.png",
                        mime_type="image/png",
                    ),
                )
            self.assertEqual(1, len(competitor_paths))
            self.assertEqual(b"competitor", competitor_paths[0].read_bytes())
        finally:
            db.rollback()
            db.close()

    def test_preflush_failure_preserves_unrelated_caller_transaction_work(self):
        from canvas_models import CanvasAsset, CanvasProject
        from services.canvas import storage

        marker_id = str(uuid4())
        marker = CanvasProject(
            id=marker_id,
            name="Caller marker",
            status="active",
            semantic_state="{}",
            layout_state="{}",
            schema_version=1,
            revision=1,
        )
        db = self.Session()
        try:
            db.add(marker)
            db.flush()
            with patch.object(
                storage,
                "assert_canvas_capacity",
                side_effect=storage.CanvasStorageError(
                    "canvas_storage_project_quota_exceeded",
                    "quota exceeded",
                ),
            ):
                self._assert_asset_error(
                    "canvas_storage_project_quota_exceeded",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="preserve-caller.png",
                        mime_type="image/png",
                    ),
                )
            self.assertTrue(db.in_transaction())
            self.assertIs(marker, db.get(CanvasProject, marker_id))
            self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
            db.commit()
        finally:
            db.close()

        with self.Session() as verification:
            self.assertIsNotNone(verification.get(CanvasProject, marker_id))
            self.assertEqual(0, len(verification.scalars(select(CanvasAsset)).all()))

    def test_unexpected_working_transform_exception_is_sanitized(self):
        from services.canvas import assets

        private_detail = f"private {self.data_root}"
        db = self.Session()
        try:
            with patch.object(
                assets.ImageOps,
                "exif_transpose",
                side_effect=RuntimeError(private_detail),
            ):
                with self.assertRaises(assets.CanvasAssetPersistenceError) as raised:
                    self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="transform.png",
                        mime_type="image/png",
                    )
            self.assertEqual("canvas_image_decode_failed", raised.exception.code)
            self.assertNotIn(private_detail, str(raised.exception))
            self.assertFalse(self.data_root.exists())
        finally:
            db.rollback()
            db.close()

    def test_upload_opens_source_only_for_verify_and_one_full_decode(self):
        from services.canvas import assets

        source_data = _image_bytes("JPEG", size=(7, 5))
        real_open = Image.open
        source_open_count = 0

        def observed_open(file, *args, **kwargs):
            nonlocal source_open_count
            if isinstance(file, io.BytesIO) and file.getvalue() == source_data:
                source_open_count += 1
            return real_open(file, *args, **kwargs)

        db = self.Session()
        try:
            with patch.object(assets.Image, "open", side_effect=observed_open):
                self._upload(
                    db,
                    data=source_data,
                    filename="single-decode.jpg",
                    mime_type="image/jpeg",
                )
            self.assertEqual(2, source_open_count)
            db.rollback()
        finally:
            db.close()

    def test_ledger_hooks_run_before_raising_commit_and_transaction_end_listeners(self):
        from canvas_models import CanvasAsset
        from services.canvas import assets

        commit_session = self.Session()

        def fail_root_after_commit(session):
            if session.in_nested_transaction():
                return
            raise RuntimeError("earlier after_commit listener failed")

        event.listen(commit_session, "after_commit", fail_root_after_commit)
        try:
            uploaded = self._upload(
                commit_session,
                data=_image_bytes("PNG"),
                filename="commit-listener.png",
                mime_type="image/png",
            )
            committed_paths = self._asset_paths(uploaded)
            with self.assertRaisesRegex(RuntimeError, "after_commit listener"):
                commit_session.commit()
        finally:
            commit_session.close()

        with self.Session() as verification:
            self.assertEqual(2, len(verification.scalars(select(CanvasAsset)).all()))
        self.assertTrue(all(path.is_file() for path in committed_paths))

        savepoint_rollback_session = self.Session()

        def fail_every_after_commit(_session):
            raise RuntimeError("savepoint after_commit listener failed")

        event.listen(
            savepoint_rollback_session,
            "after_commit",
            fail_every_after_commit,
        )
        try:
            with self.assertRaises(assets.CanvasAssetPersistenceError) as raised:
                self._upload(
                    savepoint_rollback_session,
                    data=_image_bytes("PNG"),
                    filename="savepoint-listener-rollback.png",
                    mime_type="image/png",
                )
            self.assertEqual("canvas_asset_database_failed", raised.exception.code)
            savepoint_paths = tuple(
                path
                for path in self.data_root.rglob("*.png")
                if path not in committed_paths
            )
            self.assertEqual(2, len(savepoint_paths))
            savepoint_rollback_session.rollback()
            self.assertTrue(all(not path.exists() for path in savepoint_paths))
        finally:
            savepoint_rollback_session.close()

        rollback_session = self.Session()
        transaction_end_failure_armed = False

        def fail_after_transaction_end(_session, _transaction):
            if transaction_end_failure_armed:
                raise RuntimeError("earlier after_transaction_end listener failed")

        event.listen(
            rollback_session,
            "after_transaction_end",
            fail_after_transaction_end,
        )
        try:
            uploaded = self._upload(
                rollback_session,
                data=_image_bytes("PNG"),
                filename="rollback-listener.png",
                mime_type="image/png",
            )
            rolled_back_paths = self._asset_paths(uploaded)
            transaction_end_failure_armed = True
            with self.assertRaisesRegex(RuntimeError, "after_transaction_end listener"):
                rollback_session.rollback()
        finally:
            rollback_session.close()
        self.assertTrue(all(not path.exists() for path in rolled_back_paths))

    def test_transient_cleanup_failure_is_retried_without_losing_ledger_ownership(self):
        from services.canvas import assets

        db = self.Session()
        try:
            uploaded = self._upload(
                db,
                data=_image_bytes("PNG"),
                filename="retry-cleanup.png",
                mime_type="image/png",
            )
            paths = self._asset_paths(uploaded)
            denied_path = paths[0]
            real_delete_owned_file = assets._delete_owned_file
            failure_count = 0

            def transient_cleanup(owned_file):
                nonlocal failure_count
                if owned_file.path == denied_path:
                    failure_count += 1
                    raise PermissionError("transient cleanup denial")
                return real_delete_owned_file(owned_file)

            with patch.object(
                assets,
                "_delete_owned_file",
                side_effect=transient_cleanup,
            ):
                db.rollback()

            self.assertGreaterEqual(failure_count, 1)
            self.assertTrue(denied_path.is_file())
            self.assertTrue(db.info.get("canvas_file_cleanup_retry"))

            self.assertEqual(0, assets.retry_pending_file_cleanup(db))
            self.assertFalse(denied_path.exists())
            self.assertTrue(all(not path.exists() for path in paths))
            self.assertFalse(db.info.get("canvas_file_rollback_ledger"))
            self.assertFalse(db.info.get("canvas_file_cleanup_retry"))
        finally:
            db.close()

    def test_cleanup_read_failure_remains_owned_for_explicit_retry(self):
        from services.canvas import assets

        db = self.Session()
        try:
            uploaded = self._upload(
                db,
                data=_image_bytes("PNG"),
                filename="retry-read.png",
                mime_type="image/png",
            )
            paths = self._asset_paths(uploaded)
            denied_path = paths[0]
            real_delete_owned_file = assets._delete_owned_file

            def denied_cleanup(owned_file):
                if owned_file.path == denied_path:
                    raise PermissionError("transient cleanup read denial")
                return real_delete_owned_file(owned_file)

            with patch.object(
                assets,
                "_delete_owned_file",
                side_effect=denied_cleanup,
            ):
                db.rollback()

            self.assertTrue(denied_path.is_file())
            self.assertTrue(db.info.get("canvas_file_cleanup_retry"))
            self.assertEqual(0, assets.retry_pending_file_cleanup(db))
            self.assertFalse(denied_path.exists())
        finally:
            db.close()

    def test_real_flush_integrity_failure_rolls_back_only_internal_savepoint(self):
        from canvas_models import CanvasAsset, CanvasProject
        from services.canvas import assets

        collision_uuid = uuid4()
        working_uuid = uuid4()
        marker_id = str(uuid4())
        with self.Session.begin() as seed:
            seed.add(
                CanvasAsset(
                    id=str(collision_uuid),
                    project_id=self.other_project_id,
                    asset_type="source",
                    relative_path=f"source/{collision_uuid}.png",
                    original_filename="collision.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1,
                    height=1,
                    sha256="4" * 64,
                    metadata_json="{}",
                )
            )

        marker = CanvasProject(
            id=marker_id,
            name="Flush marker",
            status="active",
            semantic_state="{}",
            layout_state="{}",
            schema_version=1,
            revision=1,
        )
        db = self.Session()
        try:
            db.add(marker)
            db.flush()
            with patch.object(
                assets,
                "uuid4",
                side_effect=(collision_uuid, working_uuid),
            ):
                self._assert_asset_error(
                    "canvas_asset_database_failed",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="real-integrity.png",
                        mime_type="image/png",
                    ),
                )

            self.assertTrue(db.in_transaction())
            self.assertFalse(db.in_nested_transaction())
            self.assertIs(marker, db.get(CanvasProject, marker_id))
            self.assertEqual([], [path for path in self.data_root.rglob("*") if path.is_file()])
            db.commit()
        finally:
            if db.in_transaction():
                db.rollback()
            db.close()

        with self.Session() as verification:
            self.assertIsNotNone(verification.get(CanvasProject, marker_id))
            project_assets = verification.scalars(
                select(CanvasAsset).where(CanvasAsset.project_id == self.project_id)
            ).all()
            self.assertEqual([], project_assets)
            self.assertIsNotNone(verification.get(CanvasAsset, str(collision_uuid)))

    def test_same_session_dirty_project_and_parent_guards_are_not_clobbered(self):
        from canvas_models import CanvasAsset, CanvasProject
        from services.canvas import assets, storage

        project_session = self.Session()
        try:
            project = project_session.get(CanvasProject, self.project_id)
            project.status = "archived"
            self.assertTrue(inspect(project).attrs.status.history.has_changes())
            self._assert_asset_error(
                "canvas_asset_project_inactive",
                lambda: self._upload(
                    project_session,
                    data=_image_bytes("PNG"),
                    filename="local-archive.png",
                    mime_type="image/png",
                ),
            )
            self.assertEqual("archived", project.status)
            self.assertTrue(inspect(project).attrs.status.history.has_changes())
            self.assertIn(project, project_session.dirty)
            self.assertFalse(self.data_root.exists())
        finally:
            project_session.rollback()
            project_session.close()

        source_session = self.Session()
        try:
            uploaded = self._upload(
                source_session,
                data=_image_bytes("PNG"),
                filename="dirty-parent.png",
                mime_type="image/png",
            )
            source_session.commit()
        finally:
            source_session.close()
        before_files = {path for path in self.data_root.rglob("*") if path.is_file()}

        parent_session = self.Session()
        try:
            parent = parent_session.get(CanvasAsset, uploaded.source.id)
            local_deleted_at = datetime.now()
            parent.deleted_at = local_deleted_at
            self.assertTrue(inspect(parent).attrs.deleted_at.history.has_changes())
            with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                self._assert_asset_error(
                    "canvas_asset_source_deleted",
                    lambda: assets.persist_derived_image(
                        parent_session,
                        project_id=self.project_id,
                        asset_type="preview",
                        data=_image_bytes("PNG"),
                        mime_type="image/png",
                        source_asset_id=parent.id,
                        metadata={},
                    ),
                )
            self.assertEqual(local_deleted_at, parent.deleted_at)
            self.assertTrue(inspect(parent).attrs.deleted_at.history.has_changes())
            self.assertIn(parent, parent_session.dirty)
            self.assertEqual(
                before_files,
                {path for path in self.data_root.rglob("*") if path.is_file()},
            )
        finally:
            parent_session.rollback()
            parent_session.close()

    def test_guard_reads_share_materialized_sqlite_transaction_snapshot(self):
        from canvas_models import CanvasAsset
        from services.canvas import assets, storage

        real_materialize = assets._ensure_database_root_transaction
        project_mutated = False

        def archive_then_materialize(db):
            nonlocal project_mutated
            if not project_mutated:
                project_mutated = True
                with self.engine.begin() as connection:
                    connection.execute(
                        text("UPDATE canvas_projects SET status = 'archived' WHERE id = :id"),
                        {"id": self.project_id},
                    )
            return real_materialize(db)

        project_session = self.Session()
        try:
            with patch.object(
                assets,
                "_ensure_database_root_transaction",
                side_effect=archive_then_materialize,
            ):
                self._assert_asset_error(
                    "canvas_asset_project_inactive",
                    lambda: self._upload(
                        project_session,
                        data=_image_bytes("PNG"),
                        filename="guard-race.png",
                        mime_type="image/png",
                    ),
                )
            project_session.rollback()
        finally:
            project_session.close()
        self.assertTrue(project_mutated)
        self.assertFalse(self.data_root.exists())

        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE canvas_projects SET status = 'active' WHERE id = :id"),
                {"id": self.project_id},
            )

        source_session = self.Session()
        try:
            uploaded = self._upload(
                source_session,
                data=_image_bytes("PNG"),
                filename="parent-race.png",
                mime_type="image/png",
            )
            source_session.commit()
        finally:
            source_session.close()
        before_files = {path for path in self.data_root.rglob("*") if path.is_file()}

        parent_mutated = False

        def delete_parent_then_materialize(db):
            nonlocal parent_mutated
            if not parent_mutated:
                parent_mutated = True
                with self.engine.begin() as connection:
                    connection.execute(
                        text("UPDATE canvas_assets SET deleted_at = :value WHERE id = :id"),
                        {"value": datetime.now(), "id": uploaded.source.id},
                    )
            return real_materialize(db)

        derived_session = self.Session()
        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)),
                patch.object(
                    assets,
                    "_ensure_database_root_transaction",
                    side_effect=delete_parent_then_materialize,
                ),
            ):
                self._assert_asset_error(
                    "canvas_asset_source_deleted",
                    lambda: assets.persist_derived_image(
                        derived_session,
                        project_id=self.project_id,
                        asset_type="preview",
                        data=_image_bytes("PNG"),
                        mime_type="image/png",
                        source_asset_id=uploaded.source.id,
                        metadata={},
                    ),
                )
            derived_session.rollback()
        finally:
            derived_session.close()
        self.assertTrue(parent_mutated)
        self.assertEqual(
            before_files,
            {path for path in self.data_root.rglob("*") if path.is_file()},
        )
        with self.Session() as verification:
            self.assertEqual(
                2,
                len(
                    verification.scalars(
                        select(CanvasAsset).where(
                            CanvasAsset.project_id == self.project_id
                        )
                    ).all()
                ),
            )

    def test_rollback_cleanup_never_uses_racy_path_unlink_for_owned_final(self):
        db = self.Session()
        try:
            uploaded = self._upload(
                db,
                data=_image_bytes("PNG"),
                filename="unlink-race.png",
                mime_type="image/png",
            )
            source_path, working_path = self._asset_paths(uploaded)
            competitor = source_path.with_name("rollback-competitor.bin")
            competitor.write_bytes(b"competitor")
            real_unlink = Path.unlink
            real_replace = os.replace
            injected = False

            def racing_unlink(path, *args, **kwargs):
                nonlocal injected
                if path == source_path and not injected:
                    injected = True
                    real_replace(competitor, source_path)
                return real_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", new=racing_unlink):
                db.rollback()

            self.assertEqual(b"competitor", competitor.read_bytes())
            self.assertFalse(source_path.exists())
            self.assertFalse(working_path.exists())
        finally:
            db.close()

    def test_post_publish_hash_failure_cleans_provisional_final(self):
        from services.canvas import storage

        real_hash = storage._pinned_file_sha256
        failed_after_publish = False

        def fail_first_published_source(file_pin):
            nonlocal failed_after_publish
            if (
                not failed_after_publish
                and file_pin.parent is not None
                and file_pin.parent.path.name == "source"
                and file_pin.name is not None
                and file_pin.name.endswith(".png")
            ):
                failed_after_publish = True
                raise storage.CanvasStorageError(
                    "canvas_storage_io_failed",
                    "simulated post-publish inspection failure",
                )
            return real_hash(file_pin)

        db = self.Session()
        try:
            with patch.object(
                storage,
                "_pinned_file_sha256",
                side_effect=fail_first_published_source,
            ):
                self._assert_asset_error(
                    "canvas_storage_io_failed",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="post-link.png",
                        mime_type="image/png",
                    ),
                )
            self.assertTrue(failed_after_publish)
            self.assertEqual([], [path for path in self.data_root.rglob("*") if path.is_file()])
        finally:
            db.rollback()
            db.close()

    def test_same_length_temp_content_change_is_detected_by_publish_sha(self):
        from services.canvas import storage

        real_publish = storage._rename_pinned_file_no_replace
        content_changed = False

        def change_content_then_publish(file_pin, destination_parent, name):
            nonlocal content_changed
            if not content_changed:
                content_changed = True
                storage._write_pinned_file(file_pin, b"x" * file_pin.byte_count)
                storage._flush_pinned_file(file_pin)
            return real_publish(file_pin, destination_parent, name)

        db = self.Session()
        try:
            with patch.object(
                storage,
                "_rename_pinned_file_no_replace",
                side_effect=change_content_then_publish,
            ):
                self._assert_asset_error(
                    "canvas_storage_atomic_write_failed",
                    lambda: self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="tamper.png",
                        mime_type="image/png",
                    ),
                )
            self.assertTrue(content_changed)
            self.assertEqual([], [path for path in self.data_root.rglob("*") if path.is_file()])
        finally:
            db.rollback()
            db.close()

    def test_destination_parent_rename_is_blocked_before_atomic_publish(self):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        outside = Path(self.tmp.name) / "publish-outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")
        source_directory = root / "source"
        original_source_directory = root / "source-original"
        real_publish = storage._rename_pinned_file_no_replace
        rename_attempted = False
        rename_blocked = False

        def try_parent_rename_then_publish(file_pin, destination_parent, name):
            nonlocal rename_attempted, rename_blocked
            if not rename_attempted:
                rename_attempted = True
                try:
                    source_directory.rename(original_source_directory)
                except OSError:
                    rename_blocked = True
                else:
                    original_source_directory.rename(source_directory)
            return real_publish(file_pin, destination_parent, name)

        db = self.Session()
        try:
            with patch.object(
                storage,
                "_rename_pinned_file_no_replace",
                side_effect=try_parent_rename_then_publish,
            ):
                uploaded = self._upload(
                    db,
                    data=_image_bytes("PNG"),
                    filename="parent-rename.png",
                    mime_type="image/png",
                )
            paths = self._asset_paths(uploaded)
            self.assertTrue(rename_attempted)
            self.assertTrue(rename_blocked)
            self.assertEqual([sentinel], list(outside.iterdir()))
            self.assertEqual(b"keep", sentinel.read_bytes())
            self.assertTrue(all(path.is_file() for path in paths))
            db.rollback()
            self.assertTrue(all(not path.exists() for path in paths))
        finally:
            db.rollback()
            db.close()
            if original_source_directory.exists():
                if storage._lexists(source_directory):
                    try:
                        source_directory.rmdir()
                    except OSError:
                        pass
                original_source_directory.rename(source_directory)

    def test_native_publish_keeps_pinned_directory_identity_across_state_change(self):
        if os.name != "nt":
            self.skipTest("Windows native directory handles are required")

        import ctypes
        from ctypes import wintypes

        from canvas_models import CanvasAsset
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(self.project_id)
        outside = Path(self.tmp.name) / "state-change-outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_bytes(b"keep")
        source_directory = root / "source"
        transition_result: tuple[bool, int] | None = None
        native_publish_outcome: str | None = None
        outside_names_after_publish: list[str] | None = None

        device_io_control = storage._kernel32.DeviceIoControl
        device_io_control.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        device_io_control.restype = wintypes.BOOL

        def apply_directory_state_change(path: Path, target: Path) -> tuple[bool, int]:
            handle = storage._CreateFileW(
                str(path),
                storage._GENERIC_WRITE,
                storage._FILE_SHARE_READ
                | storage._FILE_SHARE_WRITE
                | storage._FILE_SHARE_DELETE,
                None,
                storage._OPEN_EXISTING,
                storage._FILE_FLAG_OPEN_REPARSE_POINT
                | storage._FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )
            if handle in (None, storage._INVALID_HANDLE_VALUE):
                return False, ctypes.get_last_error()
            try:
                resolved_target = str(target.resolve())
                substitute_name = ("\\??\\" + resolved_target).encode("utf-16-le")
                print_name = resolved_target.encode("utf-16-le")
                path_buffer = (
                    substitute_name
                    + b"\x00\x00"
                    + print_name
                    + b"\x00\x00"
                )
                payload = struct.pack(
                    "<IHHHHHH",
                    0xA0000003,
                    8 + len(path_buffer),
                    0,
                    0,
                    len(substitute_name),
                    len(substitute_name) + 2,
                    len(print_name),
                ) + path_buffer
                input_buffer = ctypes.create_string_buffer(payload)
                returned = wintypes.DWORD()
                ctypes.set_last_error(0)
                succeeded = bool(
                    device_io_control(
                        handle,
                        0x000900A4,
                        input_buffer,
                        len(payload),
                        None,
                        0,
                        ctypes.byref(returned),
                        None,
                    )
                )
                return succeeded, 0 if succeeded else ctypes.get_last_error()
            finally:
                storage._CloseHandle(handle)

        real_publish = storage._rename_pinned_file_no_replace

        def change_state_then_publish(file_pin, destination_parent, name):
            nonlocal transition_result
            nonlocal native_publish_outcome
            nonlocal outside_names_after_publish
            if transition_result is None and destination_parent.path == source_directory:
                transition_result = apply_directory_state_change(
                    source_directory,
                    outside,
                )
            try:
                result = real_publish(file_pin, destination_parent, name)
            except Exception as exc:
                cause = exc.__cause__
                native_publish_outcome = (
                    f"error:{getattr(exc, 'code', type(exc).__name__)}:"
                    f"winerror={getattr(cause, 'winerror', None)}"
                )
                outside_names_after_publish = sorted(
                    entry.name for entry in outside.iterdir()
                )
                raise
            if destination_parent.path == source_directory:
                native_publish_outcome = "published"
                outside_names_after_publish = sorted(
                    entry.name for entry in outside.iterdir()
                )
            return result

        db = self.Session()
        try:
            with patch.object(
                storage,
                "_rename_pinned_file_no_replace",
                side_effect=change_state_then_publish,
            ):
                with self.assertRaises(storage.CanvasStorageError) as raised:
                    self._upload(
                        db,
                        data=_image_bytes("PNG"),
                        filename="state-change.png",
                        mime_type="image/png",
                    )
            self.assertEqual((True, 0), transition_result)
            self.assertEqual(
                "error:canvas_storage_io_failed:winerror=1921",
                native_publish_outcome,
            )
            self.assertEqual(["keep.txt"], outside_names_after_publish)
            self.assertEqual(b"keep", sentinel.read_bytes())
            self.assertEqual("canvas_storage_io_failed", raised.exception.code)
            self.assertEqual([], list((root / "tmp").iterdir()))
            self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
        finally:
            db.rollback()
            db.close()
            if source_directory.is_junction():
                source_directory.rmdir()
                source_directory.mkdir()
        self.assertEqual([], list(source_directory.iterdir()))

    def test_global_cleanup_retry_survives_session_close_and_drains_from_new_session(self):
        from services.canvas import assets

        old_session = self.Session()
        uploaded = self._upload(
            old_session,
            data=_image_bytes("PNG"),
            filename="global-retry.png",
            mime_type="image/png",
        )
        source_path, working_path = self._asset_paths(uploaded)
        competitor = source_path.with_name("global-competitor.tmp")
        competitor.write_bytes(b"competitor")
        os.replace(competitor, source_path)

        with patch.object(
            assets,
            "_delete_owned_file",
            create=True,
            side_effect=PermissionError("persistent Windows lock"),
        ):
            old_session.rollback()
            old_session.close()
        del old_session

        self.assertEqual(b"competitor", source_path.read_bytes())
        self.assertTrue(working_path.is_file())

        new_session = self.Session()
        try:
            newer = self._upload(
                new_session,
                data=_image_bytes("PNG", color=(8, 7, 6)),
                filename="drain-retry.png",
                mime_type="image/png",
            )
            self.assertFalse(working_path.exists())
            self.assertEqual(b"competitor", source_path.read_bytes())
            self.assertEqual(0, assets.retry_pending_file_cleanup(new_session))
            new_paths = self._asset_paths(newer)
            new_session.rollback()
            self.assertTrue(all(not path.exists() for path in new_paths))
        finally:
            new_session.close()
            if source_path.exists():
                source_path.unlink()

    def test_invalid_exif_orientation_is_not_reported_as_transposed(self):
        for orientation in (0, 9):
            with self.subTest(orientation=orientation):
                image = Image.new("RGB", (4, 3), (1, 2, 3))
                exif = Image.Exif()
                exif[274] = orientation
                output = io.BytesIO()
                image.save(output, format="JPEG", exif=exif)
                db = self.Session()
                try:
                    uploaded = self._upload(
                        db,
                        data=output.getvalue(),
                        filename=f"orientation-{orientation}.jpg",
                        mime_type="image/jpeg",
                    )
                    metadata = json.loads(uploaded.working.metadata_json)
                    self.assertIs(False, metadata["exif_transposed"])
                    self.assertEqual((4, 3), (uploaded.working.width, uploaded.working.height))
                    db.rollback()
                finally:
                    db.close()


class CanvasPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "canvas-data"
        self.db_path = Path(self.tmp.name) / "canvas-previews.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import database

        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        try:
            database.init_db()
        finally:
            database.engine, database.DATABASE_URL = original

        self.project_id = str(uuid4())
        self.other_project_id = str(uuid4())
        with self.engine.begin() as connection:
            for project_id, name in (
                (self.project_id, "Previews"),
                (self.other_project_id, "Other"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO canvas_projects "
                        "(id, name, status, semantic_state, layout_state, schema_version, revision) "
                        "VALUES (:id, :name, 'active', '{}', '{}', 1, 1)"
                    ),
                    {"id": project_id, "name": name},
                )

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _upload(self, db, *, project_id: str | None = None, size=(20, 10), mode="RGB", color=None):
        from services.canvas import assets, storage

        if color is None:
            color = (12, 34, 56, 120) if mode == "RGBA" else (12, 34, 56)
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            return assets.persist_uploaded_source(
                db,
                project_id=project_id or self.project_id,
                filename="preview-source.png",
                declared_mime="image/png",
                data=_image_bytes("PNG", mode=mode, size=size, color=color),
            )

    def _create_preview(self, db, source, *, project_id: str | None = None, max_edge=2048):
        from services.canvas import previews, storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            return previews.create_preview_proxy(
                db,
                project_id=project_id or self.project_id,
                source_asset=source,
                max_edge=max_edge,
            )

    def _resolve_preview(self, db, source):
        from services.canvas import previews, storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            return previews.resolve_preview_asset(db, asset=source)

    def _asset_path(self, asset):
        from services.canvas import storage

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            return storage.resolve_asset_path(asset, project_id=asset.project_id)

    def test_preview_is_deterministic_scales_without_upscale_and_preserves_alpha(self):
        from canvas_models import CanvasAsset

        db = self.Session()
        try:
            uploaded = self._upload(db, size=(3000, 1500), mode="RGBA")
            with patch.object(Path, "read_bytes", side_effect=AssertionError("path read")):
                first = self._create_preview(db, uploaded.working)
                second = self._create_preview(db, uploaded.working)

            self.assertEqual((2048, 1024), (first.width, first.height))
            self.assertEqual(first.sha256, second.sha256)
            self.assertEqual("preview-proxy-v1", first.processor_version)
            metadata = json.loads(first.metadata_json)
            self.assertEqual(
                {
                    "maxEdge": 2048,
                    "processorVersion": "preview-proxy-v1",
                    "sourceAssetId": uploaded.working.id,
                    "sourceHeight": 1500,
                    "sourceWidth": 3000,
                },
                metadata,
            )
            with Image.open(self._asset_path(first)) as proxy:
                proxy.load()
                self.assertEqual("RGBA", proxy.mode)
                self.assertEqual(120, proxy.getpixel((0, 0))[3])
                self.assertNotIn("exif", proxy.info)
                self.assertNotIn("icc_profile", proxy.info)

            small = self._upload(db, size=(31, 17)).working
            small_preview = self._create_preview(db, small)
            self.assertEqual((31, 17), (small_preview.width, small_preview.height))
            preview_paths = [self._asset_path(asset) for asset in (first, second, small_preview)]
            db.rollback()
            self.assertEqual(0, len(db.scalars(select(CanvasAsset)).all()))
            self.assertTrue(all(not path.exists() for path in preview_paths))
        finally:
            db.close()

    def test_preview_uses_lanczos_for_nonuniform_pixels(self):
        from services.canvas import assets, storage

        image = Image.new("RGB", (9, 5))
        image.putdata(
            [
                (255, 255, 255) if (x + y) % 2 else (0, 0, 0)
                for y in range(5)
                for x in range(9)
            ]
        )
        output = io.BytesIO()
        image.save(output, format="PNG")
        db = self.Session()
        try:
            with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                working = assets.persist_uploaded_source(
                    db,
                    project_id=self.project_id,
                    filename="checker.png",
                    declared_mime="image/png",
                    data=output.getvalue(),
                ).working
            preview = self._create_preview(db, working, max_edge=4)
            with Image.open(self._asset_path(working)) as source:
                source.load()
                expected = source.resize((4, 2), Image.Resampling.LANCZOS)
            try:
                with Image.open(self._asset_path(preview)) as rendered:
                    rendered.load()
                    self.assertEqual(expected.mode, rendered.mode)
                    self.assertEqual(expected.tobytes(), rendered.tobytes())
            finally:
                expected.close()
        finally:
            db.rollback()
            db.close()

    def test_preview_allows_only_live_same_project_full_render_assets(self):
        from services.canvas import assets, previews, storage

        db = self.Session()
        try:
            uploaded = self._upload(db)
            derived_data = _image_bytes("PNG", size=(20, 10))
            allowed = [uploaded.working]
            with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                for asset_type in ("cutout", "generated_background", "composed"):
                    allowed.append(
                        assets.persist_derived_image(
                            db,
                            project_id=self.project_id,
                            asset_type=asset_type,
                            data=derived_data,
                            mime_type="image/png",
                            source_asset_id=uploaded.working.id,
                            metadata={},
                        )
                    )
            for source in allowed:
                with self.subTest(asset_type=source.asset_type):
                    self.assertEqual("preview", self._create_preview(db, source).asset_type)

            disallowed = [uploaded.source, self._create_preview(db, uploaded.working)]
            with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
                disallowed.append(
                    assets.persist_derived_image(
                        db,
                        project_id=self.project_id,
                        asset_type="export",
                        data=derived_data,
                        mime_type="image/png",
                        source_asset_id=uploaded.working.id,
                        metadata={},
                    )
                )
            for source in disallowed:
                with self.subTest(rejected_type=source.asset_type):
                    with self.assertRaises(previews.CanvasPreviewError) as raised:
                        self._create_preview(db, source)
                    self.assertEqual("canvas_preview_source_invalid", raised.exception.code)

            other = self._upload(db, project_id=self.other_project_id).working
            with self.assertRaises(previews.CanvasPreviewError) as raised:
                self._create_preview(db, other)
            self.assertEqual("canvas_preview_source_not_found", raised.exception.code)

            allowed[0].deleted_at = datetime.now()
            db.flush()
            with self.assertRaises(previews.CanvasPreviewError) as raised:
                self._create_preview(db, allowed[0])
            self.assertEqual("canvas_preview_source_not_found", raised.exception.code)
        finally:
            db.rollback()
            db.close()

    def test_preview_requeries_source_validates_parameters_and_rejects_changed_bytes(self):
        from services.canvas import previews, storage

        db = self.Session()
        try:
            working = self._upload(db, size=(40, 20)).working
            tampered_view = SimpleNamespace(
                id=working.id,
                project_id=self.other_project_id,
                asset_type="source",
                deleted_at=datetime.now(),
            )
            self.assertEqual(
                "preview",
                self._create_preview(db, tampered_view, max_edge=20).asset_type,
            )

            for invalid in (True, 0, -1, 2049, 10.5):
                with self.subTest(max_edge=invalid):
                    with self.assertRaises(previews.CanvasPreviewError) as raised:
                        self._create_preview(db, working, max_edge=invalid)
                    self.assertEqual("canvas_preview_max_edge_invalid", raised.exception.code)
            self.assertEqual(2048, previews.PREVIEW_MAX_EDGE)

            source_path = self._asset_path(working)
            original = source_path.read_bytes()
            same_size = bytes([original[0] ^ 0x01]) + original[1:]
            source_path.write_bytes(same_size)
            before = sorted(self.data_root.rglob("*.png"))
            with self.assertRaises(previews.CanvasPreviewError) as raised:
                self._create_preview(db, working)
            self.assertEqual("canvas_preview_source_changed", raised.exception.code)
            self.assertEqual(before, sorted(self.data_root.rglob("*.png")))

            source_path.write_bytes(original + b"changed")
            with patch.object(
                storage,
                "_pinned_file_bytes",
                side_effect=AssertionError("size mismatch payload read"),
            ):
                with self.assertRaises(previews.CanvasPreviewError) as raised:
                    self._create_preview(db, working)
            self.assertEqual("canvas_preview_source_changed", raised.exception.code)
            source_path.write_bytes(original)
        finally:
            db.rollback()
            db.close()

    def test_resolver_requires_one_explicit_active_preview_and_never_falls_back(self):
        from services.canvas import previews, storage

        db = self.Session()
        try:
            working = self._upload(db, size=(20, 10)).working
            with self.assertRaises(previews.CanvasPreviewError) as raised:
                self._resolve_preview(db, working)
            self.assertEqual("canvas_preview_missing", raised.exception.code)

            first = self._create_preview(db, working)
            self.assertEqual(first.id, self._resolve_preview(db, working).id)
            with self.assertRaises(previews.CanvasPreviewError) as raised:
                self._resolve_preview(db, first)
            self.assertEqual("canvas_preview_source_invalid", raised.exception.code)
            second = self._create_preview(db, working)
            with self.assertRaises(previews.CanvasPreviewError) as raised:
                self._resolve_preview(db, working)
            self.assertEqual("canvas_preview_ambiguous", raised.exception.code)

            second.deleted_at = datetime.now()
            db.flush()
            self.assertEqual(first.id, self._resolve_preview(db, working).id)
            self._asset_path(first).unlink()
            with self.assertRaises(storage.CanvasStorageError) as raised:
                self._resolve_preview(db, working)
            self.assertEqual("canvas_storage_asset_missing", raised.exception.code)

            first.deleted_at = datetime.now()
            db.flush()
            with self.assertRaises(previews.CanvasPreviewError) as raised:
                self._resolve_preview(db, working)
            self.assertEqual("canvas_preview_missing", raised.exception.code)
        finally:
            db.rollback()
            db.close()


class CanvasAssetSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-assets.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        import database

        self.database = database
        self.original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"

    def tearDown(self):
        self.database.engine, self.database.DATABASE_URL = self.original
        self.engine.dispose()
        self.tmp.cleanup()

    def _insert_project(self, connection, project_id: str) -> None:
        connection.execute(
            text(
                "INSERT INTO canvas_projects "
                "(id, name, status, semantic_state, layout_state, schema_version, revision) "
                "VALUES (:id, 'Assets', 'active', '{}', '{}', 1, 1)"
            ),
            {"id": project_id},
        )

    def _insert_asset(self, connection, *, project_id: str, asset_type: str) -> None:
        asset_id = str(uuid4())
        connection.execute(
            text(
                "INSERT INTO canvas_assets "
                "(id, project_id, asset_type, relative_path, original_filename, mime_type, "
                "byte_count, width, height, sha256, transparency_status, metadata_json) "
                "VALUES (:id, :project_id, :asset_type, :path, 'asset.png', 'image/png', "
                "1, 1, 1, :sha256, 'unknown', '{}')"
            ),
            {
                "id": asset_id,
                "project_id": project_id,
                "asset_type": asset_type,
                "path": f"{asset_type}/{asset_id}.png",
                "sha256": asset_id.replace("-", "").ljust(64, "0"),
            },
        )

    def test_asset_type_constraint_is_exact_and_source_relation_is_indexed(self):
        self.database.init_db()
        schema = inspect(self.engine)
        checks = {
            check["name"]: _normalized_sql(check.get("sqltext"))
            for check in schema.get_check_constraints("canvas_assets")
        }
        expected_values = ",".join(f"'{value}'" for value in sorted(ASSET_TYPES))
        self.assertEqual(
            f"asset_typein({expected_values})",
            checks.get("ck_canvas_assets_asset_type"),
        )
        self.assertIn(
            ("source_asset_id",),
            {tuple(index["column_names"]) for index in schema.get_indexes("canvas_assets")},
        )

    def test_database_accepts_only_the_seven_asset_types(self):
        self.database.init_db()
        project_id = str(uuid4())
        with self.engine.begin() as connection:
            self._insert_project(connection, project_id)
            for asset_type in sorted(ASSET_TYPES):
                self._insert_asset(
                    connection,
                    project_id=project_id,
                    asset_type=asset_type,
                )

        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                self._insert_asset(
                    connection,
                    project_id=project_id,
                    asset_type="thumbnail",
                )

class CanvasGenerationAssetReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "generation-asset-references.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        import database

        self.database = database
        self.original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        database.init_db()

    def tearDown(self):
        self.database.engine, self.database.DATABASE_URL = self.original
        self.engine.dispose()
        self.tmp.cleanup()

    def test_generation_item_input_and_attempt_assets_are_reported_as_references(self):
        from canvas_models import (
            CanvasAsset,
            CanvasAssetOperation,
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
            CanvasGenerationItemInput,
            CanvasProject,
            ImageModelProfile,
            ImageProviderConnection,
        )
        from services.canvas import assets
        from services.canvas.project_state import empty_project_state_json

        project_id = str(uuid4())
        with self.Session.begin() as db:
            semantic_state, layout_state = empty_project_state_json()
            project = CanvasProject(
                id=project_id,
                name="Generation references",
                semantic_state=semantic_state,
                layout_state=layout_state,
            )
            provider = ImageProviderConnection(
                adapter_type="fake",
                name="Fake",
                base_url="https://provider.invalid",
                auth_type="bearer",
            )
            db.add_all([project, provider])
            db.flush()
            model = ImageModelProfile(
                provider_id=provider.id,
                model_id="fake-v1",
                display_name="Fake V1",
            )
            db.add(model)
            db.flush()
            generation = CanvasGeneration(
                project_id=project_id,
                mode="complete_set",
                project_revision=1,
                request_snapshot_json="{}",
                request_fingerprint="a" * 64,
                idempotency_key="generation-reference-test",
            )
            db.add(generation)
            db.flush()

            asset_by_role = {}
            for ordinal, role in enumerate(
                (
                    "itemBackground",
                    "itemComposed",
                    "generationInput",
                    "attemptBackground",
                    "attemptBackgroundPreview",
                    "attemptComposed",
                    "attemptComposedPreview",
                    "unreferenced",
                )
            ):
                asset = CanvasAsset(
                    project_id=project_id,
                    asset_type="source" if role in {"generationInput", "unreferenced"} else "preview",
                    relative_path=f"source/{ordinal}-{role}.png",
                    original_filename=f"{role}.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1,
                    height=1,
                    sha256=f"{ordinal:064x}",
                )
                db.add(asset)
                db.flush()
                asset_by_role[role] = asset

            item = CanvasGenerationItem(
                generation_id=generation.id,
                ordinal=0,
                output_type="main",
                board_id="board-1",
                node_id="node-1",
                board_order_snapshot=0,
                provider_id=provider.id,
                provider_config_version=1,
                model_profile_id=model.id,
                model_config_version=1,
                provider_config_snapshot_json="{}",
                model_config_snapshot_json="{}",
                prompt="background only",
                width=1024,
                height=1024,
                ratio="1:1",
                layout_hash="b" * 64,
                layout_snapshot_json="{}",
                latest_background_asset_id=asset_by_role["itemBackground"].id,
                latest_composed_asset_id=asset_by_role["itemComposed"].id,
            )
            db.add(item)
            db.flush()
            db.add(
                CanvasGenerationItemInput(
                    item_id=item.id,
                    asset_id=asset_by_role["generationInput"].id,
                    input_role="main_product",
                    ordinal=0,
                    asset_sha256=asset_by_role["generationInput"].sha256,
                )
            )
            operation = CanvasAssetOperation(
                project_id=project_id,
                operation_type="compose",
                input_asset_id=asset_by_role["attemptBackground"].id,
                idempotency_key="generation-reference-compose",
            )
            db.add(operation)
            db.flush()
            db.add(
                CanvasGenerationAttempt(
                    item_id=item.id,
                    attempt_no=1,
                    provider_id=provider.id,
                    provider_config_version=1,
                    model_profile_id=model.id,
                    model_config_version=1,
                    provider_config_snapshot_json="{}",
                    model_config_snapshot_json="{}",
                    upstream_idempotency_key="upstream-generation-reference",
                    background_asset_id=asset_by_role["attemptBackground"].id,
                    background_preview_asset_id=asset_by_role[
                        "attemptBackgroundPreview"
                    ].id,
                    composed_asset_id=asset_by_role["attemptComposed"].id,
                    composed_preview_asset_id=asset_by_role[
                        "attemptComposedPreview"
                    ].id,
                    compose_operation_id=operation.id,
                )
            )

        expected = {
            "itemBackground": {"generationItemBackground"},
            "itemComposed": {"generationItemComposed"},
            "generationInput": {"generationInput"},
            "attemptBackground": {"generationAttemptBackground"},
            "attemptBackgroundPreview": {"generationAttemptBackgroundPreview"},
            "attemptComposed": {"generationAttemptComposed"},
            "attemptComposedPreview": {"generationAttemptComposedPreview"},
            "unreferenced": set(),
        }
        with self.Session() as db:
            for role, asset in asset_by_role.items():
                with self.subTest(role=role):
                    references = assets.collect_generation_asset_references(
                        db,
                        project_id=project_id,
                        asset_id=asset.id,
                    )
                    self.assertEqual(expected[role], references)
            from routers.canvas import assets as asset_router

            input_asset = db.get(CanvasAsset, asset_by_role["generationInput"].id)
            self.assertIn("generationInput", asset_router._asset_references(db, input_asset))

        for statement, parameters in (
            (
                "DELETE FROM canvas_assets WHERE id = :id",
                {"id": asset_by_role["generationInput"].id},
            ),
            ("DELETE FROM image_model_profiles WHERE id = :id", {"id": model.id}),
            (
                "DELETE FROM image_provider_connections WHERE id = :id",
                {"id": provider.id},
            ),
        ):
            with self.subTest(restrictive_delete=statement):
                with self.assertRaises(IntegrityError):
                    with self.engine.begin() as connection:
                        connection.execute(text(statement), parameters)


if __name__ == "__main__":
    unittest.main()
