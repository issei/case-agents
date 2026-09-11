"""Pilar 1 — Router de Queries com Calibração (Platt Scaling)."""
import time
from typing import List, Optional

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from candidate_starter.normalization import normalize
from common.interfaces import BaseRouter
from common.schemas import RouteResult


class QueryRouter(BaseRouter):
    def __init__(self) -> None:
        self._fitted = False
        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            preprocessor=normalize,
        )
        self._base_clf = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        self._clf = None
        self.classes_: Optional[np.ndarray] = None

    def fit(self, texts: List[str], labels: List[str]) -> "QueryRouter":
        """Treina o router com os exemplos de `data/router_training_data.json`."""
        X = self._vectorizer.fit_transform(texts)

        # Contar menor número de amostras por classe
        unique_labels, counts = np.unique(labels, return_counts=True)
        min_class_count = int(np.min(counts))

        if min_class_count >= 3:
            cv = 3
        elif min_class_count >= 2:
            cv = 2
        else:
            cv = None

        if cv is not None:
            self._clf = CalibratedClassifierCV(estimator=self._base_clf, method="sigmoid", cv=cv)
        else:
            self._clf = self._base_clf

        self._clf.fit(X, labels)
        self.classes_ = self._clf.classes_
        self._fitted = True
        return self

    def predict(self, query: str) -> RouteResult:
        """Classifica `query` e retorna a rota escolhida, latência e confiança calibrada."""
        if not self._fitted or self._clf is None:
            raise RuntimeError("Chame fit() antes de predict().")

        start = time.perf_counter()

        X_q = self._vectorizer.transform([query])
        probs = self._clf.predict_proba(X_q)[0]
        best_idx = np.argmax(probs)
        route = str(self.classes_[best_idx])
        confidence = float(probs[best_idx])

        latency_ms = (time.perf_counter() - start) * 1000.0

        return RouteResult(
            route=route,
            latency_ms=latency_ms,
            confidence=confidence,
        )
