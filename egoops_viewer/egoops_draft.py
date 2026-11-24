"""一条龙：采集数据 → EgoOps 草稿（建草稿、填字段、传素材、写 SOP），不提交审核。

流程：
    1. allocate-draft                     建空草稿
    2. PATCH task-sets/{id}               名称 / 现场地址 / 场景 / 描述（大模型写）
    3. tasks/allocate-draft               建任务（已有就复用）
    4. 下载素材 → 视频 HEVC 转 H.264 → 传平台 → complete
    5. PATCH tasks/{id}                   任务名 / 描述 / 时长 / SOP + 挂素材
不调用任何提交接口，草稿停在 draft 状态。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from address_parse import parse as parse_addr          # noqa: E402
from agent_fill import (generate_description, generate_task_content,  # noqa: E402
                        generate_task_content_from_media)
from transcode_pc import ensure_h264, codec_of
import tls         # noqa: E402

API = "https://mrobo.uav.meituan.com/egoops"
AUTH = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                    "egoops-viewer", "egoops_auth.json")


class DraftError(Exception):
    pass


def _token():
    if not os.path.exists(AUTH):
        raise DraftError("没有登录态文件，请先点「设置 → 大模型/登录」或在 Edge 登录一次 EgoOps")
    data = json.load(open(AUTH, encoding="utf-8"))
    for scope in ("session", "local"):
        for k, v in (data["storage"].get(scope) or {}).items():
            if v and k.startswith("oidc.user") and "access_token" in v:
                return json.loads(v)["access_token"]
    raise DraftError("登录态里没有 access_token，请重新登录 EgoOps")


def _api(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + (token or _token()))
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        if e.code in (401, 403):
            raise DraftError("EgoOps 登录态失效（%s），请重新登录" % e.code) from None
        raise DraftError("%s %s -> %s %s" % (method, path, e.code, detail)) from None
    return json.loads(txt) if txt else {}


def _real_task(site):
    """跳过「采集点-门头与全景」这种采集点级占位任务"""
    tasks = site.get("tasks") or []
    for t in tasks:
        if (t.get("name") or "") != "采集点-门头与全景":
            return t
    return tasks[-1] if tasks else {}


def _label(task):
    area = (task.get("area") or "").strip()
    return (area + " ") if area else "" + (task.get("name") or "")


def create_draft(site, relay_files=None, log=print, progress=None, token=None):
    """site: 采集点详情（含 tasks[].photos/videos）
    每个 task 都会在 EgoOps 里建一条作业任务，素材和 SOP 各归各的。
    """
    token = token or _token()
    site_name = site.get("name") or ""
    tasks = site.get("tasks") or []
    if not tasks:
        raise DraftError("这个采集点还没有任何任务")

    def step(pct, text):
        if progress:
            progress(pct, text)
        log(text)

    # ---------- 采集点级字段 ----------
    step(2, "读取采集点数据…")
    addr_text = (site.get("address") or "").strip()
    parts = parse_addr(addr_text)
    if parts["ok"]:
        full_addr = "%s %s %s %s" % (parts["province"], "" if parts["city"] == "市辖区" else parts["city"],
                                     parts["district"], parts["street"])
        full_addr = full_addr.replace("  ", " ").strip()
    else:
        full_addr = addr_text
        if addr_text:
            log("  地址拆不开（%s），原样写入" % parts.get("note"))
    if not addr_text:
        log("  ⚠ 没有现场地址，草稿里会留空")

    step(6, "生成采集点描述…")
    desc, src = generate_description(site)
    log("  描述来源：%s" % ("大模型" if src == "llm" else "模板"))

    step(10, "建草稿…")
    tsid = _api("POST", "/api/v1/task-sets/allocate-draft", {}, token=token).get("task_set_id")
    log("  草稿 id = %s" % tsid)

    step(14, "写采集点字段…")
    cur = _api("GET", "/api/v1/task-sets/%s" % tsid, token=token)
    _api("PATCH", "/api/v1/task-sets/%s" % tsid, {
        "name": site_name,
        "address": full_addr,
        "tet_node_path": site.get("scene") or cur.get("tet_node_path") or "",
        "description": desc,
    }, token=token)
    log("  名称 / 地址 / 场景 / 描述 已写入")

    # ---------- 逐个任务 ----------
    existing = _api("GET", "/api/v1/task-sets/%s/tasks?include_stats=false&include_assignments=false" % tsid,
                    token=token).get("records") or []

    # ---- 分组：采集点级（门头/全景）要并进第一个区域 ----
    def is_site_task(t):
        name = (t.get("name") or "")
        return ("门头" in name or "全景" in name) and not (t.get("area") or "").strip()

    site_tasks = [t for t in tasks if is_site_task(t)]
    area_tasks = [t for t in tasks if not is_site_task(t)]
    if not area_tasks:
        # 只有门头/全景：当成一个任务处理
        area_tasks = site_tasks
        site_tasks = []

    site_photos, site_videos = [], []
    for t in site_tasks:
        site_photos += t.get("photos") or []
        site_videos += t.get("videos") or []
    if site_photos or site_videos:
        log("  门头/全景素材：照片 %d 张、视频 %d 个，会并进任务1" % (len(site_photos), len(site_videos)))

    merged = []
    for i, t in enumerate(area_tasks):
        if i == 0:
            merged.append({
                "area": t.get("area") or "",
                "name": t.get("name") or "",
                "photos": (site_photos + (t.get("photos") or []))[:8],
                "videos": (site_videos + (t.get("videos") or []))[:3],
                "_merged": bool(site_photos or site_videos),
            })
        else:
            merged.append({
                "area": t.get("area") or "",
                "name": t.get("name") or "",
                "photos": (t.get("photos") or [])[:8],
                "videos": (t.get("videos") or [])[:3],
                "_merged": False,
            })
    tasks = merged

    made = []
    total_tasks = len(tasks)
    for ti, task in enumerate(tasks, 1):
        base_pct = 14 + int(80 * (ti - 1) / total_tasks)
        area = (task.get("area") or "").strip()
        name = (task.get("name") or "").strip() or ("任务%d" % ti)
        label = (area + "：" + name) if area else name

        # 复用草稿自带的第一个空任务，其余新建
        if ti == 1 and existing:
            tid = existing[0].get("task_id")
            step(base_pct, "[%d/%d] %s（复用默认任务）" % (ti, total_tasks, label))
        else:
            nt = _api("POST", "/api/v1/task-sets/%s/tasks/allocate-draft" % tsid, {}, token=token)
            tid = nt.get("task_id") or (nt.get("task") or {}).get("task_id")
            step(base_pct, "[%d/%d] %s（新建任务）" % (ti, total_tasks, label))
        if not tid:
            log("  ✗ 任务创建失败，跳过 %s" % label)
            continue

        photos = task.get("photos") or []
        videos = task.get("videos") or []
        if task.get("_merged"):
            log("  任务1 = 门头/全景 + 第一区域，共 照片 %d、视频 %d" % (len(photos), len(videos)))
        log("  照片 %d 张，视频 %d 个" % (len(photos), len(videos)))

        local_photos, local_videos = [], []
        for f in photos:
            try:
                local_photos.append((f, relay_files(f) if relay_files else _download(f)))
            except Exception as e:
                log("    素材下载失败 %s：%s" % (f.get("filename"), e))
        for f in videos:
            try:
                local_videos.append((f, relay_files(f) if relay_files else _download(f)))
            except Exception as e:
                log("    素材下载失败 %s：%s" % (f.get("filename"), e))

        # 看图写这个任务的内容（失败就退回模板，绝不让任务空着）
        try:
            content, src2 = generate_task_content_from_media(
                site, task, [p for _, p in local_photos], [p for _, p in local_videos])
        except Exception as e:
            log("    ⚠ 看图/大模型失败（%s），改用模板" % str(e)[:80])
            try:
                content, src2 = generate_task_content(site, task), "template"
            except Exception as e2:
                log("    ⚠ 模板也失败（%s），用最简内容" % str(e2)[:80])
                label_txt = ((task.get("area") or "") + "：" + (task.get("name") or "")).strip("：")
                content = {
                    "name": label_txt or "采集任务",
                    "desc": "在" + (site.get("name") or "") + "采集" + label_txt + "全过程，记录现场环境与操作步骤。",
                    "hours": 0.5,
                    "sop": ["到达采集区域，确认环境光线充足", "用广角拍摄区域全貌", "按步骤完成作业动作",
                            "补拍关键细节，确保画面清晰"],
                }
                src2 = "template"
        log("    内容来源：%s，时长 %s 小时，SOP %d 步" % (
            {"vision": "看过素材", "llm": "大模型", "template": "模板"}.get(src2, src2),
            content["hours"], len(content["sop"])))
        if content.get("seen"):
            log("    画面：%s" % content["seen"][:60])

        task_name = (content.get("name") or "").strip() or label
        if task.get("_merged") and not task_name.startswith("门头"):
            task_name = "门头全景·" + task_name
        if len(task_name) > 26:
            task_name = task_name[:26]

        # ① 先把文字写进去（名称/描述/时长/SOP），保证任务不空
        base_patch = {
            "task_name": task_name,
            "tet_node_path": site.get("scene") or "",
            "description": content["desc"],
            "required_duration": int(float(content["hours"]) * 3600),
            "collect_mode": "passive",
            "sop": {"steps": content["sop"]},
        }
        try:
            _api("PATCH", "/api/v1/tasks/%s" % tid, base_patch, token=token)
            log("    文字已写入：%s（时长 %s 小时，SOP %d 步）" % (task_name, content["hours"], len(content["sop"])))
        except Exception as e:
            log("    ✗ 写文字失败：%s，改用最简字段重试" % e)
            try:
                _api("PATCH", "/api/v1/tasks/%s" % tid,
                     {"task_name": task_name, "description": content["desc"]}, token=token)
                log("    已用最简字段写入名称/描述")
            except Exception as e2:
                log("    ✗ 仍然失败：%s" % e2)

        # ② 再传素材
        photo_ids, video_ids = [], []
        done = 0
        allcount = len(local_photos) + len(local_videos)
        for f, path in local_photos:
            done += 1
            step(base_pct, "[%d/%d] %s 上传照片 %d/%d" % (ti, total_tasks, label, done, allcount))
            try:
                photo_ids.append(_upload(tid, path, "photo", token))
            except Exception as e:
                log("    ✗ 照片上传失败 %s：%s" % (f.get("filename"), e))
        for f, path in local_videos:
            done += 1
            step(base_pct, "[%d/%d] %s 上传视频 %d/%d" % (ti, total_tasks, label, done, allcount))
            try:
                if codec_of(path) == "hevc":
                    log("    H.265 → H.264 转码中…")
                    path = ensure_h264(path)
                video_ids.append(_upload(tid, path, "video", token))
            except Exception as e:
                log("    ✗ 视频上传失败 %s：%s" % (f.get("filename"), e))

        # ③ 挂素材
        if photo_ids or video_ids:
            try:
                _api("PATCH", "/api/v1/tasks/%s" % tid, {"task_photos": photo_ids, "task_videos": video_ids},
                     token=token)
            except Exception as e:
                log("    ✗ 挂素材失败：%s" % e)

        # ④ 回查
        got_p, got_v = len(photo_ids), len(video_ids)
        try:
            chk = _api("GET", "/api/v1/task-sets/%s/tasks?include_stats=false&include_assignments=false" % tsid,
                       token=token).get("records") or []
            got = next((x for x in chk if x.get("task_id") == tid), {})
            gp = len(got.get("task_photos") or [])
            gv = len(got.get("task_videos") or [])
            if gp != len(photo_ids) or gv != len(video_ids):
                log("    ⚠ 回查不一致：本地 照片%d/视频%d，EgoOps 照片%d/视频%d"
                    % (len(photo_ids), len(video_ids), gp, gv))
            got_p, got_v = gp, gv
        except Exception as e:
            log("    （回查失败：%s）" % e)

        log("    完成：%s（照片 %d，视频 %d，SOP %d 步）" % (task_name, got_p, got_v, len(content["sop"])))
        made.append({"task_id": tid, "name": task_name, "label": label,
                     "photos": got_p, "videos": got_v, "sop": len(content["sop"])})

    step(100, "完成，共 %d 个任务" % len(made))
    return {
        "task_set_id": tsid,
        "name": site_name,
        "address": full_addr,
        "tasks": made,
        "photos": sum(t["photos"] for t in made),
        "videos": sum(t["videos"] for t in made),
    }


def _download(f):
    url = f.get("url") or ""
    if not url:
        raise DraftError("素材没有下载地址")
    tmp = os.path.join(os.environ.get("TEMP") or ".", f.get("filename") or (f.get("id", "x") + ".bin"))
    if os.path.exists(tmp) and os.path.getsize(tmp) == f.get("size"):
        return tmp
    with tls.urlopen(url, timeout=300) as r, open(tmp, "wb") as out:
        out.write(r.read())
    return tmp


def _upload(task_id, path, kind, token):
    business = "TASK_PHOTO" if kind == "photo" else "TASK_VIDEO"
    ct = "image/jpeg" if kind == "photo" else "video/mp4"
    r = _api("POST", "/api/v1/media-assets/upload-url", {
        "owner_type": "TASK", "owner_id": task_id, "business_type": business,
        "filename": os.path.basename(path), "content_type": ct,
        "file_size": os.path.getsize(path),
    }, token=token)
    mid, url = r["media_id"], r["upload_url"]
    with open(path, "rb") as fh:
        data = fh.read()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", ct)
    with urllib.request.urlopen(req, timeout=600) as resp:
        if resp.status >= 300:
            raise DraftError("上传失败：HTTP %s" % resp.status)
    _api("POST", "/api/v1/media-assets/%s/complete" % mid, {}, token=token)
    return mid


if __name__ == "__main__":
    site = json.load(open(sys.argv[1], encoding="utf-8"))
    relay = (sys.argv[2] if len(sys.argv) > 2 else "http://123.207.6.210/relay").rstrip("/")

    for t in site.get("tasks") or []:
        for f in (t.get("photos") or []) + (t.get("videos") or []):
            f["url"] = relay + "/files/" + f["id"]

    def bar(pct, text):
        print("[%3d%%] %s" % (pct, text), flush=True)

    res = create_draft(site, progress=bar)
    print("\n草稿:", res["task_set_id"], "|", res["name"], "|", res["address"] or "（地址空）",
          "| 照片", res["photos"], "| 视频", res["videos"])
