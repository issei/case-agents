"""Pilar 2 — Seleção de Tools Relevantes.

O catálogo de tools está em `data/tools_registry.json`. Passar todas as 285 tools no prompt
de um LLM não escala (estoura contexto, confunde o modelo, aumenta custo e latência).

`search(query, k=2)` retorna as `k` capacidades mais relevantes do catálogo para a query,
antes de qualquer chamada ao LLM.

## Arquitetura de scoring

Dois campos de recuperação, ambos cosseno TF-IDF em [0, 1], combinados por soma ponderada
(padrão BM25F de multi-field retrieval):

    score = (1 - alpha) * lexical + alpha * intent

  - `lexical`: cosseno entre a query normalizada e `name + description + category`
    da ferramenta. É o sinal do catálogo.
  - `intent`: cosseno entre a query normalizada e o glossário de vocabulário do usuário
    da capacidade (`taxonomy.CANONICAL_ALIASES`). É o sinal do domínio.

O glossário é indexado como CAMPO SEPARADO, não concatenado ao documento da tool. A versão
anterior concatenava, o que aumentava a norma L2 do documento e derrubava o peso TF-IDF dos
termos originais — medido: 35% de Hit Rate@2. Ver ADR-006.

## Colapso por capacidade

O catálogo contém duplicatas semânticas (`consultar_fatura` vs `enviar_pdf_fatura_atual`
vs `gerar_linha_digitavel_fatura`). `taxonomy.VARIANT_TO_CANONICAL` declara qual capacidade
cada variante realiza; o ranking opera sobre capacidades, tomando o MAIOR score do grupo e
atribuindo-o à tool canônica. O membro que casou é preservado em `ToolMatch.matched_variant`.

Consequência para o contrato de `k`: `search(q, k=2)` devolve 2 capacidades DISTINTAS, não
2 duplicatas da mesma. Em k pequeno isso é estritamente mais informativo.

## Abstention

`min_score` descarta candidatos abaixo do limiar de relevância. Se nenhum candidato
sobrevive, `matches` é vazio — o harness converte isso em ABSTAIN, sem executar tool.
"""
import re
import time
from typing import Dict, List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from common.interfaces import BaseToolRetriever
from common.normalization import normalize
from common.schemas import RetrievalResult, Tool, ToolMatch

DEFAULT_INTENT_WEIGHT: float = 0.5
"""Peso do campo de glossário na soma ponderada (alpha).

0.5 = os dois campos pesam igual. Escolha deliberada: não é um valor ajustado até o
benchmark passar. Com alpha=0.6 o dataset oficial chega a 20/20 em top-1, mas a diferença
vem de desempatar um caso genuinamente ambíguo por 0.005 de margem
(`atualizar_email` vs `consultar_email_vinculado_conta`). Esse caso deve ser tratado pela
guarda de margem do harness (AMBIGUOUS_CONFIRMATION), não por ajuste de peso.
"""


PT_STOPWORDS: List[str] = [
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e", "em",
    "essa", "esse", "esta", "este", "eu", "meu", "minha", "meus", "minhas", "na", "nas",
    "no", "nos", "o", "os", "os", "ou", "para", "pela", "pelo", "por", "pra", "que",
    "qual", "se", "seu", "sua", "um", "uma", "voce", "vocês",
]
"""Palavras funcionais PT-BR removidas antes da vetorização.

Não é otimização de recall — é segurança. Sem a lista, a query sem sentido
"qual a capital da mongolia interior" pontua 0.132 contra `gerar_linha_digitavel_fatura`
("Gera **a** linha digitável **da** fatura..."), ou seja, ATRAVESSA o limiar de abstenção
de 0.10 apoiada apenas em "a" e "da". Uma query curta tem norma L2 pequena, então dois
casamentos de palavra funcional dominam o cosseno.

A lista é aplicada pelo `TfidfVectorizer` (indexação e consulta usam o mesmo vetorizador),
não pela `normalize()` da Seção 3.2 — aquela função é contrato fixo da especificação e
permanece intocada.
"""


