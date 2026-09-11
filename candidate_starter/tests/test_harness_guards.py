from candidate_starter.harness import (
    compute_precision_at_k,
    compute_router_metrics,
    compute_savings,
    run_harness,
)
from common.schemas import RetrievalResult, RouteResult, ToolMatch


class DummyRouterLowConf:
    def predict(self, query: str):
        return RouteResult(route="AGENT", latency_ms=1.0, confidence=0.50)


class DummyRouterHighConf:
    def predict(self, query: str):
        return RouteResult(route="AGENT", latency_ms=1.0, confidence=0.90)


class DummyRetrieverLowScore:
    def search(self, query: str, k: int = 2):
        return RetrievalResult(
            matches=[ToolMatch(name="tool_a", score=0.05), ToolMatch(name="tool_b", score=0.01)],
            latency_ms=1.0,
        )


class DummyRetrieverLowMargin:
    def search(self, query: str, k: int = 2):
        return RetrievalResult(
            matches=[ToolMatch(name="tool_a", score=0.80), ToolMatch(name="tool_b", score=0.70)],
            latency_ms=1.0,
        )


class DummyRetrieverValid:
    def search(self, query: str, k: int = 2):
        return RetrievalResult(
            matches=[ToolMatch(name="tool_a", score=0.80), ToolMatch(name="tool_b", score=0.20)],
            latency_ms=1.0,
        )


def test_compute_router_metrics():
    y_true = ["FAST_PATH", "AGENT", "AGENT"]
    y_pred = ["FAST_PATH", "AGENT", "FAST_PATH"]
    labels = ["FAST_PATH", "AGENT"]
    metrics = compute_router_metrics(y_true, y_pred, labels)

    assert abs(metrics["accuracy"] - 2 / 3) < 1e-5
    assert metrics["confusion_matrix"]["FAST_PATH"]["FAST_PATH"] == 1
    assert metrics["confusion_matrix"]["AGENT"]["FAST_PATH"] == 1


def test_compute_precision_at_k():
    assert compute_precision_at_k([1, 1, 0, 1]) == 0.75


def test_compute_savings():
    savings = compute_savings(20.0, 100.0, 100.0, 500.0)
    assert savings["cost_savings_pct"] == 80.0
    assert savings["latency_savings_pct"] == 80.0


def test_guard_rail_low_confidence():
    eval_dataset = [{"query": "test", "expected_route": "AGENT", "expected_tool": "tool_a"}]
    report = run_harness(
        router=DummyRouterLowConf(),
        retriever=DummyRetrieverValid(),
        tools=[],
        eval_dataset=eval_dataset,
    )
    assert report["rows"][0]["final_status"] == "HUMAN_FALLBACK_LOW_CONFIDENCE"


def test_guard_rail_low_score():
    eval_dataset = [{"query": "test", "expected_route": "AGENT", "expected_tool": "tool_a"}]
    report = run_harness(
        router=DummyRouterHighConf(),
        retriever=DummyRetrieverLowScore(),
        tools=[],
        eval_dataset=eval_dataset,
    )
    assert report["rows"][0]["final_status"] == "ABSTAIN_LOW_SCORE"


def test_guard_rail_low_margin():
    eval_dataset = [{"query": "test", "expected_route": "AGENT", "expected_tool": "tool_a"}]
    report = run_harness(
        router=DummyRouterHighConf(),
        retriever=DummyRetrieverLowMargin(),
        tools=[],
        eval_dataset=eval_dataset,
    )
    assert report["rows"][0]["final_status"] == "AMBIGUOUS_CONFIRMATION"
