"""Taxonomia Canônica de Capacidades Bancárias (governança do catálogo de tools).

## Problema que este módulo resolve

O catálogo (`data/tools_registry.json`, 285 tools) contém **duplicatas semânticas**:
várias ferramentas operacionais expõem a mesma capacidade de negócio com nomes
diferentes e hiperespecíficos. Exemplo real do catálogo:

    consultar_fatura                 -> "Gera o PDF ou linha digitável da fatura do mês atual."
    gerar_linha_digitavel_fatura     -> "Gera a linha digitável da fatura ... para pagamentos."
    enviar_pdf_fatura_atual          -> "Envia o PDF da fatura atual ... para o cliente."
    consultar_valor_fatura_mes_atual -> "Consulta o valor da fatura ... do mês atual."

Isso é o estado normal de um registry que cresceu por squad ao longo de anos. Para um
retriever puramente lexical a variante hiperespecífica sempre vence a canônica, porque o
nome dela repete literalmente as palavras da query do usuário.

## Contrato adotado

Este módulo declara a camada de **governança do catálogo**: qual capacidade de negócio
cada ferramenta operacional realiza. O retriever passa a recuperar no nível de
**capacidade** (as `variants` colapsam na canônica), não no nível de endpoint bruto.

    intenção canônica -> aliases (vocabulário do usuário) -> variantes operacionais

Duas estruturas, dois papéis distintos:

- `aliases`: glossário de domínio PT-BR (como o cliente fala). Alimenta um **campo de
  recuperação separado** — não é concatenado ao documento da tool, porque diluir o
  documento com um bloco grande de sinônimos derruba o peso TF-IDF dos termos originais
  (foi exatamente o que limitou a versão anterior a 35% de Hit Rate@2).
- `variants`: ferramentas do catálogo que executam a MESMA capacidade. Colapsam na
  canônica no ranking, com o membro que casou preservado em `ToolMatch.matched_variant`
  para auditoria.

## Regras de autoria (invariantes, verificadas em `tests/test_taxonomy.py`)

1. Toda `canonical` e toda `variant` DEVE existir em `data/tools_registry.json`.
2. Nenhuma tool pode pertencer a duas capacidades (sem colisão entre intenções).
3. Uma `canonical` nunca é `variant` de outra capacidade.
4. Leitura e escrita NÃO se agrupam: `consultar_email_vinculado_conta` (leitura) não é
   variante de `atualizar_email` (escrita), ainda que sejam lexicalmente próximas.
5. O glossário é autorado a partir do domínio bancário, não do `eval_dataset.json`.
   O teste de paráfrases (queries fora do dataset oficial) é a evidência executável disso.
6. Toda capacidade declara `mode` ("read" ou "write"), e toda variante herda o `mode` da
   sua canônica — o colapso nunca pode misturar direções dentro de um grupo.
7. Em par leitura/escrita, o glossário é VERB-FORWARD. O substantivo é do domínio e é
   compartilhado pelos dois lados ("email cadastrado" serve à consulta e à alteração);
   só o verbo pertence à capacidade. Substantivo compartilhado no glossário de um dos
   lados desequilibra o par — foi assim que uma consulta passou a resolver uma escrita.

## Por que a direção é declarada e não inferida

Medido no catálogo real: `consultar_email_vinculado_conta` marca 0.85 de cosseno lexical
contra "Quero mudar o e-mail vinculado à minha conta", porque o nome dela reproduz o objeto
do pedido. A única palavra que separa consulta de alteração é o verbo — um token entre dez
num saco de palavras. Nenhum ajuste de peso vence 0.65 de diferença de cosseno. Ver ADR-008.
"""

