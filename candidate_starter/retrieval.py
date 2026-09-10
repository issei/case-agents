"""Pilar 2 — Seleção de Tools Relevantes.

O catálogo de tools está em `data/tools_registry.json`. Passar todas as tools no prompt
de um LLM não escala (estoura contexto, confunde o modelo, aumenta custo e latência).

`search(query, k=2)` deve retornar as `k` tools mais relevantes do catálogo para a query,
antes de qualquer chamada ao LLM. A estratégia de seleção/ranking é livre — escolha o que
fizer sentido e esteja preparado para justificar os trade-offs.
"""
import time
from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from common.interfaces import BaseToolRetriever
from common.normalization import normalize
from common.schemas import RetrievalResult, Tool, ToolMatch


class ToolRetriever(BaseToolRetriever):
    """Retriever lexical com normalização canônica e desempate determinístico."""

    def __init__(self) -> None:
        self._tools: List[Tool] = []
        self._fitted = False
        self._vectorizer = TfidfVectorizer(
            lowercase=False,
            strip_accents=None,
            token_pattern=r"\S+",
            ngram_range=(1, 2),
        )
        self._tfidf_matrix = None

    def fit(self, tools: List[Tool]) -> "ToolRetriever":
        """Indexa o catálogo de tools para busca."""
        self._tools = list(tools)
        if not self._tools:
            self._tfidf_matrix = None
            self._fitted = True
            return self

        corpus = [
            f"{normalize(t.name)} {normalize(t.description)} {normalize(t.category)}"
            for t in self._tools
        ]
        self._tfidf_matrix = self._vectorizer.fit_transform(corpus)
        self._fitted = True
        return self

    def search(self, query: str, k: int = 2) -> RetrievalResult:
        """Retorna as top-k tools mais relevantes para `query`."""
        if not self._fitted:
            raise RuntimeError("Chame fit() antes de search().")
        if not query or not query.strip():
            raise ValueError("Query não pode ser vazia.")
        if k <= 0:
            raise ValueError("k deve ser maior que zero.")

        start = time.perf_counter()

        if not self._tools or self._tfidf_matrix is None:
            latency_ms = (time.perf_counter() - start) * 1000.0
            return RetrievalResult(matches=[], latency_ms=latency_ms)

        normalized_query = normalize(query)
        query_vec = self._vectorizer.transform([normalized_query])
        scores = cosine_similarity(query_vec, self._tfidf_matrix)[0]

        # Desempate determinístico: score decrescente, nome da ferramenta alfabético crescente
        candidates = [
            (float(score), tool.name)
            for tool, score in zip(self._tools, scores)
        ]
        candidates.sort(key=lambda item: (-item[0], item[1]))

        top_k = candidates[: min(k, len(candidates))]
        matches = [ToolMatch(name=name, score=score) for score, name in top_k]
        latency_ms = (time.perf_counter() - start) * 1000.0

        return RetrievalResult(matches=matches, latency_ms=latency_ms)
