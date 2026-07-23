import unittest
from unittest.mock import patch

from routers import import_data, templates


class LocalScanTaskQueueTests(unittest.TestCase):
    def tearDown(self):
        import_data._reset_local_product_scan_state()
        templates._reset_local_txt_scan_state()

    def test_product_scan_uses_durable_queue_when_worker_is_alive(self):
        with (
            patch("routers.import_data.os.path.exists", return_value=True),
            patch("services.job_runs.start_job", return_value=101),
            patch("services.task_queue.task_worker_status", return_value={"alive": True}),
            patch("services.task_queue.enqueue_task") as enqueue,
            patch("services.job_runs.latest_job", return_value=None),
        ):
            import_data.start_local_product_scan()

        enqueue.assert_called_once_with(
            "local_product_scan",
            {
                "source_dir": import_data.LOCAL_PRODUCT_SOURCE_DIR,
                "job_id": 101,
            },
            max_attempts=3,
            job_run_id=101,
        )

    def test_txt_scan_uses_durable_queue_when_worker_is_alive(self):
        with (
            patch("routers.templates.os.path.exists", return_value=True),
            patch("services.job_runs.start_job", return_value=202),
            patch("services.task_queue.task_worker_status", return_value={"alive": True}),
            patch("services.task_queue.enqueue_task") as enqueue,
            patch("services.job_runs.latest_job", return_value=None),
        ):
            templates.start_local_txt_scan(
                category="烘焙",
                video_type="机制类",
                tags="共享盘",
                product_name="奶冻粉",
            )

        enqueue.assert_called_once_with(
            "local_script_scan",
            {
                "source_dir": templates.LOCAL_TXT_SCRIPT_SOURCE_DIR,
                "category": "烘焙",
                "video_type": "机制类",
                "tags": "共享盘",
                "product_name": "奶冻粉",
                "job_id": 202,
            },
            max_attempts=3,
            job_run_id=202,
        )


if __name__ == "__main__":
    unittest.main()
