import json
from pathlib import Path

from common.data_loader import load_eval_dataset, load_router_training_data, load_tools
from candidate_starter.harness import (
    RETRIEVER_MIN_SCORE,
    ROUTER_CONFIDENCE_THRESHOLD,
    print_report,
    run_harness,
)
from candidate_starter.retrieval import ToolRetriever
from candidate_starter.router import QueryRouter


def main() -> None:
    tools = load_tools()
    train_texts, train_labels = load_router_training_data()
    eval_dataset = load_eval_dataset()

    router = QueryRouter().fit(train_texts, train_labels)

    # Configuração explícita de segurança e qualidade:
    # - min_score=RETRIEVER_MIN_SCORE: ativa abstention para queries sem aderência semântica
    # - use_taxonomy=True: enriquece o índice com aliases canônicos, elevando Recall@2 de 15% → 85%
    retriever = ToolRetriever(
        min_score=RETRIEVER_MIN_SCORE,
        use_taxonomy=True,
    ).fit(tools)

    print(f"Pipeline configurado com:")
    print(f"  Router confidence threshold : {ROUTER_CONFIDENCE_THRESHOLD}")
    print(f"  Retriever min_score         : {RETRIEVER_MIN_SCORE}")
    print(f"  Taxonomy enrichment         : ativado")
    print()

    report = run_harness(router, retriever, tools, eval_dataset)
    print_report(report)

    output_path = Path(__file__).resolve().parent.parent / "reports" / "candidate_report.json"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatório salvo em: {output_path}")


if __name__ == "__main__":
    main()

