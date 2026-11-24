"""viewer/api.py 冒烟测试：登录 → 列表 → 详情 → 下载 → 校验大小"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api import Api, ApiError, human_size  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18090"

api = Api(BASE)
h = api.health()
print("health:", h)

api.login("查看器测试", invite="")
print("token:", api.token[:12] + "…")

sites = api.sites()
print("采集点:", len(sites))
for s in sites[:3]:
    print("  -", s["name"], s.get("file_count"), human_size(s.get("bytes", 0)))

target = next((s for s in sites if s.get("file_count")), None)
if not target:
    print("没有带文件的采集点，跳过下载")
    sys.exit(0)

detail = api.site(target["id"])
files = (detail.get("photos") or []) + (detail.get("videos") or [])
print("详情:", detail["name"], "文件", len(files))

f = files[0]
dest = os.path.join(os.environ.get("TEMP", "."), "viewer-test", f["filename"])
api.download("/files/" + f["id"], dest, progress=None)
size = os.path.getsize(dest)
print("下载:", dest, size, "字节 | 期望", f["size"], "| 一致", size == f["size"])
assert size == f["size"]
print("✅ viewer api 正常")