_ORTHOGRAPHIC_VARIANTS = (
    # "e-mail" é a grafia formal e "email" a corrente; `normalize()` transforma o hífen em
    # espaço, produzindo o par de tokens "e mail". O "e" então é removido como conjunção e
    # a query perde a palavra inteira — medido: "Quero mudar o e-mail vinculado à minha
    # conta" dava score lexical ~0 para `atualizar_email`, cuja descrição usa "e-mail".
    # Dobrar variantes ortográficas é a mesma classe de operação que dobrar acentos.
    (re.compile(r"\be[\s]?mail\b"), "email"),
)


def prepare_text(text: str) -> str:
    """Normalização canônica (Seção 3.2) + dobra de variantes ortográficas do domínio.

    Regra invariante preservada: documentos indexados em `fit()` e queries em `search()`
    passam por ESTA MESMA função. `common.normalization.normalize` permanece intocada —
    é o contrato fixo da especificação; a dobra de variantes é uma etapa do retriever.
    """
    text = normalize(text)
    for pattern, replacement in _ORTHOGRAPHIC_VARIANTS:
        text = pattern.sub(replacement, text)
    return text


def _vectorizer() -> TfidfVectorizer:
    """Vetorizador com normalização delegada à função canônica (Seção 3.2 da spec)."""
    return TfidfVectorizer(
        lowercase=False,
        strip_accents=None,
        token_pattern=r"\S+",
        ngram_range=(1, 2),
        stop_words=PT_STOPWORDS,
    )


