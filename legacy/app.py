"""采集数据查看器（Windows 桌面版）

功能：连自己的采集服务器 → 看采集点列表 → 看每个采集点的照片/视频 → 一键下载到本地。
打包：见 build.ps1
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from api import Api, ApiError, human_size
from address_parse import parse as parse_address
import extras

APP_VER = "v16"
APP_NAME = "采集数据查看器"
DEFAULT_SERVER = "http://123.207.6.210/relay"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "egoops-viewer")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class App:
    def _upgrade_server_url(self):
        srv = (self.cfg.get("server") or "").strip()
        if srv.startswith("http://123.207.6.210/relay"):
            self.cfg["server"] = srv.replace("http://", "https://", 1)
            try:
                save_config(self.cfg)
            except Exception:
                pass

    def __init__(self, root, autoconnect=True):
        self.root = root
        self.cfg = load_config()
        self.api = None
        self.sites = []
        self.current_site = None
        self.files = []
        self.checked = set()
        self.checked_sites = set()
        self.site_rows = {}
        self.file_rows = {}
        self.loaded_sites = set()
        self.vendor_filter = ""
        self.vendor_names = {}
        self.vendor_systems = {}
        self._preview_cache = {}
        self._preview_pending = set()
        self.events = queue.Queue()
        self.busy = False

        root.title(APP_NAME + " " + APP_VER)
        root.geometry("1560x900")
        root.configure(bg="#F1F5F9")
        root.minsize(1100, 640)
        self.var_server = tk.StringVar(value=self.cfg.get("server") or DEFAULT_SERVER)
        self.var_name = tk.StringVar(value=self.cfg.get("name", ""))
        self.var_search = tk.StringVar(value="")
        self.var_range = tk.StringVar(value="全部")
        self.var_vendor = tk.StringVar(value="全部")
        self.login_ok = None
        self.login_who = ""

        self._style()
        self._apply_theme()
        self._build()
        self._poll()

        if autoconnect and self.var_name.get():
            self.do_connect()

        self.root.after(600, self.check_egoops_login)

    # ---------------------------------------------------------------- 样式

    def _apply_theme(self):
        try:
            import sv_ttk
            sv_ttk.set_theme("light")
            self.modern = True
        except Exception:
            self.modern = False

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

    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("vista")
        except Exception:
            pass
        s.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 10))
        s.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 6))
        s.configure("Big.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(14, 10))
        try:
            if getattr(self, "modern", False):
                base = 10
            else:
                base = 9
        except Exception:
            base = 9
        s.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        s.configure("Section.TLabel", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Dim.TLabel", font=("Microsoft YaHei UI", base))
        s.configure("Guide.TLabel", font=("Microsoft YaHei UI", base + 1), foreground="#334155")
        s.configure("Status.TLabel", font=("Microsoft YaHei UI", base))
        s.configure("Preview.TLabel", font=("Microsoft YaHei UI", base), foreground="#64748B")
        s.configure("Card.TFrame", relief="solid", borderwidth=1)
        try:
            s.configure("Danger.TButton", foreground="#B91C1C")
        except Exception:
            pass
        s.configure("Big.Treeview", rowheight=44, font=("Microsoft YaHei UI", 11))
        s.configure("Big.Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Head.TFrame", background="#FFFFFF")
        s.configure("Dim.TLabel", foreground="#64748B", background="#FFFFFF", font=("Microsoft YaHei UI", 9))
        s.configure("Card.Treeview", rowheight=28, font=("Microsoft YaHei UI", 9),
                    fieldbackground="#FFFFFF", background="#FFFFFF", borderwidth=0)
        s.configure("Card.Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"), padding=(6, 6))
        s.configure("Title.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        s.configure("Group.TLabel", font=("Microsoft YaHei UI", 10, "bold"), foreground="#6b7a90", width=6)
        s.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Danger.TButton", font=("Microsoft YaHei UI", 10), foreground="#b3261e")

    # ---------------------------------------------------------------- 布局

    def _build(self):
        # ---------- 顶栏 ----------
        head = ttk.Frame(self.root, padding=(20, 14, 20, 6))
        head.pack(fill="x")

        ttk.Label(head, text="采集数据查看器", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="美团采集 · 质检 · 建草稿", style="Dim.TLabel").pack(side="left", padx=(12, 0), pady=(4, 0))
        self.lbl_status = ttk.Label(head, text="未连接", style="Status.TLabel")
        self.lbl_status.pack(side="right")

        self.lbl_egoops = tk.Label(head, text="EgoOps 检查中…", font=("Microsoft YaHei UI", 9),
                                   bg="#F1F5F9", fg="#64748B", cursor="hand2")
        self.lbl_egoops.pack(side="right", padx=(0, 16))


        # ---------- 服务器行 ----------
        bar = ttk.Frame(self.root, padding=(20, 0, 20, 8))
        bar.pack(fill="x")

        ttk.Entry(bar, textvariable=self.var_server, width=30, font=("Consolas", 10)).pack(side="left")
        ttk.Entry(bar, textvariable=self.var_name, width=8).pack(side="left", padx=(8, 8))
        self.btn_connect = ttk.Button(bar, text="连接", style="Accent.TButton", command=self.do_connect)
        self.btn_connect.pack(side="left")
        self.btn_refresh = ttk.Button(bar, text="刷新", command=self.do_refresh)
        self.btn_refresh.pack(side="left", padx=(6, 16))

        ttk.Entry(bar, textvariable=self.var_search, width=18).pack(side="left")
        self.cmb_range = ttk.Combobox(bar, textvariable=self.var_range, width=7, state="readonly",
                                      values=["全部", "今天", "近 7 天", "近 30 天"])
        self.cmb_range.pack(side="left", padx=(6, 6))
        self.cmb_vendor = ttk.Combobox(bar, textvariable=self.var_vendor, width=14, state="readonly", values=["全部"])
        self.cmb_vendor.pack(side="left")

        self.lbl_invite = ttk.Label(bar, text="")
        self.ent_invite = ttk.Entry(bar, width=8, show="*")
        self.cmb_vendor.bind("<<ComboboxSelected>>", lambda e: self.do_refresh())
        self.cmb_range.bind("<<ComboboxSelected>>", lambda e: self.do_refresh())
        self.var_search.trace_add("write", lambda *a: self._on_search_typing())

        # ---------- 主体：左列表 + 右操作 ----------
        body = ttk.Frame(self.root, padding=(20, 0, 20, 0))
        body.pack(fill="both", expand=True)

        # 左：列表
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        self.lbl_site = ttk.Label(left, text="采集点", style="Section.TLabel")
        self.lbl_site.pack(anchor="w", pady=(0, 6))

        wrap = ttk.Frame(left)
        wrap.pack(fill="both", expand=True)

        cols = ("sel", "name", "address", "vendor", "time", "draft")
        self.tree = ttk.Treeview(wrap, columns=cols, show="tree headings",
                                 selectmode="browse", style="Big.Treeview")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=34, minwidth=34, stretch=False)
        spec = [("sel", "选", 44, "center"), ("name", "门店 / 文件", 190, "w"),
                ("address", "现场地址", 230, "w"), ("vendor", "厂商", 90, "center"),
                ("time", "采集时间", 130, "center"), ("draft", "EgoOps", 96, "center")]
        for c, t, w, anchor in spec:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, minwidth=w, anchor=anchor,
                             stretch=(c in ("name", "address")))
        self.tree.tag_configure("odd", background="#FBFCFE")
        self.tree.tag_configure("even", background="#FFFFFF")

        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self.on_tree_double)

        # 右：操作面板
        side = ttk.Frame(body, width=360, padding=(16, 0, 0, 0))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        self.btn_login = ttk.Button(side, text="登录 EgoOps", style="Danger.TButton", command=self.do_login)

        self.lbl_section = ttk.Label(side, text="下一步", style="Section.TLabel")
        self.lbl_section.pack(anchor="w", pady=(0, 6))

        card = ttk.Frame(side, style="Card.TFrame", padding=16)
        card.pack(fill="x")

        self.lbl_guide = ttk.Label(card, text="点「连接」把采集点拉下来。", style="Guide.TLabel",
                                   wraplength=310, justify="left")
        self.lbl_guide.pack(anchor="w")

        self.btn_step_main = ttk.Button(card, text="连接服务器", style="Accent.TButton",
                                        command=self.do_connect)
        self.btn_step_main.pack(fill="x", pady=(14, 0))

        ttk.Separator(side).pack(fill="x", pady=14)

        ttk.Label(side, text="常用操作", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Button(side, text="下载勾选的素材", command=self.download_checked).pack(fill="x", pady=3)
        ttk.Button(side, text="质检这个采集点", command=self.qc_site).pack(fill="x", pady=3)
        ttk.Button(side, text="预览草稿内容", command=self.show_draft).pack(fill="x", pady=3)
        ttk.Button(side, text="打开 EgoOps 网页", command=self.open_egoops).pack(fill="x", pady=3)
        ttk.Button(side, text="打开下载目录", command=self.open_download_dir).pack(fill="x", pady=3)

        # 兼容旧引用
        self.btn_dl_sites = self.btn_step_main
        self.btn_check_all = ttk.Button(side)
        self.btn_check_sites = self.btn_check_all
        self.btn_del_sites = ttk.Button(side)
        self.btn_dl = self.btn_step_main
        self.btn_dl_all = self.btn_step_main
        self.btn_open = ttk.Button(side)
        self.btn_draft = ttk.Button(side)
        self.btn_batch = ttk.Button(side)
        self.btn_qc = ttk.Button(side)
        self.btn_export = ttk.Button(side)

        # ---------- 预览 ----------
        self.preview = ttk.Label(self.root, text="选中照片会在上面显示", style="Preview.TLabel",
                                 anchor="center")
        self.preview.pack(fill="x", pady=(8, 6), ipady=6)

        # ---------- 底部 ----------
        foot = ttk.Frame(self.root, padding=(20, 8, 20, 14))
        foot.pack(side="bottom", fill="x", before=body)

        self.btn_dl_checked = ttk.Button(foot, text="下载勾选", style="Accent.TButton",
                                         command=self.download_checked)
        self.btn_dl_checked.pack(side="left")

        self.btn_del_files = ttk.Button(foot, text="删除勾选", command=self.delete_checked_files)
        self.btn_del_files.pack(side="left", padx=8)

        self.btn_fill = ttk.Button(foot, text="一键建草稿（美团）", style="Accent.TButton",
                                   command=self.fill_egoops)
        self.btn_fill.pack(side="left", padx=(20, 0))

        self.progress = ttk.Progressbar(foot, mode="determinate", length=220)
        self.progress.pack(side="right")
        self.lbl_task = ttk.Label(foot, text="", style="Dim.TLabel")
        self.lbl_task.pack(side="right", padx=12)

        # ---------- 菜单 ----------
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="打开下载目录", command=self.open_download_dir)
        m_file.add_command(label="导出采集数据表…", command=self.export_table)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=m_file)

        m_site = tk.Menu(menubar, tearoff=0)
        m_site.add_command(label="刷新列表", command=self.do_refresh)
        m_site.add_command(label="全选 / 取消全选", command=self.toggle_all_checks)
        m_site.add_separator()
        m_site.add_command(label="下载这个采集点全部", command=self.download_site)
        m_site.add_command(label="质检这个采集点", command=self.qc_site)
        m_site.add_separator()
        m_site.add_command(label="删除勾选的采集点", command=self.delete_checked_sites)
        m_site.add_command(label="清理空采集点（0 文件）", command=self.cleanup_empty_sites)
        menubar.add_cascade(label="采集点", menu=m_site)

        m_mt = tk.Menu(menubar, tearoff=0)
        m_mt.add_command(label="生成草稿（先核对）", command=self.show_draft)
        m_mt.add_command(label="一键建草稿", command=self.fill_egoops)
        m_mt.add_command(label="批量建草稿", command=self.batch_draft)
        m_mt.add_separator()
        m_mt.add_command(label="刷新草稿状态", command=self.refresh_draft_status)
        m_mt.add_command(label="立即登录 EgoOps（手机验证码）", command=self.do_login)
        m_mt.add_command(label="检查登录态", command=self.check_egoops_login)
        menubar.add_cascade(label="美团", menu=m_mt)

        m_set = tk.Menu(menubar, tearoff=0)
        m_set.add_command(label="服务器空间 / 清理…", command=self.storage_dialog)
        m_set.add_command(label="设置…", command=self.open_settings)
        menubar.add_cascade(label="设置", menu=m_set)

        self.root.config(menu=menubar)

        self.ctx = tk.Menu(self.root, tearoff=0)
        self.ctx.add_command(label="下载", command=self.download_checked)
        self.ctx.add_command(label="质检", command=self.qc_site)
        self.ctx.add_command(label="生成草稿", command=self.show_draft)
        self.ctx.add_command(label="一键建草稿", command=self.fill_egoops)
        self.ctx.add_separator()
        self.ctx.add_command(label="删除", command=self.delete_checked_files)
        self.tree.bind("<Button-3>", self._show_ctx)

        self.root.bind("<Control-a>", lambda e: self.toggle_all_checks())

    def open_egoops(self):
        import webbrowser
        webbrowser.open("https://egoops.meituan.com/assignment")

    # ---------------------------------------------------------------- 引导

    def _on_step_click(self, key):
        if key == "connect":
            self.do_connect()

    def set_step(self, active):
        pass

    def update_guide(self):
        if not getattr(self, "api", None):
            self.lbl_guide.config(text="① 先在上面填服务器地址，点「连接」。")
            self.btn_step_main.config(text="连接服务器", command=self.do_connect)
            return

        site, iid = self._target_site()
        if not site:
            n = len(getattr(self, "sites", []) or [])
            self.lbl_guide.config(text="② 已拉到 %d 个采集点。\n\n点一行看详情，或点最左边的方框勾选。" % n)
            self.btn_step_main.config(text="刷新列表", command=self.do_refresh)
            return

        d = extras.draft_of(site.get("id"))
        if d:
            st = d.get("status_text") or "草稿"
            self.lbl_guide.config(text="④ 已经建过草稿：%s\n状态：%s\n\n重复建会在 EgoOps 里多出一条。"
                                  % (d.get("task_set_id"), st))
            self.btn_step_main.config(text="再次建草稿", command=self.fill_egoops)
        else:
            self.lbl_guide.config(text="③ 已选中「%s」。\n\n先点「质检这个采集点」看有没有坏图；"
                                  "确认没问题再建草稿。" % site.get("name", ""))
            self.btn_step_main.config(text="一键建草稿", command=self.fill_egoops)

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

    # ---------------------------------------------------------------- 线程通信

    def _poll(self):
        try:
            while True:
                item = self.events.get_nowait()
                fn, args = item[0], item[1]
                kwargs = item[2] if len(item) > 2 else {}
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    try:
                        log_dir = os.path.join(os.environ.get("APPDATA") or ".", "egoops-viewer")
                        os.makedirs(log_dir, exist_ok=True)
                        with open(os.path.join(log_dir, "error.log"), "a", encoding="utf-8") as fh:
                            fh.write("\n=== %s ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                            fh.write(traceback.format_exc())
                    except Exception:
                        pass
                    self.set_status("界面出错：%s" % e, "#b3261e")
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def ui(self, fn, *args, **kwargs):
        self.events.put((fn, args, kwargs))

    def set_status(self, text, color="#666"):
        self.lbl_status.config(text=text, foreground=color)

    # ---------------------------------------------------------------- 连接

    def do_connect(self):
        server = self.var_server.get().strip()
        name = self.var_name.get().strip()
        invite = self.cfg.get("invite", "").strip()
        if not server:
            messagebox.showwarning(APP_NAME, "请填写服务器地址")
            return
        if not name:
            messagebox.showwarning(APP_NAME, "请填写姓名（随便填一个，只用来记谁在看）")
            pass
            return
        self.cfg.update({"server": server, "name": name, "invite": invite})
        save_config(self.cfg)
        self.set_status("连接中…")

        def work():
            try:
                api = Api(server)
                h = api.health()
                required = bool(h.get("inviteRequired"))
                api.login(name, invite=invite if required else "")
                self.api = api
                self.ui(self.apply_invite_visibility, required)
                self.ui(self.on_connected, h)
            except ApiError as e:
                self.ui(self.set_status, "连接失败：%s" % e, "#b3261e")
                self.ui(messagebox.showerror, APP_NAME, "连接失败：\n%s" % e)
            except Exception as e:
                self.ui(self.set_status, "连接失败：%s" % e, "#b3261e")

        threading.Thread(target=work, daemon=True).start()

    def apply_invite_visibility(self, required):
        if required:
            self.lbl_invite.pack(side="left", before=self.btn_connect)
            pass
        else:
            self.lbl_invite.pack_forget()
            pass

    def _show_ctx(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.focus(iid)
            self.tree.selection_set(iid)
        try:
            self.ctx.tk_popup(event.x_root, event.y_root)
        finally:
            self.ctx.grab_release()

    def refresh_login_state(self):
        self.lbl_task.config(text="正在检查 EgoOps 登录态…")

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
                ok, msg = mod.refresh(log=lambda m: self.ui(self.lbl_task.config, text=str(m)))
            except Exception as e:
                ok, msg = False, "刷新失败：%s" % e
            self.ui(lambda: (self.lbl_task.config(text=msg),
                             messagebox.showinfo(APP_NAME, msg) if ok else messagebox.showerror(APP_NAME, msg)))

        threading.Thread(target=work, daemon=True).start()

    def _target_site(self):
        """当前选中的采集点；没选中就用勾选的第一条"""
        iid = self.tree.focus()
        if iid in self.site_rows:
            return self.site_rows[iid], iid
        for c in self.checked:
            if c in self.site_rows:
                try:
                    self.tree.focus(c)
                    self.tree.selection_set(c)
                except Exception:
                    pass
                return self.site_rows[c], c
        return None, None

    def draft_text(self, site):
        d = extras.draft_of(site.get("id"))
        if not d:
            return "未建"
        st = (d.get("status") or "").strip()
        text = {"draft": "草稿", "submitted": "待审核", "pending": "待审核",
                "approved": "已通过", "rejected": "驳回", "missing": "已删除"}.get(st, "")
        if text:
            return "%s %s" % (text, str(d.get("task_set_id"))[-6:])
        return "草稿 " + str(d.get("task_set_id"))[-6:]

    def refresh_draft_status(self):
        import importlib.util
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "egoops_status.py")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "egoops_status.py")
        spec = importlib.util.spec_from_file_location("egoops_status", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        drafts = extras.load_drafts()
        if not drafts:
            messagebox.showinfo(APP_NAME, "还没有建过草稿")
            return
        self.lbl_task.config(text="正在查 EgoOps 草稿状态…")

        def work():
            try:
                res = mod.refresh_all(drafts, log=lambda m: self.ui(self.lbl_task.config, text=m))
            except PermissionError as e:
                self.ui(messagebox.showerror, APP_NAME, str(e))
                self.ui(self.lbl_task.config, text="查询失败：登录态失效")
                return
            except Exception as e:
                self.ui(messagebox.showerror, APP_NAME, "查询失败：%s" % e)
                return

            def apply():
                d = extras.load_drafts()
                for site_id, info in res.items():
                    if site_id in d:
                        d[site_id]["status"] = info.get("status")
                        d[site_id]["status_text"] = info.get("text")
                        d[site_id]["status_at"] = info.get("at")
                extras.save_drafts(d)
                self.lbl_task.config(text="已更新 %d 条草稿状态" % len(res))
                self.do_refresh()

            self.ui(apply)

        threading.Thread(target=work, daemon=True).start()

    def invites_map(self):
        """本地配置：{"ZJMEIYI": "湛江盛宴科技有限公司"}"""
        m = self.cfg.get("invites")
        if not isinstance(m, dict):
            m = {}
            self.cfg["invites"] = m
        return m

    def vendor_of(self, site):
        code = (site.get("invite") or "").strip()
        if not code:
            return "—"
        up = code.upper()
        # 1) 服务器上的「邀请码 → 厂家」（飞书表同步过来的）
        names = getattr(self, "vendor_names", None) or {}
        sysname = (getattr(self, "vendor_systems", None) or {}).get(up, "")
        suffix = "" if sysname in ("meituan", "") else " · 其他系统"
        if up in names:
            return names[up] + suffix
        # 2) 本机自己配的映射
        for k, v in self.invites_map().items():
            if k.strip().upper() == up:
                return v
        return up + "（未登记）"

    def load_vendor_systems(self):
        try:
            self.vendor_systems = {str(k).upper(): v for k, v in (self.api.vendor_systems() or {}).items()}
        except Exception:
            pass

    def system_of(self, site):
        code = (site.get("invite") or "").strip().upper()
        return self.vendor_systems.get(code, "")

    def load_vendor_names(self):
        def work():
            try:
                items = self.api.vendor_names()
            except Exception:
                return
            self.vendor_names = {str(k).upper(): v for k, v in (items or {}).items()}
            self.ui(self.do_refresh)

        threading.Thread(target=work, daemon=True).start()

    def load_vendors(self):
        m = self.invites_map()
        values = ["全部"] + sorted(set(v for v in m.values() if v))
        self.cmb_vendor.configure(values=values)
        if self.cmb_vendor.get() not in values:
            self.cmb_vendor.set("全部")

    def on_connected(self, health):
        self.set_status("已连接 · 采集点 %s 个 · 文件 %s 个" % (health.get("sites", 0), health.get("files", 0)), "#1f7a3d")
        self.load_vendor_systems()
        self.load_vendor_names()
        self.load_vendors()
        self.do_refresh()

    def do_refresh(self):
        if not self.api:
            return
        self.set_status("读取列表中…")

        def work():
            try:
                items = self.api.sites()
                want = getattr(self, "vendor_filter", "")
                if want:
                    items = [x for x in items if self.vendor_of(x) == want]
                self.ui(self.fill_sites, items)
                self.ui(self.auto_sync_drafts)
            except ApiError as e:
                self.ui(self.set_status, "读取失败：%s" % e, "#b3261e")

        threading.Thread(target=work, daemon=True).start()

    def auto_sync_drafts(self):
        """自动核对草稿：不在了就标成「未建」"""
        import time as _t
        if not getattr(self, "api", None):
            return
        drafts = extras.load_drafts()
        if not drafts:
            return
        now = _t.time()
        if now - getattr(self, "_last_draft_sync", 0) < 60:
            return
        self._last_draft_sync = now

        def work():
            try:
                mod = self._load_status_mod()
                tok = mod.egoops_auth.token_of()
                ok, _ = mod.egoops_auth.alive(tok)
                if not ok:
                    return
            except Exception:
                return

            alive, gone = {}, []
            for site_id, info in list(drafts.items()):
                tsid = info.get("task_set_id")
                if not tsid:
                    continue
                try:
                    r = mod.fetch_one(tsid, tok)
                except PermissionError:
                    return
                except Exception:
                    continue
                if r is None:
                    gone.append(site_id)
                else:
                    alive[site_id] = r

            def apply():
                d = extras.load_drafts()
                for site_id in gone:
                    d.pop(site_id, None)
                for site_id, r in alive.items():
                    if site_id in d:
                        d[site_id]["status"] = r.get("status")
                        d[site_id]["status_text"] = r.get("text")
                        d[site_id]["status_at"] = r.get("at")
                extras.save_drafts(d)
                if gone:
                    self.lbl_task.config(text="%d 个草稿在 EgoOps 已被删除，标记为未建" % len(gone))
                self.fill_sites(self.sites)

            self.ui(apply)

        threading.Thread(target=work, daemon=True).start()

    def _load_status_mod(self):
        import importlib.util
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "egoops_status.py")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "egoops_status.py")
        spec = importlib.util.spec_from_file_location("egoops_status_auto", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

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


def selftest():
    """无界面自检：能建窗口、能布局、能读到服务器地址，结果写到 TEMP 下。"""
    out = os.path.join(os.environ.get("TEMP", "."), "egoops-viewer-selftest.txt")
    try:
        root = tk.Tk()
        root.withdraw()
        app = App(root, autoconnect=False)
        root.update_idletasks()
        with open(out, "w", encoding="utf-8") as f:
            f.write("ok\nserver=%s\ncols=%s\n" % (app.var_server.get(), ",".join(app.tree["columns"])))
        root.destroy()
    except Exception as e:
        with open(out, "w", encoding="utf-8") as f:
            f.write("fail: %r\n" % (e,))


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
