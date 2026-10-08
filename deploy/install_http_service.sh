#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="r76s-yolo-http.service"

echo "[1/5] Checking files and Python environment..."
test -x "$HERE/venv/bin/python"
test -f "$HERE/best_int8.rknn"
test -f "$HERE/r76s_http_service.py"
"$HERE/venv/bin/python" -m py_compile "$HERE/r76s_http_service.py"

echo "[2/5] Stopping the old always-on camera process to release /dev/video0..."
sudo systemctl disable --now r76s-yolo-camera.service 2>/dev/null || true

echo "[3/5] Installing the HTTP service unit..."
SERVICE_USER="$(id -un)"
if [ "$SERVICE_USER" = "root" ]; then
  echo "Run this script as your normal board user (sudo will be requested)." >&2
  exit 1
fi
UNIT_FILE="$(mktemp)"
trap 'rm -f "$UNIT_FILE"' EXIT
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=R76S YOLO RKNN HTTP inference service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$HERE
ExecStart="$HERE/venv/bin/python" "$HERE/r76s_http_service.py" --bind 0.0.0.0 --port 8765
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 0644 "$UNIT_FILE" "/etc/systemd/system/$SERVICE_NAME"
sudo systemctl daemon-reload

echo "[4/5] Starting the new service..."
sudo systemctl enable --now "$SERVICE_NAME"

echo "[5/5] Verifying health..."
sleep 2
sudo systemctl --no-pager --full status "$SERVICE_NAME"
"$HERE/venv/bin/python" -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5)))"

echo "R76S HTTP inference service is ready on port 8765."
