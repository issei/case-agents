# ADR-002: Classificador Lexical Supervisionado para Query Routing

- **Status:** Aceito
- **Data:** 2026-09-10
- **Decisores:** Time de Engenharia de Agentes
- **Conformidade ISM:** M2 (Arquitetar — Determinismo antes de Inteligência)

---

## 1. Contexto
A triagem de requisições de clientes em um banco digital deve decidir, em fração de milissegundos e a custo zero de inferência, se a solicitação pode ser atendida imediatamente via `FAST_PATH` (respostas locais, FAQs determinísticas, saudações) ou se necessita ser encaminhada para o caminho `AGENT` (planejamento deliberado com seleção de tools).

Enviar todas as consultas diretamente para um modelo de linguagem de grande porte (LLM) viola premissas de custo, latência e segurança de dados confidenciais (PII).

## 2. Decisão
Implementar o `QueryRouter` utilizando uma arquitetura linear lexical supervisionada:
1. Vetorização esparsa via `TfidfVectorizer` com n-grams (1, 2) e pré-processador canônico `normalize`.
2. Classificação supervisionada via `LogisticRegression` (`max_iter=1000`, `C=1.0`, `random_state=42`).
3. Extração da confiança probabilística calibrada nativamente através de `predict_proba`.
4. Validação estrita de contratos pré e pós-treinamento, lançando `RuntimeError("Chame fit() antes de predict().")` em caso de predição prematura.

## 3. Consequências
### Positivas:
- **Latência Ultra-baixa:** Inferência local em menos de 5ms, muito abaixo do SLA P99 de 120ms estabelecido no `APM.yml`.
- **Custo Operacional Nulo:** Elimina chamadas a APIs pagas de LLM para saudações e dúvidas frequentes.
- **Probabilidades Calibradas:** `LogisticRegression` entrega probabilidades diretas no intervalo `[0, 1]`, adequadas para limiares de certeza (*Confidence Thresholds*).
- **Simplicidade (Ponytail):** Sem dependência de vetores densos, GPUs ou bancos vetoriais complexos.

### Negativas / Limitações:
- Sensível a termos fora do vocabulário de treino (*OOV*), o que em ambiente de produção é mitigado pela arquitetura de fallback para `AGENT` ou `HUMAN_HANDOFF` descrita no APM.
