from candidate_starter.retrieval import ToolRetriever
from common.data_loader import load_tools
from common.schemas import Tool


def test_retriever_search_returns_k_matches():
    tools = load_tools()
    retriever = ToolRetriever().fit(tools)
    result = retriever.search("Quero consultar meu saldo", k=2)

    assert len(result.matches) <= 2
    assert len(result.matches) > 0
    assert result.matches[0].score >= result.matches[1].score


def test_direction_guard_read_query_zeroes_write_tool():
    tools = [
        Tool(
            name="consultar_saldo",
            description="Consulta o saldo da conta corrente",
            category="conta",
        ),
        Tool(
            name="alterar_saldo",
            description="Altera o saldo da conta corrente",
            category="conta",
        ),
    ]
    retriever = ToolRetriever().fit(tools)
    result = retriever.search("Quero ver meu saldo", k=2)

    names = [m.name for m in result.matches]
    assert "consultar_saldo" in names
    assert "alterar_saldo" not in names


def test_canonical_collapsing():
    tools = [
        Tool(
            name="consultar_saldo_v1",
            description="Consultar saldo da conta corrente",
            category="conta",
        ),
        Tool(
            name="consultar_saldo_v2",
            description="Consultar saldo atualizado da conta",
            category="conta",
        ),
    ]
    retriever = ToolRetriever().fit(tools)
    result = retriever.search("saldo conta", k=2)

    # Should collapse tools with same canonical suffix/group if applicable
    assert len(result.matches) == 1
