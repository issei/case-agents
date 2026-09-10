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
- **Problema:** O dataset de avaliação espera rótulos canônicos (`bloquear_cartao`, `consultar_fatura`), enquanto o catálogo de produção contém ferramentas operacionais hiperespecíficas (`solicitar_bloqueio_preventivo_cartao`, `gerar_linha_digitavel_fatura`). Modelos léxicos (TF-IDF/BM25) falham por ausência de sobreposição de tokens: 15% no top-2 sem tratamento, 35% com aliases concatenados ao documento da ferramenta.
- **Anti-padrão medido:** concatenar o bloco de aliases ao documento da ferramenta. O TF-IDF normaliza por norma L2, então acrescentar sinônimos **reduz** o peso relativo dos termos originais. Ganho observado: apenas 15% → 35% no top-2.
- **Solução Canônica:** tratar as duplicatas como problema de **governança de catálogo**, não de vetorização. Declarar a capacidade de negócio que cada ferramenta realiza, recuperar no nível de capacidade (as variantes colapsam na canônica) e indexar o glossário do usuário como **campo separado**, combinado por soma ponderada (padrão BM25F). Medido: 100% no top-2. Ver ADR-006.
- **Armadilha de fronteira:** nunca agrupar leitura com escrita. `consultar_email_vinculado_conta` e `atualizar_email` são lexicalmente vizinhas e operacionalmente opostas; colapsá-las faz o agente escrever quando o cliente pediu para ler.
- **Não agrupar não basta.** Medido: mesmo declaradas como capacidades distintas, a consulta perdia para a alteração com margem relativa de 0.47 — a guarda de margem não pega, porque o erro não é empate, é decisão confiante e errada. Leitura e escrita sobre o mesmo dado compartilham TODOS os substantivos; a única palavra que as separa é o verbo, um token entre dez num saco de palavras. **A direção precisa ser declarada como metadado da ferramenta, não inferida por similaridade textual.** Ver ADR-008.
- **Campo ausente não é campo zerado.** Em recuperação multi-campo, atribuir 0 a um campo que a ferramenta não possui trata dado faltante como evidência negativa. Medido aqui: capacidades sem glossário tinham o score cortado pela metade e perdiam por falta de vocabulário, não por falta de relevância.
