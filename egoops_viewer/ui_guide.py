"""步骤引导条与四步点击跳转（拆分自 app.py 425-457）"""

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


class GuideMixin:
    """GuideMixin：步骤引导条与四步点击跳转（拆分自 app.py 425-457）"""
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
