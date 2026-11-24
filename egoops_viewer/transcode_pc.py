"""电脑端转码：H.265(HEVC) → H.264，不用服务器 CPU。

ffmpeg 首次使用时自动下载到 %APPDATA%\\egoops-viewer\\ffmpeg.exe（约 80MB，只需一次）。
"""
import os
import shutil
import subprocess
import tempfile
import urllib.request

APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "egoops-viewer")
FFMPEG = os.path.join(APP_DIR, "ffmpeg.exe")
FFMPEG_URL = "https://registry.npmmirror.com/-/binary/ffmpeg-static/b6.0/ffmpeg-win32-x64.gz"


def ffmpeg_path(auto_download=True):
    if os.path.exists(FFMPEG):
        return FFMPEG
    local = shutil.which("ffmpeg")
    if local:
        return local
    if not auto_download:
        return None
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = FFMPEG + ".gz"
    urllib.request.urlretrieve(FFMPEG_URL, tmp)
    import gzip
    with gzip.open(tmp, "rb") as src, open(FFMPEG, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.remove(tmp)
    return FFMPEG


def codec_of(path):
    """返回小写编码名（hevc / h264 / …），失败返回空串"""
    exe = ffmpeg_path()
    if not exe:
        return ""
    try:
        p = subprocess.run([exe, "-hide_banner", "-i", path],
                           capture_output=True, text=True, timeout=60)
        text = (p.stderr or "").lower()
        for name in ("hevc", "h264", "av1", "vp9", "mpeg4"):
            if "video: " + name in text:
                return name
        return ""
    except Exception:
        return ""


def ensure_h264(path):
    """需要时转码，返回可直接上传的路径（可能是临时文件）"""
    codec = codec_of(path)
    if codec in ("h264", ""):
        return path
    exe = ffmpeg_path()
    if not exe:
        return path
    out = os.path.join(tempfile.gettempdir(), os.path.splitext(os.path.basename(path))[0] + ".h264.mp4")
    subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out],
                   check=True, timeout=1800)
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python transcode_pc.py <视频文件>")
        raise SystemExit(1)
    src = sys.argv[1]
    print("编码:", codec_of(src) or "未知")
    out = ensure_h264(src)
    print("输出:", out, os.path.getsize(out) if os.path.exists(out) else "-")
