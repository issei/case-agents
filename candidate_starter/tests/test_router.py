from candidate_starter.router import QueryRouter
from common.data_loader import load_router_training_data


def test_router_training_and_prediction():
    texts, labels = load_router_training_data()
    router = QueryRouter().fit(texts, labels)

    res_fast = router.predict("Bom dia, qual o horário de funcionamento?")
    assert res_fast.route == "FAST_PATH"
    assert res_fast.confidence is not None
    assert res_fast.confidence >= 0.0 and res_fast.confidence <= 1.0
    assert res_fast.latency_ms >= 0

    res_agent = router.predict("Quero consultar o saldo da minha conta corrente")
    assert res_agent.route == "AGENT"
    assert res_agent.confidence is not None
    assert res_agent.confidence >= 0.0 and res_agent.confidence <= 1.0


def test_router_calibration_confidence_range():
    texts, labels = load_router_training_data()
    router = QueryRouter().fit(texts, labels)

    for text in texts:
        res = router.predict(text)
        assert res.confidence is not None
        assert 0.0 <= res.confidence <= 1.0
