"""RTX 4060 8GB 上的垃圾检测高性价比训练脚本。

直接运行：python train_fast.py

设计目标：
1. 使用标准 YOLO11n，避免自定义模块带来的保存和部署兼容问题。
2. batch=32 提高 GPU 吞吐，130 轮约需 40 分钟（以本机历史记录为参考）。
3. Early Stopping 自动结束无收益训练。
4. 每次生成独立结果目录，避免 results.csv 混入旧实验。
5. 训练结束后用独立 test 集评估 best.pt。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import torch
from ultralytics import YOLO


# 路径全部相对于当前脚本，PyCharm 从其他工作目录启动也不会找错文件。
ROOT = Path(__file__).resolve().parent
DATA_YAML = ROOT / "ultralytics" / "cfg" / "datasets" / "trash.yaml"
MODEL_WEIGHTS = ROOT / "yolo11n.pt"
PROJECT_DIR = ROOT / "runs" / "detect"
RUN_NAME = f"fast_n_{datetime.now():%Y%m%d_%H%M%S}"

# 针对 1920 张训练图和 RTX 4060 8GB 的性能/耗时折中。
DEVICE = 0
IMG_SIZE = 640
BATCH = 32
EPOCHS = 130
PATIENCE = 18
WORKERS = 2
SEED = 0


def check_environment() -> None:
    """在正式训练前尽早报告路径或 CUDA 问题。"""
    if not DATA_YAML.is_file():
        raise FileNotFoundError(f"找不到数据配置：{DATA_YAML}")
    if not MODEL_WEIGHTS.is_file():
        raise FileNotFoundError(f"找不到预训练权重：{MODEL_WEIGHTS}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用，请确认 PyCharm 使用 yolo-train 环境。")

    gpu_name = torch.cuda.get_device_name(DEVICE)
    gpu_memory = torch.cuda.get_device_properties(DEVICE).total_memory / 1024**3
    print("\n========== 训练环境 ==========")
    print(f"PyTorch: {torch.__version__}")
    print(f"GPU: {gpu_name} ({gpu_memory:.1f} GB)")
    print(f"数据配置: {DATA_YAML}")
    print(f"预训练权重: {MODEL_WEIGHTS}")
    print(f"结果目录: {PROJECT_DIR / RUN_NAME}")
    print(f"epochs={EPOCHS}, batch={BATCH}, imgsz={IMG_SIZE}, patience={PATIENCE}")
    print("==============================\n")


def configure_torch() -> None:
    """开启适合固定 640 输入尺寸的 CUDA 加速选项。"""
    torch.cuda.empty_cache()
    torch.set_float32_matmul_precision("high")
    torch.backends.cudnn.benchmark = True
    torch.backends.cudnn.deterministic = False
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True


def train() -> Path:
    """训练模型并返回最佳权重路径。"""
    model = YOLO(str(MODEL_WEIGHTS))
    model.train(
        data=str(DATA_YAML),
        model=str(MODEL_WEIGHTS),
        device=DEVICE,
        imgsz=IMG_SIZE,
        batch=BATCH,
        epochs=EPOCHS,
        patience=PATIENCE,
        workers=WORKERS,
        cache="ram",
        amp=True,
        pretrained=True,
        optimizer="auto",
        seed=SEED,
        deterministic=False,
        project=str(PROJECT_DIR),
        name=RUN_NAME,
        exist_ok=False,
        save=True,
        save_period=-1,
        plots=True,
        val=True,

        # 中等强度增强：保留真实物体形态，同时提升背景和尺度泛化。
        hsv_h=0.015,
        hsv_s=0.65,
        hsv_v=0.35,
        degrees=5.0,
        translate=0.10,
        scale=0.40,
        shear=0.0,
        perspective=0.0,
        fliplr=0.5,
        flipud=0.0,
        mosaic=0.75,
        mixup=0.0,
        close_mosaic=10,
    )

    # trainer.save_dir 是本次运行实际采用的目录，避免依赖指标对象的版本差异。
    save_dir = Path(model.trainer.save_dir)
    best_pt = save_dir / "weights" / "best.pt"
    if not best_pt.is_file():
        raise FileNotFoundError(f"训练结束但未找到最佳权重：{best_pt}")
    return best_pt


def evaluate_test(best_pt: Path) -> None:
    """在独立 test 集上评估；workers=0 避免 Windows 页面文件错误。"""
    print(f"\n训练完成，开始测试最佳权重：{best_pt}")
    model = YOLO(str(best_pt))
    metrics = model.val(
        data=str(DATA_YAML),
        split="test",
        device=DEVICE,
        imgsz=IMG_SIZE,
        batch=BATCH,
        workers=0,
        plots=True,
        project=str(PROJECT_DIR),
        name=f"{RUN_NAME}_test",
        exist_ok=False,
    )

    print("\n========== TEST 结果 ==========")
    print(f"Precision:      {metrics.box.mp:.4f}")
    print(f"Recall:         {metrics.box.mr:.4f}")
    print(f"mAP@0.5:        {metrics.box.map50:.4f}")
    print(f"mAP@0.5-0.95:   {metrics.box.map:.4f}")
    print(f"best.pt:        {best_pt}")
    print("================================")


if __name__ == "__main__":
    check_environment()
    configure_torch()
    best = train()
    evaluate_test(best)
