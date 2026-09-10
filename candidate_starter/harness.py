"""Pilar 3 — Evaluation Harness (Evals & Benchmarking).

A orquestração do pipeline (rodar o router, a seleção de tools e os mocks de LLM/tool) já
está feita em `run_harness`. O que falta implementar são as MÉTRICAS do relatório final:

  1. Acurácia do Router (+ matriz de confusão).
  2. Precision@K do Retriever de Tools (a tool certa estava no Top-K?).
  3. Economia de custo e latência do pipeline "inteligente" (router + seleção de tools)
     comparado ao baseline de mandar tudo para o LLM mais caro.

Preencha as funções marcadas com TODO. Respeite o formato de retorno pedido em cada
docstring, pois `run_harness` e `print_report` dependem dessas chaves.
"""
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
    """Calcule a acurácia e a matriz de confusão do router."""
    total = len(y_true)
    if total == 0:
        accuracy = 0.0
    else:
        correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
        accuracy = float(correct / total)

    matrix = {true_lbl: {pred_lbl: 0 for pred_lbl in labels} for true_lbl in labels}
    for yt, yp in zip(y_true, y_pred):
        if yt in matrix and yp in matrix[yt]:
            matrix[yt][yp] += 1

    return {
        "accuracy": accuracy,
        "confusion_matrix": matrix,
    }


def compute_precision_at_k(hits: List[int]) -> float:
    """Calcule Precision@K / Hit Rate a partir de uma lista de 0/1 (acertou ou não a tool).
    
    Nota metrológica: No contexto deste benchmark (uma única ferramenta relevante
    esperada por query), esta métrica quantifica o Hit Rate (Recall@1-in-K).
    """
    if not hits:
        return 0.0
    return float(sum(hits) / len(hits))


def compute_savings(
    smart_cost_usd: float,
    smart_latency_ms: float,
    baseline_cost_usd: float,
    baseline_latency_ms: float,
) -> Dict:
    """Calcule a % de economia de custo e de latência do pipeline inteligente em
    relação ao baseline (mandar tudo pro LLM caro).
    """
    cost_savings_pct = (
        ((baseline_cost_usd - smart_cost_usd) / baseline_cost_usd) * 100.0
        if baseline_cost_usd > 0
        else 0.0
    )
    latency_savings_pct = (
        ((baseline_latency_ms - smart_latency_ms) / baseline_latency_ms) * 100.0
        if baseline_latency_ms > 0
        else 0.0
    )
    return {
        "cost_savings_pct": cost_savings_pct,
        "latency_savings_pct": latency_savings_pct,
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

    correct_executions = 0
    incorrect_executions = 0
    abstentions = 0
    agent_queries_with_expected_tool = 0

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
        }

        if route_result.route == "FAST_PATH":
            fast_path_answer(query)
            row["execution_status"] = "RESOLVED_LOCAL"
        else:
            retrieval_result = retriever.search(query, k=k)
            smart_cost += COST_RETRIEVAL_USD
            smart_latency_ms += retrieval_result.latency_ms

            top_k_names = [m.name for m in retrieval_result.matches]
            if expected_tool:
                agent_queries_with_expected_tool += 1
                precision_hits.append(int(expected_tool in top_k_names))

            row["retrieved_tools"] = top_k_names
            row["expected_tool"] = expected_tool

            if top_k_names:
                chosen_tool = top_k_names[0]
                mock_tool_execution(chosen_tool, query)
                llm_result = simulate_agent_llm_call(query, chosen_tool)
                smart_cost += llm_result["cost_usd"]

                if expected_tool:
                    if chosen_tool == expected_tool:
                        correct_executions += 1
                        row["execution_status"] = "SUCCESS"
                    else:
                        incorrect_executions += 1
                        row["execution_status"] = "INCORRECT_TOOL_EXECUTED"
                else:
                    row["execution_status"] = "EXECUTED_NO_EXPECTED_TOOL"
            else:
                abstentions += 1
                row["execution_status"] = "ABSTAIN_FALLBACK"

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

    task_success_rate = (
        float(correct_executions / agent_queries_with_expected_tool)
        if agent_queries_with_expected_tool > 0
        else None
    )

    report = {
        "n_queries": len(eval_dataset),
        "router_accuracy": router_metrics["accuracy"],
        "confusion_matrix": router_metrics["confusion_matrix"],
        "precision_at_k": precision_at_k,
        "k": k,
        "task_success_rate": task_success_rate,
        "correct_executions": correct_executions,
        "incorrect_executions": incorrect_executions,
        "abstentions": abstentions,
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
        print(f"Precision@{report['k']} do Retriever (Hit Rate): {report['precision_at_k']:.1%}")
    if report.get("task_success_rate") is not None:
        print(f"Taxa de Execução Correta (Top-1 Match): {report['task_success_rate']:.1%}")
        print(f"Execuções com Tool Incorreta (Risco): {report.get('incorrect_executions', 0)}")
        print(f"Abstentions (Fallback Seguro): {report.get('abstentions', 0)}")
    print("-" * 60)
    print(f"Custo pipeline inteligente: ${report['smart_pipeline']['total_cost_usd']:.5f}")
    print(f"Custo baseline (tudo pro LLM): ${report['baseline_always_llm']['total_cost_usd']:.5f}")
    print(f"Economia de custo: {report.get('cost_savings_pct', 0):.1f}%")
    print(f"Latência pipeline inteligente: {report['smart_pipeline']['total_latency_ms']:.1f} ms")
    print(f"Latência baseline: {report['baseline_always_llm']['total_latency_ms']:.1f} ms")
    print(f"Economia de latência: {report.get('latency_savings_pct', 0):.1f}%")
    print("=" * 60)
