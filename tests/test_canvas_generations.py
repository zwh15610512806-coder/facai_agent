"""Strict contracts for creating durable Product Canvas generations."""
from __future__ import annotations

import tempfile
import unittest
import json
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker


class GenerationRequestSchemaTests(unittest.TestCase):
    @staticmethod
    def _item(**overrides):
        item = {
            "outputType": "sku",
            "skuId": "sku-a",
            "boardId": "board-a",
            "nodeId": "node-a",
            "boardOrder": 0,
            "modelProfileId": "model-a",
            "prompt": "soft studio background",
            "width": 2048,
            "height": 2048,
            "ratio": "1:1",
            "compositionGroupId": "group-a",
            "layoutHash": "sha256:" + "a" * 64,
            "inputs": [
                {"assetId": "asset-a", "inputRole": "product", "ordinal": 0}
            ],
            "textSnapshotIds": [],
        }
        item.update(overrides)
        return item

    def test_request_is_strict_and_expands_one_to_fifty_explicit_items(self):
        from services.canvas.generation.schemas import CanvasGenerationCreate

        request = CanvasGenerationCreate.model_validate(
            {"revision": 3, "mode": "complete-set", "items": [self._item()]}
        )
        self.assertEqual(1, len(request.items))
        self.assertEqual("complete-set", request.mode)

        invalid_payloads = (
            {"revision": 3, "mode": "complete-set", "items": [], "surprise": True},
            {"revision": 3, "mode": "complete-set", "items": []},
            {
                "revision": 3,
                "mode": "complete-set",
                "items": [self._item(boardId=f"board-{index}", nodeId=f"node-{index}") for index in range(51)],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload_size=len(payload.get("items", []))):
                with self.assertRaises(ValidationError):
                    CanvasGenerationCreate.model_validate(payload)

    def test_missing_output_model_material_count_and_size_are_itemized(self):
        from services.canvas.generation.schemas import CanvasGenerationCreate

        with self.assertRaises(ValidationError) as caught:
            CanvasGenerationCreate.model_validate(
                {
                    "revision": 3,
                    "mode": "complete-set",
                    "items": [
                        {
                            "boardId": "board-a",
                            "nodeId": "node-a",
                            "boardOrder": 0,
                            "prompt": "studio",
                            "ratio": "1:1",
                            "layoutHash": "sha256:" + "a" * 64,
                        }
                    ],
                }
            )

        locations = {tuple(error["loc"]) for error in caught.exception.errors()}
        self.assertIn(("items", 0, "outputType"), locations)
        self.assertIn(("items", 0, "modelProfileId"), locations)
        self.assertIn(("items", 0, "inputs"), locations)
        self.assertIn(("items", 0, "width"), locations)
        self.assertIn(("items", 0, "height"), locations)

        with self.assertRaises(ValidationError) as no_count:
            CanvasGenerationCreate.model_validate(
                {"revision": 3, "mode": "complete-set"}
            )
        self.assertIn(
            ("items",),
            {tuple(error["loc"]) for error in no_count.exception.errors()},
        )

    def test_item_requires_one_product_material_and_unique_board_binding(self):
        from services.canvas.generation.schemas import CanvasGenerationCreate

        invalid_items = (
            self._item(inputs=[]),
            self._item(
                inputs=[
                    {"assetId": "asset-a", "inputRole": "reference", "ordinal": 0}
                ]
            ),
            self._item(outputType="main", skuId="sku-a", compositionGroupId=None),
            self._item(outputType="sku", skuId=None),
        )
        for item in invalid_items:
            with self.subTest(item=item):
                with self.assertRaises(ValidationError):
                    CanvasGenerationCreate.model_validate(
                        {"revision": 3, "mode": "complete-set", "items": [item]}
                    )

        duplicate_board = self._item()
        with self.assertRaises(ValidationError):
            CanvasGenerationCreate.model_validate(
                {
                    "revision": 3,
                    "mode": "complete-set",
                    "items": [duplicate_board, {**duplicate_board, "nodeId": "node-b"}],
                }
            )


class GenerationFingerprintAndReservationTests(unittest.TestCase):
    @staticmethod
    def _snapshot(**overrides):
        from services.canvas.generation.schemas import (
            GenerationInputSnapshot,
            GenerationItemSnapshot,
        )

        values = {
            "ordinal": 0,
            "output_type": "sku",
            "sku_id": "sku-a",
            "sku_name": "Vanilla",
            "board_id": "board-a",
            "node_id": "node-a",
            "board_order": 0,
            "provider_id": "provider-a",
            "provider_config_version": 2,
            "provider_config": {"adapterType": "seedream"},
            "model_profile_id": "model-a",
            "model_display_name": "Seedream 5.0 Pro",
            "model_config_version": 4,
            "model_config": {"model": "seedream"},
            "prompt": "warm studio",
            "width": 2048,
            "height": 2048,
            "ratio": "1:1",
            "composition_group_id": "group-a",
            "layout_hash": "sha256:" + "a" * 64,
            "layout": {"slot": {"x": 0.1, "y": 0.1}},
            "inputs": (
                GenerationInputSnapshot(
                    asset_id="asset-a",
                    input_role="product",
                    ordinal=0,
                    asset_sha256="b" * 64,
                ),
            ),
            "text_snapshots": (),
        }
        values.update(overrides)
        return GenerationItemSnapshot(**values)

    def test_fingerprint_is_canonical_and_covers_authoritative_versions_and_hashes(self):
        from services.canvas.generation.fingerprints import compute_generation_fingerprint

        first = self._snapshot()
        same = self._snapshot(provider_config={"adapterType": "seedream"})
        fingerprint = compute_generation_fingerprint(project_revision=3, items=[first])
        self.assertEqual(
            fingerprint,
            compute_generation_fingerprint(project_revision=3, items=[same]),
        )
        self.assertEqual(64, len(fingerprint))
        for changed in (
            self._snapshot(provider_config_version=3),
            self._snapshot(model_config_version=5),
            self._snapshot(prompt="cool studio"),
            self._snapshot(layout_hash="sha256:" + "c" * 64),
            self._snapshot(
                inputs=(first.inputs[0].__class__(
                    asset_id="asset-a",
                    input_role="product",
                    ordinal=0,
                    asset_sha256="d" * 64,
                ),)
            ),
        ):
            with self.subTest(changed=changed):
                self.assertNotEqual(
                    fingerprint,
                    compute_generation_fingerprint(project_revision=3, items=[changed]),
                )

    def test_reservation_includes_verified_background_composed_and_two_proxies(self):
        from services.canvas.generation.fingerprints import (
            encoded_rgba_png_upper_bound,
            estimate_generation_storage_reservation,
            proxy_dimensions,
        )

        item = self._snapshot(width=4096, height=2048)
        remote_max = 25 * 1024 * 1024
        proxy_width, proxy_height = proxy_dimensions(4096, 2048)
        expected = (
            2 * remote_max
            + encoded_rgba_png_upper_bound(4096, 2048)
            + 2 * encoded_rgba_png_upper_bound(proxy_width, proxy_height)
        )
        self.assertEqual(
            expected,
            estimate_generation_storage_reservation(
                [item], remote_image_max_bytes=remote_max
            ),
        )
        self.assertEqual(
            expected * 2,
            estimate_generation_storage_reservation(
                [
                    item,
                    self._snapshot(
                        ordinal=1,
                        board_id="board-b",
                        node_id="node-b",
                        width=4096,
                        height=2048,
                    ),
                ],
                remote_image_max_bytes=remote_max,
            ),
        )


class GenerationModelContractTests(unittest.TestCase):
    def test_layout_hash_column_holds_the_authoritative_prefixed_digest(self):
        from canvas_models import CanvasGenerationItem

        self.assertGreaterEqual(CanvasGenerationItem.layout_hash.type.length, 71)


class _GenerationFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "canvas-data"
        self.engine = create_engine(
            f"sqlite:///{(Path(self.tmp.name) / 'generations.db').as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        import canvas_models  # noqa: F401
        from database import Base
        from services.canvas import storage

        Base.metadata.create_all(self.engine)
        self.storage = storage
        self.storage_patch = patch.object(
            storage,
            "CANVAS_DATA_DIR",
            str(self.data_root),
        )
        self.storage_patch.start()
        self.ids = self._seed_project()

    def tearDown(self) -> None:
        self.storage_patch.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def _seed_project(self) -> dict[str, str]:
        from canvas_models import (
            CanvasAsset,
            CanvasProject,
            CanvasProjectSku,
            ImageModelProfile,
            ImageProviderConnection,
        )
        from services.canvas.composition import composition_layout_hash
        from services.canvas.composition_schema import CompositionLayout
        from services.canvas.schemas import empty_layout_state, empty_semantic_state

        project_id = str(uuid4())
        asset_id = str(uuid4())
        sku_id = str(uuid4())
        provider_id = str(uuid4())
        model_id = str(uuid4())
        board_id = str(uuid4())
        node_id = str(uuid4())
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
        semantic = empty_semantic_state().model_dump(by_alias=True, mode="json")
        semantic["mode"] = "complete-set"
        semantic["nodes"] = [
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
        ]
        semantic["outputBoards"] = [
            {
                "id": board_id,
                "outputNodeId": node_id,
                "outputType": "sku",
                "skuId": sku_id,
                "sortOrder": 0,
                "selectedResultAssetId": None,
            }
        ]
        semantic["compositionGroups"] = [
            {
                "id": group_id,
                "skuIds": [sku_id],
                "productLayerIds": [layer_id],
                "layoutHash": layout_hash,
                "layout": layout.model_dump(by_alias=True, mode="json"),
            }
        ]
        layout_state = empty_layout_state().model_dump(by_alias=True, mode="json")
        layout_state["objectTransforms"] = {
            transform_id: {"x": 0.5, "y": 0.9, "scale": 0.68, "rotation": 0}
        }
        layout_state["productLayers"] = [
            {
                "id": main_layer_id,
                "sourceAssetId": asset_id,
                "renderAssetId": asset_id,
                "allowOpaqueFallback": True,
                "skuId": None,
                "compositionGroupId": None,
                "transformId": transform_id,
                "locked": True,
            },
            {
                "id": layer_id,
                "sourceAssetId": asset_id,
                "renderAssetId": asset_id,
                "allowOpaqueFallback": True,
                "skuId": sku_id,
                "compositionGroupId": group_id,
                "transformId": transform_id,
                "locked": True,
            }
        ]
        with self.Session() as db:
            db.add(
                CanvasProject(
                    id=project_id,
                    name="Generation project",
                    semantic_state=json.dumps(semantic, ensure_ascii=False, separators=(",", ":")),
                    layout_state=json.dumps(layout_state, ensure_ascii=False, separators=(",", ":")),
                    revision=3,
                )
            )
            db.add(
                CanvasAsset(
                    id=asset_id,
                    project_id=project_id,
                    asset_type="working",
                    relative_path=f"working/{asset_id}.png",
                    original_filename="product.png",
                    mime_type="image/png",
                    byte_count=1234,
                    width=800,
                    height=800,
                    sha256="b" * 64,
                    transparency_status="transparent",
                )
            )
            db.add(
                CanvasProjectSku(
                    id=sku_id,
                    project_id=project_id,
                    name="Vanilla 250g",
                    sort_order=0,
                    reference_asset_id=asset_id,
                )
            )
            db.add(
                ImageProviderConnection(
                    id=provider_id,
                    adapter_type="seedream",
                    name="Seedream",
                    base_url="https://ark.cn-beijing.volces.com/api/v3/images/generations",
                    auth_type="bearer",
                    environment_credential_ref="ARK_API_KEY",
                    credential_hint="must-not-snapshot",
                    config_version=2,
                )
            )
            db.add(
                ImageModelProfile(
                    id=model_id,
                    provider_id=provider_id,
                    model_id="doubao-seedream-5-0-pro-260628",
                    display_name="Seedream 5.0 Pro（完整版）",
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
                    config_json=json.dumps(
                        {"endpoint": "images", "watermark": False},
                        separators=(",", ":"),
                    ),
                    config_version=4,
                )
            )
            db.commit()
        return {
            "project": project_id,
            "asset": asset_id,
            "sku": sku_id,
            "provider": provider_id,
            "model": model_id,
            "board": board_id,
            "node": node_id,
            "group": group_id,
            "mainLayer": main_layer_id,
            "layoutHash": layout_hash,
        }

    def _request(self, **item_overrides):
        from services.canvas.generation.schemas import CanvasGenerationCreate

        item = {
            "outputType": "sku",
            "skuId": self.ids["sku"],
            "boardId": self.ids["board"],
            "nodeId": self.ids["node"],
            "boardOrder": 0,
            "modelProfileId": self.ids["model"],
            "prompt": "soft studio background",
            "width": 2048,
            "height": 2048,
            "ratio": "1:1",
            "compositionGroupId": self.ids["group"],
            "layoutHash": self.ids["layoutHash"],
            "inputs": [
                {
                    "assetId": self.ids["asset"],
                    "inputRole": "product",
                    "ordinal": 0,
                }
            ],
            "textSnapshotIds": [],
        }
        item.update(item_overrides)
        return CanvasGenerationCreate.model_validate(
            {"revision": 3, "mode": "complete-set", "items": [item]}
        )

    def _advanced_request(self):
        """Persist the canonical advanced route with output composition on its edge."""
        from canvas_models import CanvasProject
        from services.canvas.generation.schemas import CanvasGenerationCreate

        source_id = "main-product-source"
        cutout_id = "main-product-cutout"
        prompt_id = "advanced-prompt"
        generation_id = "advanced-generation"
        composition_id = "advanced-composition"
        with self.Session() as db:
            project = db.get(CanvasProject, self.ids["project"])
            assert project is not None
            semantic = json.loads(project.semantic_state)
            semantic["mode"] = "advanced"
            output = semantic["nodes"][0]
            output["managedBy"] = None
            output["compositionGroupId"] = None
            semantic["nodes"].extend(
                [
                    {
                        "id": source_id,
                        "kind": "product_source",
                        "managedBy": None,
                        "skuId": None,
                        "assetId": self.ids["asset"],
                        "modelProfileId": None,
                        "prompt": None,
                        "compositionGroupId": None,
                        "textSnapshotId": None,
                        "outputBoardId": None,
                        "parameters": {},
                    },
                    {
                        "id": cutout_id,
                        "kind": "auto_cutout",
                        "managedBy": None,
                        "skuId": None,
                        "assetId": self.ids["asset"],
                        "modelProfileId": None,
                        "prompt": None,
                        "compositionGroupId": None,
                        "textSnapshotId": None,
                        "outputBoardId": None,
                        "parameters": {},
                    },
                    {
                        "id": prompt_id,
                        "kind": "prompt",
                        "managedBy": None,
                        "skuId": None,
                        "assetId": None,
                        "modelProfileId": None,
                        "prompt": "soft studio background",
                        "compositionGroupId": None,
                        "textSnapshotId": None,
                        "outputBoardId": None,
                        "parameters": {},
                    },
                    {
                        "id": generation_id,
                        "kind": "model_generation",
                        "managedBy": None,
                        "skuId": None,
                        "assetId": None,
                        "modelProfileId": self.ids["model"],
                        "prompt": None,
                        "compositionGroupId": None,
                        "textSnapshotId": None,
                        "outputBoardId": None,
                        "parameters": {"width": 2048, "height": 2048},
                    },
                    {
                        "id": composition_id,
                        "kind": "composition_group",
                        "managedBy": None,
                        "skuId": None,
                        "assetId": None,
                        "modelProfileId": None,
                        "prompt": None,
                        "compositionGroupId": self.ids["group"],
                        "textSnapshotId": None,
                        "outputBoardId": None,
                        "parameters": {},
                    },
                ]
            )
            semantic["edges"] = [
                {
                    "id": "main-product-source-cutout",
                    "kind": "product_asset",
                    "sourceNodeId": source_id,
                    "sourcePort": "product",
                    "targetNodeId": cutout_id,
                    "targetPort": "reference",
                    "skuId": None,
                },
                {
                    "id": "advanced-cutout-generation",
                    "kind": "cutout_asset",
                    "sourceNodeId": cutout_id,
                    "sourcePort": "cutout",
                    "targetNodeId": generation_id,
                    "targetPort": "reference",
                    "skuId": None,
                },
                {
                    "id": "advanced-prompt-generation",
                    "kind": "prompt",
                    "sourceNodeId": prompt_id,
                    "sourcePort": "prompt",
                    "targetNodeId": generation_id,
                    "targetPort": "prompt",
                    "skuId": None,
                },
                {
                    "id": "advanced-generation-output",
                    "kind": "output_image",
                    "sourceNodeId": generation_id,
                    "sourcePort": "output",
                    "targetNodeId": self.ids["node"],
                    "targetPort": "input",
                    "skuId": None,
                },
                {
                    "id": "advanced-composition-output",
                    "kind": "composition",
                    "sourceNodeId": composition_id,
                    "sourcePort": "composition",
                    "targetNodeId": self.ids["node"],
                    "targetPort": "composition",
                    "skuId": None,
                },
            ]
            project.semantic_state = json.dumps(semantic, ensure_ascii=False, separators=(",", ":"))
            db.commit()

        payload = self._request().model_dump(by_alias=True, mode="json")
        payload["mode"] = "advanced"
        return CanvasGenerationCreate.model_validate(payload)

    def _counts(self) -> tuple[int, int, int]:
        from canvas_models import (
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
        )

        with self.Session() as db:
            return (
                db.scalar(select(func.count()).select_from(CanvasGeneration)),
                db.scalar(select(func.count()).select_from(CanvasGenerationItem)),
                db.scalar(select(func.count()).select_from(CanvasGenerationAttempt)),
            )

    def test_create_snapshots_all_authoritative_values_and_queues_one_attempt(self):
        from canvas_models import (
            CanvasGenerationAttempt,
            CanvasGenerationItem,
            CanvasGenerationItemInput,
        )
        from services.canvas.generation.repository import create_generation

        with self.Session() as db:
            generation, created = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-key-0001",
            )
            generation_id = generation.id
        self.assertTrue(created)
        self.assertEqual((1, 1, 1), self._counts())
        with self.Session() as db:
            item = db.scalar(
                select(CanvasGenerationItem).where(
                    CanvasGenerationItem.generation_id == generation_id
                )
            )
            attempt = db.scalar(
                select(CanvasGenerationAttempt).where(
                    CanvasGenerationAttempt.item_id == item.id
                )
            )
            material = db.scalar(
                select(CanvasGenerationItemInput).where(
                    CanvasGenerationItemInput.item_id == item.id
                )
            )
            self.assertEqual("Vanilla 250g", item.sku_name_snapshot)
            self.assertEqual(2, item.provider_config_version)
            self.assertEqual(4, item.model_config_version)
            self.assertEqual(self.ids["layoutHash"], item.layout_hash)
            self.assertEqual("b" * 64, material.asset_sha256)
            self.assertEqual("queued", attempt.status)
            provider_snapshot = json.loads(item.provider_config_snapshot_json)
            model_snapshot = json.loads(item.model_config_snapshot_json)
            self.assertNotIn("environmentCredentialRef", provider_snapshot)
            self.assertNotIn("credentialHint", provider_snapshot)
            self.assertEqual("Seedream 5.0 Pro（完整版）", model_snapshot["displayName"])


class GenerationCreationTests(_GenerationFixture):
    TOKEN = "canvas-generation-paid-access-token"

    def _app(self) -> FastAPI:
        from database import get_db
        from routers.canvas import router as canvas_router

        app = FastAPI()
        app.include_router(canvas_router, prefix="/api/canvas")

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        return app

    def test_create_route_is_passwordless_and_requires_safe_idempotency_key(self):
        payload = self._request().model_dump(by_alias=True, mode="json")
        with TestClient(self._app()) as client:
                missing = client.post(
                    f"/api/canvas/projects/{self.ids['project']}/generations",
                    json=payload,
                )
                self.assertEqual(422, missing.status_code, missing.text)
                unsafe = client.post(
                    f"/api/canvas/projects/{self.ids['project']}/generations",
                    json=payload,
                    headers={"Idempotency-Key": "unsafe key value!"},
                )
                self.assertEqual(422, unsafe.status_code, unsafe.text)
                created = client.post(
                    f"/api/canvas/projects/{self.ids['project']}/generations",
                    json=payload,
                    headers={"Idempotency-Key": "generation-api-key-01"},
                )
                self.assertEqual(201, created.status_code, created.text)
                replay = client.post(
                    f"/api/canvas/projects/{self.ids['project']}/generations",
                    json=payload,
                    headers={"Idempotency-Key": "generation-api-key-01"},
                )
                self.assertEqual(200, replay.status_code, replay.text)
                self.assertEqual(created.json()["id"], replay.json()["id"])
                self.assertEqual((1, 1, 1), self._counts())
                serialized = json.dumps(created.json(), ensure_ascii=False)
                self.assertNotIn("credential", serialized.lower())
                self.assertNotIn("requestSnapshot", serialized)

    def test_advanced_post_uses_wired_composition_when_output_node_has_no_group(self):
        payload = self._advanced_request().model_dump(by_alias=True, mode="json")
        with TestClient(self._app()) as client:
            created = client.post(
                    f"/api/canvas/projects/{self.ids['project']}/generations",
                    json=payload,
                    headers={"Idempotency-Key": "advanced-composition-route-01"},
                )
        self.assertEqual(201, created.status_code, created.text)
        self.assertEqual("advanced", created.json()["mode"])
        self.assertEqual((1, 1, 1), self._counts())

    def test_advanced_post_rejects_tampered_system_cutout_lineage(self):
        from canvas_models import CanvasProject

        payload = self._advanced_request().model_dump(by_alias=True, mode="json")
        with self.Session() as db:
            project = db.get(CanvasProject, self.ids["project"])
            assert project is not None
            semantic = json.loads(project.semantic_state)
            for edge in semantic["edges"]:
                if edge["id"] == "main-product-source-cutout":
                    edge["sourceNodeId"] = "forged-product-source"
            project.semantic_state = json.dumps(semantic, ensure_ascii=False, separators=(",", ":"))
            db.commit()

        with TestClient(self._app()) as client:
            rejected = client.post(
                    f"/api/canvas/projects/{self.ids['project']}/generations",
                    json=payload,
                    headers={"Idempotency-Key": "advanced-forged-lineage-01"},
                )
        self.assertEqual(422, rejected.status_code, rejected.text)
        self.assertEqual((0, 0, 0), self._counts())

    def test_advanced_post_rejects_dimensions_tampered_from_generation_node(self):
        payload = self._advanced_request().model_dump(by_alias=True, mode="json")
        payload["items"][0].update({"width": 1024, "height": 1024, "ratio": "1:1"})

        with TestClient(self._app()) as client:
            rejected = client.post(
                    f"/api/canvas/projects/{self.ids['project']}/generations",
                    json=payload,
                    headers={"Idempotency-Key": "advanced-dimension-tamper-01"},
                )

        self.assertEqual(422, rejected.status_code, rejected.text)
        self.assertEqual((0, 0, 0), self._counts())

    def _mark_success_with_assets(self) -> tuple[str, str, dict[str, str]]:
        from canvas_models import (
            CanvasAsset,
            CanvasGeneration,
            CanvasGenerationAttempt,
            CanvasGenerationItem,
        )
        from services.canvas.generation.repository import create_generation

        with self.Session() as db:
            generation, _ = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-version-key-01",
            )
        with self.Session() as db:
            item = db.scalar(
                select(CanvasGenerationItem).where(
                    CanvasGenerationItem.generation_id == generation.id
                )
            )
            attempt = db.scalar(
                select(CanvasGenerationAttempt).where(
                    CanvasGenerationAttempt.item_id == item.id
                )
            )
            ids = {
                "background": str(uuid4()),
                "backgroundPreview": str(uuid4()),
                "composed": str(uuid4()),
                "composedPreview": str(uuid4()),
            }
            for asset_id, asset_type, source_id in (
                (ids["background"], "generated_background", None),
                (ids["backgroundPreview"], "preview", ids["background"]),
                (ids["composed"], "composed", ids["background"]),
                (ids["composedPreview"], "preview", ids["composed"]),
            ):
                db.add(
                    CanvasAsset(
                        id=asset_id,
                        project_id=self.ids["project"],
                        asset_type=asset_type,
                        relative_path=f"{asset_type}/{asset_id}.png",
                        original_filename=f"{asset_id}.png",
                        mime_type="image/png",
                        byte_count=10,
                        width=2048,
                        height=2048,
                        sha256=asset_id.replace("-", "")[:32].ljust(64, "0"),
                        source_asset_id=source_id,
                    )
                )
            db.flush()
            now = datetime.now(UTC).replace(tzinfo=None)
            attempt.status = "succeeded"
            attempt.provider_result_stage = "complete"
            attempt.background_asset_id = ids["background"]
            attempt.background_preview_asset_id = ids["backgroundPreview"]
            attempt.composed_asset_id = ids["composed"]
            attempt.composed_preview_asset_id = ids["composedPreview"]
            attempt.completed_at = now
            item.status = "succeeded"
            item.latest_background_asset_id = ids["background"]
            item.latest_composed_asset_id = ids["composed"]
            generation_row = db.get(CanvasGeneration, generation.id)
            generation_row.status = "succeeded"
            generation_row.succeeded_items = 1
            generation_row.storage_reservation_remaining_bytes = 0
            generation_row.completed_at = now
            db.commit()
            return generation.id, item.id, ids

    def test_result_versions_are_immutable_safe_and_require_exact_asset_lineage(self):
        from canvas_models import CanvasAsset
        from services.canvas.generation.repository import list_board_result_versions

        generation_id, _item_id, ids = self._mark_success_with_assets()
        with self.Session() as db:
            page = list_board_result_versions(
                db,
                project_id=self.ids["project"],
                board_id=self.ids["board"],
                cursor=None,
                limit=50,
            )
            self.assertEqual(1, len(page.items))
            version = page.items[0]
            self.assertEqual(generation_id, version.generation_id)
            self.assertEqual(ids["backgroundPreview"], version.background_preview_asset_id)
            self.assertEqual(ids["composedPreview"], version.composed_preview_asset_id)
            wire = page.model_dump(by_alias=True, mode="json")
            serialized = json.dumps(wire, ensure_ascii=False)
            self.assertNotIn("relativePath", serialized)
            self.assertNotIn("snapshot", serialized.lower())
            self.assertNotIn("credential", serialized.lower())

            corrupt_preview = db.get(CanvasAsset, ids["composedPreview"])
            corrupt_preview.source_asset_id = ids["background"]
            db.commit()
        with self.Session() as db:
            corrupt = list_board_result_versions(
                db,
                project_id=self.ids["project"],
                board_id=self.ids["board"],
                cursor=None,
                limit=50,
            )
            self.assertEqual([], corrupt.items)

    def test_generation_routes_are_exact_and_reads_remain_unlocked(self):
        paths = self._app().openapi()["paths"]
        self.assertIn(
            "/api/canvas/projects/{project_id}/generations",
            paths,
        )
        self.assertIn("post", paths["/api/canvas/projects/{project_id}/generations"])
        self.assertIn("/api/canvas/generations/{generation_id}", paths)
        self.assertIn("/api/canvas/projects/{project_id}/result-versions", paths)

    def test_same_key_replays_once_and_changed_request_conflicts(self):
        from canvas_models import CanvasProject
        from services.canvas.generation.repository import (
            CanvasGenerationIdempotencyConflict,
            create_generation,
        )

        with self.Session() as db:
            first, first_created = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-key-0002",
            )
        with self.Session() as db:
            project = db.get(CanvasProject, self.ids["project"])
            project.revision = 4
            db.commit()
        with self.Session() as db:
            replay, replay_created = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-key-0002",
            )
        self.assertTrue(first_created)
        self.assertFalse(replay_created)
        self.assertEqual(first.id, replay.id)
        self.assertEqual((1, 1, 1), self._counts())

        with self.Session() as db, self.assertRaises(CanvasGenerationIdempotencyConflict):
            create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(prompt="changed background"),
                idempotency_key="generation-key-0002",
            )
        self.assertEqual((1, 1, 1), self._counts())

    def test_stale_revision_and_capacity_failure_insert_nothing(self):
        from services.canvas.generation.repository import create_generation
        from services.canvas.projects import CanvasRevisionConflict

        stale = self._request().model_copy(update={"revision": 2})
        with self.Session() as db, self.assertRaises(CanvasRevisionConflict):
            create_generation(
                db,
                project_id=self.ids["project"],
                request=stale,
                idempotency_key="generation-key-0003",
            )
        self.assertEqual((0, 0, 0), self._counts())

        failure = self.storage.CanvasStorageError(
            "canvas_storage_project_quota_exceeded",
            "quota",
        )
        with patch.object(self.storage, "assert_canvas_capacity", side_effect=failure):
            with self.Session() as db, self.assertRaises(self.storage.CanvasStorageError):
                create_generation(
                    db,
                    project_id=self.ids["project"],
                    request=self._request(),
                    idempotency_key="generation-key-0004",
                )
        self.assertEqual((0, 0, 0), self._counts())

    def test_cross_project_material_and_tampered_layout_are_rejected_without_rows(self):
        from canvas_models import CanvasAsset, CanvasProject
        from services.canvas.generation.repository import (
            CanvasGenerationValidationError,
            create_generation,
        )
        from services.canvas.project_state import empty_project_state_json

        other_project = str(uuid4())
        other_asset = str(uuid4())
        semantic, layout = empty_project_state_json()
        with self.Session() as db:
            db.add(
                CanvasProject(
                    id=other_project,
                    name="Other",
                    semantic_state=semantic,
                    layout_state=layout,
                )
            )
            db.add(
                CanvasAsset(
                    id=other_asset,
                    project_id=other_project,
                    asset_type="working",
                    relative_path=f"working/{other_asset}.png",
                    original_filename="other.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1,
                    height=1,
                    sha256="c" * 64,
                )
            )
            db.commit()

        cross_project = self._request(
            inputs=[
                {"assetId": other_asset, "inputRole": "product", "ordinal": 0}
            ]
        )
        for key, request in (
            ("generation-key-0005", cross_project),
            (
                "generation-key-0006",
                self._request(layoutHash="sha256:" + "0" * 64),
            ),
        ):
            with self.subTest(key=key):
                with self.Session() as db, self.assertRaises(CanvasGenerationValidationError):
                    create_generation(
                        db,
                        project_id=self.ids["project"],
                        request=request,
                        idempotency_key=key,
                    )
                self.assertEqual((0, 0, 0), self._counts())

    def test_second_key_is_rejected_while_project_has_active_generation(self):
        from services.canvas.generation.repository import (
            CanvasGenerationActiveConflict,
            create_generation,
        )

        with self.Session() as db:
            create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-key-0007",
            )
        with self.Session() as db, self.assertRaises(CanvasGenerationActiveConflict):
            create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(prompt="new paid request"),
                idempotency_key="generation-key-0008",
            )
        self.assertEqual((1, 1, 1), self._counts())

    def test_concurrent_same_key_requests_converge_to_one_generation(self):
        from services.canvas.generation.repository import create_generation

        request = self._request()

        def create_once(_index: int) -> tuple[str, bool]:
            with self.Session() as db:
                generation, created = create_generation(
                    db,
                    project_id=self.ids["project"],
                    request=request,
                    idempotency_key="generation-concurrent-key-01",
                )
                return generation.id, created

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create_once, range(2)))
        self.assertEqual(1, sum(1 for _identifier, created in results if created))
        self.assertEqual(1, len({identifier for identifier, _created in results}))
        self.assertEqual((1, 1, 1), self._counts())

    def test_transient_sqlite_writer_lock_retries_before_creating_one_generation(self):
        """A busy writer lease may retry, but the durable graph remains singular."""

        from services.canvas.generation.repository import create_generation

        with self.Session() as db:
            real_execute = db.execute
            failures = 0

            def locked_once(statement, *args, **kwargs):
                nonlocal failures
                if str(statement) == "BEGIN IMMEDIATE" and failures == 0:
                    failures += 1
                    raise OperationalError(
                        "BEGIN IMMEDIATE",
                        {},
                        sqlite3.OperationalError("database is locked"),
                    )
                return real_execute(statement, *args, **kwargs)

            with (
                patch.object(db, "execute", side_effect=locked_once),
                patch("services.canvas.generation.repository.time.sleep") as sleep,
            ):
                generation, created = create_generation(
                    db,
                    project_id=self.ids["project"],
                    request=self._request(),
                    idempotency_key="generation-busy-retry-key-01",
                )

        self.assertTrue(created)
        self.assertEqual(1, failures)
        sleep.assert_called_once_with(0.05)
        self.assertEqual((1, 1, 1), self._counts())
        with self.Session() as db:
            replay, replay_created = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-busy-retry-key-01",
            )
        self.assertFalse(replay_created)
        self.assertEqual(generation.id, replay.id)
        self.assertEqual((1, 1, 1), self._counts())

    def test_other_projects_include_existing_remaining_reservations(self):
        from services.canvas.generation.repository import create_generation

        first_ids = self.ids
        other_ids = self._seed_project()
        with self.Session() as db:
            create_generation(
                db,
                project_id=first_ids["project"],
                request=self._request(),
                idempotency_key="generation-reservation-key-01",
            )
        original_ids = self.ids
        self.ids = other_ids
        try:
            second_request = self._request()
        finally:
            self.ids = original_ids

        captured: list[tuple[int, int]] = []
        real_assert = self.storage.assert_canvas_capacity

        def observe_capacity(**kwargs):
            captured.append(
                (
                    kwargs["reserved_project_bytes"],
                    kwargs["reserved_total_bytes"],
                )
            )
            return real_assert(**kwargs)

        with patch.object(self.storage, "assert_canvas_capacity", side_effect=observe_capacity):
            with self.Session() as db:
                create_generation(
                    db,
                    project_id=other_ids["project"],
                    request=second_request,
                    idempotency_key="generation-reservation-key-02",
                )
        self.assertEqual(1, len(captured))
        self.assertEqual(0, captured[0][0])
        self.assertGreater(captured[0][1], 0)

    def test_reservation_debit_extend_and_release_are_atomic(self):
        from canvas_models import CanvasGeneration
        from services.canvas.generation.repository import (
            create_generation,
            debit_generation_reservation,
            extend_generation_reservation,
            release_generation_reservation,
        )

        with self.Session() as db:
            generation, _ = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-accounting-key-01",
            )
            generation_id = generation.id
            original = generation.storage_reservation_remaining_bytes
        with self.Session() as db:
            remaining = debit_generation_reservation(
                db,
                generation_id=generation_id,
                allocated_bytes=123,
            )
            db.commit()
        self.assertEqual(original - 123, remaining)

        captured: list[dict[str, int]] = []
        real_assert = self.storage.assert_canvas_capacity

        def observe(**kwargs):
            captured.append(kwargs)
            return real_assert(**kwargs)

        with patch.object(self.storage, "assert_canvas_capacity", side_effect=observe):
            with self.Session() as db:
                extended = extend_generation_reservation(
                    db,
                    generation_id=generation_id,
                    additional_bytes=456,
                )
        self.assertEqual(original - 123 + 456, extended)
        self.assertEqual(456, captured[0]["additional_bytes"])
        self.assertEqual(original - 123, captured[0]["reserved_project_bytes"])

        with self.Session() as db:
            release_generation_reservation(db, generation_id=generation_id)
            db.commit()
        with self.Session() as db:
            row = db.get(CanvasGeneration, generation_id)
            self.assertEqual(0, row.storage_reservation_remaining_bytes)
            self.assertEqual(original + 456, row.storage_reservation_bytes)

    def test_generation_derived_asset_debits_existing_reservation_once(self):
        from canvas_models import CanvasGeneration
        from services.canvas.assets import persist_derived_image
        from services.canvas.generation.repository import create_generation

        with self.Session() as db:
            generation, _ = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-derived-key-01",
            )
            generation_id = generation.id
            original = generation.storage_reservation_remaining_bytes
        image = Image.new("RGBA", (2, 2), (1, 2, 3, 255))
        encoded = io.BytesIO()
        image.save(encoded, format="PNG")
        data = encoded.getvalue()
        with self.Session() as db:
            asset = persist_derived_image(
                db,
                project_id=self.ids["project"],
                asset_type="generated_background",
                data=data,
                mime_type="image/png",
                source_asset_id=None,
                metadata={"stage": "provider-background"},
                processor_version="generation-test-v1",
                generation_id=generation_id,
            )
            db.commit()
            self.assertEqual(len(data), asset.byte_count)
        with self.Session() as db:
            row = db.get(CanvasGeneration, generation_id)
            self.assertEqual(
                original - len(data),
                row.storage_reservation_remaining_bytes,
            )

    def test_ordinary_derived_asset_cannot_consume_generation_reservation(self):
        from services.canvas.assets import (
            CanvasAssetPersistenceError,
            persist_derived_image,
        )
        from services.canvas.generation.repository import create_generation

        with self.Session() as db:
            generation, _ = create_generation(
                db,
                project_id=self.ids["project"],
                request=self._request(),
                idempotency_key="generation-protected-capacity-key-01",
            )
            reserved = generation.storage_reservation_remaining_bytes
        image = Image.new("RGBA", (2, 2), (9, 8, 7, 255))
        encoded = io.BytesIO()
        image.save(encoded, format="PNG")
        usage = self.storage.canvas_usage_bytes(project_id=self.ids["project"])
        with patch.object(
            self.storage,
            "CANVAS_PROJECT_QUOTA_BYTES",
            usage + reserved,
        ):
            with self.Session() as db, self.assertRaises(CanvasAssetPersistenceError):
                persist_derived_image(
                    db,
                    project_id=self.ids["project"],
                    asset_type="generated_background",
                    data=encoded.getvalue(),
                    mime_type="image/png",
                    source_asset_id=None,
                    metadata={},
                    processor_version="ordinary-test-v1",
                )


if __name__ == "__main__":
    unittest.main()
