import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Product, SellingPoint
from services.product_knowledge_chunks import build_product_knowledge_chunks


class ProductKnowledgeEvidenceTests(unittest.TestCase):
    def test_chunks_exclude_generated_profile_items_and_keep_item_source(self):
        product = SimpleNamespace(
            id=7,
            name="浅柔色素",
            category="烘焙调色",
            brand="法采",
            description="低饱和度蛋糕调色产品。",
            price=38.6,
            selling_points=[],
        )
        detail = {
            "id": 7,
            "name": "浅柔色素",
            "category": "烘焙调色",
            "brand": "法采",
            "description": "低饱和度蛋糕调色产品。",
            "manual_source": "产品手册.md",
            "knowledge_sources": ["浅柔色素档案.md"],
            "selling_points": [],
            "sku_prices": [],
            "profile_sections": [{
                "id": "usage_scenarios",
                "title": "使用场景",
                "items": [
                    {
                        "label": "适用场景",
                        "content": "适合低饱和度奶油调色。",
                        "source": "浅柔色素档案.md",
                    },
                    {
                        "label": "门店方案",
                        "content": "这是系统自动补全文案。",
                        "generated": True,
                    },
                ],
                "sku_prices": [],
            }],
        }

        chunks = build_product_knowledge_chunks(product, detail)

        self.assertFalse(any("系统自动补全文案" in chunk.text for chunk in chunks))
        usage = next(chunk for chunk in chunks if "低饱和度奶油调色" in chunk.text)
        self.assertEqual(usage.source_name, "浅柔色素档案.md")
        self.assertEqual(usage.evidence_type, "direct_fact")
        self.assertTrue(usage.source_ref)
        self.assertEqual(len(usage.content_hash), 64)

    def test_solution_chunks_are_association_evidence(self):
        product = SimpleNamespace(
            id=8,
            name="夹心珠",
            category="烘焙夹心",
            brand="法采",
            description="增加夹心口感。",
            price=20,
            selling_points=[],
        )
        detail = {
            "id": 8,
            "name": "夹心珠",
            "category": "烘焙夹心",
            "brand": "法采",
            "description": "增加夹心口感。",
            "manual_source": "产品手册.md",
            "knowledge_sources": ["五大门店解决方案.md"],
            "selling_points": [],
            "sku_prices": [],
            "profile_sections": [{
                "id": "usage_scenarios",
                "title": "使用场景",
                "items": [{
                    "label": "门店方案",
                    "content": "夹心蛋糕方案可搭配夹心珠和奶冻粉。",
                    "source": "五大门店解决方案.md",
                }],
                "sku_prices": [],
            }],
        }

        chunks = build_product_knowledge_chunks(product, detail)

        solution = next(chunk for chunk in chunks if "夹心蛋糕方案" in chunk.text)
        self.assertEqual(solution.evidence_type, "association")

    def test_quality_report_counts_cross_product_duplicates_and_sources(self):
        from services.product_knowledge_chunks import product_knowledge_quality_report

        first = SimpleNamespace(
            id=1,
            name="产品甲",
            category="烘焙调味",
            brand="法采",
            description="共享描述",
            price=10,
            selling_points=[],
        )
        second = SimpleNamespace(
            id=2,
            name="产品乙",
            category="烘焙调味",
            brand="法采",
            description="共享描述并提到产品甲",
            price=12,
            selling_points=[],
        )

        report = product_knowledge_quality_report([first, second])

        self.assertEqual(report["product_count"], 2)
        self.assertGreaterEqual(report["chunk_count"], 2)
        self.assertGreaterEqual(report["cross_product_mention_chunks"], 1)
        self.assertEqual(report["generated_chunks"], 0)
        self.assertEqual(report["missing_source_chunks"], 0)

    def test_quality_gate_rejects_generated_or_missing_source_chunks(self):
        from services.product_knowledge_chunks import validate_product_knowledge_quality_report

        report = {
            "product_count": 1,
            "chunk_count": 10,
            "duplicate_cross_product_groups": 0,
            "cross_product_mention_chunks": 0,
            "missing_source_chunks": 1,
            "generated_chunks": 1,
        }

        with self.assertRaisesRegex(ValueError, "生成内容|缺少来源"):
            validate_product_knowledge_quality_report(report)


