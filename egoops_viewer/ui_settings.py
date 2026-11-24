"""设置对话框：服务器 / 大模型 / 存储占用（拆分自 app.py 458-753）"""

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


class SettingsMixin:
    """SettingsMixin：设置对话框：服务器 / 大模型 / 存储占用（拆分自 app.py 458-753）"""
    # ---------------------------------------------------------------- 设置（服务器 / 大模型）

    # ---------------------------------------------------------------- 设置（服务器 / 大模型）

    # ---------------------------------------------------------------- 设置（服务器 / 大模型）

    def storage_dialog(self):
        self.lbl_task.config(text="正在检查服务器存储…")

        def work():
            try:
                st = self.api._request("GET", "/api/storage", timeout=30)
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "检查失败：%s" % e)
                return
            self.ui(self._show_storage, st)

        threading.Thread(target=work, daemon=True).start()

    def _show_storage(self, st):
        def human(n):
            n = float(n or 0)
            for unit in ("B", "KB", "MB", "GB"):
                if n < 1024:
                    return "%.1f %s" % (n, unit)
                n /= 1024
            return "%.1f TB" % n

        msg = (
            "数据库记录：%d 个文件，%s\n"
            "磁盘实际：%s\n"
            "无记录的残留文件：%d 个，%s\n"
            "未完成的上传分片：%s\n"
        ) % (st.get("db_files", 0), human(st.get("db_bytes")),
             human(st.get("disk_bytes")),
             st.get("orphan_files", 0), human(st.get("orphan_bytes")),
             human(st.get("tmp_bytes")))

        if st.get("db_bytes") == st.get("disk_bytes") and not st.get("orphan_files"):
            msg += "\n✓ 数据库与磁盘一致，没有多余备份。"

        if messagebox.askyesno(APP_NAME, msg + "\n\n要清理残留文件吗？"):
            self.lbl_task.config(text="正在清理…")

            def run():
                try:
                    r = self.api._request("POST", "/api/storage/cleanup", {}, timeout=60)
                except Exception as e:
                    self.ui(messagebox.showerror, APP_NAME, "清理失败：%s" % e)
                    return
                self.ui(messagebox.showinfo, APP_NAME,
                        "已清理 %d 个残留文件，释放 %s"
                        % (r.get("removed_files", 0), human(r.get("freed_bytes"))))
                self.ui(self.do_refresh)

            threading.Thread(target=run, daemon=True).start()

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("640x600")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        bar = ttk.Frame(win)
        bar.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        # --- 服务器 ---
        tab1 = ttk.Frame(nb, padding=14)
        nb.add(tab1, text="服务器")
        ttk.Label(tab1, text="采集服务器地址").pack(anchor="w")
        e_server = ttk.Entry(tab1, font=("Consolas", 10))
        e_server.insert(0, self.var_server.get())
        e_server.pack(fill="x", pady=(4, 12))
        ttk.Label(tab1, text="姓名（只用来记谁在看）").pack(anchor="w")
        e_name = ttk.Entry(tab1)
        e_name.insert(0, self.var_name.get())
        e_name.pack(fill="x", pady=(4, 12))
        ttk.Label(tab1, text="下载目录").pack(anchor="w")
        e_dir = ttk.Entry(tab1)
        e_dir.insert(0, self.cfg.get("download_dir", ""))
        e_dir.pack(fill="x", pady=(4, 4))
        ttk.Button(tab1, text="选择…", command=lambda: self._pick_dir_into(e_dir)).pack(anchor="w")

        ttk.Separator(tab1, orient="horizontal").pack(fill="x", pady=12)
        ttk.Label(tab1, text="EgoOps 登录态").pack(anchor="w")
        login_state = ttk.Label(tab1, text="", foreground="#8a97a8")
        login_state.pack(anchor="w", pady=(2, 6))

        def show_state():
            path = os.path.join(os.environ.get("APPDATA") or ".", "egoops-viewer", "egoops_auth.json")
            if not os.path.exists(path):
                login_state.config(text="没有登录态文件，先点下面按钮登录一次", foreground="#b3261e")
                return
            try:
                import json as _json
                d = _json.load(open(path, encoding="utf-8"))
                login_state.config(text="上次保存：%s" % d.get("saved_at", "未知"), foreground="#1f7a3d")
            except Exception:
                login_state.config(text="登录态文件损坏", foreground="#b3261e")

        def refresh_login():
            login_state.config(text="正在打开浏览器校验…", foreground="#8a97a8")

            def work():
                try:
                    import importlib.util
                    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
                    path = os.path.join(base, "egoops_auth.py")
                    if not os.path.exists(path):
                        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "egoops_auth.py")
                    spec = importlib.util.spec_from_file_location("egoops_auth", path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    ok, info = mod.refresh()
                    self.ui(lambda i=info, s=ok: login_state.config(
                        text=("✓ " if s else "✗ ") + i,
                        foreground="#1f7a3d" if s else "#b3261e"))
                except Exception as e:
                    self.ui(lambda err=str(e): login_state.config(text="✗ 失败：" + err, foreground="#b3261e"))

            threading.Thread(target=work, daemon=True).start()

        bar2 = ttk.Frame(tab1)
        bar2.pack(anchor="w")
        ttk.Button(bar2, text="刷新登录态", command=refresh_login).pack(side="left")
        ttk.Button(bar2, text="查看状态", command=show_state).pack(side="left", padx=6)
        show_state()

        # --- 大模型 ---
        tab2 = ttk.Frame(nb, padding=14)
        nb.add(tab2, text="大模型 API")
        llm = self.cfg.get("llm") or {}
        ttk.Label(tab2, text="接口地址（OpenAI 兼容）").pack(anchor="w")
        e_base = ttk.Entry(tab2, font=("Consolas", 10))
        e_base.insert(0, llm.get("base") or "https://api.deepseek.com/v1")
        e_base.pack(fill="x", pady=(4, 10))

        ttk.Label(tab2, text="模型名").pack(anchor="w")
        e_model = ttk.Entry(tab2, font=("Consolas", 10))
        e_model.insert(0, llm.get("model") or "deepseek-chat")
        e_model.pack(fill="x", pady=(4, 10))

        ttk.Label(tab2, text="API Key").pack(anchor="w")
        e_key = ttk.Entry(tab2, show="*", font=("Consolas", 10))
        e_key.insert(0, llm.get("key") or "")
        e_key.pack(fill="x", pady=(4, 10))

        ttk.Label(tab2, text="用于：生成采集点描述、任务描述、SOP 步骤",
                  foreground="#8a97a8").pack(anchor="w", pady=(0, 8))

        out = ttk.Label(tab2, text="", foreground="#1f7a3d", wraplength=480, justify="left")
        out.pack(anchor="w", pady=(4, 0))

        def test_llm():
            base = e_base.get().strip().rstrip("/")
            model = e_model.get().strip()
            key = e_key.get().strip()
            if not key:
                out.config(text="先填 API Key", foreground="#b3261e")
                return
            out.config(text="测试中…", foreground="#8a97a8")

            def run():
                try:
                    import json as _j
                    import urllib.request as _u
                    payload = _j.dumps({
                        "model": model,
                        "messages": [{"role": "user", "content": "只回复两个字：可用"}],
                        "max_tokens": 16,
                    }).encode()
                    req = _u.Request(base + "/chat/completions", data=payload, method="POST")
                    req.add_header("Content-Type", "application/json")
                    req.add_header("Authorization", "Bearer " + key)
                    with _u.urlopen(req, timeout=30) as r:
                        data = _j.loads(r.read().decode())
                    text = data["choices"][0]["message"]["content"].strip()
                    self.ui(out.config, text="✓ 连接成功，模型回复：%s" % text, foreground="#1f7a3d")
                except Exception as e:
                    self.ui(out.config, text="✗ 失败：%s" % e, foreground="#b3261e")

            import threading as _t
            _t.Thread(target=run, daemon=True).start()

        ttk.Button(tab2, text="测试连接", command=test_llm).pack(anchor="w", pady=(6, 0))

        # --- 邀请码（本地：码 → 厂商，只存这台电脑）---
        tab3 = ttk.Frame(nb, padding=12)
        nb.add(tab3, text="邀请码")

        ttk.Label(tab3, text="邀请码和厂商的对应关系只保存在这台电脑，服务器不参与。",
                  foreground="#8a97a8").pack(anchor="w", pady=(0, 8))

        cols3 = ("code", "vendor")
        tv3 = ttk.Treeview(tab3, columns=cols3, show="headings", height=9)
        for c, t, w in zip(cols3, ("邀请码", "厂商"), (140, 320)):
            tv3.heading(c, text=t)
            tv3.column(c, width=w, anchor="w")
        tv3.pack(fill="both", expand=True)

        def refresh_codes():
            for i in tv3.get_children():
                tv3.delete(i)
            for code, vendor in sorted(self.invites_map().items()):
                tv3.insert("", "end", values=(code, vendor))

        row_add = ttk.Frame(tab3)
        row_add.pack(fill="x", pady=(8, 0))
        e_code = ttk.Entry(row_add, width=16)
        e_code.pack(side="left")
        ttk.Label(row_add, text="→").pack(side="left", padx=6)
        e_vendor = ttk.Entry(row_add, width=30)
        e_vendor.pack(side="left")

        def add_code():
            code = e_code.get().strip().upper()   # 统一按大写存，避免一个码两条记录
            vendor = e_vendor.get().strip()
            if not code or not vendor:
                messagebox.showinfo(APP_NAME, "邀请码和厂商名都要填", parent=win)
                return
            m = dict(self.invites_map())
            m[code] = vendor
            self.cfg["invites"] = m
            save_config(self.cfg)
            refresh_codes()
            self.load_vendors()
            self.do_refresh()
            e_code.delete(0, "end")
            e_vendor.delete(0, "end")

        def del_code():
            sel = tv3.selection()
            if not sel:
                return
            code = tv3.item(sel[0], "values")[0]
            m = dict(self.invites_map())
            m.pop(code, None)
            self.cfg["invites"] = m
            save_config(self.cfg)
            refresh_codes()
            self.load_vendors()
            self.do_refresh()

        # 选中一行时回填到输入框，方便改
        def fill_inputs(_evt=None):
            sel = tv3.selection()
            if sel:
                vals = tv3.item(sel[0], "values")
                e_code.delete(0, "end")
                e_code.insert(0, vals[0])
                e_vendor.delete(0, "end")
                e_vendor.insert(0, vals[1])

        tv3.bind("<<TreeviewSelect>>", fill_inputs)

        btns3 = ttk.Frame(tab3)
        btns3.pack(fill="x", pady=(8, 0))
        ttk.Button(btns3, text="添加 / 更新", style="Primary.TButton", command=add_code).pack(side="left")
        ttk.Button(btns3, text="删除选中", style="Danger.TButton", command=del_code).pack(side="left", padx=6)

        ttk.Label(tab3, text="采集员在 App 里填这个码，数据上传后这里按码显示厂商。",
                  foreground="#8a97a8").pack(anchor="w", pady=(8, 0))

        refresh_codes()

        def save_all():
            self.cfg["server"] = e_server.get().strip()
            self.cfg["name"] = e_name.get().strip()
            self.cfg["download_dir"] = e_dir.get().strip()
            self.cfg["llm"] = {
                "base": e_base.get().strip(),
                "model": e_model.get().strip(),
                "key": e_key.get().strip(),
            }
            save_config(self.cfg)
            self.var_server.set("")
            self.var_server.set(self.cfg["server"])
            self.var_name.set("")
            self.var_name.set(self.cfg["name"])
            win.destroy()
            messagebox.showinfo(APP_NAME, "已保存")

        ttk.Button(bar, text="保存", style="Primary.TButton", command=save_all).pack(side="right")
        ttk.Button(bar, text="取消", command=win.destroy).pack(side="right", padx=8)

    def _pick_dir_into(self, entry):
        d = filedialog.askdirectory(title="选择下载目录")
        if d:
            entry.delete(0, "end")
            entry.insert(0, d)
