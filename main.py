# -*- coding: utf-8 -*-
"""Entrypoint do app. Toda a lógica vive em app/.

Uso:
    python main.py              # abre a GUI normalmente
    python main.py --daily-check  # roda a checagem diária silenciosa (usado pelo scheduler)
"""
import sys


def main():
    if "--daily-check" in sys.argv:
        from app.daily_monitor import run_if_due
        result = run_if_due()
        if result == "open_app":
            from app.gui import main as gui_main
            gui_main()
        return

    from app.gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
