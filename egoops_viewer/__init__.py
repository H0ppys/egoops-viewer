"""egoops_viewer —— 采集数据查看器（Windows 桌面版）模块化源码包

原单文件实现见 legacy/app.py、legacy/app2.py。包内划分：
  config / api_client / tls / address_parse / transcode_pc / agent_fill /
  egoops_auth / egoops_status / egoops_draft / fill_egoops / extras  —— 逻辑层
  ui_* —— Tk 界面（按功能面板拆成 mixin）
  app  —— 主窗口装配（App）与 selftest
"""

__version__ = "16"
APP_NAME = "采集数据查看器"
APP_VER = "v16"

__all__ = ["__version__", "APP_NAME", "APP_VER"]
