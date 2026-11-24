# 架构说明（egoops-viewer）

> 本文件描述拆分后的模块职责、数据流，以及与原单文件的对应关系。
> 精确到行的映射表见 [SPLIT.md](SPLIT.md)，打包见 [PACKAGING.md](PACKAGING.md)。

## 1. 整体分层

```
main.py / main2.py                 入口（等价原 app.py / app2.py 的 __main__）
   │
   ├── egoops_viewer/app.py        App：__init__ + _upgrade_server_url + selftest
   │      │  （class App 由 14 个 mixin 组合，方法体逐字来自原 app.py 类体）
   │      ├── ui_theme.py          ThemeMixin      sv_ttk 主题 / ttk Style
   │      ├── ui_auth.py           AuthMixin       EgoOps 登录态
   │      ├── ui_layout.py         LayoutMixin     整体布局（顶栏/左树/右预览/底栏）
   │      ├── ui_guide.py          GuideMixin      四步引导条
   │      ├── ui_settings.py       SettingsMixin   设置对话框（服务器/大模型/存储）
   │      ├── ui_invite.py         InviteMixin     邀请码
   │      ├── ui_draft.py          DraftMixin      草稿预览（HTML/纯文本）
   │      ├── ui_fill.py           FillMixin       申请采集点（自动填表）
   │      ├── ui_batch.py          BatchMixin      批量建草稿 / 质检 / 导出
   │      ├── ui_events.py         EventsMixin     线程 → UI 事件泵
   │      ├── ui_connect.py        ConnectMixin    连接 / 刷新 / 厂商系统映射
   │      ├── ui_tree.py           TreeMixin       树、筛选、勾选、详情、预览
   │      ├── ui_delete.py         DeleteMixin     永久删除采集点/文件
   │      └── ui_download.py       DownloadMixin   下载
   │
   ├── egoops_viewer/ui_v2.py      v2 主从布局界面（原 app2.py 整文件，class App）
   │
   └── 逻辑层（不依赖 tkinter）
          config.py          常量 + config.json 读写
          api_client.py      采集服务器 HTTP 客户端（Api / ApiError / human_size）
          tls.py             自签证书固定校验的 urlopen
          address_parse.py   整串地址 → 省/市/区/街道
          transcode_pc.py    非 H.264 视频转码（ffmpeg 可自动下载）
          agent_fill.py      大模型补全描述 / 任务 / SOP（文本 + 视觉）
          egoops_auth.py     EgoOps 登录态（cookie 存储、Edge 重登、续期）
          egoops_status.py   按 task_set_id 批量查草稿状态
          egoops_draft.py    建草稿主流程（含媒体上传、转码）
          fill_egoops.py     Playwright 驱动本机 Edge 填「申请采集点」表单
          extras.py          质检指标、草稿缓存、CSV 导出、临时下载
```

依赖方向单向：`app.py → ui_* → 逻辑层`。逻辑层内部只有 `api_client`/`extras` 依赖 `tls`，
`egoops_draft` 依赖 `address_parse`/`agent_fill`/`transcode_pc`/`tls`，`egoops_status` 依赖 `egoops_auth`。

## 2. 数据流

### 2.1 连接与列表

```
用户填服务器 + 姓名 → do_connect()
   线程: Api(server).health() → 是否需要邀请码 → api.login(name, invite)
   回到 UI: apply_invite_visibility() → on_connected(health)
       → load_vendor_systems() / load_vendor_names() / load_vendors() → do_refresh()
           → Api.sites() → fill_sites(items)         # 左树：sel,name,address,vendor,time,draft
           → auto_sync_drafts()                       # 60s 节流，核对草稿是否还在
```

### 2.2 查看与预览

```
on_tree_select → 选中采集点 → request_preview(f) / fill_detail(iid, detail)
   detail 来自 Api.site(id)：tasks → photos / videos（每项补 f["url"]）
下载/预览 URL：cfg["server"].rstrip("/") + "/files/" + f["id"]
照片预览：_preview_ready → show_photo() → PIL.Image + ImageTk
```

### 2.3 下载（勾选 → 落盘）

```
勾选（采集点或任务/文件） → _checked_targets() → collect_files_for_targets()
  → resolve_selected_files() → download_files(files, open_after)
     线程: api.download(f, dest) → self.ui(set_progress/download_done)
     完成后按设置打开文件或目录（os.startfile）
```

### 2.4 建草稿（EgoOps）

