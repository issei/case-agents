"""Taxonomia Canônica de Intenções Bancárias.

Este módulo define o mapeamento entre:
  1. Intenção Canônica de Negócio (o que o usuário quer fazer, ex.: `bloquear_cartao`)
  2. Aliases de Vocabulário do Usuário (termos coloquiais e variações naturais)

A taxonomia resolve o descompasso entre:
  - Rótulos esperados no dataset: nomes canônicos de alto nível (`bloquear_cartao`)
  - Ferramentas operacionais no catálogo: nomes específicos de operação
    (`solicitar_bloqueio_preventivo_cartao`)

Uso:
    from candidate_starter.taxonomy import CANONICAL_ALIASES
    # CANONICAL_ALIASES[tool_name] -> str com termos adicionais de enriquecimento
"""

# Mapeamento: nome canônico da tool -> termos de vocabulário do usuário (PT-BR)
# Cada string será concatenada ao corpus da ferramenta antes da vetorização,
# ampliando a cobertura lexical sem exigir embeddings densos.
CANONICAL_ALIASES: dict[str, str] = {
    "consultar_fatura": (
        "fatura linha digitavel boleto pdf fatura valor fatura mes atual "
        "enviar fatura manda fatura codigo de barras vencimento fatura"
    ),
    "consultar_saldo": (
        "saldo disponivel quanto tenho conta saldo pix valor disponivel "
        "conta agora tenho disponivel verificar saldo extrato"
    ),
    "alterar_endereco": (
        "mudar cep mudei de casa atualizar cep endereco entrega "
        "novo endereco mudanca endereco atualizar entrega"
    ),
    "estornar_transacao": (
        "compra nao reconheco contestar compra cobranca errada dinheiro de volta "
        "estorno nao fui eu quero estornar contestar cobranca fraudulenta"
    ),
    "consultar_limite_cartao": (
        "limite cartao credito limite disponivel quanto de limite tenho "
        "limite restante limite de credito disponivel"
    ),
    "parcelar_fatura": (
        "parcelar fatura dividir fatura parcelar em vezes parcelas fatura "
        "posso dividir parcelamento parcelar em 3 vezes quero parcelar"
    ),
    "alterar_telefone": (
        "troquei de numero novo numero atualizar telefone mudar celular "
        "troquei numero atualizar telefone cadastrado telefone novo"
    ),
    "atualizar_email": (
        "mudar email email vinculado trocar email atualizar email "
        "email cadastrado quero mudar email email da conta"
    ),
    "bloquear_cartao": (
        "perdi cartao bloquear agora bloqueio preventivo perda cartao urgente "
        "perdi meu cartao bloquear cartao imediatamente cartao perdido"
    ),
    "desbloquear_cartao": (
        "cartao novo desbloquear como desbloquear ativar cartao novo "
        "chegou meu cartao novo cartao novo ativar desbloqueio cartao"
    ),
    "solicitar_segunda_via_cartao": (
        "cartao parou funcionar segunda via solicitar novo cartao plastico "
        "meu cartao parou cartao nao funciona preciso de novo cartao"
    ),
    "abrir_chamado_suporte": (
        "aplicativo travando app travando abrir chamado suporte problema app "
        "chamado suporte tecnico erro no aplicativo reportar problema"
    ),
}
