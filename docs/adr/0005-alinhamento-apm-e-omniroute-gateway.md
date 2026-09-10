# ADR-005: Alinhamento com o Manifesto APM e OmniRoute Gateway Pattern

- **Status:** Aceito
- **Data:** 2026-09-10
- **Decisores:** Time de Engenharia de Agentes
- **Conformidade ISM:** M3 (Orquestrar — APM, Guardrails, Quota Awareness e Padrões de Produção)

---

## 1. Contexto
A transição do MVP determinístico para o ambiente bancário de missão crítica exige governança rígida, empacotamento declarativo e resiliência operacional contra falhas de rede, saturação de contexto e estouro de cotas de APIs de provedores LLM. O manifesto `APM.yml` (padrão Microsoft Azure AI Foundry / Semantic Kernel) define o contrato do agente, e os princípios de gateways universais (como o OmniRoute) fornecem as táticas necessárias de contingência e otimização.

## 2. Decisão
Adotar a arquitetura orquestrada descrita no `APM.yml` integrada aos padrões de resiliência do OmniRoute:
1. **Padrão Triage-and-Delegate com 3 Tiers:**
   - `FAST_PATH`: SLA P99 de 120ms, custo zero de LLM para saudações e FAQs institucionais.
   - `AGENT`: Orquestração deliberada (ReAct Loop) com catálogo de skills (Pix, Cartões, Contas, Cadastro).
   - `HUMAN_HANDOFF`: Transbordo imediato para fila humana especializada quando `confidence < 0.75`, após 2 falhas consecutivas ou em alertas de segurança/fraude.
2. **Resiliência Multi-Provider e Quota Awareness (Padrão OmniRoute):**
   - Roteamento ciente de limites de requisições por minuto (RPM) e tokens por minuto (TPM), acionando fallback automático entre modelos/deployments da Azure OpenAI sem interromper o cliente.
3. **Poka-Yoke e Contratos ACI Estritos:**
   - Ferramentas mutáveis (`MUTATE`) exigem validação de schema prévia, idempotência (`idempotency_key` UUIDv4) e step-up authentication (MFA/Biometria).
4. **Política de Compressão de Contexto e Orçamento de Tokens:**
   - Política de 3 níveis para manter o histórico em $O(1)$: Pruning determinístico (últimas 2 iterações completas), sumarização de iterações antigas (<150 tokens) e fail-closed para `HUMAN_HANDOFF` se exceder o orçamento (`max_context_tokens_per_iteration = 3000`).
5. **Observabilidade e Conformidade Regulatória:**
   - Traces OpenTelemetry com context propagation (`correlation_id`, `session_id`), mascaramento estrito de PII (CPF, PAN de cartão, e-mail, telefone) em conformidade com LGPD, PCI-DSS v4.0 e Resolução BACEN 4893.

## 3. Consequências
### Positivas:
- **Segurança Fail-Closed:** O modelo nunca executa ações de alto risco sem confirmação ou autorização positiva.
- **Eficiência Financeira:** Economia de tokens sustentada via RTK/Caveman e triagem determinística, mantendo redução de custos > 65%.
- **Alta Disponibilidade:** Proteção contra downtime de fornecedores de IA via circuit breaker e quota-aware fallback.

### Negativas / Complexidade:
- Exige infraestrutura de observabilidade (Azure Application Insights / AI Foundry Tracing) e gerenciamento de segredos para os tokens e chaves das APIs.
