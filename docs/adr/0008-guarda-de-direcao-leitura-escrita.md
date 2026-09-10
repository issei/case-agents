# ADR-008: Guarda de Direção (Leitura vs Escrita) na Seleção de Capacidades

- **Status:** Aceita
- **Data:** 2026-09-10
- **Contexto do commit:** posterior a `c8f30d2`; responde à reavaliação externa, seções 3.4, 3.5 e 4.5
- **Relacionada a:** [ADR-006](0006-taxonomia-de-capacidades-e-colapso-de-duplicatas.md),
  [ADR-007](0007-calibracao-de-probabilidade-e-guarda-de-margem.md)

## Contexto

A reavaliação do commit `c8f30d2` apontou, na seção 3.4, um limite da guarda de margem:

> "A margem relativa de 0,25 é uma boa barreira contra empates. Ela não garante que top-1
> esteja correto quando top-2 estiver distante. **Uma ferramenta errada pode vencer com grande
> margem.**"

e pediu, na seção 4.5, um teste de colisão entre aliases de leitura e escrita. O teste foi
escrito e **falhou imediatamente**, sobre o catálogo real:

```
Query : "Qual e o email cadastrado na minha conta?"      (LEITURA)
Top-2 : atualizar_email (0.4795)  |  confirmar_email_cadastrado (0.2554)
Margem relativa: 0.47  >>  MIN_RELATIVE_MARGIN = 0.25
Decisão: EXECUTA atualizar_email
```

O cliente pergunta qual e-mail está no cadastro; o agente altera o cadastro. Não é um empate —
é uma **decisão confiante e errada**, e por isso nenhuma das três guardas existentes a impede:
a confiança do router é alta, o score é alto, e a margem é folgada.

Este é o cenário exato que a especificação do case nomeia como inaceitável: *"Uma tool incorreta
não é uma aproximação aceitável."*

## Diagnóstico

Duas causas independentes, ambas estruturais.

### Causa 1 — Ausência de glossário estava sendo lida como irrelevância

A ADR-006 estabeleceu `score = (1 - α)·lexical + α·intent` com α = 0.5. O campo `intent` só
existe para as capacidades declaradas em `CANONICAL_INTENTS`. Para qualquer outra ferramenta do
catálogo, `intents.get(group, 0.0)` devolvia **zero**, e o score era efetivamente cortado pela
metade.

O efeito: à época do defeito, 273 das 285 ferramentas competiam com metade do score contra as 12
capacidades então declaradas. `consultar_email_vinculado_conta` perdia para `atualizar_email`
**por não ter vocabulário declarado**, não por ser menos relevante. Em recuperação multi-campo
isso é um erro conhecido: campo ausente é *dado faltante*, não evidência negativa.

A correção óbvia — renormalizar sobre os campos presentes, usando `score = lexical` quando não há
glossário — foi implementada e **medida**:

| | Sucesso | Incorretas | Ambíguas | Paráfrases @2 |
|---|---:|---:|---:|---:|
| Antes | 95% | 0 | 1 | 11/12 |
| Com renormalização global | **65%** | **1** | 6 | 10/12 |

Rejeitada. A penalidade de 50% estava, por acidente, suprimindo as ~226 duplicatas semânticas
**não declaradas** do catálogo — exatamente o defeito que a ADR-006 ataca. Removê-la reabre o
problema original. A correção adotada foi mais estreita: declarar as capacidades de leitura que
formam par com uma escrita (`consultar_email_vinculado_conta`, `consultar_endereco_cadastrado`),
dando-lhes o glossário que lhes faltava, sem mexer no tratamento das ferramentas não declaradas.

### Causa 2 — Nenhum peso resolve o resto

Decomposição dos dois campos para a query de escrita do dataset oficial:

```
"Quero mudar o e-mail vinculado a minha conta"        (ESCRITA)

consultar_email_vinculado_conta   lexical = 0.8457    intent = 0.44
atualizar_email                   lexical = 0.1983    intent = 0.32
```

O nome da ferramenta de leitura — `consultar_email_vinculado_conta` — reproduz literalmente o
objeto do pedido: "e-mail vinculado ... conta". A diferença lexical é de **0.65**. Para que a
escrita vencesse por ajuste de α seria preciso `intent_escrita − intent_leitura > 0.647`, o que
é impossível: ambos os cossenos estão em [0, 1] e ambas as capacidades são legitimamente sobre
e-mail.

A palavra que separa as duas capacidades é **uma só**: o verbo. Num saco de palavras com bigramas,
esse verbo é um token entre dez. A conclusão é estrutural, não de calibração:

> **Leitura e escrita sobre o mesmo dado compartilham todos os substantivos. A direção não é
> recuperável por similaridade textual e precisa ser um sinal declarado.**

Isso também explica, em retrospecto, por que `c8f30d2` parecia correto: aquela query caía em
`AMBIGUOUS_CONFIRMATION` com margem 0.147. O sistema nunca a resolveu — a rede de segurança
pegou. Uma rede de segurança que pega o caso certo por coincidência de escala de score não é
uma garantia.

## Decisão

**Declarar a direção de cada capacidade e enforçá-la antes do ranking.**

1. Cada entrada de `CANONICAL_INTENTS` declara `"mode": "read" | "write"`. Variantes herdam a
   direção da sua canônica (verificado por teste — o colapso não pode misturar direções).
