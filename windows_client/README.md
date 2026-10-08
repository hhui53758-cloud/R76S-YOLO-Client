# Windows 客户端源码

完整安装与打包命令见 [仓库 README](../README.md)。
普通用户操作见 [用户使用说明](用户使用说明.md)。

源码默认从相邻 `../deploy/best.onnx` 读取模型；便携版从 `_internal/deploy/best.onnx` 读取。源码和发布版都可用环境变量 `R76S_MODEL_PATH` 指定模型，用 `R76S_SERVER_URL` 指定板端 HTTP 地址。

所有 BAT 入口与 PS1 文件应保持在一起。网络脚本需要管理员权限，会调整物理有线网卡和 Wi-Fi 的 IPv4 优先级。存在多个物理有线网卡时先阅读网络文档，确认脚本的自动选择符合实际连接。
