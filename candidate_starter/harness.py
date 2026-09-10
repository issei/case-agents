"""Pilar 3 — Evaluation Harness (Evals & Benchmarking).

O harness orquestra o pipeline (router -> seleção de tools -> mocks de LLM/tool) e produz
o relatório de qualidade, custo, latência e segurança.

## Barreira de segurança pré-execução

Nenhuma ferramenta é executada sem passar por três guardas, nesta ordem:

  1. `ROUTER_CONFIDENCE_THRESHOLD` — confiança do router abaixo do limiar
     -> HUMAN_FALLBACK_LOW_CONFIDENCE (o retriever nem chega a ser chamado).
  2. `RETRIEVER_MIN_SCORE` — nenhum candidato acima do limiar de relevância
     -> ABSTAIN_LOW_SCORE.
  3. `MIN_RELATIVE_MARGIN` — top-1 e top-2 empatados dentro da margem
     -> AMBIGUOUS_CONFIRMATION.

Os três guardas usam apenas sinais disponíveis em runtime (confiança, score, margem).
Nenhum deles consulta `expected_tool`.

## Fronteira entre produção e avaliação

`expected_tool` pertence EXCLUSIVAMENTE à camada de avaliação offline. Ele é usado depois
que a decisão já foi tomada, apenas para rotular o resultado (SUCCESS /
INCORRECT_TOOL_EXECUTED) e para calcular métricas. Em produção esse campo não existe — por
isso a proteção precisa acontecer ANTES da execução, via guardas 1–3.

## Métricas do relatório

  1. Acurácia do router + matriz de confusão.
  2. Hit Rate do retriever em top-1 e top-k.
     Nota metrológica: com uma única capacidade relevante por query, esta métrica é
     Hit Rate (Recall@1-in-K), não Precision@K clássica. O campo `precision_at_k` é
     mantido por compatibilidade com o schema da Seção 3.4 da especificação.
  3. Economia de custo/latência vs baseline sempre-LLM, separada entre total e
     queries efetivamente resolvidas (economia obtida por abstenção não é ganho
     operacional — é trabalho empurrado para o atendimento humano), mais o ponto de
     equilíbrio do custo de atendimento humano.
  4. Quality Gate: APROVADO / REPROVADO / INDETERMINADO, acompanhado de
     `production_readiness` — passar no gate deste benchmark não é prontidão bancária.
"""
import time
from typing import Dict, List, Optional

from common.interfaces import BaseRouter, BaseToolRetriever
from common.mock_llm import (
    COST_RETRIEVAL_USD,
    COST_ROUTER_USD,
    fast_path_answer,
    mock_tool_execution,
    simulate_agent_llm_call,
    simulate_baseline_llm_call,
)
from common.schemas import Tool

# ── Limites de Segurança Bancária ─────────────────────────────────────────────
# Baseados na Seção 4 da especificação (limiar 0.75 para a rota AGENT) e no
# kb-trust-engineering. Abaixo desses valores a operação é desviada, nunca executada.
ROUTER_CONFIDENCE_THRESHOLD: float = 0.75
"""Confiança mínima do router para encaminhar a query ao caminho AGENT sem confirmação."""

RETRIEVER_MIN_SCORE: float = 0.10
"""Score mínimo de relevância para considerar uma capacidade como candidata válida."""

MIN_RELATIVE_MARGIN: float = 0.25
"""Margem relativa mínima entre top-1 e top-2: (s1 - s2) / s1.

Um top-1 que vence o top-2 por uma fração do próprio score não é uma decisão — é um
empate. Em domínio bancário, empate entre uma capacidade de leitura e uma de escrita
(ex.: consultar e-mail vs. alterar e-mail) precisa de confirmação do cliente, não de
execução otimista. O valor é relativo, não absoluto, para não depender da escala do score.
"""

TASK_SUCCESS_RATE_THRESHOLD: float = 0.80
"""Taxa mínima de execução correta para o pipeline ser aprovado para produção."""

INCORRECT_EXECUTION_TOLERANCE: int = 0
"""Número máximo de execuções incorretas permitidas em ambiente bancário.
Qualquer execução com tool incorreta é tratada como incidente de segurança.
"""

STATUS_APPROVED = "APROVADO NO BENCHMARK DO MVP"
STATUS_REJECTED = "REPROVADO NO BENCHMARK (Quality Gate Violado)"
STATUS_INDETERMINATE = "INDETERMINADO (sem evidência transacional)"