```
fill_egoops()/batch_draft() → _start_draft/_payload → _load_draft_module()
   egoops_draft.create_draft(payload, log=, progress=)
      ├── address_parse.parse(address)      省/市/区/街道
      ├── agent_fill.generate_*             描述 / 任务 / SOP（无 key 时回落模板）
      ├── transcode_pc.ensure_h264()        非 H.264 素材先转码
      └── _upload(task_id, path, kind)      上传到 EgoOps
   成功 → extras.remember(site_id, task_set_id) → _draft_done() → 提示去页面提交审核
```

### 2.5 申请采集点（浏览器自动填表）

```
fill_egoops()（ui_fill） → fill_egoops.run_fill(site, fields=..., profile=Edge 用户目录)
   playwright.sync_api → 启动本机 Edge（--user-data-dir 指向临时副本） → 打开
   https://egoops.<FILL_ME>/assignment → 点「申请采集点」→ 按 label 填 名称/地址/面积/场景
   → 窗口留给用户核对、手动提交；字段匹配失败时把控件树写入 egoops_fill.log
```

### 2.6 质检 / 导出

```
qc_site() → extras.fetch_to_temp() → extras.check_site(site, files, download)
   photo_metrics（PIL + numpy：清晰度/亮度/占比）/ video_metrics（ffmpeg 抽帧）
   → _qc_done(site, files, issues) 列表标红
export_table() → extras.export_sites_csv(rows, path)   # utf-8-sig，Excel 直接开
```

### 2.7 线程模型

Tk 不是线程安全的：所有后台线程只做网络/磁盘，结果通过 `self.ui(fn, *args)`
塞进 `queue.Queue`，由 `_poll()`（`root.after(80, ...)` 自循环）在主线程执行。
`set_status()` / `set_progress()` / `download_done()` 都是主线程回调。

## 3. 运行时文件位置（不在仓库里）

| 路径 | 用途 | 入库 |
| --- | --- | --- |
| `%APPDATA%/egoops-viewer/config.json` | 服务器、姓名、下载目录、llm、邀请码 | 否（模板见 `config.example.json`） |
| `%APPDATA%/egoops-viewer/egoops_auth.json` | EgoOps 登录态（cookie/storage） | 否 |
| `%APPDATA%/egoops-viewer/drafts.json` | 已建草稿的 site_id → task_set_id | 否 |
| `%APPDATA%/egoops-viewer/ffmpeg.exe` | 转码用 ffmpeg（首次按需下载） | 否 |
| `egoops_viewer/egoops.crt`（或 `sys._MEIPASS/egoops.crt`） | 服务器自签证书 | 否 |
| `egoops_viewer/pca.json`（或 `sys._MEIPASS/pca.json`） | 省-市-区数据（地址拆分） | 否 |
| `egoops_fill.log` | 自动填表调试日志 | 否（`.gitignore`） |

两个数据文件缺失时的行为：`tls.context()` 回落到系统 CA；`address_parse.load()` 返回 `[]`，
`parse()` 仍返回 dict 但 `ok=False`（表单里需手选省市区）。这属于原有降级逻辑，未改动。

## 4. 与原文件的对应关系

| 原文件 | 现在的位置 | 说明 |
| --- | --- | --- |
| `app.py`（2441 行） | `egoops_viewer/app.py` + `egoops_viewer/ui_*.py`（14 个 mixin）+ `config.py` + `main.py` | 类体按功能面板切成 mixin，方法体逐行未改 |
| `app2.py`（746 行） | `egoops_viewer/ui_v2.py` + `main2.py` | 只改 4 处 import + 3 行说明 |
| `api.py` | `egoops_viewer/api_client.py` | 只改 `import tls` |
| `extras.py` | `egoops_viewer/extras.py` | 只改 `import tls` |
| `tls.py` / `address_parse.py` / `transcode_pc.py` / `agent_fill.py` / `egoops_auth.py` / `egoops_status.py` / `egoops_draft.py` / `fill_egoops.py` | 同名模块 | 逐字复制 |
| `smoke.py` / `gui_smoke.py` | `legacy/`（不参与运行） | 依赖本机服务器与窗口，改由 `tests/smoke_test.py` 覆盖 |
| `README.md` / `app.ico` | `legacy/README.md`、`assets/app.ico` | 图标仅打包用 |

原文件全部逐字节留在 `legacy/`（`sha256` 已核对一致）。
