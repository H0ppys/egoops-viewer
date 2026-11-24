"""采集数据查看器 v2 —— 主从布局（左：采集点列表；右：任务 + 素材缩略图 + 预览）

设计目标（给非技术用户）：
  1. 左边只放「采集点」，一行一个门店，点一下就选中
  2. 右边上半是「这个采集点有哪些任务」，点任务看素材
  3. 右边下半是素材缩略图墙，点图勾选，一眼看清拍了几张
  4. 操作按钮跟着选择走：选了采集点就能下载/质检/建草稿
  5. 底部状态栏固定显示：连接状态、当前进度、EgoOps 登录态
"""

# 拆分说明：本文件逐字搬运自 viewer/app2.py（v2 主从布局版），
# 仅把包外绝对 import 改成包内相对 import；方法体未改动。

import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "采集数据查看器"
APP_VER = "v2.0"
DEFAULT_SERVER = "https://123.207.6.210/relay"

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from .api_client import Api, ApiError          # noqa: E402
from . import extras                          # noqa: E402
from . import tls                             # noqa: E402

try:
    from . import egoops_auth                 # noqa: E402
except Exception:
    egoops_auth = None


def load_config():
    import json
    p = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "egoops-viewer", "config.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def human_size(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, u)
        n /= 1024
    return "%.1f TB" % n


