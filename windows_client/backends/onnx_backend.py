from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from .base import Detection, InferenceBackend, InferenceResult


INPUT_SIZE = 640
CLASS_NAMES = (
    "recyclable waste",
    "hazardous waste",
    "kitchen waste",
    "other waste",
)


class OnnxBackend(InferenceBackend):
    def __init__(self, model_path: str | os.PathLike[str]):
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError(
                "缺少 ONNX Runtime。请先运行 install_windows_client.bat 安装客户端依赖。"
            ) from exc

        path = Path(model_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"找不到 Windows ONNX 模型：{path}")

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = max(1, min(8, (os.cpu_count() or 4) // 2))

        available = ort.get_available_providers()
        preference = ["DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
        providers = [provider for provider in preference if provider in available]
        self._session = ort.InferenceSession(str(path), sess_options=options, providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        self._provider = self._session.get_providers()[0]
        self._model_path = path
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "Windows 本地 ONNX"

    @property
    def detail(self) -> str:
        return f"{self._provider} · {self._model_path.name}"

    def is_available(self) -> bool:
        return True

    @staticmethod
    def _letterbox(image: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        height, width = image.shape[:2]
        scale = min(INPUT_SIZE / width, INPUT_SIZE / height)
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        pad_x = (INPUT_SIZE - resized_width) // 2
        pad_y = (INPUT_SIZE - resized_height) // 2
        output = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
        output[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
        return output, scale, pad_x, pad_y

    @staticmethod
    def _dfl(position: np.ndarray) -> np.ndarray:
        position = np.asarray(position, dtype=np.float32)
        batch, channels, height, width = position.shape
        bins = channels // 4
        values = position.reshape(batch, 4, bins, height, width)
        values -= np.max(values, axis=2, keepdims=True)
        values = np.exp(values)
        values /= np.sum(values, axis=2, keepdims=True)
        weights = np.arange(bins, dtype=np.float32).reshape(1, 1, bins, 1, 1)
        return (values * weights).sum(2)

    @classmethod
    def _box_process(cls, position: np.ndarray) -> np.ndarray:
        height, width = position.shape[2:4]
        column, row = np.meshgrid(np.arange(width), np.arange(height))
        grid = np.concatenate(
            (column.reshape(1, 1, height, width), row.reshape(1, 1, height, width)), axis=1
        )
        stride = np.array([INPUT_SIZE // width, INPUT_SIZE // height], dtype=np.float32).reshape(1, 2, 1, 1)
        position = cls._dfl(position)
        xy1 = grid + 0.5 - position[:, 0:2]
        xy2 = grid + 0.5 + position[:, 2:4]
        return np.concatenate((xy1 * stride, xy2 * stride), axis=1)

    @staticmethod
    def _flatten(value: np.ndarray) -> np.ndarray:
        channels = value.shape[1]
        return value.transpose(0, 2, 3, 1).reshape(-1, channels)

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
        if len(boxes) == 0:
            return []
        x1, y1, x2, y2 = boxes.T
        areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
        order = scores.argsort()[::-1]
        keep: list[int] = []
        while order.size:
            index = int(order[0])
            keep.append(index)
            if order.size == 1:
                break
            remaining = order[1:]
            xx1 = np.maximum(x1[index], x1[remaining])
            yy1 = np.maximum(y1[index], y1[remaining])
            xx2 = np.minimum(x2[index], x2[remaining])
            yy2 = np.minimum(y2[index], y2[remaining])
            inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
            union = areas[index] + areas[remaining] - inter
            overlap = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
            order = remaining[np.where(overlap <= threshold)[0]]
        return keep

    @classmethod
    def _postprocess(
        cls,
        outputs: list[np.ndarray],
        confidence: float,
        iou: float,
        scale: float,
        pad_x: int,
        pad_y: int,
        source_width: int,
        source_height: int,
    ) -> list[Detection]:
        if len(outputs) != 9:
            raise RuntimeError(f"模型输出数量应为 9，实际为 {len(outputs)}；模型可能不是当前 YOLO11 导出版本。")

        boxes = []
        probabilities = []
        for branch in range(3):
            boxes.append(cls._flatten(cls._box_process(outputs[branch * 3])))
            probabilities.append(cls._flatten(outputs[branch * 3 + 1]))

        boxes_array = np.concatenate(boxes)
        probability_array = np.concatenate(probabilities)
        class_ids = np.argmax(probability_array, axis=1)
        scores = np.max(probability_array, axis=1)
        selected = scores >= confidence
        boxes_array = boxes_array[selected]
        class_ids = class_ids[selected]
        scores = scores[selected]

        detections: list[Detection] = []
        for class_id in np.unique(class_ids):
            class_mask = class_ids == class_id
            class_boxes = boxes_array[class_mask]
            class_scores = scores[class_mask]
            for kept in cls._nms(class_boxes, class_scores, iou):
                x1, y1, x2, y2 = class_boxes[kept]
                x1 = int(np.clip(round((x1 - pad_x) / scale), 0, source_width - 1))
                y1 = int(np.clip(round((y1 - pad_y) / scale), 0, source_height - 1))
                x2 = int(np.clip(round((x2 - pad_x) / scale), 0, source_width - 1))
                y2 = int(np.clip(round((y2 - pad_y) / scale), 0, source_height - 1))
                if x2 <= x1 or y2 <= y1:
                    continue
                cid = int(class_id)
                detections.append(
                    Detection(cid, CLASS_NAMES[cid], float(class_scores[kept]), (x1, y1, x2, y2))
                )
        detections.sort(key=lambda item: item.confidence, reverse=True)
        return detections

    def infer(self, image: np.ndarray, confidence: float, iou: float) -> InferenceResult:
        if image is None or image.size == 0:
            raise ValueError("输入图像为空。")
        source_height, source_width = image.shape[:2]
        padded, scale, pad_x, pad_y = self._letterbox(image)
        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        input_data = rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        started = time.perf_counter()
        with self._lock:
            outputs = self._session.run(None, {self._input_name: input_data})
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        detections = self._postprocess(
            outputs, confidence, iou, scale, pad_x, pad_y, source_width, source_height
        )
        return InferenceResult(detections, elapsed_ms, self.name)