CANONICAL_INTENTS: dict[str, dict] = {
    "consultar_fatura": {
        "mode": "read",
        "aliases": (
            "fatura cartao de credito boleto codigo de barras linha digitavel pdf "
            "documento da fatura valor total valor da fatura vencimento mes atual "
            "enviar mandar receber"
        ),
        "variants": [
            "consultar_valor_fatura_mes_atual",
            "consultar_valor_total_fatura",
            "gerar_linha_digitavel_fatura",
            "enviar_boleto_fatura_email",
            "enviar_pdf_fatura_atual",
            "gerar_pdf_fatura_mes_atual",
            "reenviar_fatura_email",
        ],
    },
    "consultar_saldo": {
        "mode": "read",
        "aliases": (
            "saldo conta corrente valor disponivel quanto tenho quanto eu tenho "
            "dinheiro na conta disponibilidade verificar consultar saldo para pix"
        ),
        "variants": [
            "verificar_saldo_conta_corrente",
            "informar_saldo_atual_conta",
            "consultar_valor_disponivel_conta",
            "consultar_saldo_disponivel_pix",
        ],
    },
    "alterar_endereco": {
        "mode": "write",
        "aliases": (
            "endereco residencial endereco de entrega cep logradouro mudanca de endereco "
            "mudei de casa mudar atualizar alterar novo endereco correspondencia"
        ),
        "variants": [
            "atualizar_cep_entrega",
            "atualizar_endereco_entrega_encomendas",
            "processar_mudanca_endereco_atualizar_entrega",
        ],
    },
    "estornar_transacao": {
        "mode": "write",
        "aliases": (
            "estorno estornar reembolso devolucao dinheiro de volta contestar contestacao "
            "compra nao reconhecida cobranca indevida cobranca errada fraude"
        ),
        "variants": [
            "contestar_compra_cartao",
            "contestar_compra_desconhecida",
            "contestar_cobranca_duplicada",
            "registrar_compra_nao_reconhecida",
            "reclamar_cobranca_errada_cartao_dinheiro_volta",
            "solicitar_devolucao_dinheiro_cobranca_errada",
            "solicitar_devolucao_valor_cobranca",
        ],
    },
    "consultar_limite_cartao": {
        "mode": "read",
        "aliases": (
            "limite do cartao limite de credito limite disponivel limite restante "
            "quanto de limite consultar saber"
        ),
        # Fora do grupo: limite corporativo, cheque especial, transferência, uso
        # internacional e pré-aprovado — produtos distintos, não sinônimos.
        "variants": [
            "consultar_limite_disponivel_credito",
            "informar_limite_disponivel_cartao_credito",
            "consultar_limite_restante_fatura",
        ],
    },
    "parcelar_fatura": {
        "mode": "write",
        "aliases": (
            "parcelar parcelamento dividir a fatura em vezes parcelas prestacoes "
            "pagar em vezes dividir o pagamento"
        ),
        # `simular_parcelamento_fatura` e `consultar_condicoes_parcelamento_fatura` são
        # simulação/leitura, não a execução do parcelamento. Ver invariante 4.
        "variants": [
            "dividir_pagamento_fatura",
            "dividir_fatura_em_vezes",
            "parcelar_valor_fatura_cartao",
            "parcelar_fatura_numero_vezes_escolhido",
        ],
    },
    "alterar_telefone": {
        "mode": "write",
        "aliases": (
            "telefone celular numero de contato telefone cadastrado trocar "
            "troquei de numero mudar atualizar alterar novo numero"
        ),
        "variants": [
            "atualizar_telefone_cadastrado_troca_numero",
            "trocar_numero_telefone_cadastro",
            "processar_troca_numero_telefone_cliente",
        ],
    },
    "atualizar_email": {
        "mode": "write",
        # Glossário de ESCRITA: o verbo carrega a capacidade, não o substantivo. As
        # locuções "email cadastrado" e "email vinculado" foram removidas daqui — são o
        # vocabulário de LEITURA (e os nomes literais das tools de consulta). Mantê-las
        # fazia "Qual e o email cadastrado na minha conta?" resolver para a escrita.
        "aliases": (
            "email e mail correio eletronico trocar mudar atualizar alterar corrigir "
            "novo email mudei de email"
        ),
        # Sem variantes: `consultar_email_vinculado_conta` (leitura) e
        # `recuperar_acesso_email` (recuperação de acesso) são capacidades distintas.
        # Ver invariante 4.
        "variants": [],
    },
    "consultar_email_vinculado_conta": {
        "mode": "read",
        # Capacidade de LEITURA declarada explicitamente. Sem esta entrada a consulta
        # ficava sem campo de glossário e era estruturalmente penalizada contra a escrita
        # (ver invariante 6): a leitura perdia por não ter vocabulário, não por ser menos
        # relevante. Declarar o par leitura/escrita é o que torna a invariante 4 efetiva.
        # Glossário VERB-FORWARD: os substantivos ("email cadastrado", "email vinculado")
        # são compartilhados com a escrita e não discriminam — só os verbos discriminam.
        "aliases": "qual email qual e mail ver saber conferir consultar mostrar informar",
        "variants": ["confirmar_email_cadastrado"],
    },
    "consultar_endereco_cadastrado": {
        "mode": "read",
        "aliases": (
            "qual endereco qual cep ver saber conferir consultar mostrar informar "
            "onde estou cadastrado"
        ),
        # `confirmar_mudanca_endereco` NÃO entra: confirma que uma alteração já
        # processada teve efeito, não devolve o endereço em cadastro.
        "variants": [],
    },
    "bloquear_cartao": {
        "mode": "write",
        "aliases": (
            "bloquear bloqueio do cartao cartao perdido cartao roubado perda roubo "
            "extravio urgente preventivo perdi o cartao"
        ),
        # `bloquear_cartao_temporariamente` e `suspender_uso_cartao` NÃO entram:
        # bloqueio temporário é reversível e tem contrato de negócio diferente.
        "variants": [
            "solicitar_bloqueio_preventivo_cartao",
            "reportar_perda_cartao",
        ],
    },
    "desbloquear_cartao": {
        "mode": "write",
        "aliases": (
            "desbloquear desbloqueio ativar ativacao cartao novo cartao recebido "
            "chegou pelo correio habilitar"
        ),
        "variants": [
            "ativar_cartao_novo",
            "ativar_cartao_novo_recebido",
            "instrucoes_desbloqueio_cartao_novo",
        ],
    },
    "solicitar_segunda_via_cartao": {
        "mode": "write",
        "aliases": (
            "segunda via do cartao novo cartao reposicao reemissao cartao danificado "
            "cartao quebrado com defeito parou de funcionar nao funciona"
        ),
        # `rastrear_segunda_via_cartao` e `diagnosticar_cartao_com_defeito` são leitura/
        # diagnóstico, não emissão. Ver invariante 4.
        "variants": [
            "emitir_segunda_via_cartao_parou_funcionar",
            "solicitar_via_reposicao_cartao_com_defeito",
            "solicitar_reemissao_cartao_danificado",
        ],
    },
    "abrir_chamado_suporte": {
        "mode": "write",
        "aliases": (
            "chamado de suporte suporte tecnico atendimento problema tecnico erro bug "
            "aplicativo app site travando lento nao abre reportar registrar ocorrencia"
        ),
        # `abrir_chamado_financeiro`, `consultar_status_chamado` e
        # `cancelar_chamado_suporte` são outras capacidades. Ver invariante 4.
        "variants": [
            "abrir_chamado_suporte_app_travando",
            "abrir_chamado_travamento_app",
            "registrar_chamado_aplicativo_travando",
            "reportar_aplicativo_travando",
            "reportar_problema_aplicativo",
        ],
    },
}


