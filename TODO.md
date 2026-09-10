# Plano de Execução — case-agents

Plano de implementação estruturado de acordo com a especificação técnica (`specification/Especificação.MD`), o manifesto de empacotamento (`APM.yml`), seguindo Spec-Driven Development e Engenharia da Confiança.

### Diretrizes de Execução e Otimização de Tokens:
- **Ponytail (Anti-Bloat / Lean Code):** Seguir escada de decisão de 7 degraus (YAGNI). Soluções estritamente enxutas, sem dependências desnecessárias ou abstrações prematuras; focar no cumprimento estrito dos contratos.
- **Caveman (Comunicação de Alta Densidade):** Eliminar floreios, respostas diretas ao ponto, foco absoluto em código, dados e resultados executáveis.
- **RTK (Token Killer / Output Compression):** Manter execuções de terminal, logs e outputs concisos com alta densidade de sinal para economizar orçamento de contexto.
- **OKF Agent Memory (Git-Native Knowledge):** Estruturar a base de conhecimento no padrão Open Knowledge Format (Markdown + YAML frontmatter com progressive disclosure de ~300 tokens por conceito auditável via Git).
- **OmniRoute Gateway Pattern:** Incorporar na arquitetura de produção e ADRs os padrões de AI Gateway universal, fallback resiliente ciente de quota e compressão token-aware.

---

## Checklist de Implementação

- [x] **1. Setup e validação de imports**
  - [x] Criar e ativar ambiente virtual Python 3.12+ (`.venv`)
  - [x] Instalar dependências (`requirements.txt`: `numpy`, `pandas`, `scikit-learn`, `pytest`)
  - [x] Executar suíte inicial de testes (`pytest candidate_starter/tests -v`) registrando baseline (2 falhas esperadas por `NotImplementedError`)
  - [x] Validar integridade dos imports entre `common/`, `candidate_starter/` e `data/`

- [x] **2. Implementação da função de normalização textual única**
  - [x] Implementar a função `normalize(text: str) -> str` canônica com:
    - Decomposição Unicode NFKD
    - Remoção de acentos/marcas combinantes (`unicodedata.combining`)
    - Conversão para minúsculas (`lower()`)
    - Remoção de símbolos/pontuação substituindo por espaço (`re.sub(r"[^a-z0-9\s]", " ", text)`)
    - Colapso de múltiplos espaços (`re.sub(r"\s+", " ", text).strip()`)
  - [x] Adicionar testes unitários dedicados à normalização (ex.: equivalência `"Cartão"` vs `"cartao"`)

- [x] **3. Implementação e testes unitários do `QueryRouter`**
  - [x] Implementar `QueryRouter` com pipeline `TfidfVectorizer` + `LogisticRegression` (com probabilidades via `predict_proba`)
  - [x] Respeitar invariante: lançar explicitamente `RuntimeError("Chame fit() antes de predict().")` se `predict()` for chamado antes de `fit()`
  - [x] Validar entradas em `fit()`: rejeitar listas vazias, verificar paridade de tamanho entre `texts` e `labels`, validar se rótulos pertencem a `{"FAST_PATH", "AGENT"}`
  - [x] Validar entradas em `predict()`: rejeitar query vazia / whitespace
  - [x] Medir latência real com `time.perf_counter()` retornando `RouteResult(route, latency_ms, confidence)`
  - [x] Criar testes unitários para o router cobrindo casos limites (antes do fit, dados vazios, calibração de confiança, latência não negativa)

- [x] **4. Implementação e testes unitários do `ToolRetriever`**
  - [x] Integrar a função `normalize()` canônica compartilhada obrigatoriamente tanto em `fit()` (para `name`, `description`, `category`) quanto em `search()` (para a query)
  - [x] Montar documento textual unificado: `normalize(name) + " " + normalize(description) + " " + normalize(category)`
  - [x] Vetorização com `TfidfVectorizer(lowercase=False, strip_accents=None, token_pattern=r"\S+", ngram_range=(1, 2))` delegando normalização à função explícita
  - [x] Ranking por Similaridade de Cosseno com desempate determinístico por `name` em ordem alfabética
  - [x] Respeitar invariante: lançar explicitamente `RuntimeError("Chame fit() antes de search().")` se chamado antes de `fit()`
  - [x] Validar `search()`: rejeitar query vazia, validar `k > 0`, limitar `k` ao tamanho do catálogo, tratar catálogo vazio
  - [x] Medir latência com `time.perf_counter()` retornando `RetrievalResult(matches, latency_ms)`
  - [x] Criar testes unitários para o retriever incluindo o teste de normalização equivalente (`"Cartão"` vs `"cartao"`)

