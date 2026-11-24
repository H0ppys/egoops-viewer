"""线程到 UI 的事件泵与状态栏（拆分自 app.py 1310-1341）"""

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


class EventsMixin:
    """EventsMixin：线程到 UI 的事件泵与状态栏（拆分自 app.py 1310-1341）"""
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
