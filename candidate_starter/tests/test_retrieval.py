"""Testes unitários completos do ToolRetriever."""
import pytest

from candidate_starter.retrieval import ToolRetriever
from common.schemas import Tool


TOOLS = [
    Tool(name="consultar_saldo", description="Consulta o saldo da conta", category="conta"),
    Tool(name="bloquear_cartao", description="Bloqueia o cartão do cliente", category="cartoes"),
    Tool(name="enviar_pix", description="Transfere dinheiro via Pix", category="pix"),
]


def test_retriever_raises_before_fit():
    r = ToolRetriever()
    with pytest.raises(RuntimeError, match="Chame fit\\(\\) antes de search\\(\\)\\."):
        r.search("saldo", k=1)


def test_retriever_empty_query():
    r = ToolRetriever().fit(TOOLS)
    with pytest.raises(ValueError, match="Query não pode ser vazia"):
        r.search("", k=1)
    with pytest.raises(ValueError, match="Query não pode ser vazia"):
        r.search("   ", k=1)


def test_retriever_invalid_k():
    r = ToolRetriever().fit(TOOLS)
    with pytest.raises(ValueError, match="k deve ser maior que zero"):
        r.search("saldo", k=0)
    with pytest.raises(ValueError, match="k deve ser maior que zero"):
        r.search("saldo", k=-1)


def test_retriever_empty_catalog():
    r = ToolRetriever().fit([])
    res = r.search("saldo", k=2)
    assert res.matches == []
    assert res.latency_ms >= 0


def test_retriever_k_larger_than_catalog():
    r = ToolRetriever().fit(TOOLS)
    res = r.search("saldo", k=10)
    assert len(res.matches) == 3


def test_retriever_normalization_equivalence():
    """Invariante da Seção 3.2: 'Cartão' e 'cartao' devem produzir mesma ordem e mesmos scores."""
    r = ToolRetriever().fit(TOOLS)
    m1 = r.search("Cartão", k=2).matches
    m2 = r.search("cartao", k=2).matches
    assert len(m1) == len(m2)
    for t1, t2 in zip(m1, m2):
        assert t1.name == t2.name
        assert pytest.approx(t1.score, rel=1e-5) == t2.score


def test_retriever_deterministic_tie_breaking():
    """Desempate determinístico por ordem alfabética de tool.name quando scores forem iguais."""
    ties = [
        Tool(name="zebra_tool", description="descricao qualquer", category="cat"),
        Tool(name="alfa_tool", description="descricao qualquer", category="cat"),
        Tool(name="beta_tool", description="descricao qualquer", category="cat"),
    ]
    r = ToolRetriever().fit(ties)
    res = r.search("termo_inexistente", k=3)
    names = [m.name for m in res.matches]
    assert names == ["alfa_tool", "beta_tool", "zebra_tool"]
