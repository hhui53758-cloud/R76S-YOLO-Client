#!/usr/bin/env python3
"""Small LAN-only HTTP inference service for the NanoPi R76S RK3576 NPU."""

from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np


ROOT = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.join(ROOT, "rknn_model_zoo", "examples", "yolo11", "python")
sys.path.insert(0, DEMO_DIR)

import yolo11  # noqa: E402
from py_utils.coco_utils import COCO_test_helper  # noqa: E402
from py_utils.rknn_executor import RKNN_model_container  # noqa: E402


MAX_IMAGE_BYTES = 16 * 1024 * 1024


class NpuEngine:
    def __init__(self, model_path: str):
        self.model_path = os.path.abspath(model_path)
        self.model = RKNN_model_container(self.model_path)
        self.lock = threading.Lock()
        self.started_at = time.time()
        self.request_count = 0
        self.camera_lock = threading.Lock()
        self.camera = None

    def infer(self, source: np.ndarray, confidence: float, iou: float) -> dict:
        helper = COCO_test_helper(enable_letter_box=True)
        image = helper.letter_box(
            im=source.copy(),
            new_shape=(yolo11.IMG_SIZE[1], yolo11.IMG_SIZE[0]),
            pad_color=(0, 0, 0),
        )
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        input_data = np.expand_dims(image, axis=0)
        started = time.perf_counter()
        with self.lock:
            yolo11.OBJ_THRESH = confidence
            yolo11.NMS_THRESH = iou
            outputs = self.model.run([input_data])
            boxes, classes, scores = yolo11.post_process(outputs)
            self.request_count += 1
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        detections = []
        if boxes is not None:
            real_boxes = helper.get_real_box(boxes)
            height, width = source.shape[:2]
            for box, class_id, score in zip(real_boxes, classes, scores):
                x1, y1, x2, y2 = [int(round(float(value))) for value in box]
                x1 = max(0, min(width - 1, x1))
                y1 = max(0, min(height - 1, y1))
                x2 = max(0, min(width - 1, x2))
                y2 = max(0, min(height - 1, y2))
                cid = int(class_id)
                if x2 <= x1 or y2 <= y1:
                    continue
                detections.append(
                    {
                        "class_id": cid,
                        "label": yolo11.CLASSES[cid],
                        "confidence": float(score),
                        "box": [x1, y1, x2, y2],
                    }
                )
        detections.sort(key=lambda item: item["confidence"], reverse=True)
        return {
            "ok": True,
            "device": "RK3576 NPU · best_int8.rknn",
            "elapsed_ms": elapsed_ms,
            "image": {"width": int(source.shape[1]), "height": int(source.shape[0])},
            "detections": detections,
        }

    def camera_frame(self, confidence: float, iou: float) -> dict:
        with self.camera_lock:
            if self.camera is None or not self.camera.isOpened():
                camera = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
                camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                camera.set(cv2.CAP_PROP_FPS, 25)
                if not camera.isOpened():
                    camera.release()
                    raise RuntimeError("cannot open /dev/video0")
                self.camera = camera
            ok, frame = self.camera.read()
        if not ok:
            raise RuntimeError("camera frame read failed")
        result = self.infer(frame, confidence, iou)
        encoded_ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not encoded_ok:
            raise RuntimeError("camera frame JPEG encoding failed")
        result["frame_jpeg_base64"] = base64.b64encode(encoded.tobytes()).decode("ascii")
        return result

    def stop_camera(self) -> None:
        with self.camera_lock:
            if self.camera is not None:
                self.camera.release()
                self.camera = None

    def close(self) -> None:
        self.stop_camera()
        self.model.release()


class ApiHandler(BaseHTTPRequestHandler):
    engine: NpuEngine
    server_version = "R76S-YOLO/1.0"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "detail": "RK3576 NPU 在线 · best_int8.rknn",
                    "service": "r76s-yolo-http",
                },
            )
            return
        if parsed.path == "/status":
            self._send_json(
                200,
                {
                    "ok": True,
                    "device": "RK3576 NPU",
                    "model": os.path.basename(self.engine.model_path),
                    "requests": self.engine.request_count,
                    "uptime_seconds": int(time.time() - self.engine.started_at),
                },
            )
            return
        if parsed.path == "/snapshot":
            try:
                query = parse_qs(parsed.query)
                confidence = float(query.get("confidence", ["0.55"])[0])
                iou = float(query.get("iou", ["0.45"])[0])
                if not 0.01 <= confidence <= 0.99 or not 0.01 <= iou <= 0.99:
                    raise ValueError("confidence/iou must be between 0.01 and 0.99")
                self._send_json(200, self.engine.camera_frame(confidence, iou))
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": f"camera failed: {exc}"})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/camera/stop":
            self.engine.stop_camera()
            self._send_json(200, {"ok": True})
            return
        if self.path != "/detect":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_IMAGE_BYTES:
                raise ValueError("image body is empty or too large")
            confidence = float(self.headers.get("X-Confidence", "0.55"))
            iou = float(self.headers.get("X-Iou", "0.45"))
            if not 0.01 <= confidence <= 0.99 or not 0.01 <= iou <= 0.99:
                raise ValueError("confidence/iou must be between 0.01 and 0.99")
            body = self.rfile.read(length)
            image = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("request body is not a supported image")
            self._send_json(200, self.engine.infer(image, confidence, iou))
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": f"inference failed: {exc}"})

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="R76S RKNN HTTP inference service")
    parser.add_argument("--model", default=os.path.join(ROOT, "best_int8.rknn"))
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    engine = NpuEngine(args.model)
    ApiHandler.engine = engine
    server = ThreadingHTTPServer((args.bind, args.port), ApiHandler)

    def request_shutdown(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    print(f"R76S YOLO HTTP service listening on {args.bind}:{args.port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        engine.close()


if __name__ == "__main__":
    main()