# ── Prontidão para produção ≠ aprovação no benchmark ──────────────────────────
# O Quality Gate mede o que este benchmark consegue observar: 30 queries, 20 delas
# transacionais, router treinado em 53 exemplos, tools mockadas. Chamar esse resultado
# de "aprovado para produção bancária" seria estender a conclusão além da evidência —
# a mesma classe de erro que reportar economia de custo sem taxa de sucesso.
READINESS_MVP_BENCHMARK: str = "MVP_BENCHMARK_ONLY"
READINESS_NOT_APPROVED: str = "NOT_APPROVED"
READINESS_INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"

PRODUCTION_READINESS_CAVEAT: str = (
    "Aprovação restrita ao benchmark do MVP. Fora do escopo desta evidência: dados de "
    "tráfego real, entradas adversariais, drift, fronteira de autorização, validação de "
    "parâmetros da operação, MFA, idempotência, auditoria operacional e validação "
    "independente da calibração."
)
# ──────────────────────────────────────────────────────────────────────────────


def compute_router_metrics(y_true: List[str], y_pred: List[str], labels: List[str]) -> Dict:
    """Calcule a acurácia e a matriz de confusão do router."""
    total = len(y_true)
    if total == 0:
        accuracy = 0.0
    else:
        correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
        accuracy = float(correct / total)

    matrix = {true_lbl: {pred_lbl: 0 for pred_lbl in labels} for true_lbl in labels}
    for yt, yp in zip(y_true, y_pred):
        if yt in matrix and yp in matrix[yt]:
            matrix[yt][yp] += 1

    return {
        "accuracy": accuracy,
        "confusion_matrix": matrix,
    }


def compute_precision_at_k(hits: List[int]) -> float:
    """Calcule o Hit Rate a partir de uma lista de 0/1 (a capacidade certa estava no top-k?).

    Nota metrológica: com uma única capacidade relevante esperada por query, esta métrica
    quantifica Hit Rate (Recall@1-in-K), não Precision@K clássica. O nome é mantido por
    compatibilidade com o schema da Seção 3.4 da especificação.
    """
    if not hits:
        return 0.0
    return float(sum(hits) / len(hits))


def compute_savings(
    smart_cost_usd: float,
    smart_latency_ms: float,
    baseline_cost_usd: float,
    baseline_latency_ms: float,
) -> Dict:
    """Calcule a % de economia de custo e de latência do pipeline inteligente vs baseline.

    AVISO: economia financeira só é virtude de engenharia quando combinada com
    task_success_rate >= TASK_SUCCESS_RATE_THRESHOLD. Economia obtida por abstenção
    desloca custo para o atendimento humano — ver `economics` no relatório.
    """
    cost_savings_pct = (
        ((baseline_cost_usd - smart_cost_usd) / baseline_cost_usd) * 100.0
        if baseline_cost_usd > 0
        else 0.0
    )
    latency_savings_pct = (
        ((baseline_latency_ms - smart_latency_ms) / baseline_latency_ms) * 100.0
        if baseline_latency_ms > 0
        else 0.0
    )
    return {
        "cost_savings_pct": cost_savings_pct,
        "latency_savings_pct": latency_savings_pct,
    }


def compute_fallback_economics(
    smart_cost_usd: float,
    baseline_cost_usd: float,
    deferred_to_human: int,
    human_fallback_cost_usd: Optional[float] = None,
) -> Dict:
    """Economia líquida quando o custo do atendimento humano entra na conta.

    A economia nominal trata uma abstenção como se fosse grátis. Não é: ela vira um
    atendimento humano. Enquanto esse custo não for medido, o número honesto de publicar
    é o PONTO DE EQUILÍBRIO — o custo por atendimento desviado a partir do qual a economia
    do pipeline zera:

        breakeven = (custo_baseline - custo_pipeline) / n_desviadas

    O break-even é derivado das medições, não arbitrado: não depende de estimar quanto
    custa um atendente. `net_cost_savings_pct` só é preenchido quando o chamador fornece
    `human_fallback_cost_usd` explicitamente, e nesse caso o valor é premissa do chamador,
    não medição deste harness.
    """
    absolute_savings = baseline_cost_usd - smart_cost_usd
    breakeven = (
        absolute_savings / deferred_to_human if deferred_to_human > 0 else None
    )

    net_cost = net_savings_pct = None
    if human_fallback_cost_usd is not None:
        net_cost = smart_cost_usd + deferred_to_human * human_fallback_cost_usd
        net_savings_pct = (
            ((baseline_cost_usd - net_cost) / baseline_cost_usd) * 100.0
            if baseline_cost_usd > 0
            else 0.0
        )

    return {
        "deferred_to_human": deferred_to_human,
        "human_handling_cost_usd": human_fallback_cost_usd,
        "human_fallback_breakeven_cost_usd": breakeven,
        "net_smart_cost_usd": net_cost,
        "net_cost_savings_pct": net_savings_pct,
    }


