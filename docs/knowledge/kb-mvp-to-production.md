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
- **Diagnóstico Empírico Crítico:** um retriever puramente léxico atinge 15% de Hit Rate no top-2 sobre as 285 tools do catálogo, porque o catálogo contém duplicatas semânticas cujos nomes hiperespecíficos repetem o vocabulário da query. Declarar a governança de capacidades e recuperar nesse nível levou a métrica a 100% (ADR-006). A lição que permanece: **economia de custo sem taxa de sucesso é risco operacional disfarçado de eficiência** — os 87,8% de economia medidos em uma iteração intermediária vinham de abstenções indevidas, com apenas 20% de execuções corretas.

### M1 · Mapear (Inventário de Comportamentos)
- Congelamento dos casos de teste e rotas esperadas em `eval_dataset.json` e catálogo de 285 tools em `tools_registry.json`.
- Mapeamento das inconsistências entre rótulos canônicos (ex.: `bloquear_cartao`) e ferramentas hiperespecíficas (ex.: `solicitar_bloqueio_preventivo_cartao`).

### M2 · Arquitetar (Contratos e Determinismo)
- No MVP: `QueryRouter` (TF-IDF + Logistic Regression), `ToolRetriever` com suporte a `min_score` para abstention e desempate determinístico, e Harness com contabilidade de taxa de acerto de execução.
- Em Produção: Tabela de Aliases canônicos, busca híbrida ponderada (Lexical + Intent), serialização matricial de documentos, ACI com JSON Schema estrito, circuit breakers e política ativa de `HUMAN_FALLBACK`.

### M3 · Orquestrar (Governança e Escala)
- Integração declarativa via manifesto `APM.yml` (especificação alvo de governança empresarial).
- **Arquitetura Multi-Linguagem (Cold vs Hot Path)**: Transição do pipeline Python de treinamento offline para o OmniRoute Gateway nativo em **Rust** (ou **Go**) no hot path de inferência, atingindo latência p99 < 1-3ms sem pausas de GC ([ADR-009](../adr/0009-arquitetura-multi-linguagem-inferencia-alta-performance.md) e [Proposta de Arquitetura Multi-Linguagem](../architecture/proposta-arquitetura-multi-linguagem.md)).
- Traces distribuídos OpenTelemetry com correlação ponta a ponta e mascaramento estrito de dados sensíveis (LGPD/PCI-DSS).
