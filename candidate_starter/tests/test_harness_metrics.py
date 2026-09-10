"""Testes unitários das funções de cálculo de métricas do harness."""
import pytest

from candidate_starter.harness import (
    READINESS_INSUFFICIENT_EVIDENCE,
    READINESS_MVP_BENCHMARK,
    READINESS_NOT_APPROVED,
    compute_fallback_economics,
    compute_precision_at_k,
    compute_router_metrics,
    compute_savings,
    _evaluate_quality_gate,
)


def test_compute_router_metrics_standard():
    y_true = ["FAST_PATH", "FAST_PATH", "AGENT", "AGENT"]
    y_pred = ["FAST_PATH", "AGENT", "AGENT", "AGENT"]
    labels = ["FAST_PATH", "AGENT"]

    metrics = compute_router_metrics(y_true, y_pred, labels)
    assert metrics["accuracy"] == 0.75
    assert metrics["confusion_matrix"] == {
        "FAST_PATH": {"FAST_PATH": 1, "AGENT": 1},
        "AGENT": {"FAST_PATH": 0, "AGENT": 2},
    }


def test_compute_router_metrics_empty():
    metrics = compute_router_metrics([], [], ["FAST_PATH", "AGENT"])
    assert metrics["accuracy"] == 0.0
    assert metrics["confusion_matrix"] == {
        "FAST_PATH": {"FAST_PATH": 0, "AGENT": 0},
        "AGENT": {"FAST_PATH": 0, "AGENT": 0},
    }


def test_compute_precision_at_k():
    assert compute_precision_at_k([1, 1, 0, 1]) == 0.75
    assert compute_precision_at_k([0, 0]) == 0.0
    assert compute_precision_at_k([]) == 0.0


def test_compute_savings_standard():
    savings = compute_savings(
        smart_cost_usd=0.01,
        smart_latency_ms=100.0,
        baseline_cost_usd=0.03,
        baseline_latency_ms=200.0,
    )
    assert pytest.approx(savings["cost_savings_pct"], rel=1e-3) == 66.666
    assert pytest.approx(savings["latency_savings_pct"], rel=1e-3) == 50.0


def test_compute_savings_zero_baseline():
    savings = compute_savings(
        smart_cost_usd=0.0,
        smart_latency_ms=0.0,
        baseline_cost_usd=0.0,
        baseline_latency_ms=0.0,
    )
    assert savings["cost_savings_pct"] == 0.0
    assert savings["latency_savings_pct"] == 0.0


# ── Quality Gate ─────────────────────────────────────────────────────────────

def test_quality_gate_approved():
    """Pipeline aprovado quando task_success_rate >= threshold e zero execuções incorretas."""
    qg = _evaluate_quality_gate(task_success_rate=1.0, incorrect_executions=0)
    assert qg["production_approved"] is True
    assert qg["quality_gate_reasons"] == []
    assert "APROVADO" in qg["operational_status"]


def test_quality_gate_fails_on_incorrect_executions():
    """Qualquer execução incorreta reprova o pipeline, independentemente da taxa de sucesso."""
    qg = _evaluate_quality_gate(task_success_rate=0.9, incorrect_executions=1)
    assert qg["production_approved"] is False
    assert any("incorreta" in r.lower() for r in qg["quality_gate_reasons"])
    assert "REPROVADO" in qg["operational_status"]


def test_quality_gate_fails_on_low_task_success_rate():
    """task_success_rate abaixo do threshold reprova o pipeline."""
    qg = _evaluate_quality_gate(task_success_rate=0.5, incorrect_executions=0)
    assert qg["production_approved"] is False
    assert any("execu" in r.lower() for r in qg["quality_gate_reasons"])


def test_quality_gate_fails_on_both():
    """Dois critérios violados geram dois motivos de reprovação."""
    qg = _evaluate_quality_gate(task_success_rate=0.4, incorrect_executions=5)
    assert qg["production_approved"] is False
    assert len(qg["quality_gate_reasons"]) == 2


def test_quality_gate_none_task_success_rate_is_indeterminate():
    """Benchmark sem queries transacionais é INDETERMINADO, nunca aprovado.

    Ausência de evidência não é evidência de segurança: um benchmark que não exercitou
    nenhuma execução de ferramenta não pode aprovar um pipeline bancário.
    """
    qg = _evaluate_quality_gate(task_success_rate=None, incorrect_executions=0)
    assert qg["production_approved"] is False
    assert "INDETERMINADO" in qg["operational_status"]
    assert any("transacion" in r.lower() for r in qg["quality_gate_reasons"])


def test_approval_in_the_benchmark_never_claims_production_readiness():
    """Passar no gate é evidência sobre ESTE benchmark, não sobre operação bancária real.

    O rótulo mais forte que o harness pode emitir é MVP_BENCHMARK_ONLY. Se algum dia esta
    asserção falhar, alguém ampliou a conclusão sem ampliar a evidência.
    """
    approved = _evaluate_quality_gate(task_success_rate=1.0, incorrect_executions=0)
    assert approved["production_approved"] is True
    assert approved["production_readiness"] == READINESS_MVP_BENCHMARK
    assert approved["production_readiness_caveat"].strip()

    rejected = _evaluate_quality_gate(task_success_rate=0.5, incorrect_executions=0)
    assert rejected["production_readiness"] == READINESS_NOT_APPROVED

    indeterminate = _evaluate_quality_gate(task_success_rate=None, incorrect_executions=0)
    assert indeterminate["production_readiness"] == READINESS_INSUFFICIENT_EVIDENCE


