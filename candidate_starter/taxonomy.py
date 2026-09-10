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
   A desambiguação entre elas é papel do glossário de verbos, não do agrupamento.
5. O glossário é autorado a partir do domínio bancário, não do `eval_dataset.json`.
   O teste de paráfrases (queries fora do dataset oficial) é a evidência executável disso.
"""

CANONICAL_INTENTS: dict[str, dict] = {
    "consultar_fatura": {
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
        "aliases": (
            "email e mail correio eletronico endereco de email email cadastrado "
            "email vinculado trocar mudar atualizar alterar novo email"
        ),
        # Sem variantes: `consultar_email_vinculado_conta` (leitura),
        # `confirmar_email_cadastrado` (confirmação) e `recuperar_acesso_email`
        # (recuperação de acesso) são capacidades distintas. Ver invariante 4.
        "variants": [],
    },
    "bloquear_cartao": {
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