class ToolRetriever(BaseToolRetriever):
    """Retriever lexical com normalização canônica, colapso por capacidade e abstention.

    Parâmetros
    ----------
    min_score : float
        Score mínimo para incluir uma capacidade nos resultados. Abaixo disso o candidato é
        descartado (abstention), prevenindo execução baseada em similaridade nula.
        Padrão: 0.0 (sem filtragem — compatibilidade retroativa).
    use_taxonomy : bool
        Se True, ativa o colapso por capacidade e o campo de glossário.
        Se False, o retriever opera em modo lexical puro sobre o catálogo bruto
        (útil para medir a contribuição da taxonomia e para testes de desempate).
        Padrão: True.
    intent_weight : float
        Alpha da soma ponderada entre os campos. Ignorado quando `use_taxonomy=False`.
    """

    def __init__(
        self,
        min_score: float = 0.0,
        use_taxonomy: bool = True,
        intent_weight: float = DEFAULT_INTENT_WEIGHT,
    ) -> None:
        if not 0.0 <= intent_weight <= 1.0:
            raise ValueError("intent_weight deve estar em [0, 1].")
        self._tools: List[Tool] = []
        self._fitted = False
        self._min_score = min_score
        self._use_taxonomy = use_taxonomy
        self._intent_weight = intent_weight

        self._vectorizer = _vectorizer()
        self._tfidf_matrix = None

        # Camada taxonômica (populada em fit quando use_taxonomy=True)
        self._variant_to_canonical: Dict[str, str] = {}
        self._intents: List[str] = []
        self._intent_vectorizer: Optional[TfidfVectorizer] = None
        self._intent_matrix = None

    # ── Indexação ────────────────────────────────────────────────────────────

    def _fit_taxonomy(self) -> None:
        """Indexa o glossário das capacidades presentes no catálogo.

        Só considera intenções cuja tool canônica realmente existe no catálogo indexado:
        o retriever nunca pode devolver um nome que não está em `self._tools`.
        """
        try:
            from candidate_starter.taxonomy import CANONICAL_ALIASES, VARIANT_TO_CANONICAL
        except ImportError:  # taxonomia é opcional — degrada para lexical puro
            return

        catalog = {t.name for t in self._tools}
        self._variant_to_canonical = {
            variant: canonical
            for variant, canonical in VARIANT_TO_CANONICAL.items()
            if variant in catalog and canonical in catalog
        }
        self._intents = sorted(name for name in CANONICAL_ALIASES if name in catalog)
        if not self._intents:
            return

        self._intent_vectorizer = _vectorizer()
        self._intent_matrix = self._intent_vectorizer.fit_transform(
            [prepare_text(CANONICAL_ALIASES[name]) for name in self._intents]
        )

    def fit(self, tools: List[Tool]) -> "ToolRetriever":
        """Indexa o catálogo de tools e, se habilitada, a camada taxonômica."""
        self._tools = list(tools)
        self._variant_to_canonical = {}
        self._intents = []
        self._intent_vectorizer = None
        self._intent_matrix = None

        if not self._tools:
            self._tfidf_matrix = None
            self._fitted = True
            return self

        self._tfidf_matrix = self._vectorizer.fit_transform(
            [
                f"{prepare_text(t.name)} {prepare_text(t.description)} {prepare_text(t.category)}"
                for t in self._tools
            ]
        )
        if self._use_taxonomy:
            self._fit_taxonomy()

        self._fitted = True
        return self

    # ── Busca ────────────────────────────────────────────────────────────────

    def _intent_scores(self, normalized_query: str) -> Dict[str, float]:
        if self._intent_matrix is None or self._intent_vectorizer is None:
            return {}
        sims = cosine_similarity(
            self._intent_vectorizer.transform([normalized_query]), self._intent_matrix
        )[0]
        return {name: float(s) for name, s in zip(self._intents, sims)}

    def _collapse(self, lexical_scores) -> Dict[str, Tuple[float, str]]:
        """Agrupa o catálogo por capacidade, ficando com o maior score de cada grupo.

        Retorna {capacidade: (melhor_score_lexical, tool_que_casou)}.
        """
        best: Dict[str, Tuple[float, str]] = {}
        for tool, score in zip(self._tools, lexical_scores):
            group = self._variant_to_canonical.get(tool.name, tool.name)
            score = float(score)
            if group not in best or score > best[group][0]:
                best[group] = (score, tool.name)
        return best

    def search(self, query: str, k: int = 2, min_score: float = None) -> RetrievalResult:
        """Retorna as top-k capacidades mais relevantes para `query`.

        Se todos os candidatos ficarem abaixo de `min_score`, retorna lista vazia,
        sinalizando ao harness que a execução deve ser desviada para fallback seguro.

        Parâmetros
        ----------
        query : str
            Texto da consulta do usuário.
        k : int
            Número máximo de capacidades a retornar.
        min_score : float, opcional
            Sobrescreve o `min_score` do construtor para esta chamada.
        """
        if not self._fitted:
            raise RuntimeError("Chame fit() antes de search().")
        if not query or not query.strip():
            raise ValueError("Query não pode ser vazia.")
        if k <= 0:
            raise ValueError("k deve ser maior que zero.")

        start = time.perf_counter()

        if not self._tools or self._tfidf_matrix is None:
            return RetrievalResult(
                matches=[], latency_ms=(time.perf_counter() - start) * 1000.0
            )

        effective_min_score = min_score if min_score is not None else self._min_score
        normalized_query = prepare_text(query)

        lexical = cosine_similarity(
            self._vectorizer.transform([normalized_query]), self._tfidf_matrix
        )[0]

        if not self._use_taxonomy:
            groups = {t.name: (float(s), t.name) for t, s in zip(self._tools, lexical)}
            intents: Dict[str, float] = {}
            alpha = 0.0
        else:
            groups = self._collapse(lexical)
            intents = self._intent_scores(normalized_query)
            alpha = self._intent_weight

        candidates = []
        for group, (lex_score, member) in groups.items():
            score = (1.0 - alpha) * lex_score + alpha * intents.get(group, 0.0)
            if score >= effective_min_score:
                candidates.append((score, group, member))

        # Desempate determinístico: score decrescente, nome da capacidade alfabético.
        candidates.sort(key=lambda item: (-item[0], item[1]))

        matches = [
            ToolMatch(
                name=group,
                score=score,
                matched_variant=member if member != group else None,
            )
            for score, group, member in candidates[: min(k, len(candidates))]
        ]
        return RetrievalResult(
            matches=matches, latency_ms=(time.perf_counter() - start) * 1000.0
        )
