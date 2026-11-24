"""EgoOps 登录态检查、续登与提示（拆分自 app.py 103-179）"""

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


class AuthMixin:
    """AuthMixin：EgoOps 登录态检查、续登与提示（拆分自 app.py 103-179）"""
    # ---------------------------------------------------------------- EgoOps 登录态

    def _load_egoops_auth_mod(self):
        import importlib.util
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "egoops_auth.py")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "egoops_auth.py")
        spec = importlib.util.spec_from_file_location("egoops_auth", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def check_egoops_login(self):
        """启动时查一次；掉了就马上让用户登录"""
        if not hasattr(self, "lbl_egoops"):
            return
        self.lbl_egoops.config(text="EgoOps 检查中…", foreground="#64748B")

        def work():
            try:
                mod = self._load_egoops_auth_mod()
                ok, who = mod.alive(mod.token_of())
            except Exception as e:
                ok, who = False, str(e)
            self.ui(self._after_login_check, ok, who)

        threading.Thread(target=work, daemon=True).start()

    def _after_login_check(self, ok, who):
        self.login_ok = ok
        self.login_who = who
        if ok:
            self.lbl_egoops.config(text="EgoOps 已登录（%s）" % who, foreground="#15803D")
            try:
                self.btn_login.pack_forget()
            except Exception:
                pass
        else:
            self.lbl_egoops.config(text="EgoOps 登录已失效", foreground="#B91C1C")
            try:
                self.btn_login.config(text="点击登录 EgoOps", style="Danger.TButton")
                self.btn_login.pack(fill="x", pady=(0, 8), before=self.lbl_section)
            except Exception:
                pass

    def prompt_login(self, why=""):
        msg = ("EgoOps 登录态已失效%s。\n\n现在登录吗？登录时会弹出一个浏览器窗口，"
               "用手机验证码登一次就好。\n" % (("（%s）" % why) if why else ""))
        if messagebox.askyesno(APP_NAME, msg):
            self.do_login()

    def do_login(self):
        self.lbl_egoops.config(text="正在打开登录窗口…", foreground="#B45309")
        self.lbl_task.config(text="请在弹出的窗口里登录 EgoOps（最多等 5 分钟）")

        def work():
            try:
                mod = self._load_egoops_auth_mod()
                ok, info = mod.refresh(log=lambda m: self.ui(self.lbl_task.config, text=str(m)))
            except Exception as e:
                ok, info = False, str(e)
            self.ui(self._after_login, ok, info)

        threading.Thread(target=work, daemon=True).start()

    def _after_login(self, ok, info):
        if ok:
            self.lbl_egoops.config(text="EgoOps：已登录", foreground="#15803D")
            self.lbl_task.config(text=str(info))
            messagebox.showinfo(APP_NAME, str(info))
            self.check_egoops_login()
        else:
            self.lbl_egoops.config(text="EgoOps：未登录", foreground="#B91C1C")
            self.lbl_task.config(text=str(info))
            messagebox.showwarning(APP_NAME, str(info))
