# Especificação Técnica Consolidada — Case Agents

## Do MVP Determinístico à Arquitetura de Produção sob a Engenharia da Confiança

> **Revisão 2 — Refinamentos de precisão aplicados:**
> (i) normalização textual obrigatória no `ToolRetriever` (Seção 3.2);
> (ii) política de compressão de janela no ReAct Loop de produção (Seção 4.4);
> (iii) estratégia de calibração de probabilidade para alternativas ao `LogisticRegression` (Seção 3.1).

---

## 1. Visão Executiva e Princípios Arquiteturais

O projeto `case-agents` implementa o cérebro de roteamento de um agente de atendimento para um banco digital fictício. O objetivo é classificar consultas localmente antes de qualquer chamada de LLM de maior custo, encaminhando consultas simples para um `FAST_PATH` e consultas operacionais para um caminho baseado em ferramentas.

A premissa central que governa toda a evolução deste sistema é extraída da Engenharia da Confiança:

> **A capacidade vem do modelo; a confiança vem da engenharia.** Um sistema de IA confiável tem muito pouca IA no caminho crítico.

O LLM não deve ser tratado como o sistema. O LLM opera dentro de um **Harness** que controla contexto, ferramentas, autorização, estado, execução, observabilidade e avaliação. A arquitetura deve transformar saída probabilística em comportamento verificável em produção.

### 1.1. Princípios Invariantes

| Princípio | Definição | Aplicação no `case-agents` |
|---|---|---|
| **Determinismo antes de inteligência** | O modelo entra somente onde regras não bastam. | Roteamento TF-IDF e recuperação lexical resolvem a maior parte das consultas sem LLM. |
| **Contratos rígidos** | A saída do LLM é input não confiável até ser validada por schema estrito que rejeita campos inesperados. | Validação de argumentos via JSON Schema / Pydantic antes de qualquer execução de tool. |
| **Separação Cérebro × Vitrine** | O motor cognitivo é um sistema; a interface exposta é outro. Eles se comunicam por contrato estreito. | O `Harness` isola o LLM das tools; o `Tool Gateway` é a única fronteira de execução. |
| **Mundo Aberto (Open-World Assumption)** | Ausência de dado é incerteza explícita, nunca “falso”. | `score < LOW_THRESHOLD` produz degradação controlada, não negação. |
| **Auditabilidade e Rastreabilidade** | Toda decisão automatizada guarda a evidência que a sustentou, em formato reexecutável. | Traces estruturados com correlation ID, session ID, candidatos recuperados, tool calls e resultado final. |
| **Spec-Driven Development** | A especificação é a fonte da verdade; o código implementa contra ela. | Este documento é o contrato executável do sistema; cada critério pode falhar. |

### 1.2. O Paradigma “Modelo + Harness”

```text
                 ┌────────────────────┐
                 │       LLM          │
                 │ decisão/raciocínio │
                 └─────────┬──────────┘
                           │
                  controlled context
                           │
                 ┌─────────▼──────────┐
                 │      Harness       │
                 │                    │
                 │ Policies           │
                 │ Guardrails         │
                 │ State              │
                 │ Tool permissions   │
                 │ Validation         │
                 │ Retry              │
                 │ Observability      │
                 │ Evaluation         │
                 └─────────┬──────────┘
                           │
                    controlled tools
```

O Harness determina: qual contexto chega ao modelo; quais ferramentas estão disponíveis; quais ferramentas podem ser executadas; quais parâmetros são válidos; quais ações exigem autorização; quantas tentativas são permitidas; como falhas são tratadas; quando o humano deve assumir; e como a execução será auditada.

---

## 2. Modelo de Referência: Engenharia da Confiança e ISM

O sistema `case-agents` é a implementação prática do **Intentional Systems Model (ISM) v1.0**, um modelo de referência que trata cada saída de IA como um artefato governado por arquitetura, não pela esperança de que o prompt acerte.

A jornada de quatro módulos do ISM estrutura a evolução do MVP para produção:

| Módulo | Foco | Artefato Gerado no `case-agents` |
|---|---|---|
| **M0 · Despertar** | Reconhecer o Crash Silencioso — falha de intenção que não gera exceção mas perde valor de negócio. | Métricas de baseline vs. pipeline inteligente que expõem economia de custo e latência. |
| **M1 · Mapear** | Congelar a verdade do sistema (As-Is) num Inventário de Comportamentos auditável. | Dataset de avaliação (`eval_dataset.json`) com rotas esperadas e tools esperadas. |
| **M2 · Arquitetar** | Determinístico-primeiro, contratos rígidos, Limiar de Certeza e MCP como fronteira de segurança. | `QueryRouter` + `ToolRetriever` + `Harness` + `Tool Gateway` com validação de schema. |
| **M3 · Orquestrar** | Escalar a intenção com Spec-Driven Development e renderização governada. | APM (Agent Packaging Manifest), skills catalogadas, traces OpenTelemetry. |

### 2.1. Limiar de Certeza

