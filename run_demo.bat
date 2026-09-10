@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   DEMO LOCAL: CASE-AGENTS (BANCO DIGITAL - HARNESS DE IA)
echo ============================================================
echo.

REM Verifica presenca do ambiente virtual
if not exist ".venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual .venv nao encontrado!
    echo Execute: py -3.12 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo [1/3] Ativando ambiente virtual .venv...
call .venv\Scripts\activate.bat

echo.
echo [2/3] Executando bateria completa de testes de sanidade e unitarios...
pytest candidate_starter/tests -q
if %ERRORLEVEL% neq 0 (
    echo [FALHA] Testes unitarios falharam! Verifique os logs.
    pause
    exit /b %ERRORLEVEL%
)
echo [OK] Todos os testes passaram com 100%% de aprovacao!

echo.
echo [3/3] Executando Pipeline de Roteamento, Recuperacao e Avaliacao...
echo.
python -m candidate_starter.run_case

echo.
echo ============================================================
echo   DEMONSTRACAO CONCLUIDA COM SUCESSO!
echo   Relatorio consolidado salvo em reports\candidate_report.json
echo ============================================================
echo.
pause
