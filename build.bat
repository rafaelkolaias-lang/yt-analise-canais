@echo off
setlocal

REM ============================================================
REM Build do yt-analise-canais via PyInstaller
REM Gera: dist\yt-analise-canais.exe (arquivo unico, sem console)
REM ============================================================

cd /d "%~dp0"

set "APP_NAME=yt-analise-canais"
set "ENTRY=main.py"

echo.
echo [1/4] Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo [2/4] Verificando PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller nao encontrado. Instalando...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo ERRO: falha ao instalar PyInstaller.
        exit /b 1
    )
)

echo.
echo [3/4] Empacotando...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "%APP_NAME%" ^
    --collect-submodules app ^
    --hidden-import ttkbootstrap ^
    --hidden-import xlsxwriter ^
    --hidden-import dateutil.parser ^
    "%ENTRY%"

if errorlevel 1 (
    echo.
    echo ERRO: build falhou.
    exit /b 1
)

echo.
echo [4/4] Movendo executavel para a raiz e limpando artefatos...
if exist "%APP_NAME%.exe" del /q "%APP_NAME%.exe"
if exist "dist\%APP_NAME%.exe" (
    move /y "dist\%APP_NAME%.exe" "%APP_NAME%.exe" >nul
    if errorlevel 1 (
        echo AVISO: falha ao mover o .exe para a raiz. Arquivo continua em dist\.
    )
) else (
    echo ERRO: nao encontrei dist\%APP_NAME%.exe.
    exit /b 1
)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo ============================================================
echo Build concluido!
echo Executavel: %CD%\%APP_NAME%.exe
echo ============================================================
echo.
echo Dicas:
echo   - O .exe usa a pasta 'dados\' AO LADO DELE (mesma pasta do .exe).
echo   - A primeira execucao cria dados\config.json; preencha as API keys na GUI.
echo   - Para rodar o modo silencioso, use: %APP_NAME%.exe --daily-check

endlocal
