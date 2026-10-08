# 训练工程与真实历史记录

当前部署模型来自 `fast_n_20260922_122303`，标准 YOLO11n 检测训练，不是注意力改造模型。本目录提供历史原始脚本、去除本机绝对路径的参数、逐轮 results.csv 和可移植训练入口。没有提供未找到的注意力实验结论。

[真实历史指标与局限](HISTORICAL_RESULTS.md) · [数据检查报告](dataset_audit.json) · [训练权重下载](https://github.com/hhui53758-cloud/R76S-YOLO-Client/releases/tag/v1.0.0)

仅评估已有模型：下载 Releases 的 `best.pt` 到仓库根目录、准备数据后执行 `python training/train.py --test-only --weights best.pt --device 0`。只加载自己生成或可信来源的 PyTorch 权重，历史 best.pt 的 SHA256 在 `WEIGHTS_SHA256SUMS.txt`。

## 安装与运行

训练环境与 Windows 客户端环境分开建立。建议 Python 3.11；先按 [PyTorch 官方安装说明](https://pytorch.org/get-started/locally/) 安装适合显卡的版本，再安装此目录 requirements。没有显卡也可运行 CPU 训练，但速度较慢。训练依赖和上游 Ultralytics 框架各自许可独立适用。

```powershell
py -3.11 -m venv .venv-train
.\.venv-train\Scripts\python.exe -m pip install -r training/requirements.txt
.\.venv-train\Scripts\python.exe training/train.py --device 0
```

运行前按 [数据集说明](DATASET.md) 准备 `datasets/trash/`。`yolo11n.pt` 首次会由 Ultralytics 下载；也可用 `--weights` 指定已有文件。查看参数用 `python training/train.py --help`；CPU 测试用 `--device cpu --batch 4`。命令会创建 `training_runs/` 和临时数据配置；默认会进行耗时训练，不是客户端启动命令。

`train_fast_original.py` 是保留的原始历史脚本，不保证离开旧目录可直接运行；使用新入口。`historical_args.yaml` 的模型、数据、输出路径已替换，其他参数保留。`results.csv` 是逐轮验证集指标，不是独立 test 集指标。不能把某一轮的验证结果标成测试成绩。

历史参数：640 输入、batch 32、最多 130 轮、patience 18、seed 0、deterministic=False。由于原随机增强、运行环境、源数据版本和校准名单未全部固定，重新训练不保证产生相同权重或数值。新训练入口尚未完成一次全量重训；只验证参数解析与语法。

## 训练模型不是客户端部署模型

训练得到 `best.pt`（PyTorch 权重）后，还需使用 Rockchip 适配版 YOLO11 导出九输出 ONNX，再用 RKNN-Toolkit2 转换 RK3576 模型。当前客户端不接受标准单输出 ONNX。现成部署模型位于 `deploy/`，检查契约见 `deploy/model_manifest.json`；不要把重新训练的 `.pt` 改后缀直接使用。

ONNX：Open Neural Network Exchange，开放神经网络交换格式。GPU：Graphics Processing Unit，图形处理器。CUDA 是 NVIDIA 的并行计算平台名称。mAP：mean Average Precision，平均精度均值；验证集指标不能替代泛化与真实摄像头实测。
