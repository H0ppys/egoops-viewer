"""草稿预览：HTML 核对稿与纯文本草稿（拆分自 app.py 827-943）"""

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


class DraftMixin:
    """DraftMixin：草稿预览：HTML 核对稿与纯文本草稿（拆分自 app.py 827-943）"""
    # ---------------------------------------------------------------- 草稿预览

    def draft_html(self, site):
        import html as _html
        esc = _html.escape
        tasks = site.get("tasks") or []
        files = []
        rows = []
        for t in tasks:
            area = (t.get("area") or "").strip() or "—"
            photos = t.get("photos") or []
            videos = t.get("videos") or []
            rows.append((area, t.get("name") or "", len(photos), len(videos)))
            label = ((t.get("area") + "：") if (t.get("area") or "").strip() else "") + (t.get("name") or "")
            for f in photos + videos:
                files.append((label, "照片" if f.get("kind") == "photo" else "视频",
                              f.get("filename", ""), human_size(f.get("size", 0))))
        area_txt = (str(site.get("area")) + " ㎡") if site.get("area") else "（未填）"
        body_rows = "".join(
            "<tr><td style='color:#6b7a90;width:130px'>%s</td><td>%s</td></tr>" % (k, v) for k, v in [
                ("采集点名称", "<b>%s</b>" % esc(site.get("name") or "")),
                ("采集场景分类", esc(site.get("scene_label") or site.get("scene") or "（未选）")),
                ("现场地址", esc(site.get("address") or "（未填）")
                 + ("" if not site.get("address") else
                    " <span style='color:#6b7a90;font-size:12px'>（省 %s / 市 %s / 区 %s / 街道 %s）</span>" % (
                        esc(parse_address(site.get("address")).get("province") or "?"),
                        esc(parse_address(site.get("address")).get("city") or "?"),
                        esc(parse_address(site.get("address")).get("district") or "?"),
                        esc(parse_address(site.get("address")).get("street") or "?")))),
                ("场地面积", esc(area_txt)),
                ("采集点描述", esc(site.get("note") or "（未填）")),
            ])
        task_rows = "".join(
            "<tr><td>%s</td><td>%s</td><td>%d</td><td>%d</td></tr>" % (esc(a), esc(n), p_, v_)
            for a, n, p_, v_ in rows)
        file_rows = "".join(
            "<tr><td>%s</td><td>%s</td><td style='color:#6b7a90'>%s</td><td>%s</td></tr>" % (esc(a), esc(k), esc(fn), esc(sz))
            for a, k, fn, sz in files)
        return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>申请采集点草稿</title>
<style>body{margin:0;padding:28px;background:#f2f5fa;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#17202e}
.card{max-width:860px;margin:0 auto;background:#fff;border-radius:16px;padding:26px 30px}
h1{font-size:21px;margin:0 0 4px}.sub{color:#6b7a90;font-size:13px;margin-bottom:18px}
table{width:100%%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid #eef2f7}
h2{font-size:15px;margin:22px 0 8px}</style></head><body><div class="card">
<h1>申请采集点 · 草稿</h1><div class="sub">采集员 %s · 共 %d 个素材</div>
<table>%s</table><h2>任务清单（%d 个）</h2>
<table><tr><th style="width:110px">区域</th><th>任务</th><th style="width:70px">照片</th><th style="width:70px">视频</th></tr>%s</table>
<h2>素材清单（%d 个文件）</h2>
<table><tr><th style="width:180px">任务</th><th style="width:60px">类型</th><th>文件名</th><th style="width:80px">大小</th></tr>%s</table>
<p style="color:#6b7a90;margin-top:18px">提交前核对稿，尚未提交到 EgoOps。</p>
</div></body></html>""" % (esc(site.get("created_by") or ""), len(files), body_rows, len(tasks), task_rows, len(files), file_rows)

    def show_draft(self):
        site = self.current_site
        if not site:
            messagebox.showinfo(APP_NAME, "先在左边选一个采集点")
            return
        doc = self.draft_html(site)
        win = tk.Toplevel(self.root)
        win.title("申请采集点草稿 - %s" % (site.get("name") or ""))
        win.geometry("820x680")
        win.transient(self.root)
        txt = tk.Text(win, wrap="word", font=("Microsoft YaHei UI", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        plain = self.draft_plain(site)
        txt.insert("1.0", plain)
        txt.config(state="disabled")

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=(0, 10))

        def save():
            name = (site.get("name") or "采集点").replace("/", "_").replace("\\", "_")
            path = filedialog.asksaveasfilename(defaultextension=".html", initialfile="草稿-%s.html" % name,
                                                filetypes=[("网页", "*.html")])
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(doc)
            messagebox.showinfo(APP_NAME, "已保存：\n%s" % path)

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(plain)
            messagebox.showinfo(APP_NAME, "草稿内容已复制")

        ttk.Button(bar, text="保存为网页", command=save).pack(side="left")
        ttk.Button(bar, text="复制文本", command=copy).pack(side="left", padx=8)
        ttk.Button(bar, text="关闭", command=win.destroy).pack(side="left")

    def draft_plain(self, site):
        lines = ["申请采集点 · 草稿", "=" * 30,
                 "采集点名称：%s" % (site.get("name") or ""),
                 "采集场景分类：%s" % (site.get("scene_label") or site.get("scene") or "（未选）"),
                 "现场地址：%s" % (site.get("address") or "（未填）"),
                 "  → 拆解：省=%s 市=%s 区=%s 街道=%s" % (
                     (parse_address(site.get("address") or "").get("province") or "?"),
                     (parse_address(site.get("address") or "").get("city") or "?"),
                     (parse_address(site.get("address") or "").get("district") or "?"),
                     (parse_address(site.get("address") or "").get("street") or "?")),
                 "场地面积：%s" % ((str(site.get("area")) + " ㎡") if site.get("area") else "（未填）"),
                 "采集点描述：%s" % (site.get("note") or "（未填）"),
                 "采集员：%s" % (site.get("created_by") or ""), "", "任务清单："]
        for t in site.get("tasks") or []:
            area = (t.get("area") or "").strip() or "—"
            lines.append("  · %s / %s —— 照片 %d，视频 %d"
                         % (area, t.get("name") or "",
                            len(t.get("photos") or []), len(t.get("videos") or [])))
        lines += ["", "素材清单："]
        for t in site.get("tasks") or []:
            label = ((t.get("area") + "：") if (t.get("area") or "").strip() else "") + (t.get("name") or "")
            for f in (t.get("photos") or []) + (t.get("videos") or []):
                lines.append("  · %s | %s | %s | %s" % (label,
                            "照片" if f.get("kind") == "photo" else "视频",
                            f.get("filename", ""), human_size(f.get("size", 0))))
        return "\n".join(lines)
