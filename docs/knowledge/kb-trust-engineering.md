---
id: kb-trust-engineering
title: Guia de Engenharia da Confiança para Sistemas de Agentes
tags: [trust-engineering, harness, poka-yoke, certainty-threshold, ism]
progressive_tokens: 320
version: 1.0.0
standard: Google OKF v0.2
---

# Engenharia da Confiança e Harness Engineering

### 1. O Princípio da Separação Cérebro × Vitrine
- **A capacidade vem do modelo; a confiança vem da engenharia.**
- O LLM não é o sistema; o LLM opera estritamente encapsulado dentro de um **Harness**.
- Toda saída do modelo é considerada entrada não confiável até que passe por validação de schema rígido e políticas de negócio.

### 2. Limiar de Certeza (*Certainty Threshold*)
A recuperação e a inferência devem respeitar limiares explícitos:
- $\text{Score} \ge \text{HIGH\_THRESHOLD}$ (ex.: 0.85): Execução automatizada normal.
- $\text{LOW\_THRESHOLD} \le \text{Score} < \text{HIGH\_THRESHOLD}$ (0.75 a 0.85): Confirmação ou validação adicional necessária.
- $\text{Score} < \text{LOW\_THRESHOLD}$ (< 0.75): Transbordo imediato para `HUMAN_HANDOFF` (*Human-in-the-Loop*).

### 3. Poka-Yoke em Ferramentas Bancárias
- Ferramentas devem tornar erros impossíveis antes da execução.
- Nenhuma mutação sem `idempotency_key` (prevenção de gasto duplo).
- Restrições negativas explícitas: limites diários, saldo positivo, autorização MFA ativa.
- Falha rápida (*fail-fast*) em qualquer discrepância de contrato.
