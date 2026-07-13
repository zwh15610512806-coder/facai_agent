import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tests" / "fixtures" / "product_rag_benchmark.json"


class ProductRagEvaluationTests(unittest.TestCase):
    def test_benchmark_expands_to_at_least_120_curated_queries(self):
        from services.product_rag_evaluation import load_product_rag_benchmark

        cases = load_product_rag_benchmark(BENCHMARK)
        queries = {case.query for case in cases}

        self.assertGreaterEqual(len(cases), 120)
        self.assertIn("布蕾粉价格", queries)
        self.assertIn("适合淋面的产品有哪些？", queries)
        self.assertIn("有哪些低糖产品？", queries)
        self.assertIn("有哪些适合蛋糕夹心的产品？", queries)
        self.assertTrue(any(case.allow_no_answer for case in cases))

    def test_evaluator_reports_retrieval_and_no_answer_metrics(self):
        from services.product_rag_evaluation import BenchmarkCase, evaluate_retrieval_cases

        cases = [
            BenchmarkCase(
                group="entity",
                query="布蕾粉价格",
                expected=("布蕾粉",),
                excluded=("夹心果泥",),
            ),
            BenchmarkCase(
                group="no_answer",
                query="有没有完全不存在的产品",
                expected=(),
                excluded=(),
                allow_no_answer=True,
            ),
        ]

        def retrieve(query, limit):
            if query == "布蕾粉价格":
                return ["布蕾粉", "奶冻粉"]
            return []

        report = evaluate_retrieval_cases(cases, retrieve)

        self.assertEqual(report["case_count"], 2)
        self.assertEqual(report["hit_at_1"], 1.0)
        self.assertEqual(report["recall_at_30"], 1.0)
        self.assertEqual(report["exclusion_violation_rate"], 0.0)
        self.assertEqual(report["no_answer_false_positive_rate"], 0.0)
        self.assertGreater(report["precision_at_10"], 0)


class ProductRagAsyncEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_evaluator_uses_ranked_results(self):
        from services.product_rag_evaluation import (
            BenchmarkCase,
            evaluate_retrieval_cases_async,
        )

        cases = [BenchmarkCase(
            group="entity",
            query="布蕾粉价格",
            expected=("布蕾粉",),
        )]

        async def retrieve(query, limit):
            return ["布蕾粉"]

        report = await evaluate_retrieval_cases_async(cases, retrieve)

        self.assertEqual(report["hit_at_1"], 1.0)
        self.assertGreaterEqual(report["retrieval_latency_p95_ms"], 0)

    async def test_pipeline_evaluator_splits_initial_recall_from_final_precision(self):
        from services.product_rag_evaluation import (
            BenchmarkCase,
            evaluate_pipeline_cases_async,
        )

        cases = [BenchmarkCase(
            group="selection",
            query="调色产品",
            expected=("水性色素", "油性色素"),
            excluded=("手绘膏",),
        )]

        async def retrieve(query, limit):
            return {
                "initial_products": ["水性色素", "油性色素", "手绘膏"],
                "final_products": ["水性色素", "油性色素"],
            }

        report = await evaluate_pipeline_cases_async(cases, retrieve)

        self.assertEqual(report["recall_at_30"], 1.0)
        self.assertEqual(report["precision_at_10"], 1.0)
        self.assertEqual(report["exclusion_violation_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
