Você é um Engenheiro de Software Sênior e agente autônomo responsável pela implementação do projeto `case-agents`.

Seu objetivo neste momento NÃO é escrever o código final ainda, mas sim PREPARAR O AMBIENTE, AUDITAR O REPOSITÓRIO e CRIAR O PLANO DE EXECUÇÃO alinhado à especificação.

Siga rigorosamente os passos abaixo em ordem sequencial:

1. RECONHECIMENTO DE CONTEXTO E FONTE DA VERDADE
- Leia atentamente o arquivo `specification/Especificação.MD`. Ele é a sua FONTE ÚNICA DA VERDADE (Spec-Driven Development).
- Verifique o arquivo `APM.yml` na raiz para entender o manifesto de empacotamento do agente.
- Inspecione a estrutura existente do repositório, prestando atenção em:
  * `common/`: schemas (`Tool`, `RouteResult`, `ToolMatch`, `RetrievalResult`) e contratos abstratos (`BaseRouter`, `BaseToolRetriever`).
  * `candidate_starter/`: arquivos iniciais do router, retriever, harness e entrypoint (`run_case.py`).
  * `data/`: os arquivos JSON de treino, catálogo de ferramentas e avaliação.
  * `candidate_starter/tests/`: a suíte de testes existente.

2. CONFIGURAÇÃO E VALIDAÇÃO DO AMBIENTE PYTHON
- Verifique se o ambiente virtual Python 3.10+ está ativo (`.venv`). Se não existir, instale/crie.
- Instale as dependências declaradas em `requirements.txt` (ex: `scikit-learn`, `pytest`, etc.).
- Execute a suíte de testes inicial para registrar o estado atual (baseline de falhas/sucessos):
  `pytest candidate_starter/tests -v`

3. AUDITORIA DOS INVARIANTES DO MVP
Confirme que você assimilou as regras críticas do MVP especificadas no documento:
- Lançamento literal da exceção `RuntimeError("Chame fit() antes de predict().")` antes de chamar `fit()`.
- Implementação da função `normalize()` canônica (Unicode NFKD, remoção de acentos, lowercase, remoção de símbolos) compartilhada obrigatoriamente entre indexação e busca do `ToolRetriever`.
- Uso do algoritmo `TfidfVectorizer` + `LogisticRegression` (ou `LinearSVC` com calibração explícita via `CalibratedClassifierCV`) no `QueryRouter`.
- Desempate determinístico por `name` em ordem alfabética no ranking do retriever.
- Formato exato do relatório final em `reports/candidate_report.json`.

4. GERAÇÃO DO PLANO DE EXECUÇÃO (`TODO.md`)
Com base no levantamento, crie ou atualize o arquivo `TODO.md` na raiz do projeto com um checklist passo a passo contendo:
- [ ] Setup e validação de imports
- [ ] Implementação da função de normalização textual única
- [ ] Implementação e testes unitários do `QueryRouter`
- [ ] Implementação e testes unitários do `ToolRetriever`
- [ ] Implementação das métricas de avaliação (`accuracy`, `confusion_matrix`, `precision_at_k`, `cost_savings_pct`, `latency_savings_pct`)
- [ ] Implementação do orquestrador em `run_case.py` e geração do relatório `reports/candidate_report.json`
- [ ] Execução completa do `pytest` com 100% de aprovação

Após concluir esses 4 passos, apresente um resumo do diagnóstico do ambiente e me confirme quando estiver pronto para iniciar a implementação da primeira etapa do `TODO.md`.