class ProductQueryPlannerTests(unittest.TestCase):
    def test_plan_recognizes_exact_product_price_query(self):
        from services.product_query_planner import build_product_query_plan

        products = [
            SimpleNamespace(id=1, name="布蕾粉", category="烘焙夹心"),
            SimpleNamespace(id=2, name="夹心果泥", category="烘焙夹心"),
        ]

        plan = build_product_query_plan("布蕾粉价格", products)

        self.assertEqual(plan.query_type, "price")
        self.assertEqual(plan.entity_product_ids, (1,))
        self.assertEqual(plan.entity_names, ("布蕾粉",))
        self.assertTrue(plan.wants_price)

    def test_plan_recognizes_product_alias_as_exact_entity(self):
        from services.product_query_planner import build_product_query_plan

        products = [
            SimpleNamespace(
                id=1,
                name="浅柔色素",
                category="烘焙调色",
                selling_points=[],
            ),
        ]

        plan = build_product_query_plan("浅色色素价格", products)

        self.assertEqual(plan.entity_product_ids, (1,))
        self.assertEqual(plan.entity_names, ("浅柔色素",))

    def test_plan_distinguishes_use_case_from_attribute_filter(self):
        from services.product_query_planner import build_product_query_plan

        use_case = build_product_query_plan("适合淋面的产品有哪些？", [])
        attribute = build_product_query_plan("有哪些低糖产品？", [])

        self.assertEqual(use_case.query_type, "use_case_recommendation")
        self.assertEqual(use_case.desired_use, "淋面")
        self.assertEqual(attribute.query_type, "attribute_filter")
        self.assertEqual(attribute.desired_use, "低糖控糖")

    def test_plan_extracts_glaze_scene_from_natural_word_order(self):
        from services.product_query_planner import build_product_query_plan

        plan = build_product_query_plan("蛋糕淋面可以用什么？", [])

        self.assertEqual(plan.query_type, "use_case_recommendation")
        self.assertEqual(plan.desired_use, "淋面")
        self.assertIn("glaze", plan.facets)

    def test_plan_recognizes_macaron_as_direct_evidence_scene(self):
        from services.product_query_planner import build_product_query_plan

        plan = build_product_query_plan("马卡龙调色用什么？", [])

        self.assertIn("macaron", plan.facets)

    def test_plan_expands_oven_query_to_high_heat_evidence_facet(self):
        from services.product_query_planner import build_product_query_plan

        plan = build_product_query_plan("可以进烤箱的产品有哪些？", [])

        self.assertEqual(plan.query_type, "attribute_filter")
        self.assertEqual(plan.desired_use, "耐高温烘烤")
        self.assertIn("high_heat", plan.facets)

    def test_plan_does_not_treat_generic_baked_dessert_selection_as_heat_resistance(self):
        from services.product_query_planner import build_product_query_plan

        plan = build_product_query_plan("做烤制甜点用哪些产品？", [])

        self.assertNotIn("high_heat", plan.facets)

    def test_plan_recognizes_friendly_sweetness_as_low_sugar_facet(self):
        from services.product_query_planner import build_product_query_plan

        plan = build_product_query_plan("有哪些糖类产品甜度更友好？", [])

        self.assertIn("low_sugar", plan.facets)

    def test_plan_keeps_baked_texture_separate_from_color_heat_stability(self):
        from services.product_query_planner import build_product_query_plan

        plan = build_product_query_plan("烤后还能保持口感的产品", [])

        self.assertIn("baked_texture", plan.facets)
        self.assertNotIn("high_heat", plan.facets)

    def test_plan_expands_negative_product_synonyms(self):
        from services.product_query_planner import build_product_query_plan

        plan = build_product_query_plan("调色产品，不要油性色素", [])

        self.assertIn("油性色素", plan.negative_terms)
        self.assertIn("油溶色粉", plan.negative_terms)

    def test_plan_keeps_different_length_products_in_comparison(self):
        from services.product_query_planner import build_product_query_plan

        products = [
            SimpleNamespace(id=1, name="甲粉", selling_points=[]),
            SimpleNamespace(id=2, name="超长产品乙-大", selling_points=[]),
            SimpleNamespace(id=3, name="超长产品乙", selling_points=[]),
        ]

        plan = build_product_query_plan("甲粉和超长产品乙-大有什么区别？", products)

        self.assertEqual(plan.query_type, "comparison")
        self.assertEqual(plan.entity_product_ids, (1, 2))


