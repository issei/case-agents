"""Testes unitários da função de normalização textual canônica."""
from common.normalization import normalize


def test_normalize_samples():
    assert normalize("Cartão de crédito") == "cartao de credito"
    assert normalize("cartao") == "cartao"
    assert normalize("Cartão!") == "cartao"
    assert normalize("PIX?") == "pix"
    assert normalize("R$ 250,50") == "r 250 50"


def test_normalize_empty_and_whitespace():
    assert normalize("") == ""
    assert normalize("   ") == ""
    assert normalize(None) == ""


def test_normalize_diacritics_and_symbols():
    assert normalize("Atenção à transferência bancária! #123") == "atencao a transferencia bancaria 123"
