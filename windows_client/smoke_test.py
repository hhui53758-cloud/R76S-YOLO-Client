from __future__ import annotations

import sys
import numpy as np
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backends.onnx_backend import OnnxBackend  # noqa: E402
from image_utils import read_image  # noqa: E402


def main() -> int:
    model = ROOT.parent / "deploy" / "best.onnx"
    backend = OnnxBackend(model)
    image = np.full((720, 1280, 3), 128, dtype=np.uint8)
    result = backend.infer(image, confidence=0.55, iou=0.45)

    print(f"backend={backend.detail}")
    print(f"image={image.shape[1]}x{image.shape[0]}")
    print(f"inference_ms={result.elapsed_ms:.2f}")
    print(f"detections={len(result.detections)}")
    for detection in result.detections:
        print(
            f"class={detection.class_id} label={detection.label} "
            f"confidence={detection.confidence:.6f} box={detection.box}"
        )

    for detection in result.detections:
        x1, y1, x2, y2 = detection.box
        if not (0 <= detection.class_id < 4 and 0 <= detection.confidence <= 1
                and 0 <= x1 < x2 < 1280 and 0 <= y1 < y2 < 720):
            raise AssertionError("Invalid model output")
    print("SMOKE_TEST_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
