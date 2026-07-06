import asyncio
import os
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db


ROOT = Path(__file__).resolve().parents[1]


PROVIDER_ENV_KEYS = [
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "ARK_MODEL",
    "DEEPSEEK_API_KEY",
    "DOUBAO_API_KEY",
    "DOUBAO_BASE_URL",
    "DOUBAO_MODEL",
    "MINIMAX_API_KEY",
    "GLM_API_KEY",
    "ZAI_API_KEY",
    "QWEN_API_KEY",
    "DASHSCOPE_API_KEY",
]

INSPIRATION_TOOLS_INTERFACE_KEY = "inspiration_tools"
SCRIPT_GENERATE_INTERFACE_KEY = "script_generate"
SCRIPT_CREATION_INTERFACE_KEY = "script_creation"
CONTENT_ANALYSIS_INTERFACE_KEY = "content_analysis"
VISIBLE_AI_INTERFACE_KEYS = [
    "inspiration_chat",
    INSPIRATION_TOOLS_INTERFACE_KEY,
    SCRIPT_GENERATE_INTERFACE_KEY,
    SCRIPT_CREATION_INTERFACE_KEY,
    CONTENT_ANALYSIS_INTERFACE_KEY,
]
INSPIRATION_TOOL_KEYS = [
    "inspiration_thinking",
    "inspiration_research",
    "inspiration_analysis",
    "inspiration_attachment",
]
SCRIPT_CREATION_KEYS = [
    "script_library_rewrite",
    "script_rewrite",
    "seedance_prompt",
]
CONTENT_ANALYSIS_KEYS = [
    "product_rag_global",
    "product_rag_scoped",
    "selling_point_extract",
    "viral_script_analyze",
    "reference_script_analyze",
]
MERGED_AI_INTERFACE_KEYS = INSPIRATION_TOOL_KEYS + SCRIPT_CREATION_KEYS + CONTENT_ANALYSIS_KEYS
ARK_DEFAULT_MODEL = "ep-20260703160153-h5cx5"
ARK_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


