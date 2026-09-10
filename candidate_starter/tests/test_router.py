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


# ── Distribuição da confiança ────────────────────────────────────────────────
# Acurácia diz se a CLASSE está certa. O limiar de 0.75 do harness é uma política de
# risco sobre a CONFIANÇA — e uma política só funciona se a confiança tiver dispersão
# real. Um classificador 100% acurado pode ser inútil aqui de duas formas opostas:
# subconfiante (tudo abaixo do limiar, cobertura destruída — foi o defeito de `fc830dc`)
# ou saturado (tudo em ~1.0, o limiar não separa nada e a abstenção nunca dispara, que é
# o que a calibração isotônica produziu com 53 amostras). Ver ADR-007.

def test_router_confidence_distribution_is_usable_as_a_risk_policy():
    from candidate_starter.harness import ROUTER_CONFIDENCE_THRESHOLD
    from common.data_loader import load_eval_dataset, load_router_training_data

    texts, labels = load_router_training_data()
    router = QueryRouter().fit(texts, labels)
    results = [(d, router.predict(d["query"])) for d in load_eval_dataset()]
    confidences = sorted(r.confidence for _, r in results)

    assert max(confidences) < 1.0, (
        "Confiança saturada em 1.0: o limiar deixa de separar qualquer coisa"
    )
    assert max(confidences) - min(confidences) > 0.15, (
        f"Distribuição achatada (amplitude {max(confidences) - min(confidences):.3f}). "
        f"Sem dispersão, o limiar de {ROUTER_CONFIDENCE_THRESHOLD} é decorativo."
    )
    assert min(confidences) < 0.80, (
        "Nenhuma query gerou dúvida: o modelo perdeu a capacidade de expressar incerteza"
    )

    # Cobertura: nenhuma query AGENT pode cair abaixo do limiar por subconfiança.
    agent = [r.confidence for _, r in results if r.route == "AGENT"]
    slack = min(agent) - ROUTER_CONFIDENCE_THRESHOLD
    assert slack > 0, (
        f"Query AGENT com confiança {min(agent):.4f} abaixo do limiar "
        f"{ROUTER_CONFIDENCE_THRESHOLD}: cobertura perdida por subconfiança, não por risco"
    )
    # Folga medida no commit atual: 0.017. É pequena — está registrada como risco no
    # README. O teste protege a propriedade; não congela o valor.
