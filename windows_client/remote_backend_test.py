from __future__ import annotations

import json
import base64
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backends.r76s_backend import R76SBackend  # noqa: E402
from image_utils import read_image  # noqa: E402


class MockHandler(BaseHTTPRequestHandler):
    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/snapshot"):
            image = np.zeros((48, 64, 3), dtype=np.uint8)
            ok, encoded = cv2.imencode(".jpg", image)
            if not ok:
                self.send_error(500)
                return
            self._json(
                {
                    "ok": True,
                    "device": "mock RK3576 NPU",
                    "elapsed_ms": 11.0,
                    "frame_jpeg_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
                    "detections": [],
                }
            )
            return
        self._json({"ok": True, "detail": "mock RK3576 NPU"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/camera/stop":
            self._json({"ok": True})
            return
        length = int(self.headers["Content-Length"])
        if length <= 100 or self.rfile.read(length)[:2] != b"\xff\xd8":
            self.send_error(400)
            return
        self._json(
            {
                "ok": True,
                "device": "mock RK3576 NPU",
                "elapsed_ms": 12.5,
                "detections": [
                    {
                        "class_id": 0,
                        "label": "recyclable waste",
                        "confidence": 0.75,
                        "box": [10, 20, 100, 200],
                    }
                ],
            }
        )

    def log_message(self, _format: str, *_args) -> None:
        return None


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    backend = R76SBackend(f"http://127.0.0.1:{server.server_port}")
    try:
        if not backend.is_available():
            print("FAILED: mock health check")
            return 1
        image = np.full((240, 320, 3), 128, dtype=np.uint8)
        result = backend.infer(image, 0.55, 0.45)
        if len(result.detections) != 1 or result.detections[0].box != (10, 20, 100, 200):
            print("FAILED: remote response parsing")
            return 1
        camera_image, camera_result = backend.capture_frame(0.55, 0.45)
        if camera_image.shape[:2] != (48, 64) or camera_result.elapsed_ms != 11.0:
            print("FAILED: remote camera response parsing")
            return 1
        backend.stop_camera()
        print(f"backend={result.backend_name} detail={backend.detail}")
        print(f"elapsed_ms={result.elapsed_ms} detections={len(result.detections)}")
        print(f"camera={camera_image.shape[1]}x{camera_image.shape[0]}")
        print("REMOTE_BACKEND_TEST_PASSED")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