O ISM define que a recuperação percorre da camada mais específica para a mais geral e para no primeiro nível que satisfaz o **limiar_de_certeza**. Abaixo dele, a resposta não é emitida: é degradada para incerteza explícita.

No `case-agents`, essa política se traduz em:

```text
score >= HIGH_THRESHOLD  → execução normal
LOW_THRESHOLD <= score < HIGH_THRESHOLD → confirmação / validação adicional
score < LOW_THRESHOLD    → Human-in-the-Loop
```

### 2.2. Spec-Driven Development

Cada especificação versionada é um critério de aceite executável. Toda linha da seção de critérios deve virar um teste, e a especificação é considerada incompleta enquanto algum critério não tiver como reprovar. Um critério só vale se puder falhar: “melhorar a performance” não é critério; `p95 < 400 ms` é.

---

## 3. Especificação do MVP (Starter Kit)

### 3.1. Arquitetura do Roteador Local

#### Objetivo

O `QueryRouter` deve classificar cada consulta em exatamente uma das duas rotas: `FAST_PATH` ou `AGENT`. `FAST_PATH` cobre saudações, FAQs e perguntas genéricas; `AGENT` cobre consultas que exigem uma operação específica ou acesso a uma ferramenta.

#### Contrato Público

```python
class BaseRouter(ABC):
    def fit(self, texts: List[str], labels: List[str]) -> "BaseRouter": ...
    def predict(self, query: str) -> RouteResult: ...
```

```python
@dataclass
class RouteResult:
    route: str
    latency_ms: float
    confidence: Optional[float] = None
```

#### Implementação Recomendada

```text
TfidfVectorizer
      │
      ▼
LogisticRegression
      │
      ▼
FAST_PATH / AGENT
```

`TfidfVectorizer` transforma as consultas em representação lexical esparsa. `LogisticRegression` fornece um classificador supervisionado simples e uma forma direta de obter confiança através das probabilidades de classe (`predict_proba`), já normalizadas no intervalo `[0, 1]` e alinhadas com a semântica do campo `RouteResult.confidence`.

#### Estratégia de Calibração de Probabilidade

A escolha do classificador determina como a confiança será produzida. O contrato de `RouteResult.confidence` exige um valor opcional, porém quando fornecido deve ser interpretável como probabilidade normalizada em `[0, 1]`. As alternativas válidas são:

1. **`LogisticRegression` (recomendado)** — produz `predict_proba` nativamente. A confiança é a maior probabilidade entre as classes:

   ```python
   proba = clf.predict_proba(X)[0]
   confidence = float(np.max(proba))
   ```

   Nenhuma calibração adicional é necessária no MVP. O modelo é intrinsecamente calibrado para problemas lineares em espaço TF-IDF.

2. **`LinearSVC` (alternativa)** — **não produz probabilidades nativamente**. `decision_function` retorna distâncias ao hiperplano, que **não são probabilidades** e **não podem ser expostas diretamente** como `confidence` sem violar o contrato. Duas estratégias aceitáveis:

   - **(a) Calibração explícita via `CalibratedClassifierCV`** — envolver o `LinearSVC` em `CalibratedClassifierCV(base_estimator=LinearSVC(), method="sigmoid", cv=5)`. O método `sigmoid` (Platt scaling) produz probabilidades calibradas a partir de validação cruzada, mantendo a fronteira de decisão do SVM. É a opção preferida quando o `LinearSVC` for escolhido por razões de desempenho.

     ```python
     from sklearn.calibration import CalibratedClassifierCV
     from sklearn.svm import LinearSVC

     base = LinearSVC()
     calibrated = CalibratedClassifierCV(base, method="sigmoid", cv=5)
     calibrated.fit(X, y)
     confidence = float(np.max(calibrated.predict_proba(X_query)[0]))
     ```

   - **(b) Transformação monotônica de `decision_function`** — aplicar uma sigmoide sobre a distância ao hiperplano para obter um score em `[0, 1]`:

     ```python
     score = clf.decision_function(X)[0]
     confidence = float(1 / (1 + np.exp(-score)))
     ```

     Essa abordagem é aceitável para **ranking e logging**, mas **não deve ser usada para thresholds de roteamento em produção**, pois a escala não é calibrada probabilisticamente. No MVP, onde a confiança é apenas registrada, é suficiente.

3. **Regra de decisão do MVP**: se o classificador escolhido não expõe probabilidade calibrada, `confidence` deve ser `None` — nunca um valor transformado que se pretenda ser probabilístico sem calibração. O harness registra `None` e segue.

#### Validações

`fit()` deve:

1. Rejeitar listas vazias.
2. Validar que `texts` e `labels` possuem o mesmo tamanho.
3. Validar que todos os rótulos são `FAST_PATH` ou `AGENT`.
4. Treinar o modelo.
5. Somente depois do treinamento, marcar `_fitted = True`.
6. Retornar `self`.

`predict()` deve:

