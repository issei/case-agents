"""Estruturas de dados compartilhadas entre o starter e a solução de referência."""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Tool:
    name: str
    description: str
    category: str


@dataclass
class RouteResult:
    route: str  # "FAST_PATH" ou "AGENT"
    latency_ms: float
    confidence: Optional[float] = None


@dataclass
class ToolMatch:
    name: str
    score: float
    # Trilha de auditoria: quando o retriever recupera no nível de capacidade, `name` é a
    # tool canônica e `matched_variant` é o membro do grupo que efetivamente casou com a
    # query (ex.: name="consultar_fatura", matched_variant="enviar_pdf_fatura_atual").
    # Campo opcional — o contrato anterior (name, score) permanece válido.
    matched_variant: Optional[str] = None


@dataclass
class RetrievalResult:
    matches: List[ToolMatch]
    latency_ms: float
