# ADR-001: Estratégia de Normalização Textual Canônica Pré-Vetorização

- **Status:** Aceito
- **Data:** 2026-09-10
- **Decisores:** Time de Engenharia de Agentes
- **Conformidade ISM:** M2 (Arquitetar — Contratos Rígidos e Determinismo)

---

## 1. Contexto
No domínio bancário em língua portuguesa, consultas de usuários e o catálogo de ferramentas apresentam grande variabilidade diacrítica e ortográfica (ex.: `"Cartão"`, `"cartao"`, `"cartão!"`, `"PIX?"`). Se o vetorizador lexical operar sobre tokens brutos, variantes tipográficas geram representações esparsas distintas, degradando silenciosamente o recall do `ToolRetriever`.

## 2. Decisão
Implementar e compartilhar uma função estrita e canônica de normalização (`common/normalization.py`), aplicada obrigatoriamente:
1. Em `fit()`: em cada campo individual (`name`, `description`, `category`) antes da concatenação.
2. Em `search()`: na `query` antes da inferência.

### Algoritmo Canônico:
1. Decomposição Unicode NFKD (separa glifos de diacríticos).
2. Remoção de marcas combinantes via `unicodedata.combining`.
3. Conversão para minúsculas (`lower()`).
4. Substituição de caracteres não alfanuméricos por espaço (`re.sub(r"[^a-z0-9\s]", " ", text)`).
5. Colapso de múltiplos espaços (`re.sub(r"\s+", " ", text).strip()`).

Configuração explícita do `TfidfVectorizer`: delegar toda normalização à função explícita (`lowercase=False, strip_accents=None, token_pattern=r"\S+"`).

## 3. Consequências
### Positivas:
- **Garantia de Equivalência Estrita:** `"Cartão"` e `"cartao"` geram exatamente a mesma representação esparsa e idênticos scores de similaridade de cosseno.
- **Auditabilidade Total:** Toda regra de pré-processamento é visível e testável, sem dependência de comportamento implícito de bibliotecas de terceiros.
- **Zero Bloat (Princípio Ponytail):** Utiliza apenas a biblioteca padrão do Python (`unicodedata`, `re`).

### Negativas / Trade-offs:
- Não realiza stemming ou lematização avançada (ex.: flexões verbais), o que é proposital para manter o MVP leve e determinístico.