1. Verificar `_fitted`.
2. Rejeitar query vazia.
3. Medir a execução com `time.perf_counter()`.
4. Realizar a classificação.
5. Calcular confiança quando disponível (seguindo a estratégia de calibração acima).
6. Retornar `RouteResult`.

Antes de `fit`, deve ser produzido exatamente: `RuntimeError("Chame fit() antes de predict().")`.

#### Justificativa do TF-IDF no MVP

O problema de avaliação é pequeno, o dataset é local e o objetivo é estabelecer um baseline reproduzível. TF-IDF é leve, determinístico e explicável. Não devem ser introduzidos no MVP: embeddings, banco vetorial, reranking por LLM, chamadas externas, memória de conversação ou agentes autônomos.

---

### 3.2. Arquitetura do Retriever

#### Objetivo

O `ToolRetriever` deve selecionar as ferramentas mais relevantes para uma consulta sem enviar todo o catálogo (285 ferramentas) ao LLM.

#### Contrato Público

```python
class BaseToolRetriever(ABC):
    def fit(self, tools: List[Tool]) -> "BaseToolRetriever": ...
    def search(self, query: str, k: int = 2) -> RetrievalResult: ...
```

```python
@dataclass
class Tool:
    name: str
    description: str
    category: str

@dataclass
class ToolMatch:
    name: str
    score: float

@dataclass
class RetrievalResult:
    matches: List[ToolMatch]
    latency_ms: float
```

#### Normalização Textual Obrigatória

A normalização textual é **pré-requisito funcional do contrato do retriever**, não uma otimização opcional. O motivo é direto: o `TfidfVectorizer` opera sobre tokens exatos; `"Cartão"`, `"cartao"` e `"cartão"` produzem três representações esparsas distintas se não houver normalização prévia, o que degrada a recuperação em um domínio onde variantes tipográficas e acentuação são abundantes.

**Regra invariante:**

> Todo texto — documentos indexados em `fit()` e queries em `search()` — deve passar por **exatamente a mesma função de normalização** antes da vetorização.

A função de normalização canônica para o domínio é:

```python
import re
import unicodedata

def normalize(text: str) -> str:
    # 1. Unicode NFKD: separa caracteres base de diacríticos
    text = unicodedata.normalize("NFKD", text)
    # 2. Remove marcas combinantes (acentos)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # 3. Converte para minúsculas
    text = text.lower()
    # 4. Substitui pontuação e símbolos por espaço
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # 5. Colapsa espaços múltiplos
    text = re.sub(r"\s+", " ", text).strip()
    return text
```

Resultado esperado após normalização:

```text
"Cartão de crédito"   → "cartao de credito"
"cartao"              → "cartao"
"Cartão!"             → "cartao"
"PIX?"                → "pix"
"R$ 250,50"           → "r 250 50"
```

Assim, `"Cartão"` e `"cartao"` convergem para o mesmo token e produzem **exatamente a mesma representação esparsa** após o TF-IDF.

**Onde aplicar:**

- Em `fit()`: normalizar cada campo (`name`, `description`, `category`) **antes** da concatenação. A concatenação deve ocorrer sobre o texto já normalizado.
- Em `search()`: normalizar a query com a mesma função. Nunca usar uma normalização diferente (mesmo que “equivalente”) entre indexação e consulta — divergências mínimas causam degradação silenciosa do recall.

**Configuração complementar do `TfidfVectorizer`:** mesmo com a normalização acima, recomenda-se configurar o vetorizador com `lowercase=False`, `strip_accents=None`, `token_pattern=r"\S+"` e `ngram_range=(1, 2)`. O objetivo é delegar toda a normalização à função explícita, mantendo o comportamento do vetorizador determinístico e auditável. **Toda a lógica de normalização deve ser visível no código do projeto, não delegada implicitamente ao `TfidfVectorizer`.**

#### Representação das Ferramentas

Para o índice, deve ser criado um único documento textual por ferramenta, aplicando a normalização acima:

```text
normalize(name) + " " + normalize(description) + " " + normalize(category)
```

#### Recuperação

```text
Tool catalog → Texto normalizado → TF-IDF → Query normalizada → TF-IDF da query
    → Cosine Similarity → Ordenação decrescente → Top-k
```

O ranking deve: calcular similaridade de cosseno; ordenar por score decrescente; usar `name` como desempate; retornar no máximo `k` ferramentas. O desempate por nome mantém o comportamento determinístico.

#### Regras de Validação

`search()` deve exigir `_fitted`; rejeitar query vazia; exigir `k > 0`; limitar `k` ao tamanho do catálogo; retornar lista vazia quando o catálogo estiver vazio. Antes de `fit`, deve produzir: `RuntimeError("Chame fit() antes de search().")`.

#### Critério de Teste para Normalização

Deve existir teste unitário que verifique:

```python
def test_normalizacao_equivalente():
    r = ToolRetriever()
    r.fit([Tool(name="consultar_saldo", description="Consulta saldo da conta", category="conta")])
    m1 = r.search("Cartão", k=1).matches
    m2 = r.search("cartao", k=1).matches
    assert m1 == m2  # mesma ordem, mesmos scores
```

