"""Integridade da taxonomia de capacidades e generalização fora do dataset oficial.

Os testes de integridade verificam as invariantes de autoria declaradas no docstring de
`candidate_starter/taxonomy.py`. O teste de paráfrases é a evidência executável de que o
glossário foi autorado a partir do domínio bancário e não ajustado ao `eval_dataset.json`.
"""
import pytest

from candidate_starter.retrieval import ToolRetriever
from candidate_starter.taxonomy import CANONICAL_INTENTS, VARIANT_TO_CANONICAL
from common.data_loader import load_eval_dataset, load_tools

CATALOG = {t.name for t in load_tools()}


# ── Invariantes de autoria ───────────────────────────────────────────────────

def test_every_canonical_intent_exists_in_catalog():
    """Invariante 1: nenhuma capacidade canônica pode ser um nome inventado."""
    missing = sorted(name for name in CANONICAL_INTENTS if name not in CATALOG)
    assert missing == [], f"Capacidades canônicas ausentes do catálogo: {missing}"


def test_every_variant_exists_in_catalog():
    """Invariante 1: nenhuma variante mapeada pode ser um nome inventado."""
    missing = sorted(name for name in VARIANT_TO_CANONICAL if name not in CATALOG)
    assert missing == [], f"Variantes ausentes do catálogo: {missing}"


def test_no_tool_belongs_to_two_capabilities():
    """Invariante 2: sem colisão entre intenções."""
    seen = {}
    for canonical, spec in CANONICAL_INTENTS.items():
        for variant in spec["variants"]:
            assert variant not in seen, (
                f"'{variant}' mapeado para '{seen.get(variant)}' e '{canonical}'"
            )
            seen[variant] = canonical


def test_canonical_is_never_a_variant_of_another_capability():
    """Invariante 3: uma capacidade canônica não pode ser subordinada a outra."""
    overlap = sorted(set(CANONICAL_INTENTS) & set(VARIANT_TO_CANONICAL))
    assert overlap == [], f"Capacidades canônicas usadas como variantes: {overlap}"


def test_every_capability_has_a_non_empty_glossary():
    for canonical, spec in CANONICAL_INTENTS.items():
        assert spec["aliases"].strip(), f"Glossário vazio para '{canonical}'"


def test_read_and_write_capabilities_are_not_grouped():
    """Invariante 4: leitura e escrita são capacidades distintas, mesmo se lexicalmente próximas.

    Sentinelas concretas do catálogo. Agrupá-las faria o retriever executar uma escrita
    quando o cliente pediu uma leitura — exatamente a falha que o Quality Gate persegue.
    """
    for read_tool in (
        "consultar_email_vinculado_conta",
        "consultar_endereco_cadastrado",
        "consultar_condicoes_parcelamento_fatura",
        "simular_parcelamento_fatura",
        "rastrear_segunda_via_cartao",
        "consultar_status_chamado",
    ):
        assert read_tool in CATALOG, f"Sentinela '{read_tool}' saiu do catálogo"
        assert read_tool not in VARIANT_TO_CANONICAL, (
            f"'{read_tool}' é leitura/simulação e não pode ser variante de uma escrita"
        )


def test_every_expected_tool_of_the_dataset_exists_in_catalog():
    """O dataset oficial não pode esperar uma ferramenta que não existe."""
    expected = {d["expected_tool"] for d in load_eval_dataset() if d.get("expected_tool")}
    missing = sorted(expected - CATALOG)
    assert missing == [], f"expected_tool sem correspondência no catálogo: {missing}"


# ── Generalização fora do dataset oficial ────────────────────────────────────

# Paráfrases escritas a partir do domínio, com vocabulário que NÃO aparece no
# `eval_dataset.json`. Servem para detectar ajuste do glossário ao gabarito: se o
# retriever só acerta as 20 queries oficiais, a taxonomia é um gabarito disfarçado.
PARAPHRASES = [
    ("Fui roubado, cancela meu cartao ja", "bloquear_cartao"),
    ("Nao consigo pagar tudo, da pra dividir em 6x?", "parcelar_fatura"),
    ("Recebi o plastico novo, preciso habilitar", "desbloquear_cartao"),
    ("Meu app fecha sozinho toda hora", "abrir_chamado_suporte"),
    ("Quanto ainda posso gastar no credito?", "consultar_limite_cartao"),
    ("Me manda o codigo de barras pra pagar", "consultar_fatura"),
    ("Troquei de operadora e de numero", "alterar_telefone"),
    ("Nao reconheco esse debito, quero meu dinheiro", "estornar_transacao"),
    ("Meu correio eletronico mudou, corrige no cadastro", "atualizar_email"),
    ("Fui morar em outro bairro, cadastra o novo lugar", "alterar_endereco"),
    ("Tem quanto na minha conta?", "consultar_saldo"),
    ("O cartao quebrou ao meio, preciso de outro", "solicitar_segunda_via_cartao"),
]

# Piso documentado, não meta. O valor observado está registrado no README; o teste protege
# contra regressão sem fingir que recuperação lexical resolve paráfrase arbitrária.
PARAPHRASE_HIT_RATE_FLOOR_AT_2 = 0.75


@pytest.fixture(scope="module")
def retriever():
    return ToolRetriever(use_taxonomy=True).fit(load_tools())


