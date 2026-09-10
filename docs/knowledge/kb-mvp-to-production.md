---
id: kb-mvp-to-production
title: Arquitetura de Transição do MVP para Produção (ISM v1.0)
tags: [architecture, ism, production-readiness, apm, evolution]
progressive_tokens: 330
version: 1.0.0
standard: Google OKF v0.2
---

# Arquitetura de Transição: MVP para Produção

A evolução do `case-agents` obedece aos quatro módulos do **Intentional Systems Model (ISM v1.0)**:

### M0 · Despertar (Baseline vs Smart Pipeline)
- O baseline sempre-LLM evidenciou desperdício de latência (2747ms vs 132ms) e custo ($0.90 vs $0.20), comprovando o valor de rotas determinísticas locais (`FAST_PATH`).
- **Diagnóstico Empírico Crítico:** O benchmark revelou também que um retriever puramente léxico atinge apenas 15% de precisão no top-2 devido ao descompasso taxonômico entre o dataset e as 285 tools operacionais do catálogo, demonstrando que economia sintética sem precisão de negócio é um risco operacional.

### M1 · Mapear (Inventário de Comportamentos)
- Congelamento dos casos de teste e rotas esperadas em `eval_dataset.json` e catálogo de 285 tools em `tools_registry.json`.
- Mapeamento das inconsistências entre rótulos canônicos (ex.: `bloquear_cartao`) e ferramentas hiperespecíficas (ex.: `solicitar_bloqueio_preventivo_cartao`).

### M2 · Arquitetar (Contratos e Determinismo)
- No MVP: `QueryRouter` (TF-IDF + Logistic Regression), `ToolRetriever` com suporte a `min_score` para abstention e desempate determinístico, e Harness com contabilidade de taxa de acerto de execução.
- Em Produção: Tabela de Aliases canônicos, busca híbrida (BM25 + Dense Embeddings), Reranker contextual, ACI com JSON Schema estrito, circuit breakers e política ativa de `HUMAN_FALLBACK`.

### M3 · Orquestrar (Governança e Escala)
- Integração declarativa via manifesto `APM.yml` (especificação alvo de governança empresarial).
- Traces distribuídos OpenTelemetry com correlação ponta a ponta e mascaramento estrito de dados sensíveis (LGPD/PCI-DSS).
