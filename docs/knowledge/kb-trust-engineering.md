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

### 4. A Falácia da Economia Financeira sem Barreira de Segurança
- Economia de custo (ex.: 78,9%) só é virtude de engenharia se o sistema estiver operando de forma correta e segura.
- Executar cegamente a primeira tool de um ranking com 65% de erro no top-2 (estado medido antes da ADR-006) significa transferir o risco diretamente para a conta do cliente.
- **Uma guarda de margem não protege contra erro confiante.** Ela cobre empates. Um top-1 errado que vence o top-2 por larga margem passa por ela intacto — e é o modo de falha mais perigoso, porque parece uma decisão. Guardas estatísticas precisam ser complementadas por restrições semânticas declaradas (direção da operação, autorização, validação de parâmetros).
- **Escreva o teste que você tem medo de rodar.** O teste de colisão leitura/escrita foi escrito porque um revisor externo pediu, e falhou na primeira execução sobre o catálogo real, expondo uma falha que três guardas e 54 testes não pegavam. Métricas verdes não são cobertura.
- **Abstenção também mente.** Em uma iteração intermediária deste projeto a economia subiu para 87,8% enquanto a taxa de sucesso caía para 20%: um limiar de confiança mal calibrado desviava 45% das queries para atendimento humano, e cada desvio economizava uma chamada de LLM. O relatório deve separar economia total de economia sobre queries efetivamente resolvidas, e expor quantas foram empurradas para o humano.
- Um harness de confiança deve auditar a **Taxa de Execução Correta (Top-1 Match)** e contabilizar execuções incorretas como incidentes de segurança, priorizando a **Abstention Segura** sobre a execução forçada.
