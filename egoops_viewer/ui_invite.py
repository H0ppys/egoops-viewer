"""邀请码对话框（拆分自 app.py 754-826）"""

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


class InviteMixin:
    """InviteMixin：邀请码对话框（拆分自 app.py 754-826）"""
    # ---------------------------------------------------------------- 邀请码

    def open_invite(self):
        """查看/生成/关闭邀请码。手机端必须填对同一个码才能上传。"""
        key = (self.cfg.get("admin_key") or "").strip()
        if not key:
            key = simpledialog.askstring(
                "管理口令", "请输入服务器管理口令（adminKey）：\n（填一次会记住）", parent=self.root)
            if not key:
                return
            key = key.strip()
            self.cfg["admin_key"] = key
            save_config(self.cfg)

        win = tk.Toplevel(self.root)
        win.title("邀请码")
        win.geometry("440x300")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        ttk.Label(win, text="当前邀请码", font=("Microsoft YaHei UI", 11)).pack(pady=(20, 6))
        lbl = ttk.Label(win, text="读取中…", font=("Consolas", 30, "bold"), foreground="#2f6fed")
        lbl.pack()
        state = ttk.Label(win, text="", foreground="#666")
        state.pack(pady=(4, 14))

        server = self.var_server.get().strip()

        def call(fn):
            try:
                r = fn()
                code = r.get("code", "")
                lbl.config(text=code if code else "（未启用）", foreground="#2f6fed" if code else "#999")
                state.config(text="已启用：手机上必须填这个码才能上传" if code
                             else "未启用：任何拿到地址的人都能上传，建议生成一个", foreground="#b3261e" if not code else "#1f7a3d")
            except ApiError as e:
                state.config(text="操作失败：%s" % e, foreground="#b3261e")
            except Exception as e:
                state.config(text="操作失败：%s" % e, foreground="#b3261e")

        def bg(fn):
            threading.Thread(target=lambda: self.ui(call, fn), daemon=True).start()

        api = Api(server)
        bg(lambda: api.invite_get(key))

        btns = ttk.Frame(win)
        btns.pack(pady=6)

        def gen():
            state.config(text="生成中…", foreground="#666")
            bg(lambda: api.invite_generate(key))

        def close_invite():
            if not messagebox.askyesno(APP_NAME, "关闭邀请码后，任何人拿到地址都能上传，确定？", parent=win):
                return
            state.config(text="关闭中…", foreground="#666")
            bg(lambda: api.invite_disable(key))

        def copy_code():
            self.root.clipboard_clear()
            self.root.clipboard_append(lbl.cget("text"))
            state.config(text="已复制到剪贴板", foreground="#1f7a3d")

        ttk.Button(btns, text="生成新邀请码", command=gen).pack(side="left", padx=4)
        ttk.Button(btns, text="复制", command=copy_code).pack(side="left", padx=4)
        ttk.Button(btns, text="关闭邀请码", command=close_invite).pack(side="left", padx=4)

        ttk.Label(win, text="手机：设置 → 邀请码，填这个码；填错就传不上去。",
                  foreground="#6b7a90").pack(pady=(14, 0))
        ttk.Button(win, text="关闭窗口", command=win.destroy).pack(pady=(10, 0))
