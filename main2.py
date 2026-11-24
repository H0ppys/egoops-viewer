"""采集数据查看器 v2（主从布局版）—— 程序入口，等价原 viewer/app2.py 的 __main__

    python main2.py             # 启动 v2 界面（左采集点 / 右任务+素材墙）
    python main2.py --help      # 打印本说明
"""
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from egoops_viewer.ui_v2 import App as AppV2  # noqa: E402

USAGE = """采集数据查看器 v2.0（主从布局）

用法：
  python main2.py            启动 v2 界面（等价原 app2.py）
  python main2.py --help     显示本说明

说明：
  v2 与 v16（main.py）共用同一套逻辑层（api_client / extras / tls / egoops_*），
  只是界面组织不同，发布时二选一打包。
"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    root = tk.Tk()
    AppV2(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
