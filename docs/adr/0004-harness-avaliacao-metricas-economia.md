# ADR-004: Harness de Avaliação em Camadas e Métricas de Economia

- **Status:** Aceito
- **Data:** 2026-09-10
- **Decisores:** Time de Engenharia de Agentes
- **Conformidade ISM:** M0/M1 (Despertar e Mapear — Reconhecimento do Crash Silencioso e Inventário de Comportamentos)

---

## 1. Contexto
A avaliação de sistemas de agentes de IA frequentemente sofre do "Crash Silencioso": falhas de intenção ou desperdício de recursos que não geram exceções de runtime, mas deterioram os custos e a experiência do usuário. Precisamos de métricas quantitativas objetivas que meçam tanto a qualidade da decisão de roteamento e recuperação quanto os ganhos econômicos e de latência em relação a uma abordagem ingênua que envia todo o catálogo de ferramentas para um LLM caro.

## 2. Decisão
Implementar no módulo `candidate_starter/harness.py`:
1. **Acurácia e Matriz de Confusão:**
   `compute_router_metrics()` mede o acerto de rotas e estrutura matrizes completas `FAST_PATH` e `AGENT`, mesmo em células com valor zero.
2. **Precision@K no Top-K de Tools:**
   `compute_precision_at_k()` avalia se a ferramenta esperada pelo dataset está contida entre as `k` candidatas recuperadas, retornando `0.0` para listas vazias.
3. **Economia de Custo e Latência:**
   `compute_savings()` compara o pipeline inteligente (`smart_pipeline`) contra o baseline sempre-LLM (`baseline_always_llm`):
   $$\text{savings\_pct} = \frac{\text{baseline} - \text{smart}}{\text{baseline}} \times 100$$
   com proteção estrita contra divisão por zero quando o baseline for nulo.

## 3. Consequências
### Positivas:
- **Transparência e Auditabilidade:** O relatório gerado evidencia o ROI técnico e financeiro do sistema de roteamento.
- **Fail-Safe Matemático:** Trata divisões por zero e entradas vazias sem interromper a execução do harness.
- **Base para Avaliação em Camadas:** Alinhado com as Camadas 1 (Retrieval) e 2 (Routing) do ISM especificadas para produção.

### Negativas / Limitações:
- O MVP simula os custos e latências através de constantes determinísticas em `common/mock_llm.py`; em produção, essas métricas devem ser alimentadas por telemetria real OpenTelemetry.