Esse teste é a prova executável de que o invariante de normalização está satisfeito.

---

### 3.3. Pipeline de Orquestração e Avaliação

#### Fluxo Operacional

```text
1. Query
   │
   ▼
2. QueryRouter
   │
   ├─────────────── FAST_PATH ───────────────┐
   │                                         │
   │                                    resposta local
   │
   └──────────────── AGENT ──────────────────┐
                                             │
                                             ▼
                                      ToolRetriever
                                             │
                                             ▼
                                       primeira Tool
                                             │
                                             ▼
                                    simulate_agent_llm_call
```

Independentemente da rota, a mesma consulta deve ser enviada ao `simulate_baseline_llm_call(query)` para obtenção do baseline comparável.

#### Regra Fundamental do `AGENT`

O MVP não implementa um loop autônomo. A regra é:

```text
AGENT
  → search(top-k)
  → registrar top-k
  → executar somente a primeira tool
  → chamar uma vez o mock LLM
```

Não devem ser implementados múltiplos ciclos ReAct no starter.

#### Ausência de Estado Conversacional

Não existe histórico de mensagens, sessão global, memória de longo prazo, armazenamento de embeddings ou estado de conversa. O estado fica restrito às variáveis locais do harness e aos modelos treinados pelo router e retriever.

---

### 3.4. Métricas e Relatório

#### Acurácia

```text
accuracy = acertos / total
Para lista vazia: accuracy = 0.0
```

#### Matriz de Confusão

Deve conter explicitamente as duas classes: `FAST_PATH` e `AGENT`, inclusive quando uma célula possui valor zero.

#### Precision@K

Para cada item com `expected_tool` e rota prevista `AGENT`:

```text
hit = 1 se expected_tool estiver no top-k
hit = 0 caso contrário
precision_at_k = média dos hits
Para lista vazia: precision_at_k = 0.0
```

#### Economia de Custo e Latência

```text
cost_savings_pct = (baseline_cost - smart_cost) / baseline_cost * 100
latency_savings_pct = (baseline_latency - smart_latency) / baseline_latency * 100
```

Quando o baseline for zero: `savings = 0.0`.

#### Formato do Relatório

O relatório deve ser JSON serializável e conter:

```json
{
  "n_queries": 30,
  "router_accuracy": 0.0,
  "confusion_matrix": {},
  "precision_at_k": 0.0,
  "k": 2,
  "smart_pipeline": { "total_cost_usd": 0.0, "total_latency_ms": 0.0 },
  "baseline_always_llm": { "total_cost_usd": 0.0, "total_latency_ms": 0.0 },
  "cost_savings_pct": 0.0,
  "latency_savings_pct": 0.0,
  "rows": []
}
```

O arquivo deve ser salvo em `reports/candidate_report.json` com `ensure_ascii=False` e indentação legível.

#### Critério de Aceite do MVP

```text
pytest candidate_starter/tests -v
```

Deve passar, o entrypoint executar sem exceção e o relatório esperado ser produzido.

---

## 4. Especificação da Arquitetura de Produção

### 4.1. Agent Packaging Manifest (APM) e Runtime

O APM define o contrato de empacotamento e gerenciamento do agente para produção, seguindo o padrão Microsoft Azure AI Foundry / Semantic Kernel.

```yaml
apiVersion: apm.azure.microsoft.com/v1alpha1
kind: AgentPackagingManifest
metadata:
  name: banking-router-agent
  version: "1.0.0"
  environment: "production"
  compliance:
    standards:
      - "PCI-DSS-v4.0"
      - "LGPD-BR-13709"
      - "BACEN-Resolution-4893"
      - "ISO-IEC-27001-2022"
    data_classification: "CONFIDENTIAL_PII"

runtime:
  engine: "semantic-kernel-v1"
  default_llm_deployment: "azure-openai-gpt-4o-mini"
  orchestration_pattern: "triage-and-delegate"
```

### 4.2. Roteamento e Políticas de Confiança

#### Query Router de Produção

```yaml
routing_and_policies:
  query_router:
    name: "AdaptiveConfidenceRouter"
    strategy: "hybrid_classification"  # Sparse (BM25/Regex) + Dense Embedding
    min_confidence: 0.75
    cache_policy:
      enabled: true
      ttl_seconds: 3600
      max_size: 10000
```

#### Rotas de Produção

| Rota | Descrição | Execution Target | Confiança | Fallback | SLA P99 |
|---|---|---|---|---|---|
| `FAST_PATH` | FAQs, saudações, dúvidas institucionais sem tools | `mock_llm.fast_response_engine` | 0.85 | `AGENT` | 120 ms |
| `AGENT` | Operações transacionais, dados privados, ações com catálogo de tools | `ReActOrchestrator` | 0.75 | `HUMAN_HANDOFF` | 1800 ms |
| `HUMAN_HANDOFF` | Transbordo imediato para atendente humano | `escalation_bridge` | — | — | — |

