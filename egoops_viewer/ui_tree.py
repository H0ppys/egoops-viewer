"""采集点/文件树：搜索筛选、勾选、详情填充、照片预览（拆分自 app.py 1629-2012）"""

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


class TreeMixin:
    """TreeMixin：采集点/文件树：搜索筛选、勾选、详情填充、照片预览（拆分自 app.py 1629-2012）"""
    # ---------------------------------------------------------------- 树形列表

    def _on_search_typing(self, event=None):
        # 输入停顿 400ms 再过滤，避免每敲一下就刷
        if getattr(self, "_search_job", None):
            try:
                self.root.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.root.after(400, self.do_refresh)

    def _apply_filters(self, items):
        import datetime
        kw = ""
        try:
            kw = (self.ent_search.get() or "").strip().lower()
        except Exception:
            pass
        rng = "全部"
        try:
            rng = self.cmb_range.get()
        except Exception:
            pass

        limit = None
        now = datetime.datetime.now()
        if rng == "今天":
            limit = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif rng == "近 7 天":
            limit = now - datetime.timedelta(days=7)
        elif rng == "近 30 天":
            limit = now - datetime.timedelta(days=30)

        out = []
        for it in items:
            if kw:
                blob = " ".join(str(it.get(k) or "") for k in
                                ("name", "address", "created_by", "invite", "scene_label")).lower()
                if kw not in blob:
                    continue
            if limit:
                ts = (it.get("created_at") or "")[:19].replace("T", " ")
                try:
                    dt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    if dt < limit:
                        continue
                except Exception:
                    pass
            out.append(it)
        return out

    def fill_sites(self, items):
        items = self._apply_filters(items)
        self.sites = items
        self.site_rows.clear()
        self.file_rows.clear()
        self.checked = set()
        self.update_check_label()
        for row in self.tree.get_children():
            self.tree.delete(row)
        for it in items:
            iid = "site:" + it["id"]
            self.site_rows[iid] = it
            # 列顺序：sel / name / address / vendor / time / draft
            self.tree.insert("", "end", iid=iid, text="", values=(
                "☐",
                it.get("name", ""),
                it.get("address") or "（未填地址）",
                self.vendor_of(it),
                (it.get("created_at") or "").replace("T", " ")[:16] + " · %d件" % it.get("file_count", 0),
                self.draft_text(it),
            ))
            self.tree.insert(iid, "end", iid=iid + ":loading", text="", values=("", "加载中…", "", "", "", ""))
        if not items:
            self.tree.insert("", "end", iid="empty:hint", text="", values=(
                "", "还没有采集点", "让采集员用手机 App 拍完上传，这里会自动出现", "", "", ""))
        self.set_status("已连接 · 采集点 %d 个 · %s · %s" % (len(items), APP_VER, time.strftime("%H:%M:%S")), "#1f7a3d")
        self.update_guide()
        self.lbl_site.config(text="采集点（点开左侧三角展开任务和文件）")

    def on_tree_select(self, event=None):
        try:
            self.update_guide()
        except Exception:
            pass
        iid = self.tree.focus()
        if iid in self.site_rows:
            it = self.site_rows[iid]
            self.lbl_site.config(text="%s · %s · %s 个文件 · %s · 采集员 %s" % (
                it.get("name", ""),
                it.get("address") or "（未填地址）",
                it.get("file_count", 0),
                human_size(it.get("bytes", 0)),
                it.get("created_by", "")))
        elif iid in self.file_rows:
            f = self.file_rows[iid]
            self.lbl_site.config(text="%s · %s · %s" % (
                f.get("filename", ""), human_size(f.get("size", 0)), f.get("kind", "")))
            if f.get("kind") == "photo":
                self.request_preview(f)
            else:
                self.preview.config(image="", text="视频：双击用系统播放器打开")
        else:
            self.lbl_site.config(text="采集点（点开左侧三角展开任务和文件）")

    def request_preview(self, f):
        """后台线程下载照片，绝不阻塞界面"""
        fid = f.get("id")
        if not fid:
            return
        if fid in self._preview_cache:
            self.show_photo(self._preview_cache[fid])
            return
        if fid in self._preview_pending:
            return
        self._preview_pending.add(fid)
        self.preview.config(image="", text="正在加载照片…")

        server = (self.cfg.get("server") or "").rstrip("/")
        token = getattr(self.api, "token", "")

        def work():
            try:
                import urllib.request
                req = urllib.request.Request(server + "/files/" + fid)
                if token:
                    req.add_header("Authorization", "Bearer " + token)
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                tmp = os.path.join(os.environ.get("TEMP") or ".", "egoops_preview_" + fid + ".jpg")
                with open(tmp, "wb") as fh:
                    fh.write(data)
                self.ui(self._preview_ready, fid, tmp)
            except Exception as e:
                self.ui(self._preview_failed, fid, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _preview_ready(self, fid, path):
        self._preview_pending.discard(fid)
        self._preview_cache[fid] = path
        # 只在当前选中的仍是这张时才显示
        cur = self.tree.focus()
        f = self.file_rows.get(cur)
        if f and f.get("id") == fid:
            self.show_photo(path)

    def _preview_failed(self, fid, err):
        self._preview_pending.discard(fid)
        cur = self.tree.focus()
        f = self.file_rows.get(cur)
        if f and f.get("id") == fid:
            self.preview.config(image="", text="预览失败：%s" % err)

    def show_photo(self, path):
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((560, 320))
            self._img = ImageTk.PhotoImage(img)
            self.preview.config(image=self._img, text="")
            img.close()
        except Exception as e:
            self.preview.config(image="", text="预览失败：%s" % e)

    def on_tree_open(self, event):
        iid = self.tree.focus()
        # 点三角展开时焦点不一定落在这一行，兜底找「已展开但没加载过」的采集点
        if iid not in self.site_rows:
            for sid in self.tree.get_children():
                if sid in self.site_rows and self.tree.item(sid, "open") and sid not in self.loaded_sites:
                    iid = sid
                    break
        if iid not in self.site_rows or iid in self.loaded_sites:
            return
        self.loaded_sites.add(iid)
        site = self.site_rows.get(iid)
        if not site:
            return

        def work():
            try:
                detail = self.api.site(site["id"])
                self.ui(self.fill_detail, iid, detail)
            except Exception as e:
                self.ui(self._load_failed, iid, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _load_failed(self, iid, err):
        self.loaded_sites.discard(iid)
        try:
            for ch in self.tree.get_children(iid):
                self.tree.delete(ch)
            self.tree.insert(iid, "end", text="", values=("", "加载失败，点三角收起再展开重试：%s" % err, "", "", "", "", ""))
        except Exception:
            pass
        self.set_status("读取文件失败：%s" % err, "#b3261e")

    def fill_detail(self, iid, detail):
        for ch in self.tree.get_children(iid):
            self.tree.delete(ch)
        tasks = detail.get("tasks") or []
        if not tasks:
            self.tree.insert(iid, "end", text="", values=("", "（没有任务）", "", "", "", ""))
            return
        for t in tasks:
            tid = "%s:task:%s" % (iid, t.get("id") or t.get("name"))
            area = (t.get("area") or "").strip()
            label = (area + "：" if area else "") + (t.get("name") or "")
            photos = t.get("photos") or []
            videos = t.get("videos") or []
            self.tree.insert(iid, "end", iid=tid, text="", values=(
                "☐", label, "", "区域任务", "照片 %d · 视频 %d" % (len(photos), len(videos)), "", "", ""))
            for f in photos + videos:
                fid = "file:" + f["id"]
                self.file_rows[fid] = f
                self.tree.insert(tid, "end", iid=fid, text="", values=(
                    "☐",
                    f.get("filename", ""),
                    "",
                    "%s · %s" % (label, "照片" if f.get("kind") == "photo" else "视频"),
                    "照片" if f.get("kind") == "photo" else "视频",
                    (f.get("created_at") or "").replace("T", " ")[:16],
                    human_size(f.get("size", 0)),
                    "",
                ))
        # 父级已勾选的话，把新加载的子节点也勾上
        if self.tree.set(iid, "sel") == "☑":
            for child in self.tree.get_children(iid):
                self._set_checked(child, True, cascade=True)

        self.tree.item(iid, open=True)

    def on_tree_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None

        try:
            self.tree.focus(iid)
            self.tree.selection_set(iid)
        except Exception:
            pass
        want = self.tree.set(iid, "sel") != "☑"     # 点一下要变成的状态
        if iid in self.site_rows and want and iid not in self.loaded_sites:
            # 还没展开过：先加载，加载完会自动按父级状态补勾
            try:
                self.tree.item(iid, open=True)
                self.on_tree_open(None)
            except Exception:
                pass
        self._set_checked(iid, want, cascade=True)   # 勾采集点 = 连带下面全部
        self._sync_ancestors(iid)
        self.update_check_label()
        return "break"

    def _set_checked(self, iid, checked, cascade=False):
        mark = "☑" if checked else "☐"
        try:
            self.tree.set(iid, "sel", mark)
        except Exception:
            return
        if checked:
            self.checked.add(iid)
        else:
            self.checked.discard(iid)
        if cascade:
            for child in self.tree.get_children(iid):
                self._set_checked(child, checked, cascade=True)

    def _sync_ancestors(self, iid):
        """下级全勾 → 上级自动勾；有一个没勾 → 上级取消"""
        parent = self.tree.parent(iid)
        while parent:
            kids = self.tree.get_children(parent)
            if kids:
                all_on = all(self.tree.set(k, "sel") == "☑" for k in kids)
                self._set_checked(parent, all_on, cascade=False)
            parent = self.tree.parent(parent)

    def _is_checked(self, iid):
        try:
            return self.tree.set(iid, "sel") == "☑"
        except Exception:
            return False

    def on_tree_double(self, event):
        iid = self.tree.identify_row(event.y)
        if iid in self.site_rows:
            opened = self.tree.item(iid, "open")
            self.tree.item(iid, open=not opened)
            if not opened:
                self.on_tree_open(None)
            return
        if not iid or not iid.startswith("file:"):
            return
        f = self.file_rows.get(iid)
        if f:
            self.download_files([f], open_after=True)

    def update_check_label(self):
        n = len(self.checked)
        text = "下载勾选（%d）" % n if n else "下载勾选"
        try:
            self.btn_dl_checked.config(text=text)
            self.btn_dl_sites.config(text=text)
        except Exception:
            pass

    def checked_files(self):
        """勾选的文件 + 勾选采集点下的所有文件（占位行已删除时也不会崩）"""
        out, seen = [], set()

        def add(f):
            if f and f.get("id") not in seen:
                seen.add(f.get("id"))
                out.append(f)

        for iid in list(self.checked):
            f = self.file_rows.get(iid)
            if f:
                add(f)

        for iid in list(self.checked):
            if not str(iid).startswith("site:") or str(iid).endswith(":loading"):
                continue
            try:
                tasks = self.tree.get_children(iid)
            except Exception:
                continue
            for task_iid in tasks:
                if str(task_iid).endswith(":loading"):
                    continue
                try:
                    files = self.tree.get_children(task_iid)
                except Exception:
                    continue
                for f_iid in files:
                    add(self.file_rows.get(f_iid))
        return out

    def toggle_all_checks(self):
        rows = self.tree.get_children()
        if not rows:
            return
        all_checked = all(self._is_checked(i) for i in rows)
        for i in rows:
            self._set_checked(i, not all_checked, cascade=True)
        self.update_check_label()

    def toggle_all_sites(self):
        self.toggle_all_checks()

    def download_checked_sites(self):
        self.download_checked()

    def download_site(self):
        site, iid = self._target_site()
        if not site:
            messagebox.showinfo(APP_NAME, "先勾选一个采集点（点最左边的方框）")
            return
        self.lbl_task.config(text="读取中…")

        def work():
            try:
                detail = self.api.site(site["id"])
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "读取失败：%s" % e)
                return
            files = []
            for t in detail.get("tasks") or []:
                files += (t.get("photos") or []) + (t.get("videos") or [])
            self.ui(self.download_files, files, False)

        threading.Thread(target=work, daemon=True).start()

    def update_site_check_label(self):
        pass
