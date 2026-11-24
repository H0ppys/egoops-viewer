"""冒烟测试：能 import 新包全部模块 + 入口 --help 可执行（不弹任何 Tk 窗口）。

    python -X utf8 tests/smoke_test.py
"""
import importlib
import os
import pkgutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAIL = []


def step(name, fn):
    try:
        fn()
        print("  [OK]   %s" % name)
    except Exception as e:  # noqa: BLE001
        FAIL.append((name, repr(e)))
        print("  [FAIL] %s -> %r" % (name, e))


def import_all():
    import egoops_viewer
    mods = sorted(m.name for m in pkgutil.iter_modules(egoops_viewer.__path__))
    assert mods, "包目录为空"
    for name in mods:
        importlib.import_module("egoops_viewer." + name)
    print("       已 import %d 个子模块：%s" % (len(mods), ", ".join(mods)))


def check_app():
    from egoops_viewer.app import App, selftest
    methods = [n for n in dir(App) if not n.startswith("__") and callable(getattr(App, n))]
    assert len(methods) >= 100, "App 方法数异常：%d" % len(methods)
    assert callable(selftest), "selftest 不可调用"
    # 入口函数对象存在即可（不建窗口）
    import egoops_viewer.ui_v2 as v2
    assert callable(v2.App), "ui_v2.App 缺失"


def check_config():
    from egoops_viewer import config
    assert isinstance(config.APP_NAME, str) and config.APP_NAME
    assert isinstance(config.DEFAULT_SERVER, str) and config.DEFAULT_SERVER.startswith("http")
    assert callable(config.load_config) and callable(config.save_config)


def check_logic():
    from egoops_viewer.api_client import Api, ApiError, human_size  # noqa: F401
    from egoops_viewer import tls, address_parse, transcode_pc, extras
    assert callable(tls.context) and callable(tls.urlopen)
    assert callable(address_parse.parse) and callable(transcode_pc.codec_of)
    assert callable(extras.load_drafts) and callable(extras.check_site)


def check_cli():
    for entry in ("main.py", "main2.py"):
        p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, entry), "--help"],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert p.returncode == 0, "%s --help 退出码 %s\n%s" % (entry, p.returncode, p.stderr[-800:])
        assert "用法" in (p.stdout or ""), "%s --help 无输出" % entry


def main():
    print("egoops-viewer 冒烟测试：%s" % ROOT)
    step("import egoops_viewer 全部子模块", import_all)
    step("App 装配 / ui_v2 入口", check_app)
    step("config 常量与配置读写", check_config)
    step("逻辑层符号（api/tls/address/transcode/extras）", check_logic)
    step("入口 --help（main.py / main2.py）", check_cli)
    if FAIL:
        print("\n失败 %d 项：" % len(FAIL))
        for name, err in FAIL:
            print("  - %s: %s" % (name, err))
        return 1
    print("\n全部通过（未创建任何 Tk 窗口）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
