"""Testes unitários completos do ToolRetriever."""
import pytest

from candidate_starter.retrieval import ToolRetriever
from candidate_starter.taxonomy import CANONICAL_ALIASES
from common.data_loader import load_tools
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


def test_taxonomy_fixes_ranking_that_lexical_alone_gets_wrong():
    """Contraste medido no catálogo real: a taxonomia corrige o ranking, não o score.

    Sem taxonomia, a variante hiperespecífica vence porque o nome dela repete as palavras
    da query. Com a taxonomia, o grupo colapsa e a capacidade canônica assume o top-1,
    com a variante que casou preservada em `matched_variant` para auditoria.
    """
    tools = load_tools()
    r_plain = ToolRetriever(use_taxonomy=False).fit(tools)
    r_tax = ToolRetriever(use_taxonomy=True).fit(tools)

    query = "Manda o pdf da minha fatura atual"

    assert r_plain.search(query, k=1).matches[0].name == "enviar_pdf_fatura_atual"

    top = r_tax.search(query, k=1).matches[0]
    assert top.name == "consultar_fatura"
    assert top.matched_variant == "enviar_pdf_fatura_atual"


def test_capability_collapse_deduplicates_top_k():
    """top-k devolve k capacidades DISTINTAS, não k duplicatas da mesma capacidade."""
    from candidate_starter.taxonomy import VARIANT_TO_CANONICAL

    r = ToolRetriever(use_taxonomy=True).fit(load_tools())
    names = [m.name for m in r.search("Me envia a linha digitável da fatura", k=3).matches]

    assert len(names) == len(set(names))
    assert not (set(names) & set(VARIANT_TO_CANONICAL)), (
        "Nenhuma variante pode aparecer no resultado: o ranking opera sobre capacidades."
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



# ── Estabilidade e contrato de capacidade ────────────────────────────────────

def test_ranking_is_stable_under_catalog_reordering():
    """A ordem das linhas do registry não pode influenciar a decisão.

    O catálogo é um arquivo JSON: uma reordenação (merge, regeneração, ordenação
    alfabética) não é uma mudança de domínio e não pode mover uma escrita para o topo.
    O desempate por nome existe exatamente para isso — este teste é a prova.
    """
    import random

    tools = load_tools()
    shuffled = tools[:]
    random.Random(20260910).shuffle(shuffled)
    assert [t.name for t in shuffled] != [t.name for t in tools], "embaralhamento não ocorreu"

    queries = [
        "Quero saber meu saldo",
        "Me manda o codigo de barras pra pagar",
        "Perdi meu cartao, bloqueia agora",
        "Quero mudar o e-mail vinculado à minha conta",
    ]

    def ranking(catalog):
        r = ToolRetriever(min_score=0.10, use_taxonomy=True).fit(catalog)
        return [
            [(m.name, round(m.score, 12)) for m in r.search(q, k=3).matches] for q in queries
        ]

    assert ranking(tools) == ranking(shuffled)


def test_matched_variant_is_the_executable_endpoint():
    """Capacidade canônica e endpoint executável são coisas distintas.

    `name` responde "qual é a intenção"; `matched_variant` responde "qual endpoint casou
    com o pedido". Um runtime real precisa do segundo. O contrato: quando presente,
    `matched_variant` é sempre uma tool real do catálogo e nunca é igual a `name`.
    """
    from candidate_starter.taxonomy import VARIANT_TO_CANONICAL

    catalog = {t.name for t in load_tools()}
    r = ToolRetriever(min_score=0.10, use_taxonomy=True).fit(load_tools())

    match = r.search("Me manda o boleto da fatura em PDF no meu email", k=1).matches[0]
    assert match.name == "consultar_fatura"
    assert match.matched_variant in catalog, "a variante precisa ser um endpoint real"
    assert match.matched_variant != match.name
    assert VARIANT_TO_CANONICAL[match.matched_variant] == match.name

    # Contraprova: `atualizar_email` não declara variantes, então a própria canônica é o
    # endpoint executável e não há variante a reportar.
    direct = r.search("Quero mudar meu email", k=1).matches[0]
    assert direct.name == "atualizar_email"
    assert direct.matched_variant is None

    # O contrato vale para TODO resultado, não só para os dois casos acima.
    for query in ("Perdi meu cartao", "Quero saber meu saldo", "Qual meu limite"):
        for m in r.search(query, k=3).matches:
            if m.matched_variant is not None:
                assert m.matched_variant in catalog
                assert VARIANT_TO_CANONICAL[m.matched_variant] == m.name


def test_query_made_only_of_functional_words_abstains():
    """Query reduzida a palavras funcionais não pode pontuar acima do limiar.

    Complementa a query fora de domínio: aqui não há sequer conteúdo a interpretar.
    Sem a lista de stopwords, "a" e "da" bastavam para atravessar min_score, porque uma
    query curta tem norma L2 pequena e dois casamentos funcionais dominam o cosseno.
    """
    r = ToolRetriever(min_score=0.10, use_taxonomy=True).fit(load_tools())
    for query in ("a de da o para com", "qual e o que", "por que de uma"):
        assert r.search(query, k=2).matches == [], f"'{query}' deveria abster"
