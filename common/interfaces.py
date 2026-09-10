"""Contratos (ABCs) que tanto o starter quanto a solução de referência implementam.

Isso garante que `run_case.py` funcione de forma idêntica nas duas pastas, trocando
apenas a implementação concreta de Router e Retriever.
"""
from abc import ABC, abstractmethod
from typing import List

from common.schemas import RetrievalResult, RouteResult, Tool


class BaseRouter(ABC):
    """Contrato do Router (Pilar 1)."""

    @abstractmethod
    def fit(self, texts: List[str], labels: List[str]) -> "BaseRouter":
        """Treina o router a partir de exemplos rotulados (FAST_PATH / AGENT)."""

    @abstractmethod
    def predict(self, query: str) -> RouteResult:
        """Classifica uma query e retorna a rota escolhida + latência medida."""


class BaseToolRetriever(ABC):
    """Contrato do componente de Seleção de Tools (Pilar 2)."""

    @abstractmethod
    def fit(self, tools: List[Tool]) -> "BaseToolRetriever":
        """Indexa o catálogo de tools (sparse + dense)."""

    @abstractmethod
    def search(self, query: str, k: int = 2) -> RetrievalResult:
        """Retorna as top-k entradas mais relevantes para a query.

        Contrato de `k` (mudança em relação à leitura ingênua de "k tools do catálogo"):
        uma implementação que declare uma taxonomia de capacidades devolve `k` CAPACIDADES
        DISTINTAS, não `k` linhas brutas do registry. O catálogo contém duplicatas
        semânticas — sem colapso, `k=2` pode devolver duas variações do mesmo pedido e
        desperdiçar metade do orçamento de contexto.

        Nesse modo, `ToolMatch.name` é a capacidade canônica e `ToolMatch.matched_variant`
        é a variante operacional que efetivamente casou com a query. Um runtime que precise
        chamar o endpoint concreto deve ler `matched_variant`, não `name`.

        Implementações sem taxonomia devolvem `k` tools do catálogo e `matched_variant`
        é sempre None — o contrato antigo continua válido.
        """