class ProductHybridSearchTests(unittest.TestCase):
    def test_hybrid_search_fuses_vector_and_keyword_results(self):
        from vector_store.product_store import ProductVectorStore

        store = ProductVectorStore.__new__(ProductVectorStore)
        store.store = SimpleNamespace(require_available=lambda: None)
        vector_hit = {
            "chunk_id": "product_1:info",
            "product_id": 1,
            "name": "水性色素",
            "document": "适合奶油调色",
            "distance": 0.1,
        }
        keyword_hit = {
            "chunk_id": "product_2:info",
            "product_id": 2,
            "name": "浅柔色素",
            "document": "适合低饱和度调色",
            "distance": None,
        }
        store.search = lambda *args, **kwargs: [vector_hit]
        store._keyword_search = lambda *args, **kwargs: [keyword_hit]

        results = store.hybrid_search("奶油调色", db=None, limit=10)

        self.assertEqual({item["product_id"] for item in results}, {1, 2})
        self.assertTrue(all("rrf_score" in item for item in results))
        self.assertEqual(results[0]["retrieval_sources"], ["vector"])

    def test_hybrid_search_downweights_association_evidence(self):
        from vector_store.product_store import ProductVectorStore

        store = ProductVectorStore.__new__(ProductVectorStore)
        store.store = SimpleNamespace(require_available=lambda: None)
        association = {
            "chunk_id": "product_1:association",
            "product_id": 1,
            "name": "搭配产品",
            "document": "方案中顺带提到该产品。",
            "distance": 0.05,
            "evidence_type": "association",
        }
        direct = {
            "chunk_id": "product_2:direct",
            "product_id": 2,
            "name": "直接产品",
            "document": "该产品直接适用于问题场景。",
            "distance": 0.1,
            "evidence_type": "direct_fact",
        }
        store.search = lambda *args, **kwargs: [association, direct]
        store._keyword_search = lambda *args, **kwargs: []

        results = store.hybrid_search("适用产品", db=None, limit=10)

        self.assertEqual(results[0]["product_id"], 2)
        self.assertLess(results[1]["rrf_score"], results[0]["rrf_score"])

    def test_hybrid_search_keeps_bm25_when_vector_search_fails(self):
        from vector_store.product_store import ProductVectorStore

        store = ProductVectorStore.__new__(ProductVectorStore)
        store.store = SimpleNamespace()
        store.search = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("vector down"))
        store._keyword_search = lambda *args, **kwargs: [{
            "chunk_id": "product_2:info",
            "product_id": 2,
            "name": "浅柔色素",
            "document": "适合低饱和度调色",
            "keyword_score": 8.0,
        }]

        results = store.hybrid_search("浅柔调色", db=None, limit=10)

        self.assertEqual([item["product_id"] for item in results], [2])
        self.assertIn("vector down", results[0]["vector_degraded_reason"])

    def test_hybrid_search_caps_chunks_per_product(self):
        from vector_store.product_store import ProductVectorStore

        store = ProductVectorStore.__new__(ProductVectorStore)
        store.store = SimpleNamespace()
        store.search = lambda *args, **kwargs: [
            {
                "chunk_id": f"product_1:{index}",
                "product_id": 1,
                "name": "重复产品",
                "document": f"重复证据 {index}",
                "distance": index / 100,
            }
            for index in range(4)
        ] + [{
            "chunk_id": "product_2:info",
            "product_id": 2,
            "name": "另一产品",
            "document": "另一条直接证据",
            "distance": 0.2,
        }]
        store._keyword_search = lambda *args, **kwargs: []

        results = store.hybrid_search("产品", db=None, limit=4)

        self.assertIn(2, {item["product_id"] for item in results})
        self.assertLessEqual(
            sum(1 for item in results if item["product_id"] == 1),
            3,
        )


class ProductRerankerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            from services.product_reranker import clear_product_rerank_cache

            clear_product_rerank_cache()
        except ImportError:
            pass

    async def test_reranker_filters_irrelevant_hits_and_preserves_pinned_product(self):
        from services.product_reranker import rerank_product_hits

        hits = [
            {
                "product_id": 2,
                "chunk_id": "product_2:usage",
                "name": "手绘膏",
                "document": "用于蛋糕表面绘画，不是淋面原料。",
                "evidence_type": "direct_fact",
            },
            {
                "product_id": 1,
                "chunk_id": "product_1:usage",
                "name": "调味果酱",
                "document": "可用于奶油、慕斯和蛋糕淋面调味。",
                "evidence_type": "direct_fact",
            },
        ]

        async def fake_chat(messages, **kwargs):
            self.assertEqual(kwargs["interface_key"], "product_rag_rerank")
            return json.dumps({
                "items": [
                    {"product_id": 1, "score": 96, "relevant": True},
                    {"product_id": 2, "score": 18, "relevant": False},
                ]
            }, ensure_ascii=False)

        outcome = await rerank_product_hits(
            "适合淋面的产品有哪些？",
            hits,
            ai_chat=fake_chat,
            pinned_product_ids=(1,),
            limit=8,
        )

        self.assertEqual([item["product_id"] for item in outcome.hits], [1])
        self.assertEqual(outcome.status, "success")
        self.assertEqual(outcome.scores[1], 96)

    async def test_reranker_failure_returns_fused_order(self):
        from services.product_reranker import rerank_product_hits

        hits = [
            {"product_id": 1, "chunk_id": "one", "name": "产品一", "document": "资料一"},
            {"product_id": 2, "chunk_id": "two", "name": "产品二", "document": "资料二"},
        ]

        async def failing_chat(*args, **kwargs):
            raise RuntimeError("rerank unavailable")

        outcome = await rerank_product_hits(
            "查询",
            hits,
            ai_chat=failing_chat,
            limit=8,
        )

        self.assertEqual([item["product_id"] for item in outcome.hits], [1, 2])
        self.assertEqual(outcome.status, "degraded")
        self.assertIn("rerank unavailable", outcome.degraded_reason)

    async def test_reranker_rejects_auxiliary_relation_even_when_model_marks_relevant(self):
        from services.product_reranker import rerank_product_hits

        hits = [{
            "product_id": 1,
            "chunk_id": "hand_paint",
            "name": "手绘膏",
            "category": "烘焙装饰",
            "document": "用于在蛋糕淋面上绘画。",
        }]

        async def fake_chat(messages, **kwargs):
            self.assertIn("品类：烘焙装饰", messages[1]["content"])
            return json.dumps({
                "items": [{
                    "product_id": 1,
                    "score": 85,
                    "relation": "auxiliary",
                    "relevant": True,
                }]
            }, ensure_ascii=False)

        outcome = await rerank_product_hits(
            "适合淋面的产品有哪些？",
            hits,
            ai_chat=fake_chat,
        )

        self.assertEqual(outcome.hits, [])
        self.assertEqual(outcome.relations[1], "auxiliary")

    async def test_successful_rerank_is_cached_for_identical_evidence(self):
        from services.product_reranker import rerank_product_hits

        calls = 0
        hits = [{
            "product_id": 1,
            "chunk_id": "one",
            "name": "产品一",
            "document": "可直接回答问题。",
            "content_hash": "abc",
        }]

        async def fake_chat(*args, **kwargs):
            nonlocal calls
            calls += 1
            return '{"items":[{"product_id":1,"score":90,"relevant":true}]}'

        await rerank_product_hits("查询", hits, ai_chat=fake_chat)
        await rerank_product_hits("查询", hits, ai_chat=fake_chat)

        self.assertEqual(calls, 1)

    async def test_known_intent_comparison_pins_filtered_primary_products(self):
        from services import product_rag
        from services.product_rag import ProductQueryPolicy, ProductRetrievalSelection
        from services.product_reranker import ProductRerankOutcome

        products = [
            SimpleNamespace(id=1, name="水性色素", selling_points=[]),
            SimpleNamespace(id=2, name="油性色素", selling_points=[]),
        ]
        selection = ProductRetrievalSelection(
            products=products,
            policy=ProductQueryPolicy(
                intent="coloring",
                broad=True,
                strict_primary_filter=True,
                intents=("coloring",),
                categories=("烘焙调色",),
            ),
            hit_chunks=[
                {"product_id": 1, "chunk_id": "one", "document": "水性体系"},
                {"product_id": 2, "chunk_id": "two", "document": "油性体系"},
            ],
            excluded_product_ids=[],
            retrieval_mode="vector+keyword+category",
        )
        query_plan = SimpleNamespace(
            entity_product_ids=(),
            query_type="comparison",
            facets=(),
        )
        captured = {}

        async def fake_rerank(*args, **kwargs):
            captured["pinned"] = kwargs["pinned_product_ids"]
            return ProductRerankOutcome(hits=selection.hit_chunks, status="success")

        with patch("services.product_rag.rerank_product_hits", side_effect=fake_rerank):
            await product_rag._rerank_product_selection(
                "调色产品适用材料区别",
                selection,
                products,
                query_plan,
                candidate_limit=30,
                index_version="test",
            )

        self.assertEqual(captured["pinned"], (1, 2))

    async def test_rerank_cache_isolated_by_index_version(self):
        from services.product_reranker import rerank_product_hits

        calls = 0
        hits = [{
            "product_id": 1,
            "chunk_id": "one",
            "name": "产品一",
            "document": "可直接回答问题。",
            "content_hash": "abc",
        }]

        async def fake_chat(*args, **kwargs):
            nonlocal calls
            calls += 1
            return '{"items":[{"product_id":1,"score":90,"relevant":true}]}'

        await rerank_product_hits("查询", hits, ai_chat=fake_chat, index_version="v1")
        await rerank_product_hits("查询", hits, ai_chat=fake_chat, index_version="v2")

        self.assertEqual(calls, 2)


class ProductGroundingVerifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_verifier_replaces_unsupported_answer(self):
        from services.product_grounding import verify_grounded_answer

        async def fake_chat(messages, **kwargs):
            self.assertEqual(kwargs["interface_key"], "product_rag_verify")
            return json.dumps({
                "supported": False,
                "answer": "简要回答：资料只支持冷藏定型。\n\n具体信息：建议冷藏定型。",
            }, ensure_ascii=False)

        outcome = await verify_grounded_answer(
            "布蕾粉怎么定型",
            "简要回答：室温十分钟即可定型。",
            "建议冷藏定型。",
            ai_chat=fake_chat,
        )

        self.assertFalse(outcome.supported)
        self.assertIn("冷藏定型", outcome.answer)
        self.assertNotIn("室温十分钟", outcome.answer)

    async def test_verifier_failure_keeps_original_answer(self):
        from services.product_grounding import verify_grounded_answer

        async def failing_chat(*args, **kwargs):
            raise RuntimeError("verify unavailable")

        outcome = await verify_grounded_answer(
            "怎么用",
            "原始答案",
            "资料",
            ai_chat=failing_chat,
        )

        self.assertEqual(outcome.answer, "原始答案")
        self.assertFalse(outcome.supported)
        self.assertEqual(outcome.status, "degraded")


