---
id: kb-edge-cases
title: Catálogo de Casos de Borda e Gotchas em Agentes Bancários
tags: [edge-cases, normalization, pt-br, token-efficiency, gotchas]
progressive_tokens: 310
version: 1.0.0
standard: Google OKF v0.2
---

# Catálogo de Casos de Borda e Gotchas

### 1. Divergência Silenciosa de Recall por Acentuação (PT-BR)
- **Problema:** Usuários digitam `"cartao"`, `"cartão"`, `"bloqueio"`, `"bloquear"`. Modelos baseados em tokens exatos tratam palavras acentuadas e sem acento como vocabulários disjuntos.
- **Solução Canônica:** Pré-processamento determinístico com Unicode NFKD e strip de combining characters antes de qualquer tokenização.
- **Gotcha:** Jamais misture pré-processamento manual com flags implícitas de bibliotecas (ex.: `strip_accents='unicode'` no `TfidfVectorizer`). Centralize em uma função canônica única para evitar assimetria entre indexação e busca.

### 2. Desempate Não Determinístico em Recuperação Vetorial
- **Problema:** Quando múltiplas tools obtêm score de similaridade idêntico (ex.: score 0.0 para query não relacionada), algoritmos de ordenação instáveis retornam listas em ordens arbitrárias dependendo da ordem interna do catálogo ou versão do interpretador.
- **Solução Canônica:** Função de ordenação com tupla composta: `(-score, tool.name)`. Isso garante ordenação decrescente por score e desempate alfabético por nome.

### 3. Calibração Falsa de Probabilidade
- **Problema:** Modelos como `LinearSVC` expõem `decision_function` (distância geométrica ao hiperplano). Tratar essa distância diretamente como probabilidade de confiança viola contratos probabilísticos.
- **Solução Canônica:** Utilize `LogisticRegression` para obter `predict_proba` nativo calibrado no intervalo `[0, 1]`, ou `CalibratedClassifierCV` se usar SVM.
