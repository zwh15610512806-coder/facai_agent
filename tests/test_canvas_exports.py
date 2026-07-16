"""Authoritative Product Canvas export contracts."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker


class ExportSchemaTests(unittest.TestCase):
    @staticmethod
    def _selection(**overrides):
        value = {
            "boardId": "board-main",
            "versionId": "attempt-main",
            "composedAssetId": "composed-main",
            "order": 0,
        }
        value.update(overrides)
        return value

    def test_export_request_is_strict_and_jpeg_requires_an_explicit_background(self) -> None:
        from services.canvas.export_schemas import CanvasExportCreate

        request = CanvasExportCreate.model_validate({
            "projectRevision": 3,
            "mode": "single",
            "format": "png",
            "selectedBoards": [self._selection()],
            "jpegBackground": None,
        })
        self.assertEqual("single", request.mode)
        for payload in (
            {"projectRevision": 3, "mode": "single", "format": "jpeg", "selectedBoards": [self._selection()], "jpegBackground": None},
            {"projectRevision": 3, "mode": "single", "format": "png", "selectedBoards": [self._selection(), self._selection(order=1)], "jpegBackground": None},
            {"projectRevision": 3, "mode": "detail_long", "format": "png", "selectedBoards": [self._selection(order=1), self._selection(boardId="b2", versionId="v2", composedAssetId="c2", order=1)], "jpegBackground": None},
            {"projectRevision": 3, "mode": "single", "format": "png", "selectedBoards": [self._selection()], "jpegBackground": None, "extra": True},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    CanvasExportCreate.model_validate(payload)


class ExportBuilderTests(unittest.TestCase):
    def test_safe_components_handle_chinese_devices_controls_duplicates_and_traversal(self) -> None:
        from services.canvas.exports import safe_export_component, unique_export_names

        self.assertEqual("产品 主图", safe_export_component("产品/主图"))
        self.assertEqual("_CON", safe_export_component("CON"))
        self.assertEqual("unnamed", safe_export_component("..\\\x00"))
        names = unique_export_names(["产品", "产品", "../产品", "AUX"])
        self.assertEqual(["产品", "产品 (2)", "产品 (3)", "_AUX"], names)
        self.assertTrue(all("/" not in name and "\\" not in name and ".." not in name for name in names))

    def test_single_encoders_and_ordered_long_image_are_deterministic(self) -> None:
        from services.canvas.exports import encode_export_image, stack_detail_images

        first = Image.new("RGBA", (4, 3), (255, 0, 0, 128))
        second = Image.new("RGBA", (4, 2), (0, 0, 255, 255))
        try:
            png = encode_export_image(first, format="png", jpeg_background=None)
            jpeg = encode_export_image(first, format="jpeg", jpeg_background="#ffffff")
            webp = encode_export_image(first, format="webp", jpeg_background=None)
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertTrue(jpeg.startswith(b"\xff\xd8"))
            self.assertTrue(webp.startswith(b"RIFF") and b"WEBP" in webp[:16])
            long_image = stack_detail_images([first, second])
            self.assertEqual((4, 5), long_image.size)
            self.assertEqual((255, 0, 0), long_image.getpixel((0, 0))[:3])
            self.assertEqual((0, 0, 255), long_image.getpixel((0, 4))[:3])
            long_image.close()
        finally:
            first.close()
            second.close()

    def test_zip_builder_uses_only_safe_ordered_relative_entries(self) -> None:
        from services.canvas.exports import build_export_zip

        archive = build_export_zip([
            ("02 详情.png", b"two"),
            ("01 主图.png", b"one"),
        ])
        with zipfile.ZipFile(io.BytesIO(archive)) as opened:
            self.assertEqual(["02 详情.png", "01 主图.png"], opened.namelist())
            self.assertEqual(b"two", opened.read("02 详情.png"))
            for info in opened.infolist():
                self.assertEqual((1980, 1, 1, 0, 0, 0), info.date_time)
                self.assertFalse(info.filename.startswith(("/", "\\")))


def _png(size: tuple[int, int], color: tuple[int, int, int, int]) -> bytes:
    output = io.BytesIO()
    image = Image.new("RGBA", size, color)
    try:
        image.save(output, format="PNG", optimize=False, compress_level=9)
    finally:
        image.close()
    return output.getvalue()


class ExportQueueWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        import canvas_models  # noqa: F401
        from database import Base
        from services.canvas import storage

        self.temporary = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temporary.name) / "canvas-data"
        self.engine = create_engine(
            f"sqlite:///{(Path(self.temporary.name) / 'exports.db').as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        Base.metadata.create_all(self.engine)
        self.storage_patch = patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root))
        self.storage_patch.start()
        self.ids = self._seed_completed_version()

    def tearDown(self) -> None:
        self.storage_patch.stop()
        self.engine.dispose()
        self.temporary.cleanup()

    def _seed_completed_version(self) -> dict[str, str | int]:
        from canvas_models import (
            CanvasProject,
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
            CanvasProjectSku,
            ImageModelProfile,
            ImageProviderConnection,
        )
        from services.canvas import assets, projects
        from services.canvas.composition import composition_layout_hash
        from services.canvas.composition_schema import CompositionLayout
        from services.canvas.generation.repository import create_generation
        from services.canvas.generation.schemas import CanvasGenerationCreate
        from services.canvas.schemas import empty_layout_state, empty_semantic_state

        board_id = str(uuid4())
        node_id = str(uuid4())
        sku_id = str(uuid4())
        provider_id = str(uuid4())
        model_id = str(uuid4())
        group_id = str(uuid4())
        layer_id = str(uuid4())
        main_layer_id = str(uuid4())
        transform_id = str(uuid4())
        layout = CompositionLayout.model_validate(
            {
                "slot": {"x": 0.15, "y": 0.1, "width": 0.7, "height": 0.8},
                "anchor": {"x": 0.5, "y": 0.5},
                "safeArea": {"top": 0.05, "right": 0.05, "bottom": 0.05, "left": 0.05},
                "contain": True,
                "relativeProductFraction": 0.68,
                "baseline": 0.9,
                "rotation": 0,
            }
        )
        layout_hash = composition_layout_hash(layout)
        with self.Session() as db:
            project = projects.create_project(db, name="产品/导出项目")
            uploaded = assets.persist_uploaded_source(
                db,
                project_id=project.id,
                filename="product.png",
                declared_mime="image/png",
                data=_png((8, 8), (220, 20, 30, 255)),
            )
            uploaded.working.transparency_status = "transparent"
            db.add_all(
                [
                    CanvasProjectSku(
                        id=sku_id,
                        project_id=project.id,
                        name="香草/250g",
                        sort_order=0,
                        reference_asset_id=uploaded.working.id,
                    ),
                    ImageProviderConnection(
                        id=provider_id,
                        adapter_type="seedream",
                        name="Seedream",
                        base_url="https://example.com/images",
                        auth_type="bearer",
                        environment_credential_ref="TEST_KEY",
                        config_version=1,
                    ),
                    ImageModelProfile(
                        id=model_id,
                        provider_id=provider_id,
                        model_id="doubao-seedream-5-0-pro-260628",
                        display_name="Seedream 5.0 Pro",
                        capabilities_json=json.dumps(
                            {
                                "text_to_image": True,
                                "image_to_image": True,
                                "mask_edit": False,
                                "allowed_ratios": [],
                                "allowed_sizes": [],
                                "min_width": None,
                                "max_width": None,
                                "min_height": None,
                                "max_height": None,
                                "max_quantity": 1,
                                "max_reference_images": 1,
                                "reference_transfer": "public_url",
                                "protocol": "sync",
                                "supports_cancel": False,
                                "supports_idempotency": False,
                                "supports_idempotency_lookup": False,
                                "concurrency_limit": 1,
                                "price_metadata": None,
                            },
                            separators=(",", ":"),
                        ),
                        config_json="{}",
                        config_version=1,
                    ),
                ]
            )
            semantic = empty_semantic_state().model_dump(by_alias=True, mode="json")
            semantic.update(
                {
                    "mode": "complete-set",
                    "nodes": [
                        {
                            "id": node_id,
                            "kind": "sku_output",
                            "managedBy": "complete-set",
                            "skuId": sku_id,
                            "assetId": None,
                            "modelProfileId": None,
                            "prompt": None,
                            "compositionGroupId": group_id,
                            "textSnapshotId": None,
                            "outputBoardId": board_id,
                            "parameters": {},
                        }
                    ],
                    "outputBoards": [
                        {
                            "id": board_id,
                            "outputNodeId": node_id,
                            "outputType": "sku",
                            "skuId": sku_id,
                            "sortOrder": 0,
                            "selectedResultAssetId": None,
                        }
                    ],
                    "completeSet": {
                        "selectedOutputTypes": ["sku"],
                        "outputs": [
                            {
                                "outputType": "sku",
                                "skuId": sku_id,
                                "quantity": 1,
                                "aspectRatio": "1:1",
                                "width": 32,
                                "height": 32,
                                "prompt": "studio",
                                "modelProfileId": model_id,
                                "modelParameters": {},
                                "referenceAssetId": uploaded.working.id,
                                "compositionGroupId": group_id,
                            }
                        ],
                    },
                    "compositionGroups": [
                        {
                            "id": group_id,
                            "skuIds": [sku_id],
                            "productLayerIds": [layer_id],
                            "layoutHash": layout_hash,
                            "layout": layout.model_dump(by_alias=True, mode="json"),
                        }
                    ],
                }
            )
            layout_state = empty_layout_state().model_dump(by_alias=True, mode="json")
            layout_state["objectTransforms"] = {
                transform_id: {"x": 0.5, "y": 0.9, "scale": 0.68, "rotation": 0}
            }
            layout_state["productLayers"] = [
                {
                    "id": main_layer_id,
                    "sourceAssetId": uploaded.working.id,
                    "renderAssetId": uploaded.working.id,
                    "allowOpaqueFallback": True,
                    "skuId": None,
                    "compositionGroupId": None,
                    "transformId": transform_id,
                    "locked": True,
                },
                {
                    "id": layer_id,
                    "sourceAssetId": uploaded.working.id,
                    "renderAssetId": uploaded.working.id,
                    "allowOpaqueFallback": True,
                    "skuId": sku_id,
                    "compositionGroupId": group_id,
                    "transformId": transform_id,
                    "locked": True,
                }
            ]
            project.semantic_state = json.dumps(semantic, ensure_ascii=False, separators=(",", ":"))
            project.layout_state = json.dumps(layout_state, ensure_ascii=False, separators=(",", ":"))
            project.revision = 3
            db.commit()
            generation, _ = create_generation(
                db,
                project_id=project.id,
                request=CanvasGenerationCreate.model_validate(
                    {
                        "revision": 3,
                        "mode": "complete-set",
                        "items": [
                            {
                                "outputType": "sku",
                                "skuId": sku_id,
                                "boardId": board_id,
                                "nodeId": node_id,
                                "boardOrder": 0,
                                "modelProfileId": model_id,
                                "prompt": "studio",
                                "width": 32,
                                "height": 32,
                                "ratio": "1:1",
                                "compositionGroupId": group_id,
                                "layoutHash": layout_hash,
                                "inputs": [
                                    {"assetId": uploaded.working.id, "inputRole": "product", "ordinal": 0}
                                ],
                                "textSnapshotIds": [],
                            }
                        ],
                    }
                ),
                idempotency_key="export-fixture-generation-key",
            )
            item = db.scalar(
                select(CanvasGenerationItem).where(CanvasGenerationItem.generation_id == generation.id)
            )
            attempt = db.scalar(
                select(CanvasGenerationAttempt).where(CanvasGenerationAttempt.item_id == item.id)
            )
            background = assets.persist_derived_image(
                db,
                project_id=project.id,
                asset_type="generated_background",
                data=_png((32, 32), (245, 245, 245, 255)),
                mime_type="image/png",
                source_asset_id=uploaded.working.id,
                metadata={},
            )
            historical = assets.persist_derived_image(
                db,
                project_id=project.id,
                asset_type="composed",
                data=_png((32, 32), (0, 255, 0, 255)),
                mime_type="image/png",
                source_asset_id=background.id,
                metadata={},
            )
            attempt.status = "succeeded"
            attempt.provider_result_stage = "complete"
            attempt.background_asset_id = background.id
            attempt.composed_asset_id = historical.id
            item.status = "succeeded"
            item.latest_background_asset_id = background.id
            item.latest_composed_asset_id = historical.id
            generation.status = "succeeded"
            generation.succeeded_items = 1
            semantic["outputBoards"][0]["selectedResultAssetId"] = historical.id
            db.execute(
                update(CanvasProject)
                .where(CanvasProject.id == project.id)
                .values(
                    semantic_state=json.dumps(
                        semantic,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
            )
            db.commit()
            return {
                "project": project.id,
                "revision": project.revision,
                "board": board_id,
                "version": attempt.id,
                "composed": historical.id,
            }

    def _request(self, *, format: str = "png", background: str | None = None):
        from services.canvas.export_schemas import CanvasExportCreate

        return CanvasExportCreate.model_validate(
            {
                "projectRevision": self.ids["revision"],
                "mode": "single",
                "format": format,
                "selectedBoards": [
                    {
                        "boardId": self.ids["board"],
                        "versionId": self.ids["version"],
                        "composedAssetId": self.ids["composed"],
                        "order": 0,
                    }
                ],
                "jpegBackground": background,
            }
        )

    def test_export_is_idempotent_and_worker_rebuilds_authoritative_saved_state(self) -> None:
        from canvas_models import CanvasAssetOperation
        from services.canvas import assets, operations
        from services.canvas.exports import enqueue_canvas_export, run_export_operation

        with self.Session() as db:
            first = enqueue_canvas_export(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="export-request-key-0001",
            )
            duplicate = enqueue_canvas_export(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="export-request-key-0001",
            )
            self.assertEqual(first.id, duplicate.id)
            db.commit()
            claimed = operations.claim_next_operation(
                db,
                worker_id="export-worker",
                lane="local",
                now=datetime.now(UTC).replace(tzinfo=None),
            )
            db.commit()
        exported = run_export_operation(
            claimed.id,
            db_factory=self.Session,
            worker_id=claimed.worker_id,
            attempt_count=claimed.attempt_count,
        )
        with self.Session() as db:
            operation = db.get(CanvasAssetOperation, claimed.id)
            self.assertEqual("succeeded", operation.status)
            self.assertEqual(exported.id, operation.output_asset_id)
            persisted = db.get(type(exported), exported.id)
            data = assets.read_verified_asset_bytes(
                db,
                asset=persisted,
                project_id=self.ids["project"],
            )
            self.assertEqual(
                {"exportSelection"},
                assets.collect_export_asset_references(
                    db,
                    project_id=self.ids["project"],
                    asset_id=self.ids["composed"],
                ),
            )
            from routers.canvas.assets import download_export

            response = download_export(exported.id, db)
            self.assertEqual(data, response.body)
            self.assertIn("attachment", response.headers["content-disposition"])
            self.assertIn("filename*=UTF-8''", response.headers["content-disposition"])
            self.assertEqual("nosniff", response.headers["x-content-type-options"])
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                self.assertEqual("PNG", image.format)
                self.assertNotEqual((0, 255, 0), image.getpixel((0, 0))[:3])

    def test_same_idempotency_key_rejects_a_different_export(self) -> None:
        from services.canvas.operations import CanvasOperationIdempotencyConflict
        from services.canvas.exports import enqueue_canvas_export

        with self.Session() as db:
            enqueue_canvas_export(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="export-request-key-0002",
            )
            with self.assertRaises(CanvasOperationIdempotencyConflict):
                enqueue_canvas_export(
                    db,
                    project_id=self.ids["project"],
                    request=self._request(format="jpeg", background="#ffffff"),
                    idempotency_key="export-request-key-0002",
                )


if __name__ == "__main__":
    unittest.main()
