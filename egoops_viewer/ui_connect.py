"""连接服务器、刷新采集点、厂商/系统映射、草稿状态刷新（拆分自 app.py 1342-1628）"""

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


class ConnectMixin:
    """ConnectMixin：连接服务器、刷新采集点、厂商/系统映射、草稿状态刷新（拆分自 app.py 1342-1628）"""
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
