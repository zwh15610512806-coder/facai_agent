import asyncio
import json
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import Request
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from database import Base
from main import app
from routers.canvas import events as canvas_event_routes


class CanvasSSEDisconnectRegressionTests(unittest.TestCase):
    def test_uvicorn_client_disconnect_stops_canvas_sse_polling(self):
        """A disconnect must stop the production Canvas event generator polling."""
        import uvicorn
        import canvas_models  # noqa: F401 - register metadata.
        from services.canvas import projects

        route_path = "/api/canvas/_sse-disconnect-regression"
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = create_engine(
                f"sqlite:///{Path(temp_dir) / 'canvas-sse.db'}",
                connect_args={"check_same_thread": False},
            )
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            Base.metadata.create_all(bind=engine)
            with Session() as db:
                project = projects.create_project(db, name="Disconnect regression")
                project_id = project.id
            factory = TrackingSessionFactory(Session)
            stream_finalized = threading.Event()

            async def tracked_event_stream(request: Request):
                try:
                    async for event in canvas_event_routes.project_event_stream(
                        request,
                        project_id=project_id,
                        session_factory=factory,
                        last_event_id=None,
                    ):
                        yield event
                finally:
                    stream_finalized.set()

            def event_route(request: Request):
                return StreamingResponse(
                    tracked_event_stream(request),
                    media_type="text/event-stream",
                )

            async def asgi_24(scope, receive, send):
                scope = dict(scope)
                scope["asgi"] = {**scope.get("asgi", {}), "spec_version": "2.4"}
                await app(scope, receive, send)

            app.add_api_route(route_path, event_route, methods=["GET"])
            route = next(
                route
                for route in app.router.routes
                if getattr(route, "path", None) == route_path
            )
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            server = uvicorn.Server(
                uvicorn.Config(
                    asgi_24,
                    host="127.0.0.1",
                    port=port,
                    lifespan="off",
                    access_log=False,
                    log_level="error",
                    ws="none",
                )
            )
            server_thread = threading.Thread(target=server.run, daemon=True)
            connection = None
            try:
                server_thread.start()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.01)
                else:
                    self.fail("Uvicorn did not start in time")

                connection = socket.create_connection(("127.0.0.1", port), timeout=1)
                connection.sendall(
                    (
                        f"GET {route_path} HTTP/1.1\r\n"
                        "Host: testserver\r\n"
                        "Accept: text/event-stream\r\n"
                        "Connection: keep-alive\r\n\r\n"
                    ).encode("ascii")
                )
                response = b""
                deadline = time.monotonic() + 1
                while b"event: snapshot\n" not in response and time.monotonic() < deadline:
                    response += connection.recv(4096)
                self.assertIn(b"HTTP/1.1 200", response)
                self.assertIn(b"event: snapshot\n", response)

                deadline = time.monotonic() + 1
                while factory.created_count < 2 and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertGreaterEqual(factory.created_count, 2)
                polls_before_disconnect = factory.created_count

                connection.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_LINGER,
                    struct.pack("ii", 1, 0),
                )
                connection.close()
                connection = None

                time.sleep(canvas_event_routes.POLL_INTERVAL_SECONDS * 2 + 0.1)
                self.assertEqual(
                    polls_before_disconnect,
                    factory.created_count,
                    "Canvas SSE generator kept polling after its client disconnected",
                )
                self.assertEqual(0, factory.open_count)
                self.assertTrue(
                    stream_finalized.wait(timeout=1),
                    "Canvas SSE generator did not exit after its client disconnected",
                )
            finally:
                if connection is not None:
                    connection.close()
                server.should_exit = True
                server_thread.join(timeout=2)
                server_thread_alive = server_thread.is_alive()
                app.router.routes.remove(route)
                app.openapi_schema = None
                engine.dispose()
                self.assertFalse(
                    server_thread_alive,
                    "Uvicorn regression-test thread did not exit",
                )


