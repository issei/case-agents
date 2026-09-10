# ADR-006: Taxonomia de Capacidades, Colapso de Duplicatas e Recuperação Multi-Campo

- **Status:** Aceito
- **Data:** 2026-09-10
- **Decisores:** Time de Engenharia de Agentes
- **Conformidade ISM:** M2 (Arquitetar — Contratos rígidos, Tool Gateway como fronteira de segurança)
- **Substitui:** o enriquecimento por concatenação de aliases introduzido no commit `fc830dc`

---

## 1. Contexto

O `ToolRetriever` do MVP recuperava no nível de **endpoint bruto** sobre `data/tools_registry.json`
(285 ferramentas). A medição do commit `fc830dc` mostrou Hit Rate@2 de **35%** e 7 execuções
com ferramenta incorreta em 20 queries transacionais.

A causa não é qualidade de vetorização. É **duplicata semântica no catálogo**: várias
ferramentas operacionais expõem a mesma capacidade de negócio com nomes hiperespecíficos
que repetem literalmente o vocabulário da query do cliente.

Amostra verificada no catálogo:

| Capacidade de negócio | Ferramentas que a realizam |
|---|---|
| Obter a fatura atual | `consultar_fatura`, `consultar_valor_fatura_mes_atual`, `consultar_valor_total_fatura`, `gerar_linha_digitavel_fatura`, `gerar_pdf_fatura_mes_atual`, `enviar_pdf_fatura_atual`, `enviar_boleto_fatura_email`, `reenviar_fatura_email` |
| Abrir chamado de suporte | `abrir_chamado_suporte`, `abrir_chamado_suporte_app_travando`, `abrir_chamado_travamento_app`, `registrar_chamado_aplicativo_travando`, `reportar_aplicativo_travando`, `reportar_problema_aplicativo` |

A descrição de `consultar_fatura` é *"Gera o PDF ou linha digitável da fatura do mês atual"* —
ou seja, a capacidade canônica **subsome** as variantes. Ainda assim, para a query
*"Manda o pdf da minha fatura atual"*, `enviar_pdf_fatura_atual` vencia por casamento literal
de nome. Esse é o estado normal de um registry que cresceu por squad ao longo de anos, não um
artefato do dataset.

A primeira tentativa de correção concatenava um bloco de sinônimos ao documento da ferramenta
canônica. **Não funcionou, e a razão é mecânica:** o TF-IDF normaliza o vetor do documento por
norma L2. Acrescentar 15 termos ao documento aumenta a norma e **reduz** o peso relativo dos
termos originais. O ganho medido foi de 15% para 35% de Hit Rate@2, contra a alegação de ~85%
que constava no docstring — alegação não verificada, removida nesta revisão.

## 2. Decisão

Introduzir uma camada de **governança de catálogo** em `candidate_starter/taxonomy.py` e mover
a recuperação do nível de endpoint para o nível de **capacidade**.

### 2.1. Contrato da taxonomia

```text
intenção canônica -> aliases (glossário do usuário) -> variantes operacionais
```

`CANONICAL_INTENTS` declara, por capacidade, dois campos com papéis distintos:

- **`variants`**: ferramentas do catálogo que executam a MESMA capacidade. No ranking, o grupo
  colapsa: a capacidade recebe o MAIOR score entre seus membros e é apresentada pelo nome
  canônico. O membro que efetivamente casou é preservado em `ToolMatch.matched_variant` para
  auditoria.
- **`aliases`**: glossário de domínio PT-BR indexado como **campo de recuperação separado** —
  nunca concatenado ao documento da ferramenta, precisamente pelo efeito de norma L2 descrito
  acima.

### 2.2. Scoring multi-campo (padrão BM25F)

```text
score = (1 - alpha) * lexical + alpha * intent        alpha = 0.5
```

Ambos os termos são cosseno TF-IDF em `[0, 1]`, então o score composto permanece em `[0, 1]` e
`min_score` continua interpretável. `alpha = 0.5` significa "os dois campos pesam igual" — é uma
escolha declarada, não um valor buscado até o benchmark passar. Com `alpha = 0.6` o dataset
oficial atinge 20/20 em top-1, mas a diferença vem de desempatar um caso genuinamente ambíguo
por 0.005 de margem; esse caso pertence à guarda de margem do harness, não ao peso.

### 2.3. Invariantes de autoria (verificadas em `tests/test_taxonomy.py`)

1. Toda `canonical` e toda `variant` existe em `data/tools_registry.json`.
2. Nenhuma ferramenta pertence a duas capacidades.
3. Uma `canonical` nunca é `variant` de outra capacidade.
4. **Leitura e escrita não se agrupam.** `consultar_email_vinculado_conta` (leitura) não é
   variante de `atualizar_email` (escrita), ainda que sejam lexicalmente vizinhas.
   Agrupá-las faria o retriever executar uma escrita quando o cliente pediu uma leitura.