#### Condições de Acionamento do Human-in-the-Loop

```yaml
trigger_conditions:
  - "confidence < 0.75"
  - "consecutive_failures >= 2"
  - "sentiment_frustration_detected == true"
  - "security_alert_raised == true"
```

O encaminhamento deve preservar: query original, contexto relevante, intenção inferida, candidatos recuperados, scores, ações já executadas e erros encontrados. Assim, o humano recebe o contexto necessário para assumir a execução sem reiniciar todo o atendimento.

---

### 4.3. Skills e Contratos de Ferramentas (ACI e Poka-Yoke)

No MVP, uma `Tool` é apenas `Tool(name, description, category)`. Em produção, isso é insuficiente. Uma ferramenta operacional deve possuir um contrato executável e validável.

#### Estrutura Conceitual de uma Tool

```text
Tool
 ├── identity
 ├── description
 ├── purpose
 ├── input_schema
 ├── output_schema
 ├── authorization_policy
 ├── side_effects
 ├── idempotency_policy
 ├── examples
 ├── forbidden_use_cases
 └── operational_limits
```

#### Poka-yoke: Restrições Negativas Invioláveis

O Poka-yoke consiste em projetar o sistema de forma que erros previsíveis sejam impossibilitados ou fortemente dificultados. A tool deve tornar difícil para o modelo usá-la incorretamente.

Exemplo para a skill `pix_transfers`:

```yaml
negative_constraints:
  - "PROIBIDO efetuar transferência com valor menor ou igual a R$ 0.00."
  - "PROIBIDO autorizar transação sem chave de idempotência (idempotency_key)."
  - "PROIBIDO executar transferências que ultrapassem o limite diário ou noturno do BACEN sem agendamento prévio."
  - "PROIBIDO concluir operações Pix sem validação positiva de MFA/Token de segurança."
  - "PROIBIDO solicitar a devolução de transações inexistentes ou já estornadas integralmente."
```

#### Schema Estrito

Pydantic ou JSON Schema devem validar os argumentos antes de execução.

```text
LLM output → JSON Schema validation → (inválido: rejeitar | válido) → Business validation → (inválido: rejeitar | válido) → Execute
```

O schema estrutural não substitui validação de negócio.

#### Skills Catalogadas (Exemplos)

| Skill | Tipo | MFA | Scopes | Tools Mapeadas |
|---|---|---|---|---|
| `pix_transfers` | MUTATE | Biometrics ou TOTP | `pix:transfer:write`, `pix:keys:manage` | 10 tools (enviar, agendar, estornar, etc.) |
| `cards_management` | MUTATE | Step-up token | `cards:manage:write`, `cards:dispute:create` | 17 tools (bloquear, desbloquear, limite, contestar) |
| `account_info` | READ | Bearer session auth | `account:info:read`, `account:statement:read` | 11 tools (saldo, extrato, fatura, comprovante) |
| `customer_profile` | MUTATE | OTP SMS/Email step-up | `customer:profile:read`, `customer:profile:write` | 14 tools (endereço, telefone, email, renda, suporte) |

---

### 4.4. Guardrails e Controle de Execução (ReAct Loop)

#### Restrições de Segurança

Um agente bancário não pode receber autorização implícita para executar qualquer tool que consiga encontrar.

```text
User → Intent → Tool Candidate → Authorization Policy
                                      │
                              ┌───────┼───────┐
                              ▼       ▼       ▼
                            DENY  REQUIRE_CONFIRMATION  ALLOW
```

A autorização deve considerar: identidade, sessão, papel/permissão, recurso solicitado, tipo de operação, risco, limites transacionais, contexto regulatório e estado atual da conta.

#### Operações de Leitura versus Mutação

Deve existir distinção explícita entre `READ` e `MUTATE`. Operações mutáveis (bloquear cartão, alterar cadastro, transações Pix) exigem controles adicionais: step-up auth, idempotência, limites e confirmação.

#### Idempotência

Operações mutáveis precisam impedir duplicação acidental. Exemplo:

```text
request_id = abc123
```

Uma repetição da mesma solicitação deve ser reconhecida como a mesma operação quando semanticamente apropriado. Isso evita: `Retry → Transaction → Timeout → Retry → Duplicate transaction`.

#### ReAct Loop Controlado

```text
               ┌───────────────┐
               │     Model     │
               └───────┬───────┘
                       │
                     Action
                       │
                       ▼
                  Tool Gateway
                       │
                       ▼
                   Tool Result
                       │
                       ▼
                   Observation
                       │
                       └──────► Model
```

O loop deve possuir limites:

```yaml
execution_policies:
  max_iterations: 5
  timeouts:
    per_step_timeout_ms: 2500
    global_timeout_ms: 10000
  resilience:
    retries:
      max_attempts: 3
      backoff_strategy: "exponential_with_jitter"
      initial_interval_ms: 200
      multiplier: 2.0
      max_interval_ms: 1500
    circuit_breaker:
      failure_threshold_percentage: 50
      sampling_duration_seconds: 30
      minimum_requests_sampled: 10
      break_duration_seconds: 60
```

