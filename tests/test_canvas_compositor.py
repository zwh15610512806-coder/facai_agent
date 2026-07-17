from __future__ import annotations

import hashlib
import io
import json
import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch


EXPECTED_FONT_DIGEST = "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
EXPECTED_LICENSE_DIGEST = "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2"


def _text_snapshot(**patch):
    value = {
        "id": "text-1",
        "nodeId": "node-1",
        "content": "显式第一行\n显式第二行",
        "fontAssetId": None,
        "fontFamily": "Noto Sans CJK SC",
        "fontVersion": f"sha256:{EXPECTED_FONT_DIGEST}",
        "boxWidth": 320.0,
        "lines": [
            {"text": "显式第一行", "x": 20.0, "y": 40.0, "width": 120.0},
            {"text": "显式第二行", "x": 20.0, "y": 80.0, "width": 120.0},
        ],
        "fontSize": 24,
        "color": "#112233",
        "letterSpacing": 1.0,
        "lineHeight": 1.5,
        "align": "left",
        "baseline": "alphabetic",
        "zBand": "above-product",
        "sortOrder": 3,
    }
    value.update(patch)
    return value


class CanvasFontResourceTests(unittest.TestCase):
    def test_vendored_font_and_license_match_the_locked_official_resources(self):
        from services.canvas.font_resource import BUILT_FONT_PATH, FONT_RESOURCE_VERSION

        source_root = Path(__file__).resolve().parents[1] / "frontend" / "canvas" / "public" / "fonts"
        source_font = source_root / "NotoSansCJKsc-Regular.otf"
        source_license = source_root / "OFL.txt"
        self.assertEqual(16_437_364, source_font.stat().st_size)
        self.assertEqual(EXPECTED_FONT_DIGEST, hashlib.sha256(source_font.read_bytes()).hexdigest())
        canonical_license = source_license.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(4_301, len(canonical_license))
        self.assertEqual(EXPECTED_LICENSE_DIGEST, hashlib.sha256(canonical_license).hexdigest())
        self.assertEqual(f"sha256:{EXPECTED_FONT_DIGEST}", FONT_RESOURCE_VERSION)
        self.assertEqual(source_font.read_bytes(), BUILT_FONT_PATH.read_bytes())

    def test_font_digest_is_checked_before_rendering(self):
        from services.canvas.font_resource import CanvasFontResourceError, verify_font_resource

        with tempfile.TemporaryDirectory() as temporary:
            wrong_font = Path(temporary) / "font.otf"
            wrong_font.write_bytes(b"not-the-locked-font")
            with self.assertRaises(CanvasFontResourceError):
                verify_font_resource(wrong_font, f"sha256:{EXPECTED_FONT_DIGEST}")


