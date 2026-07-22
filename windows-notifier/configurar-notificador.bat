@echo off
rem Abre a janela de configuracoes do notificador (autostart, URLs, sair da conta).
start "" pythonw "%~dp0notifier.py" --config
