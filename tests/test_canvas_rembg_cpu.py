import importlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


MODULE_NAME = "services.canvas.rembg_cpu"


class RembgMaskerSessionTests(unittest.TestCase):
    def test_session_is_lazy_singleton_cpu_only_and_uses_controlled_model_home(self):
        spec = importlib.util.find_spec(MODULE_NAME)
        self.assertIsNotNone(spec, "services.canvas.rembg_cpu must exist")
        module = importlib.import_module(MODULE_NAME)
        masker_type = getattr(module, "RembgMasker", None)
        self.assertTrue(callable(masker_type), "RembgMasker must be defined")

        created_session = object()
        session_calls = []
        loader_calls = []

        def fake_new_session(model_name, *, providers):
            session_calls.append((model_name, providers, os.environ.get("U2NET_HOME")))
            return created_session

        def fake_remove(*_args, **_kwargs):
            raise AssertionError("remove must not run while only loading the session")

        def fake_loader():
            loader_calls.append("loaded")
            return fake_new_session, fake_remove

        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory) / "controlled model cache"
            with (
                patch.object(module, "_load_rembg_api", side_effect=fake_loader),
                patch.dict(os.environ, {"U2NET_HOME": "untrusted-existing-value"}),
            ):
                masker = masker_type(model_dir=model_dir)
                self.assertEqual([], loader_calls)
                self.assertEqual([], session_calls)

                first = masker.get_session()
                second = masker.get_session()

                self.assertIs(created_session, first)
                self.assertIs(first, second)
                self.assertEqual(["loaded"], loader_calls)
                self.assertEqual(
                    [
                        (
                            "isnet-general-use",
                            ["CPUExecutionProvider"],
                            str(model_dir.resolve()),
                        )
                    ],
                    session_calls,
                )
                self.assertTrue(model_dir.is_dir())
                self.assertEqual(
                    "untrusted-existing-value",
                    os.environ.get("U2NET_HOME"),
                    "RembgMasker must restore the process environment after session creation",
                )

    def test_session_setup_failures_expose_only_stable_recoverable_error(self):
        module = importlib.import_module(MODULE_NAME)
        error_type = getattr(module, "CanvasRembgModelUnavailable", None)
        self.assertTrue(
            isinstance(error_type, type) and issubclass(error_type, Exception),
            "CanvasRembgModelUnavailable must be defined",
        )

        def failing_loader():
            raise ImportError(r"failed at C:\private\python\rembg.py")

        def failing_new_session(_model_name, *, providers):
            self.assertEqual(["CPUExecutionProvider"], providers)
            raise OSError(r"missing C:\private\models\isnet.onnx")

        for failure_name, loader in (
            ("import", failing_loader),
            ("model", lambda: (failing_new_session, object())),
        ):
            with self.subTest(failure=failure_name), tempfile.TemporaryDirectory() as directory:
                with patch.object(module, "_load_rembg_api", side_effect=loader):
                    masker = module.RembgMasker(model_dir=Path(directory) / "models")
                    with self.assertRaises(error_type) as raised:
                        masker.get_session()

                error = raised.exception
                self.assertEqual(
                    "Background removal model is unavailable",
                    str(error),
                )
                self.assertEqual(
                    {
                        "code": "rembg_model_unavailable",
                        "message": "Background removal model is unavailable",
                        "retryable": True,
                    },
                    error.safe_error,
                )
                serialized = repr(error.safe_error).lower()
                self.assertNotIn("private", serialized)
                self.assertNotIn("onnx", serialized)


