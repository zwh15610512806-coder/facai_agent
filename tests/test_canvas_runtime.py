import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi import FastAPI


class CanvasRuntimeTests(unittest.TestCase):
    def test_pre_start_test_configuration_is_typed_and_used(self):
        from services.canvas.runtime import (
            begin_canvas_runtime,
            configure_canvas_test_runtime,
            end_canvas_runtime,
        )

        app = FastAPI()
        fake_masker = object()
        factory = Mock(return_value=fake_masker)
        compose_runner = Mock()

        configure_canvas_test_runtime(
            app,
            masker_factory=factory,
            compose_runner=compose_runner,
        )
        factories = begin_canvas_runtime(app)

        self.assertIs(fake_masker, factories.masker_factory())
        self.assertIs(compose_runner, factories.compose_runner)
        factory.assert_called_once_with()
        end_canvas_runtime(app)

    def test_pre_start_test_provider_bindings_seed_before_workers_and_replace_registry(self):
        from services.canvas.runtime import (
            configure_canvas_test_runtime,
            start_canvas_runtime,
            stop_canvas_runtime,
        )

        app = FastAPI()
        db_factory = Mock(name="db_factory")
        fake_registry = object()
        registry_factory = Mock(return_value=fake_registry)
        profile_seed_factory = Mock()
        rembg_worker = Mock(name="rembg_worker")
        local_worker = Mock(name="local_worker")
        generation_worker = Mock(name="generation_worker")
        rembg_worker.stop.return_value = True
        local_worker.stop.return_value = True
        generation_worker.stop.return_value = True
        configure_canvas_test_runtime(
            app,
            masker_factory=Mock(return_value=object()),
            provider_registry_factory=registry_factory,
            model_profile_seed_factory=profile_seed_factory,
        )

        with (
            patch("services.canvas.runtime.cleanup_canvas_temporary_files"),
            patch(
                "services.canvas.operation_worker.CanvasOperationWorker",
                side_effect=[rembg_worker, local_worker],
            ),
            patch(
                "services.canvas.generation.worker.CanvasGenerationWorker",
                return_value=generation_worker,
            ) as generation_worker_type,
        ):
            start_canvas_runtime(app, db_factory=db_factory)

        profile_seed_factory.assert_called_once_with(db_factory)
        registry_factory.assert_called_once_with()
        self.assertIs(fake_registry, generation_worker_type.call_args.kwargs["registry"])
        stop_canvas_runtime(app)

    def test_configuration_is_rejected_during_and_after_first_lifespan(self):
        from services.canvas.runtime import (
            CanvasRuntimeConfigurationError,
            begin_canvas_runtime,
            configure_canvas_test_runtime,
            end_canvas_runtime,
        )

        app = FastAPI()
        configure_canvas_test_runtime(app, masker_factory=Mock)
        begin_canvas_runtime(app)
        with self.assertRaises(CanvasRuntimeConfigurationError):
            configure_canvas_test_runtime(app, masker_factory=Mock)
        with self.assertRaises(CanvasRuntimeConfigurationError):
            begin_canvas_runtime(app)
        end_canvas_runtime(app)
        with self.assertRaises(CanvasRuntimeConfigurationError):
            configure_canvas_test_runtime(app, masker_factory=Mock)

    def test_invalid_factory_is_rejected_before_state_changes(self):
        from services.canvas.runtime import (
            CanvasRuntimeConfigurationError,
            configure_canvas_test_runtime,
        )

        app = FastAPI()
        with self.assertRaises(CanvasRuntimeConfigurationError):
            configure_canvas_test_runtime(app, masker_factory=None)

    def test_production_factory_always_constructs_real_masker_not_environment_fake(self):
        from services.canvas.runtime import begin_canvas_runtime, end_canvas_runtime

        app = FastAPI()
        real_masker = object()
        with (
            patch.dict(
                os.environ,
                {"CANVAS_MASKER_FACTORY": "tests.fakes.canvas_processors:FakeMasker"},
            ),
            patch(
                "services.canvas.rembg_cpu.RembgMasker",
                return_value=real_masker,
            ) as constructor,
        ):
            factories = begin_canvas_runtime(app)
            self.assertIs(real_masker, factories.masker_factory())
            constructor.assert_called_once_with()
            end_canvas_runtime(app)

    def test_start_and_reverse_stop_own_canvas_workers_with_exact_claim_tokens(self):
        from services.canvas.runtime import (
            configure_canvas_test_runtime,
            start_canvas_runtime,
            stop_canvas_runtime,
        )

        app = FastAPI()
        masker = object()
        db_factory = Mock(name="db_factory")
        rembg_worker = Mock(name="rembg_worker")
        local_worker = Mock(name="local_worker")
        generation_worker = Mock(name="generation_worker")
        stop_order = []
        rembg_worker.stop.side_effect = lambda: stop_order.append("rembg") or True
        local_worker.stop.side_effect = lambda: stop_order.append("local") or True
        generation_worker.stop.side_effect = lambda: stop_order.append("generation") or True
        compose_runner = Mock(name="compose_runner")
        configure_canvas_test_runtime(
            app,
            masker_factory=Mock(return_value=masker),
            compose_runner=compose_runner,
        )

        with (
            patch("services.canvas.runtime.cleanup_canvas_temporary_files") as cleanup,
            patch(
                "services.canvas.operation_worker.CanvasOperationWorker",
                side_effect=[rembg_worker, local_worker],
            ) as worker_type,
            patch(
                "services.canvas.generation.worker.CanvasGenerationWorker",
                return_value=generation_worker,
            ) as generation_worker_type,
            patch("services.canvas.rembg_cpu.run_cutout_operation") as run_cutout,
            patch("services.canvas.exports.run_export_operation") as run_export,
        ):
            handle = start_canvas_runtime(app, db_factory=db_factory)
            cleanup.assert_called_once_with(db_factory)
            rembg_worker.start.assert_called_once_with()
            local_worker.start.assert_called_once_with()
            generation_worker.start.assert_called_once_with()
            rembg_kwargs = worker_type.call_args_list[0].kwargs
            local_kwargs = worker_type.call_args_list[1].kwargs
            self.assertIs(db_factory, rembg_kwargs["db_factory"])
            self.assertEqual("rembg", rembg_kwargs["lane"])
            self.assertEqual({"cutout"}, set(rembg_kwargs["handlers"]))
            self.assertIs(db_factory, local_kwargs["db_factory"])
            self.assertEqual("local", local_kwargs["lane"])
            self.assertEqual({"compose", "export"}, set(local_kwargs["handlers"]))
            claimed = Mock(
                id="operation-1",
                worker_id="worker-1",
                attempt_count=3,
            )
            rembg_kwargs["handlers"]["cutout"](claimed)
            run_cutout.assert_called_once_with(
                "operation-1",
                masker=masker,
                db_factory=db_factory,
                worker_id="worker-1",
                attempt_count=3,
            )
            local_kwargs["handlers"]["compose"](claimed)
            compose_runner.assert_called_once_with(
                "operation-1",
                db_factory=db_factory,
                worker_id="worker-1",
                attempt_count=3,
            )
            local_kwargs["handlers"]["export"](claimed)
            run_export.assert_called_once_with(
                "operation-1",
                db_factory=db_factory,
                worker_id="worker-1",
                attempt_count=3,
            )
            self.assertIs(rembg_worker, handle.rembg_worker)
            self.assertIs(local_worker, handle.local_worker)
            self.assertIs(generation_worker, handle.generation_worker)
            generation_kwargs = generation_worker_type.call_args.kwargs
            self.assertIs(db_factory, generation_kwargs["db_factory"])
            stop_canvas_runtime(app)
            self.assertEqual(["generation", "local", "rembg"], stop_order)

    def test_failed_worker_stop_keeps_runtime_handle_for_a_later_retry(self):
        from services.canvas.runtime import (
            CanvasRuntimeShutdownError,
            configure_canvas_test_runtime,
            start_canvas_runtime,
            stop_canvas_runtime,
        )

        app = FastAPI()
        rembg_worker = Mock(name="rembg_worker")
        local_worker = Mock(name="local_worker")
        generation_worker = Mock(name="generation_worker")
        local_worker.stop.side_effect = [False, True]
        rembg_worker.stop.return_value = True
        generation_worker.stop.return_value = True
        configure_canvas_test_runtime(app, masker_factory=Mock(return_value=object()))

        with (
            patch("services.canvas.runtime.cleanup_canvas_temporary_files"),
            patch(
                "services.canvas.operation_worker.CanvasOperationWorker",
                side_effect=[rembg_worker, local_worker],
            ),
            patch(
                "services.canvas.generation.worker.CanvasGenerationWorker",
                return_value=generation_worker,
            ),
        ):
            handle = start_canvas_runtime(app, db_factory=Mock())
            with self.assertRaises(CanvasRuntimeShutdownError):
                stop_canvas_runtime(app)
            self.assertIs(handle, getattr(app.state, "_product_canvas_runtime_handle"))
            stop_canvas_runtime(app)

        self.assertFalse(hasattr(app.state, "_product_canvas_runtime_handle"))
        self.assertEqual(2, local_worker.stop.call_count)
        self.assertEqual(2, generation_worker.stop.call_count)
        rembg_worker.stop.assert_called_once_with()

    def test_local_start_failure_preserves_handle_when_rembg_cannot_stop(self):
        from services.canvas.runtime import (
            CanvasRuntimeShutdownError,
            configure_canvas_test_runtime,
            start_canvas_runtime,
            stop_canvas_runtime,
        )

        app = FastAPI()
        rembg_worker = Mock(name="rembg_worker")
        local_worker = Mock(name="local_worker")
        generation_worker = Mock(name="generation_worker")
        local_worker.start.side_effect = RuntimeError("local start failed")
        local_worker.stop.return_value = True
        rembg_worker.stop.side_effect = [False, True]
        generation_worker.stop.return_value = True
        configure_canvas_test_runtime(app, masker_factory=Mock(return_value=object()))

        with (
            patch("services.canvas.runtime.cleanup_canvas_temporary_files"),
            patch(
                "services.canvas.operation_worker.CanvasOperationWorker",
                side_effect=[rembg_worker, local_worker],
            ),
            patch(
                "services.canvas.generation.worker.CanvasGenerationWorker",
                return_value=generation_worker,
            ),
        ):
            with self.assertRaises(CanvasRuntimeShutdownError):
                start_canvas_runtime(app, db_factory=Mock())
            self.assertTrue(hasattr(app.state, "_product_canvas_runtime_handle"))
            stop_canvas_runtime(app)

        self.assertFalse(hasattr(app.state, "_product_canvas_runtime_handle"))
        self.assertEqual(2, rembg_worker.stop.call_count)

    def test_cleanup_passes_every_asset_reference_including_deleted_rows(self):
        from services.canvas.runtime import cleanup_canvas_temporary_files

        db = MagicMock()
        db.execute.return_value.all.return_value = [
            ("11111111-1111-1111-1111-111111111111", "tmp/old.uploading"),
            ("22222222-2222-2222-2222-222222222222", "working/live.png"),
        ]
        db_factory = MagicMock()
        db_factory.return_value.__enter__.return_value = db
        with patch(
            "services.canvas.storage.cleanup_stale_temporary_files",
            return_value=1,
        ) as cleanup:
            self.assertEqual(1, cleanup_canvas_temporary_files(db_factory))
        cleanup.assert_called_once_with(
            referenced_relative_paths={
                "11111111-1111-1111-1111-111111111111/tmp/old.uploading",
                "22222222-2222-2222-2222-222222222222/working/live.png",
            }
        )


if __name__ == "__main__":
    unittest.main()
