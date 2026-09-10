"""Pilar 1 — Router de Queries.

Implemente um componente que decide, para cada `query` do usuário, se ela deve ir para:
  - "FAST_PATH": queries simples (saudação, FAQ) -> resposta local, sem LLM.
  - "AGENT": queries que precisam de uma tool + raciocínio -> vai para o Pilar 2.

A técnica é livre (ex: modelo clássico de ML, embeddings + classificador, regras, etc.)
— escolha o que fizer sentido e esteja preparado para justificar.
"""
import time
from collections import Counter
from typing import List

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
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
        # Calibração de probabilidade (Platt scaling) sobre LogisticRegression.
        #
        # Motivo: o limiar de segurança do harness (0.75) só é uma política de risco válida
        # se `confidence` estimar a probabilidade real de acerto. A regressão logística
        # regularizada sobre TF-IDF esparso (53 exemplos, vocabulário de bigramas) encolhe
        # os coeficientes e produz probabilidades sistematicamente subconfiantes: com C=1.0
        # as 30 queries do dataset oficial ficam abaixo de 0.75, embora a acurácia seja
        # 100%. O limiar então não separa nada — apenas descarta cobertura.
        #
        # A versão anterior contornava isso elevando C para 5.0 (afrouxar a regularização
        # até as probabilidades "passarem"). Isso é mover a trave: o modelo não fica mais
        # confiável, só mais confiante. `CalibratedClassifierCV` ataca a causa — ajusta uma
        # sigmoide sobre predições out-of-fold, de modo que a probabilidade reportada seja
        # uma estimativa de acerto, e permite restaurar a regularização padrão (C=1.0).
        #
        # `method="sigmoid"` (Platt), não isotônica: a isotônica é não paramétrica e
        # sobreajusta com 53 amostras (medido: mínimo 0.806, nenhuma abstenção — confiança
        # artificialmente saturada). StratifiedKFold sem shuffle -> determinístico.
        # O número de folds é escolhido em fit(), a partir da classe minoritária.
        self._classifier = None

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
        self._classifier = self._build_classifier(labels)
        self._classifier.fit(X, labels)
        self._fitted = True
        return self

    @staticmethod
    def _build_classifier(labels: List[str]):
        """Monta o classificador, calibrado quando há amostras suficientes.

        A calibração precisa de predições out-of-fold, o que exige pelo menos 2 exemplos
        na classe minoritária. Abaixo disso (cenários de teste unitário com 4 exemplos)
        a calibração é omitida e o modelo usa a probabilidade bruta da regressão logística.
        """
        base = LogisticRegression(random_state=42, max_iter=1000)
        counts = Counter(labels)
        n_splits = min(5, min(counts.values()))
        if len(counts) < 2 or n_splits < 2:
            return base
        return CalibratedClassifierCV(base, method="sigmoid", cv=n_splits)

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
