#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ "$(uname -m)" != "aarch64" ]; then
  echo "This setup is for the ARM64 R76S, not the Windows computer." >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3-venv python3-opencv python3-numpy
python3 -m venv --system-site-packages "$HERE/venv"
echo "Download the matching RKNN Lite2 2.3.2 wheel from the official toolkit repository."
echo "Specify it via: bash setup_board.sh /path/to/rknn_toolkit_lite2-*.whl"
WHEEL="${1:-}"
if [ -z "$WHEEL" ] || [ ! -f "$WHEEL" ]; then
  echo "Missing RKNN Lite2 wheel. See docs/DEPLOY_R76S.md." >&2
  exit 1
fi
"$HERE/venv/bin/python" -m pip install "$WHEEL"
"$HERE/venv/bin/python" -c "import cv2,numpy; from rknnlite.api import RKNNLite; print('BOARD_ENVIRONMENT_READY')"
