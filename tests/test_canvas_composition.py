from __future__ import annotations

import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError


FIXTURE = (
    Path(__file__).parents[1]
    / "frontend"
    / "canvas"
    / "test"
    / "fixtures"
    / "composition-vectors.json"
)


class CanvasCompositionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_python_uses_the_shared_camel_case_v1_vectors(self):
        from services.canvas.composition import (
            canonical_layout_json,
            composition_layout_hash,
            map_product_to_board,
        )
        from services.canvas.composition_schema import CompositionLayout

        self.assertEqual(1, self.fixture["schemaVersion"])
        for vector in self.fixture["vectors"]:
            with self.subTest(vector=vector["name"]):
                layout = CompositionLayout.model_validate(vector["layout"])
                self.assertEqual(
                    vector["expectedCanonical"].encode("utf-8"),
                    canonical_layout_json(layout),
                )
                self.assertEqual(vector["expectedHash"], composition_layout_hash(layout))
                placement = map_product_to_board(
                    layout,
                    source_size=(
                        vector["sourceSize"]["width"],
                        vector["sourceSize"]["height"],
                    ),
                    output_size=(
                        vector["outputSize"]["width"],
                        vector["outputSize"]["height"],
                    ),
                )
                self.assertEqual(
                    vector["expectedPlacement"],
                    placement.model_dump(by_alias=True),
                )
                self.assertAlmostEqual(
                    placement.width / placement.height,
                    vector["sourceSize"]["width"] / vector["sourceSize"]["height"],
                    places=2,
                )
                angle = math.radians(placement.rotation)
                rotated_width = abs(placement.width * math.cos(angle)) + abs(
                    placement.height * math.sin(angle)
                )
                rotated_height = abs(placement.width * math.sin(angle)) + abs(
                    placement.height * math.cos(angle)
                )
                center_x = placement.x + placement.width / 2
                center_y = placement.y + placement.height / 2
                slot = layout.slot
                self.assertGreaterEqual(
                    center_x - rotated_width / 2,
                    slot.x * vector["outputSize"]["width"] - 1e-6,
                )
                self.assertLessEqual(
                    center_x + rotated_width / 2,
                    (slot.x + slot.width) * vector["outputSize"]["width"] + 1e-6,
                )
                self.assertGreaterEqual(
                    center_y - rotated_height / 2,
                    slot.y * vector["outputSize"]["height"] - 1e-6,
                )
                self.assertLessEqual(
                    center_y + rotated_height / 2,
                    (slot.y + slot.height) * vector["outputSize"]["height"] + 1e-6,
                )

    def test_layout_rejects_stretch_and_out_of_bounds_normalized_geometry(self):
        from services.canvas.composition_schema import CompositionLayout

        valid = self.fixture["vectors"][0]["layout"]
        for patch in (
            {"contain": False},
            {"slot": {"x": 0.8, "y": 0.1, "width": 0.3, "height": 0.8}},
            {"safeArea": {"top": 0.6, "right": 0.1, "bottom": 0.5, "left": 0.1}},
            {"relativeProductFraction": 0},
            {"rotation": 181},
        ):
            with self.subTest(patch=patch), self.assertRaises(ValidationError):
                CompositionLayout.model_validate({**valid, **patch})

    def test_group_hash_ignores_nonshared_scene_and_board_fields(self):
        from services.canvas.composition import canonical_layout_json, composition_layout_hash
        from services.canvas.composition_schema import CompositionLayout, CompositionSpec

        vector = self.fixture["vectors"][0]
        layout = CompositionLayout.model_validate(vector["layout"])
        spec = CompositionSpec.model_validate(
            {
                "schemaVersion": 1,
                "projectId": "project-a",
                "compositionGroupId": "group-a",
                "skuId": "sku-a",
                "productLayerId": "layer-a",
                "sourceAssetId": "working-a",
                "renderAssetId": "cutout-a",
                "allowOpaqueFallback": False,
                "layout": vector["layout"],
                "layoutHash": vector["expectedHash"],
                "sourceSize": vector["sourceSize"],
                "outputRatio": vector["outputRatio"],
                "background": "studio",
                "model": "person-a",
                "lighting": "softbox",
                "color": "warm",
                "decoration": "petals",
            }
        )
        self.assertEqual(vector["expectedHash"], composition_layout_hash(spec.layout))
        self.assertNotIn(b"studio", canonical_layout_json(layout))

    def test_composition_state_rejects_group_membership_hash_and_unlocked_products(self):
        from services.canvas.composition import (
            CompositionValidationError,
            validate_composition_state,
        )
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState

        semantic, layout = self._valid_states()
        validate_composition_state(semantic, layout)

        cases = []
        wrong_hash_wire = semantic.model_dump(by_alias=True)
        wrong_hash_wire["compositionGroups"][0]["layoutHash"] = "sha256:" + "0" * 64
        wrong_hash = CanvasSemanticState.model_validate(wrong_hash_wire)
        cases.append(("hash", wrong_hash, layout))
        wrong_group_wire = layout.model_dump(by_alias=True)
        wrong_group_wire["productLayers"][1]["compositionGroupId"] = "other-group"
        wrong_group = CanvasLayoutState.model_validate(wrong_group_wire)
        cases.append(("group", semantic, wrong_group))
        unlocked_wire = layout.model_dump(by_alias=True)
        unlocked_wire["productLayers"][1]["locked"] = False
        unlocked = CanvasLayoutState.model_validate(unlocked_wire)
        cases.append(("locked", semantic, unlocked))

        for label, candidate_semantic, candidate_layout in cases:
            with self.subTest(case=label), self.assertRaises(CompositionValidationError):
                validate_composition_state(candidate_semantic, candidate_layout)

    def test_composition_specs_enforce_project_asset_lineage_and_main_fallback(self):
        from services.canvas.composition import (
            CompositionValidationError,
            build_composition_specs,
        )

        semantic, layout = self._valid_states()
        vector = self.fixture["vectors"][0]
        specs = build_composition_specs(
            project_id="project-a",
            semantic_state=semantic,
            layout_state=layout,
            sku_reference_asset_ids={"sku-a": None},
            assets={
                "working-main": {
                    "projectId": "project-a",
                    "assetType": "working",
                    "sourceAssetId": "source-main",
                    "width": 1200,
                    "height": 600,
                },
                "cutout-main": {
                    "projectId": "project-a",
                    "assetType": "cutout",
                    "sourceAssetId": "working-main",
                    "width": 1200,
                    "height": 600,
                },
            },
            output_ratios={"sku-a": vector["outputRatio"]},
        )
        self.assertEqual(2, len(specs))
        sku_spec = next(spec for spec in specs if spec.sku_id == "sku-a")
        self.assertEqual("working-main", sku_spec.source_asset_id)
        self.assertEqual("cutout-main", sku_spec.render_asset_id)

        cross_project = {
            "working-main": {
                "projectId": "project-b",
                "assetType": "working",
                "sourceAssetId": "source-main",
                "width": 1200,
                "height": 600,
            },
            "cutout-main": {
                "projectId": "project-a",
                "assetType": "cutout",
                "sourceAssetId": "working-main",
                "width": 1200,
                "height": 600,
            },
        }
        with self.assertRaises(CompositionValidationError):
            build_composition_specs(
                project_id="project-a",
                semantic_state=semantic,
                layout_state=layout,
                sku_reference_asset_ids={"sku-a": None},
                assets=cross_project,
                output_ratios={"sku-a": vector["outputRatio"]},
            )

        direct_opaque = {
            "working-main": {
                "projectId": "project-a",
                "assetType": "working",
                "sourceAssetId": "source-main",
                "width": 1200,
                "height": 600,
                "transparencyStatus": "opaque",
            }
        }
        opaque_layout = layout.model_copy(deep=True)
        for layer in opaque_layout.product_layers:
            layer.render_asset_id = "working-main"
        with self.assertRaises(CompositionValidationError):
            build_composition_specs(
                project_id="project-a",
                semantic_state=semantic,
                layout_state=opaque_layout,
                sku_reference_asset_ids={"sku-a": None},
                assets=direct_opaque,
                output_ratios={"sku-a": vector["outputRatio"]},
            )

    def test_schema_v1_migrates_node_fallback_into_strict_product_layer(self):
        from services.canvas.project_state import upgrade_project_state

        semantic, layout = self._valid_states()
        layout_wire = layout.model_dump(by_alias=True)
        layout_wire["productLayers"][0]["allowOpaqueFallback"] = False
        semantic_wire = semantic.model_dump(by_alias=True)
        semantic_wire["nodes"].append(
            {
                "id": "main-product-source",
                "kind": "product_source",
                "managedBy": None,
                "skuId": None,
                "assetId": "working-main",
                "modelProfileId": None,
                "prompt": None,
                "compositionGroupId": None,
                "textSnapshotId": None,
                "outputBoardId": None,
                "parameters": {"allowOpaqueFallback": True},
            }
        )
        upgraded_semantic, upgraded_layout, version = upgrade_project_state(
            semantic_state=semantic_wire,
            layout_state=layout_wire,
            schema_version=1,
        )
        self.assertEqual(1, version)
        self.assertTrue(upgraded_layout["productLayers"][0]["allowOpaqueFallback"])
        self.assertNotIn(
            "allowOpaqueFallback",
            next(
                node["parameters"]
                for node in upgraded_semantic["nodes"]
                if node["id"] == "main-product-source"
            ),
        )

    def test_schema_v1_migrates_legacy_group_transform_into_shared_layout(self):
        from services.canvas.composition import (
            composition_layout_hash,
            validate_composition_state,
        )
        from services.canvas.project_state import upgrade_project_state
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState

        semantic, layout = self._valid_states()
        semantic_wire = semantic.model_dump(by_alias=True)
        legacy_group = semantic_wire["compositionGroups"][0]
        legacy_group.pop("layout")
        legacy_group["layoutHash"] = "legacy-transform"
        upgraded_semantic, upgraded_layout, _ = upgrade_project_state(
            semantic_state=semantic_wire,
            layout_state=layout.model_dump(by_alias=True),
            schema_version=1,
        )
        migrated_semantic = CanvasSemanticState.model_validate(upgraded_semantic)
        migrated_layout = CanvasLayoutState.model_validate(upgraded_layout)
        group = migrated_semantic.composition_groups[0]
        self.assertEqual(0.9, group.layout.baseline)
        self.assertEqual(0.68, group.layout.relative_product_fraction)
        self.assertEqual(group.layout_hash, composition_layout_hash(group.layout))
        validate_composition_state(migrated_semantic, migrated_layout)

    def test_backend_schema_rejects_duplicate_group_and_product_layer_ids(self):
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState

        semantic, layout = self._valid_states()
        duplicate_groups = semantic.model_dump(by_alias=True)
        duplicate_groups["compositionGroups"].append(
            deepcopy(duplicate_groups["compositionGroups"][0])
        )
        with self.assertRaisesRegex(ValidationError, "composition group ids"):
            CanvasSemanticState.model_validate(duplicate_groups)

        duplicate_layers = layout.model_dump(by_alias=True)
        duplicate_layers["productLayers"].append(
            deepcopy(duplicate_layers["productLayers"][0])
        )
        with self.assertRaisesRegex(ValidationError, "product layer ids"):
            CanvasLayoutState.model_validate(duplicate_layers)

    def _valid_states(self):
        from services.canvas.composition_schema import CompositionLayout
        from services.canvas.composition import composition_layout_hash
        from services.canvas.schemas import (
            CanvasLayoutState,
            CanvasSemanticState,
            empty_layout_state,
            empty_semantic_state,
        )

        layout_contract = CompositionLayout.model_validate(
            self.fixture["vectors"][0]["layout"]
        )
        semantic_wire = empty_semantic_state().model_dump(by_alias=True)
        semantic_wire["compositionGroups"].append(
            {
                "id": "group-a",
                "skuIds": ["sku-a"],
                "productLayerIds": ["main-layer", "sku-layer"],
                "layout": layout_contract.model_dump(by_alias=True),
                "layoutHash": composition_layout_hash(layout_contract),
            }
        )
        layout_wire = empty_layout_state().model_dump(by_alias=True)
        layout_wire["objectTransforms"] = {
            "main-transform": {"x": 0.5, "y": 0.9, "scale": 0.68, "rotation": 0},
            "sku-transform": {"x": 0.5, "y": 0.9, "scale": 0.68, "rotation": 0},
        }
        layout_wire["productLayers"] = [
            {
                "id": "main-layer",
                "sourceAssetId": "working-main",
                "renderAssetId": "cutout-main",
                "allowOpaqueFallback": False,
                "skuId": None,
                "compositionGroupId": "group-a",
                "transformId": "main-transform",
                "locked": True,
            },
            {
                "id": "sku-layer",
                "sourceAssetId": "working-main",
                "renderAssetId": "cutout-main",
                "allowOpaqueFallback": False,
                "skuId": "sku-a",
                "compositionGroupId": "group-a",
                "transformId": "sku-transform",
                "locked": True,
            },
        ]
        return (
            CanvasSemanticState.model_validate(semantic_wire),
            CanvasLayoutState.model_validate(layout_wire),
        )


class CanvasCompositionRequestMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import database

        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{(Path(self.tmp.name) / 'composition.db').as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = str(self.engine.url)
        try:
            database.init_db()
        finally:
            database.engine, database.DATABASE_URL = original

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def test_real_project_state_request_and_api_preserve_legacy_fallback(self):
        from canvas_models import CanvasAsset
        from routers.canvas.projects import ProjectStateRequest, save_project_state
        from services.canvas.projects import create_project
        from services.canvas.schemas import empty_layout_state, empty_semantic_state

        with self.Session() as db:
            project = create_project(db, name="Fallback migration")
            working_id = "00000000-0000-0000-0000-000000000101"
            db.add(
                CanvasAsset(
                    id=working_id,
                    project_id=project.id,
                    asset_type="working",
                    relative_path=f"working/{working_id}.png",
                    original_filename="working.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1,
                    height=1,
                    sha256="a" * 64,
                    source_asset_id=None,
                    transparency_status="opaque",
                    metadata_json="{}",
                )
            )
            db.commit()

            semantic = empty_semantic_state().model_dump(by_alias=True)
            semantic["nodes"].append(
                {
                    "id": "main-product-source",
                    "kind": "product_source",
                    "managedBy": None,
                    "skuId": None,
                    "assetId": working_id,
                    "modelProfileId": None,
                    "prompt": None,
                    "compositionGroupId": None,
                    "textSnapshotId": None,
                    "outputBoardId": None,
                    "parameters": {"allowOpaqueFallback": True},
                }
            )
            semantic["nodes"].append(
                {
                    "id": "main-product-cutout",
                    "kind": "auto_cutout",
                    "managedBy": None,
                    "skuId": None,
                    "assetId": working_id,
                    "modelProfileId": None,
                    "prompt": None,
                    "compositionGroupId": None,
                    "textSnapshotId": None,
                    "outputBoardId": None,
                    "parameters": {},
                }
            )
            semantic["edges"].append(
                {
                    "id": "main-product-source-cutout",
                    "kind": "product_asset",
                    "sourceNodeId": "main-product-source",
                    "sourcePort": "product",
                    "targetNodeId": "main-product-cutout",
                    "targetPort": "reference",
                    "skuId": None,
                }
            )
            layout = empty_layout_state().model_dump(by_alias=True)
            layout["nodePositions"] = {
                "main-product-source": {"x": 0.1, "y": 0.1},
                "main-product-cutout": {"x": 0.3, "y": 0.1},
            }
            layout["objectTransforms"]["main-product"] = {
                "x": 0.5,
                "y": 0.5,
                "scale": 1.0,
                "rotation": 0.0,
            }
            layout["productLayers"].append(
                {
                    "id": "main-product",
                    "sourceAssetId": working_id,
                    "renderAssetId": working_id,
                    "skuId": None,
                    "compositionGroupId": None,
                    "transformId": "main-product",
                    "locked": True,
                }
            )
            payload = ProjectStateRequest.model_validate(
                {
                    "revision": 1,
                    "semanticState": semantic,
                    "layoutState": layout,
                }
            )
            self.assertTrue(payload.layout_state.product_layers[0].allow_opaque_fallback)
            self.assertNotIn(
                "allowOpaqueFallback",
                payload.semantic_state.nodes[0].parameters,
            )

            response = save_project_state(project.id, payload, db)
            self.assertTrue(
                response["project"]["layoutState"]["productLayers"][0][
                    "allowOpaqueFallback"
                ]
            )
            source_node = next(
                node
                for node in response["project"]["semanticState"]["nodes"]
                if node["id"] == "main-product-source"
            )
            self.assertNotIn("allowOpaqueFallback", source_node["parameters"])


if __name__ == "__main__":
    unittest.main()
