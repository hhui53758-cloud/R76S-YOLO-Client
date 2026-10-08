from __future__ import annotations

import json
import base64
import time
import urllib.error
import urllib.request

import cv2
import numpy as np

from .base import Detection, InferenceBackend, InferenceResult


CLASS_NAMES = (
    "recyclable waste",
    "hazardous waste",
    "kitchen waste",
    "other waste",
)


class R76SBackend(InferenceBackend):
    """Send images to the RK3576 NPU service over the private LAN."""

    def __init__(self, base_url: str = "http://192.168.137.47:8765", timeout: float = 0.8):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._last_ok = 0.0
        self._detail = "等待连接 R76S"

    @property
    def name(self) -> str:
        return "R76S 远程 NPU"

    @property
    def detail(self) -> str:
        return self._detail

    def is_available(self) -> bool:
        request = urllib.request.Request(f"{self.base_url}/health", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self._detail = payload.get("detail", "RK3576 NPU 在线")
            self._last_ok = time.monotonic()
            return payload.get("ok", False) is True
        except (OSError, ValueError, urllib.error.URLError):
            self._detail = "未连接 R76S"
            return False

    def infer(self, image: np.ndarray, confidence: float, iou: float) -> InferenceResult:
        if image is None or image.size == 0:
            raise ValueError("输入图像为空。")
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise RuntimeError("发送到 R76S 前无法编码图片。")
        request = urllib.request.Request(
            f"{self.base_url}/detect",
            data=encoded.tobytes(),
            headers={
                "Content-Type": "image/jpeg",
                "X-Confidence": f"{confidence:.6f}",
                "X-Iou": f"{iou:.6f}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(10.0, self.timeout)) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                reason = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
            except (ValueError, OSError):
                reason = str(exc)
            raise RuntimeError(f"R76S 推理失败：{reason}") from exc
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise RuntimeError(f"无法连接 R76S 推理服务：{exc}") from exc

        detections = self._parse_detections(payload)
        self._detail = str(payload.get("device", "RK3576 NPU 在线"))
        self._last_ok = time.monotonic()
        return InferenceResult(
            detections=detections,
            elapsed_ms=float(payload.get("elapsed_ms", 0.0)),
            backend_name=self.name,
        )

    @staticmethod
    def _parse_detections(payload: dict) -> list[Detection]:
        detections: list[Detection] = []
        for item in payload.get("detections", []):
            class_id = int(item["class_id"])
            box_values = tuple(int(value) for value in item["box"])
            if len(box_values) != 4:
                raise RuntimeError("R76S 返回了无效的检测框。")
            label = item.get("label")
            if not label and 0 <= class_id < len(CLASS_NAMES):
                label = CLASS_NAMES[class_id]
            detections.append(
                Detection(
                    class_id=class_id,
                    label=str(label or class_id),
                    confidence=float(item["confidence"]),
                    box=box_values,
                )
            )
        return detections

    def capture_frame(self, confidence: float, iou: float) -> tuple[np.ndarray, InferenceResult]:
        url = f"{self.base_url}/snapshot?confidence={confidence:.6f}&iou={iou:.6f}"
        try:
            with urllib.request.urlopen(url, timeout=max(10.0, self.timeout)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            raw = base64.b64decode(payload["frame_jpeg_base64"], validate=True)
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("R76S 返回的摄像头图像无效。")
        except urllib.error.HTTPError as exc:
            try:
                reason = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
            except (ValueError, OSError):
                reason = str(exc)
            raise RuntimeError(f"无法读取 R76S 摄像头：{reason}") from exc
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            raise RuntimeError(f"无法读取 R76S 摄像头：{exc}") from exc
        result = InferenceResult(
            detections=self._parse_detections(payload),
            elapsed_ms=float(payload.get("elapsed_ms", 0.0)),
            backend_name=self.name,
        )
        self._detail = str(payload.get("device", "RK3576 NPU 在线"))
        self._last_ok = time.monotonic()
        return image, result

    def stop_camera(self) -> None:
        request = urllib.request.Request(f"{self.base_url}/camera/stop", data=b"", method="POST")
        try:
            urllib.request.urlopen(request, timeout=self.timeout).close()
        except (OSError, urllib.error.URLError):
            pass