class RembgMaskerMaskTests(unittest.TestCase):
    def test_create_mask_rejects_invalid_source_type_and_mode_before_runtime_load(self):
        module = importlib.import_module(MODULE_NAME)

        with tempfile.TemporaryDirectory() as directory, patch.object(
            module,
            "_load_rembg_api",
            side_effect=AssertionError("runtime must not load for invalid input"),
        ) as loader:
            masker = module.RembgMasker(model_dir=Path(directory) / "models")
            for invalid_source, expected_type in (
                ("not-an-image", TypeError),
                (Image.new("L", (1, 1), 255), ValueError),
                (Image.new("CMYK", (1, 1)), ValueError),
            ):
                with self.subTest(source_type=type(invalid_source).__name__):
                    try:
                        masker.create_mask(invalid_source)
                    except Exception as error:
                        self.assertIsInstance(error, expected_type)
                    else:
                        self.fail("invalid rembg source must be rejected")

            loader.assert_not_called()

    def test_create_mask_uses_only_mask_output_and_does_not_mutate_source(self):
        module = importlib.import_module(MODULE_NAME)
        create_mask = getattr(module.RembgMasker, "create_mask", None)
        self.assertTrue(callable(create_mask), "RembgMasker.create_mask must be defined")

        session = object()
        source = Image.new("RGB", (2, 2))
        source.putdata([(1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12)])
        original_pixels = source.tobytes()
        expected_mask = Image.new("L", source.size)
        expected_mask.putdata([0, 64, 128, 255])
        remove_calls = []
        session_calls = []

        def fake_new_session(model_name, *, providers):
            session_calls.append((model_name, providers))
            return session

        def fake_remove(image, *, only_mask, session):
            remove_calls.append(
                {
                    "mode": image.mode,
                    "size": image.size,
                    "pixels": image.tobytes(),
                    "only_mask": only_mask,
                    "session": session,
                }
            )
            image.putpixel((0, 0), (250, 251, 252))
            return expected_mask

        with tempfile.TemporaryDirectory() as directory, patch.object(
            module,
            "_load_rembg_api",
            return_value=(fake_new_session, fake_remove),
        ):
            masker = module.RembgMasker(model_dir=Path(directory) / "models")
            first = masker.create_mask(source)
            second = masker.create_mask(source)

        self.assertEqual(original_pixels, source.tobytes())
        self.assertEqual("L", first.mode)
        self.assertEqual(source.size, first.size)
        self.assertEqual(bytes([0, 64, 128, 255]), first.tobytes())
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertIsNot(first, expected_mask)
        self.assertEqual(
            [("isnet-general-use", ["CPUExecutionProvider"])],
            session_calls,
        )
        self.assertEqual(2, len(remove_calls))
        for call in remove_calls:
            self.assertEqual("RGB", call["mode"])
            self.assertEqual((2, 2), call["size"])
            self.assertEqual(original_pixels, call["pixels"])
            self.assertIs(True, call["only_mask"])
            self.assertIs(session, call["session"])

    def test_create_mask_rejects_non_grayscale_or_mismatched_mask_output(self):
        module = importlib.import_module(MODULE_NAME)
        source = Image.new("RGBA", (2, 2), (1, 2, 3, 255))
        invalid_masks = (
            "not-a-pillow-mask",
            Image.new("RGBA", source.size, (200, 100, 50, 128)),
            Image.new("L", (1, 2), 128),
        )

        for invalid_mask in invalid_masks:
            with self.subTest(mask_type=type(invalid_mask).__name__), tempfile.TemporaryDirectory() as directory:
                with patch.object(
                    module,
                    "_load_rembg_api",
                    return_value=(
                        lambda *_args, **_kwargs: object(),
                        lambda *_args, **_kwargs: invalid_mask,
                    ),
                ):
                    masker = module.RembgMasker(model_dir=Path(directory) / "models")
                    try:
                        masker.create_mask(source)
                    except Exception as error:
                        self.assertIsInstance(error, ValueError)
                        self.assertIn("mask", str(error).lower())
                    else:
                        self.fail("invalid rembg mask output must be rejected")

    def test_remove_failure_maps_to_the_same_stable_model_error(self):
        module = importlib.import_module(MODULE_NAME)

        def failing_remove(_image, *, only_mask, session):
            self.assertIs(True, only_mask)
            self.assertIsNotNone(session)
            raise RuntimeError(r"onnx failed at C:\private\input.png")

        with tempfile.TemporaryDirectory() as directory, patch.object(
            module,
            "_load_rembg_api",
            return_value=(lambda *_args, **_kwargs: object(), failing_remove),
        ):
            masker = module.RembgMasker(model_dir=Path(directory) / "models")
            try:
                masker.create_mask(Image.new("RGB", (1, 1), (1, 2, 3)))
            except Exception as error:
                self.assertIsInstance(error, module.CanvasRembgModelUnavailable)
                raised_error = error
            else:
                self.fail("create_mask must fail when rembg inference fails")

        self.assertEqual(
            {
                "code": "rembg_model_unavailable",
                "message": "Background removal model is unavailable",
                "retryable": True,
            },
            raised_error.safe_error,
        )
        self.assertNotIn("private", str(raised_error).lower())


