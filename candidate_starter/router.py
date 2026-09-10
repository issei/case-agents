"""Pilar 1 — Router de Queries.

Implemente um componente que decide, para cada `query` do usuário, se ela deve ir para:
  - "FAST_PATH": queries simples (saudação, FAQ) -> resposta local, sem LLM.
  - "AGENT": queries que precisam de uma tool + raciocínio -> vai para o Pilar 2.

A técnica é livre (ex: modelo clássico de ML, embeddings + classificador, regras, etc.)
— escolha o que fizer sentido e esteja preparado para justificar.
"""
import time
from typing import List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from common.interfaces import BaseRouter
from common.normalization import normalize
from common.schemas import RouteResult


class QueryRouter(BaseRouter):
    """Router supervisionado para classificação determinística FAST_PATH vs AGENT."""

    VALID_ROUTES = {"FAST_PATH", "AGENT"}

    def __init__(self) -> None:
        self._fitted = False
        self._vectorizer = TfidfVectorizer(
            preprocessor=normalize,
            ngram_range=(1, 2),
            min_df=1,
        )
        self._classifier = LogisticRegression(
            random_state=42,
            C=1.0,
            max_iter=1000,
        )

    def fit(self, texts: List[str], labels: List[str]) -> "QueryRouter":
        """Treina o router com os exemplos rotulados."""
        if not texts or not labels:
            raise ValueError("Texts e labels não podem ser listas vazias.")
        if len(texts) != len(labels):
            raise ValueError(f"Dimensões incompatíveis: {len(texts)} textos e {len(labels)} labels.")

        for label in labels:
            if label not in self.VALID_ROUTES:
                raise ValueError(f"Rótulo inválido: '{label}'. Esperado um de {self.VALID_ROUTES}.")

        X = self._vectorizer.fit_transform(texts)
        self._classifier.fit(X, labels)
        self._fitted = True
        return self

    def predict(self, query: str) -> RouteResult:
        """Classifica `query` e retorna a rota escolhida + latência medida (em ms)."""
        if not self._fitted:
            raise RuntimeError("Chame fit() antes de predict().")
        if not query or not query.strip():
            raise ValueError("Query não pode ser vazia.")

        start = time.perf_counter()
        X = self._vectorizer.transform([query])
        proba = self._classifier.predict_proba(X)[0]
        max_idx = int(np.argmax(proba))
        predicted_route = str(self._classifier.classes_[max_idx])
        confidence = float(proba[max_idx])
        latency_ms = (time.perf_counter() - start) * 1000.0

        return RouteResult(
            route=predicted_route,
            latency_ms=latency_ms,
            confidence=confidence,
        )