#### Política de Compressão da Janela de Contexto

O limite de 5 iterações impõe um risco silencioso: cada iteração acumula **o histórico completo de mensagens** (system prompt, query original, ações, observações de tool, resultados parciais). Se cada tool retornar payloads volumosos — extratos, listas de transações, respostas de ERPs — a janela de contexto pode ser esgotada antes da última iteração, degradando a qualidade da decisão final e elevando a latência das últimas chamadas ao modelo.

A política de compressão é, portanto, **obrigatória e explícita**:

**Regra invariante:**

> A cada iteração do ReAct Loop, o histórico de mensagens deve ser comprimido segundo uma política determinística antes de ser enviado ao modelo. Nunca se envia o histórico completo acumulado.

A política é composta por três níveis, aplicados em ordem:

**Nível 1 — Pruning Determinístico (sempre aplicado).**

- Manter **integralmente** o system prompt e a query original do usuário.
- Manter **integralmente** o par (Ação, Observação) das **duas últimas iterações**. Essas são as que sustentam a decisão seguinte.
- Truncar a **Observação** de iterações anteriores a `-2` para um resumo curto de uma linha: `{action_name, status, result_summary}`. Payloads brutos são descartados do contexto.
- Nunca truncar o system prompt, a query original ou os resultados de validação de schema/autorização — esses são parte da cadeia de custódia.

**Nível 2 — Sumarização de Iterações Antigas (quando o limite de tokens é atingido).**

- Se, após o Nível 1, o histórico ainda exceder o **orçamento de tokens por iteração** (recomendado: `max_context_tokens_per_iteration = 3000`, reservando 60% para o system prompt e a query), as iterações anteriores a `-2` são substituídas por um **resumo textual compacto** de até 150 tokens, produzido por uma chamada dedicada ao modelo com prompt determinístico do tipo: *“Resuma em até 3 bullets as ações já executadas e o estado atual. Não inclua PII. Não invente informação ausente.”*

- O resumo é armazenado no trace como `context_compaction_event` para auditoria — não é descartado.

**Nível 3 — Fallback Fail-Closed (quando a sumarização não é suficiente).**

- Se, mesmo com Nível 2, o orçamento for excedido, o loop **não continua tentando**. Ele interrompe a iteração corrente, marca o trace com `context_budget_exceeded = true` e encaminha para `HUMAN_HANDOFF` com o estado atual consolidado. Essa escolha preserva o princípio de degradação controlada: um contexto degradado não deve produzir uma decisão.

**Orçamento explícito por iteração:**

```yaml
context_window_policy:
  max_context_tokens_per_iteration: 3000
  reserve_for_system_and_query: 1800     # 60%
  reserve_for_last_two_iterations: 800   # 27%
  reserve_for_summary_buffer: 400        # 13%
  pruning_strategy: "keep_last_two_full_others_summarized"
  summarization_model: "azure-openai-gpt-4o-mini"
  fail_closed_on_exceed: true
  trace_compaction_events: true
```

**Resultado esperado:** ao final de 5 iterações, o histórico no prompt do modelo é composto de: system prompt + query original + resumo compacto das iterações `1..n-2` + pares (Ação, Observação) completos das iterações `n-1` e `n`. O crescimento do contexto é **O(1)** em relação ao número de iterações, não **O(n)**. Sem essa política, a latência da 5ª iteração seria tipicamente 2–4× a latência da 1ª devido ao volume de tokens processados; com a política, a latência se mantém aproximadamente constante.

#### Correção após Erro

O erro da tool deve ser estruturado:

```json
{
  "success": false,
  "error_code": "INVALID_CARD_STATUS",
  "retryable": false,
  "message": "..."
}
```

O modelo decide: `retryable` → corrigir argumentos; `authorization_error` → interromper; `business_error` → reformular/explicar; `unknown` → fallback.

#### Circuit Breaker

```text
CLOSED → (falhas excessivas) → OPEN → (período de recuperação) → HALF_OPEN
                                                                    │
                                                          ┌─────────┴─────────┐
                                                          ▼                   ▼
                                                       sucesso              falha
                                                          │                   │
                                                          ▼                   ▼
                                                       CLOSED              OPEN
```

---

### 4.5. Observabilidade e Avaliação Contínua

#### Por que Precision@K não basta?

Precision@K responde: “A ferramenta correta apareceu entre os candidatos?” Isso não garante: “A operação final foi correta?” Exemplo: tool correta → parâmetros incorretos → operação incorreta. A recuperação foi tecnicamente correta, mas o atendimento falhou.

#### Avaliação por Camadas

