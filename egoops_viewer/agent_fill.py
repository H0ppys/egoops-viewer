"""用大模型（或模板）补全「申请采集点」里缺失的内容。

采集点级：采集点描述
任务级：任务描述、预计时长（小时）、SOP 步骤

配置：%APPDATA%\\egoops-viewer\\config.json
    "llm": {"base": "https://api.deepseek.com/v1", "model": "deepseek-chat", "key": "sk-..."}
"""
import json
import os
import urllib.error
import urllib.request


VISION_MODEL_DEFAULT = "doubao-seed-2-1-pro-260915"


def vision_model():
    cfg = load_llm_config()
    return (cfg.get("vision_model") or "").strip() or VISION_MODEL_DEFAULT


def load_llm_config():
    path = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                        "egoops-viewer", "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("llm") or {}
    except Exception:
        return {}


def _areas(site):
    out = []
    for t in site.get("tasks") or []:
        a = (t.get("area") or "").strip()
        if a and a not in out:
            out.append(a)
    return out


# ---------------------------------------------------------------- 采集点描述

def template_description(site):
    name = site.get("name") or "该门店"
    scene = (site.get("scene_label") or "").split("/")[-1].strip() or "门店"
    area = site.get("area")
    areas = _areas(site)
    s = "%s 为%s场景，%s。" % (name, scene, ("场地面积约 %s 平方米" % int(float(area))) if area else "场地面积未测")
    s += ("现场包含%s等区域，" % "、".join(areas[:4])) if areas else "现场已完成门头与全景采集，"
    s += "可开展清洁、整理、家电操作等具身智能动作采集，支持第一视角与手部特写同步录制。"
    s += "注意事项：拍摄前确认光线充足、通道畅通，避开顾客与隐私区域。"
    return s


def build_site_prompt(site):
    return (
        "你在帮数据采集公司填写美团 EgoOps「申请采集点」表单的『采集点描述』。\n"
        "写 80~150 字中文，说明：1) 业态与现场环境；2) 可采集的动作/场景；3) 注意事项。\n"
        "只输出描述正文，不要标题、不要分点。\n\n"
        "门店名称：%s\n场景分类：%s\n面积：%s 平方米\n区域：%s\n"
        % (site.get("name") or "", site.get("scene_label") or site.get("scene") or "",
           site.get("area") or "未填", "、".join(_areas(site)) or "未填")
    )


# ---------------------------------------------------------------- 任务级

def template_task_content(site, task):
    area = (task.get("area") or "").strip()
    name = (task.get("name") or "").strip() or "作业任务"
    scene = (site.get("scene_label") or "").split("/")[-1].strip() or "门店"
    desc = ("%s区域，作业场景为%s。执行范围：%s 内的%s；关键动作按现场实际执行顺序完成；"
            "拍摄时保持第一视角稳定，注意避开顾客与隐私物品。" % (
                area or "门店", scene, area or "门店", name))
    if "门头" in name or "全景" in name:
        desc = ("采集点门头与整体环境。执行范围：门店入口与店内公共区域；"
                "关键动作：正对门头拍摄招牌与入口、站店内中心缓慢环拍全景；"
                "注意事项：光线充足、招牌完整、避开顾客正脸。")
    hours = 1
    sop = ["准备设备并确认光线", "按提示完成拍摄", "检查画面清晰完整", "上传素材"]
    return {"name": name, "desc": desc, "hours": hours, "sop": [s for s in sop if s]}