class SourceRgbAlphaCompositionTests(unittest.TestCase):
    def test_apply_alpha_strictly_rejects_invalid_types_modes_and_dimensions(self):
        module = importlib.import_module(MODULE_NAME)
        apply_alpha = module.apply_alpha_to_source_rgb
        valid_source = Image.new("RGB", (2, 2), (1, 2, 3))
        valid_mask = Image.new("L", (2, 2), 255)
        invalid_cases = (
            (
                "not-an-image",
                valid_mask,
                TypeError,
                "source must be a Pillow Image",
            ),
            (
                valid_source,
                "not-an-image",
                TypeError,
                "mask must be a Pillow Image",
            ),
            (
                Image.new("L", (2, 2), 255),
                valid_mask,
                ValueError,
                "source image mode must be RGB or RGBA",
            ),
            (
                valid_source,
                Image.new("RGBA", (2, 2), (0, 0, 0, 255)),
                ValueError,
                "mask mode must be L",
            ),
            (
                valid_source,
                Image.new("L", (1, 2), 255),
                ValueError,
                "mask dimensions must match the source image",
            ),
        )

        for source, mask, expected_type, expected_message in invalid_cases:
            with self.subTest(expected_message=expected_message):
                try:
                    apply_alpha(source, mask)
                except Exception as error:
                    self.assertIsInstance(error, expected_type)
                    self.assertEqual(expected_message, str(error))
                else:
                    self.fail("invalid alpha composition input must be rejected")

    def test_apply_alpha_uses_only_mask_alpha_and_preserves_every_source_rgb_byte(self):
        module = importlib.import_module(MODULE_NAME)
        apply_alpha = getattr(module, "apply_alpha_to_source_rgb", None)
        self.assertTrue(callable(apply_alpha), "apply_alpha_to_source_rgb must be defined")

        source_pixels = [
            (1, 2, 3, 0),
            (4, 5, 6, 255),
            (7, 8, 9, 10),
            (10, 11, 12, 200),
            (13, 14, 15, 128),
            (16, 17, 18, 64),
        ]
        mask_alpha = [0, 1, 127, 128, 254, 255]
        source = Image.new("RGBA", (3, 2))
        source.putdata(source_pixels)
        mask = Image.new("L", source.size)
        mask.putdata(mask_alpha)
        source_before = source.tobytes()
        mask_before = mask.tobytes()

        output = apply_alpha(source, mask)

        self.assertEqual("RGBA", output.mode)
        self.assertEqual(source.size, output.size)
        output_bytes = output.tobytes()
        output_pixels = [
            tuple(output_bytes[index : index + 4])
            for index in range(0, len(output_bytes), 4)
        ]
        self.assertEqual(
            [
                (red, green, blue, alpha)
                for (red, green, blue, _source_alpha), alpha in zip(
                    source_pixels,
                    mask_alpha,
                    strict=True,
                )
            ],
            output_pixels,
        )
        self.assertEqual(source_before, source.tobytes())
        self.assertEqual(mask_before, mask.tobytes())


class DeterministicPngTests(unittest.TestCase):
    def test_encode_deterministic_png_is_metadata_free_and_pixel_exact(self):
        module = importlib.import_module(MODULE_NAME)
        encode_png = getattr(module, "encode_deterministic_png", None)
        self.assertTrue(callable(encode_png), "encode_deterministic_png must be defined")

        image = Image.new("RGBA", (2, 1))
        image.putdata([(1, 2, 3, 0), (250, 251, 252, 255)])
        image.info["private_path"] = r"C:\private\input.png"
        same_pixels_without_metadata = image.copy()
        same_pixels_without_metadata.info.clear()

        first = encode_png(image)
        second = encode_png(image)
        metadata_free = encode_png(same_pixels_without_metadata)

        self.assertEqual(first, second)
        self.assertEqual(first, metadata_free)
        self.assertTrue(first.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertNotIn(b"private", first.lower())
        with Image.open(io.BytesIO(first)) as decoded:
            decoded.load()
            self.assertEqual("PNG", decoded.format)
            self.assertEqual("RGBA", decoded.mode)
            self.assertEqual(image.size, decoded.size)
            self.assertEqual(image.tobytes(), decoded.tobytes())


if __name__ == "__main__":
    unittest.main()
