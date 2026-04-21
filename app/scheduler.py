# -*- coding: utf-8 -*-
"""Agendador via schtasks do Windows (onlogon) para o monitoramento diário.

Cria uma tarefa que roda `python main.py --daily-check` sempre que o usuário
fizer login. O próprio `daily_monitor` tem a trava "já rodou hoje".
"""
import os
import subprocess
import sys
from pathlib import Path

from . import config


TASK_NAME = "yt-analise-canais-daily"
STARTUP_LNK_NAME = "yt-analise-canais-daily.bat"


def _main_py_path() -> Path:
    return config.PROJECT_ROOT / "main.py"


def _python_exe() -> str:
    # Se estivermos num .exe empacotado (PyInstaller), sys.executable é o próprio .exe
    # e não tem sentido chamar 'python main.py' — seria só chamar o .exe com --daily-check.
    return sys.executable


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _startup_bat_path() -> Path:
    return _startup_dir() / STARTUP_LNK_NAME


def _command_for_daily_check() -> str:
    """Monta o comando executado pelo agendador/startup."""
    py = _python_exe()
    main_py = _main_py_path()
    if py.lower().endswith("python.exe") or py.lower().endswith("pythonw.exe"):
        # pythonw.exe não abre console preto
        pyw = py.replace("python.exe", "pythonw.exe")
        return f'"{pyw}" "{main_py}" --daily-check'
    # PyInstaller / .exe empacotado
    return f'"{py}" --daily-check'


def _has_task() -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _has_startup_bat() -> bool:
    return _startup_bat_path().exists()


def is_enabled() -> bool:
    return _has_task() or _has_startup_bat()


def _enable_via_schtasks() -> tuple[bool, str]:
    tr = _command_for_daily_check()
    try:
        r = subprocess.run(
            [
                "schtasks", "/create", "/f",
                "/tn", TASK_NAME,
                "/sc", "onlogon",
                "/tr", tr,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return True, "Tarefa registrada no Agendador do Windows."
        return False, (r.stderr or r.stdout or "falha desconhecida").strip()
    except Exception as ex:
        return False, f"Erro: {ex}"


def _enable_via_startup() -> tuple[bool, str]:
    """Fallback: cria um .bat em shell:startup que roda o comando silenciosamente."""
    try:
        target = _startup_bat_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tr = _command_for_daily_check()
        # 'start "" /min ...' roda sem abrir janela (pythonw não abre console mesmo).
        content = "@echo off\r\nstart \"\" /b " + tr + "\r\n"
        target.write_text(content, encoding="utf-8")
        return True, f"Script de inicialização criado em:\n{target}"
    except Exception as ex:
        return False, f"Erro ao criar startup script: {ex}"


def enable() -> tuple[bool, str]:
    """Tenta via schtasks; se falhar (acesso negado, etc), cai para Startup folder."""
    ok, msg = _enable_via_schtasks()
    if ok:
        return True, msg
    ok2, msg2 = _enable_via_startup()
    if ok2:
        return True, (
            "schtasks indisponível (provavelmente precisa de admin). "
            "Usando pasta Startup como fallback.\n\n" + msg2
        )
    return False, f"schtasks falhou: {msg}\nStartup fallback também falhou: {msg2}"


def _disable_schtasks() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["schtasks", "/delete", "/f", "/tn", TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return True, "Tarefa removida."
        return False, (r.stderr or r.stdout or "falha desconhecida").strip()
    except Exception as ex:
        return False, f"Erro: {ex}"


def _disable_startup() -> tuple[bool, str]:
    try:
        p = _startup_bat_path()
        if p.exists():
            p.unlink()
            return True, f"Script de inicialização removido: {p}"
        return True, "Nenhum script de inicialização encontrado."
    except Exception as ex:
        return False, f"Erro ao remover startup script: {ex}"


def disable() -> tuple[bool, str]:
    """Remove de ambas as fontes (tarefa e startup) se existirem."""
    removed = []
    errors = []

    if _has_task():
        ok, msg = _disable_schtasks()
        if ok:
            removed.append("tarefa do agendador")
        else:
            errors.append(msg)

    if _has_startup_bat():
        ok, msg = _disable_startup()
        if ok:
            removed.append("script da pasta Startup")
        else:
            errors.append(msg)

    if not removed and not errors:
        return True, "Nada para desativar."
    if errors and not removed:
        return False, "; ".join(errors)
    summary = "Removido: " + ", ".join(removed) + "."
    if errors:
        summary += " Avisos: " + "; ".join(errors)
    return True, summary
