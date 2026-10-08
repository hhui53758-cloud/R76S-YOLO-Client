from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backends.base import Detection


CLASS_NAMES_ZH = ("可回收物", "有害垃圾", "厨余垃圾", "其他垃圾")
COLORS = (
    (52, 152, 219),
    (53, 53, 220),
    (58, 175, 92),
    (125, 125, 125),
)


def _load_chinese_font(size: int = 20):
    candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    )
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return None


CHINESE_FONT = _load_chinese_font()


def read_image(path: str | Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图片：{path}")
    return image


def write_image(path: str | Path, image: np.ndarray) -> None:
    suffix = Path(path).suffix.lower() or ".jpg"
    extension = suffix if suffix in {".jpg", ".jpeg", ".png", ".bmp"} else ".jpg"
    ok, encoded = cv2.imencode(extension, image)
    if not ok:
        raise ValueError(f"无法编码图片：{path}")
    encoded.tofile(str(path))


def annotate(image: np.ndarray, detections: list[Detection] | tuple[Detection, ...]) -> np.ndarray:
    output = image.copy()
    labels: list[tuple[int, int, tuple[int, int, int], str]] = []
    for detection in detections:
        x1, y1, x2, y2 = detection.box
        color = COLORS[detection.class_id % len(COLORS)]
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        class_name = (
            CLASS_NAMES_ZH[detection.class_id]
            if 0 <= detection.class_id < len(CLASS_NAMES_ZH)
            else detection.label
        )
        text = f"{class_name} {detection.confidence:.2f}"
        if CHINESE_FONT is not None:
            labels.append((x1, y1, color, text))
            continue
        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        label_top = max(0, y1 - text_height - baseline - 6)
        cv2.rectangle(output, (x1, label_top), (x1 + text_width + 8, y1), color, -1)
        cv2.putText(
            output,
            text,
            (x1 + 4, max(text_height + 2, y1 - baseline - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    if labels and CHINESE_FONT is not None:
        pil_image = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)
        for x1, y1, color, text in labels:
            left, top, right, bottom = draw.textbbox((0, 0), text, font=CHINESE_FONT)
            text_width = right - left
            text_height = bottom - top
            label_top = max(0, y1 - text_height - 8)
            rgb_color = (color[2], color[1], color[0])
            draw.rectangle((x1, label_top, x1 + text_width + 8, y1), fill=rgb_color)
            draw.text((x1 + 4, label_top + 2 - top), text, font=CHINESE_FONT, fill=(255, 255, 255))
        output = cv2.cvtColor(np.asarray(pil_image), cv2.COLOR_RGB2BGR)
    return output
