"""默认配置与本地配置文件读写（拆分自 app.py 20-38）

服务器地址、APP 名/版本、%APPDATA%/egoops-viewer/config.json 的读写。
"""

import json
import os

APP_VER = "v16"
APP_NAME = "采集数据查看器"
DEFAULT_SERVER = "http://123.207.6.210/relay"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "egoops-viewer")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
