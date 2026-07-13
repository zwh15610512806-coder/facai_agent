"""Run the offline product retrieval benchmark without writing query logs."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import SessionLocal
from services.product_rag import (
    _retrieve_product_selection,
    retrieve_product_pipeline_for_evaluation,
)
from services.product_rag_evaluation import (
    evaluate_retrieval_cases,
    evaluate_pipeline_cases_async,
    load_product_rag_benchmark,
)


DEFAULT_BENCHMARK = ROOT / "tests" / "fixtures" / "product_rag_benchmark.json"


async def _run(args) -> dict:
    cases = load_product_rag_benchmark(args.benchmark)
    if args.max_cases > 0:
        cases = cases[:args.max_cases]
    db = SessionLocal()
    try:
        if args.initial_only:
            def retrieve(query: str, limit: int):
                return _retrieve_product_selection(query, db, limit).products

            report = evaluate_retrieval_cases(cases, retrieve)
            report["pipeline_stage"] = "exact+bm25+vector+rrf"
        else:
            async def retrieve(query: str, limit: int):
                return await retrieve_product_pipeline_for_evaluation(
                    query,
                    db,
                    limit=limit,
                )

            report = await evaluate_pipeline_cases_async(cases, retrieve)
            report["pipeline_stage"] = "exact+bm25+vector+rrf+llm_rerank"
        report["benchmark"] = str(args.benchmark)
        return report
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate product RAG retrieval quality")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--initial-only", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(_run(args))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