class FakeRequest:
    def __init__(self, disconnect_values=False):
        if isinstance(disconnect_values, bool):
            self.disconnect_values = None
            self.default = disconnect_values
        else:
            self.disconnect_values = iter(disconnect_values)
            self.default = False

    async def is_disconnected(self):
        if self.disconnect_values is None:
            return self.default
        return next(self.disconnect_values, self.default)


class TrackingSessionFactory:
    class _Context:
        def __init__(self, owner):
            self.owner = owner
            self.session = None

        def __enter__(self):
            self.session = self.owner.base_factory()
            self.owner.open_count += 1
            self.owner.created_count += 1
            return self.session

        def __exit__(self, exc_type, exc, traceback):
            try:
                self.session.close()
            finally:
                self.owner.open_count -= 1

    def __init__(self, base_factory):
        self.base_factory = base_factory
        self.created_count = 0
        self.open_count = 0

    def __call__(self):
        return self._Context(self)


def parse_sse_chunk(chunk):
    parsed = {"id": None, "event": None, "data": None, "comment": None}
    data_lines = []
    for line in chunk.splitlines():
        if line.startswith("id: "):
            parsed["id"] = int(line[4:])
        elif line.startswith("event: "):
            parsed["event"] = line[7:]
        elif line.startswith("data: "):
            data_lines.append(line[6:])
        elif line.startswith(":"):
            parsed["comment"] = line[1:].strip()
    if data_lines:
        parsed["data"] = json.loads("\n".join(data_lines))
    return parsed


class CanvasEventEndpointContractTests(unittest.TestCase):
    def test_project_event_endpoint_is_registered_as_get(self):
        paths = app.openapi()["paths"]

        self.assertIn("/api/canvas/projects/{project_id}/events", paths)
        self.assertIn("get", paths["/api/canvas/projects/{project_id}/events"])


class CanvasEventReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "canvas-event-api.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        import canvas_models  # noqa: F401 - register metadata.
        from canvas_models import CanvasAsset, CanvasAssetOperation, CanvasEvent
        from services.canvas import projects

        Base.metadata.create_all(bind=self.engine)
        with self.Session() as db:
            project = projects.create_project(db, name="Event API")
            projects.update_project_metadata(
                db,
                project_id=project.id,
                expected_revision=1,
                name="Event API 2",
            )
            projects.update_project_metadata(
                db,
                project_id=project.id,
                expected_revision=2,
                name="Event API 3",
            )
            self.project_id = project.id
            self.event_rows = [
                (event.id, event.event_type, json.loads(event.payload_json))
                for event in db.execute(
                    select(CanvasEvent)
                    .where(CanvasEvent.project_id == self.project_id)
                    .order_by(CanvasEvent.id)
                ).scalars().all()
            ]
            asset_id = str(uuid4())
            db.add(
                CanvasAsset(
                    id=asset_id,
                    project_id=self.project_id,
                    asset_type="working",
                    relative_path=f"working/{asset_id}.png",
                    original_filename="working.png",
                    mime_type="image/png",
                    byte_count=1,
                    width=1,
                    height=1,
                    sha256="0" * 64,
                )
            )
            db.flush()
            valid_id = str(uuid4())
            invalid_id = str(uuid4())
            db.add_all(
                [
                    CanvasAssetOperation(
                        id=valid_id,
                        project_id=self.project_id,
                        operation_type="cutout",
                        status="failed",
                        attempt_count=2,
                        worker_id="secret-worker",
                        input_asset_id=asset_id,
                        request_snapshot_json='{"secret":"never expose"}',
                        processor_version="rembg-v1",
                        idempotency_key="secret-idempotency",
                        safe_error_json=json.dumps(
                            {
                                "code": "canvas_cutout_failed",
                                "message": "Cutout failed",
                                "retryable": True,
                                "path": "C:\\private\\product.png",
                                "traceback": "secret traceback",
                            }
                        ),
                    ),
                    CanvasAssetOperation(
                        id=invalid_id,
                        project_id=self.project_id,
                        operation_type="compose",
                        status="interrupted",
                        attempt_count=1,
                        input_asset_id=asset_id,
                        request_snapshot_json='{"secret":"also hidden"}',
                        idempotency_key="secret-invalid-idempotency",
                        safe_error_json="{broken",
                    ),
                ]
            )
            db.commit()
            self.operation_ids = {valid_id, invalid_id}

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _stream_builder(self):
        builder = getattr(canvas_event_routes, "project_event_stream", None)
        self.assertIsNotNone(builder, "SSE stream builder must be implemented")
        return builder

    def test_last_event_id_parser_accepts_non_negative_integers_only(self):
        parser = getattr(canvas_event_routes, "parse_last_event_id", None)
        self.assertIsNotNone(parser, "Last-Event-ID parser must be implemented")

        self.assertIsNone(parser(None))
        self.assertEqual(0, parser("0"))
        self.assertEqual(42, parser("42"))
        for invalid in ("", " 1", "1 ", "-1", "+1", "1.0", "abc", str(2**63)):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                parser(invalid)

    def test_replays_persisted_events_after_last_id_in_ascending_order(self):
        builder = self._stream_builder()
        factory = TrackingSessionFactory(self.Session)

        async def scenario():
            stream = builder(
                FakeRequest(False),
                project_id=self.project_id,
                session_factory=factory,
                last_event_id=self.event_rows[0][0],
            )
            try:
                chunks = []
                open_counts = []
                for _ in range(2):
                    chunks.append(await anext(stream))
                    open_counts.append(factory.open_count)
                return chunks, open_counts
            finally:
                await stream.aclose()

        chunks, open_counts = asyncio.run(scenario())
        parsed = [parse_sse_chunk(chunk) for chunk in chunks]

        self.assertEqual([row[0] for row in self.event_rows[1:]], [row["id"] for row in parsed])
        self.assertEqual([row[1] for row in self.event_rows[1:]], [row["event"] for row in parsed])
        self.assertEqual([row[2] for row in self.event_rows[1:]], [row["data"] for row in parsed])
        self.assertEqual(sorted(row["id"] for row in parsed), [row["id"] for row in parsed])
        self.assertEqual([0, 0], open_counts)
        self.assertEqual(0, factory.open_count)

    def test_retention_gap_emits_snapshot_then_continues_with_new_events(self):
        from canvas_models import CanvasEvent
        from services.canvas import projects

        deleted_event_id = self.event_rows[0][0]
        with self.Session() as db:
            db.execute(delete(CanvasEvent).where(CanvasEvent.id == deleted_event_id))
            db.commit()

        builder = self._stream_builder()
        factory = TrackingSessionFactory(self.Session)

        async def scenario():
            stream = builder(
                FakeRequest(False),
                project_id=self.project_id,
                session_factory=factory,
                last_event_id=deleted_event_id,
            )
            try:
                snapshot_chunk = await anext(stream)
                snapshot_open_count = factory.open_count
                with self.Session() as db:
                    updated = projects.update_project_metadata(
                        db,
                        project_id=self.project_id,
                        expected_revision=3,
                        name="Event API 4",
                    )
                event_chunk = await anext(stream)
                return snapshot_chunk, event_chunk, snapshot_open_count, updated.revision
            finally:
                await stream.aclose()

        snapshot_chunk, event_chunk, snapshot_open_count, revision = asyncio.run(scenario())
        snapshot_event = parse_sse_chunk(snapshot_chunk)
        next_event = parse_sse_chunk(event_chunk)

        self.assertEqual("snapshot", snapshot_event["event"])
        self.assertEqual(
            {"project", "skus", "revision", "operations", "generations", "highWaterEventId"},
            set(snapshot_event["data"]),
        )
        self.assertEqual(3, snapshot_event["data"]["revision"])
        operations = snapshot_event["data"]["operations"]
        self.assertEqual(self.operation_ids, {operation["id"] for operation in operations})
        self.assertTrue(
            all(
                set(operation)
                == {
                    "id",
                    "projectId",
                    "type",
                    "status",
                    "attemptCount",
                    "inputAssetId",
                    "outputAssetId",
                    "error",
                    "createdAt",
                    "updatedAt",
                    "startedAt",
                    "completedAt",
                }
                for operation in operations
            )
        )
        valid = next(operation for operation in operations if operation["status"] == "failed")
        invalid = next(
            operation for operation in operations if operation["status"] == "interrupted"
        )
        self.assertEqual(
            {
                "code": "canvas_cutout_failed",
                "message": "Cutout failed",
                "retryable": True,
            },
            valid["error"],
        )
        self.assertEqual(
            {
                "code": "canvas_operation_error_unavailable",
                "message": "Operation error details are unavailable",
                "retryable": False,
            },
            invalid["error"],
        )
        serialized_operations = json.dumps(operations)
        for secret in ("secret", "private", "traceback", "idempotency", "worker"):
            self.assertNotIn(secret, serialized_operations.lower())
        self.assertEqual(self.event_rows[-1][0], snapshot_event["id"])
        self.assertEqual("project.updated", next_event["event"])
        self.assertGreater(next_event["id"], snapshot_event["id"])
        self.assertEqual(revision, next_event["data"]["revision"])
        self.assertEqual(0, snapshot_open_count)
        self.assertEqual(0, factory.open_count)

    def test_idle_stream_emits_heartbeat_comment_without_holding_session(self):
        builder = self._stream_builder()
        factory = TrackingSessionFactory(self.Session)

        async def scenario():
            stream = builder(
                FakeRequest(False),
                project_id=self.project_id,
                session_factory=factory,
                last_event_id=self.event_rows[-1][0],
            )
            try:
                return await anext(stream), factory.open_count
            finally:
                await stream.aclose()

        with (
            patch.object(canvas_event_routes, "HEARTBEAT_INTERVAL_SECONDS", 0),
            patch.object(canvas_event_routes, "POLL_INTERVAL_SECONDS", 0),
        ):
            chunk, open_count = asyncio.run(scenario())

        self.assertEqual(": heartbeat\n\n", chunk)
        self.assertEqual(0, open_count)
        self.assertEqual(0, factory.open_count)

    def test_disconnect_closes_promptly_without_opening_or_leaking_session(self):
        builder = self._stream_builder()
        factory = TrackingSessionFactory(self.Session)

        async def scenario():
            stream = builder(
                FakeRequest(True),
                project_id=self.project_id,
                session_factory=factory,
                last_event_id=self.event_rows[-1][0],
            )
            with self.assertRaises(StopAsyncIteration):
                await asyncio.wait_for(anext(stream), timeout=0.25)
            await stream.aclose()

        asyncio.run(scenario())

        self.assertEqual(0, factory.created_count)
        self.assertEqual(0, factory.open_count)

    def test_route_rejects_invalid_last_event_id_and_missing_project_before_streaming(self):
        dependency = getattr(canvas_event_routes, "get_canvas_session_factory", None)
        self.assertIsNotNone(dependency, "SSE session factory dependency must be implemented")
        factory = TrackingSessionFactory(self.Session)
        app.dependency_overrides[dependency] = lambda: factory
        client = TestClient(app)
        try:
            invalid = client.get(
                f"/api/canvas/projects/{self.project_id}/events",
                headers={"Last-Event-ID": "-1"},
            )
            missing = client.get(f"/api/canvas/projects/{uuid4()}/events")
        finally:
            client.close()
            app.dependency_overrides.pop(dependency, None)

        self.assertEqual(
            {"detail": "Invalid Last-Event-ID", "code": "invalid_last_event_id"},
            invalid.json(),
        )
        self.assertEqual(400, invalid.status_code, invalid.text)
        self.assertEqual(
            {"detail": "Canvas resource not found", "code": "canvas_resource_not_found"},
            missing.json(),
        )
        self.assertEqual(404, missing.status_code, missing.text)
        self.assertEqual(0, factory.open_count)


if __name__ == "__main__":
    unittest.main()
