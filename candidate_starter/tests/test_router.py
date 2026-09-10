"""Testes unitários completos do QueryRouter."""
import pytest

from candidate_starter.router import QueryRouter


TRAIN_TEXTS = [
    "Bom dia, qual o horário de atendimento?",
    "Olá, tudo bem?",
    "Quero saber meu saldo",
    "Preciso bloquear meu cartão perdido",
]
TRAIN_LABELS = ["FAST_PATH", "FAST_PATH", "AGENT", "AGENT"]


def test_router_raises_before_fit():
    router = QueryRouter()
    with pytest.raises(RuntimeError, match="Chame fit\\(\\) antes de predict\\(\\)\\."):
        router.predict("Qualquer coisa")


def test_router_fit_validation_empty():
    router = QueryRouter()
    with pytest.raises(ValueError, match="Texts e labels não podem ser listas vazias"):
        router.fit([], [])


def test_router_fit_validation_length_mismatch():
    router = QueryRouter()
    with pytest.raises(ValueError, match="Dimensões incompatíveis"):
        router.fit(["texto 1"], ["FAST_PATH", "AGENT"])


def test_router_fit_validation_invalid_label():
    router = QueryRouter()
    with pytest.raises(ValueError, match="Rótulo inválido"):
        router.fit(["texto 1"], ["INVALID_LABEL"])


def test_router_predict_empty_query():
    router = QueryRouter().fit(TRAIN_TEXTS, TRAIN_LABELS)
    with pytest.raises(ValueError, match="Query não pode ser vazia"):
        router.predict("")
    with pytest.raises(ValueError, match="Query não pode ser vazia"):
        router.predict("   ")


def test_router_predict_valid_route_and_confidence():
    router = QueryRouter().fit(TRAIN_TEXTS, TRAIN_LABELS)
    result = router.predict("Bom dia!")
    assert result.route in {"FAST_PATH", "AGENT"}
    assert result.latency_ms >= 0
    assert result.confidence is not None
    assert 0.0 <= result.confidence <= 1.0
