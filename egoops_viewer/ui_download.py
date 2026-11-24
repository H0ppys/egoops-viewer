"""下载目录选择与批量下载（拆分自 app.py 2013-2034、2223-2413）"""

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


class DownloadMixin:
    """DownloadMixin：下载目录选择与批量下载（拆分自 app.py 2013-2034、2223-2413）"""
    # ---------------------------------------------------------------- 下载

    def ask_dir(self):
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
        base = self.cfg.get("download_dir") or os.path.join(os.path.expanduser("~"), "Desktop", "采集数据")
        d = filedialog.askdirectory(title="保存到哪里", initialdir=base if os.path.isdir(base) else None)
        if d:
            self.cfg["download_dir"] = d
            save_config(self.cfg)
        return d

    def download_selected(self):
        f = self.selected_file()
        if not f:
            messagebox.showinfo(APP_NAME, "先在右边选中一个文件")
            return
        self.download_files([f])

    def _checked_targets(self):
        """把勾选解析成 [{site, tasks:set|None}]；支持勾采集点或勾任务"""
        by_site = {}
        for iid in list(self.checked):
            iid = str(iid)
            if iid in self.site_rows:
                by_site[iid] = None                      # 整个采集点
                continue
            if ":task:" in iid:
                site_iid, _, task_id = iid.rpartition(":task:")
                if site_iid not in self.site_rows:
                    continue
                if by_site.get(site_iid, "missing") is None:
                    continue                              # 已有整站勾选
                if site_iid not in by_site:
                    by_site[site_iid] = set()
                if by_site[site_iid] is not None:
                    by_site[site_iid].add(task_id)
        out = []
        for site_iid, tasks in by_site.items():
            out.append({"site": self.site_rows[site_iid], "tasks": tasks})
        return out

    def collect_files_for_targets(self, targets):
        """按勾选目标去服务器取文件"""
        got = []
        for tg in targets:
            site = tg["site"]
            try:
                detail = self.api.site(site["id"])
            except Exception:
                continue
            want = tg["tasks"]
            for t in detail.get("tasks") or []:
                if want is not None and str(t.get("id")) not in want:
                    continue
                got += (t.get("photos") or []) + (t.get("videos") or [])
        return got

    def resolve_selected_files(self):
        """把当前勾选统一解析成文件列表；返回 (files, report)"""
        files, seen = [], set()
        report = {"sites": 0, "tasks": 0, "files": 0, "errors": [], "detail": [], "site_objs": []}

        def add(f):
            if f and f.get("id") not in seen:
                seen.add(f.get("id"))
                files.append(f)

        # 直接勾的文件
        for iid in list(self.checked):
            f = self.file_rows.get(iid)
            if f:
                add(f)
                report["files"] += 1

        # 采集点 / 任务
        site_tasks = {}      # site_iid -> set(task_id) 或 None
        for iid in list(self.checked):
            iid = str(iid)
            if iid in self.site_rows:
                site_tasks[iid] = None
                report["sites"] += 1
                continue
            if ":task:" in iid:
                site_iid, _, tid = iid.rpartition(":task:")
                if site_iid in self.site_rows:
                    if site_tasks.get(site_iid, "x") is None:
                        continue
                    site_tasks.setdefault(site_iid, set()).add(tid)
                    report["tasks"] += 1

        for site_iid, tids in site_tasks.items():
            site = self.site_rows[site_iid]
            try:
                detail = self.api.site(site["id"])
            except Exception as e:
                report["errors"].append("%s 读取失败：%s" % (site.get("name"), e))
                continue
            cnt = 0
            for t in detail.get("tasks") or []:
                if tids is not None and str(t.get("id")) not in tids:
                    continue
                for f in (t.get("photos") or []) + (t.get("videos") or []):
                    add(f)
                    cnt += 1
            report["detail"].append((site.get("name") or site.get("id"), cnt))
            report["site_objs"].append(site)
        return files, report

    def _checked_sites(self):
        return [self.site_rows[i] for i in self.checked if i in self.site_rows]

    def download_checked(self):
        files = self.checked_files()
        if files:
            self.download_files(files)
            return

        self.lbl_task.config(text="正在统计要下载的文件…")

        def work():
            try:
                files2, report = self.resolve_selected_files()
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "统计失败：%s" % e)
                return
            if not files2:
                self.ui(messagebox.showinfo, APP_NAME,
                        "选中范围内没有文件（采集点 %d / 任务 %d / 文件 %d）"
                        % (report["sites"], report["tasks"], report["files"]))
                return
            self.ui(self.download_files, files2, False)

        threading.Thread(target=work, daemon=True).start()

    def download_files(self, files, open_after=False):
        if not self.api or not files:
            return
        if self.busy:
            messagebox.showinfo(APP_NAME, "正在下载，请稍等")
            return
        target = self.ask_dir()
        if not target:
            return
        site_name = ""
        for iid in self.checked:
            if iid in self.site_rows:
                site_name = self.site_rows[iid].get("name", "")
                break
        if not site_name:
            site_name = (self.current_site or {}).get("name", "") or "采集点"
        safe = "".join(c for c in site_name if c not in '\\/:*?"<>|').strip() or "采集点"
        folder = os.path.join(target, safe)
        self.busy = True
        self.lbl_task.config(text="准备下载 %d 个文件…" % len(files))
        self.progress["maximum"] = 100
        self.progress["value"] = 0

        def work():
            ok, fail = 0, 0
            errors = []
            total = len(files)
            for i, f in enumerate(files, 1):
                name = f.get("filename") or (f["id"] + ".bin")
                dest = os.path.join(folder, name)
                if os.path.exists(dest):
                    stem, ext = os.path.splitext(name)
                    dest = os.path.join(folder, "%s_%s%s" % (stem, f["id"][:6], ext))
                self.ui(self.lbl_task.config, text="%d/%d %s" % (i, total, name))
                try:
                    self.api.download("/files/" + f["id"], dest,
                                      progress=lambda d, t: self.ui(self.set_progress, d, t))
                    ok += 1
                except Exception as e:
                    fail += 1
                    errors.append("%s：%s" % (name, e))
                    self.ui(self.lbl_task.config, text="失败：%s（%s）" % (name, e))
                self.ui(self.set_progress, i, total)
            self.ui(self.download_done, ok, fail, folder, open_after, files, errors)

        threading.Thread(target=work, daemon=True).start()

    def set_progress(self, done, total):
        if total:
            self.progress["maximum"] = 100
            self.progress["value"] = max(0, min(100, done * 100.0 / total))

    def download_done(self, ok, fail, folder, open_after, files, errors=None):
        self.busy = False
        self.lbl_task.config(text="完成：成功 %d，失败 %d" % (ok, fail))
        if open_after and ok == 1:
            try:
                path = os.path.join(folder, files[0].get("filename", ""))
                if os.path.exists(path):
                    os.startfile(path)
            except Exception:
                pass
        if fail:
            detail = "\n".join((errors or [])[:5])
            messagebox.showwarning(APP_NAME, "有 %d 个文件下载失败：\n\n%s" % (fail, detail or "（无详细信息）"))
        else:
            messagebox.showinfo(APP_NAME, "下载完成\n\n保存位置：\n%s" % folder)

    def open_download_dir(self):
        d = self.cfg.get("download_dir")
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showinfo(APP_NAME, "还没有下载过文件")