class AiConfigApiTests(unittest.TestCase):
    def setUp(self):
        from routers import ai_config

        self.ai_config = ai_config
        self.original_env = {key: os.environ.get(key) for key in PROVIDER_ENV_KEYS}
        for key in PROVIDER_ENV_KEYS:
            os.environ.pop(key, None)

        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_db
        app.include_router(ai_config.router, prefix="/api/ai-config")
        self.client = TestClient(app)

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_providers_include_required_vendors_without_leaking_keys(self):
        os.environ["QWEN_API_KEY"] = "qwen-secret-value"

        response = self.client.get("/api/ai-config/providers")

        self.assertEqual(response.status_code, 200)
        providers = {provider["key"]: provider for provider in response.json()["providers"]}
        for key in ["deepseek", "doubao", "minimax", "glm", "qwen"]:
            self.assertIn(key, providers)

        self.assertEqual(providers["doubao"]["label"], "豆包 / 火山方舟")
        self.assertTrue(providers["qwen"]["configured"])
        self.assertFalse(providers["minimax"]["configured"])
        self.assertNotIn("qwen-secret-value", response.text)
        self.assertIn("qwen-plus", providers["qwen"]["preset_models"])
        self.assertIn("MiniMax-M3", providers["minimax"]["preset_models"])
        self.assertIn(ARK_DEFAULT_MODEL, providers["doubao"]["preset_models"])
        self.assertIn("doubao-seed-2-0-lite-260215", providers["doubao"]["preset_models"])
        self.assertIn("doubao-seed-1-8-251228", providers["doubao"]["preset_models"])

    def test_doubao_provider_prefers_ark_key_and_endpoint_defaults(self):
        os.environ["ARK_API_KEY"] = "ark-secret-value"
        os.environ["DOUBAO_API_KEY"] = "legacy-doubao-secret"

        response = self.client.get("/api/ai-config/providers")

        self.assertEqual(response.status_code, 200)
        providers = {provider["key"]: provider for provider in response.json()["providers"]}
        doubao = providers["doubao"]
        self.assertTrue(doubao["configured"])
        self.assertEqual(doubao["configured_env"], "ARK_API_KEY")
        self.assertEqual(doubao["base_url"], ARK_DEFAULT_BASE_URL)
        self.assertEqual(doubao["default_model"], ARK_DEFAULT_MODEL)
        self.assertIn("ARK_API_KEY", doubao["api_key_env_names"])
        self.assertNotIn("ark-secret-value", response.text)
        self.assertNotIn("legacy-doubao-secret", response.text)
        self.assertIn("glm-5.2", providers["glm"]["preset_models"])

    def test_interface_settings_can_be_updated_and_validated(self):
        update = {
            "provider": "qwen",
            "model": "qwen-plus",
            "max_tokens": 4096,
        }

        response = self.client.put("/api/ai-config/interfaces/inspiration_chat", json=update)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["interface_key"], "inspiration_chat")
        self.assertEqual(data["provider"], "qwen")
        self.assertEqual(data["model"], "qwen-plus")
        self.assertEqual(data["max_tokens"], 4096)

        interfaces = self.client.get("/api/ai-config/interfaces").json()["interfaces"]
        by_key = {item["interface_key"]: item for item in interfaces}
        self.assertEqual(by_key["inspiration_chat"]["provider"], "qwen")
        self.assertIn(SCRIPT_CREATION_INTERFACE_KEY, by_key)
        self.assertNotIn("script_rewrite", by_key)
        self.assertNotIn("inspiration_analysis", by_key)

        bad_provider = self.client.put(
            "/api/ai-config/interfaces/inspiration_chat",
            json={"provider": "unknown", "model": "x", "max_tokens": 1000},
        )
        self.assertEqual(bad_provider.status_code, 400)

        bad_tokens = self.client.put(
            "/api/ai-config/interfaces/inspiration_chat",
            json={"provider": "qwen", "model": "qwen-plus", "max_tokens": 0},
        )
        self.assertEqual(bad_tokens.status_code, 422)

    def test_screenshot_groups_are_merged_into_three_interfaces_plus_chat(self):
        response = self.client.get("/api/ai-config/interfaces")

        self.assertEqual(response.status_code, 200)
        interfaces = response.json()["interfaces"]
        keys = [item["interface_key"] for item in interfaces]
        self.assertEqual(keys, VISIBLE_AI_INTERFACE_KEYS)
        for legacy_key in MERGED_AI_INTERFACE_KEYS:
            self.assertNotIn(legacy_key, keys)

    def test_default_work_interfaces_use_volcengine_ark(self):
        response = self.client.get("/api/ai-config/interfaces")

        self.assertEqual(response.status_code, 200)
        by_key = {item["interface_key"]: item for item in response.json()["interfaces"]}
        for key in ["inspiration_chat", INSPIRATION_TOOLS_INTERFACE_KEY, SCRIPT_GENERATE_INTERFACE_KEY, SCRIPT_CREATION_INTERFACE_KEY]:
            self.assertEqual(by_key[key]["provider"], "doubao")
            self.assertEqual(by_key[key]["model"], ARK_DEFAULT_MODEL)
            self.assertEqual(by_key[key]["base_url"], ARK_DEFAULT_BASE_URL)
        self.assertEqual(by_key["inspiration_chat"]["max_tokens"], 2400)
        self.assertEqual(by_key[INSPIRATION_TOOLS_INTERFACE_KEY]["max_tokens"], 3600)
        self.assertEqual(by_key[SCRIPT_GENERATE_INTERFACE_KEY]["max_tokens"], 3600)
        self.assertEqual(by_key[SCRIPT_CREATION_INTERFACE_KEY]["max_tokens"], 3600)
        self.assertEqual(by_key[CONTENT_ANALYSIS_INTERFACE_KEY]["provider"], "deepseek")
        self.assertNotIn("seedance_prompt", by_key)

    def test_doubao_endpoint_update_keeps_base_url_as_provider_url(self):
        response = self.client.put(
            "/api/ai-config/interfaces/inspiration_chat",
            json={
                "provider": "doubao",
                "model": "ep-custom-from-ui",
                "max_tokens": 2400,
                "base_url": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["provider"], "doubao")
        self.assertEqual(data["model"], "ep-custom-from-ui")
        self.assertEqual(data["display_model"], "ep-custom-from-ui")
        self.assertEqual(data["custom_base_url"], "")
        self.assertEqual(data["base_url"], ARK_DEFAULT_BASE_URL)

    def test_script_generation_interface_description_is_provider_neutral(self):
        response = self.client.get("/api/ai-config/interfaces")

        self.assertEqual(response.status_code, 200)
        by_key = {item["interface_key"]: item for item in response.json()["interfaces"]}
        description = by_key[SCRIPT_GENERATE_INTERFACE_KEY]["description"]
        self.assertIn("AI生成引擎", description)
        self.assertNotIn("DeepSeek AI 引擎", description)

    def test_legacy_default_deepseek_work_setting_upgrades_to_volcengine_ark(self):
        from models import AIInterfaceSetting

        self.db.add_all([
            AIInterfaceSetting(
                interface_key="inspiration_chat",
                provider="deepseek",
                model="deepseek-v4-flash",
                max_tokens=2400,
            ),
            AIInterfaceSetting(
                interface_key=INSPIRATION_TOOLS_INTERFACE_KEY,
                provider="deepseek",
                model="deepseek-v4-flash",
                max_tokens=2400,
            ),
            AIInterfaceSetting(
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                provider="deepseek",
                model="deepseek-chat",
                max_tokens=2400,
            ),
            AIInterfaceSetting(
                interface_key=SCRIPT_CREATION_INTERFACE_KEY,
                provider="deepseek",
                model="deepseek-v4-pro",
                max_tokens=3600,
            ),
        ])
        self.db.commit()

        response = self.client.get("/api/ai-config/interfaces")

        self.assertEqual(response.status_code, 200)
        by_key = {item["interface_key"]: item for item in response.json()["interfaces"]}
        for key in ["inspiration_chat", INSPIRATION_TOOLS_INTERFACE_KEY, SCRIPT_GENERATE_INTERFACE_KEY, SCRIPT_CREATION_INTERFACE_KEY]:
            self.assertEqual(by_key[key]["provider"], "doubao")
            self.assertEqual(by_key[key]["model"], ARK_DEFAULT_MODEL)
        self.assertEqual(by_key[INSPIRATION_TOOLS_INTERFACE_KEY]["max_tokens"], 3600)
        self.assertEqual(by_key[SCRIPT_GENERATE_INTERFACE_KEY]["max_tokens"], 3600)
        self.assertEqual(by_key[SCRIPT_CREATION_INTERFACE_KEY]["max_tokens"], 3600)

    def test_manual_interface_settings_are_not_overwritten_by_ark_default_migration(self):
        from models import AIInterfaceSetting

        custom_key = AIInterfaceSetting(
            interface_key="inspiration_chat",
            provider="deepseek",
            model="deepseek-chat",
            max_tokens=1234,
        )
        custom_key.api_key_secret = "manual-deepseek-key"
        custom_base_url = AIInterfaceSetting(
            interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
            provider="deepseek",
            model="deepseek-chat",
            max_tokens=1234,
        )
        custom_base_url.base_url_override = "https://api.deepseek.com"
        manual_provider = AIInterfaceSetting(
            interface_key=SCRIPT_CREATION_INTERFACE_KEY,
            provider="qwen",
            model="qwen-plus",
            max_tokens=2048,
        )
        self.db.add_all([custom_key, custom_base_url, manual_provider])
        self.db.commit()

        response = self.client.get("/api/ai-config/interfaces")

        self.assertEqual(response.status_code, 200)
        by_key = {item["interface_key"]: item for item in response.json()["interfaces"]}
        self.assertEqual(by_key["inspiration_chat"]["provider"], "deepseek")
        self.assertEqual(by_key["inspiration_chat"]["model"], "deepseek-chat")
        self.assertEqual(by_key[SCRIPT_GENERATE_INTERFACE_KEY]["provider"], "deepseek")
        self.assertEqual(by_key[SCRIPT_GENERATE_INTERFACE_KEY]["model"], "deepseek-chat")
        self.assertEqual(by_key[SCRIPT_CREATION_INTERFACE_KEY]["provider"], "qwen")
        self.assertEqual(by_key[SCRIPT_CREATION_INTERFACE_KEY]["model"], "qwen-plus")

    def test_legacy_interface_update_resolves_to_its_screenshot_group(self):
        response = self.client.put(
            "/api/ai-config/interfaces/script_rewrite",
            json={
                "provider": "qwen",
                "model": "qwen-plus",
                "max_tokens": 4096,
                "api_key": "shared-qwen-secret",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["interface_key"], SCRIPT_CREATION_INTERFACE_KEY)
        self.assertEqual(data["provider"], "qwen")
        self.assertEqual(data["model"], "qwen-plus")
        self.assertEqual(data["api_key_source"], "interface")
        self.assertNotIn("shared-qwen-secret", response.text)

        interfaces = self.client.get("/api/ai-config/interfaces").json()["interfaces"]
        by_key = {item["interface_key"]: item for item in interfaces}
        self.assertEqual(by_key[SCRIPT_CREATION_INTERFACE_KEY]["provider"], "qwen")
        self.assertNotIn("script_rewrite", by_key)

    def test_interface_setting_can_store_mask_and_clear_custom_api_config(self):
        update = {
            "provider": "qwen",
            "model": "qwen-plus",
            "max_tokens": 4096,
            "api_key": "tenant-secret-123456",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/tenant",
        }

        response = self.client.put("/api/ai-config/interfaces/inspiration_chat", json=update)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["api_key_configured"])
        self.assertEqual(data["api_key_source"], "interface")
        self.assertEqual(data["api_key_mask"], "****3456")
        self.assertEqual(data["custom_base_url"], "https://dashscope.aliyuncs.com/compatible-mode/v1/tenant")
        self.assertEqual(data["base_url"], "https://dashscope.aliyuncs.com/compatible-mode/v1/tenant")
        self.assertNotIn("tenant-secret-123456", response.text)

        get_response = self.client.get("/api/ai-config/interfaces")
        self.assertNotIn("tenant-secret-123456", get_response.text)
        by_key = {item["interface_key"]: item for item in get_response.json()["interfaces"]}
        self.assertEqual(by_key["inspiration_chat"]["api_key_mask"], "****3456")

        clear_response = self.client.put(
            "/api/ai-config/interfaces/inspiration_chat",
            json={
                "provider": "qwen",
                "model": "qwen-plus",
                "max_tokens": 4096,
                "clear_api_key": True,
                "base_url": "",
            },
        )

        self.assertEqual(clear_response.status_code, 200)
        cleared = clear_response.json()
        self.assertFalse(cleared["api_key_configured"])
        self.assertEqual(cleared["api_key_source"], "missing")
        self.assertEqual(cleared["api_key_mask"], "")
        self.assertEqual(cleared["custom_base_url"], "")

    def test_changing_provider_without_new_key_clears_interface_secret(self):
        response = self.client.put(
            "/api/ai-config/interfaces/inspiration_chat",
            json={
                "provider": "qwen",
                "model": "qwen-plus",
                "max_tokens": 4096,
                "api_key": "tenant-qwen-secret",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["api_key_source"], "interface")

        changed = self.client.put(
            "/api/ai-config/interfaces/inspiration_chat",
            json={
                "provider": "minimax",
                "model": "MiniMax-M3",
                "max_tokens": 4096,
                "base_url": "",
            },
        )

        self.assertEqual(changed.status_code, 200)
        data = changed.json()
        self.assertEqual(data["provider"], "minimax")
        self.assertFalse(data["api_key_configured"])
        self.assertEqual(data["api_key_source"], "missing")
        self.assertEqual(data["api_key_mask"], "")
        self.assertEqual(data["custom_base_url"], "")
        self.assertNotIn("tenant-qwen-secret", changed.text)

    def test_interface_update_rejects_untrusted_custom_base_url(self):
        response = self.client.put(
            "/api/ai-config/interfaces/inspiration_chat",
            json={
                "provider": "qwen",
                "model": "qwen-plus",
                "max_tokens": 4096,
                "api_key": "tenant-qwen-secret",
                "base_url": "https://evil.example.com/compatible/v1",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("base_url", response.json()["detail"])

    def test_usage_endpoint_returns_recent_records_and_totals(self):
        from models import AIUsageRecord

        self.db.add_all([
            AIUsageRecord(
                interface_key="inspiration_chat",
                provider="qwen",
                model="qwen-plus",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                usage_source="provider",
                latency_ms=120,
                status="success",
            ),
            AIUsageRecord(
                interface_key="script_rewrite",
                provider="glm",
                model="glm-5.2",
                prompt_tokens=5,
                completion_tokens=6,
                total_tokens=11,
                usage_source="estimated",
                latency_ms=80,
                status="success",
            ),
        ])
        self.db.commit()

        response = self.client.get("/api/ai-config/usage")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["totals"]["total_tokens"], 41)
        self.assertEqual(data["totals"]["calls"], 2)
        self.assertEqual(len(data["records"]), 2)
        self.assertEqual(data["records"][0]["interface_key"], "script_rewrite")

    def test_interface_payload_exposes_latest_called_model_for_display(self):
        from models import AIInterfaceSetting, AIUsageRecord

        self.db.add(
            AIInterfaceSetting(
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                provider="doubao",
                model="configured-model",
                max_tokens=3600,
            )
        )
        self.db.add(
            AIUsageRecord(
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                provider="doubao",
                model="called-model",
                prompt_tokens=10,
                completion_tokens=4,
                total_tokens=14,
                usage_source="provider",
                latency_ms=120,
                status="success",
            )
        )
        self.db.commit()

        response = self.client.get("/api/ai-config/interfaces")

        self.assertEqual(response.status_code, 200)
        by_key = {item["interface_key"]: item for item in response.json()["interfaces"]}
        script_generate = by_key[SCRIPT_GENERATE_INTERFACE_KEY]
        self.assertEqual(script_generate["model"], "configured-model")
        self.assertEqual(script_generate["latest_model"], "called-model")
        self.assertEqual(script_generate["display_model"], "called-model")

    def test_display_model_uses_configured_model_when_latest_call_is_stale(self):
        from models import AIInterfaceSetting, AIUsageRecord

        now = datetime.now()
        self.db.add(
            AIInterfaceSetting(
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                provider="doubao",
                model="new-configured-model",
                max_tokens=3600,
                updated_at=now,
            )
        )
        self.db.add(
            AIUsageRecord(
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                provider="doubao",
                model="old-called-model",
                prompt_tokens=10,
                completion_tokens=4,
                total_tokens=14,
                usage_source="provider",
                latency_ms=120,
                status="success",
                created_at=now - timedelta(minutes=5),
            )
        )
        self.db.commit()

        response = self.client.get("/api/ai-config/interfaces")

        self.assertEqual(response.status_code, 200)
        by_key = {item["interface_key"]: item for item in response.json()["interfaces"]}
        script_generate = by_key[SCRIPT_GENERATE_INTERFACE_KEY]
        self.assertEqual(script_generate["latest_model"], "old-called-model")
        self.assertEqual(script_generate["display_model"], "new-configured-model")

    def test_screenshot_group_usage_includes_only_its_legacy_records(self):
        from models import AIUsageRecord

        self.db.add_all([
            AIUsageRecord(
                interface_key="script_rewrite",
                provider="qwen",
                model="qwen-plus",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                usage_source="provider",
                latency_ms=120,
                status="success",
            ),
            AIUsageRecord(
                interface_key=SCRIPT_CREATION_INTERFACE_KEY,
                provider="qwen",
                model="qwen-plus",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                usage_source="provider",
                latency_ms=40,
                status="success",
            ),
            AIUsageRecord(
                interface_key="product_rag_global",
                provider="qwen",
                model="qwen-plus",
                prompt_tokens=1_000,
                completion_tokens=500,
                total_tokens=1_500,
                usage_source="provider",
                latency_ms=50,
                status="success",
            ),
        ])
        self.db.commit()

        response = self.client.get(f"/api/ai-config/usage?interface_key={SCRIPT_CREATION_INTERFACE_KEY}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["totals"]["total_tokens"], 165)
        self.assertEqual(data["totals"]["calls"], 2)
        record_keys = {record["interface_key"] for record in data["records"]}
        self.assertEqual(record_keys, {"script_rewrite", SCRIPT_CREATION_INTERFACE_KEY})

    def test_usage_totals_estimate_cny_cost_from_prompt_and_completion_tokens(self):
        from models import AIUsageRecord

        self.db.add(AIUsageRecord(
            interface_key="inspiration_chat",
            provider="qwen",
            model="qwen-plus",
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            total_tokens=1_500_000,
            usage_source="provider",
            latency_ms=120,
            status="success",
        ))
        self.db.commit()

        response = self.client.get("/api/ai-config/usage?interface_key=inspiration_chat")

        self.assertEqual(response.status_code, 200)
        totals = response.json()["totals"]
        self.assertAlmostEqual(totals["estimated_cost_cny"], 1.8, places=4)
        self.assertEqual(totals["estimated_cost_display"], "¥1.80")


class FakeUsage:
    prompt_tokens = 7
    completion_tokens = 11
    total_tokens = 18


class FakeMessage:
    content = "AI ok"
    reasoning_content = ""


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]
    usage = FakeUsage()


class FakeResponseWithoutUsage:
    choices = [FakeChoice()]
    usage = None


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.payload = None

    def create(self, **payload):
        self.payload = payload
        return self.response


class FakeClient:
    def __init__(self, response):
        self.completions = FakeCompletions(response)
        self.chat = type("Chat", (), {"completions": self.completions})()


class AiServiceRoutingTests(unittest.TestCase):
    def setUp(self):
        from models import AIInterfaceSetting

        self.original_env = {key: os.environ.get(key) for key in PROVIDER_ENV_KEYS}
        for key in PROVIDER_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["QWEN_API_KEY"] = "test-qwen-key"

        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add(AIInterfaceSetting(
            interface_key="inspiration_chat",
            provider="qwen",
            model="qwen-plus",
            max_tokens=1234,
        ))
        self.db.commit()

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_chat_routes_to_interface_provider_and_records_provider_usage(self):
        from models import AIUsageRecord
        from services.ai_service import AIService

        service = AIService()
        fake_client = FakeClient(FakeResponse())
        service._clients["qwen"] = fake_client

        result = asyncio.run(service.chat(
            [{"role": "user", "content": "hello"}],
            interface_key="inspiration_chat",
            allow_fallback=False,
            db=self.db,
        ))

        self.assertEqual(result, "AI ok")
        self.assertEqual(fake_client.completions.payload["model"], "qwen-plus")
        self.assertEqual(fake_client.completions.payload["max_tokens"], 1234)

        records = self.db.query(AIUsageRecord).all()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.interface_key, "inspiration_chat")
        self.assertEqual(record.provider, "qwen")
        self.assertEqual(record.model, "qwen-plus")
        self.assertEqual(record.total_tokens, 18)
        self.assertEqual(record.usage_source, "provider")
        self.assertEqual(record.status, "success")

    def test_chat_passes_request_timeout_to_provider_call(self):
        from services.ai_service import AIService

        service = AIService()
        fake_client = FakeClient(FakeResponse())
        service._clients["qwen"] = fake_client

        result = asyncio.run(service.chat(
            [{"role": "user", "content": "hello"}],
            interface_key="inspiration_chat",
            allow_fallback=False,
            request_timeout=240.0,
            db=self.db,
        ))

        self.assertEqual(result, "AI ok")
        self.assertEqual(fake_client.completions.payload["timeout"], 240.0)

    def test_legacy_interface_chat_uses_its_screenshot_group_setting(self):
        from models import AIInterfaceSetting, AIUsageRecord
        from services.ai_service import AIService

        self.db.query(AIInterfaceSetting).delete()
        self.db.add(AIInterfaceSetting(
            interface_key=SCRIPT_CREATION_INTERFACE_KEY,
            provider="qwen",
            model="qwen-plus",
            max_tokens=2048,
        ))
        self.db.commit()

        service = AIService()
        fake_client = FakeClient(FakeResponse())
        service._clients["qwen"] = fake_client

        result = asyncio.run(service.chat(
            [{"role": "user", "content": "rewrite this"}],
            interface_key="script_rewrite",
            allow_fallback=False,
            db=self.db,
        ))

        self.assertEqual(result, "AI ok")
        self.assertEqual(fake_client.completions.payload["model"], "qwen-plus")
        self.assertEqual(fake_client.completions.payload["max_tokens"], 2048)
        record = self.db.query(AIUsageRecord).one()
        self.assertEqual(record.interface_key, SCRIPT_CREATION_INTERFACE_KEY)
        self.assertEqual(record.provider, "qwen")

    def test_seedance_prompt_alias_uses_script_creation_setting(self):
        from models import AIInterfaceSetting, AIUsageRecord
        from services.ai_service import AIService

        self.db.query(AIInterfaceSetting).delete()
        self.db.add(AIInterfaceSetting(
            interface_key=SCRIPT_CREATION_INTERFACE_KEY,
            provider="qwen",
            model="qwen-plus",
            max_tokens=2048,
        ))
        self.db.commit()

        service = AIService()
        fake_client = FakeClient(FakeResponse())
        service._clients["qwen"] = fake_client

        result = asyncio.run(service.chat(
            [{"role": "user", "content": "seedance this"}],
            interface_key="seedance_prompt",
            allow_fallback=False,
            db=self.db,
        ))

        self.assertEqual(result, "AI ok")
        self.assertEqual(fake_client.completions.payload["model"], "qwen-plus")
        self.assertEqual(fake_client.completions.payload["max_tokens"], 2048)
        record = self.db.query(AIUsageRecord).one()
        self.assertEqual(record.interface_key, SCRIPT_CREATION_INTERFACE_KEY)
        self.assertEqual(record.provider, "qwen")

    def test_script_generate_chat_uses_separate_generation_setting(self):
        from models import AIInterfaceSetting, AIUsageRecord
        from services.ai_service import AIService

        self.db.query(AIInterfaceSetting).delete()
        self.db.add_all([
            AIInterfaceSetting(
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                provider="qwen",
                model="qwen-max",
                max_tokens=3072,
            ),
            AIInterfaceSetting(
                interface_key=SCRIPT_CREATION_INTERFACE_KEY,
                provider="qwen",
                model="qwen-plus",
                max_tokens=2048,
            ),
        ])
        self.db.commit()

        service = AIService()
        fake_client = FakeClient(FakeResponse())
        service._clients["qwen"] = fake_client

        result = asyncio.run(service.chat(
            [{"role": "user", "content": "generate this"}],
            interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
            allow_fallback=False,
            db=self.db,
        ))

        self.assertEqual(result, "AI ok")
        self.assertEqual(fake_client.completions.payload["model"], "qwen-max")
        self.assertEqual(fake_client.completions.payload["max_tokens"], 3072)
        record = self.db.query(AIUsageRecord).one()
        self.assertEqual(record.interface_key, SCRIPT_GENERATE_INTERFACE_KEY)
        self.assertEqual(record.provider, "qwen")

    def test_script_generate_clear_interface_key_falls_back_to_ark_env(self):
        from models import AIInterfaceSetting
        from services.ai_config import resolve_interface_connection, update_interface_setting

        os.environ["ARK_API_KEY"] = "ark-env-secret"
        os.environ["ARK_BASE_URL"] = ARK_DEFAULT_BASE_URL
        self.db.query(AIInterfaceSetting).delete()
        self.db.add(AIInterfaceSetting(
            interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
            provider="doubao",
            model="豆包2.0lite",
            max_tokens=2400,
            api_key_secret="bad-interface-key",
        ))
        self.db.commit()

        setting = update_interface_setting(
            db=self.db,
            interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
            provider="doubao",
            model=ARK_DEFAULT_MODEL,
            max_tokens=3600,
            api_key=None,
            base_url="",
            clear_api_key=True,
        )
        connection = resolve_interface_connection(setting)

        self.assertEqual(setting.model, ARK_DEFAULT_MODEL)
        self.assertEqual(setting.max_tokens, 3600)
        self.assertEqual(setting.api_key_secret, "")
        self.assertEqual(setting.base_url_override, "")
        self.assertTrue(connection["configured"])
        self.assertEqual(connection["api_key_source"], "env")
        self.assertEqual(connection["base_url"], ARK_DEFAULT_BASE_URL)

    def test_default_ark_interfaces_create_volcengine_client_from_ark_env(self):
        from models import AIInterfaceSetting, AIUsageRecord
        from services import ai_service as ai_module

        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ["ARK_API_KEY"] = "ark-env-secret"
        os.environ["ARK_BASE_URL"] = "https://ark.example.test/api/v3"
        os.environ["ARK_MODEL"] = "ep-unit-test"
        self.db.query(AIInterfaceSetting).delete()
        self.db.commit()

        original_openai = ai_module.OpenAI
        created_clients = []

        class CapturingOpenAI:
            def __init__(self, api_key, base_url, timeout):
                self.api_key = api_key
                self.base_url = base_url
                self.timeout = timeout
                self.completions = FakeCompletions(FakeResponse())
                self.chat = type("Chat", (), {"completions": self.completions})()
                created_clients.append(self)

        ai_module.OpenAI = CapturingOpenAI
        try:
            service = ai_module.AIService()
            service.client = None
            service._clients = {}
            self.assertTrue(service.is_interface_available(SCRIPT_GENERATE_INTERFACE_KEY, db=self.db))
            result = asyncio.run(service.chat(
                [{"role": "user", "content": "generate this"}],
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                allow_fallback=False,
                db=self.db,
            ))
        finally:
            ai_module.OpenAI = original_openai

        ark_client = next(client for client in created_clients if client.base_url == "https://ark.example.test/api/v3")
        self.assertEqual(result, "AI ok")
        self.assertEqual(ark_client.api_key, "ark-env-secret")
        self.assertEqual(ark_client.completions.payload["model"], "ep-unit-test")
        record = self.db.query(AIUsageRecord).one()
        self.assertEqual(record.interface_key, SCRIPT_GENERATE_INTERFACE_KEY)
        self.assertEqual(record.provider, "doubao")
        self.assertNotIn("ark-env-secret", record.error_summary or "")

    def test_doubao_interface_uses_endpoint_id_as_model_and_env_base_url(self):
        from models import AIInterfaceSetting, AIUsageRecord
        from services import ai_service as ai_module

        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ["ARK_API_KEY"] = "ark-env-secret"
        os.environ["ARK_BASE_URL"] = "https://ark.example.test/api/v3"
        self.db.query(AIInterfaceSetting).delete()
        self.db.add(AIInterfaceSetting(
            interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
            provider="doubao",
            model="ep-custom-from-ui",
            max_tokens=2400,
        ))
        self.db.commit()

        original_openai = ai_module.OpenAI
        created_clients = []

        class CapturingOpenAI:
            def __init__(self, api_key, base_url, timeout):
                self.api_key = api_key
                self.base_url = base_url
                self.timeout = timeout
                self.completions = FakeCompletions(FakeResponse())
                self.chat = type("Chat", (), {"completions": self.completions})()
                created_clients.append(self)

        ai_module.OpenAI = CapturingOpenAI
        try:
            service = ai_module.AIService()
            service.client = None
            service._clients = {}
            result = asyncio.run(service.chat(
                [{"role": "user", "content": "generate this"}],
                interface_key=SCRIPT_GENERATE_INTERFACE_KEY,
                allow_fallback=False,
                db=self.db,
            ))
        finally:
            ai_module.OpenAI = original_openai

        ark_client = next(client for client in created_clients if client.base_url == "https://ark.example.test/api/v3")
        self.assertEqual(result, "AI ok")
        self.assertEqual(ark_client.api_key, "ark-env-secret")
        self.assertEqual(ark_client.completions.payload["model"], "ep-custom-from-ui")
        record = self.db.query(AIUsageRecord).one()
        self.assertEqual(record.interface_key, SCRIPT_GENERATE_INTERFACE_KEY)
        self.assertEqual(record.provider, "doubao")
        self.assertEqual(record.model, "ep-custom-from-ui")

    def test_doubao_non_thinking_chat_disables_provider_reasoning(self):
        from models import AIInterfaceSetting
        from services.ai_service import AIService

        self.db.query(AIInterfaceSetting).delete()
        self.db.add(AIInterfaceSetting(
            interface_key="inspiration_chat",
            provider="doubao",
            model="ep-unit-test",
            max_tokens=2400,
        ))
        self.db.commit()

        service = AIService()
        fake_client = FakeClient(FakeResponse())
        service._clients["doubao"] = fake_client

        result = asyncio.run(service.chat(
            [{"role": "user", "content": "hello"}],
            interface_key="inspiration_chat",
            allow_fallback=False,
            thinking=False,
            db=self.db,
        ))

        self.assertEqual(result, "AI ok")
        self.assertEqual(
            fake_client.completions.payload.get("extra_body"),
            {"thinking": {"type": "disabled"}},
        )

    def test_chat_prefers_interface_api_key_and_base_url_over_env_defaults(self):
        from models import AIInterfaceSetting
        from services import ai_service as ai_module

        self.db.query(AIInterfaceSetting).delete()
        setting = AIInterfaceSetting(
            interface_key="inspiration_chat",
            provider="qwen",
            model="qwen-plus",
            max_tokens=1234,
        )
        setting.api_key_secret = "interface-qwen-key"
        setting.base_url_override = "https://interface.example.com/compatible/v1"
        self.db.add(setting)
        self.db.commit()

        original_openai = ai_module.OpenAI
        created_clients = []

        class CapturingOpenAI:
            def __init__(self, api_key, base_url, timeout):
                self.api_key = api_key
                self.base_url = base_url
                self.timeout = timeout
                self.completions = FakeCompletions(FakeResponse())
                self.chat = type("Chat", (), {"completions": self.completions})()
                created_clients.append(self)

        ai_module.OpenAI = CapturingOpenAI
        try:
            service = ai_module.AIService()
            service.client = None
            service._clients = {}

            result = asyncio.run(service.chat(
                [{"role": "user", "content": "hello"}],
                interface_key="inspiration_chat",
                allow_fallback=False,
                db=self.db,
            ))
        finally:
            ai_module.OpenAI = original_openai

        qwen_client = next(
            client for client in created_clients
            if client.base_url == "https://interface.example.com/compatible/v1"
        )
        self.assertEqual(result, "AI ok")
        self.assertEqual(qwen_client.api_key, "interface-qwen-key")
        self.assertEqual(qwen_client.base_url, "https://interface.example.com/compatible/v1")
        self.assertEqual(qwen_client.completions.payload["model"], "qwen-plus")

    def test_chat_estimates_usage_when_provider_does_not_return_usage(self):
        from models import AIUsageRecord
        from services.ai_service import AIService

        service = AIService()
        service._clients["qwen"] = FakeClient(FakeResponseWithoutUsage())

        result = asyncio.run(service.chat(
            [{"role": "user", "content": "estimate this response"}],
            interface_key="inspiration_chat",
            allow_fallback=False,
            db=self.db,
        ))

        self.assertEqual(result, "AI ok")
        record = self.db.query(AIUsageRecord).one()
        self.assertGreater(record.total_tokens, 0)
        self.assertEqual(record.usage_source, "estimated")
        self.assertEqual(record.status, "success")

    def test_unconfigured_provider_records_unavailable_without_secret_leak(self):
        from models import AIInterfaceSetting, AIUsageRecord
        from services.ai_service import AIService

        os.environ.pop("MINIMAX_API_KEY", None)
        self.db.query(AIInterfaceSetting).delete()
        self.db.add(AIInterfaceSetting(
            interface_key="inspiration_chat",
            provider="minimax",
            model="MiniMax-M3",
            max_tokens=1000,
        ))
        self.db.commit()

        service = AIService()
        result = asyncio.run(service.chat(
            [{"role": "user", "content": "hello"}],
            interface_key="inspiration_chat",
            allow_fallback=False,
            db=self.db,
        ))

        self.assertEqual(result, "")
        record = self.db.query(AIUsageRecord).one()
        self.assertEqual(record.status, "unavailable")
        self.assertEqual(record.provider, "minimax")
        self.assertNotIn("test-qwen-key", record.error_summary or "")


class AiConfigPageTests(unittest.TestCase):
    def test_ai_config_route_renders_page(self):
        from main import app

        response = TestClient(app).get("/app/ai-config")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AI配置", response.text)
        self.assertIn("providerSelect", response.text)
        self.assertIn("modelSelect", response.text)
        self.assertIn("customModelInput", response.text)
        self.assertIn("apiKeyInput", response.text)
        self.assertIn("baseUrlInput", response.text)
        self.assertIn("baseUrlLabel", response.text)
        self.assertIn("baseUrlHelp", response.text)
        self.assertIn("clearApiKeyBtn", response.text)
        self.assertIn("estimatedCost", response.text)
        self.assertIn("预估花费", response.text)
        self.assertNotIn("latestStatus", response.text)
        self.assertIn("usageRecordTable", response.text)

    def test_provider_status_uses_selected_interface_api_key_state(self):
        page = (ROOT / "templates" / "ai_config.html").read_text(encoding="utf-8-sig")

        self.assertIn("function providerStatusForDisplay(provider,item)", page)
        self.assertIn("item.provider===provider.key&&item.api_key_source==='interface'", page)
        self.assertIn("item.api_key_mask||'****'", page)
        self.assertIn("renderProviderStatus();\n loadUsage();", page)
        self.assertIn("renderProviderStatus();\n }catch(error)", page)

    def test_ai_config_page_displays_latest_called_model(self):
        page = (ROOT / "templates" / "ai_config.html").read_text(encoding="utf-8-sig")

        self.assertIn('id="callModelStatus"', page)
        self.assertIn("function modelForDisplay(item)", page)
        self.assertIn("item.display_model||item.latest_model||item.model", page)
        self.assertIn("document.getElementById('callModelStatus').textContent=modelForDisplay(item)||'-';", page)
        self.assertIn("escHtml(modelForDisplay(item))", page)

    def test_doubao_ui_uses_model_dropdown_for_volcengine_services(self):
        page = (ROOT / "templates" / "ai_config.html").read_text(encoding="utf-8-sig")

        self.assertIn('<select id="modelSelect" class="input" onchange="onModelSelectChange()"></select>', page)
        self.assertIn("renderModelOptions(item.model);", page)
        self.assertIn("function isDoubaoProvider()", page)
        self.assertIn("function volcengineEndpointForDisplay(model)", page)
        self.assertIn("model:isDoubaoProvider()?(document.getElementById('baseUrlInput').value.trim()||currentModelValue()):currentModelValue()", page)
        self.assertIn("base_url:isDoubaoProvider()?'':document.getElementById('baseUrlInput').value.trim()", page)
        self.assertIn("toast('请填写模型名或 Endpoint ID','error');return;", page)
        self.assertNotIn("document.getElementById('modelSelectField').style.display=isDoubaoProvider()?'none':'grid';", page)

    def test_doubao_base_url_field_becomes_endpoint_id_input(self):
        page = (ROOT / "templates" / "ai_config.html").read_text(encoding="utf-8-sig")

        self.assertIn("document.getElementById('baseUrlLabel').textContent=isDoubaoProvider()?'接入点 ID':'Base URL';", page)
        self.assertIn("填写火山方舟接入点 ID（ep-...）；留空则使用上方模型服务。", page)
        self.assertIn("document.getElementById('baseUrlInput').placeholder=isDoubaoProvider()?'例如 ep-20260703160153-h5cx5':", page)
        self.assertIn("document.getElementById('baseUrlInput').value=isDoubaoProvider()?volcengineEndpointForDisplay(item.model):(item.custom_base_url||'');", page)
        self.assertIn("document.getElementById('baseUrlInput').type=isDoubaoProvider()?'text':'url';", page)

    def test_top_nav_no_longer_contains_ai_config_link(self):
        pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
            "ai_config.html",
        ]
        for name in pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            nav_links = re.search(
                r'<div class="nav-links">(?P<body>.*?)</div></div></nav>',
                page,
                flags=re.S,
            )
            self.assertIsNotNone(nav_links, name)
            self.assertNotIn('href="/app/ai-config"', nav_links.group("body"), name)
            self.assertNotIn(">AI配置</a>", nav_links.group("body"), name)
            self.assertRegex(nav_links.group("body"), r'href="/app/search"[^>]*>检索</a>\s*$', name)

    def test_non_config_pages_have_bottom_right_ai_config_button(self):
        non_config_pages = [
            "index.html",
            "rewrite.html",
            "products.html",
            "import.html",
            "templates.html",
            "history.html",
            "search.html",
            "inspiration.html",
        ]
        for name in non_config_pages:
            page = (ROOT / "templates" / name).read_text(encoding="utf-8-sig")
            self.assertIn('class="ai-config-fab"', page, name)
            self.assertIn('href="/app/ai-config"', page, name)
            self.assertIn('aria-label="打开 AI配置"', page, name)
            self.assertIn('data-lucide="settings"', page, name)

        config_page = (ROOT / "templates" / "ai_config.html").read_text(encoding="utf-8-sig")
        self.assertNotIn('class="ai-config-fab"', config_page)


if __name__ == "__main__":
    unittest.main()
