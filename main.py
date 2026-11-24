"""采集数据查看器 —— 程序入口（等价原 viewer/app.py 的 __main__ 启动方式）

    python main.py              # 启动 GUI（原 app.py 的 main()）
    python main.py --selftest   # 无界面自检，写到 %TEMP%/egoops-viewer-selftest.txt
    python main.py --help       # 打印本说明
"""
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from egoops_viewer.app import App, selftest  # noqa: E402

USAGE = """采集数据查看器 v16（egoops-viewer）

用法：
  python main.py              启动图形界面（等价原 app.py）
  python main.py --selftest   无界面自检：建窗口、布局、读服务器地址，结果写
                              %TEMP%/egoops-viewer-selftest.txt
  python main.py --help       显示本说明

界面入口：
  左：采集点列表（门店/采集员/时间/场景/面积/任务数/文件数/大小），最左列可勾选
  右：文件列表（按区域/任务分组）+ 照片预览
  底：下载 / 删除 / 申请采集点（自动填表）三行操作

配置文件：%APPDATA%/egoops-viewer/config.json（见 config.example.json）
"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    if "--selftest" in argv:
        selftest()
        out = os.path.join(os.environ.get("TEMP", "."), "egoops-viewer-selftest.txt")
        print("selftest -> %s" % out)
        return 0
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
