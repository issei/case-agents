# ADR-007: Calibração de Probabilidade do Router e Guarda de Margem na Seleção

- **Status:** Aceito
- **Data:** 2026-09-10
- **Decisores:** Time de Engenharia de Agentes
- **Conformidade ISM:** M2 (Limiar de Certeza), M3 (Observar — evidência antes de aprovação)

---

## 1. Contexto

### 1.1. O limiar de confiança não estava separando nada

A Seção 4 da especificação fixa `0.75` como confiança mínima para a rota `AGENT`. O harness
implementava o limiar corretamente: abaixo dele, `HUMAN_FALLBACK_LOW_CONFIDENCE` sem chamar o
retriever nem executar ferramenta.

A medição, porém, mostrou o limiar operando às cegas:

| Métrica | Valor no commit `fc830dc` |
|---|---|
| Acurácia do router | **100%** (30/30) |
| Queries `AGENT` abaixo de 0.75 | **9 de 20** |

O router **acertou todas as 30 decisões** e ainda assim 45% das queries transacionais foram
descartadas por baixa confiança. Um limiar que rejeita quase metade das decisões corretas e
nenhuma incorreta não está comprando segurança — está destruindo cobertura. E, como cada
abstenção evita uma chamada de LLM, ele inflava artificialmente a economia reportada
(87,8%) enquanto a taxa de sucesso ficava em 20%.

A causa é **subconfiança por regularização**: regressão logística L2 sobre TF-IDF esparso com
53 exemplos de treino e vocabulário de bigramas encolhe os coeficientes, e a probabilidade
resultante é uma margem encolhida, não uma estimativa de acerto. Medição por configuração:

| Configuração | Acurácia | Queries abaixo de 0.75 | Confiança mínima |
|---|---:|---:|---:|
| `LogisticRegression(C=1.0)` (padrão) | 30/30 | 30 | 0.529 |
| `LogisticRegression(C=5.0)` (commit `fc830dc`) | 30/30 | 14 | 0.613 |
| `LogisticRegression(C=20.0)` | 30/30 | 5 | 0.661 |
| `LogisticRegression(C=100.0)` | 30/30 | 1 | 0.693 |
| **`CalibratedClassifierCV(sigmoid, cv=5)` sobre `C=1.0`** | **30/30** | **1** | **0.738** |
| `CalibratedClassifierCV(isotonic, cv=5)` | 30/30 | 0 | 0.806 |

A acurácia é 100% em todas as linhas. O que muda é só quanto o modelo *diz* que sabe.

### 1.2. Top-1 executava sem verificar se era uma decisão ou um empate

Satisfeitos os guardas de confiança e de score, o harness executava `top_k_names[0]`
incondicionalmente. Não havia teste de que o top-1 fosse distinguível do top-2. Caso concreto
medido no dataset: *"Quero mudar o e-mail vinculado à minha conta"* produzia
`consultar_email_vinculado_conta` (leitura) e `atualizar_email` (escrita) praticamente
empatados. Executar o top-1 aí é apostar, não decidir.

## 2. Decisão

### 2.1. Calibrar a probabilidade em vez de afrouxar a regularização

`QueryRouter` passa a envolver a regressão logística em
`CalibratedClassifierCV(method="sigmoid", cv=5)` (Platt scaling) e **restaura `C=1.0`**, o padrão.

Elevar `C` até as probabilidades "passarem" no limiar é mover a trave: o modelo não fica mais
confiável, só mais confiante. O Platt scaling ataca a causa — ajusta uma sigmoide sobre predições
*out-of-fold*, de modo que `RouteResult.confidence` seja uma estimativa da probabilidade de
acerto. Só assim `0.75` é uma política de risco, e não um número comparado a uma escala arbitrária.

**`sigmoid`, não `isotonic`:** a calibração isotônica é não paramétrica e sobreajusta com 53
amostras — satura a confiança (mínimo 0.806, zero abstenções), reintroduzindo pelo outro lado
exatamente o problema que se quer evitar. `StratifiedKFold` sem shuffle mantém o determinismo.

