"""从 EgoOps 查草稿的审核状态（草稿 / 待审核 / 已通过 / 驳回）。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import egoops_auth  # noqa: E402

API = "https://mrobo.uav.meituan.com/egoops"
STATUS_TEXT = {
    "draft": "草稿",
    "submitted": "待审核",
    "pending": "待审核",
    "approved": "已通过",
    "rejected": "驳回",
    "archived": "已归档",
}


def fetch_one(tsid, token):
    req = urllib.request.Request(API + "/api/v1/task-sets/" + str(tsid))
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise PermissionError("登录态失效") from None
        if e.code == 404:
            return None
        raise
    st = (d.get("review_status") or "").lower()
    return {
        "status": st,
        "text": STATUS_TEXT.get(st, st or "未知"),
        "name": d.get("name") or "",
        "at": time.strftime("%H:%M"),
    }


def refresh_all(draft_map, log=print):
    """draft_map: {site_id: {task_set_id, name}}  返回 {site_id: {status,text}}"""
    tok = egoops_auth.token_of()
    ok, who = egoops_auth.alive(tok)
    if not ok:
        raise PermissionError("EgoOps 登录态失效（%s），点「刷新登录态」重新登录" % who)

    out = {}
    total = len(draft_map)
    for i, (site_id, info) in enumerate(draft_map.items(), 1):
        tsid = info.get("task_set_id")
        if not tsid:
            continue
        log("查询草稿状态 %d/%d：%s" % (i, total, tsid))
        try:
            r = fetch_one(tsid, tok)
            if r:
                out[site_id] = r
            else:
                out[site_id] = {"status": "missing", "text": "已删除", "at": time.strftime("%H:%M")}
        except PermissionError:
            raise
        except Exception as e:
            out[site_id] = {"status": "error", "text": "查询失败", "at": str(e)[:20]}
    return out
