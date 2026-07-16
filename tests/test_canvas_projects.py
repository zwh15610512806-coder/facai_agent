import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Column, String, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker


PROJECT_DIRECTORIES = {
    "source",
    "working",
    "preview",
    "cutout",
    "generated",
    "composed",
    "exports",
    "tmp",
}

TemporarySubjectBase = declarative_base()


class TemporaryCanvasEventSubject(TemporarySubjectBase):
    __tablename__ = "temporary_canvas_event_subjects"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False)


class CanvasProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "canvas-projects"

    def tearDown(self):
        self.tmp.cleanup()

    def _storage(self):
        self.assertIsNotNone(
            importlib.util.find_spec("services.canvas"),
            "services.canvas must exist before project storage can be used",
        )
        self.assertIsNotNone(
            importlib.util.find_spec("services.canvas.storage"),
            "services.canvas.storage must implement the storage boundary",
        )
        from services.canvas import storage

        return storage

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

    def test_project_root_is_absolute_contained_and_does_not_create_directories(self):
        storage = self._storage()
        project_id = str(uuid4())
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.project_root(project_id)

        self.assertTrue(root.is_absolute())
        self.assertEqual((self.data_root / project_id).resolve(), root)
        self.assertFalse(root.exists())

    def test_ensure_project_tree_creates_only_declared_directories_idempotently(self):
        storage = self._storage()
        project_id = str(uuid4())
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(project_id)
            repeated_root = storage.ensure_project_tree(project_id)

        self.assertEqual(root, repeated_root)
        self.assertEqual(PROJECT_DIRECTORIES, {path.name for path in root.iterdir()})
        self.assertTrue(all(path.is_dir() for path in root.iterdir()))

    def test_invalid_or_noncanonical_uuid_is_rejected_without_creating_data_root(self):
        storage = self._storage()
        valid = uuid4()
        invalid_values = (
            "",
            "not-a-uuid",
            "../escape",
            f"{valid}/source",
            valid.hex,
            "{" + str(valid) + "}",
        )
        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            for value in invalid_values:
                with self.subTest(value=value):
                    with self.assertRaises((TypeError, ValueError)):
                        storage.project_root(value)
                    with self.assertRaises((TypeError, ValueError)):
                        storage.ensure_project_tree(value)
                    with self.assertRaises((TypeError, ValueError)):
                        storage.remove_project_tree(value)

        self.assertFalse(self.data_root.exists())

    def test_project_root_symlink_escape_is_rejected(self):
        storage = self._storage()
        project_id = str(uuid4())
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        self.data_root.mkdir()
        project_link = self.data_root / project_id
        self._make_directory_link(project_link, outside)

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            with self.assertRaises(ValueError):
                storage.project_root(project_id)
            with self.assertRaises(ValueError):
                storage.ensure_project_tree(project_id)
            with self.assertRaises(ValueError):
                storage.remove_project_tree(project_id)

        self.assertTrue(outside.exists())

    def test_required_subdirectory_symlink_escape_is_rejected(self):
        storage = self._storage()
        project_id = str(uuid4())
        outside = Path(self.tmp.name) / "outside-child"
        outside.mkdir()
        project_dir = self.data_root / project_id
        project_dir.mkdir(parents=True)
        source_link = project_dir / "source"
        self._make_directory_link(source_link, outside)

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            with self.assertRaises(ValueError):
                storage.ensure_project_tree(project_id)

        self.assertEqual([], list(outside.iterdir()))

    def test_remove_project_tree_is_contained_and_idempotent(self):
        storage = self._storage()
        project_id = str(uuid4())
        outside = Path(self.tmp.name) / "outside-sentinel"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")

        with patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root)):
            root = storage.ensure_project_tree(project_id)
            (root / "tmp" / "runtime.txt").write_text("runtime", encoding="utf-8")
            storage.remove_project_tree(project_id)
            storage.remove_project_tree(project_id)

        self.assertFalse(root.exists())
        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))


class CanvasEventAppendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-events.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        import database

        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        try:
            database.init_db()
        finally:
            database.engine, database.DATABASE_URL = original

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _events(self):
        self.assertIsNotNone(
            importlib.util.find_spec("services.canvas.events"),
            "services.canvas.events must provide append_canvas_event",
        )
        from services.canvas import events

        return events

    @staticmethod
    def _create_project(db, project_id: str | None = None):
        from canvas_models import CanvasProject

        project = CanvasProject(id=project_id or str(uuid4()), name="Event project")
        db.add(project)
        db.commit()
        return project

    def test_append_without_subject_is_deterministic_and_does_not_commit(self):
        events = self._events()
        from canvas_models import CanvasEvent

        with self.Session() as db:
            project = self._create_project(db)
            payload = {"z": 1, "a": ["中文", True, None]}
            with patch.object(db, "commit") as commit_spy:
                event = events.append_canvas_event(
                    db,
                    project_id=project.id,
                    event_type="project.created",
                    payload=payload,
                )
                commit_spy.assert_not_called()

            self.assertIsNone(event.id)
            self.assertIn(event, db.new)
            self.assertEqual('{"a":["中文",true,null],"z":1}', event.payload_json)
            payload["z"] = 2
            self.assertEqual('{"a":["中文",true,null],"z":1}', event.payload_json)

            db.commit()
            saved_id = event.id

        with self.Session() as db:
            saved = db.get(CanvasEvent, saved_id)
            self.assertIsNotNone(saved)
            self.assertEqual("project.created", saved.event_type)
            self.assertEqual('{"a":["中文",true,null],"z":1}', saved.payload_json)

    def test_missing_project_is_rejected(self):
        events = self._events()

        with self.Session() as db:
            with self.assertRaises(events.CanvasEventValidationError):
                events.append_canvas_event(
                    db,
                    project_id=str(uuid4()),
                    event_type="project.missing",
                    payload={"revision": 1},
                )
            self.assertEqual(0, len(db.new))

    def test_unavailable_table_and_orphan_subjects_are_rejected(self):
        events = self._events()

        with self.Session() as db:
            project = self._create_project(db)
            for subject_field in ("generation_id", "item_id"):
                with self.subTest(subject_field=subject_field):
                    with self.assertRaises(events.CanvasEventValidationError):
                        events.append_canvas_event(
                            db,
                            project_id=project.id,
                            event_type="subject.unavailable",
                            payload={"subjectField": subject_field},
                            **{subject_field: str(uuid4())},
                        )

            with self.assertRaises(events.CanvasEventValidationError):
                events.append_canvas_event(
                    db,
                    project_id=project.id,
                    event_type="operation.orphan",
                    payload={"status": "pending"},
                    operation_id=str(uuid4()),
                )

            with patch.dict(events.SUBJECT_MODEL_REGISTRY):
                events.register_canvas_event_subject_model(
                    "item_id",
                    TemporaryCanvasEventSubject,
                )
                with self.assertRaises(events.CanvasEventValidationError):
                    events.append_canvas_event(
                        db,
                        project_id=project.id,
                        event_type="item.table-missing",
                        payload={"status": "pending"},
                        item_id=str(uuid4()),
                    )

                TemporarySubjectBase.metadata.create_all(self.engine)
                with self.assertRaises(events.CanvasEventValidationError):
                    events.append_canvas_event(
                        db,
                        project_id=project.id,
                        event_type="item.orphan",
                        payload={"status": "pending"},
                        item_id=str(uuid4()),
                    )

    def test_registered_subject_must_belong_to_event_project(self):
        events = self._events()
        TemporarySubjectBase.metadata.create_all(self.engine)

        with self.Session() as db:
            project_a = self._create_project(db)
            project_b = self._create_project(db)
            subject = TemporaryCanvasEventSubject(
                id=str(uuid4()),
                project_id=project_b.id,
            )
            db.add(subject)
            db.commit()

            with patch.dict(events.SUBJECT_MODEL_REGISTRY):
                events.register_canvas_event_subject_model(
                    "operation_id",
                    TemporaryCanvasEventSubject,
                )
                with self.assertRaises(events.CanvasEventValidationError):
                    events.append_canvas_event(
                        db,
                        project_id=project_a.id,
                        event_type="operation.cross-project",
                        payload={"status": "running"},
                        operation_id=subject.id,
                    )

                event = events.append_canvas_event(
                    db,
                    project_id=project_b.id,
                    event_type="operation.running",
                    payload={"status": "running"},
                    operation_id=subject.id,
                )
                db.commit()

            self.assertEqual(project_b.id, event.project_id)
            self.assertEqual(subject.id, event.operation_id)

    def test_payload_must_be_json_safe_bounded_and_not_full_project_state(self):
        events = self._events()
        from canvas_models import CanvasEvent

        with self.Session() as db:
            project = self._create_project(db)
            invalid_payloads = (
                ["not", "an", "object"],
                {"blob": b"binary"},
                {"number": float("nan")},
                {1: "non-string-key"},
                {"tuple": (1, 2)},
                {"semanticState": {"nodes": []}},
                {"layout_state": {"node_positions": {}}},
                {"nodes": []},
                {"outputBoards": []},
                {"productLayers": []},
                {"versionHistory": []},
                {"summary": "x" * events.MAX_EVENT_PAYLOAD_BYTES},
            )
            for payload in invalid_payloads:
                with self.subTest(payload_type=type(payload).__name__):
                    with self.assertRaises(events.CanvasEventValidationError):
                        events.append_canvas_event(
                            db,
                            project_id=project.id,
                            event_type="payload.invalid",
                            payload=payload,
                        )

            self.assertEqual([], db.execute(select(CanvasEvent)).scalars().all())
            self.assertEqual(0, len(db.new))


class CanvasProjectDomainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-projects.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        import database

        original = (database.engine, database.DATABASE_URL)
        database.engine = self.engine
        database.DATABASE_URL = f"sqlite:///{self.db_path.as_posix()}"
        try:
            database.init_db()
        finally:
            database.engine, database.DATABASE_URL = original

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    @staticmethod
    def _empty_states():
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState

        semantic = CanvasSemanticState.model_validate(
            {
                "nodes": [],
                "edges": [],
                "outputBoards": [],
                "mode": "complete-set",
                "advancedCustomized": False,
                "completeSet": {"selectedOutputTypes": [], "outputs": []},
                "compositionGroups": [],
            }
        )
        layout = CanvasLayoutState.model_validate(
            {
                "nodePositions": {},
                "objectTransforms": {},
                "viewport": {"x": 0, "y": 0, "zoom": 1},
                "productLayers": [],
                "textSnapshots": [],
            }
        )
        return semantic, layout

    @staticmethod
    def _semantic_payload(**overrides):
        payload = {
            "nodes": [],
            "edges": [],
            "outputBoards": [],
            "mode": "complete-set",
            "advancedCustomized": False,
            "completeSet": {"selectedOutputTypes": [], "outputs": []},
            "compositionGroups": [],
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def _layout_payload(**overrides):
        payload = {
            "nodePositions": {},
            "objectTransforms": {},
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "productLayers": [],
            "textSnapshots": [],
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def _add_asset(db, *, project_id: str, asset_id: str | None = None):
        from canvas_models import CanvasAsset

        asset_id = asset_id or str(uuid4())
        asset = CanvasAsset(
            id=asset_id,
            project_id=project_id,
            asset_type="source",
            relative_path=f"source/{asset_id}.png",
            original_filename="source.png",
            mime_type="image/png",
            byte_count=10,
            width=2,
            height=2,
            sha256=asset_id.replace("-", "")[:64].ljust(64, "0"),
        )
        db.add(asset)
        db.commit()
        return asset

    def test_new_project_has_canonical_empty_v1_state_and_revision_one(self):
        from services.canvas.projects import create_project, get_project_snapshot

        with self.Session() as db:
            project = create_project(db, name="  Summer launch  ")
            snapshot = get_project_snapshot(db, project_id=project.id)

        self.assertEqual("Summer launch", snapshot.project.name)
        self.assertEqual(1, snapshot.revision)
        self.assertEqual([], snapshot.skus)
        self.assertEqual([], snapshot.semantic_state.nodes)
        self.assertEqual([], snapshot.semantic_state.output_boards)
        self.assertEqual([], snapshot.semantic_state.complete_set.selected_output_types)
        self.assertEqual(1, snapshot.project.schema_version)
        self.assertEqual(
            '{"advancedCustomized":false,"completeSet":{"outputs":[],"selectedOutputTypes":[]},'
            '"compositionGroups":[],"edges":[],"mode":"complete-set","nodes":[],"outputBoards":[]}',
            snapshot.project.semantic_state,
        )

    def test_wire_schema_is_strict_camel_case_and_round_trips_canonically(self):
        from pydantic import ValidationError

        from services.canvas.project_state import dump_project_state, load_semantic_state
        from services.canvas.schemas import CanvasSemanticState

        semantic, _layout = self._empty_states()
        encoded = dump_project_state(semantic)
        self.assertEqual(encoded, dump_project_state(load_semantic_state(encoded)))
        self.assertEqual(
            semantic.model_dump(by_alias=True),
            load_semantic_state(encoded).model_dump(by_alias=True),
        )
        invalid = semantic.model_dump(by_alias=True)
        invalid["output_boards"] = invalid.pop("outputBoards")
        with self.assertRaises(ValidationError):
            CanvasSemanticState.model_validate(invalid)

    def test_shared_python_typescript_v1_fixture_round_trips_without_drift(self):
        from services.canvas.project_state import dump_project_state
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState

        fixture_path = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "canvas"
            / "test"
            / "fixtures"
            / "project-state-v1.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(1, fixture["schemaVersion"])
        semantic = CanvasSemanticState.model_validate(fixture["semanticState"])
        layout = CanvasLayoutState.model_validate(fixture["layoutState"])
        self.assertEqual(fixture["semanticState"], json.loads(dump_project_state(semantic)))
        self.assertEqual(fixture["layoutState"], json.loads(dump_project_state(layout)))

    def test_metadata_state_and_sku_writes_share_one_project_revision(self):
        from services.canvas.projects import (
            create_project,
            create_sku,
            save_project_state,
            update_project_metadata,
            update_sku,
        )
        from services.canvas.schemas import SkuCreate, SkuUpdate

        semantic, layout = self._empty_states()
        with self.Session() as db:
            project = create_project(db, name="Revision project")
            renamed = update_project_metadata(
                db,
                project_id=project.id,
                expected_revision=1,
                name="Renamed project",
            )
            saved = save_project_state(
                db,
                project_id=project.id,
                expected_revision=2,
                semantic_state=semantic,
                layout_state=layout,
            )
            created = create_sku(
                db,
                project_id=project.id,
                expected_revision=3,
                request=SkuCreate.model_validate(
                    {"name": "Vanilla", "prompt": "clean packshot", "config": {}}
                ),
            )
            sku_id = created.skus[0].id
            updated = update_sku(
                db,
                project_id=project.id,
                sku_id=sku_id,
                expected_revision=4,
                request=SkuUpdate.model_validate({"name": "Vanilla XL"}),
            )

        self.assertEqual([2, 3, 4, 5], [renamed.revision, saved.revision, created.revision, updated.revision])
        self.assertEqual("Vanilla XL", updated.skus[0].name)

    def test_create_sku_revalidates_mutated_request_before_database_writes(self):
        from pydantic import ValidationError
        from sqlalchemy import func

        from canvas_models import CanvasEvent, CanvasProject, CanvasProjectSku
        from services.canvas.projects import create_project, create_sku
        from services.canvas.schemas import SkuCreate

        mutations = {
            "fabric-marker": {"objects": []},
            "remote-url": {"source": "https://evil.example/result.png"},
        }
        with self.Session() as db:
            for label, mutation in mutations.items():
                project = create_project(db, name=f"Mutated create request {label}")
                request = SkuCreate.model_validate(
                    {
                        "name": f"Unsafe {label}",
                        "config": {"nested": {"safe": True}},
                    }
                )
                request.config["nested"].update(mutation)

                with self.subTest(label=label):
                    with self.assertRaises(ValidationError):
                        create_sku(
                            db,
                            project_id=project.id,
                            expected_revision=1,
                            request=request,
                        )

                    revision = db.execute(
                        select(CanvasProject.revision).where(CanvasProject.id == project.id)
                    ).scalar_one()
                    event_count = db.execute(
                        select(func.count(CanvasEvent.id)).where(CanvasEvent.project_id == project.id)
                    ).scalar_one()
                    sku_count = db.execute(
                        select(func.count(CanvasProjectSku.id)).where(
                            CanvasProjectSku.project_id == project.id
                        )
                    ).scalar_one()
                    self.assertEqual((1, 1, 0), (revision, event_count, sku_count))

    def test_update_sku_revalidates_mutated_request_before_database_writes(self):
        from pydantic import ValidationError
        from sqlalchemy import func

        from canvas_models import CanvasEvent, CanvasProject, CanvasProjectSku
        from services.canvas.projects import create_project, create_sku, update_sku
        from services.canvas.schemas import SkuCreate, SkuUpdate

        mutations = {
            "fabric-marker": {"objects": []},
            "remote-url": {"source": "https://evil.example/result.png"},
        }
        with self.Session() as db:
            for label, mutation in mutations.items():
                project = create_project(db, name=f"Mutated update request {label}")
                asset = self._add_asset(db, project_id=project.id)
                created = create_sku(
                    db,
                    project_id=project.id,
                    expected_revision=1,
                    request=SkuCreate.model_validate(
                        {
                            "name": "Original",
                            "referenceAssetId": asset.id,
                            "config": {"theme": "original"},
                        }
                    ),
                )
                sku_id = created.skus[0].id
                request = SkuUpdate.model_validate(
                    {
                        "referenceAssetId": None,
                        "config": {"nested": {"safe": True}},
                    }
                )
                request.config["nested"].update(mutation)

                with self.subTest(label=label):
                    with self.assertRaises(ValidationError):
                        update_sku(
                            db,
                            project_id=project.id,
                            sku_id=sku_id,
                            expected_revision=2,
                            request=request,
                        )

                    revision = db.execute(
                        select(CanvasProject.revision).where(CanvasProject.id == project.id)
                    ).scalar_one()
                    event_count = db.execute(
                        select(func.count(CanvasEvent.id)).where(CanvasEvent.project_id == project.id)
                    ).scalar_one()
                    stored_config, stored_reference = db.execute(
                        select(
                            CanvasProjectSku.config_json,
                            CanvasProjectSku.reference_asset_id,
                        ).where(CanvasProjectSku.id == sku_id)
                    ).one()
                    self.assertEqual(
                        (2, 2, '{"theme":"original"}', asset.id),
                        (revision, event_count, stored_config, stored_reference),
                    )

    def test_update_sku_revalidation_preserves_patch_fields_and_explicit_null(self):
        from services.canvas.projects import create_project, create_sku, update_sku
        from services.canvas.schemas import SkuCreate, SkuUpdate

        with self.Session() as db:
            project = create_project(db, name="Patch semantics")
            asset = self._add_asset(db, project_id=project.id)
            created = create_sku(
                db,
                project_id=project.id,
                expected_revision=1,
                request=SkuCreate.model_validate(
                    {
                        "name": "Original",
                        "referenceAssetId": asset.id,
                        "prompt": "keep prompt",
                        "config": {"theme": "keep"},
                    }
                ),
            )
            sku_id = created.skus[0].id
            renamed = update_sku(
                db,
                project_id=project.id,
                sku_id=sku_id,
                expected_revision=2,
                request=SkuUpdate.model_validate({"name": "Renamed"}),
            )
            renamed_values = (
                renamed.revision,
                renamed.skus[0].reference_asset_id,
                renamed.skus[0].prompt,
                json.loads(renamed.skus[0].config_json),
            )
            cleared = update_sku(
                db,
                project_id=project.id,
                sku_id=sku_id,
                expected_revision=3,
                request=SkuUpdate.model_validate({"referenceAssetId": None}),
            )
            cleared_values = (
                cleared.revision,
                cleared.skus[0].reference_asset_id,
                cleared.skus[0].name,
                cleared.skus[0].prompt,
                json.loads(cleared.skus[0].config_json),
            )

        self.assertEqual((3, asset.id, "keep prompt", {"theme": "keep"}), renamed_values)
        self.assertEqual((4, None, "Renamed", "keep prompt", {"theme": "keep"}), cleared_values)

    def test_all_foundation_node_kinds_and_later_slice_fields_round_trip(self):
        from services.canvas.project_state import dump_project_state, load_layout_state, load_semantic_state
        from services.canvas.schemas import NODE_KINDS, CanvasLayoutState, CanvasSemanticState

        sku_id = str(uuid4())
        asset_id = str(uuid4())
        model_id = str(uuid4())
        group_id = str(uuid4())
        board_id = str(uuid4())
        node_ids = {kind: str(uuid4()) for kind in NODE_KINDS}
        semantic_payload = self._semantic_payload(
            nodes=[
                {
                    "id": node_ids[kind],
                    "kind": kind,
                    "managedBy": "complete-set" if index == 0 else None,
                    "skuId": sku_id if kind in {"sku_reference", "sku_output"} else None,
                    "assetId": asset_id if kind in {"product_source", "sku_reference"} else None,
                    "modelProfileId": model_id if kind == "model_generation" else None,
                    "prompt": "clean scene" if kind in {"prompt", "model_generation"} else None,
                    "compositionGroupId": group_id if kind == "composition_group" else None,
                    "textSnapshotId": str(uuid4()) if kind == "text_layer" else None,
                    "outputBoardId": board_id if kind.endswith("_output") else None,
                    "parameters": {},
                }
                for index, kind in enumerate(NODE_KINDS)
            ],
            edges=[
                {
                    "id": str(uuid4()),
                    "kind": "product_asset",
                    "sourceNodeId": node_ids["product_source"],
                    "sourcePort": "product",
                    "targetNodeId": node_ids["model_generation"],
                    "targetPort": "reference",
                    "skuId": sku_id,
                }
            ],
            outputBoards=[
                {
                    "id": board_id,
                    "outputNodeId": node_ids["sku_output"],
                    "outputType": "sku",
                    "skuId": sku_id,
                    "sortOrder": 0,
                    "selectedResultAssetId": asset_id,
                }
            ],
            completeSet={
                "selectedOutputTypes": ["sku"],
                "outputs": [
                    {
                        "outputType": "sku",
                        "skuId": sku_id,
                        "quantity": 1,
                        "aspectRatio": "1:1",
                        "width": 1024,
                        "height": 1024,
                        "prompt": "white studio",
                        "modelProfileId": model_id,
                        "modelParameters": {},
                        "referenceAssetId": asset_id,
                        "compositionGroupId": group_id,
                    }
                ],
            },
            compositionGroups=[
                {
                    "id": group_id,
                    "skuIds": [sku_id],
                    "productLayerIds": ["product-layer-1"],
                    "layoutHash": "sha256:5efd4a7c6ec24de6fb15f2ade46af5288e86a41570df4503f69b2b426af48884",
                    "layout": {
                        "slot": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                        "anchor": {"x": 0.5, "y": 0.5},
                        "baseline": 0.5,
                        "relativeProductFraction": 0.75,
                        "contain": True,
                        "safeArea": {"top": 0.05, "right": 0.05, "bottom": 0.05, "left": 0.05},
                        "rotation": 0.0,
                    },
                }
            ],
        )
        layout_payload = self._layout_payload(
            nodePositions={node_ids["product_source"]: {"x": 0.25, "y": 0.5}},
            objectTransforms={
                "product-layer-1": {
                    "x": 0.5,
                    "y": 0.5,
                    "scale": 0.75,
                    "rotation": 0,
                }
            },
            productLayers=[
                {
                    "id": "product-layer-1",
                    "sourceAssetId": asset_id,
                    "renderAssetId": asset_id,
                    "allowOpaqueFallback": False,
                    "skuId": sku_id,
                    "compositionGroupId": group_id,
                    "transformId": "product-layer-1",
                    "locked": True,
                }
            ],
            textSnapshots=[
                {
                    "id": "text-1",
                    "nodeId": node_ids["text_layer"],
                    "content": "Sale\nToday",
                    "fontAssetId": None,
                    "fontFamily": "Noto Sans CJK SC",
                    "fontVersion": "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
                    "boxWidth": 0.4,
                    "lines": [
                        {"text": "Sale", "x": 0, "y": 0, "width": 0.2},
                        {"text": "Today", "x": 0, "y": 0.1, "width": 0.3},
                    ],
                    "fontSize": 32,
                    "color": "#0f172a",
                    "letterSpacing": 0,
                    "lineHeight": 1.2,
                    "align": "center",
                    "baseline": "alphabetic",
                    "zBand": "above-product",
                    "sortOrder": 0,
                }
            ],
        )

        semantic = CanvasSemanticState.model_validate(semantic_payload)
        layout = CanvasLayoutState.model_validate(layout_payload)
        self.assertEqual(NODE_KINDS, tuple(node.kind for node in semantic.nodes))
        self.assertEqual(
            semantic_payload,
            load_semantic_state(dump_project_state(semantic)).model_dump(by_alias=True),
        )
        self.assertEqual(
            layout_payload,
            load_layout_state(dump_project_state(layout)).model_dump(by_alias=True),
        )

    def test_state_bounds_fabric_markers_and_unsafe_strings_are_rejected(self):
        from pydantic import ValidationError

        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState

        valid_node = {"id": str(uuid4()), "kind": "prompt", "prompt": "ok", "parameters": {}}
        invalid_semantic_payloads = (
            self._semantic_payload(unknown=True),
            self._semantic_payload(objects=[]),
            self._semantic_payload(version="6.0.0"),
            self._semantic_payload(nodes=[valid_node] * 501),
            self._semantic_payload(
                edges=[
                    {
                        "id": str(uuid4()),
                        "kind": "prompt",
                        "sourceNodeId": "a",
                        "sourcePort": "out",
                        "targetNodeId": "b",
                        "targetPort": "in",
                    }
                    for _ in range(1001)
                ]
            ),
            self._semantic_payload(
                nodes=[{"id": str(uuid4()), "kind": "prompt", "prompt": "x" * 4001}]
            ),
            self._semantic_payload(versionHistory=[str(uuid4())]),
            self._semantic_payload(
                nodes=[
                    {
                        "id": str(uuid4()),
                        "kind": "prompt",
                        "parameters": {"versionHistory": []},
                    }
                ]
            ),
            self._semantic_payload(
                nodes=[
                    {
                        "id": str(uuid4()),
                        "kind": "prompt",
                        "parameters": {"blob": b"not-json"},
                    }
                ]
            ),
            self._semantic_payload(
                nodes=[
                    {
                        "id": str(uuid4()),
                        "kind": "prompt",
                        "parameters": {"score": float("nan")},
                    }
                ]
            ),
        )
        for payload in invalid_semantic_payloads:
            with self.subTest(keys=sorted(payload)):
                with self.assertRaises(ValidationError):
                    CanvasSemanticState.model_validate(payload)

        unsafe_values = (
            "data:image/png;base64,AAAA",
            "https://example.com/image.png",
            "http://example.com/image.png",
            "ftp://example.com/image.png",
            "C:\\private\\asset.png",
            "\\\\server\\share\\asset.png",
            "/srv/assets/image.png",
        )
        for value in unsafe_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    CanvasSemanticState.model_validate(
                        self._semantic_payload(
                            nodes=[{"id": str(uuid4()), "kind": "prompt", "prompt": value}]
                        )
                    )

        with self.assertRaises(ValidationError):
            CanvasLayoutState.model_validate(
                self._layout_payload(
                    textSnapshots=[
                        {"id": "text-1", "nodeId": "node-1", "content": "x" * 100001}
                    ]
                )
            )
        with self.assertRaises(ValidationError):
            CanvasLayoutState.model_validate(
                self._layout_payload(
                    textSnapshots=[
                        {
                            "id": "text-1",
                            "nodeId": "node-1",
                            "content": "short",
                            "lines": [
                                {"text": "x" * 60000, "x": 0, "y": 0, "width": 1},
                                {"text": "y" * 60000, "x": 0, "y": 1, "width": 1},
                            ],
                        }
                    ]
                )
            )
        with self.assertRaises(ValidationError):
            CanvasLayoutState.model_validate(
                self._layout_payload(viewport={"x": 0, "y": 0, "zoom": 1, "objects": []})
            )

    def test_rooted_windows_single_backslash_and_all_url_path_forms_are_rejected(self):
        from pydantic import ValidationError

        from services.canvas.schemas import CanvasSemanticState

        unsafe_values = (
            r"\Windows\System32\x",
            r"\\server\share\asset.png",
            r"C:\private\asset.png",
            "/srv/assets/image.png",
            "data:image/png;base64,AAAA",
            "blob:canvas-result",
            "file:///srv/assets/image.png",
            "https://example.com/image.png",
            "ftp://example.com/image.png",
        )
        for value in unsafe_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    CanvasSemanticState.model_validate(
                        self._semantic_payload(
                            nodes=[
                                {
                                    "id": str(uuid4()),
                                    "kind": "prompt",
                                    "prompt": value,
                                }
                            ]
                        )
                    )

    def test_dump_revalidates_models_after_nested_container_mutation(self):
        from pydantic import ValidationError

        from services.canvas.project_state import dump_project_state
        from services.canvas.schemas import empty_layout_state, empty_semantic_state

        unsafe_semantic = empty_semantic_state()
        unsafe_semantic.nodes.append(
            {
                "id": "mutated-unsafe-node",
                "kind": "prompt",
                "prompt": "https://evil.example/result.png",
                "parameters": {"objects": []},
            }
        )
        oversized_semantic = empty_semantic_state()
        oversized_semantic.nodes.extend(
            {
                "id": f"mutated-node-{index}",
                "kind": "prompt",
                "prompt": "safe",
            }
            for index in range(501)
        )
        unsafe_layout = empty_layout_state()
        unsafe_layout.object_transforms["mutated-transform"] = {
            "x": 0,
            "y": 0,
            "scale": 1,
            "rotation": 0,
            "objects": [],
        }

        for state in (unsafe_semantic, oversized_semantic, unsafe_layout):
            with self.subTest(state_type=type(state).__name__):
                with self.assertRaises(ValidationError):
                    dump_project_state(state)

    def test_save_revalidates_mutated_models_before_revision_or_event_write(self):
        from pydantic import ValidationError
        from sqlalchemy import func

        from canvas_models import CanvasEvent, CanvasProject
        from services.canvas.projects import create_project, save_project_state
        from services.canvas.schemas import empty_layout_state, empty_semantic_state

        def unsafe_semantic_case():
            semantic = empty_semantic_state()
            semantic.nodes.append(
                {
                    "id": "mutated-unsafe-node",
                    "kind": "prompt",
                    "prompt": "https://evil.example/result.png",
                    "parameters": {"objects": []},
                }
            )
            return semantic, empty_layout_state()

        def oversized_semantic_case():
            semantic = empty_semantic_state()
            semantic.nodes.extend(
                {
                    "id": f"mutated-node-{index}",
                    "kind": "prompt",
                    "prompt": "safe",
                }
                for index in range(501)
            )
            return semantic, empty_layout_state()

        def unsafe_layout_case():
            layout = empty_layout_state()
            layout.object_transforms["mutated-transform"] = {
                "x": 0,
                "y": 0,
                "scale": 1,
                "rotation": 0,
                "objects": [],
            }
            return empty_semantic_state(), layout

        cases = {
            "unsafe-semantic": unsafe_semantic_case,
            "oversized-semantic": oversized_semantic_case,
            "unsafe-layout": unsafe_layout_case,
        }
        with self.Session() as db:
            for label, build_states in cases.items():
                with self.subTest(case=label):
                    project = create_project(db, name=f"Mutation {label}")
                    project_id = project.id
                    semantic, layout = build_states()
                    with self.assertRaises(ValidationError):
                        save_project_state(
                            db,
                            project_id=project_id,
                            expected_revision=1,
                            semantic_state=semantic,
                            layout_state=layout,
                        )
                    saved_revision = db.execute(
                        select(CanvasProject.revision).where(CanvasProject.id == project_id)
                    ).scalar_one()
                    event_count = db.execute(
                        select(func.count(CanvasEvent.id)).where(
                            CanvasEvent.project_id == project_id
                        )
                    ).scalar_one()
                    self.assertEqual((1, 1), (saved_revision, event_count))

    def test_schema_upgrade_entrypoint_is_explicit_and_rejects_unknown_versions(self):
        from services.canvas.project_state import ProjectStateVersionError, upgrade_project_state

        semantic, layout = self._empty_states()
        upgraded_semantic, upgraded_layout, version = upgrade_project_state(
            semantic_state=(dump := semantic.model_dump(by_alias=True)),
            layout_state=layout.model_dump(by_alias=True),
            schema_version=1,
        )
        self.assertEqual(dump, upgraded_semantic)
        self.assertEqual(layout.model_dump(by_alias=True), upgraded_layout)
        self.assertEqual(1, version)
        for unsupported in (0, 2):
            with self.subTest(schema_version=unsupported):
                with self.assertRaises(ProjectStateVersionError):
                    upgrade_project_state(
                        semantic_state=dump,
                        layout_state=layout.model_dump(by_alias=True),
                        schema_version=unsupported,
                    )

    def test_revision_compare_and_swap_reports_current_revision_without_overwrite(self):
        from sqlalchemy import event

        from services.canvas.projects import (
            CanvasRevisionConflict,
            create_project,
            update_project_metadata,
        )

        statements = []

        @event.listens_for(self.engine, "before_cursor_execute")
        def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("UPDATE CANVAS_PROJECTS"):
                statements.append(" ".join(statement.lower().split()))

        try:
            with self.Session() as db:
                project = create_project(db, name="Original")
                updated = update_project_metadata(
                    db,
                    project_id=project.id,
                    expected_revision=1,
                    name="Winner",
                )
                with self.assertRaises(CanvasRevisionConflict) as conflict:
                    update_project_metadata(
                        db,
                        project_id=project.id,
                        expected_revision=1,
                        name="Stale writer",
                    )
                snapshot = db.get(type(project), project.id)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture_sql)

        self.assertEqual(2, updated.revision)
        self.assertEqual(2, conflict.exception.current_revision)
        self.assertEqual("Winner", snapshot.name)
        self.assertTrue(
            any("canvas_projects.id" in sql and "canvas_projects.revision" in sql for sql in statements),
            statements,
        )

    def test_archive_restore_and_deletion_transitions_increment_revision_and_use_guards(self):
        from services.canvas import projects

        with self.Session() as db:
            project = projects.create_project(db, name="Lifecycle")
            with patch.object(
                projects,
                "PROJECT_ACTIVITY_GUARDS",
                [lambda _db, _project_id: [{"id": "op-running", "status": "running"}]],
            ):
                with self.assertRaises(projects.CanvasProjectActivityConflict):
                    projects.archive_project(
                        db,
                        project_id=project.id,
                        expected_revision=1,
                    )

            archived = projects.archive_project(
                db,
                project_id=project.id,
                expected_revision=1,
            )
            with patch.object(
                projects,
                "PROJECT_ACTIVITY_GUARDS",
                [lambda _db, _project_id: [{"id": "item-unknown", "status": "unknown"}]],
            ):
                with self.assertRaises(projects.CanvasProjectActivityConflict):
                    projects.restore_project(
                        db,
                        project_id=project.id,
                        expected_revision=2,
                    )
                with self.assertRaises(projects.CanvasProjectActivityConflict):
                    projects.request_project_deletion(
                        db,
                        project_id=project.id,
                        expected_revision=2,
                    )

            restored = projects.restore_project(
                db,
                project_id=project.id,
                expected_revision=2,
            )
            deleting = projects.request_project_deletion(
                db,
                project_id=project.id,
                expected_revision=3,
            )

        self.assertEqual(("archived", 2), (archived.project.status, archived.revision))
        self.assertEqual(("active", 3), (restored.project.status, restored.revision))
        self.assertEqual(("deleting", 4), (deleting.project.status, deleting.revision))

    def test_operation_activity_guard_blocks_archive_and_delete_until_terminal(self):
        from canvas_models import CanvasAssetOperation
        from services.canvas import operations, projects

        self.assertIn(
            operations.canvas_operation_project_activity_guard,
            projects.PROJECT_ACTIVITY_GUARDS,
        )
        for status in ("queued", "running", "cancel_requested"):
            with self.subTest(status=status), self.Session() as db:
                project = projects.create_project(db, name=f"Blocked {status}")
                asset = self._add_asset(db, project_id=project.id)
                operation = CanvasAssetOperation(
                    project_id=project.id,
                    operation_type="cutout",
                    status=status,
                    input_asset_id=asset.id,
                    idempotency_key=f"block-{status}",
                )
                db.add(operation)
                db.commit()

                with self.assertRaises(projects.CanvasProjectActivityConflict) as archive_error:
                    projects.archive_project(
                        db,
                        project_id=project.id,
                        expected_revision=1,
                    )
                self.assertEqual(operation.id, archive_error.exception.activities[0]["operationId"])
                with self.assertRaises(projects.CanvasProjectActivityConflict):
                    projects.request_project_deletion(
                        db,
                        project_id=project.id,
                        expected_revision=1,
                    )

                operation.status = "interrupted"
                db.commit()
                deleting = projects.request_project_deletion(
                    db,
                    project_id=project.id,
                    expected_revision=1,
                )
                self.assertEqual("deleting", deleting.project.status)

    def test_finalize_blocks_active_operation_before_files_and_deletes_terminal_fk_order(self):
        from sqlalchemy import event as sqlalchemy_event

        from canvas_models import (
            CanvasAssetOperation,
            CanvasEvent,
            CanvasProject,
            CanvasProjectSku,
        )
        from services.canvas import operations, projects, storage

        with self.Session() as db:
            project = projects.create_project(db, name="Operation finalizer")
            asset = self._add_asset(db, project_id=project.id)
            operation = CanvasAssetOperation(
                project_id=project.id,
                operation_type="cutout",
                status="queued",
                input_asset_id=asset.id,
                idempotency_key="finalizer-cutout",
            )
            sku = CanvasProjectSku(
                project_id=project.id,
                name="Delete me",
                sort_order=0,
                reference_asset_id=asset.id,
            )
            db.add_all([operation, sku])
            db.flush()
            db.add(
                CanvasEvent(
                    project_id=project.id,
                    operation_id=operation.id,
                    event_type="operation.queued",
                    payload_json='{"status":"queued"}',
                )
            )
            project.status = "deleting"
            db.commit()
            project_id = project.id
            operation_id = operation.id

        with patch.object(storage, "remove_project_tree") as remove_tree:
            with self.assertRaises(projects.CanvasProjectActivityConflict):
                projects.finalize_deleting_project(self.Session, project_id=project_id)
            remove_tree.assert_not_called()

        with self.Session() as db:
            operation = db.get(CanvasAssetOperation, operation_id)
            operation.status = "failed"
            db.commit()

        delete_tables = []

        @sqlalchemy_event.listens_for(self.engine, "before_cursor_execute")
        def capture_delete_order(_conn, _cursor, statement, _parameters, _context, _executemany):
            normalized = " ".join(statement.lower().split())
            if normalized.startswith("delete from canvas_"):
                delete_tables.append(normalized.split()[2])

        try:
            with patch.object(storage, "remove_project_tree") as remove_tree:
                projects.finalize_deleting_project(self.Session, project_id=project_id)
                remove_tree.assert_called_once_with(project_id)
        finally:
            sqlalchemy_event.remove(self.engine, "before_cursor_execute", capture_delete_order)

        self.assertEqual(
            [
                "canvas_events",
                "canvas_generation_item_inputs",
                "canvas_generation_attempts",
                "canvas_generation_items",
                "canvas_generations",
                "canvas_asset_operations",
                "canvas_project_skus",
                "canvas_assets",
                "canvas_projects",
            ],
            delete_tables,
        )
        with self.Session() as db:
            self.assertIsNone(db.get(CanvasProject, project_id))

    def test_permanent_delete_is_contained_file_first_and_crash_resumable(self):
        from canvas_models import CanvasProject
        from services.canvas import projects, storage

        data_root = Path(self.tmp.name) / "canvas-data"
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")

        with patch.object(storage, "CANVAS_DATA_DIR", str(data_root)):
            with self.Session() as db:
                project = projects.create_project(db, name="Delete safely")
                root = storage.ensure_project_tree(project.id)
                (root / "tmp" / "partial.bin").write_bytes(b"partial")
                deleting = projects.request_project_deletion(
                    db,
                    project_id=project.id,
                    expected_revision=1,
                )

            self.assertEqual("deleting", deleting.project.status)
            self.assertTrue(root.exists(), "requesting deletion must not remove files synchronously")
            real_remove = storage.remove_project_tree

            def remove_then_crash(project_id):
                real_remove(project_id)
                raise RuntimeError("simulated crash after contained tree removal")

            with patch.object(storage, "remove_project_tree", side_effect=remove_then_crash):
                with self.assertRaises(RuntimeError):
                    projects.finalize_deleting_project(self.Session, project_id=project.id)

            self.assertFalse(root.exists())
            with self.Session() as db:
                self.assertEqual("deleting", db.get(CanvasProject, project.id).status)

            projects.finalize_deleting_project(self.Session, project_id=project.id)
            projects.finalize_deleting_project(self.Session, project_id=project.id)

        with self.Session() as db:
            self.assertIsNone(db.get(CanvasProject, project.id))
        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))

    def test_recovery_finalizes_every_deleting_project_only(self):
        from canvas_models import CanvasProject
        from services.canvas import projects, storage

        data_root = Path(self.tmp.name) / "canvas-recovery"
        with patch.object(storage, "CANVAS_DATA_DIR", str(data_root)):
            with self.Session() as db:
                active = projects.create_project(db, name="Keep active")
                doomed = [projects.create_project(db, name=f"Delete {index}") for index in range(2)]
                for project in doomed:
                    storage.ensure_project_tree(project.id)
                    projects.request_project_deletion(
                        db,
                        project_id=project.id,
                        expected_revision=1,
                    )

            self.assertEqual(2, projects.recover_deleting_projects(self.Session))

        with self.Session() as db:
            self.assertIsNotNone(db.get(CanvasProject, active.id))
            self.assertTrue(all(db.get(CanvasProject, project.id) is None for project in doomed))

    def test_save_state_rejects_cross_project_sku_and_asset_references_everywhere(self):
        from services.canvas.projects import (
            CanvasStateOwnershipError,
            create_project,
            create_sku,
            save_project_state,
        )
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState, SkuCreate

        with self.Session() as db:
            project_a = create_project(db, name="Owner A")
            project_b = create_project(db, name="Owner B")
            asset_b = self._add_asset(db, project_id=project_b.id)
            sku_b_snapshot = create_sku(
                db,
                project_id=project_b.id,
                expected_revision=1,
                request=SkuCreate.model_validate({"name": "Foreign", "prompt": "", "config": {}}),
            )
            sku_b = sku_b_snapshot.skus[0]
            foreign_sku_id = sku_b.id
            foreign_asset_id = asset_b.id

            semantic = CanvasSemanticState.model_validate(
                self._semantic_payload(
                    nodes=[
                        {
                            "id": "node-foreign",
                            "kind": "sku_reference",
                            "skuId": sku_b.id,
                            "assetId": asset_b.id,
                        },
                        {
                            "id": "output-foreign",
                            "kind": "sku_output",
                            "skuId": sku_b.id,
                            "outputBoardId": "board-foreign",
                        },
                    ],
                    outputBoards=[
                        {
                            "id": "board-foreign",
                            "outputNodeId": "output-foreign",
                            "outputType": "sku",
                            "skuId": sku_b.id,
                            "sortOrder": 0,
                            "selectedResultAssetId": asset_b.id,
                        }
                    ],
                    completeSet={
                        "selectedOutputTypes": ["sku"],
                        "outputs": [
                            {
                                "outputType": "sku",
                                "skuId": sku_b.id,
                                "quantity": 1,
                                "referenceAssetId": asset_b.id,
                            }
                        ],
                    },
                )
            )
            layout = CanvasLayoutState.model_validate(
                self._layout_payload(
                    productLayers=[
                        {
                            "id": "foreign-layer",
                            "sourceAssetId": asset_b.id,
                            "renderAssetId": asset_b.id,
                            "skuId": sku_b.id,
                            "transformId": "foreign-layer",
                            "locked": True,
                        }
                    ]
                )
            )
            with self.assertRaises(CanvasStateOwnershipError) as conflict:
                save_project_state(
                    db,
                    project_id=project_a.id,
                    expected_revision=1,
                    semantic_state=semantic,
                    layout_state=layout,
                )

        self.assertIn(foreign_sku_id, conflict.exception.sku_ids)
        self.assertIn(foreign_asset_id, conflict.exception.asset_ids)

    def test_sku_reference_asset_must_share_owner(self):
        from services.canvas.projects import CanvasStateOwnershipError, create_project, create_sku
        from services.canvas.schemas import SkuCreate

        with self.Session() as db:
            project_a = create_project(db, name="SKU owner")
            project_b = create_project(db, name="Asset owner")
            foreign_asset = self._add_asset(db, project_id=project_b.id)
            with self.assertRaises(CanvasStateOwnershipError):
                create_sku(
                    db,
                    project_id=project_a.id,
                    expected_revision=1,
                    request=SkuCreate.model_validate(
                        {
                            "name": "Wrong asset",
                            "referenceAssetId": foreign_asset.id,
                            "prompt": "",
                            "config": {},
                        }
                    ),
                )

    def test_delete_sku_reports_all_live_references_then_soft_deletes_history_row(self):
        from canvas_models import CanvasAsset, CanvasProjectSku
        from services.canvas.projects import (
            CanvasSkuReferenceConflict,
            create_project,
            create_sku,
            delete_sku,
            get_project_snapshot,
            save_project_state,
        )
        from services.canvas.schemas import CanvasLayoutState, CanvasSemanticState, SkuCreate

        with self.Session() as db:
            project = create_project(db, name="SKU references")
            asset = self._add_asset(db, project_id=project.id)
            asset.asset_type = "working"
            asset.relative_path = f"working/{asset.id}.png"
            asset.transparency_status = "opaque"
            db.commit()
            created = create_sku(
                db,
                project_id=project.id,
                expected_revision=1,
                request=SkuCreate.model_validate(
                    {
                        "name": "Chocolate",
                        "referenceAssetId": asset.id,
                        "prompt": "rich cocoa",
                        "config": {"quantity": 2},
                    }
                ),
            )
            sku = created.skus[0]
            semantic = CanvasSemanticState.model_validate(
                self._semantic_payload(
                    nodes=[
                        {
                            "id": "main-product-source",
                            "kind": "product_source",
                            "assetId": asset.id,
                        },
                        {
                            "id": "main-product-cutout",
                            "kind": "auto_cutout",
                            "assetId": asset.id,
                        },
                        {"id": "source", "kind": "sku_reference", "skuId": sku.id, "assetId": asset.id},
                        {"id": "output", "kind": "sku_output", "skuId": sku.id, "outputBoardId": "board"},
                        {"id": "sku-prompt", "kind": "prompt", "skuId": sku.id, "prompt": "cocoa"},
                        {"id": "sku-generation", "kind": "model_generation"},
                    ],
                    edges=[
                        {
                            "id": "main-product-source-cutout",
                            "kind": "product_asset",
                            "sourceNodeId": "main-product-source",
                            "sourcePort": "product",
                            "targetNodeId": "main-product-cutout",
                            "targetPort": "reference",
                            "skuId": None,
                        },
                        {
                            "id": "sku-prompt-edge",
                            "kind": "prompt",
                            "sourceNodeId": "sku-prompt",
                            "sourcePort": "prompt",
                            "targetNodeId": "sku-generation",
                            "targetPort": "prompt",
                            "skuId": sku.id,
                        }
                    ],
                    outputBoards=[
                        {
                            "id": "board",
                            "outputNodeId": "output",
                            "outputType": "sku",
                            "skuId": sku.id,
                            "sortOrder": 0,
                            "selectedResultAssetId": None,
                        }
                    ],
                    completeSet={
                        "selectedOutputTypes": ["sku"],
                        "outputs": [
                            {
                                "outputType": "sku",
                                "skuId": sku.id,
                                "quantity": 1,
                                "referenceAssetId": asset.id,
                            }
                        ],
                    },
                    compositionGroups=[
                        {
                            "id": "group",
                            "skuIds": [sku.id],
                            "productLayerIds": ["main-layer", "layer"],
                            "layoutHash": "sha256:4fa0c93a85b21f386b9d29061587607818ebfcc3a3cf2073aec4d3902d320a34",
                            "layout": {
                                "slot": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                                "anchor": {"x": 0.5, "y": 0.5},
                                "baseline": 0.9,
                                "relativeProductFraction": 0.8,
                                "contain": True,
                                "safeArea": {"top": 0.05, "right": 0.05, "bottom": 0.05, "left": 0.05},
                                "rotation": 0.0,
                            },
                        }
                    ],
                )
            )
            layout = CanvasLayoutState.model_validate(
                self._layout_payload(
                    objectTransforms={
                        "main-layer": {"x": 0.5, "y": 0.9, "scale": 0.8, "rotation": 0.0},
                        "layer": {"x": 0.5, "y": 0.9, "scale": 0.8, "rotation": 0.0},
                    },
                    productLayers=[
                        {
                            "id": "main-layer",
                            "sourceAssetId": asset.id,
                            "renderAssetId": asset.id,
                            "allowOpaqueFallback": True,
                            "skuId": None,
                            "compositionGroupId": "group",
                            "transformId": "main-layer",
                            "locked": True,
                        },
                        {
                            "id": "layer",
                            "sourceAssetId": asset.id,
                            "renderAssetId": asset.id,
                            "allowOpaqueFallback": True,
                            "skuId": sku.id,
                            "compositionGroupId": "group",
                            "transformId": "layer",
                            "locked": True,
                        }
                    ]
                )
            )
            saved = save_project_state(
                db,
                project_id=project.id,
                expected_revision=2,
                semantic_state=semantic,
                layout_state=layout,
            )
            with self.assertRaises(CanvasSkuReferenceConflict) as conflict:
                delete_sku(
                    db,
                    project_id=project.id,
                    sku_id=sku.id,
                    expected_revision=3,
                )
            self.assertEqual(3, get_project_snapshot(db, project_id=project.id).revision)
            detached = save_project_state(
                db,
                project_id=project.id,
                expected_revision=3,
                semantic_state=CanvasSemanticState.model_validate(self._semantic_payload()),
                layout_state=CanvasLayoutState.model_validate(self._layout_payload()),
            )
            deleted = delete_sku(
                db,
                project_id=project.id,
                sku_id=sku.id,
                expected_revision=4,
            )
            historical_row = db.get(CanvasProjectSku, sku.id)
            retained_asset = db.get(CanvasAsset, asset.id)

        self.assertEqual(3, saved.revision)
        self.assertEqual(4, detached.revision)
        self.assertEqual(5, deleted.revision)
        self.assertTrue(
            {"nodes", "edges", "outputBoards", "completeSet", "compositionGroups", "productLayers"}
            <= set(conflict.exception.references)
        )
        self.assertEqual([], deleted.skus)
        self.assertEqual("Chocolate", historical_row.name)
        self.assertEqual("rich cocoa", historical_row.prompt)
        self.assertEqual('{"quantity":2}', historical_row.config_json)
        self.assertIsNone(historical_row.reference_asset_id)
        self.assertIsNotNone(historical_row.deleted_at)
        self.assertIsNotNone(retained_asset)

    def test_project_list_search_archive_filter_and_tie_break_order_are_stable(self):
        from sqlalchemy import update

        from canvas_models import CanvasProject
        from services.canvas.projects import archive_project, create_project, list_projects

        with self.Session() as db:
            summer = create_project(db, name="Summer launch")
            winter = create_project(db, name="Winter launch")
            archived = create_project(db, name="Summer archive")
            archive_project(db, project_id=archived.id, expected_revision=1)
            tied = datetime(2026, 7, 13, 12, 0, 0)
            db.execute(
                update(CanvasProject)
                .where(CanvasProject.id.in_([summer.id, winter.id, archived.id]))
                .values(updated_at=tied)
            )
            db.commit()

            active = list_projects(db, query=None, include_archived=False)
            all_projects = list_projects(db, query=None, include_archived=True)
            summer_projects = list_projects(db, query="  SUMMER  ", include_archived=True)

        self.assertEqual(
            sorted([summer.id, winter.id], reverse=True),
            [project.id for project in active],
        )
        self.assertEqual(
            sorted([summer.id, winter.id, archived.id], reverse=True),
            [project.id for project in all_projects],
        )
        self.assertEqual(
            sorted([summer.id, archived.id], reverse=True),
            [project.id for project in summer_projects],
        )

    def test_events_commit_with_mutations_use_safe_summaries_and_roll_back_together(self):
        from canvas_models import CanvasEvent, CanvasProject
        from services.canvas import projects

        semantic, layout = self._empty_states()
        with self.Session() as db:
            project = projects.create_project(db, name="Events")
            projects.update_project_metadata(
                db,
                project_id=project.id,
                expected_revision=1,
                name="Events renamed",
            )
            projects.save_project_state(
                db,
                project_id=project.id,
                expected_revision=2,
                semantic_state=semantic,
                layout_state=layout,
            )
            events = db.execute(
                select(CanvasEvent)
                .where(CanvasEvent.project_id == project.id)
                .order_by(CanvasEvent.id)
            ).scalars().all()
            event_values = [
                (event.event_type, event.payload_json)
                for event in events
            ]
            before_failure = db.get(CanvasProject, project.id)
            db.expunge(before_failure)

            with patch.object(projects, "append_canvas_event", side_effect=RuntimeError("event failure")):
                with self.assertRaises(RuntimeError):
                    projects.update_project_metadata(
                        db,
                        project_id=project.id,
                        expected_revision=3,
                        name="Must roll back",
                    )
            after_failure = db.get(CanvasProject, project.id)

        self.assertEqual(
            ["project.created", "project.updated", "project.state_saved"],
            [event_type for event_type, _payload_json in event_values],
        )
        for _event_type, payload_json in event_values:
            payload = json.loads(payload_json)
            self.assertNotIn("semanticState", payload)
            self.assertNotIn("semantic_state", payload)
            self.assertNotIn("layoutState", payload)
            self.assertNotIn("layout_state", payload)
            self.assertLess(len(payload_json.encode("utf-8")), 2048)
        self.assertEqual(("Events renamed", 3), (after_failure.name, after_failure.revision))


class CanvasProjectApiContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-project-api.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        import canvas_models  # noqa: F401 - register Canvas metadata for the test database.
        from database import Base, get_db
        from main import app
        from routers.canvas import projects as canvas_project_routes

        Base.metadata.create_all(bind=self.engine)

        def override_db():
            with self.Session() as db:
                yield db

        self.app = app
        self.get_db = get_db
        self.canvas_project_routes = canvas_project_routes
        self.canvas_session_factory_dependency = (
            canvas_project_routes.get_canvas_session_factory
        )
        self.app.dependency_overrides[self.get_db] = override_db
        self.app.dependency_overrides[self.canvas_session_factory_dependency] = (
            lambda: self.Session
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.pop(self.get_db, None)
        self.app.dependency_overrides.pop(
            self.canvas_session_factory_dependency,
            None,
        )
        self.engine.dispose()
        self.tmp.cleanup()

    def _create_project(self, name="API project"):
        response = self.client.post("/api/canvas/projects", json={"name": name})
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _state_payload(revision, **overrides):
        payload = {
            "revision": revision,
            "semanticState": {
                "nodes": [],
                "edges": [],
                "outputBoards": [],
                "mode": "complete-set",
                "advancedCustomized": False,
                "completeSet": {"selectedOutputTypes": [], "outputs": []},
                "compositionGroups": [],
            },
            "layoutState": {
                "nodePositions": {},
                "objectTransforms": {},
                "viewport": {"x": 0, "y": 0, "zoom": 1},
                "productLayers": [],
                "textSnapshots": [],
            },
        }
        payload.update(overrides)
        return payload

    def _add_working_asset(self, project_id, asset_id):
        from canvas_models import CanvasAsset

        with self.Session() as db:
            db.add(
                CanvasAsset(
                    id=asset_id,
                    project_id=project_id,
                    asset_type="working",
                    relative_path=f"working/{asset_id}.png",
                    original_filename="main.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1200,
                    height=1200,
                    sha256="a" * 64,
                    source_asset_id=None,
                    transparency_status="transparent",
                    metadata_json="{}",
                )
            )
            db.commit()

    def _canonical_main_product_state(self, revision, *, source_asset_id, render_asset_id):
        payload = self._state_payload(revision)
        payload["semanticState"]["nodes"] = [
            {
                "id": "main-product-source",
                "kind": "product_source",
                "managedBy": None,
                "skuId": None,
                "assetId": source_asset_id,
                "modelProfileId": None,
                "prompt": None,
                "compositionGroupId": None,
                "textSnapshotId": None,
                "outputBoardId": None,
                "parameters": {},
            },
            {
                "id": "main-product-cutout",
                "kind": "auto_cutout",
                "managedBy": None,
                "skuId": None,
                "assetId": render_asset_id,
                "modelProfileId": None,
                "prompt": None,
                "compositionGroupId": None,
                "textSnapshotId": None,
                "outputBoardId": None,
                "parameters": {},
            },
        ]
        payload["semanticState"]["edges"] = [
            {
                "id": "main-product-source-cutout",
                "kind": "product_asset",
                "sourceNodeId": "main-product-source",
                "sourcePort": "product",
                "targetNodeId": "main-product-cutout",
                "targetPort": "reference",
                "skuId": None,
            }
        ]
        payload["layoutState"]["objectTransforms"] = {
            "main-product": {"x": 0.5, "y": 0.5, "scale": 1, "rotation": 0}
        }
        payload["layoutState"]["productLayers"] = [
            {
                "id": "main-product",
                "sourceAssetId": source_asset_id,
                "renderAssetId": render_asset_id,
                "allowOpaqueFallback": False,
                "skuId": None,
                "compositionGroupId": None,
                "transformId": "main-product",
                "locked": True,
            }
        ]
        return payload

    def _advanced_graph_state(self, revision):
        payload = self._state_payload(revision)
        payload["semanticState"].update(
            {
                "mode": "advanced",
                "advancedCustomized": True,
                "nodes": [
                    {
                        "id": "prompt-scene",
                        "kind": "prompt",
                        "prompt": "clean studio scene",
                    },
                    {
                        "id": "generation-scene",
                        "kind": "model_generation",
                    },
                    {
                        "id": "output-main",
                        "kind": "main_output",
                        "outputBoardId": "board-main",
                    },
                ],
                "edges": [
                    {
                        "id": "prompt-to-generation",
                        "kind": "prompt",
                        "sourceNodeId": "prompt-scene",
                        "sourcePort": "prompt",
                        "targetNodeId": "generation-scene",
                        "targetPort": "prompt",
                        "skuId": None,
                    },
                    {
                        "id": "generation-to-output",
                        "kind": "output_image",
                        "sourceNodeId": "generation-scene",
                        "sourcePort": "output",
                        "targetNodeId": "output-main",
                        "targetPort": "input",
                        "skuId": None,
                    },
                ],
                "outputBoards": [
                    {
                        "id": "board-main",
                        "outputNodeId": "output-main",
                        "outputType": "main",
                        "skuId": None,
                        "sortOrder": 0,
                        "selectedResultAssetId": None,
                    }
                ],
            }
        )
        return payload

    def test_state_save_rejects_invalid_ordinary_graph_edges_before_revision_advance(self):
        cases = {
            "dangling": lambda payload: payload["semanticState"]["edges"][0].update(
                {"targetNodeId": "missing-node"}
            ),
            "wrong_ports": lambda payload: payload["semanticState"]["edges"][0].update(
                {"sourcePort": "output"}
            ),
            "wrong_node_kinds": lambda payload: payload["semanticState"]["edges"][0].update(
                {
                    "kind": "output_image",
                    "sourcePort": "output",
                    "targetPort": "input",
                }
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                created = self._create_project(f"Invalid ordinary edge {label}")
                project_id = created["project"]["id"]
                payload = self._advanced_graph_state(1)
                mutate(payload)

                rejected = self.client.put(
                    f"/api/canvas/projects/{project_id}/state",
                    json=payload,
                )

                self.assertEqual(422, rejected.status_code, rejected.text)
                self.assertEqual(
                    1,
                    self.client.get(f"/api/canvas/projects/{project_id}").json()["revision"],
                )

    def test_state_save_rejects_duplicate_graph_identifiers_before_revision_advance(self):
        cases = {
            "node": lambda payload: payload["semanticState"]["nodes"].append(
                {**payload["semanticState"]["nodes"][0]}
            ),
            "edge": lambda payload: payload["semanticState"]["edges"].append(
                {**payload["semanticState"]["edges"][0]}
            ),
            "output_board": lambda payload: payload["semanticState"]["outputBoards"].append(
                {**payload["semanticState"]["outputBoards"][0]}
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                created = self._create_project(f"Duplicate {label}")
                project_id = created["project"]["id"]
                payload = self._advanced_graph_state(1)
                mutate(payload)

                rejected = self.client.put(
                    f"/api/canvas/projects/{project_id}/state",
                    json=payload,
                )

                self.assertEqual(422, rejected.status_code, rejected.text)
                self.assertEqual(
                    1,
                    self.client.get(f"/api/canvas/projects/{project_id}").json()["revision"],
                )

    def test_state_save_rejects_duplicate_singleton_input_before_revision_advance(self):
        created = self._create_project("Duplicate singleton input")
        project_id = created["project"]["id"]
        payload = self._advanced_graph_state(1)
        payload["semanticState"]["nodes"].append(
            {
                "id": "prompt-alternate",
                "kind": "prompt",
                "prompt": "alternate scene",
            }
        )
        payload["semanticState"]["edges"].append(
            {
                "id": "alternate-prompt-to-generation",
                "kind": "prompt",
                "sourceNodeId": "prompt-alternate",
                "sourcePort": "prompt",
                "targetNodeId": "generation-scene",
                "targetPort": "prompt",
                "skuId": None,
            }
        )

        rejected = self.client.put(
            f"/api/canvas/projects/{project_id}/state",
            json=payload,
        )

        self.assertEqual(422, rejected.status_code, rejected.text)
        self.assertEqual(
            1,
            self.client.get(f"/api/canvas/projects/{project_id}").json()["revision"],
        )

    def test_state_save_rejects_nonreciprocal_output_board_before_revision_advance(self):
        created = self._create_project("Nonreciprocal output board")
        project_id = created["project"]["id"]
        payload = self._advanced_graph_state(1)
        payload["semanticState"]["nodes"][2]["outputBoardId"] = "other-board"

        rejected = self.client.put(
            f"/api/canvas/projects/{project_id}/state",
            json=payload,
        )

        self.assertEqual(422, rejected.status_code, rejected.text)
        self.assertEqual(
            1,
            self.client.get(f"/api/canvas/projects/{project_id}").json()["revision"],
        )

    def test_state_save_persists_valid_advanced_graph(self):
        created = self._create_project("Valid advanced graph")
        project_id = created["project"]["id"]

        saved = self.client.put(
            f"/api/canvas/projects/{project_id}/state",
            json=self._advanced_graph_state(1),
        )

        self.assertEqual(200, saved.status_code, saved.text)
        self.assertEqual(2, saved.json()["revision"])
        self.assertEqual("advanced", saved.json()["project"]["semanticState"]["mode"])

    def test_state_save_rejects_tampered_main_product_system_pipeline_before_revision_advance(self):
        cases = {
            "missing": lambda payload, _alternate: payload["semanticState"].update(
                {"nodes": [], "edges": []}
            ),
            "duplicate": lambda payload, _alternate: payload["semanticState"]["edges"].append(
                {**payload["semanticState"]["edges"][0], "id": "duplicate-source-cutout"}
            ),
            "fake": lambda payload, _alternate: payload["semanticState"]["nodes"].append(
                {**payload["semanticState"]["nodes"][1], "id": "forged-auto-cutout"}
            ),
            "wrong_asset_binding": lambda payload, alternate: payload["semanticState"]["nodes"][0].update(
                {"assetId": alternate}
            ),
            "disconnected": lambda payload, _alternate: payload["semanticState"]["edges"][0].update(
                {"targetNodeId": "main-product-source"}
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                created = self._create_project(f"Pipeline {label}")
                project_id = created["project"]["id"]
                source_asset_id = str(uuid4())
                alternate_asset_id = str(uuid4())
                self._add_working_asset(project_id, source_asset_id)
                self._add_working_asset(project_id, alternate_asset_id)
                payload = self._canonical_main_product_state(
                    1,
                    source_asset_id=source_asset_id,
                    render_asset_id=source_asset_id,
                )
                mutate(payload, alternate_asset_id)

                rejected = self.client.put(
                    f"/api/canvas/projects/{project_id}/state",
                    json=payload,
                )

                self.assertEqual(422, rejected.status_code, rejected.text)
                current = self.client.get(f"/api/canvas/projects/{project_id}")
                self.assertEqual(200, current.status_code, current.text)
                self.assertEqual(1, current.json()["revision"])

    def test_state_save_rejects_unversioned_result_selection_but_allows_null_clear(self):
        created = self._create_project("Result selection")
        project_id = created["project"]["id"]
        unrelated_asset_id = str(uuid4())
        self._add_working_asset(project_id, unrelated_asset_id)
        payload = self._state_payload(1)
        payload["semanticState"]["nodes"] = [
            {
                "id": "output-main",
                "kind": "main_output",
                "outputBoardId": "board-main",
            }
        ]
        payload["semanticState"]["outputBoards"] = [
            {
                "id": "board-main",
                "outputNodeId": "output-main",
                "outputType": "main",
                "skuId": None,
                "sortOrder": 0,
                "selectedResultAssetId": unrelated_asset_id,
            }
        ]

        rejected = self.client.put(
            f"/api/canvas/projects/{project_id}/state",
            json=payload,
        )
        self.assertEqual(422, rejected.status_code, rejected.text)
        self.assertEqual(1, self.client.get(f"/api/canvas/projects/{project_id}").json()["revision"])

        payload["semanticState"]["outputBoards"][0]["selectedResultAssetId"] = None
        cleared = self.client.put(
            f"/api/canvas/projects/{project_id}/state",
            json=payload,
        )
        self.assertEqual(200, cleared.status_code, cleared.text)
        self.assertEqual(2, cleared.json()["revision"])

    def test_create_list_and_get_return_stable_camel_case_snapshots(self):
        created = self.client.post(
            "/api/canvas/projects",
            json={"name": "  Summer launch  "},
        )

        self.assertEqual(201, created.status_code, created.text)
        snapshot = created.json()
        self.assertEqual({"project", "skus", "revision"}, set(snapshot))
        self.assertEqual([], snapshot["skus"])
        self.assertEqual(1, snapshot["revision"])
        self.assertEqual("Summer launch", snapshot["project"]["name"])
        self.assertEqual("active", snapshot["project"]["status"])
        self.assertEqual(1, snapshot["project"]["schemaVersion"])
        self.assertIn("semanticState", snapshot["project"])
        self.assertIn("layoutState", snapshot["project"])
        self.assertNotIn("semantic_state", snapshot["project"])
        project_id = snapshot["project"]["id"]

        listed = self.client.get("/api/canvas/projects")
        self.assertEqual(200, listed.status_code, listed.text)
        self.assertEqual([project_id], [row["id"] for row in listed.json()["projects"]])

        fetched = self.client.get(f"/api/canvas/projects/{project_id}")
        self.assertEqual(200, fetched.status_code, fetched.text)
        self.assertEqual(snapshot, fetched.json())

    def test_metadata_state_archive_and_restore_share_snapshot_revision(self):
        created = self._create_project()
        project_id = created["project"]["id"]

        renamed = self.client.patch(
            f"/api/canvas/projects/{project_id}",
            json={"revision": 1, "name": "Renamed API project"},
        )
        self.assertEqual(200, renamed.status_code, renamed.text)
        self.assertEqual(("Renamed API project", 2), (
            renamed.json()["project"]["name"],
            renamed.json()["revision"],
        ))

        saved = self.client.put(
            f"/api/canvas/projects/{project_id}/state",
            json=self._state_payload(2),
        )
        self.assertEqual(200, saved.status_code, saved.text)
        self.assertEqual(3, saved.json()["revision"])
        self.assertEqual([], saved.json()["project"]["semanticState"]["nodes"])

        archived = self.client.post(
            f"/api/canvas/projects/{project_id}/archive",
            json={"revision": 3},
        )
        self.assertEqual(200, archived.status_code, archived.text)
        self.assertEqual(("archived", 4), (
            archived.json()["project"]["status"],
            archived.json()["revision"],
        ))
        self.assertEqual([], self.client.get("/api/canvas/projects").json()["projects"])
        included = self.client.get("/api/canvas/projects?includeArchived=true")
        self.assertEqual([project_id], [row["id"] for row in included.json()["projects"]])

        restored = self.client.post(
            f"/api/canvas/projects/{project_id}/restore",
            json={"revision": 4},
        )
        self.assertEqual(200, restored.status_code, restored.text)
        self.assertEqual(("active", 5), (
            restored.json()["project"]["status"],
            restored.json()["revision"],
        ))

    def test_legacy_composition_group_migrates_raw_transform_through_real_http(self):
        from canvas_models import CanvasAsset

        created = self._create_project("Legacy composition")
        project_id = created["project"]["id"]
        working_id = "00000000-0000-0000-0000-000000000201"
        with self.Session() as db:
            db.add(
                CanvasAsset(
                    id=working_id,
                    project_id=project_id,
                    asset_type="working",
                    relative_path=f"working/{working_id}.png",
                    original_filename="legacy.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1200,
                    height=600,
                    sha256="b" * 64,
                    source_asset_id=None,
                    transparency_status="transparent",
                    metadata_json="{}",
                )
            )
            db.commit()

        payload = self._state_payload(1)
        payload["semanticState"]["nodes"] = [
            {
                "id": "main-product-source",
                "kind": "product_source",
                "assetId": working_id,
            },
            {
                "id": "main-product-cutout",
                "kind": "auto_cutout",
                "assetId": working_id,
            },
        ]
        payload["semanticState"]["edges"] = [
            {
                "id": "main-product-source-cutout",
                "kind": "product_asset",
                "sourceNodeId": "main-product-source",
                "sourcePort": "product",
                "targetNodeId": "main-product-cutout",
                "targetPort": "reference",
                "skuId": None,
            }
        ]
        payload["semanticState"]["compositionGroups"] = [
            {
                "id": "legacy-group",
                "skuIds": [],
                "productLayerIds": ["legacy-layer"],
                "layoutHash": "legacy-transform",
            }
        ]
        payload["layoutState"]["objectTransforms"] = {
            "legacy-transform": {"x": 0.3, "y": 0.7, "scale": 0.4, "rotation": 30}
        }
        payload["layoutState"]["productLayers"] = [
            {
                "id": "legacy-layer",
                "sourceAssetId": working_id,
                "renderAssetId": working_id,
                "skuId": None,
                "compositionGroupId": "legacy-group",
                "transformId": "legacy-transform",
                "locked": True,
            }
        ]
        safe_client = TestClient(self.app, raise_server_exceptions=False)
        try:
            response = safe_client.put(
                f"/api/canvas/projects/{project_id}/state",
                json=payload,
            )
        finally:
            safe_client.close()

        self.assertEqual(200, response.status_code, response.text)
        group = response.json()["project"]["semanticState"]["compositionGroups"][0]
        self.assertEqual(
            {
                "slot": {"x": 0.0, "y": 0.1, "width": 0.6, "height": 0.8},
                "anchor": {"x": 0.5, "y": 0.5},
                "baseline": 0.7,
                "relativeProductFraction": 0.4,
                "contain": True,
                "safeArea": {"top": 0.05, "right": 0.05, "bottom": 0.05, "left": 0.05},
                "rotation": 30.0,
            },
            group["layout"],
        )
        self.assertRegex(group["layoutHash"], r"^sha256:[0-9a-f]{64}$")

    def test_raw_v1_text_migration_canonicalizes_integral_font_size_and_rejects_bypasses(self):
        created = self._create_project("Legacy text")
        project_id = created["project"]["id"]

        def payload(font_size, *, content="标签", line_text="标签"):
            value = self._state_payload(1)
            value["semanticState"]["nodes"] = [
                {
                    "id": "text-node",
                    "kind": "text_layer",
                    "managedBy": None,
                    "skuId": None,
                    "assetId": None,
                    "modelProfileId": None,
                    "prompt": None,
                    "compositionGroupId": None,
                    "textSnapshotId": "text-layer",
                    "outputBoardId": None,
                    "parameters": {},
                }
            ]
            value["layoutState"]["textSnapshots"] = [
                {
                    "id": "text-layer",
                    "nodeId": "text-node",
                    "content": content,
                    "fontAssetId": "legacy-font",
                    "fontFamily": "Inter",
                    "fontVersion": "1",
                    "boxWidth": 120,
                    "lines": [{"text": line_text, "x": 0, "y": 20, "width": 120}],
                    "fontSize": font_size,
                    "letterSpacing": 0,
                    "lineHeight": 1.2,
                    "align": "left",
                    "baseline": "alphabetic",
                    "zBand": "above-product",
                }
            ]
            return value

        migrated = self.client.put(
            f"/api/canvas/projects/{project_id}/state",
            json=payload(24.0),
        )
        self.assertEqual(200, migrated.status_code, migrated.text)
        text = migrated.json()["project"]["layoutState"]["textSnapshots"][0]
        self.assertEqual(24, text["fontSize"])

        for invalid in (
            payload(24.5),
            payload(True),
            payload(24, content="different"),
            payload(24, content="bad\nline", line_text="bad\nline"),
        ):
            invalid["revision"] = 2
            response = self.client.put(
                f"/api/canvas/projects/{project_id}/state",
                json=invalid,
            )
            self.assertEqual(422, response.status_code, response.text)

    def test_invalid_composition_domain_error_is_safely_mapped_to_422(self):
        created = self._create_project("Invalid composition")
        project_id = created["project"]["id"]
        payload = self._state_payload(1)
        payload["semanticState"]["compositionGroups"] = [
            {
                "id": "stale-group",
                "skuIds": [],
                "productLayerIds": ["stale-layer"],
                "layoutHash": "sha256:" + "0" * 64,
                "layout": {
                    "slot": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                    "anchor": {"x": 0.5, "y": 0.5},
                    "baseline": 0.9,
                    "relativeProductFraction": 0.8,
                    "contain": True,
                    "safeArea": {"top": 0.05, "right": 0.05, "bottom": 0.05, "left": 0.05},
                    "rotation": 0,
                },
            }
        ]
        payload["layoutState"]["objectTransforms"] = {
            "stale-transform": {"x": 0.5, "y": 0.9, "scale": 0.8, "rotation": 0}
        }
        payload["layoutState"]["productLayers"] = [
            {
                "id": "stale-layer",
                "sourceAssetId": "missing-working",
                "renderAssetId": "missing-working",
                "allowOpaqueFallback": False,
                "skuId": None,
                "compositionGroupId": "stale-group",
                "transformId": "stale-transform",
                "locked": True,
            }
        ]
        safe_client = TestClient(self.app, raise_server_exceptions=False)
        try:
            response = safe_client.put(
                f"/api/canvas/projects/{project_id}/state",
                json=payload,
            )
        finally:
            safe_client.close()

        self.assertEqual(422, response.status_code, response.text)
        self.assertEqual(
            {
                "detail": "Canvas composition state is invalid",
                "code": "canvas_composition_invalid",
            },
            response.json(),
        )
        self.assertNotIn("stale layout hash", response.text)

    def test_malformed_composition_sections_remain_strict_model_and_http_422(self):
        from routers.canvas.projects import ProjectStateRequest

        created = self._create_project("Malformed composition")
        project_id = created["project"]["id"]
        cases = (
            ("compositionGroups", {"semanticState": {"compositionGroups": None}}),
            ("productLayers", {"layoutState": {"productLayers": None}}),
        )
        safe_client = TestClient(self.app, raise_server_exceptions=False)
        try:
            for label, patch_payload in cases:
                with self.subTest(section=label):
                    payload = self._state_payload(1)
                    for section, values in patch_payload.items():
                        payload[section].update(values)
                    with self.assertRaises(ValidationError):
                        ProjectStateRequest.model_validate(payload)
                    response = safe_client.put(
                        f"/api/canvas/projects/{project_id}/state",
                        json=payload,
                    )
                    self.assertEqual(422, response.status_code, response.text)
                    self.assertNotIn("NoneType", response.text)
                    self.assertNotIn("not iterable", response.text)
        finally:
            safe_client.close()

    def test_sku_list_create_update_and_delete_return_project_snapshot(self):
        created = self._create_project()
        project_id = created["project"]["id"]

        listed = self.client.get(f"/api/canvas/projects/{project_id}/skus")
        self.assertEqual(created, listed.json())

        added = self.client.post(
            f"/api/canvas/projects/{project_id}/skus",
            json={
                "revision": 1,
                "name": "Vanilla",
                "prompt": "clean packshot",
                "config": {"quantity": 2},
            },
        )
        self.assertEqual(201, added.status_code, added.text)
        self.assertEqual(2, added.json()["revision"])
        self.assertEqual(1, len(added.json()["skus"]))
        sku = added.json()["skus"][0]
        self.assertEqual(
            {"id", "projectId", "name", "sortOrder", "referenceAssetId", "prompt", "config"},
            set(sku),
        )
        self.assertEqual({"quantity": 2}, sku["config"])

        updated = self.client.patch(
            f"/api/canvas/projects/{project_id}/skus/{sku['id']}",
            json={"revision": 2, "name": "Vanilla XL", "referenceAssetId": None},
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual(("Vanilla XL", 3), (
            updated.json()["skus"][0]["name"],
            updated.json()["revision"],
        ))

        deleted = self.client.request(
            "DELETE",
            f"/api/canvas/projects/{project_id}/skus/{sku['id']}",
            json={"revision": 3},
        )
        self.assertEqual(200, deleted.status_code, deleted.text)
        self.assertEqual(([], 4), (deleted.json()["skus"], deleted.json()["revision"]))

    def test_sku_reorder_swaps_occupied_sort_orders_atomically(self):
        created = self._create_project()
        project_id = created["project"]["id"]
        first = self.client.post(
            f"/api/canvas/projects/{project_id}/skus",
            json={"revision": 1, "name": "First"},
        ).json()
        second = self.client.post(
            f"/api/canvas/projects/{project_id}/skus",
            json={"revision": 2, "name": "Second"},
        ).json()
        first_sku, second_sku = second["skus"]

        reordered = self.client.patch(
            f"/api/canvas/projects/{project_id}/skus/{second_sku['id']}",
            json={"revision": 3, "sortOrder": first_sku["sortOrder"]},
        )

        self.assertEqual(200, reordered.status_code, reordered.text)
        self.assertEqual(4, reordered.json()["revision"])
        self.assertEqual(
            [(second_sku["id"], 0), (first_sku["id"], 1)],
            [(sku["id"], sku["sortOrder"]) for sku in reordered.json()["skus"]],
        )

    def test_missing_and_cross_project_sku_have_identical_non_leaking_404(self):
        owner = self._create_project("Owner")
        foreign = self._create_project("Foreign")
        owner_id = owner["project"]["id"]
        foreign_id = foreign["project"]["id"]
        added = self.client.post(
            f"/api/canvas/projects/{foreign_id}/skus",
            json={"revision": 1, "name": "Foreign SKU"},
        )
        self.assertEqual(201, added.status_code, added.text)
        foreign_sku_id = added.json()["skus"][0]["id"]

        foreign_response = self.client.patch(
            f"/api/canvas/projects/{owner_id}/skus/{foreign_sku_id}",
            json={"revision": 1, "name": "Do not leak"},
        )
        missing_response = self.client.patch(
            f"/api/canvas/projects/{owner_id}/skus/{uuid4()}",
            json={"revision": 1, "name": "Still missing"},
        )
        self.assertEqual(404, foreign_response.status_code, foreign_response.text)
        self.assertEqual(404, missing_response.status_code, missing_response.text)
        self.assertEqual(missing_response.json(), foreign_response.json())
        self.assertNotIn(foreign_id, foreign_response.text)
        self.assertNotIn(foreign_sku_id, foreign_response.text)

    def test_stale_revision_is_top_level_camel_case_conflict_payload(self):
        created = self._create_project()
        project_id = created["project"]["id"]
        winner = self.client.patch(
            f"/api/canvas/projects/{project_id}",
            json={"revision": 1, "name": "Winner"},
        )
        self.assertEqual(200, winner.status_code, winner.text)

        stale = self.client.patch(
            f"/api/canvas/projects/{project_id}",
            json={"revision": 1, "name": "Stale writer"},
        )
        self.assertEqual(409, stale.status_code, stale.text)
        self.assertEqual(
            {
                "detail": "Canvas project revision conflict",
                "code": "canvas_revision_conflict",
                "currentRevision": 2,
            },
            stale.json(),
        )
        self.assertNotIn("current_revision", stale.json())

    def test_write_schemas_reject_unknown_fields_before_domain_lookup(self):
        project_id = str(uuid4())
        sku_id = str(uuid4())
        cases = (
            ("POST", "/api/canvas/projects", {"name": "Unknown", "unknown": True}),
            ("PATCH", f"/api/canvas/projects/{project_id}", {"revision": 1, "name": "x", "unknown": True}),
            ("PUT", f"/api/canvas/projects/{project_id}/state", self._state_payload(1, unknown=True)),
            ("POST", f"/api/canvas/projects/{project_id}/archive", {"revision": 1, "unknown": True}),
            ("POST", f"/api/canvas/projects/{project_id}/restore", {"revision": 1, "unknown": True}),
            ("DELETE", f"/api/canvas/projects/{project_id}", {"revision": 1, "unknown": True}),
            ("POST", f"/api/canvas/projects/{project_id}/skus", {"revision": 1, "name": "x", "unknown": True}),
            ("PATCH", f"/api/canvas/projects/{project_id}/skus/{sku_id}", {"revision": 1, "name": "x", "unknown": True}),
            ("DELETE", f"/api/canvas/projects/{project_id}/skus/{sku_id}", {"revision": 1, "unknown": True}),
        )
        for method, path, payload in cases:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, json=payload)
                self.assertEqual(422, response.status_code, response.text)

    def test_canvas_patch_routes_are_allowed_by_cors_preflight(self):
        cors_options = next(
            middleware.kwargs
            for middleware in self.app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        )

        self.assertIn("PATCH", cors_options["allow_methods"])

    def test_lifecycle_domain_conflicts_are_precisely_mapped(self):
        from services.canvas import projects as project_service

        created = self._create_project()
        project_id = created["project"]["id"]
        with patch.object(
            project_service,
            "PROJECT_ACTIVITY_GUARDS",
            [lambda _db, _project_id: [{"id": "running-op", "status": "running"}]],
        ):
            active = self.client.post(
                f"/api/canvas/projects/{project_id}/archive",
                json={"revision": 1},
            )
        self.assertEqual(409, active.status_code, active.text)
        self.assertEqual("canvas_project_activity_conflict", active.json()["code"])
        self.assertEqual([{"id": "running-op", "status": "running"}], active.json()["activities"])

        archived = self.client.post(
            f"/api/canvas/projects/{project_id}/archive",
            json={"revision": 1},
        )
        self.assertEqual(200, archived.status_code, archived.text)
        repeated = self.client.post(
            f"/api/canvas/projects/{project_id}/archive",
            json={"revision": 2},
        )
        self.assertEqual(409, repeated.status_code, repeated.text)
        self.assertEqual("canvas_project_status_conflict", repeated.json()["code"])
        self.assertEqual("archived", repeated.json()["status"])

    def test_state_ownership_and_live_sku_reference_conflicts_are_mapped(self):
        owner = self._create_project("Owner")
        foreign = self._create_project("Foreign")
        owner_id = owner["project"]["id"]
        foreign_id = foreign["project"]["id"]
        foreign_sku = self.client.post(
            f"/api/canvas/projects/{foreign_id}/skus",
            json={"revision": 1, "name": "Foreign SKU"},
        ).json()["skus"][0]
        ownership_state = self._state_payload(1)
        ownership_state["semanticState"]["nodes"] = [
            {"id": "foreign-node", "kind": "sku_reference", "skuId": foreign_sku["id"]}
        ]
        ownership = self.client.put(
            f"/api/canvas/projects/{owner_id}/state",
            json=ownership_state,
        )
        self.assertEqual(404, ownership.status_code, ownership.text)
        self.assertEqual(
            {"detail": "Canvas resource not found", "code": "canvas_resource_not_found"},
            ownership.json(),
        )
        self.assertNotIn(foreign_sku["id"], ownership.text)

        local_sku = self.client.post(
            f"/api/canvas/projects/{owner_id}/skus",
            json={"revision": 1, "name": "Local SKU"},
        ).json()["skus"][0]
        referenced_state = self._state_payload(2)
        referenced_state["semanticState"]["nodes"] = [
            {"id": "local-node", "kind": "sku_reference", "skuId": local_sku["id"]}
        ]
        saved = self.client.put(
            f"/api/canvas/projects/{owner_id}/state",
            json=referenced_state,
        )
        self.assertEqual(200, saved.status_code, saved.text)
        blocked = self.client.request(
            "DELETE",
            f"/api/canvas/projects/{owner_id}/skus/{local_sku['id']}",
            json={"revision": 3},
        )
        self.assertEqual(409, blocked.status_code, blocked.text)
        self.assertEqual("canvas_sku_reference_conflict", blocked.json()["code"])
        self.assertIn("nodes", blocked.json()["references"])

    def test_project_delete_commits_deleting_before_background_finalizer_runs(self):
        from canvas_models import CanvasProject
        from services.canvas import projects as project_service

        created = self._create_project("Delete in background")
        project_id = created["project"]["id"]
        observed_statuses = []
        received_factories = []

        def observe_committed_status(db_factory, *, project_id):
            received_factories.append(db_factory)
            with self.Session() as db:
                observed_statuses.append(db.get(CanvasProject, project_id).status)

        with patch.object(
            project_service,
            "finalize_deleting_project",
            side_effect=observe_committed_status,
        ) as finalizer:
            response = self.client.request(
                "DELETE",
                f"/api/canvas/projects/{project_id}",
                json={"revision": 1},
            )

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(("deleting", 2), (
            response.json()["project"]["status"],
            response.json()["revision"],
        ))
        self.assertEqual(["deleting"], observed_statuses)
        self.assertEqual([self.Session], received_factories)
        self.assertEqual(1, finalizer.call_count)

    def test_project_delete_finalizer_uses_overridden_database_and_removes_tree(self):
        from canvas_models import CanvasProject
        from database import Base
        from services.canvas import projects as project_service, storage

        global_db_path = Path(self.tmp.name) / "canvas-global-factory.db"
        global_engine = create_engine(
            f"sqlite:///{global_db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        GlobalSession = sessionmaker(bind=global_engine, expire_on_commit=False)
        Base.metadata.create_all(bind=global_engine)
        with GlobalSession() as db:
            sentinel = project_service.create_project(db, name="Global sentinel")
            sentinel_id = sentinel.id

        global_factory_calls = 0

        def tracking_global_factory():
            nonlocal global_factory_calls
            global_factory_calls += 1
            return GlobalSession()

        created = self._create_project("Delete from overridden database")
        project_id = created["project"]["id"]
        data_root = Path(self.tmp.name) / "canvas-delete-data"
        try:
            with (
                patch.object(storage, "CANVAS_DATA_DIR", str(data_root)),
                patch.object(
                    self.canvas_project_routes,
                    "SessionLocal",
                    tracking_global_factory,
                ),
            ):
                project_root = storage.ensure_project_tree(project_id)
                (project_root / "tmp" / "partial.bin").write_bytes(b"partial")
                response = self.client.request(
                    "DELETE",
                    f"/api/canvas/projects/{project_id}",
                    json={"revision": 1},
                )

            with self.Session() as db:
                target = db.get(CanvasProject, project_id)
                target_status = target.status if target is not None else None
            with GlobalSession() as db:
                sentinel_survives = db.get(CanvasProject, sentinel_id) is not None

            self.assertEqual(200, response.status_code, response.text)
            self.assertEqual(("deleting", 2), (
                response.json()["project"]["status"],
                response.json()["revision"],
            ))
            self.assertEqual(
                (False, None, 0, True),
                (
                    project_root.exists(),
                    target_status,
                    global_factory_calls,
                    sentinel_survives,
                ),
            )
        finally:
            global_engine.dispose()

    def test_unexpected_service_exception_is_not_converted_to_success(self):
        from services.canvas import projects as project_service

        client = TestClient(self.app, raise_server_exceptions=False)
        try:
            with patch.object(project_service, "list_projects", side_effect=RuntimeError("boom")):
                response = client.get("/api/canvas/projects")
        finally:
            client.close()

        self.assertEqual(500, response.status_code, response.text)

    def test_lifespan_recovers_deleting_projects_before_serving(self):
        import asyncio
        import database
        import main
        from services.canvas import projects as project_service

        calls = []

        async def scenario():
            with (
                patch.object(main, "init_db", side_effect=lambda: calls.append("init")),
                patch("services.canvas.providers.bootstrap.bootstrap_builtin_image_profiles"),
                patch("services.job_runs.recover_interrupted_jobs", side_effect=lambda: calls.append("jobs")),
                patch.object(
                    project_service,
                    "recover_deleting_projects",
                    side_effect=lambda factory: calls.append(("canvas", factory)),
                ),
                patch(
                    "services.canvas.runtime.start_canvas_runtime",
                    side_effect=lambda app, *, db_factory: calls.append(
                        ("canvas-runtime-start", app, db_factory)
                    ),
                ),
                patch(
                    "services.canvas.runtime.stop_canvas_runtime",
                    side_effect=lambda app: calls.append(("canvas-runtime-stop", app)),
                ),
                patch("vector_store.init_vector_store", side_effect=lambda: calls.append("vectors")),
                patch("services.vector_sync.start_vector_sync_worker", side_effect=lambda: calls.append("start")),
                patch("services.vector_sync.stop_vector_sync_worker", side_effect=lambda: calls.append("stop")),
            ):
                async with main.lifespan(main.app):
                    calls.append("serving")

        asyncio.run(scenario())

        canvas_calls = [call for call in calls if isinstance(call, tuple) and call[0] == "canvas"]
        self.assertEqual(1, len(canvas_calls), calls)
        canvas_call = canvas_calls[0]
        self.assertIs(database.SessionLocal, canvas_call[1])
        self.assertLess(calls.index(canvas_call), calls.index("serving"))
        runtime_start = next(call for call in calls if isinstance(call, tuple) and call[0] == "canvas-runtime-start")
        runtime_stop = next(call for call in calls if isinstance(call, tuple) and call[0] == "canvas-runtime-stop")
        self.assertIs(main.app, runtime_start[1])
        self.assertIs(database.SessionLocal, runtime_start[2])
        self.assertIs(main.app, runtime_stop[1])
        self.assertLess(calls.index(runtime_start), calls.index("serving"))
        self.assertLess(calls.index("serving"), calls.index(runtime_stop))
        self.assertLess(calls.index("stop"), calls.index(runtime_stop))

    def test_lifespan_stops_canvas_runtime_when_later_startup_fails(self):
        import asyncio
        import main

        calls = []

        async def scenario():
            with (
                patch.object(main, "init_db"),
                patch("services.canvas.providers.bootstrap.bootstrap_builtin_image_profiles"),
                patch("services.canvas.projects.recover_deleting_projects"),
                patch(
                    "services.canvas.runtime.start_canvas_runtime",
                    side_effect=lambda app, *, db_factory: calls.append("canvas-start"),
                ),
                patch(
                    "services.canvas.runtime.stop_canvas_runtime",
                    side_effect=lambda app: calls.append("canvas-stop"),
                ),
                patch(
                    "services.job_runs.recover_interrupted_jobs",
                    side_effect=RuntimeError("later startup failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "later startup failed"):
                    async with main.lifespan(main.app):
                        self.fail("lifespan must not serve after startup failure")

        asyncio.run(scenario())
        self.assertEqual(["canvas-start", "canvas-stop"], calls)

    def test_lifespan_stops_canvas_runtime_when_vector_shutdown_fails(self):
        import asyncio
        import main

        calls = []

        def fail_vector_stop():
            calls.append("vector-stop")
            raise RuntimeError("vector stop failed")

        async def scenario():
            with (
                patch.object(main, "init_db"),
                patch("services.canvas.providers.bootstrap.bootstrap_builtin_image_profiles"),
                patch("services.canvas.projects.recover_deleting_projects"),
                patch(
                    "services.canvas.runtime.start_canvas_runtime",
                    side_effect=lambda app, *, db_factory: calls.append("canvas-start"),
                ),
                patch(
                    "services.canvas.runtime.stop_canvas_runtime",
                    side_effect=lambda app: calls.append("canvas-stop"),
                ),
                patch("services.job_runs.recover_interrupted_jobs"),
                patch("vector_store.init_vector_store"),
                patch(
                    "services.vector_sync.start_vector_sync_worker",
                    side_effect=lambda: calls.append("vector-start"),
                ),
                patch(
                    "services.vector_sync.stop_vector_sync_worker",
                    side_effect=fail_vector_stop,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "vector stop failed"):
                    async with main.lifespan(main.app):
                        calls.append("serving")

        asyncio.run(scenario())
        self.assertEqual(
            ["canvas-start", "vector-start", "serving", "vector-stop", "canvas-stop"],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
