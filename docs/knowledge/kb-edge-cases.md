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

### 2. Desempate Estável vs. Ilusão de Relevância (A Armadilha do Score Zero)
- **Problema:** Quando múltiplas tools obtêm score de similaridade idêntico (ex.: score 0.0 para queries sem sobreposição vocabular), algoritmos de ordenação instáveis variam a saída. No entanto, usar apenas ordenação alfabética cria uma falsa ilusão de relevância ao retornar tools arbitrárias com score zero.
- **Solução Canônica:** Desempate estável via tupla `(-score, tool.name)` combinado com **Abstention via Limiar Mínimo (`min_score`)**. Consultas com score nulo ou irrelevante devem retornar lista vazia, disparando fallback ou pedido de esclarecimento em vez de forçar a execução de ferramentas com score zero.

### 3. Calibração Falsa de Probabilidade
- **Problema:** Modelos como `LinearSVC` expõem `decision_function` (distância geométrica ao hiperplano). Tratar essa distância diretamente como probabilidade de confiança viola contratos probabilísticos.
- **Solução Canônica:** Utilize `LogisticRegression` para obter `predict_proba` nativo calibrado no intervalo `[0, 1]`, ou `CalibratedClassifierCV` se usar SVM.

### 4. Descasamento Taxonômico (Intenção de Alto Nível vs. Granularidade do Catálogo)
- **Problema:** O dataset de avaliação espera rótulos canônicos (`bloquear_cartao`, `consultar_fatura`), enquanto o catálogo de produção contém ferramentas operacionais hiperespecíficas (`solicitar_bloqueio_preventivo_cartao`, `gerar_linha_digitavel_fatura`). Modelos léxicos (TF-IDF/BM25) falham por ausência de sobreposição de tokens, gerando baixos índices de acerto (ex.: 15% no top-2).
- **Solução Canônica:** Enriquecer o índice com **aliases canônicos**, sinônimos operacionais e suporte a recuperação híbrida (léxica + embeddings densos).
