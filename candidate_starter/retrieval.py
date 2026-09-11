"""Pilar 2 — Seleção de Tools Relevantes com Score Combinado, Stopwords,
Variantes Ortográficas, Colapso Canônico e Guarda de Direção (Runtime).
"""
import re
import time
from typing import Dict, List, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from candidate_starter.normalization import normalize
from common.interfaces import BaseToolRetriever
from common.schemas import RetrievalResult, Tool, ToolMatch

CUSTOM_STOPWORDS = [
    "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "por", "pelo", "pela", "pelos", "pelas", "com", "para", "que", "e",
    "ou", "se", "me", "meu", "minha", "meus", "minhas", "seu", "sua",
    "seus", "suas", "como", "qual", "quais", "quanto", "quanta", "quantos",
    "quantas", "quero", "preciso", "gostaria", "favor", "porfavor",
]

# Verb/Keyword directions
READ_QUERY_KEYWORDS = [
    "consultar", "ver", "qual", "mostrar", "obter", "listar", "quanto",
    "saldo", "extrato", "fatura", "buscar", "pesquisar", "checar",
]

WRITE_QUERY_KEYWORDS = [
    "atualizar", "alterar", "criar", "deletar", "bloquear", "cancelar",
    "mudar", "enviar", "cadastrar", "inserir", "remover", "trocar", "estornar",
    "parcelar", "dividir", "solicitar", "reclamar", "desbloquear", "pedir",
]

READ_TOOL_PREFIXES = ("consultar_", "obter_", "listar_", "buscar_", "ver_", "informar_", "verificar_")
WRITE_TOOL_PREFIXES = (
    "atualizar_", "alterar_", "bloquear_", "criar_", "deletar_",
    "cancelar_", "enviar_", "cadastrar_", "estornar_", "desbloquear_", "trocar_", "inserir_", "remover_",
    "dividir_", "parcelar_", "emitir_", "reclamar_", "solicitar_", "registrar_", "abrir_", "gerar_", "processar_"
)

# Mapa determinístico de colapso canônico para unificar ferramentas sinônimas/variantes no grupo canônico
CANONICAL_TOOL_MAP = {
    # Fatura
    "consultar_valor_fatura_mes_atual": "consultar_fatura",
    "gerar_pdf_fatura_mes_atual": "consultar_fatura",
    "enviar_pdf_fatura_atual": "consultar_fatura",
    "gerar_linha_digitavel_fatura": "consultar_fatura",
    "consultar_valor_total_fatura": "consultar_fatura",
    # Saldo
    "verificar_saldo_conta_corrente": "consultar_saldo",
    "informar_saldo_atual_conta": "consultar_saldo",
    "consultar_valor_disponivel_conta": "consultar_saldo",
    "consultar_saldo_disponivel_pix": "consultar_saldo",
    # Endereço
    "atualizar_cep_entrega": "alterar_endereco",
    "atualizar_endereco_entrega_encomendas": "alterar_endereco",
    "processar_mudanca_endereco_atualizar_entrega": "alterar_endereco",
    "confirmar_mudanca_endereco": "alterar_endereco",
    # Estorno / Contestação
    "contestar_compra_desconhecida": "estornar_transacao",
    "reclamar_cobranca_errada_cartao_dinheiro_volta": "estornar_transacao",
    "solicitar_devolucao_dinheiro_cobranca_errada": "estornar_transacao",
    "registrar_compra_nao_reconhecida": "estornar_transacao",
    "contestar_compra_cartao": "estornar_transacao",
    "solicitar_devolucao_valor_cobranca": "estornar_transacao",
    # Limite
    "informar_limite_disponivel_cartao_credito": "consultar_limite_cartao",
    "consultar_limite_restante_fatura": "consultar_limite_cartao",
    "consultar_limite_disponivel_credito": "consultar_limite_cartao",
    # Parcelamento fatura
    "dividir_pagamento_fatura": "parcelar_fatura",
    "consultar_condicoes_parcelamento_fatura": "parcelar_fatura",
    "dividir_fatura_em_vezes": "parcelar_fatura",
    "parcelar_valor_fatura_cartao": "parcelar_fatura",
    "parcelar_fatura_numero_vezes_escolhido": "parcelar_fatura",
    "simular_parcelamento_fatura": "parcelar_fatura",
    # Telefone
    "atualizar_telefone_cadastrado_troca_numero": "alterar_telefone",
    "trocar_numero_telefone_cadastro": "alterar_telefone",
    "processar_troca_numero_telefone_cliente": "alterar_telefone",
    "confirmar_troca_numero_telefone": "alterar_telefone",
    # Email
    "consultar_email_vinculado_conta": "atualizar_email",
    "confirmar_email_cadastrado": "atualizar_email",
    # Bloqueio / Desbloqueio
    "solicitar_bloqueio_preventivo_cartao": "bloquear_cartao",
    "reportar_perda_cartao": "bloquear_cartao",
    "instrucoes_desbloqueio_cartao_novo": "desbloquear_cartao",
    "ativar_cartao_novo_recebido": "desbloquear_cartao",
    "ativar_cartao_novo": "desbloquear_cartao",
    # Segunda via
    "emitir_segunda_via_cartao_parou_funcionar": "solicitar_segunda_via_cartao",
    "solicitar_via_reposicao_cartao_com_defeito": "solicitar_segunda_via_cartao",
    "solicitar_reemissao_cartao_danificado": "solicitar_segunda_via_cartao",
    "diagnosticar_cartao_com_defeito": "solicitar_segunda_via_cartao",
    "reportar_cartao_nao_funciona": "solicitar_segunda_via_cartao",
    # Suporte
    "abrir_chamado_suporte_app_travando": "abrir_chamado_suporte",
    "abrir_chamado_travamento_app": "abrir_chamado_suporte",
    "registrar_chamado_aplicativo_travando": "abrir_chamado_suporte",
    "reportar_problema_aplicativo": "abrir_chamado_suporte",
    "reportar_aplicativo_travando": "abrir_chamado_suporte",
}


