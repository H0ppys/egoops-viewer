"""采集数据服务器访问层（只用标准库，便于打包成 exe）。"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from . import tls


class ApiError(Exception):
    def __init__(self, message, status=None, detail=None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class Api:
    def __init__(self, base, token=""):
        self.base = base.rstrip("/")
        self.token = token

    # ---------- 基础请求 ----------
    def _request(self, method, path, body=None, timeout=30, headers=None):
        url = self.base + path
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("Accept", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with tls.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            msg, detail = "HTTP %s" % e.code, text
            try:
                err = json.loads(text).get("error") or {}
                msg = err.get("message") or msg
                detail = err.get("detail")
                if isinstance(detail, list):
                    detail = "；".join(str(x) for x in detail)
            except Exception:
                pass
            raise ApiError(msg, e.code, detail) from None
        except urllib.error.URLError as e:
            raise ApiError("连不上服务器：%s" % e.reason) from None
        except OSError as e:
            raise ApiError("网络错误：%s" % e) from None
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    # ---------- 接口 ----------
    def health(self):
        return self._request("GET", "/api/health", timeout=8)

    def login(self, name, phone="", invite=""):
        r = self._request("POST", "/api/auth/login", {"name": name, "phone": phone, "invite": invite})
        self.token = r.get("token", "")
        return r

    def sites(self, vendor=""):
        q = ("?vendor=" + urllib.parse.quote(vendor)) if vendor else ""
        return self._request("GET", "/api/sites" + q).get("items", [])

    def invites(self, admin_key):
        return self._request("GET", "/api/invites", headers={"x-admin-key": admin_key}, timeout=10).get("items", [])

    def add_invite(self, code, vendor, note, admin_key):
        return self._request("POST", "/api/invites", {"code": code, "vendor": vendor, "note": note},
                             headers={"x-admin-key": admin_key}, timeout=10)

    def del_invite(self, code, admin_key):
        return self._request("DELETE", "/api/invites?code=" + urllib.parse.quote(code),
                             headers={"x-admin-key": admin_key}, timeout=10)

    def vendor_systems(self):
        return self._request("GET", "/api/vendor-systems", timeout=10).get("items", {})

    def vendor_names(self):
        return self._request("GET", "/api/vendor-names", timeout=10).get("items", {})

    def vendors(self):
        return self._request("GET", "/api/vendors", timeout=10).get("items", [])

    def site(self, site_id):
        return self._request("GET", "/api/sites/" + urllib.parse.quote(site_id))

    # ---------- 邀请码管理（需管理口令） ----------
    def invite_get(self, admin_key):
        return self._request("GET", "/api/invite", headers={"x-admin-key": admin_key}, timeout=10)

    def invite_generate(self, admin_key):
        return self._request("POST", "/api/invite", {"generate": True}, headers={"x-admin-key": admin_key}, timeout=10)

    def invite_disable(self, admin_key):
        return self._request("POST", "/api/invite", {"code": ""}, headers={"x-admin-key": admin_key}, timeout=10)

    # ---------- 删除 ----------
    def delete_site(self, site_id):
        return self._request("DELETE", "/api/sites/" + urllib.parse.quote(site_id), timeout=30)

    def delete_file(self, file_id):
        return self._request("DELETE", "/api/files/" + urllib.parse.quote(file_id), timeout=30)

    def file_url(self, url):
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return self.base + url

    def download(self, url, dest_path, progress=None, chunk=256 * 1024):
        """流式下载到本地文件，progress(已下载, 总大小)"""
        full = self.file_url(url)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        req = urllib.request.Request(full)
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        with tls.urlopen(req, timeout=600) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            tmp = dest_path + ".part"
            with open(tmp, "wb") as f:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    done += len(buf)
                    if progress:
                        progress(done, total)
            os.replace(tmp, dest_path)
        return dest_path


def human_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024
    return "%.1f GB" % n
