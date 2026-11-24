# 打包说明（PyInstaller）

> 原始打包文件在 workspace 根目录：`采集数据查看器.spec`（入口 `viewer/app.py`）、
> `采集数据查看器-新版.spec`（入口 `viewer/app2.py`）。下面先复述原 spec 的关键点，
> 再给出拆分后仓库（`main.py` / `main2.py` + `egoops_viewer/` 包）应改成什么样。

## 1. 原 spec 要点（两个文件几乎相同）

```python
datas = [('viewer/fill_egoops.py', '.'), ('viewer/agent_fill.py', '.'),
         ('viewer/address_parse.py', '.'), ('viewer/transcode_pc.py', '.'),
         ('viewer/egoops_draft.py', '.'), ('viewer/egoops_auth.py', '.'),
         ('viewer/egoops_status.py', '.'), ('viewer/extras.py', '.'),
         ('viewer/tls.py', '.'), ('viewer/egoops.crt', '.'), ('viewer/pca.json', '.')]
binaries = []; hiddenimports = []
tmp_ret = collect_all('sv_ttk')     ; datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('playwright') ; datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

a = Analysis(['viewer/app.py'], ..., datas=datas, hiddenimports=hiddenimports, ...)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='采集数据查看器',
          console=False, upx=True, icon=['viewer/app.ico'])
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name='采集数据查看器')
```

结论（原作者的取舍，拆分后仍适用）：

1. **用文件夹版（`exclude_binaries=True` + `COLLECT`），不做 onefile**。
   代码注释写明：单文件会解压到 `%TEMP%`，部分电脑被拦截。
2. **业务 .py 作为 datas 平铺到运行目录**：因为 `app.py` 里的 `_load_egoops_auth_mod` /
   `_load_draft_module` / `_load_status_mod` 用 `importlib.util.spec_from_file_location`
   按文件路径加载这几个模块，路径解析顺序是
   `sys._MEIPASS/<name>.py` → `dirname(__file__)/<name>.py`。
3. **`collect_all('sv_ttk')` / `collect_all('playwright')`**：主题库和浏览器驱动需要连数据一起带上。
4. `console=False`（无黑框）、`upx=True`、`icon=['viewer/app.ico']`。
5. `egoops.crt`、`pca.json` 是运行期数据（自签证书、省市区库），随包一起走。

## 2. 拆分后仓库的 spec（推荐写法）

```
egoops-viewer/
  main.py              <- 原 viewer/app.py 的入口
  main2.py             <- 原 viewer/app2.py 的入口（v2 布局）
  egoops_viewer/*.py   <- 包
  assets/app.ico
```

### 2.1 只改入口和 datas 路径

```python
# 采集数据查看器.spec（文件夹版，入口 main.py）
from PyInstaller.utils.hooks import collect_all

datas = [
    # 被 importlib 按文件路径加载的三个模块，跟着包目录一起进 datas
    ('egoops_viewer/egoops_auth.py', 'egoops_viewer'),
    ('egoops_viewer/egoops_status.py', 'egoops_viewer'),
    ('egoops_viewer/egoops_draft.py', 'egoops_viewer'),
    # 运行期数据（不入库，打包前自行放到 egoops_viewer/ 下）
    ('egoops_viewer/egoops.crt', 'egoops_viewer'),
    ('egoops_viewer/pca.json', 'egoops_viewer'),
]
binaries = []
hiddenimports = []
for pkg in ('sv_ttk', 'playwright'):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

a = Analysis(['main.py'], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='采集数据查看器', debug=False, strip=False, upx=True,
          console=False, icon=['assets/app.ico'])
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
               name='采集数据查看器')
```

`-新版` 版把 `Analysis(['main.py'])` 换成 `Analysis(['main2.py'])`、
`name` 换成 `采集数据查看器-新版` 即可，其余不变。

### 2.2 为什么 datas 里还要放那三个 .py

三个 UI 模块仍在用文件式加载（原逻辑未改）：

```python
base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(base, "egoops_auth.py")
if not os.path.exists(path):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "egoops_auth.py")
```

打包后 `__file__` 位于 `_MEIPASS/egoops_viewer/ui_auth.py`，所以：
- 首选 `_MEIPASS/egoops_auth.py`（旧写法）；
- 回退 `_MEIPASS/egoops_viewer/egoops_auth.py`（新布局，对应 datas 目标目录 `egoops_viewer`）。

两条路径任一命中即可，因此按 2.1 的写法打包能正常工作，不必改源码。
`egoops_status.py` 在被加载时会 `import egoops_auth`；`egoops_draft.py` 会 `import tls` /
`from address_parse import parse` 等，而它们在 datas 目标目录里同级，配合模块自带的
`sys.path.insert(0, HERE)` 能正常解析。

### 2.3 打包命令

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller==6.22.3
pyinstaller --noconfirm 采集数据查看器.spec      # 产物在 dist/采集数据查看器/
```

首次运行注意：

- `playwright` 不需要 `playwright install`——自动填表用的是**本机 Edge**
  （`msedge.exe` + CDP 9222 + 临时 `--user-data-dir`），只需要这台电脑的 Edge 登录过 EgoOps。
- `ffmpeg.exe` 首次转码时才下载到 `%APPDATA%/egoops-viewer/ffmpeg.exe`
  （来源见 `egoops_viewer/transcode_pc.py: FFMPEG_URL`），因此首次转码需要网络。
- `egoops.crt` 缺失 → 走系统 CA；`pca.json` 缺失 → 地址只做字符串处理，
  省市区需要用户在表单里手选。这两个文件按公司内部规范不入库。

## 3. 原 spec 与仓库的差异清单

| 项目 | 原 spec | 拆分后 |
| --- | --- | --- |
| 入口 | `viewer/app.py` / `viewer/app2.py` | `main.py` / `main2.py` |
| datas 源路径 | `viewer/*.py`（平铺到 `.`） | `egoops_viewer/*.py`（目标目录 `egoops_viewer`） |
| 图标 | `viewer/app.ico` | `assets/app.ico` |
| 业务模块 | 全部靠 datas 落到磁盘 | 逻辑层与 UI 层都在 PYZ 内，只有被 `spec_from_file_location` 加载的三个模块 + 两个数据文件保留在 datas |
| 打包形态 | 文件夹版 | 文件夹版（保持一致） |
| `console` | `False` | `False` |
