"""EgoOps 登录态：用已保存的 cookie 静默续期，并在 EgoOps 上验证是否还活着。"""
import json
import os
import time

AUTH = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                    "egoops-viewer", "egoops_auth.json")
CHECK_URL = "https://mrobo.uav.meituan.com/egoops/api/v1/users/me"


def _load():
    with open(AUTH, encoding="utf-8") as f:
        return json.load(f)


def token_of(data=None):
    data = data or _load()
    for scope in ("session", "local"):
        for k, v in (data["storage"].get(scope) or {}).items():
            if v and k.startswith("oidc.user") and "access_token" in v:
                return json.loads(v)["access_token"]
    return ""


def alive(token):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(CHECK_URL)
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
        return True, j.get("display_name") or "已登录"
    except urllib.error.HTTPError as e:
        return False, "HTTP %s" % e.code
    except Exception as e:
        return False, str(e)


EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP = "http://127.0.0.1:9222"


def _kill_temp_edge():
    """关掉之前残留的临时登录窗口（只杀用 egoops-edge-prof 的那个）"""
    try:
        import subprocess
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
              "Where-Object { $_.CommandLine -like '*egoops-edge-prof*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=20)
    except Exception:
        pass


def _edge_with_cdp():
    """起一个带调试端口的 Edge（独立配置，不动日常浏览器），并把它置前"""
    import subprocess
    import urllib.request

    # 已经有可用的调试端口就直接用
    try:
        urllib.request.urlopen(CDP + "/json/version", timeout=2).read()
        return True
    except Exception:
        pass

    if not os.path.exists(EDGE):
        return False

    _kill_temp_edge()
    time.sleep(1)

    prof = os.path.join(os.environ.get("TEMP") or ".", "egoops-edge-prof")
    try:
        subprocess.Popen([EDGE,
                          "--remote-debugging-port=9222",
                          "--user-data-dir=" + prof,
                          "--no-first-run",
                          "--no-default-browser-check",
                          "--new-window",
                          "https://egoops.meituan.com/assignment"],
                         close_fds=True)
    except Exception:
        return False

    ok = False
    for _ in range(40):
        try:
            urllib.request.urlopen(CDP + "/json/version", timeout=2).read()
            ok = True
            break
        except Exception:
            time.sleep(1)
    if not ok:
        return False

    # 把窗口提到最前
    try:
        import ctypes
        u = ctypes.windll.user32
        for _ in range(10):
            hwnd = u.FindWindowW(None, "美团 M-EgoOps")
            if not hwnd:
                hwnd = u.FindWindowW(None, "Microsoft\u200b Edge")
            if hwnd:
                u.ShowWindow(hwnd, 9)
                u.SetForegroundWindow(hwnd)
                break
            time.sleep(0.5)
    except Exception:
        pass

    return True


def relogin(wait_seconds=300, log=print):
    """打开浏览器让用户登录一次，然后把 cookie/storage 抓下来"""
    from playwright.sync_api import sync_playwright

    if not _edge_with_cdp():
        return False, "起不来带调试端口的 Edge"

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        page = None
        for x in ctx.pages:
            if "meituan" in x.url:
                page = x
                break
        if page is None:
            page = ctx.new_page()
        page.goto("https://egoops.meituan.com/assignment", wait_until="domcontentloaded", timeout=60000)

        log("请在弹出的浏览器窗口里登录 EgoOps（手机验证码），最多等 %d 秒…" % wait_seconds)
        deadline = time.time() + wait_seconds
        storage = {"local": {}, "session": {}}
        while time.time() < deadline:
            try:
                for pg in ctx.pages:
                    if "egoops.meituan.com" not in pg.url:
                        continue
                    st = pg.evaluate("""() => {
                        const dump = s => { const o = {}; for (let i = 0; i < s.length; i++) { const k = s.key(i); o[k] = s.getItem(k); } return o; };
                        return { local: dump(localStorage), session: dump(sessionStorage) };
                    }""")
                    has_token = any("oidc.user" in k for k in (st.get("session") or {})) or \
                                any("oidc.user" in k for k in (st.get("local") or {}))
                    if has_token:
                        storage = st
                        page = pg
                        break
                else:
                    time.sleep(3)
                    continue
                break
            except Exception:
                time.sleep(3)
        else:
            return False, "等待超时，没拿到登录态（登录窗口还开着，可以再点一次登录）"

        if not storage.get("session") and not storage.get("local"):
            return False, "没拿到登录态"

        page.wait_for_timeout(1500)
        data = {
            "url": page.url,
            "cookies": ctx.cookies(),
            "storage": storage,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        ok, who = alive(token_of(data))
        if not ok:
            return False, "抓到的登录态校验失败（%s），没有覆盖原文件" % who

        os.makedirs(os.path.dirname(AUTH), exist_ok=True)
        with open(AUTH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True, "已保存登录态（%s）" % who


def refresh(wait_seconds=300, log=print):
    """先看保存的态还活着吗，死了就引导重新登录一次再抓"""
    if os.path.exists(AUTH):
        data = _load()
        ok, who = alive(token_of(data))
        if ok:
            data["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            data["verified"] = who
            with open(AUTH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            return True, "登录态有效（%s），已刷新" % who
        log("登录态失效（%s），需要重新登录" % who)
    return relogin(wait_seconds=wait_seconds, log=log)


if __name__ == "__main__":
    print(refresh())
