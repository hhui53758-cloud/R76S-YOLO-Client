#!/usr/bin/env python3
"""Run the custom YOLO11 RKNN model on the R76S USB camera."""

import argparse
import os
import sys
import time

import cv2
import numpy as np


ROOT = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.join(ROOT, "rknn_model_zoo", "examples", "yolo11", "python")
sys.path.insert(0, DEMO_DIR)

from yolo11 import IMG_SIZE, draw, post_process  # noqa: E402
from py_utils.coco_utils import COCO_test_helper  # noqa: E402
from py_utils.rknn_executor import RKNN_model_container  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="R76S USB camera YOLO11 detector")
    parser.add_argument("--model", default=os.path.join(ROOT, "best_int8.rknn"))
    parser.add_argument("--camera", default="/dev/video0")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--save", default=os.path.join(ROOT, "camera_result.jpg"))
    parser.add_argument("--frames", type=int, default=0,
                        help="0 means keep running; otherwise stop after N frames")
    args = parser.parse_args()

    model = RKNN_model_container(args.model)
    camera = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    camera.set(cv2.CAP_PROP_FPS, 25)
    if not camera.isOpened():
        model.release()
        raise RuntimeError(f"Cannot open camera: {args.camera}")

    helper = COCO_test_helper(enable_letter_box=True)
    count = 0
    last_report = time.perf_counter()
    report_frames = 0
    print("Camera detection started. Press Ctrl+C to stop.")

    try:
        while True:
            ok, source = camera.read()
            if not ok:
                print("Camera frame read failed; retrying...")
                continue

            image = helper.letter_box(
                im=source.copy(),
                new_shape=(IMG_SIZE[1], IMG_SIZE[0]),
                pad_color=(0, 0, 0),
            )
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            outputs = model.run([np.expand_dims(image, axis=0)])
            boxes, classes, scores = post_process(outputs)

            annotated = source.copy()
            if boxes is not None:
                draw(annotated, helper.get_real_box(boxes), scores, classes)
            cv2.imwrite(args.save, annotated)

            count += 1
            report_frames += 1
            now = time.perf_counter()
            if now - last_report >= 2.0:
                fps = report_frames / (now - last_report)
                detections = 0 if boxes is None else len(boxes)
                print(f"frames={count} fps={fps:.2f} detections={detections} saved={args.save}")
                last_report = now
                report_frames = 0

            if args.frames and count >= args.frames:
                break
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        camera.release()
        model.release()


if __name__ == "__main__":
    main()