# ── Custo líquido com fallback humano ────────────────────────────────────────

def test_fallback_breakeven_is_derived_without_assuming_a_human_cost():
    """Sem premissa de custo, o número publicável é o ponto de equilíbrio."""
    econ = compute_fallback_economics(
        smart_cost_usd=0.20, baseline_cost_usd=0.90, deferred_to_human=7
    )
    # (0.90 - 0.20) / 7 = 0.10 por desvio zera a economia.
    assert pytest.approx(econ["human_fallback_breakeven_cost_usd"], rel=1e-9) == 0.10
    assert econ["human_handling_cost_usd"] is None
    assert econ["net_cost_savings_pct"] is None


def test_fallback_cost_above_breakeven_turns_savings_negative():
    """A economia nominal trata abstenção como grátis; a líquida não. Este é o teste que
    impede o relatório de vender desvio ao humano como eficiência."""
    econ = compute_fallback_economics(
        smart_cost_usd=0.20,
        baseline_cost_usd=0.90,
        deferred_to_human=7,
        human_fallback_cost_usd=0.50,  # bem acima do break-even de 0.10
    )
    assert econ["net_smart_cost_usd"] == pytest.approx(0.20 + 7 * 0.50)
    assert econ["net_cost_savings_pct"] < 0, (
        "Com custo humano acima do ponto de equilíbrio, a economia líquida é negativa"
    )


def test_no_deferral_means_no_breakeven_and_net_equals_nominal():
    econ = compute_fallback_economics(
        smart_cost_usd=0.20,
        baseline_cost_usd=0.90,
        deferred_to_human=0,
        human_fallback_cost_usd=0.50,
    )
    assert econ["human_fallback_breakeven_cost_usd"] is None
    assert econ["net_smart_cost_usd"] == pytest.approx(0.20)


# ── Harness End-to-End ────────────────────────────────────────────────────────

def test_run_harness_human_fallback_low_confidence():
    """Com confiança abaixo do limiar, o harness desvia para HUMAN_FALLBACK sem executar tool."""
    from common.interfaces import BaseRouter, BaseToolRetriever
    from common.schemas import RetrievalResult, RouteResult, ToolMatch
    from candidate_starter.harness import run_harness
    import unittest.mock as mock

    class LowConfidenceRouter(BaseRouter):
        def fit(self, texts, labels): return self
        def predict(self, query):
            return RouteResult(route="AGENT", latency_ms=1.0, confidence=0.50)

    class DummyRetriever(BaseToolRetriever):
        def fit(self, tools): return self
        def search(self, query, k=2):
            return RetrievalResult(matches=[ToolMatch(name="tool_a", score=0.9)], latency_ms=1.0)

    eval_data = [
        {"query": "query ambigua", "expected_route": "AGENT", "expected_tool": "tool_a"},
    ]

    with mock.patch("candidate_starter.harness.mock_tool_execution") as mock_exec:
        rep = run_harness(LowConfidenceRouter(), DummyRetriever(), [], eval_data, k=1)
        # Tool NÃO deve ter sido executada
        mock_exec.assert_not_called()

    assert rep["abstentions"] == 1
    assert rep["human_fallbacks"] == 1
    assert rep["correct_executions"] == 0
    assert rep["rows"][0]["execution_status"] == "HUMAN_FALLBACK_LOW_CONFIDENCE"


def test_run_harness_execution_metrics():
    """Valida métricas de execução segura e abstention no harness com confidence alta."""
    from common.interfaces import BaseRouter, BaseToolRetriever
    from common.schemas import RetrievalResult, RouteResult, ToolMatch
    from candidate_starter.harness import run_harness

    class HighConfidenceRouter(BaseRouter):
        def fit(self, texts, labels): return self
        def predict(self, query):
            return RouteResult(route="AGENT", latency_ms=1.0, confidence=0.90)

    class DummyRetriever(BaseToolRetriever):
        def fit(self, tools): return self
        def search(self, query, k=2):
            if "abstain" in query:
                return RetrievalResult(matches=[], latency_ms=1.0)
            if "correct" in query:
                return RetrievalResult(matches=[ToolMatch(name="tool_a", score=0.9)], latency_ms=1.0)
            return RetrievalResult(matches=[ToolMatch(name="tool_wrong", score=0.9)], latency_ms=1.0)

    eval_data = [
        {"query": "correct query", "expected_route": "AGENT", "expected_tool": "tool_a"},
        {"query": "wrong query", "expected_route": "AGENT", "expected_tool": "tool_b"},
        {"query": "abstain query", "expected_route": "AGENT", "expected_tool": "tool_c"},
    ]

    rep = run_harness(HighConfidenceRouter(), DummyRetriever(), [], eval_data, k=1)
    assert rep["correct_executions"] == 1
    assert rep["incorrect_executions"] == 1
    assert rep["abstentions"] == 1
    assert pytest.approx(rep["task_success_rate"], rel=1e-3) == 1 / 3
    # Com 1 execução incorreta, o Quality Gate deve reprovar
    assert rep["production_approved"] is False