| Camada | Foco | Métricas |
|---|---|---|
| **Layer 1 — Retrieval** | Recuperação de ferramentas | Precision@K, Recall@K, ranking quality |
| **Layer 2 — Routing** | Classificação de rota | Accuracy, precision, recall, calibration |
| **Layer 3 — Tool Usage** | Uso de ferramentas | Schema validity, authorization correctness, argument correctness |
| **Layer 4 — Task Execution** | Execução da tarefa | Success/failure, business invariants |
| **Layer 5 — Final Response** | Resposta ao cliente | Factuality, completeness, policy compliance |

#### Rubricas Determinísticas e LLM-as-a-Judge

Alguns critérios não devem depender exclusivamente de um LLM Judge:

```text
Expected balance after transaction = Actual balance
Expected card status = BLOCKED | Actual card status = BLOCKED
```

Esses invariantes devem ser validados diretamente pelo sistema. O juiz LLM avalia características difíceis de transformar em regras: adequação da resposta, clareza, completude, consistência com o contexto, qualidade do atendimento.

```text
              Execution Trace
                    │
          ┌─────────┴─────────┐
          │                   │
          ▼                   ▼
 Deterministic Checks      LLM Judge
          │                   │
          └─────────┬─────────┘
                    ▼
              Final Evaluation
```

#### Traces Estruturados

Cada execução deve gerar um trace:

```text
TRACE
├── User Query
├── Router Decision
├── Retrieval (Candidate A, B, C)
├── Model Decision
├── Context Compaction Events (se houver)
├── Tool Call (Input + Authorization result)
├── Tool Response
├── Model Decision
├── Final State
└── Final Response
```

No mínimo: correlation ID, session ID, model, prompt/context version, router result, retrieval candidates, tool calls, tool inputs validados, tool outputs, erros, retries, latências, custos, resultado final. Quando houver compressão de contexto, incluir `context_compaction_event` com tokens antes/depois e estratégia aplicada (Nível 1, 2 ou 3).

#### Pipeline de Observabilidade (OpenTelemetry)

```yaml
audit_and_observability:
  pipeline:
    framework: "OpenTelemetry"
    specification_version: "1.28.0"
    exporters:
      - type: "AzureApplicationInsights"
      - type: "AzureAIFoundryTracing"
    context_propagation:
      mandatory_identifiers:
        - key: "correlation_id"
          source: "header:x-correlation-id"
        - key: "session_id"
          source: "header:x-session-id"
        - key: "final_state"
          source: "context:execution.final_state"
        - key: "selected_route"
          source: "context:router.predicted_route"
        - key: "router_confidence"
          source: "context:router.confidence_score"
    pii_redaction_and_security:
      enabled: true
      data_masking_policy: "strict_fintech_mask"
      redaction_rules:
        - name: "mask_cpf"
        - name: "mask_pan_card"
        - name: "mask_pix_key_phone"
        - name: "mask_email"
    telemetry_metrics:
      router_latency_p95_target_ms: 150
      tool_retrieval_precision_at_k: 0.90
      handoff_rate_max_threshold: 0.10
      cost_reduction_vs_direct_llm_percent: 65.0
      context_compaction_rate_target: "< 0.20"
```

#### O Trace como Instrumento de Engenharia

```text
Production Trace
      │
      ▼
Failure Analysis
      │
      ├── routing problem
      ├── retrieval problem
      ├── context problem
      ├── tool problem
      ├── policy problem
      └── model problem
      │
      ▼
Targeted Improvement
      │
      ▼
Regression Dataset
      │
      ▼
Evaluation
      │
      ▼
Production
```

Problemas reais da operação tornam-se casos de teste permanentes.

---

## 5. Integração com o Ciclo de Vida da Engenharia da Confiança

### 5.1. Do MVP à Produção: A Jornada Completa

| Dimensão | MVP (Starter Kit) | Produção (Harness Engineering) |
|---|---|---|
| **Roteamento** | TF-IDF + LogisticRegression | AdaptiveConfidenceRouter (híbrido: BM25 + embeddings densos) |
| **Normalização** | Função `normalize()` explícita e compartilhada entre index e query | Mesma função + camada de normalização linguística PT-BR |
| **Retrieval** | TF-IDF + Cosine Similarity | Hybrid Retrieval (BM25 + Vector Search) + Reranker |
| **Confiança** | `predict_proba` ou `None` (sem calibração obrigatória) | `CalibratedClassifierCV` + limiar obrigatório (0.75) |
| **Ferramentas** | Mock sem contrato | ACI com schema estrito, Poka-yoke, idempotência, autorização |
| **Loop** | Executa primeira tool + 1 chamada LLM | ReAct Loop controlado + compressão de janela + circuit breaker |
| **Estado** | Variáveis locais do harness | State Management com sessão, idempotência, ledger de quota |
| **Avaliação** | Accuracy, Precision@K, economia de custo | Camadas 1–5 + rubricas determinísticas + LLM-as-a-Judge |
| **Observabilidade** | Relatório JSON | Traces OpenTelemetry + PII redaction + regressão contínua |
| **Governança** | Nenhuma | APM, compliance PCI-DSS/LGPD/BACEN, políticas fail-closed |

