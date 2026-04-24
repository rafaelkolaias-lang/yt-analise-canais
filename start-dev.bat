@echo off
REM =========================================================
REM youtube-analyzer — dev launcher
REM Abre 2 terminais: API (FastAPI / porta 8000) e WEB (Next.js / porta 3000)
REM Pre-requisito: MySQL do XAMPP ligado (painel XAMPP -> Start em MySQL)
REM Parar: feche as janelas ou Ctrl+C em cada uma
REM =========================================================

set "ROOT=%~dp0"

if not exist "%ROOT%api\.venv\Scripts\python.exe" (
    echo [ERRO] venv da API nao encontrada em api\.venv
    echo Rode primeiro: cd api ^&^& python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%ROOT%web\node_modules" (
    echo [ERRO] node_modules nao encontrado em web\
    echo Rode primeiro: cd web ^&^& npm install
    pause
    exit /b 1
)

echo Iniciando youtube-analyzer...
echo - API:       http://localhost:8000  (Swagger: /docs)
echo - WEB:       http://localhost:3000
echo - Config UI: http://localhost:3000/configuracoes
echo.

start "youtube-analyzer API" cmd /k "cd /d "%ROOT%api" && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"
start "youtube-analyzer WEB" cmd /k "cd /d "%ROOT%web" && npm run dev"

echo Janelas abertas. Essa janela pode ser fechada.
timeout /t 3 >nul