def test_paraphrases_outside_dataset_generalize(retriever):
    hits = sum(
        expected in [m.name for m in retriever.search(query, k=2).matches]
        for query, expected in PARAPHRASES
    )
    rate = hits / len(PARAPHRASES)
    assert rate >= PARAPHRASE_HIT_RATE_FLOOR_AT_2, (
        f"Hit Rate@2 em paráfrases caiu para {rate:.0%} "
        f"(piso {PARAPHRASE_HIT_RATE_FLOOR_AT_2:.0%}). "
        f"Indica regressão do glossário ou ajuste ao dataset oficial."
    )


def test_unknown_query_produces_abstention(retriever):
    """Query fora do domínio bancário não pode devolver candidato algum."""
    strict = ToolRetriever(min_score=0.10, use_taxonomy=True).fit(load_tools())
    assert strict.search("qual a capital da mongolia interior", k=2).matches == []


def test_read_and_write_glossaries_do_not_cross_map(retriever):
    """Invariante 4, no nível do glossário: um pedido de leitura não pode resolver escrita.

    O teste de sentinelas prova que as tools não foram AGRUPADAS. Este prova o efeito que
    importa: mesmo com vocabulário compartilhado ("email", "endereço", "telefone"), o
    verbo do pedido decide a capacidade. Colisão aqui é a falha mais cara do domínio —
    o cliente pergunta e o agente altera.
    """
    read_then_write = [
        ("Qual e o email cadastrado na minha conta?", "consultar_email_vinculado_conta",
         "atualizar_email"),
        ("Qual endereco esta no meu cadastro?", "consultar_endereco_cadastrado",
         "alterar_endereco"),
    ]
    for query, expected_read, forbidden_write in read_then_write:
        top = retriever.search(query, k=1).matches[0].name
        assert top == expected_read, (
            f"'{query}' resolveu '{top}'; esperado a capacidade de leitura '{expected_read}'"
        )
        assert top != forbidden_write


def test_write_intent_does_not_resolve_to_a_read_capability(retriever):
    """Contraprova: o verbo de escrita precisa alcançar a capacidade de escrita.

    Sem esta metade, a invariante seria satisfeita por um sistema que nunca escreve.
    `k=2` porque leitura e escrita sobre o mesmo dado são vizinhas por construção — a
    desambiguação final é da guarda de margem, não do retriever.
    """
    for query, expected_write in (
        ("Quero trocar meu numero de telefone", "alterar_telefone"),
        ("Muda meu endereco de cobranca", "alterar_endereco"),
    ):
        names = [m.name for m in retriever.search(query, k=2).matches]
        assert expected_write in names, f"'{query}' não alcançou '{expected_write}': {names}"


# ── Direção da intenção (leitura vs escrita) ─────────────────────────────────

def test_every_capability_declares_a_direction():
    """Invariante 6: capacidade sem `mode` não pode ser protegida pela guarda de direção."""
    for canonical, spec in CANONICAL_INTENTS.items():
        assert spec.get("mode") in ("read", "write"), (
            f"'{canonical}' não declara mode read/write"
        )


def test_variants_inherit_the_direction_of_their_capability():
    from candidate_starter.taxonomy import CAPABILITY_MODE

    for variant, canonical in VARIANT_TO_CANONICAL.items():
        assert CAPABILITY_MODE[variant] == CAPABILITY_MODE[canonical], (
            f"'{variant}' diverge da direção de '{canonical}' — colapso mistura direções"
        )


def test_query_direction_reads_the_verb_not_the_noun():
    """O substantivo é compartilhado por leitura e escrita; só o verbo decide."""
    from candidate_starter.taxonomy import query_direction

    assert query_direction("qual email cadastrado conta".split()) == "read"
    assert query_direction("quero mudar email vinculado conta".split()) == "write"
    # Escrita tem precedência: a frase pergunta e manda ao mesmo tempo.
    assert query_direction("qual endereco quero atualizar".split()) == "write"
    # Sem verbo nem marcador -> nenhuma restrição é imposta.
    assert query_direction("fatura cartao credito".split()) == ""
    # "enviar"/"mandar" são entrega, não mutação: não podem virar escrita.
    assert query_direction("me manda o boleto".split()) == ""


def test_a_read_request_can_never_resolve_to_a_write_capability(retriever):
    """A invariante de segurança mais cara do domínio, verificada no ranking completo.

    Antes da guarda de direção, "Qual e o email cadastrado na minha conta?" devolvia
    `atualizar_email` (ESCRITA) em primeiro lugar com margem relativa de 0.47 — acima do
    limiar de 0.25, ou seja, a guarda de margem NÃO pegava e a alteração seria executada.
    """
    from candidate_starter.taxonomy import CAPABILITY_MODE

    read_requests = [
        "Qual e o email cadastrado na minha conta?",
        "Qual endereco esta no meu cadastro?",
        "Qual o telefone que voces tem de mim?",
        "Quanto de limite ainda tenho?",
        "Quero saber meu saldo",
    ]
    for query in read_requests:
        for m in retriever.search(query, k=3).matches:
            assert CAPABILITY_MODE.get(m.name, "read") != "write", (
                f"'{query}' recuperou a ESCRITA '{m.name}': o cliente pergunta e o "
                f"agente altera o cadastro"
            )
