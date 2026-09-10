import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from common.data_loader import load_eval_dataset, load_router_training_data, load_tools
from candidate_starter.harness import (
    MIN_RELATIVE_MARGIN,
    RETRIEVER_MIN_SCORE,
    ROUTER_CONFIDENCE_THRESHOLD,
    print_report,
    run_harness,
)
from candidate_starter.retrieval import DEFAULT_INTENT_WEIGHT, ToolRetriever
from candidate_starter.router import QueryRouter
from common.mock_llm import RANDOM_SEED

ROOT = Path(__file__).resolve().parent.parent

HUMAN_FALLBACK_COST_SCENARIO_USD: float = 0.50
"""Custo assumido por query desviada para atendimento humano.

PREMISSA DE CENÁRIO, NÃO MEDIÇÃO. Não há dado de atendimento real neste case; o valor
existe para que a economia líquida seja calculável e comparável ao ponto de equilíbrio,
que o harness deriva das medições e não depende deste número.
"""


def _git(*args: str) -> str:
    """Metadado do git, ou string vazia fora de um repositório."""
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _source_is_dirty() -> bool:
    """Há alteração de FONTE não commitada?

    `reports/` fica deliberadamente fora da conta. O relatório é escrito por esta mesma
    execução e, uma vez versionado, regenerá-lo suja a árvore por conta própria — incluí-lo
    faria toda execução a partir da segunda se declarar irreprodutível por causa do arquivo
    que ela acabou de gerar. O que `git_dirty` precisa responder é se o CÓDIGO que produziu
    estes números estava commitado.
    """
    status = _git("status", "--porcelain")
    return any(
        line[3:].strip() and not line[3:].strip().startswith("reports/")
        for line in status.splitlines()
    )


def build_snapshot() -> dict:
    """Procedência do relatório: sem isso um JSON versionado vira alegação sem data.

    A latência é aleatória entre execuções e o catálogo muda com o commit — um relatório
    no repositório só é auditável se disser de qual commit, seed e versão de dependências
    ele saiu. `git_dirty` marca a execução feita sobre alterações não commitadas.
    """
    def pkg(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return "não instalado"

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "HEAD") or None,
        "git_dirty": _source_is_dirty(),
        "random_seed": RANDOM_SEED,
        "python_version": platform.python_version(),
        "dependencies": {name: pkg(name) for name in ("scikit-learn", "numpy", "scipy")},
        "note": (
            "Snapshot de uma execução. Latência é simulada com sleep aleatório e varia "
            "entre execuções; custo e decisões são determinísticos para o mesmo commit."
        ),
    }


def main() -> None:
    tools = load_tools()
    train_texts, train_labels = load_router_training_data()
    eval_dataset = load_eval_dataset()

    router = QueryRouter().fit(train_texts, train_labels)

    # Configuração explícita de segurança e qualidade:
    # - min_score=RETRIEVER_MIN_SCORE: abstenção para queries sem aderência semântica
    # - use_taxonomy=True: recuperação em nível de capacidade + campo de glossário
    retriever = ToolRetriever(
        min_score=RETRIEVER_MIN_SCORE,
        use_taxonomy=True,
    ).fit(tools)

    print("Pipeline configurado com:")
    print(f"  Router confidence threshold : {ROUTER_CONFIDENCE_THRESHOLD}")
    print(f"  Retriever min_score         : {RETRIEVER_MIN_SCORE}")
    print(f"  Margem relativa mínima      : {MIN_RELATIVE_MARGIN}")
    print(f"  Taxonomia de capacidades    : ativada (alpha={DEFAULT_INTENT_WEIGHT})")
    print(f"  Custo/desvio humano (cenário): ${HUMAN_FALLBACK_COST_SCENARIO_USD:.2f} (premissa)")
    print()

    report = run_harness(
        router,
        retriever,
        tools,
        eval_dataset,
        human_fallback_cost_usd=HUMAN_FALLBACK_COST_SCENARIO_USD,
    )
    report["snapshot"] = build_snapshot()
    print_report(report)

    output_path = ROOT / "reports" / "candidate_report.json"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatório salvo em: {output_path}")
    if report["snapshot"]["git_dirty"]:
        print("AVISO: gerado com alterações não commitadas — snapshot não é reprodutível.")


if __name__ == "__main__":
    main()

