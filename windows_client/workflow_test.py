from __future__ import annotations

import csv
import queue
import sys
import threading
from pathlib import Path

import cv2
import numpy as np
import tempfile
import atexit


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import DetectionClient  # noqa: E402
from backends.onnx_backend import OnnxBackend  # noqa: E402
from image_utils import read_image  # noqa: E402


def main() -> int:
    temporary = tempfile.TemporaryDirectory(prefix="r76s-workflow-")
    atexit.register(temporary.cleanup)
    test_root = Path(temporary.name)
    source_dir = test_root / "source"
    batch_dir = test_root / "batch"
    source_dir.mkdir(parents=True, exist_ok=True)
    image = np.full((720, 1280, 3), 128, dtype=np.uint8)
    cv2.imencode(".jpg", image)[1].tofile(str(source_dir / "sample.jpg"))

    client = DetectionClient.__new__(DetectionClient)
    client.stop_event = threading.Event()
    client.events = queue.Queue()
    client.capture = None
    backend = OnnxBackend(ROOT.parent / "deploy" / "best.onnx")

    client._batch_folder_loop(source_dir, batch_dir, [source_dir / "sample.jpg"], backend, 0.55, 0.45, 1)
    result_image = batch_dir / "sample_detected.jpg"
    result_csv = batch_dir / "detection_records.csv"
    if not result_image.exists() or not result_csv.exists():
        print("FAILED: batch outputs are missing")
        return 1
    with result_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or any(row[3] not in {"可回收物", "有害垃圾", "厨余垃圾", "其他垃圾", ""} for row in rows[1:]):
        print("FAILED: batch CSV content is incorrect")
        return 1

    video_source = test_root / "source.mp4"
    video_result = test_root / "source_detected.mp4"
    writer = cv2.VideoWriter(str(video_source), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 180))
    frame = cv2.resize(image, (320, 180))
    for _ in range(3):
        writer.write(frame)
    writer.release()

    capture = cv2.VideoCapture(str(video_source))
    client.capture = capture
    client.stop_event.clear()
    client._capture_loop(capture, "workflow-test", backend, 0.55, 0.45, 2, video_result)
    check = cv2.VideoCapture(str(video_result))
    frame_count = int(check.get(cv2.CAP_PROP_FRAME_COUNT))
    check.release()
    backend.close()
    if frame_count != 3:
        print(f"FAILED: expected 3 saved video frames, got {frame_count}")
        return 1

    print(f"batch_image={result_image}")
    print(f"batch_csv={result_csv}")
    print(f"video={video_result} frames={frame_count}")
    print("WORKFLOW_TEST_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
