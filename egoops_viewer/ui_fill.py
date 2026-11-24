"""申请采集点自动填表（拆分自 app.py 944-1107）"""

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


class FillMixin:
    """FillMixin：申请采集点自动填表（拆分自 app.py 944-1107）"""
    # ---------------------------------------------------------------- 申请采集点（自动填表）

    def _ensure_meituan(self, site):
        """只有美团走 EgoOps；其它厂商的提交流程还没接，别把数据推进美团账号"""
        code = (site.get("invite") or "").strip().upper()
        sysname = self.vendor_systems.get(code, "")
        if sysname == "meituan":
            return True
        vendor = self.vendor_names.get(code) or (code or "未填邀请码")
        messagebox.showwarning(
            APP_NAME,
            "这个采集点的厂商是「%s」，提交系统和美团 EgoOps 不一样。\n\n"
            "目前只接入了美团的 EgoOps，其它厂商还需要单独对接。\n"
            "这个采集点你可以照常：下载素材、质检、导出表格。" % vendor)
        return False

    def fill_egoops(self):
        """一条龙：建草稿 + 填字段 + 转码上传素材 + 写 SOP，不提交审核"""
        site, iid = self._target_site()
        if not site:
            messagebox.showinfo(APP_NAME, "先勾选一个采集点（点最左边的方框）")
            return
        if not self._ensure_meituan(site):
            return
        if getattr(self, "login_ok", None) is False:
            if messagebox.askyesno(APP_NAME, "EgoOps 登录已失效，需要先登录才能建草稿。\n\n现在登录吗？"):
                self.do_login()
            return

        labels = [
            ("name", "采集点名称", site.get("name", "")),
            ("address", "现场地址", site.get("address", "")),
            ("scene", "采集场景分类", site.get("scene_label") or site.get("scene") or ""),
            ("desc", "采集点描述（模型生成）", "自动"),
            ("sop", "任务描述 + SOP（模型生成）", "自动"),
            ("media", "任务照片/视频（视频自动转 H.264）", "自动"),
        ]
        saved = self.cfg.get("fill_fields")
        if not isinstance(saved, list):
            saved = [k for k, _, _ in labels]

        win = tk.Toplevel(self.root)
        win.title("申请采集点 · 一条龙")
        win.geometry("460x360")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        ttk.Label(win, text="勾选要自动处理的内容，没勾的留空、你去 EgoOps 里手动补",
                  font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=16, pady=(14, 8))

        vars_ = {}
        for key, label, value in labels:
            v = tk.BooleanVar(value=(key in saved))
            vars_[key] = v
            row = ttk.Frame(win)
            row.pack(fill="x", padx=16, pady=2)
            ttk.Checkbutton(row, text=label, variable=v).pack(side="left")

        ttk.Label(win, text="只生成草稿，不会提交审核；地址取自采集数据，缺了就留空。",
                  foreground="#8a97a8", wraplength=420).pack(anchor="w", padx=16, pady=(10, 0))

        def go():
            chosen = [k for k, v in vars_.items() if v.get()]
            if not chosen:
                messagebox.showinfo(APP_NAME, "至少勾一项", parent=win)
                return
            self.cfg["fill_fields"] = chosen
            save_config(self.cfg)
            win.destroy()
            self._start_draft(site, chosen)

        btns = ttk.Frame(win)
        btns.pack(pady=16)
        ttk.Button(btns, text="开始", style="Big.TButton", command=go).pack(side="left", padx=6)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=6)

    def _start_draft(self, site, fields):
        exist = extras.draft_of(site.get("id"))
        if exist and not messagebox.askyesno(
                APP_NAME,
                "这个采集点已经建过草稿 %s。\n再建一份会在 EgoOps 里多出一条。\n\n仍然新建吗？" % exist.get("task_set_id")):
            return
        self.btn_fill.config(state="disabled")
        self._reset_progress()
        self.progress["value"] = 0
        self.lbl_task.config(text="准备中…")

        def log(msg):
            self.ui(self.lbl_task.config, text=str(msg))

        def progress(pct, text):
            self.ui(self._set_progress, pct, text)

        def work():
            try:
                # 取完整详情（含任务与文件）
                detail = self.api.site(site["id"])
                for t in detail.get("tasks") or []:
                    for f in (t.get("photos") or []) + (t.get("videos") or []):
                        f["url"] = self.cfg.get("server", "").rstrip("/") + "/files/" + f["id"]
                if "name" not in fields:
                    pass
                import importlib.util
                import sys as _sys
                base = getattr(_sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
                path = os.path.join(base, "egoops_draft.py")
                if not os.path.exists(path):
                    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "egoops_draft.py")
                spec = importlib.util.spec_from_file_location("egoops_draft", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                payload = dict(detail)
                if "address" not in fields:
                    payload["address"] = ""
                res = mod.create_draft(payload, log=log, progress=progress)
                extras.remember(site["id"], res["task_set_id"], res.get("name", ""))
                self.ui(self._draft_done, res)
            except Exception as e:
                self.ui(self._draft_failed, e)
            finally:
                self.ui(lambda: self.btn_fill.config(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    def _reset_progress(self):
        self.progress["maximum"] = 100
        self.progress["value"] = 0

    def _set_progress(self, pct, text):
        self.progress["maximum"] = 100
        self.progress["value"] = max(0, min(100, pct))
        self.lbl_task.config(text=text)

    def _draft_done(self, res):
        self.progress["maximum"] = 100
        self.progress["value"] = 100
        self.lbl_task.config(text="草稿已建：%s（%d 个任务）" % (res["task_set_id"], len(res.get("tasks") or [])))
        tasks = res.get("tasks") or []
        lines = [
            "草稿已建好（未提交审核）",
            "",
            "采集点：%s" % res["name"],
            "草稿 ID：%s" % res["task_set_id"],
            "现场地址：%s" % (res["address"] or "（空，需在页面上选省市区）"),
            "",
            "任务 %d 个：" % len(tasks),
        ]
        for t in tasks[:8]:
            lines.append("  · %s —— 照片 %d，视频 %d，SOP %d 步" % (t["name"], t["photos"], t["videos"], t["sop"]))
        if len(tasks) > 8:
            lines.append("  …")
        lines.append("")
        lines.append("去 EgoOps「申报 → 草稿」核对，没问题再点提交审核。")

        if messagebox.askyesno(APP_NAME, "\n".join(lines) + "\n\n现在打开 EgoOps 看吗？"):
            import webbrowser
            webbrowser.open("https://egoops.meituan.com/assignment")

    def _draft_failed(self, err):
        self.lbl_task.config(text="失败：%s" % err)
        messagebox.showerror(APP_NAME, "建草稿失败：\n\n%s" % err)
