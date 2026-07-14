import asyncio
import threading
import unittest

from services.bounded_executor import BoundedExecutor, WorkQueueFull


class BoundedExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_saturated_executor_rejects_without_blocking_event_loop(self):
        executor = BoundedExecutor(max_workers=1, max_pending=1, thread_name_prefix="test-parse")
        started = threading.Event()
        release = threading.Event()

        def blocking_work():
            started.set()
            release.wait(timeout=2)
            return "done"

        first = asyncio.create_task(executor.run(blocking_work))
        self.assertTrue(await asyncio.to_thread(started.wait, 1))
        try:
            with self.assertRaises(WorkQueueFull):
                await executor.run(lambda: "never queued")
        finally:
            release.set()
        self.assertEqual(await first, "done")
        executor.shutdown()


if __name__ == "__main__":
    unittest.main()