class CanvasTextSnapshotContractTests(unittest.TestCase):
    def test_text_snapshot_persists_explicit_lines_metrics_color_baseline_and_z_band(self):
        from services.canvas.schemas import TextSnapshot

        snapshot = TextSnapshot.model_validate(_text_snapshot())
        self.assertEqual("#112233", snapshot.color)
        self.assertEqual(3, snapshot.sort_order)
        self.assertEqual(["显式第一行", "显式第二行"], [line.text for line in snapshot.lines])

    def test_text_snapshot_rejects_any_unlocked_font_or_unsupported_metric(self):
        from services.canvas.schemas import TextSnapshot

        invalid_patches = (
            {"fontAssetId": "font-upload"},
            {"fontFamily": "Arial"},
            {"fontVersion": "sha256:" + "0" * 64},
            {"align": "justify"},
            {"baseline": "hanging"},
            {"color": "red"},
        )
        for patch in invalid_patches:
            with self.subTest(patch=patch), self.assertRaises(ValidationError):
                TextSnapshot.model_validate(_text_snapshot(**patch))

    def test_font_size_is_a_strict_positive_integer(self):
        from services.canvas.schemas import TextSnapshot

        for valid in (1, 24, 10_000):
            with self.subTest(valid=valid):
                self.assertEqual(valid, TextSnapshot.model_validate(
                    _text_snapshot(fontSize=valid)
                ).font_size)
        for invalid in (True, 1.0, 1.5, "24", float("nan"), 0, 10_001):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                TextSnapshot.model_validate(_text_snapshot(fontSize=invalid))

    def test_lines_are_single_line_content_canonical_and_spacing_is_codepoint_safe(self):
        from services.canvas.schemas import TextSnapshot

        self.assertEqual(
            "中文 Logo 123",
            TextSnapshot.model_validate(
                _text_snapshot(
                    content="中文 Logo 123",
                    lines=[{"text": "中文 Logo 123", "x": 0, "y": 0, "width": 200}],
                    letterSpacing=1,
                )
            ).content,
        )
        invalid = (
            {"content": "first\nsecond", "lines": [{"text": "first\nsecond", "x": 0, "y": 0, "width": 100}]},
            {"content": "first\rsecond", "lines": [{"text": "first\rsecond", "x": 0, "y": 0, "width": 100}]},
            {"content": "different", "lines": [{"text": "saved", "x": 0, "y": 0, "width": 100}]},
            {"content": "", "lines": [{"text": "", "x": 0, "y": 0, "width": 100}]},
            {"content": "e\u0301", "lines": [{"text": "e\u0301", "x": 0, "y": 0, "width": 100}], "letterSpacing": 1},
            {"content": "👩", "lines": [{"text": "👩", "x": 0, "y": 0, "width": 100}], "letterSpacing": 1},
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValidationError):
                TextSnapshot.model_validate(_text_snapshot(**candidate))

    def test_four_baselines_share_one_logical_em_line_box(self):
        from services.canvas.schemas import TextSnapshot
        from services.canvas.text_layout import line_top_from_anchor, render_text_lines

        expected = {"top": 100, "middle": 90, "bottom": 80, "alphabetic": 84}
        for baseline, top in expected.items():
            with self.subTest(baseline=baseline):
                self.assertEqual(
                    top,
                    line_top_from_anchor(100, font_size=20, baseline=baseline),
                )
                layer = TextSnapshot.model_validate(_text_snapshot(
                    content="Anchor",
                    lines=[{"text": "Anchor", "x": 10, "y": 100, "width": 100}],
                    fontSize=20,
                    baseline=baseline,
                    letterSpacing=0,
                ))
                with patch("services.canvas.text_layout._draw_spaced_text") as draw_text:
                    render_text_lines(Image.new("RGBA", (160, 140), "white"), layer=layer)
                self.assertEqual(top, draw_text.call_args.kwargs["position"][1])

    def test_line_frame_left_and_width_define_the_alignment_anchor(self):
        from services.canvas.schemas import TextSnapshot
        from services.canvas.text_layout import render_text_lines

        cases = (
            ("left", 40.0),
            ("center", 100.0),
            ("right", 160.0),
        )
        for align, expected_x in cases:
            with self.subTest(align=align):
                layer = TextSnapshot.model_validate(
                    _text_snapshot(
                        align=align,
                        content="frame",
                        lines=[{"text": "frame", "x": 40.0, "y": 60.0, "width": 120.0}],
                    )
                )
                with patch("services.canvas.text_layout._draw_spaced_text") as draw_text:
                    render_text_lines(Image.new("RGBA", (240, 120), "white"), layer=layer)
                self.assertEqual((expected_x, 40.8), draw_text.call_args.kwargs["position"])

    def test_zero_line_width_uses_the_persisted_box_width_for_alignment(self):
        from services.canvas.schemas import TextSnapshot
        from services.canvas.text_layout import render_text_lines

        layer = TextSnapshot.model_validate(
            _text_snapshot(
                align="center",
                content="frame",
                boxWidth=200.0,
                lines=[{"text": "frame", "x": 25.0, "y": 60.0, "width": 0.0}],
            )
        )
        with patch("services.canvas.text_layout._draw_spaced_text") as draw_text:
            render_text_lines(Image.new("RGBA", (240, 120), "white"), layer=layer)
        self.assertEqual((125.0, 40.8), draw_text.call_args.kwargs["position"])

    def test_nonzero_spacing_preserves_av_pair_kerning_for_center_and_right(self):
        from services.canvas.text_layout import _draw_spaced_text, pair_aware_text_metrics

        class KerningDraw:
            widths = {"A": 10.0, "V": 9.0, "AV": 17.0}

            def __init__(self):
                self.calls = []

            def textlength(self, text, *, font):
                return self.widths[text]

            def text(self, position, text, *, font, fill, anchor):
                self.calls.append((position, text, anchor))

        expected = {
            "center": [((90.5, 20.0), "A", "lt"), ((100.5, 20.0), "V", "lt")],
            "right": [((81.0, 20.0), "A", "lt"), ((91.0, 20.0), "V", "lt")],
        }
        metrics = pair_aware_text_metrics(
            "AV",
            measure_text=KerningDraw.widths.__getitem__,
            letter_spacing=2.0,
        )
        self.assertEqual(19.0, metrics.total_advance)
        self.assertEqual((0.0, 10.0), metrics.character_starts)
        for align, expected_calls in expected.items():
            with self.subTest(align=align):
                draw = KerningDraw()
                _draw_spaced_text(
                    draw,
                    position=(100.0, 20.0),
                    text="AV",
                    font=object(),
                    fill="#000000",
                    align=align,
                    letter_spacing=2.0,
                )
                self.assertEqual(expected_calls, draw.calls)


