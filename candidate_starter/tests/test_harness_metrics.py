"""Testes unitários das funções de cálculo de métricas do harness."""
import pytest

from candidate_starter.harness import (
    compute_precision_at_k,
    compute_router_metrics,
    compute_savings,
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
