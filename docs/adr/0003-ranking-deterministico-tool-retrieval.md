# ADR-003: Ranking Determinístico e Desempate Alfabético no Tool Retrieval

- **Status:** Aceito
- **Data:** 2026-09-10
- **Decisores:** Time de Engenharia de Agentes
- **Conformidade ISM:** M2 (Arquitetar — Determinismo antes de Inteligência)

---

## 1. Contexto
No catálogo de 285 ferramentas bancárias, consultas curtas ou ambíguas frequentemente produzem empates de pontuação de similaridade de cosseno (notadamente score 0.0 quando termos da query não coincidem com o vocabulário). Sem uma política explícita de desempate, o ordenamento retornado depende da ordem física do arquivo JSON ou da estabilidade do algoritmo interno de sort, violando o princípio de reproducibilidade estrita.

## 2. Decisão
Implementar no `ToolRetriever` (`candidate_starter/retrieval.py`):
1. Representação textual unificada por ferramenta:
   `normalize(name) + " " + normalize(description) + " " + normalize(category)`
2. Vetorização e cálculo de similaridade de cosseno entre a query normalizada e a matriz esparsa das ferramentas.
3. Critério de ordenação com tupla composta determinística:
   `candidates.sort(key=lambda item: (-item[0], item[1]))`
   - Chave primária: `-score` (similaridade de cosseno em ordem decrescente).
   - Chave secundária (desempate): `tool.name` (ordem lexicográfica ascendente).
4. Limitação estrita a no máximo `k` ferramentas (com `k > 0` e limitado ao tamanho do catálogo).

## 3. Consequências
### Positivas:
- **Determinismo Absoluto:** Consultas idênticas produzem sempre a mesma lista de ferramentas no Top-K em qualquer plataforma ou ambiente.
- **Isolamento de Contexto:** Apenas as ferramentas mais relevantes são enviadas ao LLM no caminho `AGENT`, reduzindo o custo em até 66% e prevenindo alucinações.
- **Conformidade com Testes Automatizados:** Permite testes unitários reproduzíveis e verificáveis em CI/CD.

### Negativas / Limitações:
- O desempate alfabético é uma convenção determinística arbitrária na ausência de sinal semântico adicional; em produção (conforme `APM.yml`), a ordenação secundária pode considerar popularidade ou escopos de autorização do usuário.