# Índice derivado: ferramenta operacional -> capacidade canônica.
VARIANT_TO_CANONICAL: dict[str, str] = {
    variant: canonical
    for canonical, spec in CANONICAL_INTENTS.items()
    for variant in spec["variants"]
}

# Glossário por capacidade (campo de recuperação separado do documento da tool).
CANONICAL_ALIASES: dict[str, str] = {
    canonical: spec["aliases"] for canonical, spec in CANONICAL_INTENTS.items()
}

# Direção declarada da capacidade: "read" não altera estado, "write" altera.
CAPABILITY_MODE: dict[str, str] = {
    canonical: spec["mode"] for canonical, spec in CANONICAL_INTENTS.items()
}
CAPABILITY_MODE.update(
    {variant: CANONICAL_INTENTS[canonical]["mode"]
     for variant, canonical in VARIANT_TO_CANONICAL.items()}
)


# ── Direção da intenção do usuário ───────────────────────────────────────────
#
# Por que isto existe, e por que NÃO é resolvível por similaridade textual:
#
# Leitura e escrita sobre o mesmo dado compartilham todos os substantivos. A tool
# `consultar_email_vinculado_conta` marca 0.85 de cosseno contra "Quero mudar o e-mail
# vinculado à minha conta" — o nome dela reproduz literalmente o objeto do pedido. A
# palavra que separa as duas capacidades é UMA: o verbo. Num saco de palavras esse verbo
# é um token entre dez, e nenhum ajuste de alpha o faz vencer uma diferença de 0.65 de
# cosseno. A direção precisa entrar como sinal declarado, não inferido.
#
# Medido antes desta guarda: "Qual e o email cadastrado na minha conta?" (uma LEITURA)
# resolvia `atualizar_email` (uma ESCRITA) com margem relativa de 0.47 — folgadamente
# acima do limiar de 0.25, ou seja, a guarda de margem não pegava. O cliente pergunta e o
# agente altera o cadastro.