class App:
    def __init__(self, root, autoconnect=True):
        self.root = root
        self.cfg = load_config()
        self.api = None
        self.sites = []
        self.site = None          # 当前采集点
        self.task = None          # 当前任务
        self.files = []           # 当前任务的素材
        self.selected = set()     # 勾选的 file id
        self.thumbs = {}
        self.events = queue.Queue()
        self.busy = False
        self.login_ok = None

        root.title("%s %s" % (APP_NAME, APP_VER))
        root.geometry("1560x900")
        root.minsize(1180, 700)
        root.configure(bg="#F1F5F9")

        self.var_server = tk.StringVar(value=self.cfg.get("server") or DEFAULT_SERVER)
        self.var_name = tk.StringVar(value=self.cfg.get("name") or "查看者")
        self.var_search = tk.StringVar()

        self._theme()
        self._build()
        self._poll()
        if autoconnect:
            self.root.after(200, self.connect)
        self.root.after(900, self.check_login)

    # ------------------------------------------------------------ 主题

    def _theme(self):
        try:
            import sv_ttk
            sv_ttk.set_theme("light")
        except Exception:
            pass
        s = ttk.Style()
        s.configure("Title.TLabel", font=("Microsoft YaHei UI", 17, "bold"))
        s.configure("Sub.TLabel", font=("Microsoft YaHei UI", 9), foreground="#64748B")
        s.configure("Section.TLabel", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Hint.TLabel", font=("Microsoft YaHei UI", 9), foreground="#94A3B8")
        s.configure("Big.Treeview", rowheight=40, font=("Microsoft YaHei UI", 10))
        s.configure("Big.Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    # ------------------------------------------------------------ 布局

    def _build(self):
        # 顶部
        head = ttk.Frame(self.root, padding=(18, 14, 18, 6))
        head.pack(fill="x")
        ttk.Label(head, text="采集数据查看器", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="美团采集 · 质检 · 建草稿", style="Sub.TLabel").pack(side="left", padx=(12, 0), pady=(6, 0))

        self.lbl_login = ttk.Label(head, text="EgoOps 检查中…", style="Sub.TLabel")
        self.lbl_login.pack(side="right")

        # 工具行
        bar = ttk.Frame(self.root, padding=(18, 0, 18, 8))
        bar.pack(fill="x")
        ttk.Entry(bar, textvariable=self.var_server, width=30).pack(side="left")
        ttk.Button(bar, text="连接", style="Accent.TButton", command=self.connect).pack(side="left")
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="left", padx=(6, 16))
        ttk.Label(bar, text="搜索", style="Sub.TLabel").pack(side="left")
        ent = ttk.Entry(bar, textvariable=self.var_search, width=18)
        ent.pack(side="left", padx=(4, 0))
        self.var_search.trace_add("write", lambda *a: self.fill_sites())

        # 底部操作条
        foot = ttk.Frame(self.root, padding=(18, 6, 18, 12))
        foot.pack(side="bottom", fill="x")
        self.btn_dl_sel = ttk.Button(foot, text="下载选中", command=self.download_selected)
        self.btn_dl_sel.pack(side="left")
        self.btn_del_sel = ttk.Button(foot, text="删除选中", command=self.delete_selected)
        self.btn_del_sel.pack(side="left", padx=6)
        ttk.Button(foot, text="全选", command=self.select_all).pack(side="left", padx=(12, 4))
        ttk.Button(foot, text="取消选择", command=self.select_none).pack(side="left")

        self.progress = ttk.Progressbar(foot, mode="determinate", length=240)
        self.progress.pack(side="right")
        self.lbl_status = ttk.Label(foot, text="未连接", style="Sub.TLabel")
        self.lbl_status.pack(side="right", padx=10)

        # 主体：左右分栏
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 6))

        # ---- 左：采集点 ----
        left = ttk.Frame(body)
        body.add(left, weight=1)

        lh = ttk.Frame(left)
        lh.pack(fill="x", pady=(0, 4))
        ttk.Label(lh, text="采集点", style="Section.TLabel").pack(side="left")
        self.lbl_count = ttk.Label(lh, text="0 个", style="Hint.TLabel")
        self.lbl_count.pack(side="left", padx=6)

        wrap = ttk.Frame(left)
        wrap.pack(fill="both", expand=True)
        cols = ("name", "addr", "files", "ego")
        self.tv_sites = ttk.Treeview(wrap, columns=cols, show="headings", style="Big.Treeview", selectmode="browse")
        for c, t, w in (("name", "门店", 150), ("addr", "地址", 220), ("files", "文件", 60), ("ego", "EgoOps", 90)):
            self.tv_sites.heading(c, text=t)
            self.tv_sites.column(c, width=w, anchor="w" if c in ("name", "addr") else "center",
                                 stretch=(c in ("name", "addr")))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv_sites.yview)
        self.tv_sites.configure(yscrollcommand=sb.set)
        self.tv_sites.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv_sites.bind("<<TreeviewSelect>>", lambda e: self.on_site_select())

        # ---- 右：详情 ----
        right = ttk.Frame(body)
        body.add(right, weight=2)

        # 采集点标题 + 主操作
        rh = ttk.Frame(right)
        rh.pack(fill="x", pady=(0, 6))
        self.lbl_site_name = ttk.Label(rh, text="（未选择采集点）", style="Section.TLabel")
        self.lbl_site_name.pack(side="left")
        self.lbl_site_info = ttk.Label(rh, text="", style="Hint.TLabel")
        self.lbl_site_info.pack(side="left", padx=10)

        self.btn_draft = ttk.Button(rh, text="建 EgoOps 草稿", style="Accent.TButton", command=self.make_draft)
        self.btn_draft.pack(side="right")
        ttk.Button(rh, text="质检", command=self.qc_site).pack(side="right", padx=6)
        ttk.Button(rh, text="下载全部", command=self.download_site).pack(side="right", padx=(0, 6))

        # 任务选择
        tf = ttk.Frame(right)
        tf.pack(fill="x", pady=(0, 6))
        ttk.Label(tf, text="任务", style="Sub.TLabel").pack(side="left")
        self.cmb_task = ttk.Combobox(tf, state="readonly", width=42)
        self.cmb_task.pack(side="left", padx=6)
        self.cmb_task.bind("<<ComboboxSelected>>", lambda e: self.on_task_select())
        self.lbl_task_count = ttk.Label(tf, text="", style="Hint.TLabel")
        self.lbl_task_count.pack(side="left", padx=8)

        # 素材清单
        wall = ttk.Frame(right)
        wall.pack(fill="both", expand=True)
        cols = ("pick", "name", "kind", "size", "time")
        self.tv_files = ttk.Treeview(wall, columns=cols, show="headings",
                                     style="Big.Treeview", selectmode="browse")
        for c, t, w, anchor in (("pick", "选", 44, "center"), ("name", "文件名", 300, "w"),
                                ("kind", "类型", 70, "center"), ("size", "大小", 90, "center"),
                                ("time", "时间", 140, "center")):
            self.tv_files.heading(c, text=t)
            self.tv_files.column(c, width=w, anchor=anchor, stretch=(c == "name"))
        vs = ttk.Scrollbar(wall, orient="vertical", command=self.tv_files.yview)
        self.tv_files.configure(yscrollcommand=vs.set)
        self.tv_files.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tv_files.bind("<Button-1>", self._on_file_click)
        self.tv_files.bind("<space>", lambda e: self._toggle_focus_file())

        # 菜单
        mb = tk.Menu(self.root)
        m1 = tk.Menu(mb, tearoff=0)
        m1.add_command(label="刷新", command=self.refresh)
        m1.add_command(label="导出 CSV…", command=self.export_csv)
        m1.add_separator()
        m1.add_command(label="退出", command=self.root.destroy)
        mb.add_cascade(label="文件", menu=m1)

        m2 = tk.Menu(mb, tearoff=0)
        m2.add_command(label="删除当前采集点", command=self.delete_site)
        m2.add_command(label="清理空采集点（0 文件）", command=self.cleanup_empty)
        mb.add_cascade(label="采集点", menu=m2)

        m3 = tk.Menu(mb, tearoff=0)
        m3.add_command(label="建草稿", command=self.make_draft)
        m3.add_command(label="打开 EgoOps 网页", command=self.open_egoops)
        m3.add_command(label="检查登录态", command=self.check_login)
        m3.add_command(label="刷新登录态（扫码）", command=self.relogin)
        mb.add_cascade(label="美团", menu=m3)

        m4 = tk.Menu(mb, tearoff=0)
        m4.add_command(label="服务器空间 / 清理…", command=self.storage_dialog)
        mb.add_cascade(label="设置", menu=m4)
        self.root.config(menu=mb)

    # ------------------------------------------------------------ 线程工具

    def ui(self, fn, *a, **k):
        self.events.put((fn, a, k))

    def _poll(self):
        try:
            while True:
                fn, a, k = self.events.get_nowait()
                try:
                    fn(*a, **k)
                except Exception as e:
                    print("ui error:", e)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    # ------------------------------------------------------------ 连接

    def set_status(self, text, color="#64748B"):
        self.lbl_status.config(text=text, foreground=color)

    def connect(self):
        self.api = Api(self.var_server.get().strip())
        self.set_status("连接中…")
        name = self.cfg.get("name") or "查看者"

        def work():
            try:
                self.api.login(name)
                self.ui(self.set_status, "已连接", "#15803D")
                self.ui(self.refresh)
            except Exception as e:
                self.ui(self.set_status, "连接失败：%s" % e, "#B91C1C")

        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        if not self.api:
            return
        self.set_status("读取列表中…")

        def work():
            try:
                items = self.api.sites()
                self.ui(self.fill_sites, items)
                self.ui(self.set_status, "共 %d 个采集点" % len(items), "#15803D")
            except Exception as e:
                self.ui(self.set_status, "读取失败：%s" % e, "#B91C1C")

        threading.Thread(target=work, daemon=True).start()

    def fill_sites(self, items=None):
        if items is not None:
            self.sites = items
        kw = (self.var_search.get() or "").strip().lower()
        self.tv_sites.delete(*self.tv_sites.get_children())
        shown = 0
        for s in self.sites:
            blob = ((s.get("name") or "") + (s.get("address") or "")).lower()
            if kw and kw not in blob:
                continue
            shown += 1
            self.tv_sites.insert("", "end", iid=s["id"], values=(
                s.get("name", ""),
                s.get("address", ""),
                s.get("file_count", 0),
                self.draft_text(s),
            ))
        self.lbl_count.config(text="%d 个" % shown)

        # 自动选中第一个采集点，省一次点击
        kids = self.tv_sites.get_children()
        if kids and not self.tv_sites.selection():
            self.tv_sites.selection_set(kids[0])
            self.tv_sites.focus(kids[0])
            self.on_site_select()

    def draft_text(self, site):
        d = extras.draft_of(site.get("id"))
        if not d:
            return "未建"
        st = {"draft": "草稿", "submitted": "待审核", "approved": "已通过",
              "rejected": "驳回", "missing": "已删除"}.get(d.get("status") or "", "草稿")
        return "%s %s" % (st, str(d.get("task_set_id"))[-6:])

    # ------------------------------------------------------------ 选择采集点

    def current_site(self):
        sel = self.tv_sites.selection()
        if not sel:
            return None
        sid = sel[0]
        for s in self.sites:
            if s["id"] == sid:
                return s
        return None

    def on_site_select(self):
        site = self.current_site()
        if not site:
            return
        self.site = site
        self.task = None
        self.files = []
        self.selected.clear()
        self.render_files()
        self.lbl_site_name.config(text=site.get("name", ""))
        self.lbl_site_info.config(text="%s · %s 个文件 · %s" % (
            site.get("address", ""), site.get("file_count", 0),
            (site.get("created_at") or "")[:16].replace("T", " ")))
        self.cmb_task.set("")
        self.cmb_task["values"] = []
        self.lbl_task_count.config(text="读取任务…")

        def work():
            try:
                detail = self.api.site(site["id"])
            except Exception as e:
                self.ui(self.lbl_task_count.config, text="读取失败：%s" % e)
                return
            self.ui(self.fill_tasks, detail)

        threading.Thread(target=work, daemon=True).start()

    def fill_tasks(self, detail):
        tasks = detail.get("tasks") or []
        labels = []
        self._tasks = tasks
        for i, t in enumerate(tasks):
            area = (t.get("area") or "").strip()
            name = (t.get("name") or "").strip()
            n = len(t.get("photos") or []) + len(t.get("videos") or [])
            labels.append("%d. %s%s（%d 个素材）" % (i + 1, (area + "：") if area else "", name, n))
        self.cmb_task["values"] = labels
        self.lbl_task_count.config(text="%d 个任务" % len(tasks))
        if labels:
            self.cmb_task.current(0)
            self.on_task_select()

    def on_task_select(self):
        idx = self.cmb_task.current()
        if idx < 0 or not getattr(self, "_tasks", None):
            return
        if idx >= len(self._tasks):
            return
        self.task = self._tasks[idx]
        self.files = (self.task.get("photos") or []) + (self.task.get("videos") or [])
        self.selected.clear()
        self.render_files()

    # ------------------------------------------------------------ 缩略图墙

    def render_files(self):
        self.tv_files.delete(*self.tv_files.get_children())
        if not self.files:
            self.tv_files.insert("", "end", iid="__empty", values=("", "这个任务还没有素材", "", "", ""))
            self.update_sel_state()
            return
        for f in self.files:
            fid = f["id"]
            self.tv_files.insert("", "end", iid=fid, values=(
                "☑" if fid in self.selected else "☐",
                f.get("filename") or fid,
                "照片" if f.get("kind") == "photo" else "视频",
                human_size(f.get("size")),
                (f.get("created_at") or "")[:16].replace("T", " "),
            ))
        self.update_sel_state()

    def _on_file_click(self, event):
        if self.tv_files.identify_region(event.x, event.y) != "cell":
            return
        if self.tv_files.identify_column(event.x) != "#1":
            return
        iid = self.tv_files.identify_row(event.y)
        if iid and iid != "__empty":
            self._toggle_file(iid)
            return "break"

    def _toggle_focus_file(self):
        iid = self.tv_files.focus()
        if iid and iid != "__empty":
            self._toggle_file(iid)

    def _toggle_file(self, fid):
        if fid in self.selected:
            self.selected.discard(fid)
            self.tv_files.set(fid, "pick", "☐")
        else:
            self.selected.add(fid)
            self.tv_files.set(fid, "pick", "☑")
        self.update_sel_state()

    def update_sel_state(self):
        n = len(self.selected)
        self.btn_dl_sel.config(text="下载选中（%d）" % n if n else "下载选中")
        self.btn_del_sel.config(text="删除选中（%d）" % n if n else "删除选中")

    def select_all(self):
        self.selected = {f["id"] for f in self.files if f["id"]}
        self.render_files()

    def select_none(self):
        self.selected.clear()
        self.render_files()

    # ------------------------------------------------------------ 操作

    def _files_by_ids(self, ids):
        return [f for f in self.files if f["id"] in ids]

    def download_selected(self):
        files = self._files_by_ids(self.selected)
        if not files:
            messagebox.showinfo(APP_NAME, "先点缩略图选中素材")
            return
        self.download_files(files)

    def delete_selected(self):
        files = self._files_by_ids(self.selected)
        if not files:
            messagebox.showinfo(APP_NAME, "先点缩略图选中素材")
            return
        if not messagebox.askyesno(APP_NAME, "删除选中的 %d 个素材？不可恢复。" % len(files)):
            return

        def work():
            ok = fail = 0
            for f in files:
                try:
                    self.api.delete_file(f["id"])
                    ok += 1
                except Exception:
                    fail += 1
            self.ui(self.set_status, "已删除 %d，失败 %d" % (ok, fail), "#15803D")
            self.ui(self.on_site_select)

        threading.Thread(target=work, daemon=True).start()

    def download_files(self, files):
        from tkinter import filedialog
        target = filedialog.askdirectory(title="选择保存目录")
        if not target:
            return
        site_name = (self.site or {}).get("name") or "采集点"
        folder = os.path.join(target, site_name)
        os.makedirs(folder, exist_ok=True)
        self.progress["maximum"] = 100
        self.progress["value"] = 0

        def work():
            total = len(files)
            for i, f in enumerate(files, 1):
                try:
                    dest = os.path.join(folder, f.get("filename") or f["id"])
                    self.api.download("/files/" + f["id"], dest)
                except Exception:
                    pass
                self.ui(self.progress.config, value=int(i * 100 / total))
                self.ui(self.set_status, "下载 %d/%d" % (i, total), "#15803D")
            self.ui(self.set_status, "下载完成：%d 个文件" % total, "#15803D")
            try:
                os.startfile(folder)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def download_site(self):
        if not self.site:
            messagebox.showinfo(APP_NAME, "先选一个采集点")
            return

        def work():
            detail = self.api.site(self.site["id"])
            files = []
            for t in detail.get("tasks") or []:
                files += (t.get("photos") or []) + (t.get("videos") or [])
            self.ui(self.download_files, files)

        threading.Thread(target=work, daemon=True).start()

    def qc_site(self):
        if not self.site:
            messagebox.showinfo(APP_NAME, "先选一个采集点")
            return
        self.set_status("质检中…")

        def work():
            try:
                detail = self.api.site(self.site["id"])
                files = []
                for t in detail.get("tasks") or []:
                    files += (t.get("photos") or []) + (t.get("videos") or [])
                issues = []
                for f in files:
                    if not f.get("size"):
                        issues.append("%s：文件为 0 字节" % f.get("filename"))
                if issues:
                    self.ui(messagebox.showwarning, APP_NAME, "发现 %d 个问题：\n\n%s"
                            % (len(issues), "\n".join(issues[:10])))
                else:
                    self.ui(messagebox.showinfo, APP_NAME, "质检通过：%d 个素材都有内容" % len(files))
                self.ui(self.set_status, "质检完成", "#15803D")
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "质检失败：%s" % e)

        threading.Thread(target=work, daemon=True).start()

    def delete_site(self):
        site = self.current_site()
        if not site:
            return
        if not messagebox.askyesno(APP_NAME, "删除采集点「%s」及其全部素材？不可恢复。" % site.get("name")):
            return

        def work():
            try:
                self.api.delete_site(site["id"])
                self.ui(self.set_status, "已删除", "#15803D")
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "删除失败：%s" % e)
            self.ui(self.refresh)

        threading.Thread(target=work, daemon=True).start()

    def cleanup_empty(self):
        def work():
            items = self.api.sites()
            empty = [x for x in items if not x.get("file_count")]
            if not empty:
                self.ui(messagebox.showinfo, APP_NAME, "没有空采集点")
                return
            names = "\n".join("· " + (x.get("name") or "") for x in empty[:15])
            self.ui(lambda: self._do_cleanup(empty, names))

        threading.Thread(target=work, daemon=True).start()

    def _do_cleanup(self, empty, names):
        if not messagebox.askyesno(APP_NAME, "删除 %d 个空采集点？\n\n%s" % (len(empty), names)):
            return

        def work():
            for x in empty:
                try:
                    self.api.delete_site(x["id"])
                except Exception:
                    pass
            self.ui(self.refresh)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ EgoOps

    def open_egoops(self):
        import webbrowser
        webbrowser.open("https://egoops.meituan.com/assignment")

    def check_login(self):
        if egoops_auth is None:
            self.lbl_login.config(text="EgoOps 模块缺失")
            return

        def work():
            try:
                ok, who = egoops_auth.alive(egoops_auth.token_of())
            except Exception as e:
                ok, who = False, str(e)
            self.login_ok = ok
            self.ui(lambda: self.lbl_login.config(
                text=("EgoOps 已登录 %s" % who) if ok else "EgoOps 未登录（点美团菜单登录）",
                foreground="#15803D" if ok else "#B91C1C"))

        threading.Thread(target=work, daemon=True).start()

    def relogin(self):
        if egoops_auth is None:
            return

        def work():
            ok, info = egoops_auth.relogin(log=lambda m: self.ui(self.set_status, str(m)))
            self.ui(lambda: messagebox.showinfo(APP_NAME, str(info)))
            self.ui(self.check_login)

        threading.Thread(target=work, daemon=True).start()

    def make_draft(self):
        if not self.site:
            messagebox.showinfo(APP_NAME, "先选一个采集点")
            return
        if self.login_ok is False:
            messagebox.showwarning(APP_NAME, "EgoOps 未登录，先在「美团」菜单里登录")
            return

        d = extras.draft_of(self.site["id"])
        if d and not messagebox.askyesno(
                APP_NAME, "这个采集点已经建过草稿（%s），要再建一份吗？" % d.get("task_set_id")):
            return

        code = (self.site.get("invite") or "").strip().upper()
        try:
            systems = self.api.vendor_systems()
        except Exception:
            systems = {}
        if systems.get(code) != "meituan":
            messagebox.showwarning(APP_NAME, "这个采集点的厂商不是美团，EgoOps 流程不适用")
            return

        win = tk.Toplevel(self.root)
        win.title("正在建草稿…")
        win.geometry("520x220")
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text="步骤：", style="Sub.TLabel", padding=12).pack(anchor="w")
        logv = tk.StringVar(value="准备中…")
        ttk.Label(win, textvariable=logv, padding=(12, 0), wraplength=480).pack(anchor="w")
        pb = ttk.Progressbar(win, maximum=100, length=460)
        pb.pack(padx=12, pady=12)
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=(0, 10))

        def ui_log(msg):
            self.ui(lambda: (logv.set(str(msg)), pb.step(2)))

        def work():
            try:
                import egoops_draft as ed
                detail = self.api.site(self.site["id"])
                payload = dict(detail)
                for t in payload.get("tasks") or []:
                    for f in (t.get("photos") or []) + (t.get("videos") or []):
                        f["url"] = "/files/" + f["id"]
                def prog(pct, text):
                    self.ui(pb.configure, value=pct)
                    ui_log(text)

                res = ed.create_draft(payload,
                                      relay_files=lambda f: self._local_copy(f),
                                      log=ui_log,
                                      progress=prog)
                extras.remember(self.site["id"], res["task_set_id"], res.get("name", ""))
                self.ui(lambda: (win.destroy(), messagebox.showinfo(
                    APP_NAME, "草稿已建：%s\n任务 %d 个" % (res["task_set_id"], len(res.get("tasks") or [])))))
                self.ui(self.refresh)
            except Exception as e:
                self.ui(lambda: (logv.set("失败：%s" % e), messagebox.showerror(APP_NAME, "建草稿失败：%s" % e)))

        threading.Thread(target=work, daemon=True).start()

    def _local_copy(self, f):
        """把服务器上的素材下载到临时目录，供建草稿使用"""
        path = os.path.join(HERE, ".cache", f["id"] + os.path.splitext(f.get("filename") or "")[1])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            self.api.download("/files/" + f["id"], path)
        return path

    # ------------------------------------------------------------ 其它

    def storage_dialog(self):
        def work():
            try:
                st = self.api._request("GET", "/api/storage", timeout=30)
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "检查失败：%s" % e)
                return
            msg = ("数据库：%d 个文件 / %s\n磁盘：%s\n残留：%d 个 / %s"
                   % (st.get("db_files"), human_size(st.get("db_bytes")),
                      human_size(st.get("disk_bytes")), st.get("orphan_files"),
                      human_size(st.get("orphan_bytes"))))
            self.ui(lambda: messagebox.showinfo(APP_NAME, msg))

        threading.Thread(target=work, daemon=True).start()

    def export_csv(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="采集点.csv")
        if not path:
            return
        rows = []
        for s in self.sites:
            rows.append([s.get("name", ""), s.get("address", ""), s.get("file_count", 0),
                         s.get("created_by", ""), (s.get("created_at") or "")[:19], self.draft_text(s)])
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                import csv
                w = csv.writer(f)
                w.writerow(["门店", "地址", "文件数", "采集员", "时间", "EgoOps"])
                w.writerows(rows)
            messagebox.showinfo(APP_NAME, "已导出 %d 条" % len(rows))
        except Exception as e:
            messagebox.showerror(APP_NAME, "导出失败：%s" % e)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
