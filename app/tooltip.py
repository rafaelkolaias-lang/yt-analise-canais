# -*- coding: utf-8 -*-
"""Tooltip simples para widgets Tkinter."""
import tkinter as tk
from tkinter import ttk


class Tooltip:
    def __init__(self, widget, text, delay_ms=350, wraplength=320):
        self.widget = widget
        self.text = text
        self.delay = delay_ms
        self.wraplength = wraplength
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _e=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        lbl = tk.Label(
            tw, text=self.text, justify="left",
            background="#222", foreground="#eee",
            relief="solid", borderwidth=1,
            wraplength=self.wraplength,
            padx=8, pady=6,
            font=("Segoe UI", 9),
        )
        lbl.pack()

    def _hide(self, _e=None):
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def help_badge(parent, text):
    """Cria um label '?' clicável-hover com tooltip; retorna o widget para .grid()/pack()."""
    lbl = ttk.Label(parent, text=" ? ", cursor="question_arrow")
    try:
        lbl.configure(foreground="#4ea1ff")
    except Exception:
        pass
    Tooltip(lbl, text)
    return lbl
