# Case Study & Whitepaper: Tool Routing & Retrieval de Alta Performance para Agentes Bancários

> **Uma Arquitetura Determinística em Camadas baseada em Spec-Driven Development (SDD) e Engenharia da Confiança**

![Testes](https://img.shields.io/badge/Testes-71%20Aprovados-success)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![Acurácia Router](https://img.shields.io/badge/Acur%C3%A1cia%20Router-100%25-brightgreen)
![Hit Rate@2](https://img.shields.io/badge/Hit%20Rate%402-100%25-brightgreen)
![Execuções Incorretas](https://img.shields.io/badge/Execu%C3%A7%C3%B5es%20Incorretas-0-success)
![Economia de Custo](https://img.shields.io/badge/Economia%20de%20Custo-77.8%25-brightgreen)
![Redução de Latência](https://img.shields.io/badge/Redu%C3%A7%C3%A3o%20de%20Lat%C3%AAncia-92.6%25-brightgreen)

---

## 1. Visão Geral e o Desafio

Em sistemas conversacionais modernos aplicados a domínios de missão crítica — como bancos digitais, fintechs e meios de pagamento —, o erro de arquitetura mais frequente e custoso é utilizar o **Large Language Model (LLM)** como o orquestrador único e síncrono de todo o fluxo de atendimento.

### O Problema do Catálogo Massivo (285 Ferramentas)
No domínio bancário deste case, o ecossistema disponibiliza **285 ferramentas operacionais** (`data/tools_registry.json`), cobrindo desde consultas simples de saldo e extrato até operações transacionais de risco (como bloqueio de cartão, contestação de compra e alteração de limites).

Injetar as descrições das 285 ferramentas diretamente na janela de contexto de um LLM a cada mensagem do usuário gera quatro gargalos estruturais:

1. **Dispersão de Atenção (*Lost-in-the-Middle*) e Alucinação**: Modelos de linguagem sofrem degradação de atenção ao tentar selecionar funções em catálogos extensos. A presença de ferramentas com semântica próxima (ex.: `consultar_fatura` vs. `pagar_fatura_cartao`) frequentemente induz a alucinações de argumentos e escolhas incorretas.
2. **Custo Financeiro Proibitivo**: Enviar dezenas de milhares de tokens de definições de ferramentas para resolver saudações informativas ("Bom dia", "Qual o horário do chat?") ou consultas diretas eleva o custo por interação em até 10x.
3. **Latência Inaceitável**: Requisições síncronas para LLMs de alta capacidade consomem entre **2.000 ms e 4.000 ms**. Para canais móveis e robôs de atendimento síncrono, esse nível de latência degrada severamente a experiência do usuário.
4. **Falta de Determinismo e Risco de Conformidade**: Ações operacionais bancárias exigem garantias formais de execução. O sistema não pode depender do humor estatístico do LLM para decidir se altera ou não o e-mail cadastrado de um cliente.

### O Motor de Roteamento Determinístico
Para resolver este desafio, construímos um **Motor Determinístico em Camadas**:
- **Fast Path (Roteamento Direto)**: Mensagens simples, saudações e FAQs são interceptadas na camada zero em **< 5 ms**, respondidas localmente sem consumo de tokens de LLM.
- **Agent Path (Recuperação Filtrada)**: Mensagens operacionais acionam um mecanismo de recuperação estatística e semântica leve que filtra as **2 ferramentas mais relevantes (Top-2)** do catálogo de 285 ferramentas.
- **Invocação Segura de LLM**: O LLM só é invocado para preenchimento de parâmetros (*slot filling*) quando a ferramenta necessária já foi identificada com alto grau de certeza e isolada do restante do catálogo.

---

## 🚀 Quickstart: Como Rodar em 1 Clique

Para validar o ambiente, executar a suíte de **71 testes unitários** e gerar o relatório do benchmark oficial:

### No Linux / macOS:
```bash
chmod +x run_demo.sh
./run_demo.sh
```

### No Windows:
```cmd
run_demo.bat
```

### Execução Manual:
```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Executar suíte de testes unitários
pytest candidate_starter/tests -v

# 3. Executar o benchmark oficial
python -m candidate_starter.run_case
```

---

## 2. A Inteligência do Motor (Core Tech)

A arquitetura do motor foi desenhada sob a premissa de **eficiência computacional máxima**: alcançar precisão perfeita sem a necessidade de manter bancos de dados vetoriais pesados (como Pinecone, Qdrant ou Milvus) ou modelos de *embeddings* em GPU no *hot path* de inferência.

```mermaid
flowchart TD
    Q[Query do Usuário] --> N[Normalização Canônica<br/>Unicode NFKD + Strip Diacritics]
    N --> R[1. Router: TF-IDF n-grams 1-2 + Logistic Regression]
    R -->|Platt Scaling Calibrated<br/>Probabilidade Real| C{Confiança >= 0.75?}

    C -->|Não / FAST_PATH| FP[Resolução Local / Mock LLM<br/>Latência < 5ms]
    C -->|Sim / AGENT| RET[2. Retriever: Cosseno Combinado + Taxonomia]

    RET --> M[Lexical TF-IDF 0.5 + Intent Glossário 0.5]
    M --> CC[Colapso Canônico de Duplicatas Semânticas]
    CC --> G[3. Guard Rails em Runtime]
```

### 2.1. O Router: Regressão Logística com Platt Scaling (`router.py`)

O classificador de intenção primária decide se a query pertence ao `FAST_PATH` ou ao `AGENT`.

* **Vetorização com N-Grams**: Utiliza `TfidfVectorizer` com unigramas e bigramas ($1, 2$) e normalização sublinear de frequência (`sublinear_tf=True`), permitindo capturar expressões compostas críticas em PT-BR (ex.: "fatura aberta", "trocar senha", "comprovante pix").
* **O Risco de Calibração e o Platt Scaling**: Classificadores lineares com regularização L2 (como `LogisticRegression`) sofrem de subconfiança em datasets pequenos, encolhendo as probabilidades estimadas (`predict_proba`) para próximo da margem neutra ($0.5$). Em um sistema com limiar rígido de corte ($\ge 0.75$), essa subconfiança causava **45% de falsos negativos (abstenções indevidas)** em decisões onde o modelo acertava a classe.
* **Solução**: Envolver o estimador em `CalibratedClassifierCV(method="sigmoid")` (Platt Scaling) treinado em esquema *out-of-fold*. Com a calibração sigmoid, o valor retornado em `RouteResult.confidence` reflete uma probabilidade calibrada de acerto, eliminando a abstenção indevida e garantindo 100% de acurácia com total segurança.

### 2.2. O Retriever: Similaridade de Cosseno Combinada e Colapso Canônico (`retrieval.py`)

A recuperação de ferramentas do catálogo de 285 itens adota um modelo híbrido estilo **BM25F / Multi-Field Search**, ponderando o texto descritivo e o glossário de intenção:

1. **Busca Multi-Campo ($0.5 \cdot \text{Lexical} + 0.5 \cdot \text{Intent}$)**:
   - **Score Léxico ($S_{\text{lex}}$)**: Similaridade de cosseno entre o vetor TF-IDF da query e o campo composto `name + description + category` da ferramenta.
   - **Score de Intenção/Glossário ($S_{\text{intent}}$)**: Similaridade de cosseno calculada separadamente contra o glossário e sinônimos expandidos da taxonomia de domínio.
   - A combinação aditiva balanceada ($\alpha = 0.5$) evita o colapso de relevância que ocorreria ao concatenar dezenas de sinônimos no documento principal (o que diluiria a norma L2 do vetor TF-IDF).

2. **Colapso Canônico de Duplicatas Semânticas**:
   - No catálogo original, 8 ferramentas representavam variações operacionais da mesma intenção de negócio (ex.: `consultar_fatura`, `enviar_pdf_fatura_atual`, `gerar_linha_digitavel_fatura`).
   - Sem o colapso, uma busca $k=2$ retornaria 2 variações redundantes da mesma tarefa, desperdiçando a janela de contexto do LLM.
   - O retriever agrupa as ferramentas na sua **Capacidade Canônica** correspondente (`taxonomy.py`), retornando $k$ capacidades distintas. A variante que gerou o maior score individual é preservada no atributo `matched_variant` para fins de auditoria e roteamento fino.

3. **Desempate Determinístico**: Em situações de pontuação idêntica, o ranking aplica ordenação alfabética pelo nome canônico da capacidade, garantindo reprodutibilidade absoluta entre execuções.

---

## 3. Engenharia da Confiança (Guard Rails)

Sistemas de IA em produção financeira não falham apenas quando "erram de classe"; falham silenciosamente quando executam uma ação não intencionada. A **Engenharia da Confiança** substitui o otimismo probabilístico por um **Harness Determinístico em 4 Camadas de Segurança**:

```mermaid
flowchart LR
    In[Query] --> G1{Camada 1<br/>Router Conf >= 0.75}
    G1 -->|Não| HB[Human Fallback / Fast Path]
    G1 -->|Sim| G2{Camada 2<br/>Retriever Score >= 0.10}

    G2 -->|Não| AB[Abstenção: Low Score]
    G2 -->|Sim| G3{Camada 3<br/>Margem Relativa >= 0.25}

    G3 -->|Não| AC[Confirmação: Ambiguidade]
    G3 -->|Sim| G4{Camada 4<br/>Guarda Direcional Leitura vs Escrita}

    G4 -->|Violação| AC
    G4 -->|Passou| EX[Execução Segura Top-1]
```

### As 4 Camadas de Segurança em Runtime

| Camada | Mecanismo | Regra / Limiar | Propósito / Erro Prevenido |
|---|---|---|---|
| **1. Confiança do Router** | Platt Scaling Probabilistic Check | $\text{Confidence} \ge 0.75$ | Impede que dúvidas do classificador primário passem para a execução agêntica, redirecionando para suporte humano ou caminho informativo. |
| **2. Relevância Mínima do Retriever** | Minimum Score Floor | $S_{\text{top1}} \ge 0.10$ | Protege contra queries fora de domínio ("Qual a capital da Mongólia?") ou compostas por *stopwords* que pontuariam residualmente contra o catálogo. |
| **3. Margem Relativa entre Candidatos** | Relative Margin Check | $\frac{S_{\text{top1}} - S_{\text{top2}}}{S_{\text{top1}}} \ge 0.25$ | Detecta empates semânticos e ambiguidades (ex.: cliente pede "extrato do cartão" quando há saldo de conta e cartão). Em vez de chutar, solicita confirmação. |
| **4. Guarda Direcional (Runtime Mode Guard)** | Verbo da Query vs. Direção da Tool | $\text{Mode}(\text{Query}) = \text{Read} \implies \text{Mode}(\text{Tool}) \ne \text{Write}$ | **Prevenção de Catástrofe de Produção**: Impede que uma consulta de leitura (ex.: *"Qual o e-mail cadastrado?"*) execute uma ação de escrita (ex.: `atualizar_email_cadastrado`). |

### A Análise Detalhada da Guarda Direcional (Camada 4)

A necessidade da Guarda Direcional foi descoberta durante os testes de estresse de fronteira:
* **Cenário de Falha Sem a Guarda**: A query *"Qual é o e-mail cadastrado na minha conta?"* gerava score $0.4795$ para a ferramenta `atualizar_email` e $0.2554$ para `confirmar_email`. A margem relativa era de $0.47$ (superior ao limiar de $0.25$).
* **O Risco**: O sistema determinava a execução automática de **alteração de cadastro** quando o cliente apenas desejava **consultar o dado**. O erro ocorria porque a ferramenta de escrita repetia as palavras chaves ("e-mail", "cadastrado", "conta"), sobrepujando a sutil variação verbal de leitura/escrita no espaço TF-IDF.
* **A Solução Determinística**: O parser extrai a intenção verbal da query. Se a intenção é de leitura (`read`), qualquer capacidade cadastrada como escrita (`write`) tem seu score zerado ou é filtrada antes do ranking. Essa regra de runtime zerou os riscos transacionais sem impactar a latência.

---

## 4. Uma Base, Duas Filosofias

Este repositório documenta duas abordagens arquiteturais completas para o mesmo problema matemático. Ambas atingem as métricas de excelência no benchmark, mas refletem trade-offs distintos no ciclo de vida do software:

```
                          ┌─────────────────────────────────────────┐
                          │   PROBLEMA COMPARTILHADO & CORE TECH   │
                          │   285 Tools | TF-IDF + Platt Scaling   │
                          │   100% Router | 100% Hit Rate@2 | 0 Errors│
                          └────────────────────┬────────────────────┘
                                               │
                      ┌────────────────────────┴────────────────────────┐
                      ▼                                                 ▼
        ┌───────────────────────────┐                     ┌───────────────────────────┐
        │  solucao-sdd-vibe         │                     │  feature/solucao-enxuta   │
        │  (Mission-Critical / SDD) │                     │  (Lean / Pragmatic)       │
        ├───────────────────────────┤                     ├───────────────────────────┤
        │ • Módulo taxonomy.py      │                     │ • Taxonomia no retriever  │
        │ • 9 ADRs formalizados     │                     │ • Código enxuto / minimal │
        │ • Manifesto APM.yml       │                     │ • Foco em entrega rápida  │
        │ • Harness com Quality Gate│                     │ • Testes unitários diretos│
        └───────────────────────────┘                     └───────────────────────────┘
```

### Tabela Comparativa de Trade-offs

| Dimensão Arquitetural | Abordagem SDD / Mission-Critical (`solucao-sdd-vibe`) | Abordagem Lean / Pragmática (`feature/solucao-enxuta`) |
|---|---|---|
| **Filosofia Central** | Spec-Driven Development, Governança, Auditabilidade | Minimalismo, Baixa Fricção, Entrega Rápida de MVP |
| **Estrutura de Código** | Modular: `taxonomy.py`, `router.py`, `retrieval.py`, `harness.py` desacoplados | Compacta: Regras de taxonomia e expansão embutidas diretamente no `retrieval.py` |
| **Gestão de Decisões** | 9 ADRs formais ([`docs/adr/`](docs/adr/)) documentando motivações e descartes | Decisões expressas diretamente no código e em *commit messages* |
| **Conformidade Enterprise** | Especificação [`APM.yml`](APM.yml) (PCI-DSS v4.0, LGPD, BACEN 4893) e Base OKF | Foco no cumprimento rigoroso do contrato do desafio |
| **Manutenibilidade em Escala** | Alta em times grandes (mudanças de taxonomia não afetam lógica do retriever) | Alta em times pequenos (menos arquivos e abstrações para navegar) |
| **Velocidade de Modificação** | Requer atualização de especificações e contratos de governança | Alteração direta no código com resposta imediata dos testes |

---

## 5. Arquitetura para Produção de Alta Demanda (OmniRoute Gateway Pattern)

Para transpor o protótipo Python para um ecossistema bancário corporativo capaz de processar **milhares de Requisições por Segundo (RPS)** com **latência p99 previsível (< 1–3 ms)** e zero dependência de runtime Python no caminho crítico, projetamos a **Arquitetura Multi-Linguagem com Desacoplamento Cold/Hot Path** ([ADR-009](docs/adr/0009-arquitetura-multi-linguagem-inferencia-alta-performance.md)).

📄 **Documento Completo de Referência**: Consulte a [Proposta de Arquitetura Multi-Linguagem: Tool Routing & Retrieval de Alta Performance](docs/architecture/proposta-arquitetura-multi-linguagem.md) para a especificação detalhada de baixo nível.

```mermaid
flowchart TD
    subgraph ColdPath [Cold Path: Treinamento & MLOps (Python 3.12 Offline/CI)]
        TD[Data: router_training & tools_registry] --> TR[Treinamento: scikit-learn]
        TR --> TF[TF-IDF Vectorizer + Platt Scaling]
        TF --> EXP[Exportador Determinístico de Artefatos]
        EXP -->|Model Export| ONNX[Modelo Router .onnx / Pesos Nativos]
        EXP -->|Vocab Export| VOC[Vocabulário & Pesos TF-IDF JSON/Protobuf]
        EXP -->|Matrix Export| DOCS[Matriz CSR Pré-computada de Docs]
        EXP -->|Taxonomy Export| TAX[Taxonomia, Stopwords & Regras Read/Write]
    end

    subgraph HotPath [Hot Path: OmniRoute Gateway de Inferência (Rust / Go Online)]
        REQ[Cliente / App Bancário] -->|gRPC / HTTPS mTLS| GW[OmniRoute Gateway - Stateless]
        GW --> SEC[1. Auth mTLS/JWT + Rate Limiting]
        SEC --> NORM[2. Normalização Canônica Unicode NFKD]
        NORM --> ONNX_RT[3. Router: Projeção TF-IDF + Platt Sigmoid]
        
        ONNX_RT -->|Confiança >= 0.75| RUST_RET[4. Retriever: Cosseno Lexical 0.5 + Intent 0.5]
        ONNX_RT -->|Confiança < 0.75| FP[Fast Path Local / Fallback Humano]
        
        RUST_RET --> GR{5. Guard Rails em Runtime}
        GR -->|Score >= 0.10 & Margem >= 0.25 & Read==Read| PASS[Top-1 Tool Selecionada]
        GR -->|Violação / Ambiguidade| CONF[Abstenção / Confirmação]
    end

    ONNX -.->|Deploy / Hot-Reload| ONNX_RT
    VOC -.->|Memory-Map| ONNX_RT
    DOCS -.->|Matriz CSR em Memória| RUST_RET
    TAX -.->|ArcSwap State| GR
    PASS -->|Payload Enxuto < 2ms| LLM[LLM Engine: Slot Filling Apenas]
```

### 5.1. Segregação Rígida: Cold Path vs. Hot Path

* **Cold Path (Pesquisa, Treinamento e MLOps em Python 3.12)**:
  - Responsável exclusivo por engenharia de features, treino com `scikit-learn`, calibração via `CalibratedClassifierCV` (Platt Scaling), validação cruzada, SHAP e testes adversariais.
  - Exporta artefatos imutáveis versionados: grafo ONNX, vocabulário TF-IDF com pesos IDF, matriz esparsa CSR dos 285 documentos do catálogo e regras de normalização.
  - **O runtime de produção nunca importa Python, numpy ou scikit-learn**.
* **Hot Path (Gateway de Inferência em Rust ou Go)**:
  - Ponto de entrada único via gRPC/HTTP-2 stateless com binário compilado nativo.
  - Motor de inferência embutido (*in-process*), eliminando saltos de rede ou IPC. Executa normalização, vetorização TF-IDF, inferência linear, busca vetorial e guard rails inteiramente em memória RAM.

### 5.2. Escolha da Stack Tecnológica: Rust vs. Go

* **Rust (Recomendado Primário)**:
  - **Zero Garbage Collection**: Ausência total de pausas de GC, assegurando latência p99 determinística e ultra-baixa (< 1–3 ms) sob carga extrema de concorrência.
  - **Zero-Allocation Hot Path**: Utilização de pools de buffers e arenas (`tokio` async + `rayon`), eliminando alocações dinâmicas de heap por requisição.
  - **Memory Safety Bancária**: Garantia em tempo de compilação contra data races e vazamentos de memória em ambientes regulados.
  - **Binário Único**: Container `distroless` mínimo (~20 MB) com superfície de ataque reduzida.
* **Go (Alternativa Secundária Viável)**:
  - Opção pragmática caso a equipe já domine o ecossistema Go. Exige disciplina estrita de pooling (`sync.Pool`) para mitigar jitter do GC na manipulação de strings e vetores.

### 5.3. Portabilidade do Modelo (O Gargalo Matemático)

Por ser um classificador linear com calibração sigmoide, a portabilidade é simples e matematicamente exata:
1. **Fase 1 (Adoção Rápida)**: Exportação via `skl2onnx` e inferência no Gateway através do `onnxruntime` oficial (crate `ort` em Rust). Risco de divergência zero.
2. **Fase 2 (Ultra-Performance Nativa)**: Projeção esparsa de vocabulário via hash table estática (*Perfect Hash* / `phf`), produto escalar ($w^T x + b$) e aplicação direta da sigmoid de Platt em Rust puro. Latência de inferência < 50 microsegundos.
3. **Retriever Pré-computado**: As 285 ferramentas têm seus vetores TF-IDF (Léxico e Glossário de Intenção) pré-computados e serializados em matriz esparsa CSR durante o build. O cálculo em runtime é uma multiplicação matriz-vetor esparsa paralela.

### 5.4. Ciclo de Vida da Requisição (SLA: < 1–3 ms p99)

```
[Cliente / App] ──> (1) gRPC Request
                ──> (2) Autenticação mTLS / JWT + Rate Limiting
                ──> (3) Normalização Canônica (Unicode NFKD + Regex)
                ──> (4) Vetorização TF-IDF Esparsa em Memória
                ──> (5) Router: Inferência Linear + Platt Sigmoid (Confiança)
                ──> (6) Guard Rail 1: Confiança >= 0.75?
                ──> (7) Retriever: Cosseno Combinado (0.5*Lexical + 0.5*Intent) sobre Matriz CSR
                ──> (8) Guard Rails 2, 3 e 4: Score >= 0.10, Margem >= 0.25 e Guarda Direcional (Read != Write)
                ──> (9) Montagem do Payload de Decisão
                ──> (10) Resposta de Baixa Latência (< 2ms) para o Orquestrador / Slot Filling
```

### 5.5. Pipeline MLOps e Deploy Zero-Downtime

* **Testes de Paridade Automáticos**: A cada commit, a esteira de CI/CD roda 1.000 queries sintéticas e verifica paridade estrita entre o modelo Python e a engine Rust ($|\text{Score}_{\text{Python}} - \text{Score}_{\text{Rust}}| < 10^{-5}$).
* **Hot-Reload de Catálogo**: Modificações no catálogo de ferramentas (descrições, sinônimos, categorização leitura/escrita) regeram a matriz de documentos sem retreinar o classificador, recarregando o estado em memória via `ArcSwap` sem reiniciar o Gateway.

---

## 6. Resultados e Conclusão

O benchmark foi executado sobre o dataset oficial de teste de 30 consultas (`data/eval_dataset.json`) contra o catálogo de 285 ferramentas.

### Tabela de Métricas do Benchmark

| Métrica | Baseline (Mandar tudo pro LLM) | Pipeline Inteligente (Este Case) | Impacto / Ganho |
|---|---|---|---|
| **Acurácia do Router** | N/A | **100.0%** | Precisão absoluta na classificação |
| **Hit Rate@1 do Retriever** | N/A | **100.0%** | Ferramenta correta no topo em 100% dos casos |
| **Hit Rate@2 do Retriever** | N/A | **100.0%** | Cobertura perfeita do catálogo de 285 tools |
| **Taxa de Execuções Incorretas** | Alta (Alucinações) | **0.0% (0 falhas)** | **Zero erro em operações transacionais** |
| **Custo por Bateria (30 queries)** | $0.90000 | **$0.20003** | **77.8% de Economia de Custo** |
| **Latência Média de Resposta** | 2.741,3 ms | **203,6 ms** | **92.6% de Redução de Latência** |
| **Quality Gate Status** | N/A | **APROVADO** | Rótulo: `MVP_BENCHMARK_ONLY` |

### Conclusão

A implementação deste case comprova que a eficiência e a segurança em arquiteturas de IA agêntica não dependem de modelos cada vez maiores ou de infraestruturas complexas de bancos vetoriais.

Através da combinação disciplinada de **modelos lineares calibrados**, **recuperação baseada em taxonomia de domínio** e **guard rails determinísticos em runtime**, foi possível eliminar completamente as execuções incorretas, reduzir a latência em mais de 90% e cortar custos em cerca de 78%.

> *"A capacidade vem do modelo; a confiança vem da engenharia."*

---

## 🏛️ Documentação Técnica e Referências de Arquitetura

* [**Especificação Técnica Consolidada**](specification/Especificação.MD): Requisitos formais, contratos de API e invariantes do sistema.
* [**Proposta de Arquitetura Multi-Linguagem: Tool Routing & Retrieval de Alta Performance**](docs/architecture/proposta-arquitetura-multi-linguagem.md): Documento técnico completo de arquitetura para produção (Cold vs. Hot Path, Rust/Go, ONNX, Matrizes CSR e MLOps).
* [**Registros de Decisão de Arquitetura (ADRs)**](docs/adr/):
  * [ADR-001: Normalização Textual Canônica](docs/adr/0001-normalizacao-textual-canonica.md)
  * [ADR-002: Classificador Lexical para Query Routing](docs/adr/0002-classificador-lexical-query-routing.md)
  * [ADR-003: Ranking Determinístico no Retrieval](docs/adr/0003-ranking-deterministico-tool-retrieval.md)
  * [ADR-004: Harness de Avaliação e Métricas](docs/adr/0004-harness-avaliacao-metricas-economia.md)
  * [ADR-005: Alinhamento APM e OmniRoute Gateway](docs/adr/0005-alinhamento-apm-e-omniroute-gateway.md)
  * [ADR-006: Taxonomia de Capacidades e Colapso de Duplicatas](docs/adr/0006-taxonomia-de-capacidades-e-colapso-de-duplicatas.md)
  * [ADR-007: Calibração de Probabilidade e Guarda de Margem](docs/adr/0007-calibracao-de-probabilidade-e-guarda-de-margem.md)
  * [ADR-008: Guarda Direcional (Leitura vs Escrita)](docs/adr/0008-guarda-de-direcao-leitura-escrita.md)
  * [ADR-009: Arquitetura Multi-Linguagem para Inferência de Alta Performance](docs/adr/0009-arquitetura-multi-linguagem-inferencia-alta-performance.md)
* [**Base de Conhecimento Operacional (OKF Knowledge Base)**](docs/knowledge/):
  * [Guia de Transição MVP para Produção (ISM v1.0)](docs/knowledge/kb-mvp-to-production.md)
  * [Guia de Boas Práticas de Engenharia da Confiança](docs/knowledge/kb-trust-engineering.md)
  * [Catálogo de Casos de Borda e Edge Cases](docs/knowledge/kb-edge-cases.md)
  * [Guia de Eficiência de Tokens e Anti-Bloat](docs/knowledge/kb-token-efficiency.md)
* [**Manifesto Enterprise Packaging (`APM.yml`)**](APM.yml): Mapeamento de compliance LGPD, PCI-DSS v4.0 e BACEN 4893.