O número de folds é derivado da classe minoritária em `fit()`. Abaixo de 2 exemplos por classe
(cenários de teste unitário com 4 amostras) a calibração é omitida e o modelo usa a
probabilidade bruta — a alternativa seria falhar em construir o classificador.

### 2.2. Guarda de margem relativa antes da execução

Terceiro guarda no harness, aplicado depois da confiança e do score mínimo:

```text
margem_relativa = (score_top1 - score_top2) / score_top1
margem_relativa < MIN_RELATIVE_MARGIN  ->  AMBIGUOUS_CONFIRMATION (não executa)
```

`MIN_RELATIVE_MARGIN = 0.25`. A margem é **relativa**, não absoluta, para não depender da escala
do score. Com um único candidato não há empate possível e a guarda não se aplica.

O valor tem folga larga sobre os dados observados: as 19 decisões corretas do dataset oficial têm
margem relativa entre **0.55 e 0.72**, enquanto o caso ambíguo do e-mail fica em **0.147**. Não é
um limiar espremido entre acerto e erro.

### 2.3. `INDETERMINADO` como terceiro estado do Quality Gate

`task_success_rate = None` (nenhuma query transacional no benchmark) deixa de ser tratado como
aprovação. Ausência de evidência não é evidência de segurança: um benchmark que não exercitou
nenhuma execução de ferramenta não pode aprovar um pipeline bancário.

### 2.4. Separar economia total de economia sobre queries resolvidas

O relatório passa a publicar, além de `cost_savings_pct`, o bloco `economics` com
`cost_savings_pct_on_resolved` e `deferred_to_human`. Economia obtida por abstenção não é ganho
operacional — é custo deslocado para o atendimento humano, e esse custo não está modelado neste
MVP. Publicar só o número agregado convidava exatamente a leitura errada que o commit anterior
produziu.

## 3. Consequências

### Positivas

- Fallbacks por baixa confiança no dataset oficial: **9 → 0**. Nenhuma decisão correta é
  descartada, e o limiar de 0.75 permanece intacto.
- A única query fora do top-1 vira `AMBIGUOUS_CONFIRMATION` em vez de execução incorreta:
  **0 execuções incorretas**, com `task_success_rate = 95%`.
- O Quality Gate deixa de poder ser aprovado por um benchmark vazio.
- O relatório não consegue mais apresentar economia sem expor quantas queries foram desviadas.

### Negativas / Limitações

- **A calibração é medida no mesmo dataset em que o router é avaliado.** Com 53 exemplos de
  treino e 30 de avaliação, "100% de acurácia" diz pouco sobre o mundo real. O número honesto a
  reportar é que o router não errou *neste* benchmark, não que o roteamento esteja resolvido.
- **`CalibratedClassifierCV` treina 5 modelos** em vez de 1. Irrelevante nesta escala
  (latência do `predict` inalterada), mas é custo de `fit` a considerar em retreinos frequentes.
- **`MIN_RELATIVE_MARGIN = 0.25` é uma política de produto, não uma constante universal.** O valor
  correto depende do custo relativo entre confirmar com o cliente e executar errado, e difere por
  capacidade: bloquear cartão por engano é reversível; transferir dinheiro não é. Em produção o
  limiar deveria ser por classe de risco da ferramenta, não global.
- A cobertura transacional passou a 95% e o custo do pipeline subiu proporcionalmente. É o
  trade-off correto, mas precisa ser declarado: **cobrir mais queries custa mais dinheiro.**

## 4. Conformidade com a Especificação

- **Seção 4** — o limiar de 0.75 para `AGENT` é preservado; o que mudou foi a qualidade da
  probabilidade comparada a ele.
- **Seção 3.1** — a especificação já previa "estratégia de calibração de probabilidade para
  alternativas ao `LogisticRegression`"; esta ADR aplica o princípio ao próprio `LogisticRegression`.
- **Seção 1.1 (Determinismo antes de inteligência)** — os três guardas usam apenas sinais
  disponíveis em runtime (confiança, score, margem). Nenhum consulta `expected_tool`, que
  permanece exclusivo da camada de avaliação offline.
