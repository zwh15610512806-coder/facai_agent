import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services import selling_point_extractor


class SellingPointExtractorConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_read_runs_outside_the_event_loop_thread(self):
        event_loop_thread = threading.get_ident()
        parser_threads: list[int] = []

        def read_content(_file_path: str) -> str:
            parser_threads.append(threading.get_ident())
            return "这是足够长的产品卖点资料，用于验证离线回退提取。"

        with (
            patch.object(selling_point_extractor, "read_file_content", side_effect=read_content),
            patch.object(
                selling_point_extractor,
                "ai_service",
                SimpleNamespace(is_available=False),
            ),
        ):
            points = await selling_point_extractor.extract_selling_points(
                "fixture.pdf",
                "测试产品",
                "测试品类",
            )

        self.assertTrue(points)
        self.assertEqual(len(parser_threads), 1)
        self.assertNotEqual(parser_threads[0], event_loop_thread)


if __name__ == "__main__":
    unittest.main()