### 5.2. O Que Permanece do MVP

O MVP não é descartado; ele é a **base determinística** sobre a qual a produção se assenta. Os contratos `BaseRouter`, `BaseToolRetriever`, `RouteResult`, `ToolMatch` e `RetrievalResult` são preservados como interfaces estáveis. A lógica de TF-IDF pode ser substituída por embeddings densos sem quebrar o contrato.

A regra fundamental permanece: **o LLM não é o sistema; o LLM opera dentro do Harness.** A produção adiciona camadas de segurança, confiabilidade e governança, mas não remove o princípio de que consultas simples devem ser resolvidas localmente antes de qualquer chamada cara.

### 5.3. Estrutura de Dados e Gestão de Estado

| Arquivo | Formato | Conteúdo |
|---|---|---|
| `data/tools_registry.json` | Lista de objetos | 285 tools com nome, descrição e categoria |
| `data/router_training_data.json` | Lista de objetos | 53 exemplos com `text` e `label` |
| `data/eval_dataset.json` | Lista de objetos | 30 queries com `expected_route` e `expected_tool` opcional |

**Estado da execução do harness:** variáveis locais (`y_true`, `y_pred`, `precision_hits`, totais de custo e latência, `rows`). **Estado dos componentes:** router guarda modelo ajustado e `_fitted`; retriever guarda `_tools`, índice e `_fitted`. **Persistência:** apenas o relatório final em `reports/candidate_report.json`.

---

## 6. Conclusão e Critérios de Aceite

### 6.1. Critérios de Aceite do MVP

```text
pytest candidate_starter/tests -v
python -m candidate_starter.run_case
```

1. Os testes de sanidade exigem que o router aceite treino e preveja rota válida com latência não negativa.
2. O retriever treinado deve retornar exatamente dois matches para `k=2`.
3. Testes unitários adicionais: erro antes de `fit`, tamanhos incompatíveis, `k` maior que o catálogo, `k` inválido, query vazia, desempates determinísticos, matriz de confusão, listas vazias, baseline zero.
4. **Teste de normalização:** `"Cartão"` e `"cartao"` produzem o mesmo resultado de `search()` (mesma ordem, mesmos scores) — prova executável do invariante de normalização.
5. O entrypoint executa sem exceção e o relatório é gerado em `reports/candidate_report.json`.

### 6.2. Critérios de Aceite da Produção

1. **Contratos rígidos:** toda saída de LLM passa por JSON Schema validation antes de qualquer execução.
2. **Poka-yoke:** cada skill declara restrições negativas invioláveis e limites operacionais.
3. **Autorização:** nenhuma tool mutável executa sem `Authorization Policy` explícita.
4. **Idempotência:** operações mutáveis exigem `idempotency_key` e evitam duplicação.
5. **Confiança calibrada:** roteamento com `min_confidence: 0.75`, classificadores calibrados (`CalibratedClassifierCV` quando aplicável) e fallback para `HUMAN_HANDOFF` quando abaixo do limiar.
6. **Compressão de janela:** ReAct Loop aplica política de três níveis (pruning, sumarização, fail-closed) com orçamento explícito de tokens por iteração.
7. **Observabilidade:** cada execução gera trace com correlation ID, session ID, candidatos, tool calls, erros, eventos de compactação de contexto e resultado final.
8. **Avaliação:** camadas 1–5 implementadas, com rubricas determinísticas e LLM-as-a-Judge.
9. **Governança:** conformidade com PCI-DSS, LGPD e BACEN-Resolution-4893.

### 6.3. Princípio Central

```text
Modelo
+
Contexto correto
+
Tools bem projetadas
+
Policies
+
Estado verificável
+
Observabilidade
+
Avaliação contínua
=
Agente operacionalmente confiável
```

Esse é o princípio central da **Harness Engineering** aplicado ao `case-agents`.

---

## Referências

[1]: https://github.com/caiomar/case-agents "Repositório case-agents analisado"
[2]: https://github.com/caiomar/case-agents/blob/main/README.md "README e requisitos do case"
[3]: https://github.com/caiomar/case-agents/tree/main/candidate_starter "Módulos starter de router, retrieval, harness e entrypoint"
[4]: https://github.com/caiomar/case-agents/tree/main/common "Contratos, schemas, carregadores e mocks comuns"
[5]: https://github.com/caiomar/case-agents/tree/main/data "Catálogo de tools e datasets JSON"
[6]: https://mauricio.issei.com.br/apresentacao.html "Arquitetura de IA auditável — Perspectiva Executiva"
[7]: https://mauricio.issei.com.br/engenharia-confianca.html "A Engenharia da Confiança: Da Intenção à Execução Agêntica"
[8]: https://mauricio.issei.com.br/engenharia-agentes-ia.html "Engenharia de Agentes de IA — os dez princípios"
[9]: APM.yml "Microsoft Agent Packaging & Management Manifest — banking-router-agent"