#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/rknn_model_zoo/examples/yolo11/python"
"$HERE/venv/bin/python" yolo11.py \
  --model_path "$HERE/best_int8.rknn" \
  --target rk3576 \
  --img_folder "$HERE/test_images" \
  --img_save
echo "Annotated image is in: $PWD/result/"
