"""Barreira de segurança pré-execução e critérios de aceite do benchmark oficial.

Os testes de guarda provam a invariante central do domínio bancário: `mock_tool_execution`
NUNCA é chamada quando um dos três guardas reprova. São testes de ausência de efeito, não
de métrica — é o que separa "recuperou mal" de "executou a operação errada na conta".
"""
import unittest.mock as mock

import pytest

from candidate_starter.harness import (
    MIN_RELATIVE_MARGIN,
    RETRIEVER_MIN_SCORE,
    ROUTER_CONFIDENCE_THRESHOLD,
    TASK_SUCCESS_RATE_THRESHOLD,
    run_harness,
)
from candidate_starter.retrieval import ToolRetriever
from candidate_starter.router import QueryRouter
from common.data_loader import load_eval_dataset, load_router_training_data, load_tools
from common.interfaces import BaseRouter, BaseToolRetriever
from common.schemas import RetrievalResult, RouteResult, ToolMatch


class _Router(BaseRouter):
    def __init__(self, confidence):
        self.confidence = confidence

    def fit(self, texts, labels):
        return self

    def predict(self, query):
        return RouteResult(route="AGENT", latency_ms=1.0, confidence=self.confidence)


class _Retriever(BaseToolRetriever):
    def __init__(self, matches):
        self.matches = matches

    def fit(self, tools):
        return self

    def search(self, query, k=2):
        return RetrievalResult(matches=list(self.matches), latency_ms=1.0)


ONE_QUERY = [{"query": "quero mexer na minha conta", "expected_route": "AGENT",
              "expected_tool": "tool_a"}]


def _run(router, retriever, k=2):
    with mock.patch("candidate_starter.harness.mock_tool_execution") as executed:
        report = run_harness(router, retriever, [], ONE_QUERY, k=k)
    return report, executed


# ── GUARDA 1: confiança do router ────────────────────────────────────────────

def test_low_router_confidence_never_executes_a_tool():
    router = _Router(ROUTER_CONFIDENCE_THRESHOLD - 0.01)
    retriever = _Retriever([ToolMatch(name="tool_a", score=0.99)])

    report, executed = _run(router, retriever)

    executed.assert_not_called()
    assert report["rows"][0]["execution_status"] == "HUMAN_FALLBACK_LOW_CONFIDENCE"
    assert report["human_fallbacks"] == 1
    assert report["coverage_rate"] == 0.0


# ── GUARDA 2: score mínimo do retriever ──────────────────────────────────────

def test_empty_retrieval_never_executes_a_tool():
    """Retriever sem candidato acima de min_score -> abstenção, nunca execução."""
    report, executed = _run(_Router(0.99), _Retriever([]))

    executed.assert_not_called()
    assert report["rows"][0]["execution_status"] == "ABSTAIN_LOW_SCORE"
    assert report["abstentions"] == 1


def test_min_score_filters_candidates_before_the_harness_sees_them():
    """A abstenção nasce no retriever: com min_score alto, `matches` já chega vazio."""
    retriever = ToolRetriever(min_score=0.99, use_taxonomy=True).fit(load_tools())
    assert retriever.search("Quero saber meu saldo", k=2).matches == []
    # Sanidade do limiar de produção: o mesmo pedido passa com RETRIEVER_MIN_SCORE.
    permissive = ToolRetriever(min_score=RETRIEVER_MIN_SCORE, use_taxonomy=True).fit(load_tools())
    assert permissive.search("Quero saber meu saldo", k=2).matches


# ── GUARDA 3: margem entre candidatos ────────────────────────────────────────

def test_low_margin_requires_confirmation_instead_of_executing():
    """Empate entre top-1 e top-2 é confirmação do cliente, não execução otimista."""
    retriever = _Retriever(
        [ToolMatch(name="tool_wrong", score=0.50), ToolMatch(name="tool_a", score=0.49)]
    )
    report, executed = _run(_Router(0.99), retriever)

    executed.assert_not_called()
    row = report["rows"][0]
    assert row["execution_status"] == "AMBIGUOUS_CONFIRMATION"
    assert row["relative_margin"] < MIN_RELATIVE_MARGIN
    assert report["ambiguous_confirmations"] == 1
    assert report["incorrect_executions"] == 0, (
        "Um empate desviado para confirmação não pode ser contado como execução incorreta"
    )


def test_sufficient_margin_executes():
    """Contraprova: com margem folgada o pipeline executa normalmente."""
    retriever = _Retriever(
        [ToolMatch(name="tool_a", score=0.90), ToolMatch(name="tool_b", score=0.10)]
    )
    report, executed = _run(_Router(0.99), retriever)

    executed.assert_called_once()
    assert report["rows"][0]["execution_status"] == "SUCCESS"


def test_single_candidate_has_no_margin_and_still_executes():
    """Com um único candidato não há empate a resolver — a guarda 3 não se aplica."""
    report, executed = _run(_Router(0.99), _Retriever([ToolMatch(name="tool_a", score=0.4)]), k=1)

    executed.assert_called_once()
    assert report["rows"][0]["relative_margin"] is None
    assert report["rows"][0]["execution_status"] == "SUCCESS"


# ── Benchmark oficial: critérios de aceite ───────────────────────────────────

@pytest.fixture(scope="module")
def official_report():
    tools = load_tools()
    texts, labels = load_router_training_data()
    router = QueryRouter().fit(texts, labels)
    retriever = ToolRetriever(min_score=RETRIEVER_MIN_SCORE, use_taxonomy=True).fit(tools)
    return run_harness(router, retriever, tools, load_eval_dataset(), k=2)


def test_official_benchmark_meets_acceptance_criteria(official_report):
    """Critérios de aceite da FASE 7 — limiares, não um snapshot congelado."""
    assert official_report["router_accuracy"] == 1.0
    assert official_report["retrieval_hit_rate_at_k"] >= 0.80
    assert official_report["task_success_rate"] >= TASK_SUCCESS_RATE_THRESHOLD
    assert official_report["incorrect_executions"] == 0
    assert official_report["production_approved"] is True


def test_official_benchmark_report_carries_the_full_metric_contract(official_report):
    for field in (
        "operational_status", "production_approved", "quality_gate_reasons",
        "task_success_rate", "incorrect_execution_rate", "abstention_rate",
        "coverage_rate", "retrieval_hit_rate_at_1", "retrieval_hit_rate_at_k",
        "precision_at_k", "cost_savings_pct", "economics",
    ):
        assert field in official_report, f"Campo obrigatório ausente do relatório: {field}"


def test_pipeline_decisions_are_reproducible():
    """Duas construções independentes produzem exatamente as mesmas decisões.

    Cobre reprodutibilidade sem repagar os `sleep` dos mocks de LLM: o que precisa ser
    determinístico é a decisão (rota, confiança, ranking), não a latência simulada.
    """
    tools = load_tools()
    texts, labels = load_router_training_data()
    queries = [d["query"] for d in load_eval_dataset()]

    def decisions():
        router = QueryRouter().fit(texts, labels)
        retriever = ToolRetriever(min_score=RETRIEVER_MIN_SCORE).fit(tools)
        out = []
        for q in queries:
            route = router.predict(q)
            names = [(m.name, round(m.score, 12)) for m in retriever.search(q, k=2).matches]
            out.append((route.route, round(route.confidence, 12), names))
        return out

    assert decisions() == decisions()