class CanvasPureCompositorTests(unittest.TestCase):
    @staticmethod
    def _product() -> Image.Image:
        image = Image.new("RGBA", (2, 2))
        image.putdata(
            [
                (255, 0, 0, 255),
                (0, 255, 0, 255),
                (0, 0, 255, 255),
                (255, 255, 0, 255),
            ]
        )
        return image

    def test_identity_placement_keeps_every_visible_product_rgb_pixel_exact(self):
        from services.canvas.compositor import LockedProductLayer, compose_image
        from services.canvas.composition_schema import PixelPlacement

        background = Image.new("RGB", (8, 8), "white")
        source = self._product()
        result = compose_image(
            background=background,
            products=(
                LockedProductLayer(
                    image=source,
                    placement=PixelPlacement.model_validate(
                        {"x": 3, "y": 2, "width": 2, "height": 2, "rotation": 0.0}
                    ),
                ),
            ),
            text_layers=(),
            output_size=(8, 8),
        )
        self.assertEqual(
            [source.getpixel((x, y))[:3] for y in range(2) for x in range(2)],
            [result.getpixel((x + 3, y + 2))[:3] for y in range(2) for x in range(2)],
        )

    def test_output_pixel_limit_accepts_the_boundary_and_rejects_before_allocation(self):
        from services.canvas.compositor import CanvasCompositionError, compose_image

        with patch("services.canvas.compositor.CANVAS_MAX_IMAGE_PIXELS", 4, create=True):
            result = compose_image(
                background=Image.new("RGB", (2, 2), "white"),
                products=(),
                text_layers=(),
                output_size=(2, 2),
            )
            self.assertEqual((2, 2), result.size)
            result.close()
            with self.assertRaises(CanvasCompositionError):
                compose_image(
                    background=Image.new("RGB", (2, 2), "white"),
                    products=(),
                    text_layers=(),
                    output_size=(3, 2),
                )

    def test_multiple_text_layers_verify_and_load_each_integer_font_size_once_per_compose(self):
        from services.canvas.compositor import compose_image
        from services.canvas.font_resource import verify_font_resource as real_verify
        from services.canvas.schemas import TextSnapshot
        from services.canvas.text_layout import ImageFont

        layers = tuple(
            TextSnapshot.model_validate(
                _text_snapshot(
                    id=f"text-{index}",
                    content=f"标签{index}",
                    lines=[{"text": f"标签{index}", "x": 4, "y": 20 + index * 24, "width": 80}],
                    fontSize=16 if index < 2 else 20,
                )
            )
            for index in range(3)
        )
        expected = Image.new("RGBA", (128, 96), "white")
        from services.canvas.text_layout import render_text_lines
        for layer in layers:
            render_text_lines(expected, layer=layer)
        with (
            patch("services.canvas.text_layout.verify_font_resource", wraps=real_verify) as verify,
            patch("services.canvas.text_layout.ImageFont.truetype", wraps=ImageFont.truetype) as load,
        ):
            result = compose_image(
                background=Image.new("RGB", (128, 96), "white"),
                products=(),
                text_layers=layers,
                output_size=(128, 96),
            )
        self.assertEqual(list(expected.get_flattened_data()), list(result.get_flattened_data()))
        expected.close()
        result.close()
        verify.assert_called_once()
        self.assertEqual(2, load.call_count)

    def test_scaled_and_thirty_degree_rotated_products_are_deterministic(self):
        from services.canvas.compositor import LockedProductLayer, encode_composed_png, compose_image
        from services.canvas.composition_schema import PixelPlacement

        background = Image.new("RGB", (16, 16), "white")
        source = self._product()
        product = LockedProductLayer(
            image=source,
            placement=PixelPlacement.model_validate(
                {"x": 5, "y": 5, "width": 6, "height": 6, "rotation": 30.0}
            ),
        )
        first = encode_composed_png(
            compose_image(
                background=background,
                products=(product,),
                text_layers=(),
                output_size=(16, 16),
            )
        )
        second = encode_composed_png(
            compose_image(
                background=background,
                products=(product,),
                text_layers=(),
                output_size=(16, 16),
            )
        )
        self.assertEqual(
            "c55de65b3a1c206edca9ee16efcb91950e63f71cfebab9b6e2e33f65c5d80912",
            hashlib.sha256(first).hexdigest(),
        )
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

    def test_fixed_z_order_places_below_text_under_product_and_above_text_over_product(self):
        from services.canvas.compositor import LockedProductLayer, compose_image
        from services.canvas.composition_schema import PixelPlacement
        from services.canvas.schemas import TextSnapshot

        product_image = Image.new("RGBA", (16, 16), (0, 0, 255, 255))
        product = LockedProductLayer(
            image=product_image,
            placement=PixelPlacement.model_validate(
                {"x": 8, "y": 8, "width": 16, "height": 16, "rotation": 0.0}
            ),
        )
        common = {
            "content": "■",
            "lines": [{"text": "■", "x": 16.0, "y": 16.0, "width": 16.0}],
            "boxWidth": 16.0,
            "fontSize": 14,
            "align": "center",
            "baseline": "middle",
        }
        below = TextSnapshot.model_validate(
            _text_snapshot(**common, color="#ff0000", zBand="below-product")
        )
        above = TextSnapshot.model_validate(
            _text_snapshot(**common, color="#00ff00", zBand="above-product")
        )
        below_result = compose_image(
            background=Image.new("RGB", (32, 32), "white"),
            products=(product,),
            text_layers=(below,),
            output_size=(32, 32),
        )
        above_result = compose_image(
            background=Image.new("RGB", (32, 32), "white"),
            products=(product,),
            text_layers=(above,),
            output_size=(32, 32),
        )
        self.assertTrue(
            all(
                below_result.getpixel((x, y))[:3] == (0, 0, 255)
                for y in range(8, 24)
                for x in range(8, 24)
            )
        )
        self.assertTrue(
            any(
                pixel[1] > pixel[2]
                for pixel in (
                    above_result.getpixel((x, y))[:3]
                    for y in range(8, 24)
                    for x in range(8, 24)
                )
            )
        )

    def test_compositor_draws_only_saved_lines_and_never_wraps_content(self):
        from services.canvas.compositor import compose_image
        from services.canvas.schemas import TextSnapshot

        snapshot = TextSnapshot.model_validate(
            _text_snapshot(
                content="显式",
                lines=[{"text": "显式", "x": 2.0, "y": 30.0, "width": 48.0}],
                color="#000000",
            )
        )
        result = compose_image(
            background=Image.new("RGB", (128, 64), "white"),
            products=(),
            text_layers=(snapshot,),
            output_size=(128, 64),
        )
        colors = set(result.get_flattened_data())
        self.assertIn((0, 0, 0, 255), colors)
        self.assertNotEqual({(255, 255, 255, 255)}, colors)


