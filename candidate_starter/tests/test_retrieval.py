"""Testes unitários completos do ToolRetriever."""
import pytest

from candidate_starter.retrieval import ToolRetriever
from candidate_starter.taxonomy import CANONICAL_ALIASES
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
    r = ToolRetriever(use_taxonomy=False).fit(ties)
    res = r.search("termo_inexistente", k=3)
    names = [m.name for m in res.matches]
    assert names == ["alfa_tool", "beta_tool", "zebra_tool"]


def test_retriever_abstention_with_min_score():
    """Com min_score > 0, termos sem similaridade acionam abstention (lista vazia)."""
    ties = [
        Tool(name="zebra_tool", description="descricao qualquer", category="cat"),
        Tool(name="alfa_tool", description="descricao qualquer", category="cat"),
    ]
    r = ToolRetriever().fit(ties)
    # Sem min_score (default 0.0), retorna os 2 com score 0.0
    res_zero = r.search("termo_inexistente", k=2, min_score=0.0)
    assert len(res_zero.matches) == 2

    # Com min_score > 0, descarta itens com similaridade nula
    res_abstain = r.search("termo_inexistente", k=2, min_score=0.05)
    assert res_abstain.matches == []


def test_retriever_configurable_min_score_in_init():
    """Configuração de min_score no construtor deve ser respeitada nas buscas."""
    r = ToolRetriever(min_score=0.1, use_taxonomy=False).fit(TOOLS)
    res = r.search("termo_completamente_aleatorio_xyz", k=2)
    assert res.matches == []


# ── Testes de Taxonomia Canônica ──────────────────────────────────────────────

def test_taxonomy_module_has_canonical_aliases():
    """O módulo de taxonomia deve conter aliases para as intenções do dataset oficial."""
    expected_intents = [
        "consultar_fatura", "consultar_saldo", "alterar_endereco",
        "estornar_transacao", "parcelar_fatura", "bloquear_cartao",
        "desbloquear_cartao", "solicitar_segunda_via_cartao", "abrir_chamado_suporte",
    ]
    for intent in expected_intents:
        assert intent in CANONICAL_ALIASES, f"Intent '{intent}' ausente em CANONICAL_ALIASES"
        assert len(CANONICAL_ALIASES[intent].strip()) > 0, f"Aliases vazios para '{intent}'"


def test_taxonomy_enrichment_improves_recall():
    """Com use_taxonomy=True, o retriever encontra a tool canônica via vocabulário do usuário."""
    tools = [
        Tool(name="bloquear_cartao", description="Bloqueia cartão de crédito", category="cartoes"),
        Tool(name="consultar_saldo", description="Consulta saldo da conta", category="conta"),
        Tool(name="enviar_pix", description="Transferência via Pix", category="pix"),
    ]
    # Sem taxonomia: "perdi meu cartão" não encontra "bloquear_cartao" com score alto
    r_plain = ToolRetriever(use_taxonomy=False).fit(tools)
    r_tax = ToolRetriever(use_taxonomy=True).fit(tools)

    res_plain = r_plain.search("perdi meu cartao na rua", k=1)
    res_tax = r_tax.search("perdi meu cartao na rua", k=1)

    # Com taxonomia, a tool canônica deve estar em top-1
    assert res_tax.matches[0].name == "bloquear_cartao"
    # E o score com taxonomia deve ser maior que sem taxonomia
    score_tax = res_tax.matches[0].score if res_tax.matches else 0.0
    score_plain = res_plain.matches[0].score if res_plain.matches else 0.0
    assert score_tax > score_plain, (
        "Taxonomia deve elevar o score da tool canônica para queries com vocabulário coloquial"
    )


def test_taxonomy_no_side_effects_on_unrelated_tools():
    """Ferramentas sem aliases na taxonomia não são afetadas pelo enriquecimento."""
    tools = [
        Tool(name="enviar_pix", description="Transferência via Pix", category="pix"),
        Tool(name="consultar_extrato", description="Consulta extrato bancário", category="conta"),
    ]
    r = ToolRetriever(use_taxonomy=True).fit(tools)
    res = r.search("pix transferencia", k=2)
    assert len(res.matches) >= 1
    assert res.matches[0].name == "enviar_pix"

