@echo off
rem Inicia o notificador em segundo plano (sem janela de console).
rem Requer Python 3.10+ instalado no Windows (py launcher).
start "" pythonw "%~dp0notifier.py"
