# 采集数据查看器（egoops-viewer）

## 1. 一句话定位

Windows 桌面工具——连自己的采集服务器，按采集点/任务看照片视频、批量下载与删除，
并能把采集点信息一键建成 EgoOps 草稿、驱动本机 Edge 自动填「申请采集点」表单。

具体包含：

- **左**：采集点列表（门店 / 采集员 / 时间 / 场景分类 / 面积 / 任务数 / 文件数 / 大小），最左列可勾选
- **右**：文件列表按「区域 / 任务」分组，勾选批量下载；点照片在下方预览
- **底部三行**：文件（下载/全选/删除/下载选中）、采集点（下载/全选/删除/打开目录）、美团（申请采集点·自动填表）
- **附加**：草稿预览与批量建草稿、EgoOps 草稿状态自动核对、质检指标（清晰度/亮度/视频抽帧）、CSV 导出

## 2. 原始来源

| 项目 | 内容 |
| --- | --- |
| 原始位置（工作区） | `C:\Users\Administrator\Documents\deepseek-harness\default-workspace\viewer\` |
| 原始文件 | `app.py`（2441 行，v16 主程序）、`app2.py`（746 行，v2.0 主从布局版）、`api.py`、`extras.py`、`tls.py`、`address_parse.py`、`transcode_pc.py`、`agent_fill.py`、`egoops_auth.py`、`egoops_status.py`、`egoops_draft.py`、`fill_egoops.py`、`smoke.py`、`gui_smoke.py`、`README.md`、`app.ico` |
| 版本 | APP_VER `v16`（v2 界面为 `v2.0`） |
| 打包脚本 | workspace 根 `采集数据查看器.spec`、`采集数据查看器-新版.spec` |
| 原始形态 | 单文件 Tkinter 程序 + 一堆平铺的兄弟模块，靠 `sys.path` 和 `importlib.util.spec_from_file_location` 互相加载 |
| 本仓库形态 | 同一份代码拆成 `egoops_viewer/` 包（逻辑层 + 14 个 UI mixin），原文件逐字节留存在 `legacy/` |

## 3. 目录结构

```
egoops-viewer/
  main.py                     # 入口（等价原 app.py 的 __main__，额外支持 --help）
  main2.py                    # v2 入口（等价原 app2.py）
  requirements.txt
  config.example.json         # 配置模板（值全是 <FILL_ME>）
  assets/app.ico
  egoops_viewer/
    __init__.py
    config.py                 # 常量 + config.json 读写
    api_client.py             # 采集服务器 HTTP 客户端
    tls.py                    # 自签证书固定校验
    address_parse.py          # 地址 → 省/市/区/街道
    transcode_pc.py           # 非 H.264 转码（ffmpeg 按需下载）
    agent_fill.py             # 大模型补全描述 / 任务 / SOP
    egoops_auth.py            # EgoOps 登录态
    egoops_status.py          # 草稿状态批量查询
    egoops_draft.py           # 建草稿主流程
    fill_egoops.py            # Playwright 填「申请采集点」表单
    extras.py                 # 质检 / 草稿缓存 / CSV 导出
    ui_theme.py  ui_auth.py  ui_layout.py  ui_guide.py
    ui_settings.py  ui_invite.py  ui_draft.py  ui_fill.py
    ui_batch.py  ui_events.py  ui_connect.py  ui_tree.py
    ui_delete.py  ui_download.py
    ui_v2.py                  # 原 app2.py 整文件（v2 界面）
    app.py                    # class App(...14 个 mixin) + selftest()
  legacy/                     # 原始单文件镜像（只读参照，不参与运行）
  docs/
    ARCHITECTURE.md  SPLIT.md  PACKAGING.md
  tests/smoke_test.py
```

## 4. 安装与运行

```powershell
python -m pip install -r requirements.txt      # playwright / sv-ttk / pillow / numpy