5. O glossário é autorado a partir do domínio bancário, **não** do `eval_dataset.json`.

### 2.4. Evidência executável contra ajuste ao gabarito

A invariante 5 não é auditável por leitura. `tests/test_taxonomy.py::test_paraphrases_outside_dataset_generalize`
avalia 12 paráfrases escritas com vocabulário que **não** aparece no dataset oficial
(*"Fui roubado, cancela meu cartao ja"*, *"Recebi o plastico novo, preciso habilitar"*).
Se o retriever só acertasse as 20 queries oficiais, a taxonomia seria um gabarito disfarçado.
Resultado medido: **9/12 em top-1, 11/12 em top-2**.

### 2.5. Correções de tokenização decorrentes

Duas falhas foram expostas ao medir o novo pipeline e corrigidas na preparação de texto do
retriever (aplicada identicamente a índice e query, preservando a invariante da Seção 3.2):

- **Stopwords PT-BR.** Sem removê-las, a query *"qual a capital da mongolia interior"* pontuava
  **0.132** contra `gerar_linha_digitavel_fatura` (*"Gera **a** linha digitável **da** fatura"*),
  **atravessando** o limiar de abstenção de 0.10 apoiada só em `"a"` e `"da"`. Isso é falha de
  segurança, não de recall: uma query sem sentido não pode chegar à camada de execução.
- **Variante ortográfica `e-mail`.** `normalize()` converte o hífen em espaço, produzindo os
  tokens `"e mail"`; o `"e"` é então removido como conjunção e a query perde a palavra inteira.
  Medido: score lexical ≈ 0 para `atualizar_email` na query *"Quero mudar o e-mail vinculado à
  minha conta"*. A dobra `"e mail" -> "email"` é a mesma classe de operação que a dobra de
  acentos já prevista na ADR-001.

`common/normalization.py` **não foi alterada** — é contrato fixo da especificação (Seção 3.2).
Ambas as correções vivem em `candidate_starter/retrieval.py`.

## 3. Consequências

### Positivas

- Hit Rate@2 no dataset oficial: **35% → 100%**; Hit Rate@1: **95%** (19/20).
- Execuções com ferramenta incorreta: **7 → 0**. A única query que não fica em top-1
  (*"Quero mudar o e-mail vinculado à minha conta"*) é desviada para
  `AMBIGUOUS_CONFIRMATION` pela guarda de margem — não é executada errada.
- `search(q, k=2)` passa a devolver 2 capacidades **distintas** em vez de 2 duplicatas da mesma,
  o que é estritamente mais informativo para o contexto enviado ao LLM.
- `ToolMatch.matched_variant` dá trilha de auditoria: registra qual endpoint concreto casou com
  a query, mesmo quando a decisão é reportada no nível de capacidade.

### Negativas / Limitações

- **A taxonomia é um artefato mantido à mão.** 12 capacidades e 34 variantes hoje; um catálogo
  de milhares de ferramentas exige derivação assistida (clusterização de embeddings com revisão
  humana) e um processo de governança no ciclo de vida do registry. As invariantes automatizadas
  reduzem, mas não eliminam, o custo de manutenção.
- **Mudança de contrato de métrica.** O ranking agora opera sobre capacidades. Uma variante
  nunca aparece no resultado. Se a avaliação exigisse a tool operacional exata, esta decisão
  precisaria ser revertida — ver Seção 4.
- **Cobertura de paráfrase é o teto do lexical.** 9/12 em top-1 fora do dataset. O caso que falha
  (*"Fui morar em outro bairro, cadastra o novo lugar"*) usa vocabulário ausente do catálogo e do
  glossário. Nenhum ajuste de peso resolve isso; a resposta é recuperação densa (ADR de produção).
- **Economia de custo caiu de 87,8% para 78,9%** — e isso é correto. A economia anterior vinha de
  9 abstenções que não deveriam existir (ver ADR-007). Cobrir mais queries custa mais.

## 4. Alternativa considerada e rejeitada

**Tratar apenas o nome canônico como correto e priorizá-lo deliberadamente no ranking**
(opção B da análise de continuidade). Rejeitada: exigiria um bônus arbitrário para o nome
canônico sem justificativa de negócio, e não explicaria *por que* `enviar_pdf_fatura_atual` é
uma resposta pior. O colapso por capacidade explica: as duas ferramentas fazem a mesma coisa, e
o registry expõe uma delas como interface. A regra vale para queries que o dataset não contém.

## 5. Conformidade com a Especificação

- **Seção 3.2** — `normalize()` permanece a função canônica única, aplicada a índice e query.
- **Seção 1.1 (Contratos rígidos)** — a taxonomia é um contrato declarado e verificado por testes,
  não heurística implícita no ranking.
- **Seção 4 (Tool Gateway)** — o colapso por capacidade é a versão MVP do que, em produção, é o
  gateway que expõe capacidades e resolve o endpoint concreto na camada de autorização.
