"""把查看器里选中的采集点，自动填到 EgoOps「申请采集点」表单里。

登录态怎么来：
    直接用你电脑上 Edge 的**真实配置文件**启动浏览器（不是新建干净环境），
    所以只要这台电脑的 Edge 登录过 EgoOps，打开就是登录状态 —— 换电脑也一样，
    在新电脑上用 Edge 登录一次即可，不需要手工拷 token / cookie。

前提：运行时 Edge 必须全部关闭（同一个配置文件不能两个进程同时用）。
"""
import json
import os
import sys
import time

URL = "https://egoops.meituan.com/assignment"
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "egoops_fill.log")


def edge_profile_dir():
    """Edge 默认用户数据目录"""
    local = os.environ.get("LOCALAPPDATA", "")
    for name in ("Default", "Profile 1", "Profile 2"):
        p = os.path.join(local, "Microsoft", "Edge", "User Data", name)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "Preferences")):
            return p
    return os.path.join(local, "Microsoft", "Edge", "User Data", "Default")


def _log_factory(cb):
    def log(msg):
        line = time.strftime("%H:%M:%S ") + str(msg)
        print(line, flush=True)
        try:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        if cb:
            try:
                cb(str(msg))
            except Exception:
                pass
    return log


def _dump_form(pg, log):
    info = pg.evaluate("""() => {
        const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        return [...document.querySelectorAll('input,textarea,select,button')].filter(vis).map(el => ({
            tag: el.tagName.toLowerCase(), type: el.type || '',
            placeholder: el.placeholder || '',
            label: (el.closest('label')?.innerText || '').trim().slice(0, 40),
            text: (el.innerText || '').trim().slice(0, 40),
        }));
    }""")
    log("=== 表单可见控件 %d 个 ===" % len(info))
    for i, x in enumerate(info):
        log("  [%d] %s type=%s placeholder=%r label=%r text=%r"
            % (i, x["tag"], x["type"], x["placeholder"], x["label"], x["text"]))
    return info


def fill_address(pg, address, log):
    """省/市/区 级联下拉 + 街道门牌号"""
    from address_parse import parse
    parts = parse(address or "")
    if not parts.get("ok"):
        log("地址拆不开（%s），需要手动选省市区：%s" % (parts.get("note"), address))
        return False
    try:
        pg.get_by_text("请选择省、市、区（县）", exact=False).first.click(timeout=6000)
        pg.wait_for_timeout(800)
        for name in (parts["province"], parts["city"], parts["district"]):
            btn = pg.get_by_role("button", name=name, exact=True)
            if not btn.count():
                log("地址级联里没找到「%s」" % name)
                return False
            btn.first.click()
            pg.wait_for_timeout(700)
        log("✓ 省市区 = %s %s %s" % (parts["province"], parts["city"], parts["district"]))
    except Exception as e:
        log("选省市区失败：%s" % e)
        return False
    try:
        street = pg.get_by_placeholder("街道、门牌号、园区或楼栋").first
        street.fill(parts["street"])
        log("✓ 街道 = %s" % parts["street"])
    except Exception as e:
        log("填街道失败：%s" % e)
    return True


def _fill_by_label(pg, labels, value, log, tag):
    for lb in labels:
        try:
            box = pg.get_by_label(lb, exact=False)
            if box.count():
                box.first.fill(str(value))
                log("✓ %s = %s（按标签「%s」）" % (tag, value, lb))
                return True
        except Exception:
            continue
    return False


AUTH_FILE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                         "egoops-viewer", "egoops_auth.json")


def _seed_script():
    """把保存的 localStorage / sessionStorage 在页面加载前写回去"""
    if not os.path.exists(AUTH_FILE):
        return None, None
    data = json.load(open(AUTH_FILE, encoding="utf-8"))
    storage = data.get("storage") or {}
    seed = {"local": storage.get("local") or {}, "session": storage.get("session") or {}}
    script = """
    (() => {
      const seed = %s;
      try {
        for (const [k, v] of Object.entries(seed.local || {})) localStorage.setItem(k, v);
        for (const [k, v] of Object.entries(seed.session || {})) sessionStorage.setItem(k, v);
      } catch (e) {}
    })();
    """ % json.dumps(seed, ensure_ascii=False)
    return data.get("cookies") or [], script


