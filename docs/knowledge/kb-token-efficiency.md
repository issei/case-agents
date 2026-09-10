---
id: kb-token-efficiency
title: Eficiência de Contexto, Anti-Bloat e Gestão de Tokens
tags: [token-efficiency, rtk, caveman, ponytail, omniroute, compaction]
progressive_tokens: 340
version: 1.0.0
standard: Google OKF v0.2
---

# Eficiência de Contexto e Princípios Anti-Bloat

### 1. Ponytail (Anti-Bloat & YAGNI)
- Escada de 7 degraus: priorizar sempre a solução mais simples que atenda ao contrato antes de cogitar dependências adicionais.
- O MVP foi construído usando unicamente a biblioteca padrão (`unicodedata`, `re`) e bibliotecas fundamentais (`scikit-learn`, `numpy`), sem frameworks agênticos pesados.

### 2. Caveman & Densidade de Informação
- Eliminação sistemática de floreios conversacionais.
- Mensagens e interfaces focadas 100% em dados auditáveis, métricas consolidadas e relatórios estruturados.

### 3. RTK (Token Killer) e Compressão de Terminal
- Outputs de terminal direcionados e estruturados para economizar contexto no ciclo de desenvolvimento e em ambientes automatizados (CI/CD).

### 4. Política de Compressão de Janela no ReAct Loop (Produção)
- Manter o crescimento de tokens por iteração em $O(1)$:
  - **Nível 1 (Pruning):** Manter system prompt, query original e o par (Ação, Observação) das últimas 2 iterações completas. Iterações anteriores são reduzidas a sumários unilineares.
  - **Nível 2 (Sumarização Compacta):** Resumo compacto de até 150 tokens quando o orçamento de 3.000 tokens for atingido.
  - **Nível 3 (Fail-Closed):** Transbordo para `HUMAN_HANDOFF` se o limite de contexto for extrapolado.
