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
- O baseline sempre-LLM evidenciou um desperdício massivo de latência (2747ms vs 136ms) e custo ($0.90 vs $0.20), comprovando que consultas determinísticas não devem transitar por LLMs caros.

### M1 · Mapear (Inventário de Comportamentos)
- Congelamento dos casos de teste e rotas esperadas em `eval_dataset.json` e catálogo de 285 tools em `tools_registry.json`.

### M2 · Arquitetar (Contratos e Determinismo)
- No MVP: `QueryRouter` (TF-IDF + Logistic Regression) e `ToolRetriever` (TF-IDF + Cosine Sim + Desempate Alfabético).
- Em Produção: `AdaptiveConfidenceRouter` (híbrido BM25 + embeddings densos), ACI com JSON Schema estrito e circuit breakers.

### M3 · Orquestrar (Governança e Escala)
- Integração declarativa via manifesto `APM.yml`.
- Traces distribuídos OpenTelemetry com correlação ponta a ponta e mascaramento estrito de dados sensíveis (LGPD/PCI-DSS).
