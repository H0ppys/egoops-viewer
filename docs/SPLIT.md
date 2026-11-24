# 拆分映射表（原文件行段 → 新模块）

原单文件全部保留在 `legacy/`（逐字节一致）。下表按 `def` 行号列出，行号对应 `legacy/app.py`。

## 1. app.py → 逻辑层 / 界面层

| 原文件 | 行段 / 符号 | 新模块 | 说明 |
| --- | --- | --- | --- |
| app.py | 1-19 文件头与 import | egoops_viewer/*（各模块头部重写） | 只保留 docstring 与 import 的等价物 |
| app.py | 20-38 常量 + load_config/save_config | egoops_viewer/config.py | 逐字搬运 |
| app.py | 41 `class App:` | egoops_viewer/app.py | 类头改为 mixin 组合，方法体不动 |
| app.py | 42 `App._upgrade_server_url` | egoops_viewer/app.py | App 装配：服务器地址升级 |
| app.py | 51 `App.__init__` | egoops_viewer/app.py | App 装配：__init__（原样） |
| app.py | 95 `App._apply_theme` | egoops_viewer/ui_theme.py | 样式：sv_ttk 主题 |
| app.py | 105 `App._load_egoops_auth_mod` | egoops_viewer/ui_auth.py | EgoOps 登录态 |
| app.py | 116 `App.check_egoops_login` | egoops_viewer/ui_auth.py | EgoOps 登录态 |
| app.py | 132 `App._after_login_check` | egoops_viewer/ui_auth.py | EgoOps 登录态 |
| app.py | 149 `App.prompt_login` | egoops_viewer/ui_auth.py | EgoOps 登录态 |
| app.py | 155 `App.do_login` | egoops_viewer/ui_auth.py | EgoOps 登录态 |
| app.py | 169 `App._after_login` | egoops_viewer/ui_auth.py | EgoOps 登录态 |
| app.py | 180 `App._style` | egoops_viewer/ui_theme.py | 样式：ttk Style |
| app.py | 222 `App._build` | egoops_viewer/ui_layout.py | 布局：整体界面 |
| app.py | 421 `App.open_egoops` | egoops_viewer/ui_layout.py | 布局：打开 EgoOps |
| app.py | 427 `App._on_step_click` | egoops_viewer/ui_guide.py | 引导条 |
| app.py | 431 `App.set_step` | egoops_viewer/ui_guide.py | 引导条 |
| app.py | 434 `App.update_guide` | egoops_viewer/ui_guide.py | 引导条 |
| app.py | 464 `App.storage_dialog` | egoops_viewer/ui_settings.py | 设置：存储占用 |
| app.py | 477 `App._show_storage` | egoops_viewer/ui_settings.py | 设置：存储占用 |
| app.py | 515 `App.open_settings` | egoops_viewer/ui_settings.py | 设置：主对话框 |
| app.py | 748 `App._pick_dir_into` | egoops_viewer/ui_settings.py | 设置：选目录 |
| app.py | 756 `App.open_invite` | egoops_viewer/ui_invite.py | 邀请码 |
| app.py | 829 `App.draft_html` | egoops_viewer/ui_draft.py | 草稿预览 |
| app.py | 879 `App.show_draft` | egoops_viewer/ui_draft.py | 草稿预览 |
| app.py | 917 `App.draft_plain` | egoops_viewer/ui_draft.py | 草稿预览 |
| app.py | 946 `App._ensure_meituan` | egoops_viewer/ui_fill.py | 自动填表 |
| app.py | 960 `App.fill_egoops` | egoops_viewer/ui_fill.py | 自动填表 |
| app.py | 1021 `App._start_draft` | egoops_viewer/ui_fill.py | 自动填表 |
| app.py | 1070 `App._reset_progress` | egoops_viewer/ui_fill.py | 自动填表 |
| app.py | 1074 `App._set_progress` | egoops_viewer/ui_fill.py | 自动填表 |
| app.py | 1079 `App._draft_done` | egoops_viewer/ui_fill.py | 自动填表 |
| app.py | 1104 `App._draft_failed` | egoops_viewer/ui_fill.py | 自动填表 |
| app.py | 1110 `App._load_draft_module` | egoops_viewer/ui_batch.py | 批量/质检/导出 |
| app.py | 1121 `App._payload` | egoops_viewer/ui_batch.py | 批量/质检/导出 |
| app.py | 1129 `App.batch_draft` | egoops_viewer/ui_batch.py | 批量/质检/导出 |
| app.py | 1174 `App._batch_done` | egoops_viewer/ui_batch.py | 批量/质检/导出 |
| app.py | 1185 `App.qc_site` | egoops_viewer/ui_batch.py | 批量/质检/导出 |
| app.py | 1218 `App._qc_done` | egoops_viewer/ui_batch.py | 批量/质检/导出 |
| app.py | 1270 `App.export_table` | egoops_viewer/ui_batch.py | 批量/质检/导出 |
| app.py | 1312 `App._poll` | egoops_viewer/ui_events.py | 线程通信 |
| app.py | 1336 `App.ui` | egoops_viewer/ui_events.py | 线程通信 |
| app.py | 1339 `App.set_status` | egoops_viewer/ui_events.py | 线程通信 |
| app.py | 1344 `App.do_connect` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1376 `App.apply_invite_visibility` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1384 `App._show_ctx` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1394 `App.refresh_login_state` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1415 `App._target_site` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1430 `App.draft_text` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1441 `App.refresh_draft_status` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1483 `App.invites_map` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1491 `App.vendor_of` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1508 `App.load_vendor_systems` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1514 `App.system_of` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1518 `App.load_vendor_names` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1529 `App.load_vendors` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1536 `App.on_connected` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1543 `App.do_refresh` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1561 `App.auto_sync_drafts` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1618 `App._load_status_mod` | egoops_viewer/ui_connect.py | 连接与刷新 |
| app.py | 1631 `App._on_search_typing` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1640 `App._apply_filters` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1680 `App.fill_sites` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1709 `App.on_tree_select` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1734 `App.request_preview` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1767 `App._preview_ready` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1776 `App._preview_failed` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1783 `App.show_photo` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1794 `App.on_tree_open` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1818 `App._load_failed` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1828 `App.fill_detail` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1863 `App.on_tree_click` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1890 `App._set_checked` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1904 `App._sync_ancestors` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1914 `App._is_checked` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1920 `App.on_tree_double` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1934 `App.update_check_label` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1943 `App.checked_files` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1975 `App.toggle_all_checks` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1984 `App.toggle_all_sites` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1987 `App.download_checked_sites` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 1990 `App.download_site` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 2010 `App.update_site_check_label` | egoops_viewer/ui_tree.py | 树形列表 |
| app.py | 2015 `App.ask_dir` | egoops_viewer/ui_download.py | 下载 |
| app.py | 2028 `App.download_selected` | egoops_viewer/ui_download.py | 下载 |
| app.py | 2035 `App._delete_sites` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2054 `App._after_delete_sites` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2064 `App.cleanup_empty_sites` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2082 `App._confirm_cleanup_empty` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2088 `App.delete_checked_sites` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2102 `App.after_delete_sites` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2109 `App.delete_checked_files` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2122 `App._delete_preview` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2191 `App._confirm_delete_files` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2216 `App.after_delete_files` | egoops_viewer/ui_delete.py | 删除 |
| app.py | 2223 `App._checked_targets` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2246 `App.collect_files_for_targets` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2262 `App.resolve_selected_files` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2313 `App._checked_sites` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2316 `App.download_checked` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2339 `App.download_files` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2386 `App.set_progress` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2391 `App.download_done` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2407 `App.open_download_dir` | egoops_viewer/ui_download.py | 下载：勾选解析 |
| app.py | 2415-2429 `selftest()` | egoops_viewer/app.py | 逐字搬运 |
| app.py | 2431-2438 `main()` | main.py | 等价实现，额外支持 `--help` |

## 2. 其余单文件 → 逻辑层（整文件搬运）

| 原文件 | 行段 / 符号 | 新模块 | 说明 |
| --- | --- | --- | --- |
| app.py | 20-24 常量 / 27-38 load_config+save_config<br>APP_VER、APP_NAME、DEFAULT_SERVER、CONFIG_DIR、CONFIG_PATH、load_config、save_config | egoops_viewer/config.py | 原 app.py 的模块级常量与配置读写 |
| api.py | api.py 全文 1-147<br>ApiError、Api、human_size | egoops_viewer/api_client.py | 服务器 HTTP 客户端（仅改 `import tls` → `from . import tls`） |
| tls.py | tls.py 全文 1-29<br>context、urlopen | egoops_viewer/tls.py | 自签证书固定校验（egoops.crt 不进仓库） |
| address_parse.py | address_parse.py 全文 1-100<br>load、_norm、parse | egoops_viewer/address_parse.py | 地址拆省市区（pca.json 不进仓库，缺失时降级） |
| transcode_pc.py | transcode_pc.py 全文 1-75<br>ffmpeg_path、codec_of、ensure_h264 | egoops_viewer/transcode_pc.py | 非 H.264 视频转码 |
| agent_fill.py | agent_fill.py 全文 1-336<br>load_llm_config、generate_description、generate_task_content 等 | egoops_viewer/agent_fill.py | 大模型补全描述/SOP |
| egoops_auth.py | egoops_auth.py 全文 1-199<br>token_of、alive、relogin、refresh | egoops_viewer/egoops_auth.py | EgoOps 登录态（支持被 importlib 按文件加载） |
| egoops_status.py | egoops_status.py 全文 1-71<br>fetch_one、refresh_all | egoops_viewer/egoops_status.py | 草稿状态批量查询 |
| egoops_draft.py | egoops_draft.py 全文 1-364<br>create_draft 等 | egoops_viewer/egoops_draft.py | 建草稿主流程（文件式加载，保留 sys.path 兼容） |
| fill_egoops.py | fill_egoops.py 全文 1-277<br>run_fill、fill_address、main | egoops_viewer/fill_egoops.py | Playwright 自动填表 |
| extras.py | extras.py 全文 1-202<br>photo_metrics、video_metrics、check_site、export_sites_csv 等 | egoops_viewer/extras.py | 质检/草稿缓存/CSV 导出（仅改 `import tls`） |
| app2.py | app2.py 全文 1-746<br>load_config、human_size、App(v2)、main | egoops_viewer/ui_v2.py | v2 主从布局界面（只改 4 处 import + 3 行说明） |
| app.py | app.py 2431-2438 main()<br>main | main.py | 入口：+--help，其余等价原 main() |
| app2.py | app2.py 739-741 main()<br>main | main2.py | v2 入口 |

## 3. 界面的 14 个 mixin（原 `class App` 的 2373 行类体）

| mixin | 文件 | 原行段 | 方法数 |
| --- | --- | --- | --- |
| ThemeMixin | egoops_viewer/ui_theme.py | app.py 93-102、180-219 | 2 |
| AuthMixin | egoops_viewer/ui_auth.py | app.py 103-179 | 6 |
| LayoutMixin | egoops_viewer/ui_layout.py | app.py 220-424 | 2 |
| GuideMixin | egoops_viewer/ui_guide.py | app.py 425-457 | 3 |
| SettingsMixin | egoops_viewer/ui_settings.py | app.py 458-753 | 4 |
| InviteMixin | egoops_viewer/ui_invite.py | app.py 754-826 | 1 |
| DraftMixin | egoops_viewer/ui_draft.py | app.py 827-943 | 3 |
| FillMixin | egoops_viewer/ui_fill.py | app.py 944-1107 | 7 |
| BatchMixin | egoops_viewer/ui_batch.py | app.py 1108-1309 | 7 |
| EventsMixin | egoops_viewer/ui_events.py | app.py 1310-1341 | 3 |
| ConnectMixin | egoops_viewer/ui_connect.py | app.py 1342-1628 | 17 |
| TreeMixin | egoops_viewer/ui_tree.py | app.py 1629-2012 | 23 |
| DeleteMixin | egoops_viewer/ui_delete.py | app.py 2035-2222 | 10 |
| DownloadMixin | egoops_viewer/ui_download.py | app.py 2013-2034、2223-2413 | 11 |