class ProductContextTests(unittest.TestCase):
    def test_single_product_price_answer_is_direct(self):
        from services.product_rag import _fallback_answer

        answer = _fallback_answer(
            "布蕾粉价格",
            [{
                "name": "布蕾粉",
                "price": 18.59,
                "category": "烘焙夹心",
                "sku_prices": [{"line": "焦糖味布蕾粉200g：售价 ¥18.59"}],
                "selling_points": [],
            }],
            "global",
        )

        self.assertIn("布蕾粉参考售价为 ¥18.59", answer)
        self.assertNotIn("适合“布蕾粉价格”", answer)

    def test_ai_context_keeps_at_most_three_direct_chunks_per_product(self):
        from services.product_rag import _context_for_ai

        chunks = [
            {
                "section": "selling_point",
                "source_name": "资料.md",
                "document": f"直接证据{index}",
                "evidence_type": "direct_fact",
            }
            for index in range(1, 5)
        ]
        chunks.append({
            "section": "association",
            "source_name": "方案.md",
            "document": "关联证据不应混入",
            "evidence_type": "association",
        })

        context = _context_for_ai([{
            "name": "测试产品",
            "category": "测试品类",
            "retrieval_chunks": chunks,
            "selling_points": [],
            "sku_prices": [],
            "sources": [],
        }])

        self.assertIn("直接证据1", context)
        self.assertIn("直接证据3", context)
        self.assertNotIn("直接证据4", context)
        self.assertNotIn("关联证据不应混入", context)


class ProductRetrievalRegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _product(self, name, category, description, point):
        product = Product(
            name=name,
            category=category,
            price=20,
            brand="法采",
            description=description,
            status="active",
        )
        self.db.add(product)
        self.db.flush()
        self.db.add(SellingPoint(
            product_id=product.id,
            point_type="核心卖点",
            content=point,
            priority=1,
        ))
        self.db.commit()
        return product

    def test_exact_product_name_is_pinned_first(self):
        from services import product_rag

        target = self._product("布蕾粉", "烘焙夹心", "布蕾蛋糕夹心粉。", "用于制作布蕾夹心。")
        noisy = self._product(
            "夹心果泥",
            "烘焙夹心",
            "产品组合资料包含布蕾粉价格和奶冻粉价格。",
            "果泥夹心产品。",
        )

        hits = [
            {"product_id": noisy.id, "chunk_id": "noise", "document": noisy.description, "distance": 0.05},
            {"product_id": target.id, "chunk_id": "target", "document": target.description, "distance": 0.1},
        ]
        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection("布蕾粉价格", self.db, 10)

        self.assertEqual([product.id for product in selection.products], [target.id])

    def test_negative_product_condition_removes_matching_candidate(self):
        from services import product_rag

        kept = self._product("水性色素", "烘焙调色", "适合奶油调色。", "水性体系调色。")
        removed = self._product("油性色素", "烘焙调色", "适合油脂调色。", "油性体系调色。")

        hits = [
            {"product_id": kept.id, "chunk_id": "kept", "document": kept.description},
            {"product_id": removed.id, "chunk_id": "removed", "document": removed.description},
        ]
        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "调色产品，不要油性色素",
                self.db,
                10,
            )

        ids = [product.id for product in selection.products]
        self.assertIn(kept.id, ids)
        self.assertNotIn(removed.id, ids)
        self.assertEqual({hit["product_id"] for hit in selection.hit_chunks}, {kept.id})

    def test_unknown_use_case_excludes_auxiliary_function_categories(self):
        from services import product_rag

        decoration = self._product("手绘膏", "烘焙装饰", "可在淋面上绘画。", "用于淋面图案填充。")
        flavoring = self._product("调味果酱", "烘焙调味", "可给淋面调味。", "用于调配淋面风味。")
        hits = [
            {"product_id": decoration.id, "chunk_id": "decoration", "document": decoration.description},
            {"product_id": flavoring.id, "chunk_id": "flavoring", "document": flavoring.description},
        ]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "适合淋面的产品有哪些？",
                self.db,
                10,
            )

        self.assertEqual([product.id for product in selection.products], [flavoring.id])
        self.assertEqual({hit["product_id"] for hit in selection.hit_chunks}, {flavoring.id})

    def test_glaze_facet_keeps_direct_use_and_rejects_drawing_on_glaze(self):
        from services import product_rag

        direct = self._product(
            "调味果酱",
            "烘焙调味",
            "适合用于制作蛋糕淋面。",
            "主要场景：调奶油、慕斯、淋面。",
        )
        auxiliary = self._product(
            "手绘膏",
            "烘焙装饰",
            "可在淋面上绘画。",
            "用于淋面图案填充。",
        )
        hits = [
            {"product_id": auxiliary.id, "chunk_id": "aux", "document": auxiliary.description},
            {"product_id": direct.id, "chunk_id": "direct", "document": direct.description},
        ]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "蛋糕淋面可以用什么？",
                self.db,
                10,
            )

        self.assertEqual([product.id for product in selection.products], [direct.id])

    def test_macaron_facet_keeps_only_products_with_direct_macaron_evidence(self):
        from services import product_rag

        direct = self._product(
            "水溶色粉",
            "烘焙调色",
            "主要用于马卡龙调色。",
            "适合蛋白霜体系。",
        )
        semantic_only = self._product(
            "油性色素",
            "烘焙调色",
            "适合巧克力和油脂体系。",
            "用于油性材料调色。",
        )
        hits = [
            {"product_id": semantic_only.id, "chunk_id": "semantic", "document": semantic_only.description},
            {"product_id": direct.id, "chunk_id": "direct", "document": direct.description},
        ]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "马卡龙调色用什么？",
                self.db,
                10,
            )

        self.assertEqual([product.id for product in selection.products], [direct.id])

    def test_high_heat_facet_rejects_negated_or_incidental_mentions(self):
        from services import product_rag

        positive = self._product(
            "斑斓粉",
            "烘焙调味",
            "耐高温，烘焙后仍能保持颜色。",
            "适合烤制甜点。",
        )
        no_oven = self._product(
            "布蕾粉",
            "烘焙夹心",
            "无需烤箱即可成型。",
            "冷藏定型。",
        )
        do_not_bake = self._product(
            "夹心珠",
            "烘焙夹心",
            "别烘烤，巧克力会融化。",
            "适合冷加工夹心。",
        )
        sanitized = self._product(
            "袋装刀叉",
            "烘焙配件",
            "出厂前经过高温消毒。",
            "用于蛋糕交付。",
        )
        hits = [
            {"product_id": product.id, "chunk_id": str(product.id), "document": product.description}
            for product in [no_oven, do_not_bake, sanitized, positive]
        ]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "可以进烤箱的产品有哪些？",
                self.db,
                10,
            )

        self.assertEqual([product.id for product in selection.products], [positive.id])

    def test_low_sugar_facet_does_not_promote_products_that_only_list_sugar_ingredients(self):
        from services import product_rag

        primary = self._product(
            "海藻糖",
            "烘焙调味",
            "海藻糖产品。",
            "适合低甜度配方。",
        )
        ingredient_only = self._product(
            "色粉盘",
            "烘焙调色",
            "配料包含食用色素、山梨糖醇、海藻糖和淀粉。",
            "用于翻糖彩绘。",
        )
        hits = [
            {"product_id": ingredient_only.id, "chunk_id": "ingredient", "document": ingredient_only.description},
            {"product_id": primary.id, "chunk_id": "primary", "document": primary.description},
        ]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "有哪些低糖产品？",
                self.db,
                10,
            )

        self.assertEqual([product.id for product in selection.products], [primary.id])

    def test_baked_texture_query_does_not_use_color_stability_as_evidence(self):
        from services import product_rag

        color_stable = self._product(
            "水性色素",
            "烘焙调色",
            "烘焙后颜色保持度高，不易因高温褪色。",
            "适合烘焙调色。",
        )
        baked = self._product(
            "杏仁片",
            "烘焙调味",
            "混合后切片烘烤。",
            "用于曲奇。",
        )
        hits = [
            {"product_id": color_stable.id, "chunk_id": "color", "document": color_stable.description},
            {"product_id": baked.id, "chunk_id": "baked", "document": baked.description},
        ]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "烤后还能保持口感的产品",
                self.db,
                10,
            )

        self.assertEqual(selection.products, [])

    def test_category_completed_candidate_receives_local_direct_evidence(self):
        from services import product_rag

        first = self._product("水性色素", "烘焙调色", "适合奶油调色。", "水性体系调色。")
        second = self._product("浅柔色素", "烘焙调色", "适合低饱和调色。", "浅色更易控制。")
        hits = [{
            "product_id": first.id,
            "chunk_id": "first",
            "name": first.name,
            "category": first.category,
            "document": first.description,
        }]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection("调色产品", self.db, 10)

        self.assertEqual({product.id for product in selection.products}, {first.id, second.id})
        self.assertEqual(
            {int(hit["product_id"]) for hit in selection.hit_chunks},
            {first.id, second.id},
        )

    def test_visual_output_wording_uses_decoration_intent(self):
        from services.product_rag import _product_query_policy

        policy = _product_query_policy("提高蛋糕出片效果用什么？")

        self.assertEqual(policy.intent, "decoration")
        self.assertTrue(policy.strict_primary_filter)

    def test_out_of_domain_accessory_query_returns_no_product_candidates(self):
        from services import product_rag

        accessory = self._product(
            "盒装刀叉",
            "烘焙配件",
            "蛋糕交付配件。",
            "用于门店打包。",
        )
        hits = [{
            "product_id": accessory.id,
            "chunk_id": "accessory",
            "document": accessory.description,
        }]

        with patch("vector_store.product_store.ProductVectorStore.hybrid_search", return_value=hits):
            selection = product_rag._retrieve_product_selection(
                "有哪些手机配件？",
                self.db,
                10,
            )

        self.assertEqual(selection.policy.intent, "out_of_domain")
        self.assertEqual(selection.products, [])

    def test_scoped_question_retrieves_chunks_for_selected_product(self):
        from services import product_rag

        product = self._product("布蕾粉", "烘焙夹心", "布蕾蛋糕夹心粉。", "建议冷藏定型。")
        captured = {}

        class FakeStore:
            def search(self, query, **kwargs):
                captured["query"] = query
                captured.update(kwargs)
                return [{
                    "product_id": product.id,
                    "chunk_id": f"product_{product.id}:usage",
                    "name": product.name,
                    "category": product.category,
                    "section": "selling_point",
                    "source_name": "布蕾粉档案.md",
                    "document": "建议冷藏定型。",
                    "distance": 0.08,
                }]

        with patch("vector_store.product_store.ProductVectorStore", return_value=FakeStore()):
            result = product_rag._retrieve_scoped_product_chunks(product, "怎么定型", self.db, limit=8)

        self.assertEqual(captured["product_id_filter"], product.id)
        self.assertEqual(result[0]["chunk_id"], f"product_{product.id}:usage")

    def test_scoped_question_rejects_unrelated_distant_chunks(self):
        from services import product_rag

        product = self._product("布蕾粉", "烘焙夹心", "布蕾蛋糕夹心粉。", "建议冷藏定型。")

        class FakeStore:
            def search(self, query, **kwargs):
                return [{
                    "product_id": product.id,
                    "chunk_id": f"product_{product.id}:usage",
                    "name": product.name,
                    "category": product.category,
                    "section": "selling_point",
                    "source_name": "布蕾粉档案.md",
                    "document": "建议冷藏定型。",
                    "distance": 0.92,
                }]

        with patch("vector_store.product_store.ProductVectorStore", return_value=FakeStore()):
            result = product_rag._retrieve_scoped_product_chunks(
                product,
                "有没有医疗认证",
                self.db,
                limit=8,
            )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
