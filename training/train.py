"""Portable adaptation of the recorded standard YOLO11n training run."""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='0', help='CUDA index or cpu')
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--epochs', type=int, default=130)
    parser.add_argument('--weights', default='yolo11n.pt')
    parser.add_argument('--data', type=Path, default=ROOT / 'datasets/trash')
    parser.add_argument('--test-only', action='store_true')
    args = parser.parse_args()
    import torch
    from ultralytics import YOLO
    data = args.data.resolve()
    if not all((data / 'images' / split).is_dir() and (data / 'labels' / split).is_dir() for split in ('train', 'val', 'test')):
        raise FileNotFoundError('Expected images/{train,val,test} and labels/{train,val,test}; see training/DATASET.md')
    if args.device != 'cpu' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; install a suitable PyTorch build or use --device cpu --batch 4')
    # Absolute dataset root avoids Ultralytics global datasets_dir ambiguity.
    from ultralytics.utils import YAML
    config = ROOT / 'training/trash.yaml'
    payload = YAML.load(config)
    payload['path'] = str(data)
    generated = ROOT / 'training/generated_data.yaml'
    YAML.save(generated, payload)
    if args.device != 'cpu':
        torch.set_float32_matmul_precision('high')
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    name = f'fast_n_{datetime.now():%Y%m%d_%H%M%S}'
    model = YOLO(args.weights)
    if not args.test_only:
        model.train(data=str(generated), device=args.device, batch=args.batch,
                    epochs=args.epochs, imgsz=640, patience=18, workers=2,
                    cache='ram', amp=True, pretrained=True, optimizer='auto',
                    seed=0, deterministic=False, project=str(ROOT / 'training_runs'),
                    name=name, exist_ok=False, save=True, save_period=-1, plots=True, val=True,
                    hsv_h=0.015, hsv_s=0.65, hsv_v=0.35, degrees=5.0, translate=0.10,
                    scale=0.40, shear=0.0, perspective=0.0, fliplr=0.5,
                    flipud=0.0, mosaic=0.75, mixup=0.0, close_mosaic=10)
        model = YOLO(str(Path(model.trainer.save_dir) / 'weights/best.pt'))
    metrics = model.val(data=str(generated), split='test', device=args.device,
                        imgsz=640, batch=args.batch, workers=0, plots=True,
                        project=str(ROOT / 'training_runs'), name=name + '_test')
    print({'precision': metrics.box.mp, 'recall': metrics.box.mr,
           'mAP50': metrics.box.map50, 'mAP50_95': metrics.box.map})

if __name__ == '__main__':
    main()