def _evaluate_quality_gate(
    task_success_rate: Optional[float],
    incorrect_executions: int,
) -> Dict:
    """Avalia o Quality Gate de segurança bancária.

    Três estados possíveis:
      - APROVADO: zero execuções incorretas e taxa de sucesso acima do limiar.
      - REPROVADO: algum critério violado.
      - INDETERMINADO: `task_success_rate` é None, ou seja, o benchmark não continha
        nenhuma query transacional. Ausência de evidência não é evidência de segurança;
        um benchmark sem cenário transacional NUNCA aprova um pipeline bancário.

    `production_approved` responde "o pipeline passou neste benchmark?".
    `production_readiness` responde "isso autoriza operação bancária real?" — e a resposta
    nunca é sim aqui, no máximo MVP_BENCHMARK_ONLY. Os dois campos são distintos de
    propósito: o primeiro é o gate exigido pela especificação, o segundo impede que a
    aprovação no gate seja lida como prontidão operacional.
    """
    reasons = []

    if incorrect_executions > INCORRECT_EXECUTION_TOLERANCE:
        reasons.append(
            f"Execuções com tool incorreta: {incorrect_executions} "
            f"(tolerância zero em ambiente bancário)"
        )

    if task_success_rate is None:
        reasons.append(
            "Benchmark sem queries transacionais: não há evidência de que o pipeline "
            "execute a ferramenta correta. Aprovação exige cenário transacional."
        )
        return {
            "operational_status": STATUS_INDETERMINATE,
            "production_approved": False,
            "production_readiness": READINESS_INSUFFICIENT_EVIDENCE,
            "production_readiness_caveat": PRODUCTION_READINESS_CAVEAT,
            "quality_gate_reasons": reasons,
        }

    if task_success_rate < TASK_SUCCESS_RATE_THRESHOLD:
        reasons.append(
            f"Taxa de execução correta: {task_success_rate:.1%} "
            f"(mínimo exigido: {TASK_SUCCESS_RATE_THRESHOLD:.0%})"
        )

    production_approved = len(reasons) == 0
    return {
        "operational_status": STATUS_APPROVED if production_approved else STATUS_REJECTED,
        "production_approved": production_approved,
        "production_readiness": (
            READINESS_MVP_BENCHMARK if production_approved else READINESS_NOT_APPROVED
        ),
        "production_readiness_caveat": PRODUCTION_READINESS_CAVEAT,
        "quality_gate_reasons": reasons,
    }


def _relative_margin(scores: List[float]) -> Optional[float]:
    """Margem relativa entre top-1 e top-2: (s1 - s2) / s1.

    Retorna None quando há um único candidato (não há empate possível) ou quando o
    score do top-1 é zero (nada a comparar — a guarda de min_score já tratou o caso).
    """
    if len(scores) < 2 or scores[0] <= 0:
        return None
    return (scores[0] - scores[1]) / scores[0]