def _png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    image.close()
    return output.getvalue()


class CanvasComposeOperationTests(unittest.TestCase):
    def setUp(self):
        import canvas_models  # noqa: F401
        from database import Base
        from services.canvas import storage

        self.temporary = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temporary.name) / "canvas-data"
        self.database_path = Path(self.temporary.name) / "canvas-compose.db"
        self.engine = create_engine(
            f"sqlite:///{self.database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA journal_mode=WAL")

        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.storage_patch = patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root))
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.engine.dispose()
        self.temporary.cleanup()

    @staticmethod
    def _node(node_id: str, kind: str, **patch_value):
        node = {
            "id": node_id,
            "kind": kind,
            "managedBy": None,
            "skuId": None,
            "assetId": None,
            "modelProfileId": None,
            "prompt": None,
            "compositionGroupId": None,
            "textSnapshotId": None,
            "outputBoardId": None,
            "parameters": {},
        }
        node.update(patch_value)
        return node

    def _saved_project(self):
        from canvas_models import CanvasProject
        from services.canvas import assets, projects
        from services.canvas.composition import composition_layout_hash
        from services.canvas.composition_schema import DEFAULT_COMPOSITION_LAYOUT, CompositionLayout
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState

        with self.Session() as db:
            project = projects.create_project(db, name="Authoritative compose")
            product = assets.persist_uploaded_source(
                db,
                project_id=project.id,
                filename="product.png",
                declared_mime="image/png",
                data=_png_bytes((8, 6), (32, 96, 180)),
            )
            product.working.transparency_status = "transparent"
            background = assets.persist_uploaded_source(
                db,
                project_id=project.id,
                filename="background.png",
                declared_mime="image/png",
                data=_png_bytes((32, 32), (245, 245, 245)),
            )
            background.working.transparency_status = "opaque"
            db.commit()
            layout_contract = CompositionLayout.model_validate(DEFAULT_COMPOSITION_LAYOUT)
            group_hash = composition_layout_hash(layout_contract)
            semantic = CanvasSemanticState.model_validate(
                {
                    "nodes": [
                        self._node(
                            "main-product-source",
                            "product_source",
                            assetId=product.working.id,
                        ),
                        self._node(
                            "main-product-cutout",
                            "auto_cutout",
                            assetId=product.working.id,
                        ),
                        self._node(
                            "output-node",
                            "main_output",
                            compositionGroupId="group-main",
                            outputBoardId="board-main",
                        ),
                        self._node(
                            "text-node",
                            "text_layer",
                            textSnapshotId="text-main",
                            outputBoardId="board-main",
                        ),
                    ],
                    "edges": [
                        {
                            "id": "main-product-source-cutout",
                            "kind": "product_asset",
                            "sourceNodeId": "main-product-source",
                            "sourcePort": "product",
                            "targetNodeId": "main-product-cutout",
                            "targetPort": "reference",
                            "skuId": None,
                        }
                    ],
                    "outputBoards": [
                        {
                            "id": "board-main",
                            "outputNodeId": "output-node",
                            "outputType": "main",
                            "skuId": None,
                            "sortOrder": 0,
                            "selectedResultAssetId": None,
                        }
                    ],
                    "mode": "complete-set",
                    "advancedCustomized": False,
                    "completeSet": {
                        "selectedOutputTypes": ["main"],
                        "outputs": [
                            {
                                "outputType": "main",
                                "skuId": None,
                                "quantity": 1,
                                "aspectRatio": "1:1",
                                "width": 32,
                                "height": 32,
                                "prompt": "",
                                "modelProfileId": None,
                                "modelParameters": {},
                                "referenceAssetId": product.working.id,
                                "compositionGroupId": "group-main",
                            }
                        ],
                    },
                    "compositionGroups": [
                        {
                            "id": "group-main",
                            "skuIds": [],
                            "productLayerIds": ["product-main"],
                            "layoutHash": group_hash,
                            "layout": layout_contract.model_dump(by_alias=True),
                        }
                    ],
                }
            )
            layout = CanvasLayoutState.model_validate(
                {
                    "nodePositions": {
                        "main-product-source": {"x": 0.1, "y": 0.1},
                        "main-product-cutout": {"x": 0.3, "y": 0.1},
                        "output-node": {"x": 0.7, "y": 0.1},
                        "text-node": {"x": 0.5, "y": 0.5},
                    },
                    "objectTransforms": {
                        "transform-main": {"x": 0.5, "y": 0.9, "scale": 0.8, "rotation": 0.0}
                    },
                    "viewport": {"x": 0.0, "y": 0.0, "zoom": 1.0},
                    "productLayers": [
                        {
                            "id": "product-main",
                            "sourceAssetId": product.working.id,
                            "renderAssetId": product.working.id,
                            "allowOpaqueFallback": False,
                            "skuId": None,
                            "compositionGroupId": "group-main",
                            "transformId": "transform-main",
                            "locked": True,
                        }
                    ],
                    "textSnapshots": [
                        _text_snapshot(
                            id="text-main",
                            nodeId="text-node",
                            content="新品",
                            lines=[{"text": "新品", "x": 16.0, "y": 6.0, "width": 24.0}],
                            fontSize=8,
                            color="#102030",
                            sortOrder=0,
                        )
                    ],
                }
            )
            snapshot = projects.save_project_state(
                db,
                project_id=project.id,
                expected_revision=project.revision,
                semantic_state=semantic,
                layout_state=layout,
            )
            return (
                project.id,
                snapshot.revision,
                product.working.id,
                background.working.id,
            )

    def test_enqueue_builds_bounded_immutable_snapshot_only_from_saved_state(self):
        from services.canvas.compose_operations import enqueue_compose_operation

        project_id, revision, product_id, background_id = self._saved_project()
        with self.Session() as db:
            operation = enqueue_compose_operation(
                db,
                project_id=project_id,
                expected_revision=revision,
                board_id="board-main",
                background_asset_id=background_id,
                idempotency_key="compose-main-once",
            )
            db.commit()
            request = json.loads(operation.request_snapshot_json)
            self.assertLessEqual(len(operation.request_snapshot_json.encode("utf-8")), 256 * 1024)
            self.assertEqual(background_id, operation.input_asset_id)
            self.assertEqual(revision, request["projectRevision"])
            self.assertEqual("board-main", request["boardId"])
            self.assertEqual({"width": 32, "height": 32}, request["outputSize"])
            self.assertEqual(background_id, request["background"]["assetId"])
            self.assertEqual(product_id, request["products"][0]["spec"]["sourceAssetId"])
            self.assertEqual(product_id, request["products"][0]["spec"]["renderAssetId"])
            self.assertEqual(EXPECTED_FONT_DIGEST, request["font"]["sha256"])

    def test_enqueue_output_pixel_limit_accepts_boundary_and_rejects_over_limit(self):
        from services.canvas.compose_operations import (
            CanvasComposeRequestError,
            enqueue_compose_operation,
        )

        project_id, revision, _product_id, background_id = self._saved_project()
        with self.Session() as db, patch(
            "services.canvas.compose_operations.CANVAS_MAX_IMAGE_PIXELS", 1024, create=True
        ):
            operation = enqueue_compose_operation(
                db,
                project_id=project_id,
                expected_revision=revision,
                board_id="board-main",
                background_asset_id=background_id,
                idempotency_key="compose-pixel-boundary",
            )
            self.assertIsNotNone(operation.id)
            db.rollback()
        with self.Session() as db, patch(
            "services.canvas.compose_operations.CANVAS_MAX_IMAGE_PIXELS", 1023, create=True
        ):
            with self.assertRaises(CanvasComposeRequestError):
                enqueue_compose_operation(
                    db,
                    project_id=project_id,
                    expected_revision=revision,
                    board_id="board-main",
                    background_asset_id=background_id,
                    idempotency_key="compose-pixel-over",
                )

    def test_enqueue_rejects_a_background_owned_by_another_project(self):
        from services.canvas import assets, projects
        from services.canvas.compose_operations import (
            CanvasComposeRequestError,
            enqueue_compose_operation,
        )

        project_id, revision, _product_id, _background_id = self._saved_project()
        with self.Session() as db:
            other = projects.create_project(db, name="Other project")
            foreign = assets.persist_uploaded_source(
                db,
                project_id=other.id,
                filename="foreign-background.png",
                declared_mime="image/png",
                data=_png_bytes((32, 32), (230, 230, 230)),
            )
            db.commit()
            with self.assertRaises(CanvasComposeRequestError):
                enqueue_compose_operation(
                    db,
                    project_id=project_id,
                    expected_revision=revision,
                    board_id="board-main",
                    background_asset_id=foreign.working.id,
                    idempotency_key="compose-foreign-background",
                )

    def test_enqueue_rejects_a_tampered_saved_composition_layout_hash(self):
        from canvas_models import CanvasProject
        from services.canvas.composition import CompositionValidationError
        from services.canvas.compose_operations import enqueue_compose_operation

        project_id, revision, _product_id, background_id = self._saved_project()
        with self.Session() as db:
            project = db.get(CanvasProject, project_id)
            semantic = json.loads(project.semantic_state)
            semantic["compositionGroups"][0]["layoutHash"] = "sha256:" + "0" * 64
            project.semantic_state = json.dumps(semantic, ensure_ascii=False)
            db.commit()
            with self.assertRaises(CompositionValidationError):
                enqueue_compose_operation(
                    db,
                    project_id=project_id,
                    expected_revision=revision,
                    board_id="board-main",
                    background_asset_id=background_id,
                    idempotency_key="compose-tampered-layout-hash",
                )

    def test_worker_composes_and_persists_output_preview_and_success_atomically(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas import operations
        from services.canvas.compose_operations import enqueue_compose_operation, run_compose_operation

        project_id, revision, _product_id, background_id = self._saved_project()
        with self.Session() as db:
            operation = enqueue_compose_operation(
                db,
                project_id=project_id,
                expected_revision=revision,
                board_id="board-main",
                background_asset_id=background_id,
                idempotency_key="compose-success",
            )
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="compose-worker",
                lane="local",
                now=operation.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()

        output = run_compose_operation(
            operation.id,
            db_factory=self.Session,
            worker_id=claimed.worker_id,
            attempt_count=claimed.attempt_count,
        )
        with self.Session() as db:
            current = db.get(CanvasAssetOperation, operation.id)
            self.assertEqual("succeeded", current.status)
            self.assertEqual(output.id, current.output_asset_id)
            composed = db.get(CanvasAsset, output.id)
            self.assertEqual((32, 32), (composed.width, composed.height))
            previews = db.scalars(
                select(CanvasAsset).where(
                    CanvasAsset.project_id == project_id,
                    CanvasAsset.source_asset_id == composed.id,
                    CanvasAsset.asset_type == "preview",
                    CanvasAsset.deleted_at.is_(None),
                )
            ).all()
            self.assertEqual(1, len(previews))

    def test_generation_background_composes_to_an_immutable_terminal_result(self):
        """A generation completion uses only its saved Item snapshot."""

        from canvas_models import (
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
            CanvasAsset,
            ImageModelProfile,
            ImageProviderConnection,
        )
        from services.canvas import operations, projects
        from services.canvas.compose_operations import run_compose_operation
        from services.canvas.composition import composition_layout_hash
        from services.canvas.generation.results import (
            materialize_provider_result,
            promote_materialized_provider_result,
            remove_verified_temporary_result,
        )
        from services.canvas.generation.worker import (
            claim_next_attempt,
            prepare_claimed_attempt_for_execution,
        )
        from services.canvas.provider_schemas import ControlledImageBytes

        project_id, revision, product_id, _background_id = self._saved_project()
        now = datetime.now().replace(microsecond=0)
        provider_id, model_id, generation_id, item_id, attempt_id = (
            str(uuid4()) for _ in range(5)
        )
        capabilities = {
            "text_to_image": True,
            "image_to_image": False,
            "mask_edit": False,
            "allowed_ratios": [],
            "allowed_sizes": [],
            "min_width": None,
            "max_width": None,
            "min_height": None,
            "max_height": None,
            "max_quantity": 1,
            "max_reference_images": 0,
            "reference_transfer": "none",
            "protocol": "sync",
            "supports_cancel": False,
            "supports_idempotency": False,
            "supports_idempotency_lookup": False,
            "concurrency_limit": 1,
            "price_metadata": None,
        }
        with self.Session() as db:
            snapshot = projects.get_project_snapshot(db, project_id=project_id)
            group = snapshot.semantic_state.composition_groups[0]
            layer = snapshot.layout_state.product_layers[0]
            transform = snapshot.layout_state.object_transforms[layer.transform_id]
            board = snapshot.semantic_state.output_boards[0]
            node = next(node for node in snapshot.semantic_state.nodes if node.id == board.output_node_id)
            source = db.get(CanvasAsset, product_id)
            provider_snapshot = {
                "id": provider_id,
                "adapterType": "fake",
                "name": "Fake",
                "baseUrl": "https://provider.invalid/generate",
                "authType": "bearer",
                "configVersion": 1,
                "concurrencyLimit": 1,
            }
            model_snapshot = {
                "id": model_id,
                "providerId": provider_id,
                "modelId": "fake-sync",
                "displayName": "Fake Sync",
                "configVersion": 1,
                "capabilities": capabilities,
                "configuration": {},
            }
            layout_snapshot = {
                "version": 1,
                "compositionGroupId": group.id,
                "composition": group.layout.model_dump(by_alias=True),
                "layoutHash": composition_layout_hash(group.layout),
                "productLayer": {
                    **layer.model_dump(by_alias=True),
                    "sourceAssetSha256": source.sha256,
                    "renderAssetSha256": source.sha256,
                    "sourceWidth": source.width,
                    "sourceHeight": source.height,
                    "renderWidth": source.width,
                    "renderHeight": source.height,
                    "transform": transform.model_dump(by_alias=True),
                },
                "textSnapshots": [
                    value.model_dump(by_alias=True)
                    for value in snapshot.layout_state.text_snapshots
                ],
                "outputBoard": board.model_dump(by_alias=True),
                "outputNode": node.model_dump(by_alias=True),
            }
            db.add(ImageProviderConnection(
                id=provider_id,
                adapter_type="fake",
                name="Fake",
                base_url="https://provider.invalid/generate",
                auth_type="bearer",
            ))
            db.flush()
            db.add(ImageModelProfile(
                id=model_id,
                provider_id=provider_id,
                model_id="fake-sync",
                display_name="Fake Sync",
                capabilities_json=json.dumps(capabilities),
            ))
            db.flush()
            db.add(CanvasGeneration(
                id=generation_id,
                project_id=project_id,
                mode="complete_set",
                project_revision=revision,
                request_snapshot_json="{}",
                request_fingerprint="a" * 64,
                idempotency_key="generation-compose-chain-01",
                status="queued",
                total_items=1,
                storage_reservation_bytes=4_000_000,
                storage_reservation_remaining_bytes=4_000_000,
            ))
            db.add(CanvasGenerationItem(
                id=item_id,
                generation_id=generation_id,
                ordinal=0,
                output_type="main",
                board_id=board.id,
                node_id=node.id,
                board_order_snapshot=board.sort_order,
                provider_id=provider_id,
                provider_config_version=1,
                model_profile_id=model_id,
                model_config_version=1,
                provider_config_snapshot_json=json.dumps(provider_snapshot),
                model_config_snapshot_json=json.dumps(model_snapshot),
                prompt="clean studio backdrop",
                width=32,
                height=32,
                ratio="1:1",
                composition_group_id=group.id,
                layout_hash=layout_snapshot["layoutHash"],
                layout_snapshot_json=json.dumps(layout_snapshot),
                attempt_count=1,
                status="queued",
            ))
            db.flush()
            db.add(CanvasGenerationAttempt(
                id=attempt_id,
                item_id=item_id,
                attempt_no=1,
                provider_id=provider_id,
                provider_config_version=1,
                model_profile_id=model_id,
                model_config_version=1,
                provider_config_snapshot_json=json.dumps(provider_snapshot),
                model_config_snapshot_json=json.dumps(model_snapshot),
                status="queued",
                provider_result_stage="awaiting_provider",
                upstream_idempotency_key="generation-compose-upstream-key",
            ))
            db.commit()
        with self.Session() as db:
            claim = claim_next_attempt(db, worker_id="generation-worker", now=now)
            db.commit()
        with self.Session() as db:
            self.assertTrue(prepare_claimed_attempt_for_execution(db, claim=claim, now=now))
            db.commit()
        png = _png_bytes((32, 32), (250, 245, 235))
        asyncio.run(materialize_provider_result(
            project_id=project_id,
            attempt_id=attempt_id,
            image=ControlledImageBytes(png),
        ))
        with self.Session() as db:
            operation = promote_materialized_provider_result(
                db,
                attempt_id=attempt_id,
                claim_token=claim.claim_token,
                provider_request_id="fake-request",
                external_task_id=None,
                now=now,
            )
            db.commit()
        remove_verified_temporary_result(project_id=project_id, attempt_id=attempt_id)
        with self.Session() as db:
            local_claim = operations.claim_next_operation(
                db,
                worker_id="compose-worker",
                lane="local",
                now=operation.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()
        run_compose_operation(
            operation.id,
            db_factory=self.Session,
            worker_id=local_claim.worker_id,
            attempt_count=local_claim.attempt_count,
        )
        with self.Session() as db:
            attempt = db.get(CanvasGenerationAttempt, attempt_id)
            item = db.get(CanvasGenerationItem, item_id)
            generation = db.get(CanvasGeneration, generation_id)
            self.assertEqual("complete", attempt.provider_result_stage)
            self.assertEqual("succeeded", item.status)
            self.assertEqual("succeeded", generation.status)
            self.assertEqual(attempt.composed_asset_id, item.latest_composed_asset_id)
            self.assertIsNotNone(attempt.background_preview_asset_id)
            self.assertIsNotNone(attempt.composed_preview_asset_id)

    def test_worker_releases_every_database_connection_before_cpu_composition(self):
        from services.canvas import operations
        from services.canvas.compose_operations import enqueue_compose_operation, run_compose_operation
        from services.canvas.compositor import compose_image as real_compose

        project_id, revision, _product_id, background_id = self._saved_project()
        with self.Session() as db:
            operation = enqueue_compose_operation(
                db,
                project_id=project_id,
                expected_revision=revision,
                board_id="board-main",
                background_asset_id=background_id,
                idempotency_key="compose-no-db-during-cpu",
            )
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="compose-worker",
                lane="local",
                now=operation.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()

        checked_out = 0

        def on_checkout(*_args):
            nonlocal checked_out
            checked_out += 1

        def on_checkin(*_args):
            nonlocal checked_out
            checked_out -= 1

        event.listen(self.engine, "checkout", on_checkout)
        event.listen(self.engine, "checkin", on_checkin)

        def assert_no_database_during_cpu(**kwargs):
            self.assertEqual(0, checked_out)
            return real_compose(**kwargs)

        try:
            with patch(
                "services.canvas.compose_operations.compose_image",
                side_effect=assert_no_database_during_cpu,
            ):
                run_compose_operation(
                    operation.id,
                    db_factory=self.Session,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                )
        finally:
            event.remove(self.engine, "checkout", on_checkout)
            event.remove(self.engine, "checkin", on_checkin)

    def test_worker_rechecks_every_input_sha_before_publish(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas import operations
        from services.canvas.compose_operations import (
            CanvasComposeProcessingFailed,
            enqueue_compose_operation,
            run_compose_operation,
        )
        from services.canvas.compositor import compose_image as real_compose

        project_id, revision, product_id, background_id = self._saved_project()
        with self.Session() as db:
            operation = enqueue_compose_operation(
                db,
                project_id=project_id,
                expected_revision=revision,
                board_id="board-main",
                background_asset_id=background_id,
                idempotency_key="compose-sha-recheck",
            )
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="compose-worker",
                lane="local",
                now=operation.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()

        def mutate_after_cpu(**kwargs):
            rendered = real_compose(**kwargs)
            with self.Session() as db:
                db.get(CanvasAsset, product_id).sha256 = "0" * 64
                db.commit()
            return rendered

        with patch("services.canvas.compose_operations.compose_image", side_effect=mutate_after_cpu):
            with self.assertRaises(CanvasComposeProcessingFailed):
                run_compose_operation(
                    operation.id,
                    db_factory=self.Session,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                )
        with self.Session() as db:
            current = db.get(CanvasAssetOperation, operation.id)
            self.assertEqual("failed", current.status)
            self.assertIsNone(current.output_asset_id)
            self.assertEqual(
                0,
                len(
                    db.scalars(
                        select(CanvasAsset).where(
                            CanvasAsset.project_id == project_id,
                            CanvasAsset.asset_type == "composed",
                        )
                    ).all()
                ),
            )

    def test_worker_rejects_a_noncanonical_nonuniform_product_placement(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas import operations
        from services.canvas.compose_operations import (
            CanvasComposeProcessingFailed,
            enqueue_compose_operation,
            run_compose_operation,
        )

        project_id, revision, _product_id, background_id = self._saved_project()
        with self.Session() as db:
            operation = enqueue_compose_operation(
                db,
                project_id=project_id,
                expected_revision=revision,
                board_id="board-main",
                background_asset_id=background_id,
                idempotency_key="compose-noncanonical-placement",
            )
            request = json.loads(operation.request_snapshot_json)
            request["products"][0]["placement"]["width"] += 1
            operation.request_snapshot_json = json.dumps(request, separators=(",", ":"))
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="compose-worker",
                lane="local",
                now=operation.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()

        with self.assertRaises(CanvasComposeProcessingFailed):
            run_compose_operation(
                operation.id,
                db_factory=self.Session,
                worker_id=claimed.worker_id,
                attempt_count=claimed.attempt_count,
            )
        with self.Session() as db:
            current = db.get(CanvasAssetOperation, operation.id)
            self.assertEqual("failed", current.status)
            self.assertIsNone(current.output_asset_id)
            self.assertEqual(
                0,
                len(db.scalars(select(CanvasAsset).where(
                    CanvasAsset.project_id == project_id,
                    CanvasAsset.asset_type == "composed",
                )).all()),
            )

    def test_preview_failure_rolls_back_composed_asset_and_operation_is_retryable(self):
        from canvas_models import CanvasAsset, CanvasAssetOperation
        from services.canvas import operations
        from services.canvas.compose_operations import (
            CanvasComposeProcessingFailed,
            enqueue_compose_operation,
            run_compose_operation,
        )

        project_id, revision, _product_id, background_id = self._saved_project()
        with self.Session() as db:
            operation = enqueue_compose_operation(
                db,
                project_id=project_id,
                expected_revision=revision,
                board_id="board-main",
                background_asset_id=background_id,
                idempotency_key="compose-rollback-retry",
            )
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="compose-worker",
                lane="local",
                now=operation.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()

        with patch(
            "services.canvas.compose_operations.previews.create_preview_proxy",
            side_effect=RuntimeError("preview failed"),
        ):
            with self.assertRaises(CanvasComposeProcessingFailed):
                run_compose_operation(
                    operation.id,
                    db_factory=self.Session,
                    worker_id=claimed.worker_id,
                    attempt_count=claimed.attempt_count,
                )
        with self.Session() as db:
            current = db.get(CanvasAssetOperation, operation.id)
            self.assertEqual("failed", current.status)
            self.assertEqual(
                0,
                len(
                    db.scalars(
                        select(CanvasAsset).where(
                            CanvasAsset.project_id == project_id,
                            CanvasAsset.asset_type == "composed",
                        )
                    ).all()
                ),
            )
            retried = operations.retry_asset_operation(db, operation_id=operation.id)
            db.commit()
            claimed_retry = operations.claim_next_operation(
                db,
                worker_id="compose-worker-retry",
                lane="local",
                now=retried.next_attempt_at + timedelta(seconds=1),
            )
            db.commit()
            self.assertEqual(retried.id, claimed_retry.id)
        run_compose_operation(
            operation.id,
            db_factory=self.Session,
            worker_id=claimed_retry.worker_id,
            attempt_count=claimed_retry.attempt_count,
        )
        with self.Session() as db:
            current = db.get(CanvasAssetOperation, operation.id)
            self.assertEqual("succeeded", current.status)
            self.assertEqual(
                1,
                len(db.scalars(select(CanvasAsset).where(
                    CanvasAsset.project_id == project_id,
                    CanvasAsset.asset_type == "composed",
                    CanvasAsset.deleted_at.is_(None),
                )).all()),
            )


if __name__ == "__main__":
    unittest.main()
