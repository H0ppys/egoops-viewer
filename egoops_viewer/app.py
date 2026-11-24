"""主窗口 App 装配与自检（拆分自 app.py：42-92 类体、2415-2429 selftest）

App 自身只保留 __init__ / _upgrade_server_url；各功能面板作为 mixin 从 ui_*.py 注入，
方法体逐字保留（原始 class App 41-2413 的逐行搬运，见 docs/SPLIT.md）。
"""

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
from .ui_theme import ThemeMixin  # noqa: F401
from .ui_auth import AuthMixin  # noqa: F401
from .ui_layout import LayoutMixin  # noqa: F401
from .ui_guide import GuideMixin  # noqa: F401
from .ui_settings import SettingsMixin  # noqa: F401
from .ui_invite import InviteMixin  # noqa: F401
from .ui_draft import DraftMixin  # noqa: F401
from .ui_fill import FillMixin  # noqa: F401
from .ui_batch import BatchMixin  # noqa: F401
from .ui_events import EventsMixin  # noqa: F401
from .ui_connect import ConnectMixin  # noqa: F401
from .ui_tree import TreeMixin  # noqa: F401
from .ui_delete import DeleteMixin  # noqa: F401
from .ui_download import DownloadMixin  # noqa: F401


class App(
    ThemeMixin,
    AuthMixin,
    LayoutMixin,
    GuideMixin,
    SettingsMixin,
    InviteMixin,
    DraftMixin,
    FillMixin,
    BatchMixin,
    EventsMixin,
    ConnectMixin,
    TreeMixin,
    DeleteMixin,
    DownloadMixin,
):
    """采集数据查看器主窗口：由各 ui_* mixin 拼装，等价原 app.py 的 App。"""

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
