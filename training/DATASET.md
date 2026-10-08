# 数据集来源与本地版本

项目作者确认历史训练数据来源为 [waste — Keai Xiao / Roboflow Universe](https://universe.roboflow.com/keai-xiao-zwt9l/waste-8vlsn)。2026-10-08 核对来源页标注为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，即知识共享署名 4.0；[完整许可条款](https://creativecommons.org/licenses/by/4.0/legalcode)。使用或再分发上游数据时应保留作者、来源、许可链接和修改说明，不暗示原作者为本项目背书。

## 不可忽略的差异

来源页显示 2739 张；本地历史训练目录包含 2743 张：train 1920、val 548、test 275。原下载版本、4 张差额及历史预处理过程尚未核实。本地目录采用 images/labels 三组划分和以下类别 ID；不宣称与上游任意版本完全一致。

| ID | 英文 | 中文 |
| --- | --- | --- |
| 0 | recyclable waste | 可回收物 |
| 1 | hazardous waste | 有害垃圾 |
| 2 | kitchen waste | 厨余垃圾 |
| 3 | other waste | 其他垃圾 |

上游许可不自动证明本地未追溯新增图片也拥有相同许可。当前先公开来源、检查报告和获取方式；完整本地快照待核对差异后发布。模型和训练框架许可与数据集许可分开处理。

实际检查：2743 对图片和标签，3925 个目标框；train 2783 框、val 763 框、test 379 框。发现 1 组跨划分字节相同图片。详见 `dataset_audit.json`；数据没有被自动删改，也不将来源名称相同视为文件内容相同。

## 获取和配置

推荐从上游 Dataset 页面选择版本，导出 YOLO 检测格式，并记录版本号、类别顺序和划分。Roboflow 导出可能使用 train/images、valid/images 等目录，而本项目历史目录为 images/train、images/val、images/test；不要只改名字就假定划分或标签 ID 相同。

把数据集放在仓库根目录 `datasets/trash/`，核对四类 ID，再用 `training/trash.yaml`。若采用上游不同版本或划分，修改配置并记录差异；不能称为对当前模型的严格复现。

本地检查（不上传、不修改图片）：

```powershell
python scripts/package_dataset.py datasets/trash --audit-only
```

检查包含图片/标签配对、标签坐标和类别、逐组数量、按图片字节 SHA256 检测跨组完全相同图片。它不能识别近重复图，也不能代替授权或隐私审查。打包模式只用于已确认授权的数据，输出到忽略提交的 `release/`。
