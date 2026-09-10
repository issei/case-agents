"""O relatório versionado precisa ser um snapshot identificado, não uma alegação solta.

`reports/candidate_report.json` está no repositório para facilitar a inspeção. Um JSON de
métricas versionado tem um modo de falha próprio: envelhecer em silêncio. O código muda, o
arquivo continua lá, e quem lê acredita em números que o commit atual não produz mais.

Estes testes exigem duas coisas do arquivo:
  1. procedência declarada (commit, timestamp, seed, versões) — sem isso não é auditável;
  2. correspondência com o código atual — as decisões registradas têm de ser as que o
     retriever de hoje produz.

A latência é deliberadamente excluída da comparação: os mocks usam `sleep` aleatório e
variam entre execuções. Decisões e custo são determinísticos; latência não é.
"""
import json
import subprocess
from pathlib import Path

import pytest

from candidate_starter.harness import RETRIEVER_MIN_SCORE
from candidate_starter.retrieval import ToolRetriever
from common.data_loader import load_tools

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "reports" / "candidate_report.json"


@pytest.fixture(scope="module")
def report():
    if not REPORT_PATH.exists():
        pytest.skip("relatório ainda não gerado — rode `python -m candidate_starter.run_case`")
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _git(*args):
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def test_report_declares_its_provenance(report):
    """Sem proveniência, o arquivo é um número sem data nem origem."""
    snapshot = report.get("snapshot")
    assert snapshot, "relatório versionado sem bloco `snapshot`"
    for field in ("generated_at_utc", "git_commit", "git_dirty", "random_seed",
                  "python_version", "dependencies"):
        assert field in snapshot, f"proveniência incompleta: falta '{field}'"
    assert snapshot["dependencies"].get("scikit-learn"), (
        "a versão do scikit-learn muda o ranking; precisa estar registrada"
    )


def test_report_matches_the_current_commit_when_the_tree_is_clean():
    """Árvore limpa e relatório de outro commit = número publicado desatualizado."""
    if not REPORT_PATH.exists():
        pytest.skip("relatório ainda não gerado")
    head = _git("rev-parse", "HEAD")
    if head is None:
        pytest.skip("git indisponível")
    if _git("status", "--porcelain"):
        pytest.skip("árvore suja: o snapshot não tem como corresponder a um commit")

    snapshot = json.loads(REPORT_PATH.read_text(encoding="utf-8"))["snapshot"]
    assert snapshot["git_dirty"] is False, (
        "relatório gerado sobre alterações não commitadas foi versionado como se fosse "
        "um snapshot reprodutível"
    )
    assert snapshot["git_commit"] == head, (
        f"relatório gerado em {snapshot['git_commit']}, HEAD está em {head}. "
        f"Regenere com `python -m candidate_starter.run_case`."
    )


def test_report_decisions_still_reproduce_with_the_current_code(report):
    """A verificação que realmente importa: o código de hoje toma as mesmas decisões.

    Recomputa apenas a recuperação (sem os `sleep` dos mocks de LLM) e compara com o que
    ficou gravado. Se a taxonomia, o scoring ou o catálogo mudarem sem regenerar o
    relatório, este teste falha — que é exatamente o alarme desejado.
    """
    retriever = ToolRetriever(min_score=RETRIEVER_MIN_SCORE, use_taxonomy=True).fit(load_tools())

    compared = 0
    for row in report["rows"]:
        if "retrieved_tools" not in row or row["predicted_route"] != "AGENT":
            continue
        if row["execution_status"] == "HUMAN_FALLBACK_LOW_CONFIDENCE":
            continue  # o retriever nem foi chamado nesta linha
        current = [m.name for m in retriever.search(row["query"], k=report["k"]).matches]
        assert current == row["retrieved_tools"], (
            f"'{row['query']}': relatório diz {row['retrieved_tools']}, "
            f"o código atual devolve {current}. Regenere o relatório."
        )
        compared += 1

    assert compared > 0, "nenhuma linha transacional comparada — relatório vazio?"
