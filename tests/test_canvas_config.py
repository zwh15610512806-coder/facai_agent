import importlib.util
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.py"

CANVAS_DEFAULTS = {
    "CANVAS_DATA_DIR": "data/canvas_projects",
    "CANVAS_MAX_UPLOAD_BYTES": 12_582_912,
    "CANVAS_MAX_IMAGE_EDGE": 16_384,
    "CANVAS_MAX_IMAGE_PIXELS": 40_000_000,
    "CANVAS_PREVIEW_MAX_EDGE": 2_048,
    "CANVAS_PROJECT_QUOTA_BYTES": 5_368_709_120,
    "CANVAS_TOTAL_QUOTA_BYTES": 21_474_836_480,
    "CANVAS_MIN_FREE_BYTES": 2_147_483_648,
    "CANVAS_REMBG_MODEL_DIR": "data/models/rembg",
    "CANVAS_REMBG_WORKERS": 1,
    "CANVAS_LOCAL_OPERATION_WORKERS": 1,
}
CANVAS_ENV_KEYS = tuple(CANVAS_DEFAULTS)
NUMERIC_CANVAS_ENV_KEYS = tuple(
    key for key, value in CANVAS_DEFAULTS.items() if isinstance(value, int)
)


def load_config(overrides=None):
    environment = os.environ.copy()
    for key in CANVAS_ENV_KEYS:
        environment.pop(key, None)
    environment.update(overrides or {})
    module_name = f"_canvas_config_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, CONFIG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load config.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, environment, clear=True), patch(
        "dotenv.load_dotenv", return_value=False
    ):
        spec.loader.exec_module(module)
    return module


class CanvasRuntimeConfigTests(unittest.TestCase):
    def test_canvas_defaults_are_exact(self):
        config = load_config()

        actual = {key: getattr(config, key, None) for key in CANVAS_DEFAULTS}

        self.assertEqual(actual, CANVAS_DEFAULTS)

    def test_canvas_environment_overrides_are_strict_and_preserve_path_strings(self):
        overrides = {
            "CANVAS_DATA_DIR": r"D:\Canvas Data\projects",
            "CANVAS_MAX_UPLOAD_BYTES": "13000000",
            "CANVAS_MAX_IMAGE_EDGE": "20000",
            "CANVAS_MAX_IMAGE_PIXELS": "50000000",
            "CANVAS_PREVIEW_MAX_EDGE": "3000",
            "CANVAS_PROJECT_QUOTA_BYTES": "6000000000",
            "CANVAS_TOTAL_QUOTA_BYTES": "24000000000",
            "CANVAS_MIN_FREE_BYTES": "3000000000",
            "CANVAS_REMBG_MODEL_DIR": "relative models/rembg",
            "CANVAS_REMBG_WORKERS": "1",
            "CANVAS_LOCAL_OPERATION_WORKERS": "3",
        }

        config = load_config(overrides)

        expected = {
            key: int(value) if key in NUMERIC_CANVAS_ENV_KEYS else value
            for key, value in overrides.items()
        }
        actual = {key: getattr(config, key, None) for key in expected}

        self.assertEqual(actual, expected)

    def test_all_numeric_canvas_settings_reject_non_positive_or_non_integer_values(self):
        for key in NUMERIC_CANVAS_ENV_KEYS:
            for invalid in ("", "0", "-1", "1.5"):
                with self.subTest(key=key, invalid=invalid):
                    with self.assertRaisesRegex(ValueError, key):
                        load_config({key: invalid})

    def test_rembg_worker_count_is_locked_to_single_threaded_processing(self):
        with self.assertRaisesRegex(ValueError, "CANVAS_REMBG_WORKERS"):
            load_config({"CANVAS_REMBG_WORKERS": "2"})

    def test_preview_edge_cannot_exceed_source_image_edge(self):
        with self.assertRaisesRegex(ValueError, "CANVAS_PREVIEW_MAX_EDGE"):
            load_config(
                {
                    "CANVAS_MAX_IMAGE_EDGE": "2048",
                    "CANVAS_PREVIEW_MAX_EDGE": "2049",
                }
            )

    def test_project_quota_cannot_exceed_total_quota(self):
        with self.assertRaisesRegex(ValueError, "CANVAS_PROJECT_QUOTA_BYTES"):
            load_config(
                {
                    "CANVAS_PROJECT_QUOTA_BYTES": "200",
                    "CANVAS_TOTAL_QUOTA_BYTES": "199",
                }
            )


class CanvasRuntimePackagingTests(unittest.TestCase):
    def test_cpu_image_runtime_dependencies_are_pinned_exactly_once(self):
        lines = [
            line.strip()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        expected = [
            "Pillow==12.3.0",
            "onnxruntime==1.27.0",
            "rembg[cpu]==2.0.76",
        ]

        image_runtime_lines = [
            line
            for line in lines
            if line.split("==", 1)[0].lower() in {"pillow", "onnxruntime", "rembg[cpu]"}
        ]

        self.assertEqual(image_runtime_lines, expected)

    def test_example_environment_documents_exact_canvas_defaults(self):
        lines = set((ROOT / ".env.example").read_text(encoding="utf-8").splitlines())

        for key, value in CANVAS_DEFAULTS.items():
            with self.subTest(key=key):
                self.assertIn(f"{key}={value}", lines)

    def test_runtime_data_is_ignored_but_canvas_build_assets_are_not(self):
        ignored_paths = [
            "data/canvas_projects/project/source/image.png",
            "data/canvas_projects/project/.uploading/image.tmp",
            "data/canvas_projects/project/tmp/compose.tmp",
            "data/canvas_projects/project/exports/final.png",
            "data/models/rembg/isnet-general-use.onnx",
        ]
        for path in ignored_paths:
            with self.subTest(path=path):
                result = subprocess.run(
                    ["git", "check-ignore", "--no-index", "--quiet", path],
                    cwd=ROOT,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, f"{path} should be ignored")

        tracked_result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", "static/canvas/canvas.js"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(tracked_result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
