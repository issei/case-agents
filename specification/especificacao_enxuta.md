# Especificação Técnica Enxuta — Agente de Roteamento (Tool Routing & Retrieval)

## Objetivo

Implementar o núcleo lógico de um agente de roteamento de forma **simples, determinística e offline**, passando nos testes unitários e atingindo a mesma qualidade da solução densa (router accuracy 100%, Hit Rate@2 100%, 0 execuções incorretas no benchmark de queries transacionais), sem over-engineering.

- Código restrito à pasta `candidate_starter/`.
- Dependências: apenas as do `requirements.txt` original (`numpy`, `pandas`, `scikit-learn`, `pytest`).
- 100% offline (somente `data/tools_registry.json` + `data/router_training_data.json`).

## Módulos a implementar

### 1. `normalization.py` (novo, mínimo)

```python
def normalize(text: str) -> str:
    # 1. lower
    # 2. remover acentos (unicodedata)
    # 3. remover caracteres especiais desnecessários (manter letras, números e espaços)
    # 4. colapsar espaços múltiplos
    # 5. (opcional mas recomendado) aplicar dicionário mínimo de variantes ortográficas
    #    do domínio via regex ANTES das stopwords
    #    (ex.: unificar formas hifenizadas / grafias múltiplas em um token contínuo)
```

Objetivo: `"Criar Documento"`, `"criar documento"` e `"criár documénto  "` devem produzir a mesma string canônica.

### 2. `router.py`

- `TfidfVectorizer(ngram_range=(1, 2), min_df=1)`
- `LogisticRegression` (ou equivalente linear)
- **Obrigatório**: envolver com `CalibratedClassifierCV(method="sigmoid")` (Platt scaling)
- Treinar com `data/router_training_data.json` (53 exemplos, labels `FAST_PATH` / `AGENT`)
- `predict(query)` retorna `RouteResult(route, confidence, latency_ms)`
- Limiar de confiança de produção: **≥ 0.75**. Abaixo disso → `HUMAN_FALLBACK_LOW_CONFIDENCE`

**Por que a calibração?**  
Modelos lineares em dados esparsos com poucos exemplos geram probabilidades subconfiantes. Sem Platt scaling, predições corretas frequentemente ficam abaixo de 0.75 e o sistema cai no fallback indevidamente.

### 3. `retrieval.py`

Indexar `data/tools_registry.json` (285 tools).  
Schema real de cada tool: `name`, `description`, `category` (não existe campo `mode` nem `synonyms`).

**Score combinado (α = 0.5):**

```
Score = (1 - α) · Cosine(query, name + " " + description + " " + category)
      + α      · Cosine(query, intent_text)
```

Onde `intent_text` é derivado localmente (sem arquivo externo):
- `name.replace("_", " ") + " " + description`
- ou um dicionário mínimo de aliases embutido no próprio `retrieval.py`.

**Regras obrigatórias:**

1. **Stopwords customizadas** (a, o, da, de, para, com, em, do, no, na, …) — evita que queries curtas batam só em preposições.

2. **Variantes ortográficas do domínio** (Domain Vocabulary Alignment):  
   Antes de stopwords e TF-IDF, aplicar um dicionário pequeno de substituições via regex para unificar termos hifenizados ou com grafias múltiplas em um token único (preserva semântica na matriz).

3. **Colapso canônico**:  
   Agrupar tools pelo radical/canônico do `name` (heurística determinística simples, ex.: normalizar prefixos de ação + radical do objeto). Manter apenas a de maior score por grupo. O top-k deve conter **capacidades distintas**.

4. **Guarda de direção (runtime)**:
   - Inferir direção da **query** por verbos/palavras-chave:
     - read: consultar, ver, qual, mostrar, obter, listar, quanto, saldo, extrato…
     - write: atualizar, alterar, criar, deletar, bloquear, cancelar, mudar, enviar, cadastrar…
   - Inferir direção da **tool** pelo prefixo/radical do `name`:
     - read: `consultar_*`, `obter_*`, `listar_*`, `buscar_*`…
     - write: `atualizar_*`, `alterar_*`, `bloquear_*`, `criar_*`, `deletar_*`, `cancelar_*`, `enviar_*`…
   - Se query = read **e** tool = write → **score = 0** (descarte total).  
     (Assimetria deliberada: query write + tool read pode apenas rebaixar o score, não zerar.)

`search(query, k=2)` retorna `RetrievalResult` com as top-k tools distintas + scores + latência.

### 4. `harness.py` — Guard Rails + Métricas

O contrato original do harness continua sendo as três funções de métricas:

- `compute_router_metrics`
- `compute_precision_at_k`
- `compute_savings`

Além disso, a lógica de produção deve aplicar, **em ordem**, antes de qualquer execução (mock ou real):

1. **Confiança do Router** ≥ 0.75  
   → senão `HUMAN_FALLBACK_LOW_CONFIDENCE`

2. **Score mínimo do top-1** ≥ 0.10  
   → senão `ABSTAIN_LOW_SCORE`

3. **Margem relativa**  
   ```
   Margin = (Score1 - Score2) / Score1
   ```
   Se Margin < 0.25 → `AMBIGUOUS_CONFIRMATION`

Apenas se passar pelos três → autorizar a tool top-1.  
As abstenções devem ser contabilizadas no relatório (não inflar artificialmente a economia de LLM).

## Critérios de aceite

- Passar em `test_sanity.py` e nos testes adicionais criados na branch (`test_normalization.py`, `test_router.py`, `test_retrieval.py`, `test_harness_guards.py`).
- 100% offline.
- Nenhum framework de LLM, VectorDB ou orquestração complexa.
- Nenhum arquivo de taxonomia/ADR/documentação massiva (o mínimo necessário de aliases/canônicos fica embutido no `retrieval.py`).

## O que NÃO fazer

- Não criar `taxonomy.py` separado.
- Não introduzir embeddings densos, FAISS, LangChain, etc.
- Não chamar LLM real para roteamento.
- Não otimizar “economia de LLM” às custas de acerto (Goodhart).
- Não usar `expected_tool` do eval dataset dentro da lógica de produção (somente no harness de avaliação offline).

## Resultado esperado (meta de qualidade)

- Router accuracy = 100%
- Hit Rate@2 = 100%
- 0 execuções incorretas no benchmark de queries transacionais
- Economia de LLM líquida realista (~77–80%), sem inflar por abstenções indevidas

## Plano de ação da branch

1. Criar a branch a partir da main limpa (starter):
   ```bash
   git checkout -b feature/solucao-enxuta
   ```

2. Implementar na ordem:
   - `normalization.py`
   - `router.py` (com calibração)
   - `retrieval.py` (score combinado + colapso + direction guard)
   - Ajustar `harness.py` (métricas + integração dos 3 limiares)

3. Rodar continuamente:
   ```bash
   pytest candidate_starter/tests -v
   python -m candidate_starter.run_case
   ```

4. Quando todos os testes passarem e o relatório atingir a meta de qualidade, abrir PR com descrição técnica curta (máx. 1 página).

## Trade-offs a documentar no PR

- **Platt scaling (sigmoid)** em vez de temperature scaling ou isotonic: dataset pequeno → sigmoid é mais estável.
- **α = 0.5**: equilíbrio empírico que funcionou; pode ser recalibrado depois se necessário.
- **Direction guard** é a única regra semântica “hard”; todo o restante é lexical/probabilístico.
- **Colapso canônico** resolve o problema real do catálogo (duplicatas semânticas) sem precisar de um arquivo de taxonomia separado.
- **Inferência de direção pelo nome da tool** é necessária porque o registry não possui campo `mode`.