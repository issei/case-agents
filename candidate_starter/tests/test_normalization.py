from candidate_starter.normalization import normalize


def test_normalize_basic():
    assert normalize("Criar Documento") == "criar documento"
    assert normalize("criár documénto  ") == "criar documento"
    assert normalize("  CRIAR   DOCUMENTO!! ") == "criar documento"


def test_normalize_domain_variants():
    assert normalize("Quero 2a via / segunda via do cartão") == "quero 2a via segundavia do cartao"
    assert normalize("cartão de crédito") == "cartaocredito"
    assert normalize("cartão-crédito") == "cartaocredito"
    assert normalize("face-id") == "faceid"
