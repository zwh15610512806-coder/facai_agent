"""Offline benchmark loading and deterministic retrieval metrics."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Awaitable, Callable, Iterable


@dataclass(frozen=True)
class BenchmarkCase:
    group: str
    query: str
    expected: tuple[str, ...]
    excluded: tuple[str, ...] = ()
    allow_no_answer: bool = False


def load_product_rag_benchmark(path: Path | str) -> list[BenchmarkCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases: list[BenchmarkCase] = []
    for group in payload.get("groups") or []:
        expected = tuple(str(value) for value in group.get("expected") or [])
        excluded = tuple(str(value) for value in group.get("excluded") or [])
        allow_no_answer = bool(group.get("allow_no_answer"))
        for query_item in group.get("queries") or []:
            if isinstance(query_item, dict):
                text = str(query_item.get("query") or "").strip()
                case_expected = tuple(str(value) for value in query_item.get("expected", expected) or [])
                case_excluded = tuple(str(value) for value in query_item.get("excluded", excluded) or [])
                case_allow_no_answer = bool(query_item.get("allow_no_answer", allow_no_answer))
            else:
                text = str(query_item or "").strip()
                case_expected = expected
                case_excluded = excluded
                case_allow_no_answer = allow_no_answer
            if not text:
                continue
            cases.append(BenchmarkCase(
                group=str(group.get("name") or "default"),
                query=text,
                expected=case_expected,
                excluded=case_excluded,
                allow_no_answer=case_allow_no_answer,
            ))
    return cases


def _result_names(values: Iterable) -> list[str]:
    names = []
    for value in values:
        if isinstance(value, dict):
            name = value.get("name")
        else:
            name = getattr(value, "name", value)
        text = str(name or "").strip()
        if text and text not in names:
            names.append(text)
    return names


def evaluate_retrieval_cases(
    cases: list[BenchmarkCase],
    retrieve: Callable[[str, int], Iterable],
) -> dict:
    hit_values = []
    precision_values = []
    recall_values = []
    exclusion_violations = 0
    exclusion_checks = 0
    no_answer_false_positives = 0
    no_answer_cases = 0
    latencies_ms = []
    group_scores: dict[str, dict[str, int]] = {}
    for case in cases:
        started = time.perf_counter()
        names = _result_names(retrieve(case.query, 30))
        latencies_ms.append((time.perf_counter() - started) * 1000)
        top_10 = names[:10]
        top_30 = names[:30]
        expected = set(case.expected)
        excluded = set(case.excluded)
        group = group_scores.setdefault(case.group, {"cases": 0, "hit_at_1": 0})
        group["cases"] += 1
        if expected:
            hit = bool(top_30 and top_30[0] in expected)
            hit_values.append(1.0 if hit else 0.0)
            if hit:
                group["hit_at_1"] += 1
            precision_values.append(
                len(expected.intersection(top_10)) / max(1, len(top_10))
            )
            recall_values.append(len(expected.intersection(top_30)) / len(expected))
        if excluded:
            exclusion_checks += 1
            if excluded.intersection(top_30):
                exclusion_violations += 1
        if case.allow_no_answer:
            no_answer_cases += 1
            if names:
                no_answer_false_positives += 1
    sorted_latency = sorted(latencies_ms)
    p95_index = max(0, int(len(sorted_latency) * 0.95) - 1)
    return {
        "case_count": len(cases),
        "hit_at_1": round(sum(hit_values) / len(hit_values), 4) if hit_values else 0.0,
        "precision_at_10": round(sum(precision_values) / len(precision_values), 4) if precision_values else 0.0,
        "recall_at_30": round(sum(recall_values) / len(recall_values), 4) if recall_values else 0.0,
        "context_precision": round(sum(precision_values) / len(precision_values), 4) if precision_values else 0.0,
        "exclusion_violation_rate": round(exclusion_violations / exclusion_checks, 4) if exclusion_checks else 0.0,
        "no_answer_false_positive_rate": round(no_answer_false_positives / no_answer_cases, 4) if no_answer_cases else 0.0,
        "retrieval_latency_p95_ms": round(sorted_latency[p95_index], 2) if sorted_latency else 0.0,
        "groups": group_scores,
    }


async def evaluate_retrieval_cases_async(
    cases: list[BenchmarkCase],
    retrieve: Callable[[str, int], Awaitable[Iterable]],
) -> dict:
    """Evaluate an async full retrieval pipeline while preserving real latency."""
    cached_names: dict[str, list[str]] = {}
    latencies_ms: list[float] = []
    for case in cases:
        started = time.perf_counter()
        cached_names[case.query] = _result_names(await retrieve(case.query, 30))
        latencies_ms.append((time.perf_counter() - started) * 1000)
    report = evaluate_retrieval_cases(
        cases,
        lambda query, limit: cached_names.get(query, [])[:limit],
    )
    sorted_latency = sorted(latencies_ms)
    p95_index = max(0, int(len(sorted_latency) * 0.95) - 1)
    report["retrieval_latency_p95_ms"] = (
        round(sorted_latency[p95_index], 2) if sorted_latency else 0.0
    )
    return report


async def evaluate_pipeline_cases_async(
    cases: list[BenchmarkCase],
    retrieve: Callable[[str, int], Awaitable[dict]],
) -> dict:
    """Score initial Recall@30 and final reranked precision/no-answer separately."""
    initial_names: dict[str, list[str]] = {}
    final_names: dict[str, list[str]] = {}
    latencies_ms: list[float] = []
    for case in cases:
        started = time.perf_counter()
        pipeline = await retrieve(case.query, 30)
        latencies_ms.append((time.perf_counter() - started) * 1000)
        initial_names[case.query] = _result_names(pipeline.get("initial_products") or [])
        final_names[case.query] = _result_names(pipeline.get("final_products") or [])

    initial = evaluate_retrieval_cases(
        cases,
        lambda query, limit: initial_names.get(query, [])[:limit],
    )
    final = evaluate_retrieval_cases(
        cases,
        lambda query, limit: final_names.get(query, [])[:limit],
    )
    sorted_latency = sorted(latencies_ms)
    p95_index = max(0, int(len(sorted_latency) * 0.95) - 1)
    latency_p95 = round(sorted_latency[p95_index], 2) if sorted_latency else 0.0
    return {
        "case_count": len(cases),
        "hit_at_1": final["hit_at_1"],
        "precision_at_10": final["precision_at_10"],
        "recall_at_30": initial["recall_at_30"],
        "context_precision": final["context_precision"],
        "exclusion_violation_rate": final["exclusion_violation_rate"],
        "no_answer_false_positive_rate": final["no_answer_false_positive_rate"],
        "retrieval_latency_p95_ms": latency_p95,
        "groups": final["groups"],
        "initial_stage": initial,
        "final_stage": final,
    }