2. `taxonomy.query_direction(tokens)` deriva a direção do pedido a partir de dois léxicos de
   domínio: `WRITE_VERBS` (mutação do cadastro, do cartão ou de uma transação) e `READ_MARKERS`
   (marcadores de pergunta). Escrita tem precedência sobre leitura.
3. No ranking do retriever:
   - query de **leitura** + capacidade de **escrita** → **descarte total**;
   - query de **escrita** + capacidade de **leitura** → **rebaixamento** abaixo de todos os
     candidatos na direção correta;
   - direção indefinida (nem verbo nem marcador) → nenhuma restrição.

### A assimetria é deliberada

Alterar o cadastro de quem apenas perguntou é **dano irreversível ao cliente**. Consultar para
quem pediu alteração é **tarefa não cumprida** — recuperável com uma segunda mensagem. As duas
falhas não merecem o mesmo tratamento, e tratá-las simetricamente significaria ou ser leniente
demais com a primeira ou destruir cobertura por causa da segunda.

### Escopo dos léxicos

`WRITE_VERBS` exclui deliberadamente **"enviar"**, **"mandar"**, **"receber"** e **"gerar"**:
pedir que a fatura seja enviada não altera dado do cliente. Classificá-los como escrita rebaixaria
`consultar_fatura` (leitura) em *"me manda o boleto"* — uma regressão de 8 ferramentas.
Também fora: **"quero"** e **"preciso"**, que só introduzem o pedido (*"quero saber meu saldo"*
é leitura).

Os glossários dos pares leitura/escrita foram reescritos como **verb-forward**: os substantivos
compartilhados ("email cadastrado", "email vinculado") saíram de ambos os lados, porque não
discriminam. Uma iteração intermediária colocou essas locuções no glossário de leitura e produziu
o erro espelhado — a query de escrita passou a resolver a leitura com margem 0.60. O princípio de
autoria correto é: **o substantivo é do domínio, o verbo é da capacidade.**

## Consequências

### Medidas

| Métrica | `c8f30d2` | Após ADR-008 |
|---|---:|---:|
| Hit Rate@1 | 95% | **100%** |
| Hit Rate@2 | 100% | **100%** |
| Execuções corretas | 19/20 | **20/20** |
| Execuções incorretas | 0 | **0** |
| Confirmações por ambiguidade | 1 | **0** |
| Leitura resolvendo escrita | **sim, margem 0.47** | **impossível por construção** |
| Paráfrases fora do dataset (top-2) | 11/12 | **11/12** |

O resultado das paráfrases **não muda**. É a evidência que importa: a guarda de direção não foi
ajustada ao gabarito. Ela usa o verbo da query e a taxonomia — nunca `expected_tool`.

### Limitações

1. **A guarda só protege o que está declarado.** 59 das 285 ferramentas têm `mode`; as outras 226
   passam sem restrição. A cobertura cresce com a taxonomia, não sozinha. O lugar arquitetural
   correto para `mode` é o próprio registry — é metadado do endpoint, não da taxonomia — e
   deveria ser campo obrigatório no cadastro de qualquer ferramenta.
2. **Os léxicos são listas manuais em PT-BR.** Não cobrem erro de digitação, regionalismo nem
   negação ("não quero mudar meu e-mail" é classificado como escrita). Negação em intenção é
   problema conhecido de NLU e não se resolve com lista de verbos.
3. **O benchmark oficial deixou de exercitar as guardas 2 e 3.** Com 20/20 e zero abstenções,
   `ABSTAIN_LOW_SCORE` e `AMBIGUOUS_CONFIRMATION` não disparam em nenhuma linha do dataset. Elas
   continuam provadas pelos testes de ausência de efeito, mas não pela execução oficial — o que
   está registrado como limitação no README.

## Alternativas rejeitadas

**Renormalizar os campos globalmente.** Medida acima: reabre o problema das duplicatas não
declaradas e custa uma execução incorreta. Rejeitada por medição, não por opinião.

**Aumentar α até a escrita vencer.** Impossível: exigiria uma diferença de cosseno de 0.647 entre
glossários que descrevem o mesmo objeto. Verificado aritmeticamente, não por tentativa.

**Elevar `MIN_RELATIVE_MARGIN` para capturar o caso.** A margem do erro era 0.47, e as margens
das decisões corretas do benchmark hoje ficam entre 0.592 e 0.741 — então um limiar de, digamos,
0.55 tecnicamente separaria os dois grupos **neste dataset**. Rejeitada mesmo assim, por dois
motivos:

1. Essa separação é uma coincidência de 15 medições, não uma propriedade. Calibrar um limiar de
   segurança na folga observada entre acerto e erro de um dataset de 20 queries é ajustar ao
   gabarito por outro caminho.
2. Mais decisivo: **não resolveria o problema, só o mascararia.** A margem transformaria uma
   escrita indevida em `AMBIGUOUS_CONFIRMATION` — o sistema continuaria sem saber que o cliente
   fez uma pergunta. Com a direção declarada, a mesma consulta resolve corretamente para a
   capacidade de leitura, sem incomodar o cliente com uma confirmação.

**Quarta guarda no harness, em vez de restrição no retriever.** Bloquearia a execução, mas
deixaria o candidato errado em primeiro lugar, propagando o ranking incorreto para qualquer outro
consumidor do retriever — e transformaria em `AMBIGUOUS_CONFIRMATION` casos que a direção resolve
sozinha. A restrição no ranking corrige a ordem; as três guardas do harness continuam aplicáveis
sobre o resultado já corrigido.