WRITE_VERBS: frozenset = frozenset({
    "mudar", "mude", "mudo", "mudei", "muda",
    "trocar", "troque", "troco", "troquei", "troca",
    "alterar", "altere", "altero", "alterei", "altera",
    "atualizar", "atualize", "atualizo", "atualizei", "atualiza",
    "corrigir", "corrija", "corrige", "cadastrar", "cadastra", "cadastre",
    "bloquear", "bloqueia", "bloqueie", "bloqueio", "cancelar", "cancela", "cancele",
    "desbloquear", "desbloqueia", "desbloquear", "ativar", "ativa", "ative", "habilitar",
    "estornar", "estorna", "estorne", "contestar", "contesta", "conteste",
    "parcelar", "parcela", "parcele", "dividir", "divide", "divida",
    "abrir", "abre", "abra", "emitir", "emite", "solicitar", "solicita",
    "reportar", "reporta", "registrar", "registra",
})
"""Verbos que caracterizam MUTAÇÃO do cadastro, do cartão ou de uma transação.

Deliberadamente fora da lista: "enviar", "mandar", "receber" e "gerar". Pedir que a
fatura seja enviada não altera dado do cliente — é entrega de informação, e tratá-la como
escrita faria `consultar_fatura` ser rebaixada em "me manda o boleto". Também fora:
"quero" e "preciso", que apenas introduzem o pedido ("quero saber meu saldo" é leitura).
"""

READ_MARKERS: frozenset = frozenset({
    "qual", "quais", "quanto", "quanta", "quantos", "quantas", "onde", "quando",
    "consultar", "consulta", "ver", "vejo", "saber", "sei", "conferir", "confere",
    "mostrar", "mostra", "informar", "informa", "verificar", "verifica", "status",
})
"""Marcadores de PERGUNTA. Um pedido só é classificado como leitura na ausência de
qualquer verbo de escrita — "qual o limite para eu parcelar" é escrita, não leitura."""


def query_direction(tokens) -> str:
    """Direção declarada pelo texto do usuário: "read", "write" ou "" (indefinida).

    Escrita tem precedência sobre leitura: uma frase que pergunta E manda ("qual o
    endereço? muda pra este") é tratada como escrita, porque é o lado que causa dano.
    """
    tokens = set(tokens)
    if tokens & WRITE_VERBS:
        return "write"
    if tokens & READ_MARKERS:
        return "read"
    return ""