python main.py                                  # 启动 v16 界面
python main2.py                                 # 启动 v2（主从布局）界面
python main.py --selftest                        # 无界面自检，结果写到 %TEMP%/egoops-viewer-selftest.txt
python -X utf8 tests/smoke_test.py               # 冒烟：import 全部模块 + 两个入口 --help
```

不需要 `playwright install`：自动填表驱动的是**本机 Edge**（`msedge.exe` + CDP 9222 +
临时 `--user-data-dir`），只要这台电脑的 Edge 登录过 EgoOps 即可，不用拷 token/cookie。

首次转码会下载 `%APPDATA%/egoops-viewer/ffmpeg.exe`（见 `egoops_viewer/transcode_pc.py`）。

## 5. 模块说明

| 模块 | 职责 | 关键符号 |
| --- | --- | --- |
| `egoops_viewer/config.py` | 默认服务器、APP 名/版本、`config.json` 读写 | `APP_NAME`、`APP_VER`、`DEFAULT_SERVER`、`load_config`、`save_config` |
| `egoops_viewer/api_client.py` | 采集服务器 REST 客户端（health/sites/site/files/download/delete/…） | `Api`、`ApiError`、`human_size` |
| `egoops_viewer/tls.py` | 用 `egoops.crt` 固定校验自签证书；缺失回落系统 CA | `context`、`urlopen` |
| `egoops_viewer/address_parse.py` | 整串地址拆省/市/区/街道门牌（依赖 `pca.json`） | `load`、`parse` |
| `egoops_viewer/transcode_pc.py` | 检测编码，非 H.264 用 ffmpeg 转码 | `ffmpeg_path`、`codec_of`、`ensure_h264` |
| `egoops_viewer/agent_fill.py` | 大模型生成采集点描述、任务描述/SOP（含视觉抽帧） | `generate_description`、`generate_task_content`、`generate_task_content_from_media` |
| `egoops_viewer/egoops_auth.py` | EgoOps 登录态：取 token、校验、Edge 重登、静默续期 | `token_of`、`alive`、`relogin`、`refresh` |
| `egoops_viewer/egoops_status.py` | 按 `task_set_id` 查草稿状态，批量刷新 | `fetch_one`、`refresh_all` |
| `egoops_viewer/egoops_draft.py` | 建草稿：地址解析 → 内容生成 → 转码 → 上传 | `create_draft` |
| `egoops_viewer/fill_egoops.py` | Playwright 驱动本机 Edge 填表 | `run_fill`、`fill_address` |
| `egoops_viewer/extras.py` | 质检指标、草稿缓存、CSV 导出、临时下载 | `photo_metrics`、`video_metrics`、`check_site`、`remember`、`export_sites_csv` |
| `egoops_viewer/ui_*` | 界面：主题、登录态、布局、引导、设置、邀请码、草稿预览、自动填表、批量/质检/导出、事件泵、连接、树、删除、下载 | 各 `*Mixin` 类 |
| `egoops_viewer/app.py` | `App` 装配（14 个 mixin）+ `__init__` + `selftest()` | `App`、`selftest` |
| `egoops_viewer/ui_v2.py` | v2 主从布局界面（原 `app2.py` 整文件） | `App`（v2） |
| `main.py` / `main2.py` | 入口；`--help` / `--selftest` | `main` |

## 6. 配置项

配置放在 `%APPDATA%/egoops-viewer/config.json`（首次运行自动生成，界面里可改服务器与姓名）。
仓库里只有模板 `config.example.json`：

```json
{
  "server": "http://<FILL_ME>.example.com/relay",
  "name": "<FILL_ME>",
  "download_dir": "<FILL_ME>",
  "admin_key": "<FILL_ME>",
  "invite": "",
  "invites": {},
  "fill_fields": {"name": true, "address": true, "area": true, "scene": true},
  "llm": {
    "base": "https://api.<FILL_ME>/v1",
    "model": "<FILL_ME>",
    "key": "<FILL_ME>",
    "vision_model": "<FILL_ME>"
  }
}
```

| 键 | 说明 |
| --- | --- |
| `server` | 采集服务器地址（原默认 `http://123.207.6.210/relay`，界面里会自动升级成 https） |
| `name` | 使用者姓名，只用于记录「谁在看」 |
| `download_dir` | 上次下载目录 |
| `admin_key` | 服务器管理接口用的 key（可选，留空即不用） |
| `invite` / `invites` | 邀请码（服务器要求时必填） |
| `fill_fields` | 自动填表时哪些字段交给程序填 |
| `llm` | 文本模型（`base`/`model`/`key`）与视觉模型名（`vision_model`）；`key` 为空时全部回落本地模板，不联网 |

运行期还会有（都**不入库**，且在 `.gitignore` 里）：
`egoops_auth.json`（登录态）、`drafts.json`（草稿缓存）、`ffmpeg.exe`、`egoops_fill.log`。
`egoops.crt`（服务器自签证书）与 `pca.json`（省市区库）需自行放到 `egoops_viewer/` 下，
缺失时分别回落到系统 CA 与「地址不拆分」的降级路径。

## 7. 打包（PyInstaller）

```powershell
python -m pip install pyinstaller==6.22.3
pyinstaller --noconfirm 采集数据查看器.spec      # 产物：dist/采集数据查看器/
```

原 spec 的要点：**文件夹版**（`exclude_binaries=True` + `COLLECT`，不做 onefile，避免解压到
`%TEMP%` 被拦截）、`collect_all('sv_ttk')`、`collect_all('playwright')`、`console=False`、
`upx=True`、`icon=['viewer/app.ico']`，并把业务 `.py`、`egoops.crt`、`pca.json` 一起塞进 `datas`。
拆分后的 spec 怎么写（入口改 `main.py`、datas 目标目录改 `egoops_viewer`）见
[docs/PACKAGING.md](docs/PACKAGING.md)。

## 8. 拆分说明

原 `app.py` 的 2373 行 `class App` 类体，按功能面板原样切成 14 个 mixin（`ui_*.py`），
`App` 只保留 `__init__` / `_upgrade_server_url`，靠继承拼装；其余单文件整文件搬进包。
**只新增模块 docstring、import 语句与 `__init__.py`，方法体逐行未改**。

- 逐行映射表：[docs/SPLIT.md](docs/SPLIT.md)
- 模块职责与数据流：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 打包/解包：[docs/PACKAGING.md](docs/PACKAGING.md)
- 原始单文件：[legacy/](legacy/)（逐字节一致，仅作参照，不参与运行）

## 9. 说明与注意

- 删除是**永久删除**（服务器文件 + 数据库记录），界面有二次确认。
- EgoOps 相关功能依赖公司内网账号与授权，仓库不含任何 token / cookie / 业务数据。
- 许可证：MIT，见 [LICENSE](LICENSE)。