def run_harness(
    router: BaseRouter,
    retriever: BaseToolRetriever,
    tools: List[Tool],
    eval_dataset: List[dict],
    k: int = 2,
    min_relative_margin: float = MIN_RELATIVE_MARGIN,
    human_fallback_cost_usd: Optional[float] = None,
) -> dict:
    """Executa o harness de avaliação com barreira de segurança pré-execução.

    Ver o docstring do módulo para a ordem dos guardas e para a fronteira entre a lógica
    de produção e o uso de `expected_tool` na avaliação offline.

    Parâmetros
    ----------
    k : int
        Número de CAPACIDADES distintas pedidas ao retriever (ver contrato em
        `BaseToolRetriever.search`).
    min_relative_margin : float
        Limiar da guarda 3. Parametrizado para que a política de risco possa ser
        exercitada e recalibrada sem editar o módulo — é uma política, não uma constante
        física. Aumentar o valor troca cobertura por confirmações do cliente.
    human_fallback_cost_usd : float, opcional
        Custo assumido por query desviada para atendimento humano. Quando informado, o
        relatório publica a economia LÍQUIDA. Quando ausente, publica apenas o ponto de
        equilíbrio, que não depende de nenhuma premissa de custo.
    """
    labels = ["FAST_PATH", "AGENT"]

    y_true: List[str] = []
    y_pred: List[str] = []
    hits_at_k: List[int] = []
    hits_at_1: List[int] = []

    smart_cost_total = 0.0
    smart_latency_ms_total = 0.0
    baseline_cost_total = 0.0
    baseline_latency_ms_total = 0.0
    # Economia contabilizada apenas sobre queries efetivamente resolvidas pelo pipeline
    # (FAST_PATH respondido localmente + AGENT com execução correta).
    resolved_smart_cost = 0.0
    resolved_baseline_cost = 0.0

    correct_executions = 0
    incorrect_executions = 0
    abstentions = 0
    human_fallbacks = 0
    ambiguous_confirmations = 0
    agent_queries_with_expected_tool = 0

    rows = []

    for item in eval_dataset:
        query = item["query"]
        expected_route = item["expected_route"]
        expected_tool = item.get("expected_tool")

        route_result = router.predict(query)
        y_true.append(expected_route)
        y_pred.append(route_result.route)

        smart_cost = COST_ROUTER_USD
        smart_latency_ms = route_result.latency_ms
        resolved = False

        row = {
            "query": query,
            "expected_route": expected_route,
            "predicted_route": route_result.route,
            "router_confidence": route_result.confidence,
        }

        if route_result.route == "FAST_PATH":
            fast_path_answer(query)
            row["execution_status"] = "RESOLVED_LOCAL"
            resolved = True

        else:
            # ── GUARDA 1: Limiar de Confiança do Router ──────────────────────
            confidence = route_result.confidence
            if confidence is not None and confidence < ROUTER_CONFIDENCE_THRESHOLD:
                human_fallbacks += 1
                abstentions += 1
                if expected_tool:
                    agent_queries_with_expected_tool += 1
                    hits_at_k.append(0)
                    hits_at_1.append(0)
                row["execution_status"] = "HUMAN_FALLBACK_LOW_CONFIDENCE"
                row["retrieved_tools"] = []
                row["expected_tool"] = expected_tool
                row["fallback_reason"] = (
                    f"Router confidence {confidence:.3f} < "
                    f"threshold {ROUTER_CONFIDENCE_THRESHOLD}"
                )
            else:
                # ── GUARDA 2: Retrieval e Limiar de Score ────────────────────
                retrieval_result = retriever.search(query, k=k)
                smart_cost += COST_RETRIEVAL_USD
                smart_latency_ms += retrieval_result.latency_ms

                top_k_names = [m.name for m in retrieval_result.matches]
                top_scores = [m.score for m in retrieval_result.matches]

                if expected_tool:
                    agent_queries_with_expected_tool += 1
                    hits_at_k.append(int(expected_tool in top_k_names))
                    hits_at_1.append(int(bool(top_k_names) and top_k_names[0] == expected_tool))

                row["retrieved_tools"] = top_k_names
                row["retrieved_scores"] = top_scores
                row["retrieved_variants"] = [
                    m.matched_variant for m in retrieval_result.matches
                ]
                row["expected_tool"] = expected_tool

                margin = _relative_margin(top_scores)
                row["relative_margin"] = margin

                if not top_k_names:
                    abstentions += 1
                    row["execution_status"] = "ABSTAIN_LOW_SCORE"
                    row["fallback_reason"] = (
                        "Retriever retornou zero candidatos com score >= min_score. "
                        "Nenhuma tool executada."
                    )
                elif margin is not None and margin < min_relative_margin:
                    # ── GUARDA 3: Margem entre candidatos ────────────────────
                    ambiguous_confirmations += 1
                    abstentions += 1
                    row["execution_status"] = "AMBIGUOUS_CONFIRMATION"
                    row["fallback_reason"] = (
                        f"Margem relativa {margin:.3f} < {min_relative_margin} entre "
                        f"'{top_k_names[0]}' e '{top_k_names[1]}'. "
                        f"Confirmação do cliente requerida antes de executar."
                    )
                else:
                    # ── EXECUÇÃO: os três guardas foram satisfeitos ──────────
                    chosen_tool = top_k_names[0]
                    mock_tool_execution(chosen_tool, query)
                    llm_result = simulate_agent_llm_call(query, chosen_tool)
                    smart_cost += llm_result["cost_usd"]

                    if expected_tool:
                        if chosen_tool == expected_tool:
                            correct_executions += 1
                            row["execution_status"] = "SUCCESS"
                            resolved = True
                        else:
                            incorrect_executions += 1
                            row["execution_status"] = "INCORRECT_TOOL_EXECUTED"
                    else:
                        row["execution_status"] = "EXECUTED_NO_EXPECTED_TOOL"

        smart_cost_total += smart_cost
        smart_latency_ms_total += smart_latency_ms

        baseline_start = time.perf_counter()
        baseline_result = simulate_baseline_llm_call(query)
        baseline_latency_ms_total += (time.perf_counter() - baseline_start) * 1000
        baseline_cost_total += baseline_result["cost_usd"]

        if resolved:
            resolved_smart_cost += smart_cost
            resolved_baseline_cost += baseline_result["cost_usd"]

        rows.append(row)

    router_metrics = compute_router_metrics(y_true, y_pred, labels)
    hit_rate_at_k = compute_precision_at_k(hits_at_k) if hits_at_k else None
    hit_rate_at_1 = compute_precision_at_k(hits_at_1) if hits_at_1 else None
    savings = compute_savings(
        smart_cost_total, smart_latency_ms_total, baseline_cost_total, baseline_latency_ms_total
    )

    total_agent = agent_queries_with_expected_tool
    task_success_rate = float(correct_executions / total_agent) if total_agent > 0 else None
    incorrect_execution_rate = (
        float(incorrect_executions / total_agent) if total_agent > 0 else 0.0
    )
    abstention_rate = float(abstentions / total_agent) if total_agent > 0 else 0.0
    executed = correct_executions + incorrect_executions
    coverage_rate = float(executed / total_agent) if total_agent > 0 else 0.0

    quality_gate = _evaluate_quality_gate(task_success_rate, incorrect_executions)

    report = {
        "n_queries": len(eval_dataset),
        "router_accuracy": router_metrics["accuracy"],
        "confusion_matrix": router_metrics["confusion_matrix"],
        # Nome preciso da métrica; `precision_at_k` é mantido por compatibilidade
        # com o schema da Seção 3.4 da especificação.
        "retrieval_hit_rate_at_1": hit_rate_at_1,
        "retrieval_hit_rate_at_k": hit_rate_at_k,
        "precision_at_k": hit_rate_at_k,
        "k": k,
        "task_success_rate": task_success_rate,
        "coverage_rate": coverage_rate,
        "correct_executions": correct_executions,
        "incorrect_executions": incorrect_executions,
        "abstentions": abstentions,
        "human_fallbacks": human_fallbacks,
        "ambiguous_confirmations": ambiguous_confirmations,
        "thresholds": {
            "router_confidence": ROUTER_CONFIDENCE_THRESHOLD,
            "retriever_min_score": RETRIEVER_MIN_SCORE,
            "min_relative_margin": min_relative_margin,
            "task_success_rate": TASK_SUCCESS_RATE_THRESHOLD,
        },
        "incorrect_execution_rate": incorrect_execution_rate,
        "abstention_rate": abstention_rate,
        **quality_gate,
        "smart_pipeline": {
            "total_cost_usd": smart_cost_total,
            "total_latency_ms": smart_latency_ms_total,
        },
        "baseline_always_llm": {
            "total_cost_usd": baseline_cost_total,
            "total_latency_ms": baseline_latency_ms_total,
        },
        **savings,
        "economics": {
            # Economia sobre o subconjunto que o pipeline realmente resolveu. A diferença
            # em relação a `cost_savings_pct` é o custo que foi deslocado, não eliminado.
            "resolved_smart_cost_usd": resolved_smart_cost,
            "resolved_baseline_cost_usd": resolved_baseline_cost,
            "cost_savings_pct_on_resolved": (
                ((resolved_baseline_cost - resolved_smart_cost) / resolved_baseline_cost) * 100.0
                if resolved_baseline_cost > 0
                else 0.0
            ),
            **compute_fallback_economics(
                smart_cost_usd=smart_cost_total,
                baseline_cost_usd=baseline_cost_total,
                deferred_to_human=abstentions,
                human_fallback_cost_usd=human_fallback_cost_usd,
            ),
        },
        "rows": rows,
    }
    return report


