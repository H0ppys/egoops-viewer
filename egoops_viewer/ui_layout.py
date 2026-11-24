"""主窗口整体布局：顶栏 / 左树 / 右预览 / 底部三行按钮（拆分自 app.py 220-424）"""

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


class LayoutMixin:
    """LayoutMixin：主窗口整体布局：顶栏 / 左树 / 右预览 / 底部三行按钮（拆分自 app.py 220-424）"""
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
