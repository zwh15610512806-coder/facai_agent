import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker


def _png_bytes(*, transparent: bool, size: tuple[int, int] = (32, 32)) -> bytes:
    if transparent:
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        for x in range(size[0] // 4, 3 * size[0] // 4):
            for y in range(size[1] // 4, 3 * size[1] // 4):
                image.putpixel((x, y), (210, 30, 40, 255))
    else:
        image = Image.new("RGB", size, (248, 248, 248))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _complex_opaque_png_bytes(size: tuple[int, int] = (32, 32)) -> bytes:
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = (
                (x * 29 + y * 7) % 256,
                (x * 11 + y * 31) % 256,
                (x * y * 5 + 73) % 256,
            )
    output = io.BytesIO()
    image.save(output, format="PNG")
    image.close()
    return output.getvalue()


class _FakeOperationService:
    def __init__(self):
        self.enqueue_calls = []
        self.automatic_calls = []
        self.retry_calls = []

    def enqueue_asset_operation(
        self,
        db,
        *,
        project_id,
        operation_type,
        input_asset_id,
        idempotency_key,
        request_snapshot,
    ):
        from canvas_models import CanvasAssetOperation

        self.enqueue_calls.append(
            {
                "project_id": project_id,
                "operation_type": operation_type,
                "input_asset_id": input_asset_id,
                "idempotency_key": idempotency_key,
                "request_snapshot": request_snapshot,
            }
        )
        existing = db.scalar(
            select(CanvasAssetOperation).where(
                CanvasAssetOperation.project_id == project_id,
                CanvasAssetOperation.operation_type == operation_type,
                CanvasAssetOperation.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        operation = CanvasAssetOperation(
            project_id=project_id,
            operation_type=operation_type,
            input_asset_id=input_asset_id,
            idempotency_key=idempotency_key,
            request_snapshot_json=json.dumps(request_snapshot, sort_keys=True),
        )
        db.add(operation)
        db.flush()
        return operation

    def enqueue_automatic_cutout(self, db, *, project_id, input_asset_id):
        self.automatic_calls.append((project_id, input_asset_id))
        return self.enqueue_asset_operation(
            db,
            project_id=project_id,
            operation_type="cutout",
            input_asset_id=input_asset_id,
            idempotency_key=f"automatic-cutout:{input_asset_id}",
            request_snapshot={"inputAssetId": input_asset_id, "mode": "automatic"},
        )

    def retry_cutout_for_asset(
        self,
        db,
        *,
        input_asset_id,
        client_request_id,
    ):
        from canvas_models import CanvasAsset

        self.retry_calls.append((input_asset_id, client_request_id))
        asset = db.get(CanvasAsset, input_asset_id)
        return self.enqueue_asset_operation(
            db,
            project_id=asset.project_id,
            operation_type="cutout",
            input_asset_id=input_asset_id,
            idempotency_key=f"explicit-recutout:{input_asset_id}:{client_request_id}",
            request_snapshot={"mode": "explicit-recutout"},
        )


class CanvasAssetApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "canvas-data"
        self.db_path = Path(self.tmp.name) / "canvas-api.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        import canvas_models  # noqa: F401 - register all Canvas tables.
        from database import Base, get_db
        from routers.canvas import assets as asset_routes
        from services.canvas import storage

        Base.metadata.create_all(bind=self.engine)
        self.asset_routes = asset_routes
        self.storage = storage
        self.operations = _FakeOperationService()
        self.storage_patch = patch.object(storage, "CANVAS_DATA_DIR", str(self.data_root))
        self.operation_patch = patch.object(
            asset_routes,
            "_operation_service",
            return_value=self.operations,
        )
        self.storage_patch.start()
        self.operation_patch.start()

        def override_db():
            with self.Session() as db:
                yield db

        self.app = FastAPI()
        self.app.include_router(asset_routes.router, prefix="/api/canvas")
        self.app.dependency_overrides[get_db] = override_db
        self.get_db = get_db
        self.client = TestClient(self.app)
        self.project_id = self._create_project("Asset API")

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.pop(self.get_db, None)
        self.operation_patch.stop()
        self.storage_patch.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def _create_project(self, name):
        from canvas_models import CanvasProject
        from services.canvas.project_state import empty_project_state_json

        semantic_state, layout_state = empty_project_state_json()
        with self.Session() as db:
            project = CanvasProject(
                name=name,
                semantic_state=semantic_state,
                layout_state=layout_state,
            )
            db.add(project)
            db.commit()
            return project.id

    def _upload(self, data, *, filename="product.png", project_id=None):
        return self.client.post(
            f"/api/canvas/projects/{project_id or self.project_id}/assets",
            files={"file": (filename, data, "image/png")},
        )

    def _persist_without_preview(self, data, *, project_id=None):
        from services.canvas.assets import persist_uploaded_source

        with self.Session() as db:
            uploaded = persist_uploaded_source(
                db,
                project_id=project_id or self.project_id,
                filename="direct.png",
                declared_mime="image/png",
                data=data,
            )
            db.commit()
            return uploaded.source.id, uploaded.working.id

    def test_upload_list_and_read_only_access_never_enqueue_extra_cutouts(self):
        response = self._upload(_png_bytes(transparent=False))

        self.assertEqual(201, response.status_code, response.text)
        payload = response.json()
        self.assertEqual({"source", "working", "preview", "operation"}, set(payload))
        self.assertEqual("source", payload["source"]["assetType"])
        self.assertEqual("working", payload["working"]["assetType"])
        self.assertEqual("opaque", payload["working"]["transparencyStatus"])
        self.assertEqual(payload["working"]["id"], payload["preview"]["sourceAssetId"])
        self.assertEqual("queued", payload["operation"]["status"])
        self.assertEqual(
            [(self.project_id, payload["working"]["id"])],
            self.operations.automatic_calls,
        )
        self.assertEqual(1, len(self.operations.enqueue_calls))

        listed = self.client.get(f"/api/canvas/projects/{self.project_id}/assets")
        full = self.client.get(
            f"/api/canvas/assets/{payload['working']['id']}/content"
        )
        preview = self.client.get(
            f"/api/canvas/assets/{payload['working']['id']}/content?variant=preview"
        )
        listed_again = self.client.get(f"/api/canvas/projects/{self.project_id}/assets")

        self.assertEqual(3, len(listed.json()["assets"]))
        self.assertEqual(200, full.status_code, full.text)
        self.assertEqual(200, preview.status_code, preview.text)
        self.assertEqual(200, listed_again.status_code, listed_again.text)
        self.assertEqual(1, len(self.operations.enqueue_calls))
        with self.Session() as db:
            from canvas_models import CanvasAssetOperation

            self.assertEqual(1, db.scalar(select(func.count(CanvasAssetOperation.id))))

    def test_transparent_upload_creates_preview_without_cutout_operation(self):
        response = self._upload(_png_bytes(transparent=True), filename="transparent.png")

        self.assertEqual(201, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("transparent", payload["working"]["transparencyStatus"])
        self.assertIsNone(payload["operation"])
        self.assertEqual([], self.operations.enqueue_calls)
        with self.Session() as db:
            from canvas_models import CanvasAsset, CanvasAssetOperation

            assets = db.scalars(
                select(CanvasAsset).where(CanvasAsset.project_id == self.project_id)
            ).all()
            self.assertEqual({"source", "working", "preview"}, {row.asset_type for row in assets})
            self.assertEqual(0, db.scalar(select(func.count(CanvasAssetOperation.id))))

    def test_complex_opaque_background_automatically_enqueues_exactly_one_cutout(self):
        response = self._upload(
            _complex_opaque_png_bytes(),
            filename="complex-background.png",
        )

        self.assertEqual(201, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("opaque", payload["working"]["transparencyStatus"])
        self.assertEqual("queued", payload["operation"]["status"])
        self.assertEqual(
            [(self.project_id, payload["working"]["id"])],
            self.operations.automatic_calls,
        )
        self.assertEqual(1, len(self.operations.enqueue_calls))
        self.assertEqual(payload["working"]["id"], payload["preview"]["sourceAssetId"])

    def test_content_streams_verified_fixed_handle_bytes_with_mime_and_nosniff(self):
        source_bytes = _png_bytes(transparent=True)
        uploaded = self._upload(source_bytes).json()

        with patch.object(
            self.storage,
            "_pinned_file_bytes",
            wraps=self.storage._pinned_file_bytes,
        ) as pinned_reader:
            source = self.client.get(
                f"/api/canvas/assets/{uploaded['source']['id']}/content"
            )
            preview = self.client.get(
                f"/api/canvas/assets/{uploaded['working']['id']}/content?variant=preview"
            )

        self.assertEqual(source_bytes, source.content)
        self.assertEqual("image/png", source.headers["content-type"])
        self.assertEqual("nosniff", source.headers["x-content-type-options"])
        self.assertEqual("image/png", preview.headers["content-type"])
        self.assertEqual("nosniff", preview.headers["x-content-type-options"])
        self.assertEqual(2, pinned_reader.call_count)

    def test_missing_preview_is_explicit_and_never_falls_back_to_full_content(self):
        _source_id, working_id = self._persist_without_preview(
            _png_bytes(transparent=False)
        )

        response = self.client.get(
            f"/api/canvas/assets/{working_id}/content?variant=preview"
        )

        self.assertEqual(404, response.status_code, response.text)
        self.assertEqual("canvas_preview_missing", response.json()["code"])
        self.assertNotIn("relative", response.text.lower())

    def test_cutout_content_preview_variant_resolves_its_distinct_proxy(self):
        from canvas_models import CanvasAsset
        from services.canvas import assets, previews

        _source_id, working_id = self._persist_without_preview(
            _png_bytes(transparent=False)
        )
        cutout_bytes = _png_bytes(transparent=True, size=(32, 16))
        with self.Session() as db:
            cutout = assets.persist_derived_image(
                db,
                project_id=self.project_id,
                asset_type="cutout",
                data=cutout_bytes,
                mime_type="image/png",
                source_asset_id=working_id,
                metadata={"processorVersion": "test-cutout-v1"},
                processor_version="test-cutout-v1",
            )
            proxy = previews.create_preview_proxy(
                db,
                project_id=self.project_id,
                source_asset=cutout,
                max_edge=8,
            )
            db.commit()
            cutout_id, proxy_id = cutout.id, proxy.id
            proxy_bytes = assets.read_verified_asset_bytes(
                db,
                asset=db.get(CanvasAsset, proxy_id),
            )

        full = self.client.get(f"/api/canvas/assets/{cutout_id}/content")
        preview_response = self.client.get(
            f"/api/canvas/assets/{cutout_id}/content?variant=preview"
        )
        self.assertEqual(200, full.status_code, full.text)
        self.assertEqual(200, preview_response.status_code, preview_response.text)
        self.assertEqual(cutout_bytes, full.content)
        self.assertEqual(proxy_bytes, preview_response.content)
        self.assertNotEqual(full.content, preview_response.content)

    def test_upload_size_boundary_and_failed_commit_leave_no_asset_files_or_rows(self):
        with patch.object(self.asset_routes, "CANVAS_MAX_UPLOAD_BYTES", 32):
            too_large = self._upload(b"x" * 33, filename="too-large.png")
        self.assertEqual(413, too_large.status_code, too_large.text)
        self.assertEqual("canvas_upload_too_large", too_large.json()["code"])

        failing_db = self.Session()

        def override_failing_db():
            yield failing_db

        self.app.dependency_overrides[self.get_db] = override_failing_db
        client = TestClient(self.app, raise_server_exceptions=False)
        try:
            with patch.object(failing_db, "commit", side_effect=RuntimeError("commit failed")):
                failed = client.post(
                    f"/api/canvas/projects/{self.project_id}/assets",
                    files={"file": ("rollback.png", _png_bytes(transparent=False), "image/png")},
                )
        finally:
            client.close()
            failing_db.close()

        self.assertEqual(500, failed.status_code, failed.text)
        with self.Session() as db:
            from canvas_models import CanvasAsset, CanvasAssetOperation

            self.assertEqual(0, db.scalar(select(func.count(CanvasAsset.id))))
            self.assertEqual(0, db.scalar(select(func.count(CanvasAssetOperation.id))))
        self.assertEqual([], [path for path in self.data_root.rglob("*") if path.is_file()])

    def test_delete_reports_every_live_and_historical_reference_kind(self):
        from canvas_models import CanvasAssetOperation, CanvasProject, CanvasProjectSku
        from services.canvas.project_state import dump_project_state
        from services.canvas.schemas import empty_layout_state, empty_semantic_state

        target_id, derived_id = self._persist_without_preview(_png_bytes(transparent=False))
        other_id, _other_working_id = self._persist_without_preview(_png_bytes(transparent=True))
        with self.Session() as db:
            project = db.get(CanvasProject, self.project_id)
            semantic = empty_semantic_state().model_dump(by_alias=True)
            semantic["outputBoards"] = [
                {
                    "id": "board-1",
                    "outputNodeId": "output-1",
                    "outputType": "main",
                    "skuId": None,
                    "sortOrder": 0,
                    "selectedResultAssetId": target_id,
                }
            ]
            layout = empty_layout_state().model_dump(by_alias=True)
            layout["productLayers"] = [
                {
                    "id": "layer-1",
                    "sourceAssetId": target_id,
                    "renderAssetId": target_id,
                    "skuId": None,
                    "compositionGroupId": None,
                    "transformId": "transform-1",
                    "locked": True,
                }
            ]
            project.semantic_state = dump_project_state(semantic)
            project.layout_state = dump_project_state(layout)
            db.add(
                CanvasProjectSku(
                    project_id=self.project_id,
                    name="Reference SKU",
                    sort_order=0,
                    reference_asset_id=target_id,
                )
            )
            db.add_all(
                [
                    CanvasAssetOperation(
                        project_id=self.project_id,
                        operation_type="cutout",
                        status="queued",
                        input_asset_id=target_id,
                        idempotency_key="target-input",
                    ),
                    CanvasAssetOperation(
                        project_id=self.project_id,
                        operation_type="cutout",
                        status="succeeded",
                        input_asset_id=other_id,
                        output_asset_id=target_id,
                        idempotency_key="target-output",
                    ),
                ]
            )
            db.commit()

        response = self.client.delete(f"/api/canvas/assets/{target_id}")

        self.assertEqual(409, response.status_code, response.text)
        self.assertEqual("canvas_asset_reference_conflict", response.json()["code"])
        self.assertEqual(
            {
                "derivedAsset",
                "operationInput",
                "operationOutput",
                "project:outputBoards",
                "project:productLayers",
                "skuReference",
            },
            set(response.json()["references"]),
        )
        self.assertNotIn(derived_id, response.text)
        self.assertNotIn(target_id, response.text)
        self.assertNotIn("relative_path", response.text)

    def test_unreferenced_delete_soft_deletes_emits_event_and_preserves_file(self):
        uploaded = self._upload(_png_bytes(transparent=True)).json()
        preview_id = uploaded["preview"]["id"]
        with self.Session() as db:
            from canvas_models import CanvasAsset

            preview = db.get(CanvasAsset, preview_id)
            path = self.storage.resolve_asset_path(preview, project_id=self.project_id)
        self.assertTrue(path.is_file())

        response = self.client.delete(f"/api/canvas/assets/{preview_id}")

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({"assetId": preview_id, "status": "deleted"}, response.json())
        self.assertTrue(path.is_file())
        self.assertEqual(
            404,
            self.client.get(f"/api/canvas/assets/{preview_id}/content").status_code,
        )
        with self.Session() as db:
            from canvas_models import CanvasAsset, CanvasEvent

            self.assertIsNotNone(db.get(CanvasAsset, preview_id).deleted_at)
            event = db.scalar(
                select(CanvasEvent).where(CanvasEvent.event_type == "asset.deleted")
            )
            self.assertIsNotNone(event)
            self.assertEqual(preview_id, json.loads(event.payload_json)["assetId"])

    def test_delete_rejects_archived_and_deleting_projects_without_mutation(self):
        from canvas_models import CanvasAsset, CanvasEvent, CanvasProject

        for project_status in ("archived", "deleting"):
            with self.subTest(project_status=project_status):
                project_id = self._create_project(f"Delete {project_status}")
                uploaded = self._upload(
                    _png_bytes(transparent=True),
                    project_id=project_id,
                ).json()
                preview_id = uploaded["preview"]["id"]
                with self.Session() as db:
                    project = db.get(CanvasProject, project_id)
                    project.status = project_status
                    db.commit()

                response = self.client.delete(f"/api/canvas/assets/{preview_id}")

                self.assertEqual(409, response.status_code, response.text)
                self.assertEqual("canvas_asset_project_inactive", response.json()["code"])
                with self.Session() as db:
                    self.assertIsNone(db.get(CanvasAsset, preview_id).deleted_at)
                    deleted_events = db.scalars(
                        select(CanvasEvent).where(
                            CanvasEvent.project_id == project_id,
                            CanvasEvent.event_type == "asset.deleted",
                        )
                    ).all()
                    self.assertEqual([], deleted_events)

    def test_cutout_retry_is_client_idempotent_and_rejects_unknown_fields(self):
        uploaded = self._upload(_png_bytes(transparent=True)).json()
        working_id = uploaded["working"]["id"]
        path = f"/api/canvas/assets/{working_id}/cutout/retry"

        first = self.client.post(path, json={"clientRequestId": "retry-click-1"})
        second = self.client.post(path, json={"clientRequestId": "retry-click-1"})
        invalid = self.client.post(
            path,
            json={"clientRequestId": "retry-click-2", "unexpected": True},
        )

        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual("cutout", first.json()["operationType"])
        self.assertEqual(
            [(working_id, "retry-click-1"), (working_id, "retry-click-1")],
            self.operations.retry_calls,
        )
        self.assertEqual(422, invalid.status_code, invalid.text)
        with self.Session() as db:
            from canvas_models import CanvasAssetOperation

            self.assertEqual(1, db.scalar(select(func.count(CanvasAssetOperation.id))))

    def test_real_cutout_retry_requeues_and_preserves_client_idempotency_across_success(self):
        from canvas_models import CanvasAssetOperation
        from services.canvas import operations as operation_service

        with patch.object(
            self.asset_routes,
            "_operation_service",
            return_value=operation_service,
        ):
            uploaded = self._upload(_png_bytes(transparent=False)).json()
            working_id = uploaded["working"]["id"]
            operation_id = uploaded["operation"]["id"]
            with self.Session() as db:
                operation = db.get(CanvasAssetOperation, operation_id)
                operation.status = "failed"
                operation.safe_error_json = json.dumps(
                    {"code": "cutout_failed", "message": "safe", "retryable": True}
                )
                db.commit()

            path = f"/api/canvas/assets/{working_id}/cutout/retry"
            first = self.client.post(path, json={"clientRequestId": "client-a"})
            conflict_client = TestClient(self.app, raise_server_exceptions=False)
            try:
                conflict = conflict_client.post(
                    path,
                    json={"clientRequestId": "client-b"},
                )
            finally:
                conflict_client.close()

            with self.Session() as db:
                operation = db.get(CanvasAssetOperation, operation_id)
                operation.status = "succeeded"
                db.commit()
            repeated_after_success = self.client.post(
                path,
                json={"clientRequestId": "client-a"},
            )

        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual(operation_id, first.json()["id"])
        self.assertEqual(409, conflict.status_code, conflict.text)
        self.assertEqual("canvas_operation_status_conflict", conflict.json()["code"])
        self.assertNotIn(operation_id, conflict.text)
        self.assertEqual(200, repeated_after_success.status_code, repeated_after_success.text)
        self.assertEqual(operation_id, repeated_after_success.json()["id"])
        with self.Session() as db:
            self.assertEqual(1, db.scalar(select(func.count(CanvasAssetOperation.id))))

    def test_retry_maps_operation_domain_errors_without_internal_identifier_leaks(self):
        from services.canvas import operations as operation_service
        from services.canvas import projects as project_service

        working_id = self._upload(_png_bytes(transparent=True)).json()["working"]["id"]
        path = f"/api/canvas/assets/{working_id}/cutout/retry"
        cases = (
            (
                operation_service.CanvasOperationNotFound("secret-operation"),
                404,
                "canvas_operation_not_found",
            ),
            (
                operation_service.CanvasOperationStatusConflict(
                    operation_id="secret-operation",
                    status="running",
                ),
                409,
                "canvas_operation_status_conflict",
            ),
            (
                operation_service.CanvasOperationIdempotencyConflict(
                    project_id="secret-project",
                    operation_type="cutout",
                    idempotency_key="secret-key",
                ),
                409,
                "canvas_operation_idempotency_conflict",
            ),
            (
                project_service.CanvasProjectStatusConflict("archived"),
                409,
                "canvas_project_status_conflict",
            ),
        )
        for raised, expected_status, expected_code in cases:
            with self.subTest(error=type(raised).__name__):
                fake = SimpleNamespace(
                    retry_cutout_for_asset=Mock(side_effect=raised),
                )
                client = TestClient(self.app, raise_server_exceptions=False)
                try:
                    with patch.object(
                        self.asset_routes,
                        "_operation_service",
                        return_value=fake,
                    ):
                        response = client.post(
                            path,
                            json={"clientRequestId": "map-error"},
                        )
                finally:
                    client.close()
                self.assertEqual(expected_status, response.status_code, response.text)
                self.assertEqual(expected_code, response.json()["code"])
                self.assertNotIn("secret-", response.text)


if __name__ == "__main__":
    unittest.main()