def print_report(report: dict) -> None:
    sep = "=" * 68
    dash = "-" * 68
    print(sep)
    print("HARNESS DE AVALIAÇÃO - Router & Tool Retrieval")
    print(sep)
    print(f"Queries avaliadas: {report['n_queries']}")
    print(f"Acurácia do Router: {report['router_accuracy']:.1%}")
    print(f"Matriz de confusão: {report['confusion_matrix']}")

    if report.get("retrieval_hit_rate_at_1") is not None:
        print(f"Hit Rate@1 do Retriever: {report['retrieval_hit_rate_at_1']:.1%}")
    if report.get("retrieval_hit_rate_at_k") is not None:
        print(f"Hit Rate@{report['k']} do Retriever: {report['retrieval_hit_rate_at_k']:.1%}")

    if report.get("task_success_rate") is not None:
        print(f"Taxa de Execução Correta (Top-1 executado): {report['task_success_rate']:.1%}")
    print(f"Cobertura transacional (executou algo): {report.get('coverage_rate', 0):.1%}")

    print(dash)
    print(f"Execuções corretas          : {report.get('correct_executions', 0)}")
    print(f"Execuções incorretas (risco): {report.get('incorrect_executions', 0)}")
    print(f"Abstenções (total)          : {report.get('abstentions', 0)}")
    print(f"  - fallback humano (confiança baixa): {report.get('human_fallbacks', 0)}")
    print(f"  - confirmação por ambiguidade      : {report.get('ambiguous_confirmations', 0)}")
    print(f"Taxa de execução incorreta  : {report.get('incorrect_execution_rate', 0):.1%}")
    print(f"Taxa de abstenção           : {report.get('abstention_rate', 0):.1%}")

    econ = report.get("economics", {})
    print(dash)
    print(f"Custo pipeline inteligente: ${report['smart_pipeline']['total_cost_usd']:.5f}")
    print(f"Custo baseline (tudo pro LLM): ${report['baseline_always_llm']['total_cost_usd']:.5f}")
    print(f"Economia de custo (total): {report.get('cost_savings_pct', 0):.1f}%")
    print(
        f"Economia de custo (só queries resolvidas): "
        f"{econ.get('cost_savings_pct_on_resolved', 0):.1f}%"
    )
    deferred = econ.get("deferred_to_human", 0)
    print(f"  ATENÇÃO: {deferred} queries foram desviadas para atendimento humano.")
    breakeven = econ.get("human_fallback_breakeven_cost_usd")
    if breakeven is not None:
        print(
            f"  Ponto de equilíbrio: a economia zera se cada desvio custar "
            f"${breakeven:.5f} ou mais."
        )
    assumed = econ.get("human_handling_cost_usd")
    if assumed is not None:
        print(
            f"  Cenário (premissa do chamador, não medição): ${assumed:.5f} por desvio "
            f"-> economia líquida {econ.get('net_cost_savings_pct', 0):.1f}%"
        )
    else:
        print("  Custo do atendimento humano não modelado — a economia acima é nominal.")
    print(f"Latência pipeline inteligente: {report['smart_pipeline']['total_latency_ms']:.1f} ms")
    print(f"Latência baseline: {report['baseline_always_llm']['total_latency_ms']:.1f} ms")
    print(f"Economia de latência: {report.get('latency_savings_pct', 0):.1f}%")
    print(sep)

    # ── Quality Gate ─────────────────────────────────────────────────────────
    status = report.get("operational_status", STATUS_INDETERMINATE)
    approved = report.get("production_approved", False)
    gate_icon = "[OK]" if approved else "[ALERTA]"
    print(f"{gate_icon}  STATUS OPERACIONAL: {status}")
    reasons = report.get("quality_gate_reasons", [])
    if reasons:
        print("   Razoes de reprovacao:")
        for r in reasons:
            print(f"   [X] {r}")
    # Ressalva obrigatória: passar no gate não é prontidão para operação bancária real.
    print(f"   PRONTIDAO: {report.get('production_readiness', READINESS_INSUFFICIENT_EVIDENCE)}")
    print(f"   {report.get('production_readiness_caveat', PRODUCTION_READINESS_CAVEAT)}")
    print(sep)
