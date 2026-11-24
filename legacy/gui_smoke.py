"""GUI 冒烟测试：能建窗口、能布局、不报错（不进入 mainloop）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk  # noqa: E402
from app import App  # noqa: E402

root = tk.Tk()
root.withdraw()          # 不真的弹窗打扰
app = App(root)
root.update_idletasks()
print("窗口标题:", root.title())
print("采集点表列:", app.tv_sites["columns"])
print("文件表列:", app.tv_files["columns"])
print("默认服务器:", app.ent_server.get())
root.destroy()
print("✅ GUI 构建正常")