def build_task_prompt(site, task):
    scene = (site.get("scene_label") or site.get("scene") or "").replace("/", "·")
    return (
        "你在帮数据采集公司填写美团 EgoOps「申请采集点」里每个『任务』的三项内容。\n"
        "这个任务是采集员拿着手机/头戴设备，在指定区域里做一遍动作并拍下来，用于具身智能训练数据。\n\n"
        "要求：\n"
        "1. desc：60~110 字，写清 作业场景、执行范围（哪个区域）、关键动作、注意事项；\n"
        "2. hours：按实际耗时估算（0.5~3 之间的数字）；\n"
        "3. sop：5~7 条，按真实执行顺序，每条 8~18 字，必须动词开头、具体可执行，"
        "要包含『进入区域』『调整视角/构图』『执行任务动作本身』『补拍细节或环绕』『检查画面』『结束并上传』这类环节；"
        "不要写空话（如“按提示完成拍摄”）。\n\n"
        "只输出 JSON，不要 markdown 代码块：\n"
        '{"desc": "...", "hours": 1, "sop": ["...", "..."]}\n\n'
        "门店：%s\n场景分类：%s\n场地面积：%s 平方米\n"
        "任务名称：%s\n所属区域：%s\n"
        % (site.get("name") or "", scene or "未填", site.get("area") or "未填",
           task.get("name") or "", (task.get("area") or "未填"))
    )


# ---------------------------------------------------------------- 调用

def _chat(prompt, timeout=60):
    cfg = load_llm_config()
    key = (cfg.get("key") or "").strip()
    if not key:
        return None
    base = (cfg.get("base") or "https://api.deepseek.com/v1").rstrip("/")
    model = cfg.get("model") or "deepseek-chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的数据采集项目助理，只输出要求的内容。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
    }
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def _extract_json(text):
    t = text.strip()
    if "```" in t:
        parts = t.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            if part.startswith("{"):
                t = part
                break
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        t = t[start:end + 1]
    return json.loads(t)


def _shrink(path, max_px=768, quality=78):
    """压成小图再送模型，省 token"""
    import base64
    import os as _os
    import tempfile
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        img.thumbnail((max_px, max_px))
        out = _os.path.join(tempfile.gettempdir(), "egoops_llm_" + _os.path.basename(path) + ".jpg")
        img.save(out, quality=quality)
        with open(out, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        try:
            import base64 as b
            with open(path, "rb") as f:
                return b.b64encode(f.read()).decode()
        except Exception:
            return ""


def _video_frames(path, count=2):
    """从视频里抽几帧，返回临时图片路径"""
    import os as _os
    import subprocess
    import tempfile
    exe = _os.path.join(_os.environ.get("APPDATA") or "", "egoops-viewer", "ffmpeg.exe")
    if not _os.path.exists(exe):
        return []
    out_dir = _os.path.join(tempfile.gettempdir(), "egoops_frames")
    _os.makedirs(out_dir, exist_ok=True)
    base = _os.path.splitext(_os.path.basename(path))[0]
    frames = []
    for i in range(count):
        t = 0.5 + i * 1.0
        out = _os.path.join(out_dir, "%s_%d.jpg" % (base, i))
        try:
            subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t),
                            "-i", path, "-frames:v", "1", "-vf", "scale=768:-2", out],
                           check=False, timeout=60)
            if _os.path.exists(out) and _os.path.getsize(out) > 1024:
                frames.append(out)
        except Exception:
            pass
    return frames


def build_media_prompt(site, task):
    scene = (site.get("scene_label") or site.get("scene") or "").replace("/", "·")
    return (
        "下面是这家店拍的照片/视频截帧。请先看清楚画面里到底有什么（设备、物品、空间、人在做什么），"
        "再为这个采集任务写三样东西。\n\n"
        "要求：\n"
        "1. desc：60~110 字，要写**画面里真实看到的东西**（具体物件、位置），不要套话；\n"
        "2. hours：按实际耗时估算，0.5~3 的数字；\n"
        "3. sop：5~7 条，按真实执行顺序，每条 8~18 字，动词开头，"
        "必须和画面里出现的东西对应（比如画面里是货架就写走到货架前，是机器就写操作机器）；\n"
        "4. seen：一句话描述你从画面里看到了什么。\n\n"
        "只输出 JSON，不要代码块：\n"
        '{"seen": "...", "desc": "...", "hours": 1, "sop": ["...", "..."]}\n\n'
        "门店：%s\n场景分类：%s\n任务名称：%s\n所属区域：%s\n"
        % (site.get("name") or "", scene or "未填", task.get("name") or "", task.get("area") or "未填")
    )


