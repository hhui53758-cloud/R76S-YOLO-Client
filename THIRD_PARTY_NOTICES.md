# 第三方来源与许可状态

## Rockchip RKNN Model Zoo

来源：https://github.com/airockchip/rknn_model_zoo

本地部署代码来自历史下载版本 `bad6c73`。保留了以下文件并作了部署适配：

- `deploy/rknn_model_zoo/examples/yolo11/python/yolo11.py`：四类垃圾、NumPy DFL、RK3576 默认参数。
- `deploy/rknn_model_zoo/py_utils/rknn_executor.py`：使用板端 RKNN Lite。
- `deploy/rknn_model_zoo/py_utils/coco_utils.py` 及 `__init__.py`：图像补边与辅助处理。
- Windows 后处理实现采用同一类 YOLO11 解码结构，以维持两端结果一致。

上游以 Apache License 2.0 发布，许可证副本在 `licenses/RKNN_MODEL_ZOO_LICENSE.txt`。改动不代表上游官方支持或性能保证。

## 运行依赖

NumPy、OpenCV、ONNX Runtime、Pillow、Python/Tkinter、PyInstaller 与 Rockchip RKNN Lite 的代码或二进制适用各自许可证。requirements 只声明依赖，不代替依赖许可证。RKNN Lite wheel 从官方来源获取，源码仓库不附带。

## 模型与原创代码

训练数据来源经项目作者确认是 Keai Xiao 的 [Roboflow waste](https://universe.roboflow.com/keai-xiao-zwt9l/waste-8vlsn)，上游标注 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。归属、许可、历史版本及本地数量差异见 `training/DATASET.md`；不将未追溯新增部分直接认定为上游许可数据。

三份模型由 Ultralytics YOLO 训练模型经 Rockchip 适配导出/转换获得。训练框架及模型授权仍须分别核实，不将它们声明为 Apache-2.0 或 MIT。数据集许可不自动替代模型或软件许可。

本项目原创部分尚未选择公开许可证。提供源文件不等于开放任意复制、再分发或商业使用许可。作者确认后可添加根 LICENSE，并更新本文件。