- [x] **5. Implementação das métricas de avaliação no `harness.py`**
  - [x] `compute_router_metrics(y_true, y_pred, labels)`: acurácia e matriz de confusão com chaves explícitas `FAST_PATH` e `AGENT` mesmo com zero
  - [x] `compute_precision_at_k(hits)`: média de acertos (1/0) do top-k ou `0.0` para lista vazia
  - [x] `compute_savings(smart_cost_usd, smart_latency_ms, baseline_cost_usd, baseline_latency_ms)`: cálculo percentual com proteção contra divisão por zero (`savings = 0.0` quando baseline for zero)
  - [x] Testes unitários para as métricas com casos de borda

- [x] **6. Implementação do orquestrador em `run_case.py` e geração do relatório**
  - [x] Orquestração completa: carga de dados -> fit do router -> fit do retriever -> execução do harness
  - [x] Geração do arquivo `reports/candidate_report.json` com `ensure_ascii=False` e indentação formatada (2 espaços)
  - [x] Validação do schema do relatório JSON conforme Seção 3.4 da especificação

- [x] **7. Execução completa do `pytest` com 100% de aprovação**
  - [x] Executar `pytest candidate_starter/tests -v` cobrindo todos os testes de sanidade e unitários com 100% de sucesso (23/23 testes)
  - [x] Executar `python -m candidate_starter.run_case` validando a execução fim a fim e gerando o relatório final

- [x] **8. Elaboração dos Registros de Decisões de Arquitetura (ADRs)**
  - [x] Estruturar diretório `docs/adr/` seguindo template canônico de ADR (Status, Contexto, Decisão, Consequências, Conformidade com ISM)
  - [x] Elaborar ADR-001: Estratégia de Normalização Textual Canônica Pré-Vetorização (Unicode NFKD + Regex)
  - [x] Elaborar ADR-002: Classificador Lexical Supervisionado para Query Routing (TF-IDF + LogisticRegression vs Embeddings/LLM)
  - [x] Elaborar ADR-003: Ranking Determinístico e Desempate Alfabético no Tool Retrieval
  - [x] Elaborar ADR-004: Harness de Avaliação em Camadas e Métricas de Economia (Cost & Latency Savings)
  - [x] Elaborar ADR-005: Alinhamento com o Manifesto APM e OmniRoute Gateway Pattern (Multi-provider Fallback, Quota Awareness e RTK/Caveman Token Compression)

- [x] **9. Base de Conhecimento e Melhores Práticas (Knowledge Base no padrão OKF Agent Memory)**
  - [x] Estruturar repositório de conhecimento em `docs/knowledge/` no padrão OKF (Open Knowledge Format: Markdown git-native com frontmatter YAML e progressive disclosure de ~300 tokens)
  - [x] Criar `docs/knowledge/kb-trust-engineering.md`: Guia de Boas Práticas de Engenharia da Confiança (Harness Engineering, Limiar de Certeza, Poka-Yoke)
  - [x] Criar `docs/knowledge/kb-edge-cases.md`: Catálogo de Casos de Borda e Gotchas (tratamento de acentuação em PT-BR, calibração de probabilidades, desempate determinístico)
  - [x] Criar `docs/knowledge/kb-mvp-to-production.md`: Arquitetura de Transição MVP -> Produção detalhando a jornada M0 ao M3 (ISM v1.0)
  - [x] Criar `docs/knowledge/kb-token-efficiency.md`: Guia de Eficiência de Contexto e Anti-Bloat (Princípios Ponytail, Caveman, RTK e OmniRoute na Engenharia de Prompts e Roteamento)

- [x] **10. Scripts de Execução Local para Apresentação/Demo (`run_demo.bat` e `run_demo.sh`)**
  - [x] Criar `run_demo.bat` para ambiente Windows (ativa `.venv`, valida sanidade dos testes, executa `run_case.py` e exibe o relatório gerado de forma limpa)
  - [x] Criar `run_demo.sh` para ambientes Linux/macOS equivalente
  - [x] Documentar instruções de execução rápida no `README.md` (demo em 1 clique)