def run_fill(site, fields=None, on_log=None, headless=False, dump=False, wait_seconds=900, profile=None):
    fields = set(fields or ["name", "address", "area", "scene", "note"])
    log = _log_factory(on_log)
    log("采集点：%s | 面积 %s | 场景 %s | 任务 %d 个"
        % (site.get("name"), site.get("area"), site.get("scene_label"), len(site.get("tasks") or [])))

    prof = profile or edge_profile_dir()
    log("使用 Edge 配置：%s" % prof)

    from playwright.sync_api import sync_playwright

    cookies, script = _seed_script()
    with sync_playwright() as p:
        try:
            if cookies is not None:
                browser = p.chromium.launch(channel="msedge", headless=headless)
                ctx = browser.new_context(no_viewport=False)
                try:
                    ctx.add_cookies(cookies)
                except Exception as e:
                    log("注 cookie 失败（继续试）：%s" % e)
                if script:
                    ctx.add_init_script(script)
                log("使用已保存的登录态（免登录）")
            else:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=prof,
                    channel="msedge",
                    headless=headless,
                    no_viewport=True,
                    args=["--start-maximized"],
                )
        except Exception as e:
            msg = str(e)
            if "ProcessSingleton" in msg or "already" in msg.lower() or "locked" in msg.lower():
                log("Edge 正在运行，无法使用它的登录态。请先完全退出 Edge（任务栏右键退出），再点一次。")
            else:
                log("启动 Edge 失败：%s" % msg)
            return {"ok": False, "reason": "edge-launch", "detail": msg[:300]}

        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            pg.goto(URL, wait_until="domcontentloaded", timeout=90000)
            pg.wait_for_timeout(6000)

            if "login" in pg.url or "sso" in pg.url:
                log("还没登录：请在这个浏览器窗口里登录一次（美团 SSO），登录后脚本自动继续，最多等 5 分钟")
                try:
                    pg.wait_for_url(lambda u: ("login" not in u and "sso" not in u), timeout=300000)
                except Exception:
                    log("等待登录超时")
                    return {"ok": False, "reason": "login-timeout"}
                pg.wait_for_timeout(6000)

            log("已打开：%s" % pg.url)

            clicked = False
            try:
                loc = pg.get_by_text("申请采集点", exact=True)
                if loc.count():
                    loc.first.click(timeout=8000)
                    clicked = True
                    log("已点击「申请采集点」")
            except Exception as e:
                log("点击失败：%s" % e)
            if not clicked:
                log("没找到「申请采集点」按钮（可能无权限或页面结构变了）")
            pg.wait_for_timeout(4000)

            _dump_form(pg, log)
            if dump:
                log("dump 模式：不填表，窗口保持 60 秒")
                pg.wait_for_timeout(60000)
                return {"ok": True, "dump": True}

            filled = []
            skipped = []
            if "name" in fields:
                if site.get("name") and _fill_by_label(pg, ["采集点名称", "名称", "门店名称"], site["name"], log, "名称"):
                    filled.append("名称")
                else:
                    skipped.append("名称")
            else:
                skipped.append("名称")
            if "address" in fields:
                if site.get("address") and fill_address(pg, site["address"], log):
                    filled.append("地址")
                else:
                    skipped.append("地址")
            else:
                skipped.append("地址")
            if "area" in fields:
                if site.get("area") and _fill_by_label(pg, ["面积", "场地面积"], site["area"], log, "面积"):
                    filled.append("面积")
                else:
                    skipped.append("面积")
            else:
                skipped.append("面积")
            if "note" in fields:
                if site.get("note") and _fill_by_label(pg, ["采集点描述", "描述", "备注"], site["note"], log, "描述"):
                    filled.append("描述")
                else:
                    skipped.append("描述")
            else:
                skipped.append("描述")
            if "scene" not in fields:
                skipped.append("场景")
            if site.get("scene_label") and "scene" in fields:
                try:
                    pg.get_by_text("采集场景分类", exact=False).first.click(timeout=5000)
                    pg.wait_for_timeout(1200)
                    pg.get_by_text(site["scene_label"], exact=False).first.click(timeout=5000)
                    filled.append("场景")
                    log("✓ 场景 = %s" % site["scene_label"])
                except Exception as e:
                    log("场景需要手动选：%s" % e)

            log("已填写：%s" % ("、".join(filled) if filled else "（没匹配到输入框，见上面的控件清单）"))
            log("跳过：%s" % ("、".join(skipped) if skipped else "无"))
            log("请在窗口里核对、补媒体文件，然后手动提交。窗口保持 %d 分钟。" % (wait_seconds // 60))
            pg.wait_for_timeout(wait_seconds * 1000)
            return {"ok": True, "filled": filled}
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()
    with open(args.data, encoding="utf-8") as f:
        site = json.load(f)
    try:
        run_fill(site, headless=args.headless, dump=args.dump, profile=args.profile)
    except Exception as e:
        _log_factory(None)("出错：%r" % (e,))
        sys.exit(1)


if __name__ == "__main__":
    main()
