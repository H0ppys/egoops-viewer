"""查看器附加能力：草稿去重记录、批次建草稿、质检、导出。"""
import csv
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from . import tls

APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "egoops-viewer")
DRAFTS = os.path.join(APP_DIR, "drafts.json")


# ---------------------------------------------------------------- 草稿记录

def load_drafts():
    try:
        with open(DRAFTS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_drafts(data):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = DRAFTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DRAFTS)


def remember(site_id, task_set_id, name=""):
    d = load_drafts()
    d[site_id] = {"task_set_id": task_set_id, "name": name, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_drafts(d)


def forget(site_id):
    d = load_drafts()
    if site_id in d:
        d.pop(site_id)
        save_drafts(d)


def draft_of(site_id):
    return load_drafts().get(site_id)


# ---------------------------------------------------------------- 质检

def _ffmpeg():
    exe = os.path.join(APP_DIR, "ffmpeg.exe")
    return exe if os.path.exists(exe) else None


def photo_metrics(path):
    """清晰度(拉普拉斯方差) / 平均亮度 / 8x8 灰度指纹"""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return None
    try:
        img = Image.open(path).convert("L")
        img.thumbnail((800, 800))
        arr = np.asarray(img, dtype=np.float32)
        if arr.size == 0:
            return None
        k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        h, w = arr.shape
        lap = np.zeros((max(h - 2, 1), max(w - 2, 1)), dtype=np.float32)
        if h > 2 and w > 2:
            lap = (arr[1:-1, :-2] * k[1, 0] + arr[1:-1, 1:-1] * k[1, 1] + arr[1:-1, 2:] * k[1, 2]
                   + arr[:-2, 1:-1] * k[0, 1] + arr[2:, 1:-1] * k[2, 1])
        blur = float(lap.var())
        bright = float(arr.mean())
        small = Image.open(path).convert("L").resize((17, 16))
        a = np.asarray(small, dtype=np.int16)
        bits = "".join("1" if a[y][x] > a[y][x + 1] else "0" for y in range(16) for x in range(16))
        return {"blur": blur, "bright": bright, "hash": bits}
    except Exception:
        return None


def video_metrics(path):
    exe = _ffmpeg()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-hide_banner", "-i", path],
                             capture_output=True, text=True, timeout=120).stderr
        import re as _re
        dur = 0.0
        w = h = 0
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Duration:"):
                part = line.split("Duration:")[1].split(",")[0].strip()
                try:
                    hh, mm, ss = part.split(":")
                    dur = int(hh) * 3600 + int(mm) * 60 + float(ss)
                except Exception:
                    pass
            if line.startswith("Stream") and "Video:" in line:
                m = _re.search(r"(\d{2,5})x(\d{2,5})", line)   # 只认 1280x720 这种，避开 0x31637668
                if m:
                    w, h = int(m.group(1)), int(m.group(2))
        return {"duration": dur, "width": w, "height": h}
    except Exception:
        return None


def hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def check_site(site, files, download, progress=None, log=print):
    """返回 issues: [{file, kind, reason, level}]"""
    issues = []
    photos = []
    total = len(files)
    for i, f in enumerate(files, 1):
        if progress:
            progress(int(100 * i / max(total, 1)), "质检 %d/%d %s" % (i, total, f.get("filename", "")))
        try:
            path = download(f)
        except Exception as e:
            issues.append({"file": f, "kind": "下载失败", "reason": str(e), "level": "error"})
            continue
        if f.get("kind") == "photo":
            m = photo_metrics(path)
            if not m:
                continue
            if m["blur"] < 80:
                issues.append({"file": f, "kind": "模糊", "reason": "清晰度 %.0f（<80）" % m["blur"], "level": "error"})
            elif m["blur"] < 180:
                issues.append({"file": f, "kind": "偏糊", "reason": "清晰度 %.0f（<180）" % m["blur"], "level": "warn"})
            if m["bright"] < 50:
                issues.append({"file": f, "kind": "过暗", "reason": "亮度 %.0f（<50）" % m["bright"], "level": "error"})
            elif m["bright"] > 220:
                issues.append({"file": f, "kind": "过曝", "reason": "亮度 %.0f（>220）" % m["bright"], "level": "warn"})
            f["_blur"] = m["blur"]
            photos.append((f, m["hash"], f.get("task_id") or ""))
        else:
            m = video_metrics(path)
            if not m:
                continue
            if m["duration"] < 2.0:
                issues.append({"file": f, "kind": "视频过短", "reason": "%.1f 秒（<2 秒）" % m["duration"], "level": "error"})
            if m["width"] and m["width"] < 640:
                issues.append({"file": f, "kind": "分辨率低", "reason": "%dx%d" % (m["width"], m["height"]), "level": "warn"})

    # 重复图：只比同一个任务里的照片，距离 <= 3 才算（同场景不同角度不算）
    for i in range(len(photos)):
        for j in range(i + 1, len(photos)):
            fi, hi, ti = photos[i]
            fj, hj, tj = photos[j]
            if ti != tj:
                continue
            if fi.get("id") == fj.get("id"):
                continue
            bi = max(fi.get("_blur", 0), 0)
            bj = max(fj.get("_blur", 0), 0)
            if ti and hamming(hi, hj) <= 6 and abs(bi - bj) <= max(40, 0.3 * max(bi, bj)):
                issues.append({"file": fj, "kind": "疑似重复",
                               "reason": "与 %s 几乎相同（同一任务内）" % fi.get("filename", ""),
                               "level": "warn"})
    return issues


# ---------------------------------------------------------------- 导出

def export_sites_csv(rows, path):
    """rows: [{name, vendor, invite, address, area, scene, by, created, tasks, photos, videos, bytes, draft}]"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["门店", "厂商", "邀请码", "现场地址", "面积㎡", "场景分类",
                    "采集员", "采集时间", "任务数", "照片数", "视频数", "大小MB", "EgoOps草稿"])
        for r in rows:
            w.writerow([
                r.get("name", ""), r.get("vendor", ""), r.get("invite", ""), r.get("address", ""),
                r.get("area") or "", r.get("scene", ""), r.get("by", ""), r.get("created", ""),
                r.get("tasks", 0), r.get("photos", 0), r.get("videos", 0),
                round((r.get("bytes") or 0) / 1048576, 1), r.get("draft", ""),
            ])
    return path


def fetch_to_temp(server, token, f, subdir="qc"):
    d = os.path.join(tempfile.gettempdir(), "egoops_" + subdir)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, (f.get("id") or "x")[:8] + "_" + (f.get("filename") or "f"))
    if os.path.exists(path) and os.path.getsize(path) == f.get("size"):
        return path
    req = urllib.request.Request(server.rstrip("/") + "/files/" + f["id"])
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with tls.urlopen(req, timeout=300) as r, open(path, "wb") as out:
        out.write(r.read())
    return path
