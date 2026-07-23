import json
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from tests.frontend_source import read_page_source


def _parse_sse_events(response):
    events = []
    event_name = "message"
    data_lines = []
    for line in response.iter_lines():
        if not line:
            if data_lines:
                events.append((event_name, json.loads("\n".join(data_lines))))
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: "):
            data_lines.append(line[6:])
    if data_lines:
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


class InspirationStreamingApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_stream_emits_meta_context_reasoning_delta_delta_and_done(self):
        async def fake_stream(*_args, **_kwargs):
            yield {"type": "reasoning_delta", "text": "先分析"}
            yield {"type": "delta", "text": "最终答案"}
            yield {"type": "done", "model": "stream-model"}

        with (
            patch("routers.inspiration.ai_service.is_interface_available", return_value=True),
            patch("routers.inspiration.ai_service.get_model_name", return_value="stream-model"),
            patch("routers.inspiration.ai_service.stream_chat", side_effect=fake_stream),
        ):
            with self.client.stream(
                "POST",
                "/api/inspiration/chat/stream",
                json={"message": "给我一个创意", "tool_mode": "thinking"},
            ) as response:
                events = _parse_sse_events(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [name for name, _data in events],
            ["meta", "context", "reasoning_delta", "delta", "done"],
        )
        self.assertEqual(events[-1][1]["model"], "stream-model")
        self.assertIn("sources", events[-1][1])
        self.assertIn("products", events[-1][1])
        self.assertIn("attachments", events[-1][1])
        self.assertIn("agent_trace", events[-1][1])

    def test_stream_provider_error_is_an_sse_error_event(self):
        async def failing_stream(*_args, **_kwargs):
            raise RuntimeError("upstream exploded")
            yield

        with (
            patch("routers.inspiration.ai_service.is_interface_available", return_value=True),
            patch("routers.inspiration.ai_service.get_model_name", return_value="stream-model"),
            patch("routers.inspiration.ai_service.stream_chat", side_effect=failing_stream),
        ):
            with self.client.stream(
                "POST",
                "/api/inspiration/chat/stream",
                json={"message": "测试错误"},
            ) as response:
                events = _parse_sse_events(response)

        self.assertEqual([name for name, _data in events], ["meta", "context", "error"])
        self.assertIn("upstream exploded", events[-1][1]["message"])

    def test_frontend_submits_durable_job_and_restores_partial_answer(self):
        page = read_page_source("inspiration.html")

        self.assertIn("/api/inspiration/chat/jobs", page)
        self.assertIn("waitForInspirationJob", page)
        self.assertIn('id="inspirationCancelBtn"', page)
        self.assertIn("cancelled", page)
        self.assertIn("job.partial_result", page)

    def test_mobile_history_is_closed_drawer_and_fabs_move_into_navigation(self):
        page = read_page_source("inspiration.html")
        common = Path("static/js/common.js").read_text(encoding="utf-8-sig")
        css = Path("static/css/style.css").read_text(encoding="utf-8-sig")

        self.assertIn('id="historyDrawerToggle"', page)
        self.assertIn('id="historyDrawerBackdrop"', page)
        self.assertIn(".inspiration-side.is-open", page)
        self.assertIn("transform:translateX(-105%)", page)
        self.assertIn("position:sticky", page)
        self.assertIn("/app/import", common)
        self.assertIn("/app/ai-config", common)
        self.assertIn(".nav-mobile-utility", css)
        self.assertIn("后台任务", common)
        self.assertIn(".facai-tools-launcher { display: none", css)
        self.assertIn(".facai-tools-controls,.facai-tools-menu { display: none", css)

    def test_closing_consumer_closes_provider_stream_and_records_cancelled(self):
        from services.ai_service import AIService

        class FakeUpstream:
            def __init__(self):
                self.closed = False
                self.sent = False

            def __iter__(self):
                return self

            def __next__(self):
                if self.sent:
                    raise StopIteration
                self.sent = True
                delta = SimpleNamespace(content="部分内容", reasoning_content="")
                return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

            def close(self):
                self.closed = True

        upstream = FakeUpstream()
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: upstream)
            )
        )
        service = AIService()
        records = []

        async def scenario():
            with (
                patch.object(service, "_resolve_chat_config", return_value=("doubao", "stream-model", 100, None, None)),
                patch.object(service, "_get_provider_client", return_value=client),
                patch.object(service, "_record_usage_safe", side_effect=lambda **kwargs: records.append(kwargs)),
            ):
                stream = service.stream_chat([{"role": "user", "content": "测试"}])
                first = await anext(stream)
                self.assertEqual(first["text"], "部分内容")
                await stream.aclose()

        asyncio.run(scenario())

        self.assertTrue(upstream.closed)
        self.assertEqual(records[-1]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
