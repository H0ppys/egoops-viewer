"""Tk 主题与 ttk 样式（拆分自 app.py 93-219：_apply_theme / _style）"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk  # noqa: F401

from .config import (APP_NAME, APP_VER, CONFIG_DIR, CONFIG_PATH,  # noqa: F401
                     DEFAULT_SERVER, load_config, save_config)
from .api_client import Api, ApiError, human_size  # noqa: F401
from .address_parse import parse as parse_address  # noqa: F401
from . import extras  # noqa: F401


class ThemeMixin:
    """ThemeMixin：Tk 主题与 ttk 样式（拆分自 app.py 93-219：_apply_theme / _style）"""
    # ---------------------------------------------------------------- 样式

    def _apply_theme(self):
        try:
            import sv_ttk
            sv_ttk.set_theme("light")
            self.modern = True
        except Exception:
            self.modern = False

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("vista")
        except Exception:
            pass
        s.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 10))
        s.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 6))
        s.configure("Big.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(14, 10))
        try:
            if getattr(self, "modern", False):
                base = 10
            else:
                base = 9
        except Exception:
            base = 9
        s.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        s.configure("Section.TLabel", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Dim.TLabel", font=("Microsoft YaHei UI", base))
        s.configure("Guide.TLabel", font=("Microsoft YaHei UI", base + 1), foreground="#334155")
        s.configure("Status.TLabel", font=("Microsoft YaHei UI", base))
        s.configure("Preview.TLabel", font=("Microsoft YaHei UI", base), foreground="#64748B")
        s.configure("Card.TFrame", relief="solid", borderwidth=1)
        try:
            s.configure("Danger.TButton", foreground="#B91C1C")
        except Exception:
            pass
        s.configure("Big.Treeview", rowheight=44, font=("Microsoft YaHei UI", 11))
        s.configure("Big.Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Head.TFrame", background="#FFFFFF")
        s.configure("Dim.TLabel", foreground="#64748B", background="#FFFFFF", font=("Microsoft YaHei UI", 9))
        s.configure("Card.Treeview", rowheight=28, font=("Microsoft YaHei UI", 9),
                    fieldbackground="#FFFFFF", background="#FFFFFF", borderwidth=0)
        s.configure("Card.Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"), padding=(6, 6))
        s.configure("Title.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        s.configure("Group.TLabel", font=("Microsoft YaHei UI", 10, "bold"), foreground="#6b7a90", width=6)
        s.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Danger.TButton", font=("Microsoft YaHei UI", 10), foreground="#b3261e")