def _chat_vision(prompt, images, timeout=120):
    cfg = load_llm_config()
    key = (cfg.get("key") or "").strip()
    if not key or not images:
        return None
    base = (cfg.get("base") or "").rstrip("/")
    model = vision_model()
    content = [{"type": "text", "text": prompt}]
    for b64 in images:
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}})
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一名具身智能数据采集项目的执行导演，看清画面再下笔，只输出要求的 JSON。"},
            {"role": "user", "content": content},
        ],
        "temperature": 0.5,
    }
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def _name_from_steps(seen, desc, steps, task):
    """根据画面内容和步骤反推一个 8~14 字任务名；纯文本调用，快且便宜"""
    try:
        prompt = (
            "下面是一个采集任务看到的画面和要做的事。请起一个任务名称：8~14 个汉字，动宾结构，"
            "要概括这个任务到底在做什么，不要用「拍摄」「采集」「操作过程」这类空泛词。\n"
            "只输出名称本身，不要引号、不要解释、不要编号。\n\n"
            "画面：%s\n内容：%s\n步骤：%s\n原任务名：%s"
            % (seen or "", desc or "", "；".join(steps[:6]), task.get("name") or "")
        )
        text = _chat(prompt, timeout=45)
        if not text:
            return ""
        name = text.strip().strip('"').strip("“”").splitlines()[0].strip()
        name = name.replace("任务名称：", "").replace("名称：", "").strip("。 ，,")
        return name[:20]
    except Exception:
        return ""


def generate_task_content_from_media(site, task, photo_paths, video_paths):
    """看素材写 SOP。素材读不到就退回纯文本。返回 (content, 来源)"""
    images = []
    for p in photo_paths[:4]:
        b = _shrink(p)
        if b:
            images.append(b)
    for v in video_paths[:2]:
        for fp in _video_frames(v, 2)[:2]:
            b = _shrink(fp)
            if b:
                images.append(b)
    if not images:
        return generate_task_content(site, task)

    try:
        raw = _chat_vision(build_media_prompt(site, task), images[:6])
        if raw:
            obj = _extract_json(raw)
            sop = [str(x).strip() for x in (obj.get("sop") or []) if str(x).strip()]
            if sop:
                name = str(obj.get("name") or "").strip()
                if not name:
                    name = _name_from_steps(obj.get("seen"), obj.get("desc"), sop, task)
                return {
                    "name": name,
                    "desc": str(obj.get("desc") or "").strip(),
                    "hours": float(obj.get("hours") or 1),
                    "sop": sop,
                    "seen": str(obj.get("seen") or "").strip(),
                }, "vision"
    except Exception:
        pass
    return generate_task_content(site, task)


def generate_description(site):
    """返回 (描述, 来源)"""
    try:
        text = _chat(build_site_prompt(site))
        if text:
            return text, "llm"
    except Exception:
        pass
    return template_description(site), "template"


def generate_task_content(site, task):
    """返回 ({desc, hours, sop}, 来源)"""
    try:
        raw = _chat(build_task_prompt(site, task))
        if raw:
            obj = _extract_json(raw)
            return {
                "desc": str(obj.get("desc") or "").strip(),
                "hours": float(obj.get("hours") or 1),
                "sop": [str(x).strip() for x in (obj.get("sop") or []) if str(x).strip()],
            }, "llm"
    except Exception:
        pass
    return template_task_content(site, task), "template"


if __name__ == "__main__":
    site = {
        "name": "美宜佳", "scene_label": "餐馆 / 餐厅", "area": 85,
        "tasks": [{"area": "", "name": "采集点-门头与全景"},
                  {"area": "饮料区", "name": "捡垃圾"}],
    }
    d, src = generate_description(site)
    print("[采集点描述/%s] %s" % (src, d))
    for t in site["tasks"]:
        c, s2 = generate_task_content(site, t)
        print("\n[任务 %s/%s] hours=%s" % ((t.get("area") or "-"), t["name"], c["hours"]))
        print("  描述:", c["desc"])
        print("  SOP:", " / ".join(c["sop"]))
