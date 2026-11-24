"""批量建草稿 / 质检 / 导出表格（拆分自 app.py 1108-1309）"""

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


class BatchMixin:
    """BatchMixin：批量建草稿 / 质检 / 导出表格（拆分自 app.py 1108-1309）"""
    # ---------------------------------------------------------------- 批量 / 质检 / 导出

    def _load_draft_module(self):
        import importlib.util
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "egoops_draft.py")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "egoops_draft.py")
        spec = importlib.util.spec_from_file_location("egoops_draft", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _payload(self, site):
        detail = self.api.site(site["id"])
        server = (self.cfg.get("server") or "").rstrip("/")
        for t in detail.get("tasks") or []:
            for f in (t.get("photos") or []) + (t.get("videos") or []):
                f["url"] = server + "/files/" + f["id"]
        return detail

    def batch_draft(self):
        picked = [self.site_rows[i] for i in self.checked if i in self.site_rows]
        sites = []
        skipped_other = []
        for x in picked:
            if self._ensure_meituan(x):
                sites.append(x)
            else:
                skipped_other.append(x)
        if skipped_other and not sites:
            return
        if not sites:
            messagebox.showinfo(APP_NAME, "先在树里勾选采集点（可以多选）")
            return
        todo = [x for x in sites if not extras.draft_of(x.get("id"))]
        skipped = [x for x in sites if extras.draft_of(x.get("id"))]
        if skipped:
            messagebox.showinfo(APP_NAME, "跳过 %d 个已建过草稿的采集点" % len(skipped))
        if not todo:
            return
        if not messagebox.askyesno(APP_NAME, "给 %d 个采集点批量建草稿？\n（只建草稿，不提交审核）" % len(todo)):
            return

        self.btn_batch.config(state="disabled")
        results = []

        def work():
            mod = self._load_draft_module()
            for idx, site in enumerate(todo, 1):
                self.ui(self._set_progress, 0, "批量 %d/%d：%s" % (idx, len(todo), site.get("name")))

                def prog(pct, text, idx=idx):
                    self.ui(self._set_progress, int(100 * (idx - 1 + pct / 100) / len(todo)), text)

                try:
                    payload = self._payload(site)
                    res = mod.create_draft(payload, log=lambda m: None, progress=prog)
                    extras.remember(site["id"], res["task_set_id"], res.get("name", ""))
                    results.append((site.get("name"), "OK", res["task_set_id"], ""))
                except Exception as e:
                    results.append((site.get("name"), "失败", "", str(e)[:80]))
            self.ui(self._batch_done, results)

        threading.Thread(target=work, daemon=True).start()

    def _batch_done(self, results):
        self.btn_batch.config(state="normal")
        self._set_progress(100, "批量完成")
        ok = sum(1 for r in results if r[1] == "OK")
        lines = ["成功 %d / 失败 %d" % (ok, len(results) - ok), ""]
        for name, state, tsid, err in results:
            lines.append("%s %s %s%s" % ("✓" if state == "OK" else "✗", name,
                                         tsid, (" - " + err) if err else ""))
        messagebox.showinfo(APP_NAME, "\n".join(lines[:20]))
        self.do_refresh()

    def qc_site(self):
        site, iid = self._target_site()
        if not site:
            messagebox.showinfo(APP_NAME, "先勾选一个采集点（点最左边的方框）")
            return
        self.btn_qc.config(state="disabled")

        def work():
            try:
                detail = self.api.site(site["id"])
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "读取失败：%s" % e)
                self.ui(lambda: self.btn_qc.config(state="normal"))
                return
            files = []
            for t in detail.get("tasks") or []:
                files += (t.get("photos") or []) + (t.get("videos") or [])
            server = (self.cfg.get("server") or "").rstrip("/")
            token = getattr(self.api, "token", "")

            def dl(f):
                return extras.fetch_to_temp(server, token, f)

            try:
                issues = extras.check_site(detail, files,
                                           dl, progress=lambda p, t: self.ui(self._set_progress, p, t))
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "质检失败：%s" % e)
                issues = []
            self.ui(self._qc_done, site, files, issues)

        threading.Thread(target=work, daemon=True).start()

    def _qc_done(self, site, files, issues):
        self.btn_qc.config(state="normal")
        win = tk.Toplevel(self.root)
        win.title("质检结果 · %s" % site.get("name"))
        win.geometry("760x420")
        win.transient(self.root)

        bad = [i for i in issues if i["level"] == "error"]
        warn = [i for i in issues if i["level"] == "warn"]
        ttk.Label(win, text="共 %d 个文件：严重 %d 条，提示 %d 条" % (len(files), len(bad), len(warn)),
                  font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 6))

        cols = ("file", "kind", "reason")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for c, t, w in zip(cols, ("文件", "问题", "详情"), (240, 100, 340)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True, padx=12)
        id_map = {}
        for it in issues:
            iid = tv.insert("", "end", values=(it["file"].get("filename", ""), it["kind"], it["reason"]))
            id_map[iid] = it["file"]

        def delete_selected():
            sel = tv.selection()
            if not sel:
                return
            names = [id_map[i].get("filename") for i in sel if i in id_map]
            if not messagebox.askyesno(APP_NAME, "删除这 %d 个文件？\n\n%s" % (len(names), "\n".join(names[:8])), parent=win):
                return

            def work():
                ok = 0
                for i in sel:
                    f = id_map.get(i)
                    if not f:
                        continue
                    try:
                        self.api.delete_file(f["id"])
                        ok += 1
                    except Exception:
                        pass
                self.ui(lambda: (messagebox.showinfo(APP_NAME, "已删除 %d 个文件" % ok, parent=win), win.destroy()))
                self.ui(self.do_refresh)

            threading.Thread(target=work, daemon=True).start()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=10)
        ttk.Button(bar, text="删除选中文件", style="Danger.TButton", command=delete_selected).pack(side="left")
        ttk.Button(bar, text="关闭", command=win.destroy).pack(side="right")

    def export_table(self):
        path = filedialog.asksaveasfilename(
            title="导出采集数据表", defaultextension=".csv",
            filetypes=[("Excel 可打开", "*.csv")],
            initialfile="采集数据_%s.csv" % time.strftime("%Y%m%d"))
        if not path:
            return
        self.lbl_task.config(text="导出中…")

        def work():
            rows = []
            for it in self.sites:
                try:
                    detail = self.api.site(it["id"])
                except Exception:
                    detail = {}
                photos = videos = 0
                for t in detail.get("tasks") or []:
                    photos += len(t.get("photos") or [])
                    videos += len(t.get("videos") or [])
                d = extras.draft_of(it["id"])
                rows.append({
                    "name": it.get("name", ""), "vendor": self.vendor_of(it),
                    "invite": it.get("invite", ""), "address": it.get("address", ""),
                    "area": it.get("area"), "scene": it.get("scene_label") or it.get("scene", ""),
                    "by": it.get("created_by", ""),
                    "created": (it.get("created_at") or "").replace("T", " ")[:16],
                    "tasks": it.get("task_count", 0), "photos": photos, "videos": videos,
                    "bytes": it.get("bytes", 0),
                    "draft": d.get("task_set_id") if d else "未建",
                })
            try:
                extras.export_sites_csv(rows, path)
                self.ui(lambda: (self.lbl_task.config(text="已导出 %d 行" % len(rows)),
                                 messagebox.showinfo(APP_NAME, "已导出：\n%s\n共 %d 个采集点" % (path, len(rows)))))
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "导出失败：%s" % e)

        threading.Thread(target=work, daemon=True).start()