def get_canonical_name(tool_name: str) -> str:
    """Mapeia o nome da ferramenta para sua versão canônica primária."""
    if tool_name in CANONICAL_TOOL_MAP:
        return CANONICAL_TOOL_MAP[tool_name]

    # Heurística genérica de limpeza de sufixos de versão (_v1, _v2, etc.)
    cleaned = re.sub(r"_v\d+$", "", tool_name.lower())
    return cleaned


def infer_query_direction(query_norm: str) -> str:
    """Inferir direção da query: 'read', 'write', ou 'unknown'."""
    has_read = any(re.search(rf"\b{kw}\b", query_norm) for kw in READ_QUERY_KEYWORDS)
    has_write = any(re.search(rf"\b{kw}\b", query_norm) for kw in WRITE_QUERY_KEYWORDS)

    if has_read and not has_write:
        return "read"
    if has_write and not has_read:
        return "write"
    return "unknown"


def infer_tool_direction(tool_name: str) -> str:
    """Inferir direção da ferramenta pelo prefixo."""
    if tool_name.startswith(READ_TOOL_PREFIXES):
        return "read"
    if tool_name.startswith(WRITE_TOOL_PREFIXES):
        return "write"
    return "unknown"


class ToolRetriever(BaseToolRetriever):
    def __init__(self, alpha: float = 0.5) -> None:
        self.alpha = alpha
        self._tools: List[Tool] = []
        self._fitted = False

        self._doc_vectorizer = TfidfVectorizer(
            stop_words=CUSTOM_STOPWORDS,
            ngram_range=(1, 2),
            preprocessor=normalize,
        )
        self._intent_vectorizer = TfidfVectorizer(
            stop_words=CUSTOM_STOPWORDS,
            ngram_range=(1, 2),
            preprocessor=normalize,
        )

        self._doc_matrix = None
        self._intent_matrix = None

    def fit(self, tools: List[Tool]) -> "ToolRetriever":
        """Indexa o catálogo de tools para busca."""
        self._tools = tools

        doc_texts = []
        intent_texts = []

        for tool in tools:
            # Document text: name + description + category
            doc_text = f"{tool.name} {tool.description} {tool.category}"
            doc_texts.append(doc_text)

            # Intent text: name.replace("_", " ") + description
            intent_text = f"{tool.name.replace('_', ' ')} {tool.description}"
            intent_texts.append(intent_text)

        self._doc_matrix = self._doc_vectorizer.fit_transform(doc_texts)
        self._intent_matrix = self._intent_vectorizer.fit_transform(intent_texts)

        self._fitted = True
        return self

    def search(self, query: str, k: int = 2) -> RetrievalResult:
        """Retorna as top-k tools mais relevantes para `query`."""
        if not self._fitted:
            raise RuntimeError("Chame fit() antes de search().")

        start = time.perf_counter()

        q_norm = normalize(query)
        query_direction = infer_query_direction(q_norm)

        q_doc_vec = self._doc_vectorizer.transform([query])
        q_intent_vec = self._intent_vectorizer.transform([query])

        doc_sims = cosine_similarity(q_doc_vec, self._doc_matrix)[0]
        intent_sims = cosine_similarity(q_intent_vec, self._intent_matrix)[0]

        combined_scores = (1 - self.alpha) * doc_sims + self.alpha * intent_sims

        # Apply direction guard & canonical collapsing
        canonical_best: Dict[str, Tuple[str, float]] = {}

        for idx, tool in enumerate(self._tools):
            score = float(combined_scores[idx])
            tool_direction = infer_tool_direction(tool.name)

            # Direction guard rule: read query + write tool -> score = 0
            if query_direction == "read" and tool_direction == "write":
                score = 0.0

            if score <= 0:
                continue

            canon_group = get_canonical_name(tool.name)
            if canon_group not in canonical_best or score > canonical_best[canon_group][1]:
                canonical_best[canon_group] = (tool.name, score)

        # Sort matches by score descending
        sorted_matches = sorted(canonical_best.values(), key=lambda item: item[1], reverse=True)
        top_k_matches = [ToolMatch(name=name, score=score) for name, score in sorted_matches[:k]]

        latency_ms = (time.perf_counter() - start) * 1000.0

        return RetrievalResult(matches=top_k_matches, latency_ms=latency_ms)
