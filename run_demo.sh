#!/usr/bin/env bash
set -e

echo "============================================================"
echo "  DEMO LOCAL: CASE-AGENTS (BANCO DIGITAL - HARNESS DE IA)"
echo "============================================================"
echo ""

if [ ! -d ".venv" ]; then
    echo "[ERRO] Ambiente virtual .venv não encontrado!"
    echo "Execute: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "[1/3] Ativando ambiente virtual .venv..."
source .venv/bin/activate || source .venv/Scripts/activate

echo ""
echo "[2/3] Executando bateria de testes unitários e de sanidade..."
pytest candidate_starter/tests -q
echo "[OK] Todos os testes passaram com 100% de aprovação!"

echo ""
echo "[3/3] Executando Pipeline de Roteamento, Recuperação e Avaliação..."
echo ""
python -m candidate_starter.run_case

echo ""
echo "============================================================"
echo "  DEMONSTRAÇÃO CONCLUÍDA COM SUCESSO!"
echo "  Relatório consolidado salvo em reports/candidate_report.json"
echo "============================================================"
