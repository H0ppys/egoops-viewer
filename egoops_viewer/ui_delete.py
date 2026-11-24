"""永久删除采集点与文件（拆分自 app.py 2035-2222）"""

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


class DeleteMixin:
    """DeleteMixin：永久删除采集点与文件（拆分自 app.py 2035-2222）"""
    def _delete_sites(self, sites):
        total = len(sites)
        self.lbl_task.config(text="正在删除 0/%d…" % total)

        def work():
            ok = fail = 0
            errs = []
            for i, site in enumerate(sites, 1):
                self.ui(self.lbl_task.config, text="正在删除 %d/%d：%s" % (i, total, site.get("name", "")))
                try:
                    self.api.delete_site(site["id"])
                    ok += 1
                except Exception as e:
                    fail += 1
                    errs.append("%s：%s" % (site.get("name", ""), e))
            self.ui(self._after_delete_sites, ok, fail, errs)

        threading.Thread(target=work, daemon=True).start()

    def _after_delete_sites(self, ok, fail, errs=None):
        msg = "已删除 %d 个采集点" % ok
        if fail:
            msg += "，失败 %d 个" % fail
        self.lbl_task.config(text=msg)
        self.set_status(msg, "#1f7a3d" if not fail else "#b3261e")
        if errs:
            messagebox.showwarning(APP_NAME, msg + "\n\n" + "\n".join(errs[:8]))
        self.do_refresh()

    def cleanup_empty_sites(self):
        self.lbl_task.config(text="正在查找空采集点…")

        def work():
            try:
                items = self.api.sites()
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "读取失败：%s" % e)
                return
            empty = [x for x in items if not x.get("file_count")]
            if not empty:
                self.ui(messagebox.showinfo, APP_NAME, "没有空采集点")
                return
            names = "\n".join("· %s（%s）" % (x.get("name"), x.get("created_at", "")[:10]) for x in empty[:15])
            self.ui(self._confirm_cleanup_empty, empty, names)

        threading.Thread(target=work, daemon=True).start()

    def _confirm_cleanup_empty(self, empty, names):
        if messagebox.askyesno(APP_NAME,
                               "找到 %d 个没有任何文件的采集点：\n\n%s\n\n全部删除吗？不可恢复。"
                               % (len(empty), names)):
            self._delete_sites(empty)

    def delete_checked_sites(self):
        sites = [self.site_rows[i] for i in self.checked if i in self.site_rows]
        if not sites:
            messagebox.showinfo(APP_NAME, "先在树里勾选采集点（点最左边的方框）")
            return
        names = [x.get("name", "") for x in sites]
        preview = "\n".join("· " + n for n in names[:12])
        if not messagebox.askyesno("确认删除",
                                   "将永久删除 %d 个采集点及其全部照片视频：\n\n%s\n\n删除后无法恢复，确定吗？"
                                   % (len(names), preview), icon="warning"):
            return

        self._delete_sites(sites)

    def after_delete_sites(self, ok, fail):
        self.checked.clear()
        self.update_check_label()
        self.lbl_task.config(text="已删除 %d 个，失败 %d 个" % (ok, fail))
        messagebox.showinfo(APP_NAME, "删除完成：成功 %d 个，失败 %d 个" % (ok, fail))
        self.do_refresh()

    def delete_checked_files(self):
        self.lbl_task.config(text="正在统计要删除的文件…")

        def work():
            try:
                files, report = self.resolve_selected_files()
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "统计失败：%s" % e)
                return
            self.ui(self._delete_preview, files, report)

        threading.Thread(target=work, daemon=True).start()

    def _delete_preview(self, files, report):
        if report["errors"]:
            messagebox.showwarning(APP_NAME, "读取时有问题：\n" + "\n".join(report["errors"][:5]))

        if not files:
            lines = ["  %s：%d 个文件" % (n, c) for n, c in (report.get("detail") or [])]
            empty_sites = [tg for tg in report.get("site_objs") or []]
            msg = ("这些采集点里没有文件（可能素材之前已经被删掉了）。\n\n"
                   + ("\n".join(lines) if lines else "（没有勾选到采集点/任务/文件）"))
            if empty_sites:
                names = "、".join(x.get("name") or "" for x in empty_sites[:6])
                if messagebox.askyesno(
                        APP_NAME,
                        msg + "\n\n要把这些「空采集点」直接删掉吗？\n（%s）\n\n"
                              "会同时删除它们名下的任务记录，不可恢复。" % names):
                    self._delete_sites(empty_sites)
                    return
            else:
                messagebox.showinfo(APP_NAME, msg)
            self.lbl_task.config(text="没有可删除的文件")
            return

        win = tk.Toplevel(self.root)
        win.title("确认删除 %d 个文件" % len(files))
        win.geometry("560x460")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="以下文件将被永久删除，确认无误再点删除：",
                  padding=12).pack(anchor="w")

        box = ttk.Frame(win, padding=(12, 0, 12, 8))
        box.pack(fill="both", expand=True)
        tv = ttk.Treeview(box, columns=("name", "kind", "size"), show="headings", height=12)
        for c, t, w in (("name", "文件名", 300), ("kind", "类型", 70), ("size", "大小", 90)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="w")
        for f in files[:300]:
            tv.insert("", "end", values=(f.get("filename", ""),
                                         "照片" if f.get("kind") == "photo" else "视频",
                                         human_size(f.get("size", 0))))
        sb = ttk.Scrollbar(box, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        bar = ttk.Frame(win, padding=12)
        bar.pack(fill="x")

        def do_delete():
            win.destroy()
            self.lbl_task.config(text="正在删除…")

            def run():
                ok = fail = 0
                for f in files:
                    try:
                        self.api.delete_file(f["id"])
                        ok += 1
                    except Exception:
                        fail += 1
                self.ui(self.after_delete_files, ok, fail)

            threading.Thread(target=run, daemon=True).start()

        ttk.Button(bar, text="取消", command=win.destroy).pack(side="right", padx=6)
        ttk.Button(bar, text="确认删除 %d 个" % len(files), style="Accent.TButton",
                   command=do_delete).pack(side="right")

    def _confirm_delete_files(self, files):
        if not files:
            self.lbl_task.config(text="勾选的采集点里没有文件")
            messagebox.showinfo(APP_NAME, "勾选的采集点里没有文件")
            return

        names = [f.get("filename", "") for f in files]
        preview = "\n".join("· " + n for n in names[:12])
        if not messagebox.askyesno("确认删除",
                                   "将永久删除 %d 个文件：\n\n%s\n\n删除后无法恢复，确定吗？"
                                   % (len(names), preview), icon="warning"):
            return

        def work():
            ok = fail = 0
            for f in files:
                try:
                    self.api.delete_file(f["id"])
                    ok += 1
                except Exception:
                    fail += 1
            self.ui(self.after_delete_files, ok, fail)

        threading.Thread(target=work, daemon=True).start()

    def after_delete_files(self, ok, fail):
        self.checked.clear()
        self.update_check_label()
        self.lbl_task.config(text="已删除 %d 个文件，失败 %d 个" % (ok, fail))
        messagebox.showinfo(APP_NAME, "删除完成：成功 %d 个，失败 %d 个" % (ok, fail))
        self.do_refresh()
