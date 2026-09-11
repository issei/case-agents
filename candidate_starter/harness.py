"""Pilar 3 — Evaluation Harness (Evals & Benchmarking & Guard Rails)."""
import time
from typing import Dict, List

from common.interfaces import BaseRouter, BaseToolRetriever
from common.mock_llm import (
    COST_RETRIEVAL_USD,
    COST_ROUTER_USD,
    fast_path_answer,
    mock_tool_execution,
    simulate_agent_llm_call,
    simulate_baseline_llm_call,
)
from common.schemas import Tool


def compute_router_metrics(y_true: List[str], y_pred: List[str], labels: List[str]) -> Dict:
    """Calcula a acurácia e a matriz de confusão do router."""
    if not y_true:
        return {"accuracy": 0.0, "confusion_matrix": {}}

    correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    accuracy = correct / len(y_true)

    matrix = {l1: {l2: 0 for l2 in labels} for l1 in labels}
    for yt, yp in zip(y_true, y_pred):
        if yt in matrix and yp in matrix[yt]:
            matrix[yt][yp] += 1

    return {
        "accuracy": float(accuracy),
        "confusion_matrix": matrix,
    }


def compute_precision_at_k(hits: List[int]) -> float:
    """Calcula Precision@K a partir de uma lista de 0/1 (acertou ou não a tool)."""
    if not hits:
        return 0.0
    return float(sum(hits) / len(hits))


def compute_savings(
    smart_cost_usd: float,
    smart_latency_ms: float,
    baseline_cost_usd: float,
    baseline_latency_ms: float,
) -> Dict:
    """Calcula a % de economia de custo e de latência do pipeline inteligente em
    relação ao baseline (mandar tudo pro LLM caro).
    """
    cost_savings = 0.0
    if baseline_cost_usd > 0:
        cost_savings = ((baseline_cost_usd - smart_cost_usd) / baseline_cost_usd) * 100.0

    latency_savings = 0.0
    if baseline_latency_ms > 0:
        latency_savings = ((baseline_latency_ms - smart_latency_ms) / baseline_latency_ms) * 100.0

    return {
        "cost_savings_pct": float(cost_savings),
        "latency_savings_pct": float(latency_savings),
    }


def run_harness(
    router: BaseRouter,
    retriever: BaseToolRetriever,
    tools: List[Tool],
    eval_dataset: List[dict],
    k: int = 2,
) -> dict:
    labels = ["FAST_PATH", "AGENT"]

    y_true: List[str] = []
    y_pred: List[str] = []
    precision_hits: List[int] = []

    smart_cost_total = 0.0
    smart_latency_ms_total = 0.0
    baseline_cost_total = 0.0
    baseline_latency_ms_total = 0.0

    abstentions = 0
    rows = []

    for item in eval_dataset:
        query = item["query"]
        expected_route = item["expected_route"]
        expected_tool = item.get("expected_tool")

        route_result = router.predict(query)
        y_true.append(expected_route)
        y_pred.append(route_result.route)

        smart_cost = COST_ROUTER_USD
        smart_latency_ms = route_result.latency_ms

        row = {
            "query": query,
            "expected_route": expected_route,
            "predicted_route": route_result.route,
            "confidence": route_result.confidence,
            "final_status": route_result.route,
        }

        # Guard Rail 1: Router confidence >= 0.75
        confidence = route_result.confidence if route_result.confidence is not None else 1.0
        if confidence < 0.75:
            row["final_status"] = "HUMAN_FALLBACK_LOW_CONFIDENCE"
            abstentions += 1
        elif route_result.route == "FAST_PATH":
            fast_path_answer(query)
        else:
            retrieval_result = retriever.search(query, k=k)
            smart_cost += COST_RETRIEVAL_USD
            smart_latency_ms += retrieval_result.latency_ms

            top_k_matches = retrieval_result.matches
            top_k_names = [m.name for m in top_k_matches]
            row["retrieved_tools"] = top_k_names
            row["expected_tool"] = expected_tool

            if expected_tool:
                precision_hits.append(int(expected_tool in top_k_names))

            # Guard Rail 2: Top-1 score >= 0.10
            top1_score = top_k_matches[0].score if top_k_matches else 0.0
            if top1_score < 0.10:
                row["final_status"] = "ABSTAIN_LOW_SCORE"
                abstentions += 1
            else:
                # Guard Rail 3: Margin relative >= 0.25
                top2_score = top_k_matches[1].score if len(top_k_matches) > 1 else 0.0
                margin = (top1_score - top2_score) / top1_score if top1_score > 0 else 0.0
                if margin < 0.25:
                    row["final_status"] = "AMBIGUOUS_CONFIRMATION"
                    abstentions += 1
                else:
                    # Executa a tool top-1
                    mock_tool_execution(top_k_names[0], query)
                    llm_result = simulate_agent_llm_call(query, top_k_names[0])
                    smart_cost += llm_result["cost_usd"]

        smart_cost_total += smart_cost
        smart_latency_ms_total += smart_latency_ms

        baseline_start = time.perf_counter()
        baseline_result = simulate_baseline_llm_call(query)
        baseline_latency_ms_total += (time.perf_counter() - baseline_start) * 1000
        baseline_cost_total += baseline_result["cost_usd"]

        rows.append(row)

    router_metrics = compute_router_metrics(y_true, y_pred, labels)
    precision_at_k = compute_precision_at_k(precision_hits) if precision_hits else None
    savings = compute_savings(
        smart_cost_total, smart_latency_ms_total, baseline_cost_total, baseline_latency_ms_total
    )

    report = {
        "n_queries": len(eval_dataset),
        "router_accuracy": router_metrics["accuracy"],
        "confusion_matrix": router_metrics["confusion_matrix"],
        "precision_at_k": precision_at_k,
        "k": k,
        "abstention_count": abstentions,
        "abstention_rate": abstentions / len(eval_dataset) if eval_dataset else 0.0,
        "smart_pipeline": {"total_cost_usd": smart_cost_total, "total_latency_ms": smart_latency_ms_total},
        "baseline_always_llm": {
            "total_cost_usd": baseline_cost_total,
            "total_latency_ms": baseline_latency_ms_total,
        },
        **savings,
        "rows": rows,
    }
    return report


def print_report(report: dict) -> None:
    print("=" * 60)
    print("HARNESS DE AVALIAÇÃO - Router & Tool Retrieval")
    print("=" * 60)
    print(f"Queries avaliadas: {report['n_queries']}")
    print(f"Acurácia do Router: {report['router_accuracy']:.1%}")
    print(f"Matriz de confusão: {report['confusion_matrix']}")
    if report["precision_at_k"] is not None:
        print(f"Precision@{report['k']} do Retriever: {report['precision_at_k']:.1%}")
    print(f"Abstenções/Fallbacks: {report.get('abstention_count', 0)} ({report.get('abstention_rate', 0.0):.1%})")
    print("-" * 60)
    print(f"Custo pipeline inteligente: ${report['smart_pipeline']['total_cost_usd']:.5f}")
    print(f"Custo baseline (tudo pro LLM): ${report['baseline_always_llm']['total_cost_usd']:.5f}")
    print(f"Economia de custo: {report.get('cost_savings_pct', 0):.1f}%")
    print(f"Latência pipeline inteligente: {report['smart_pipeline']['total_latency_ms']:.1f} ms")
    print(f"Latência baseline: {report['baseline_latency_ms'] if 'baseline_latency_ms' in report else report['baseline_always_llm']['total_latency_ms']:.1f} ms")
    print(f"Economia de latência: {report.get('latency_savings_pct', 0):.1f}%")
    print("=" * 60)
