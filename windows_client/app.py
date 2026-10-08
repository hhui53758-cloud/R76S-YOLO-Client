from __future__ import annotations

import csv
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from backends.base import InferenceResult
from backends.onnx_backend import OnnxBackend
from backends.r76s_backend import R76SBackend
from image_utils import CLASS_NAMES_ZH, annotate, read_image, write_image


APP_DIR = Path(__file__).resolve().parent


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return (Path(sys._MEIPASS) / relative).resolve()
    return (APP_DIR.parent / relative).resolve()


DEFAULT_MODEL = Path(os.environ.get("R76S_MODEL_PATH", str(resource_path("deploy/best.onnx")))).expanduser()
SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".bmp"}
SUPPORTED_VIDEOS = {".mp4", ".avi", ".mkv", ".mov", ".wmv"}


class DetectionClient:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("垃圾分类目标检测客户端")
        self.settings_path = Path(
            os.environ.get("LOCALAPPDATA", str(Path.home()))
        ) / "R76S-YOLO-Client" / "settings.json"
        saved_settings = self._load_settings()
        self.root.geometry(str(saved_settings.get("geometry", "1260x800")))
        self.root.minsize(1050, 680)

        self.local_backend: OnnxBackend | None = None
        self.remote_backend = R76SBackend(os.environ.get("R76S_SERVER_URL", "http://192.168.137.47:8765"))
        self.backend_ready = False
        self.stop_event = threading.Event()
        self.app_stop_event = threading.Event()
        self.capture: cv2.VideoCapture | None = None
        self.worker: threading.Thread | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.current_source = ""
        self.current_original = None
        self.current_annotated = None
        self.current_result: InferenceResult | None = None
        self.folder_items: list[Path] = []
        self.folder_index = -1
        self.view_generation = 0
        self.last_frame_started = 0.0

        backend_setting = str(saved_settings.get("backend", "auto"))
        if backend_setting not in {"auto", "local", "remote"}:
            backend_setting = "auto"
        try:
            confidence_setting = min(0.95, max(0.05, float(saved_settings.get("confidence", 0.55))))
        except (TypeError, ValueError):
            confidence_setting = 0.55
        try:
            iou_setting = min(0.90, max(0.10, float(saved_settings.get("iou", 0.45))))
        except (TypeError, ValueError):
            iou_setting = 0.45
        self.backend_choice = tk.StringVar(value=backend_setting)
        self.confidence = tk.DoubleVar(value=confidence_setting)
        self.iou = tk.DoubleVar(value=iou_setting)
        self.backend_choice_value = backend_setting
        self.confidence_value = confidence_setting
        self.iou_value = iou_setting
        self.remote_available = False
        self.status_text = tk.StringVar(value="正在加载 Windows 模型……")
        self.backend_text = tk.StringVar(value="本地模型初始化中")
        self.performance_text = tk.StringVar(value="推理：-- ms　FPS：--")
        self.source_text = tk.StringVar(value="尚未选择输入")
        self.count_vars = [tk.StringVar(value="0") for _ in CLASS_NAMES_ZH]

        self._configure_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(60, self._drain_events)
        threading.Thread(target=self._load_backend, daemon=True).start()
        threading.Thread(target=self._monitor_remote, daemon=True).start()

    def _load_settings(self) -> dict[str, object]:
        try:
            if self.settings_path.exists():
                value = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def _save_settings(self) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings = {
                "backend": self.backend_choice_value,
                "confidence": self.confidence_value,
                "iou": self.iou_value,
                "geometry": self.root.geometry(),
            }
            self.settings_path.write_text(
                json.dumps(settings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"), foreground="#172033")
        style.configure("Heading.TLabel", font=("Microsoft YaHei UI", 11, "bold"), foreground="#23324d")
        style.configure("Info.TLabel", font=("Microsoft YaHei UI", 9), foreground="#53627a")
        style.configure("Count.TLabel", font=("Microsoft YaHei UI", 18, "bold"), foreground="#1769aa")
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(12, 8))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(9, 7))
        style.configure("TRadiobutton", font=("Microsoft YaHei UI", 9))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="垃圾分类目标检测客户端", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.backend_text, style="Info.TLabel").pack(side=tk.RIGHT, pady=(8, 0))

        toolbar = ttk.LabelFrame(outer, text="输入与设备", padding=9)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        input_row = ttk.Frame(toolbar)
        input_row.pack(fill=tk.X)
        for text, command in (
            ("打开图片", self.open_image),
            ("打开文件夹", self.open_folder),
            ("打开视频", self.open_video),
            ("本机摄像头", self.open_camera),
            ("R76S 摄像头", self.open_remote_camera),
            ("双端对比", self.compare_backends),
            ("批量处理文件夹", self.batch_process_folder),
            ("处理并保存视频", self.process_and_save_video),
        ):
            ttk.Button(input_row, text=text, command=command).pack(side=tk.LEFT, padx=(0, 6))

        action_row = ttk.Frame(toolbar)
        action_row.pack(fill=tk.X, pady=(7, 0))
        for text, command in (
            ("停止", self.stop_stream),
            ("刷新画面", self.reset_view),
            ("保存当前结果", self.save_current),
            ("导出检测记录", self.export_csv),
        ):
            ttk.Button(action_row, text=text, command=command).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Label(action_row, text="推理设备：").pack(side=tk.LEFT, padx=(12, 2))
        for label, value in (("自动", "auto"), ("Windows", "local"), ("R76S", "remote")):
            ttk.Radiobutton(
                action_row, text=label, value=value, variable=self.backend_choice, command=self._backend_changed
            ).pack(side=tk.LEFT, padx=3)

        content = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True)
        viewer_panel = ttk.Frame(content)
        side_panel = ttk.Frame(content, width=300)
        content.add(viewer_panel, weight=4)
        content.add(side_panel, weight=1)

        viewer_header = ttk.Frame(viewer_panel)
        viewer_header.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(viewer_header, textvariable=self.source_text, style="Info.TLabel").pack(side=tk.LEFT)
        ttk.Label(viewer_header, textvariable=self.performance_text, style="Info.TLabel").pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(viewer_panel, bg="#111827", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._redraw_current())
        self.canvas_message = self.canvas.create_text(
            400,
            280,
            text="打开图片、视频或摄像头开始检测",
            fill="#cbd5e1",
            font=("Microsoft YaHei UI", 14),
        )

        nav = ttk.Frame(viewer_panel)
        nav.pack(fill=tk.X, pady=(7, 0))
        self.previous_button = ttk.Button(nav, text="◀ 上一张", command=self.previous_item, state=tk.DISABLED)
        self.previous_button.pack(side=tk.LEFT)
        self.next_button = ttk.Button(nav, text="下一张 ▶", command=self.next_item, state=tk.DISABLED)
        self.next_button.pack(side=tk.LEFT, padx=6)
        ttk.Label(nav, textvariable=self.status_text, style="Info.TLabel").pack(side=tk.RIGHT)

        stats = ttk.LabelFrame(side_panel, text="检测统计", padding=12)
        stats.pack(fill=tk.X, padx=(10, 0), pady=(0, 10))
        for index, name in enumerate(CLASS_NAMES_ZH):
            row = ttk.Frame(stats)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text=name, style="Heading.TLabel").pack(side=tk.LEFT)
            ttk.Label(row, textvariable=self.count_vars[index], style="Count.TLabel").pack(side=tk.RIGHT)

        settings = ttk.LabelFrame(side_panel, text="检测参数", padding=12)
        settings.pack(fill=tk.X, padx=(10, 0), pady=(0, 10))
        ttk.Label(settings, text="置信度阈值", style="Heading.TLabel").pack(anchor=tk.W)
        confidence_scale = ttk.Scale(settings, from_=0.05, to=0.95, variable=self.confidence, orient=tk.HORIZONTAL)
        confidence_scale.pack(fill=tk.X, pady=(4, 0))
        self.confidence_label = ttk.Label(
            settings, text=f"{self.confidence_value:.2f}", style="Info.TLabel"
        )
        self.confidence_label.pack(anchor=tk.E)
        confidence_scale.configure(command=self._confidence_changed)

        ttk.Label(settings, text="IOU 阈值", style="Heading.TLabel").pack(anchor=tk.W, pady=(10, 0))
        iou_scale = ttk.Scale(settings, from_=0.10, to=0.90, variable=self.iou, orient=tk.HORIZONTAL)
        iou_scale.pack(fill=tk.X, pady=(4, 0))
        self.iou_label = ttk.Label(settings, text=f"{self.iou_value:.2f}", style="Info.TLabel")
        self.iou_label.pack(anchor=tk.E)
        iou_scale.configure(command=self._iou_changed)

        connection = ttk.LabelFrame(side_panel, text="运行状态", padding=12)
        connection.pack(fill=tk.X, padx=(10, 0))
        ttk.Label(connection, textvariable=self.backend_text, wraplength=260, style="Info.TLabel").pack(anchor=tk.W)
        ttk.Separator(connection).pack(fill=tk.X, pady=8)
        ttk.Label(
            connection,
            text="R76S HTTP 客户端已就绪。板端服务安装后，自动模式会在线使用 NPU、离线回退 Windows。",
            wraplength=260,
            style="Info.TLabel",
        ).pack(anchor=tk.W)

    def _load_backend(self) -> None:
        try:
            backend = OnnxBackend(DEFAULT_MODEL)
            self.events.put(("backend_ready", backend))
        except Exception as exc:
            self.events.put(("error", f"Windows 模型加载失败：{exc}"))

    def _monitor_remote(self) -> None:
        while not self.app_stop_event.is_set():
            available = self.remote_backend.is_available()
            self.remote_available = available
            self.events.put(("remote_status", available))
            if self.app_stop_event.wait(5.0):
                break

    def _drain_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "backend_ready":
                    self.local_backend = payload  # type: ignore[assignment]
                    self.backend_ready = True
                    self.backend_text.set(f"Windows 就绪 · {self.local_backend.detail}")
                    self.status_text.set("模型已加载，可以开始检测")
                elif event == "frame":
                    frame, result, source, generation = payload  # type: ignore[misc]
                    if generation == self.view_generation:
                        self._present_result(frame, result, source)
                elif event == "status":
                    if isinstance(payload, tuple):
                        message, generation = payload
                        if generation == self.view_generation:
                            self.status_text.set(str(message))
                    else:
                        self.status_text.set(str(payload))
                elif event == "stream_end":
                    message, generation = payload  # type: ignore[misc]
                    if generation == self.view_generation:
                        self.status_text.set(str(message))
                        self.stop_event.set()
                elif event == "job_done":
                    title, message, generation = payload  # type: ignore[misc]
                    if generation == self.view_generation:
                        self.status_text.set(str(message))
                        messagebox.showinfo(str(title), str(message))
                elif event == "comparison":
                    frame, local_result, remote_result, source, summary, generation = payload  # type: ignore[misc]
                    if generation == self.view_generation:
                        self._present_comparison(
                            frame, local_result, remote_result, source, str(summary)
                        )
                elif event == "remote_status":
                    if bool(payload):
                        self.backend_text.set(f"R76S 在线 · {self.remote_backend.detail}")
                    elif self.local_backend is not None:
                        self.backend_text.set(f"Windows 就绪 · {self.local_backend.detail}")
                elif event == "error":
                    self.status_text.set("发生错误")
                    messagebox.showerror("运行错误", str(payload))
        except queue.Empty:
            pass
        self.root.after(60, self._drain_events)

    def _selected_backend(self):
        choice = self.backend_choice_value
        if choice == "remote":
            if not self.remote_available:
                raise RuntimeError("R76S 推理服务尚未接入，请先选择 Windows 或自动模式。")
            return self.remote_backend
        if choice == "auto" and self.remote_available:
            return self.remote_backend
        if self.local_backend is None:
            raise RuntimeError("Windows 模型仍在加载，请稍候。")
        return self.local_backend

    def _backend_changed(self) -> None:
        self.backend_choice_value = self.backend_choice.get()
        if self.backend_choice_value == "remote" and not self.remote_available:
            self.status_text.set("R76S 服务尚未接入；可切回自动或 Windows")
        elif self.local_backend is not None:
            self.status_text.set("推理设备设置已更新")

    def _confidence_changed(self, value: str) -> None:
        self.confidence_value = float(value)
        self.confidence_label.configure(text=f"{self.confidence_value:.2f}")

    def _iou_changed(self, value: str) -> None:
        self.iou_value = float(value)
        self.iou_label.configure(text=f"{self.iou_value:.2f}")

    def _infer(
        self, frame, source: str, backend, confidence: float, iou: float, generation: int
    ) -> None:
        try:
            result = backend.infer(frame, confidence, iou)
            output = annotate(frame, list(result.detections))
            self.events.put(("frame", (output, result, source, generation)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _infer_image_async(self, image, source: str) -> None:
        self.stop_stream()
        self.view_generation += 1
        generation = self.view_generation
        self.current_original = image.copy()
        self.status_text.set("正在推理……")
        try:
            backend = self._selected_backend()
        except Exception as exc:
            messagebox.showerror("推理设备不可用", str(exc))
            return
        self.worker = threading.Thread(
            target=self._infer,
            args=(image.copy(), source, backend, self.confidence_value, self.iou_value, generation),
            daemon=True,
        )
        self.worker.start()

    def open_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择图片", filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp"), ("全部文件", "*.*")]
        )
        if not path:
            return
        try:
            self.folder_items = [Path(path)]
            self.folder_index = 0
            self._update_navigation()
            self._infer_image_async(read_image(path), str(path))
        except Exception as exc:
            messagebox.showerror("图片错误", str(exc))

    def open_folder(self) -> None:
        directory = filedialog.askdirectory(title="选择图片文件夹")
        if not directory:
            return
        items = sorted(path for path in Path(directory).rglob("*") if path.suffix.lower() in SUPPORTED_IMAGES)
        if not items:
            messagebox.showinfo("没有图片", "所选文件夹中没有支持的图片。")
            return
        self.folder_items = items
        self.folder_index = 0
        self._update_navigation()
        self._load_folder_item()

    def _load_folder_item(self) -> None:
        if not (0 <= self.folder_index < len(self.folder_items)):
            return
        path = self.folder_items[self.folder_index]
        try:
            self._infer_image_async(read_image(path), str(path))
            self._update_navigation()
        except Exception as exc:
            messagebox.showerror("图片错误", str(exc))

    def previous_item(self) -> None:
        if self.folder_index > 0:
            self.folder_index -= 1
            self._load_folder_item()

    def next_item(self) -> None:
        if self.folder_index + 1 < len(self.folder_items):
            self.folder_index += 1
            self._load_folder_item()

    def _update_navigation(self) -> None:
        count = len(self.folder_items)
        self.previous_button.configure(state=tk.NORMAL if self.folder_index > 0 else tk.DISABLED)
        self.next_button.configure(
            state=tk.NORMAL if 0 <= self.folder_index < count - 1 else tk.DISABLED
        )
        if count > 1:
            self.source_text.set(f"文件夹图片 {self.folder_index + 1}/{count}")

    def open_video(self) -> None:
        path = filedialog.askopenfilename(
            title="选择视频", filetypes=[("视频", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("全部文件", "*.*")]
        )
        if path:
            self._start_capture(path, f"视频：{Path(path).name}")

    def process_and_save_video(self) -> None:
        source = filedialog.askopenfilename(
            title="选择要处理的视频",
            filetypes=[("视频", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("全部文件", "*.*")],
        )
        if not source:
            return
        destination = filedialog.asksaveasfilename(
            title="保存检测后的视频",
            defaultextension=".mp4",
            initialfile=f"{Path(source).stem}_detected.mp4",
            filetypes=[("MP4 视频", "*.mp4")],
        )
        if not destination:
            return
        if Path(source).resolve() == Path(destination).resolve():
            messagebox.showerror("路径错误", "输出视频不能覆盖原视频，请选择另一个文件名。")
            return
        self._start_capture(
            source,
            f"视频保存：{Path(source).name}",
            save_path=Path(destination),
        )

    def open_camera(self) -> None:
        self._start_capture(0, "Windows 本机摄像头")

    def open_remote_camera(self) -> None:
        self.stop_stream()
        if not self.remote_backend.is_available():
            messagebox.showerror("R76S 不可用", "尚未连接到 R76S HTTP 推理服务。")
            return
        self.view_generation += 1
        generation = self.view_generation
        self.stop_event.clear()
        self.folder_items = []
        self.folder_index = -1
        self._update_navigation()
        self.source_text.set("R76S USB 摄像头")
        self.status_text.set("正在读取 R76S 摄像头……")
        self.worker = threading.Thread(
            target=self._remote_camera_loop,
            args=(self.confidence_value, self.iou_value, generation),
            daemon=True,
        )
        self.worker.start()

    def _remote_camera_loop(self, confidence: float, iou: float, generation: int) -> None:
        try:
            while not self.stop_event.is_set():
                started = time.perf_counter()
                frame, result = self.remote_backend.capture_frame(confidence, iou)
                output = annotate(frame, list(result.detections))
                wall_ms = (time.perf_counter() - started) * 1000.0
                fps = 1000.0 / wall_ms if wall_ms > 0 else 0.0
                self.events.put(
                    ("frame", (output, result, f"R76S USB 摄像头|{fps:.1f}", generation))
                )
            self.events.put(("stream_end", ("R76S 摄像头已停止", generation)))
        except Exception as exc:
            if not self.stop_event.is_set():
                self.events.put(("error", str(exc)))
        finally:
            self.remote_backend.stop_camera()

    @staticmethod
    def _box_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        first_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        second_area = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0

    def compare_backends(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Windows 与 R76S 对比图片",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp"), ("全部文件", "*.*")],
        )
        if not path:
            return
        if self.local_backend is None:
            messagebox.showerror("Windows 模型未就绪", "请等待 Windows 模型加载完成。")
            return
        if not self.remote_backend.is_available():
            messagebox.showerror("R76S 不可用", "尚未连接到 R76S HTTP 推理服务。")
            return
        try:
            image = read_image(path)
        except Exception as exc:
            messagebox.showerror("图片错误", str(exc))
            return
        self.stop_stream()
        self.view_generation += 1
        generation = self.view_generation
        self.stop_event.clear()
        self.status_text.set("正在进行 Windows / R76S 双端对比……")
        self.worker = threading.Thread(
            target=self._compare_backends_loop,
            args=(image, path, self.confidence_value, self.iou_value, generation),
            daemon=True,
        )
        self.worker.start()

    def _compare_backends_loop(
        self, image, source: str, confidence: float, iou: float, generation: int
    ) -> None:
        try:
            if self.local_backend is None:
                raise RuntimeError("Windows 模型未就绪。")
            local_result = self.local_backend.infer(image, confidence, iou)
            remote_result = self.remote_backend.infer(image, confidence, iou)
            local_image = annotate(image, list(local_result.detections))
            remote_image = annotate(image, list(remote_result.detections))
            cv2.putText(local_image, "Windows ONNX", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            cv2.putText(remote_image, "R76S INT8 RKNN", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            combined = cv2.hconcat([local_image, remote_image])

            matched_ious: list[float] = []
            confidence_diffs: list[float] = []
            remaining = list(remote_result.detections)
            for local in local_result.detections:
                candidates = [item for item in remaining if item.class_id == local.class_id]
                if not candidates:
                    continue
                remote = max(candidates, key=lambda item: self._box_iou(local.box, item.box))
                overlap = self._box_iou(local.box, remote.box)
                if overlap > 0:
                    matched_ious.append(overlap)
                    confidence_diffs.append(abs(local.confidence - remote.confidence))
                    remaining.remove(remote)
            mean_iou = sum(matched_ious) / len(matched_ious) if matched_ious else 0.0
            mean_conf = sum(confidence_diffs) / len(confidence_diffs) if confidence_diffs else 0.0
            summary = (
                f"Windows：{len(local_result.detections)} 个，{local_result.elapsed_ms:.1f} ms\n"
                f"R76S：{len(remote_result.detections)} 个，{remote_result.elapsed_ms:.1f} ms\n"
                f"匹配目标：{len(matched_ious)} 个，平均 IoU：{mean_iou:.3f}，"
                f"平均置信度差：{mean_conf:.3f}"
            )
            self.events.put(
                (
                    "comparison",
                    (combined, local_result, remote_result, source, summary, generation),
                )
            )
        except Exception as exc:
            self.events.put(("error", f"双端对比失败：{exc}"))

    def _present_comparison(
        self,
        frame,
        local_result: InferenceResult,
        remote_result: InferenceResult,
        source: str,
        summary: str,
    ) -> None:
        self.current_annotated = frame
        self.current_result = remote_result
        self.current_source = source
        self.source_text.set(f"双端对比：{Path(source).name}")
        self.performance_text.set(
            f"Windows：{local_result.elapsed_ms:.1f} ms　R76S：{remote_result.elapsed_ms:.1f} ms"
        )
        counts = [0] * len(CLASS_NAMES_ZH)
        for detection in remote_result.detections:
            if 0 <= detection.class_id < len(counts):
                counts[detection.class_id] += 1
        for variable, value in zip(self.count_vars, counts):
            variable.set(str(value))
        self.status_text.set("双端对比完成；右侧统计为 R76S 结果")
        self._redraw_current()
        messagebox.showinfo("Windows / R76S 对比结果", summary)

    def _start_capture(self, source, label: str, save_path: Path | None = None) -> None:
        self.stop_stream()
        self.view_generation += 1
        generation = self.view_generation
        capture = cv2.VideoCapture(source)
        if isinstance(source, int):
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        if not capture.isOpened():
            capture.release()
            messagebox.showerror("输入错误", f"无法打开：{label}")
            return
        self.capture = capture
        self.stop_event.clear()
        self.folder_items = []
        self.folder_index = -1
        self._update_navigation()
        self.source_text.set(label)
        self.status_text.set("连续推理中……")
        try:
            backend = self._selected_backend()
        except Exception as exc:
            capture.release()
            self.capture = None
            messagebox.showerror("推理设备不可用", str(exc))
            return
        self.worker = threading.Thread(
            target=self._capture_loop,
            args=(capture, label, backend, self.confidence_value, self.iou_value, generation, save_path),
            daemon=True,
        )
        self.worker.start()

    def _capture_loop(
        self,
        capture: cv2.VideoCapture,
        label: str,
        backend,
        confidence: float,
        iou: float,
        generation: int,
        save_path: Path | None,
    ) -> None:
        writer: cv2.VideoWriter | None = None
        processed = 0
        completed = False
        try:
            if save_path is not None:
                width = max(1, int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
                height = max(1, int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
                fps = capture.get(cv2.CAP_PROP_FPS)
                if not fps or fps <= 1.0 or fps > 240.0:
                    fps = 25.0
                save_path.parent.mkdir(parents=True, exist_ok=True)
                writer = cv2.VideoWriter(
                    str(save_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    fps,
                    (width, height),
                )
                if not writer.isOpened():
                    raise RuntimeError(f"无法创建输出视频：{save_path}")

            while not self.stop_event.is_set() and capture.isOpened():
                ok, frame = capture.read()
                if not ok:
                    completed = True
                    break
                started = time.perf_counter()
                result = backend.infer(frame, confidence, iou)
                output = annotate(frame, list(result.detections))
                processed += 1
                if writer is not None:
                    writer.write(output)
                wall_ms = (time.perf_counter() - started) * 1000.0
                fps = 1000.0 / wall_ms if wall_ms > 0 else 0.0
                self.events.put(("frame", (output, result, f"{label}|{fps:.1f}", generation)))
                if save_path is not None and processed % 20 == 0:
                    self.events.put(("status", (f"正在保存视频：已处理 {processed} 帧", generation)))

            if save_path is not None:
                state = "完成" if completed else "已停止，已保留部分结果"
                self.events.put(
                    (
                        "job_done",
                        (
                            "视频处理结果",
                            f"视频处理{state}：{processed} 帧\n保存位置：{save_path}",
                            generation,
                        ),
                    )
                )
            else:
                self.events.put(("stream_end", ("视频或摄像头已停止", generation)))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            if writer is not None:
                writer.release()
            capture.release()
            if self.capture is capture:
                self.capture = None

    def batch_process_folder(self) -> None:
        source = filedialog.askdirectory(title="选择待批量检测的图片文件夹")
        if not source:
            return
        destination = filedialog.askdirectory(title="选择结果保存文件夹（建议新建空文件夹）")
        if not destination:
            return
        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        if source_path == destination_path:
            messagebox.showerror("路径错误", "输入与输出不能是同一个文件夹。")
            return
        if source_path in destination_path.parents:
            messagebox.showerror("路径错误", "输出文件夹不能放在输入文件夹内部，否则会重复扫描结果。")
            return
        items = sorted(path for path in source_path.rglob("*") if path.suffix.lower() in SUPPORTED_IMAGES)
        if not items:
            messagebox.showinfo("没有图片", "所选文件夹中没有支持的图片。")
            return
        try:
            backend = self._selected_backend()
        except Exception as exc:
            messagebox.showerror("推理设备不可用", str(exc))
            return

        self.stop_stream()
        self.view_generation += 1
        generation = self.view_generation
        self.stop_event.clear()
        self.folder_items = []
        self.folder_index = -1
        self._update_navigation()
        self.source_text.set(f"批量处理：{source_path.name}")
        self.status_text.set(f"准备批量处理 {len(items)} 张图片……")
        self.worker = threading.Thread(
            target=self._batch_folder_loop,
            args=(
                source_path,
                destination_path,
                items,
                backend,
                self.confidence_value,
                self.iou_value,
                generation,
            ),
            daemon=True,
        )
        self.worker.start()

    def _batch_folder_loop(
        self,
        source_path: Path,
        destination_path: Path,
        items: list[Path],
        backend,
        confidence: float,
        iou: float,
        generation: int,
    ) -> None:
        rows: list[list[object]] = []
        errors: list[str] = []
        processed = 0
        try:
            destination_path.mkdir(parents=True, exist_ok=True)
            for index, image_path in enumerate(items, start=1):
                if self.stop_event.is_set():
                    break
                try:
                    frame = read_image(image_path)
                    result = backend.infer(frame, confidence, iou)
                    output = annotate(frame, list(result.detections))
                    relative = image_path.relative_to(source_path)
                    output_path = destination_path / relative.parent / f"{relative.stem}_detected{relative.suffix}"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    write_image(output_path, output)
                    processed += 1
                    for detection in result.detections:
                        class_name = (
                            CLASS_NAMES_ZH[detection.class_id]
                            if 0 <= detection.class_id < len(CLASS_NAMES_ZH)
                            else str(detection.class_id)
                        )
                        rows.append(
                            [
                                str(image_path),
                                str(output_path),
                                detection.class_id,
                                class_name,
                                f"{detection.confidence:.6f}",
                                *detection.box,
                            ]
                        )
                    if index == 1 or index % 10 == 0 or index == len(items):
                        self.events.put(("frame", (output, result, str(image_path), generation)))
                    self.events.put(
                        ("status", (f"批量处理中：{index}/{len(items)}，成功 {processed} 张", generation))
                    )
                except Exception as exc:
                    errors.append(f"{image_path}: {exc}")

            csv_path = destination_path / "detection_records.csv"
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["source", "output", "class_id", "class_name", "confidence", "x1", "y1", "x2", "y2"]
                )
                writer.writerows(rows)
            if errors:
                (destination_path / "errors.txt").write_text("\n".join(errors), encoding="utf-8")
            state = "已停止，已保留现有结果" if self.stop_event.is_set() else "处理完成"
            message = (
                f"批量{state}：成功 {processed}/{len(items)} 张，失败 {len(errors)} 张。\n"
                f"结果目录：{destination_path}\n检测记录：{csv_path}"
            )
            self.events.put(("job_done", ("批量处理结果", message, generation)))
        except Exception as exc:
            self.events.put(("error", f"批量处理失败：{exc}"))

    def stop_stream(self) -> None:
        self.stop_event.set()
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def reset_view(self) -> None:
        """Stop the current source and restore the initial blank screen."""
        self.stop_stream()
        self.view_generation += 1
        self.current_source = ""
        self.current_original = None
        self.current_annotated = None
        self.current_result = None
        self.folder_items = []
        self.folder_index = -1
        self._update_navigation()
        for variable in self.count_vars:
            variable.set("0")
        self.source_text.set("尚未选择输入")
        self.performance_text.set("推理：-- ms　FPS：--")
        self.status_text.set("画面已刷新")
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self.canvas_message = self.canvas.create_text(
            width // 2,
            height // 2,
            text="打开图片、视频或摄像头开始检测",
            fill="#cbd5e1",
            font=("Microsoft YaHei UI", 14),
        )

    def _present_result(self, frame, result: InferenceResult, source: str) -> None:
        self.current_annotated = frame
        self.current_result = result
        if "|" in source:
            label, fps = source.rsplit("|", 1)
            self.source_text.set(label)
            self.performance_text.set(f"推理：{result.elapsed_ms:.1f} ms　FPS：{fps}")
        else:
            self.current_source = source
            self.source_text.set(Path(source).name if source else "检测结果")
            self.performance_text.set(f"推理：{result.elapsed_ms:.1f} ms　FPS：--")
        counts = [0] * len(CLASS_NAMES_ZH)
        for detection in result.detections:
            if 0 <= detection.class_id < len(counts):
                counts[detection.class_id] += 1
        for variable, value in zip(self.count_vars, counts):
            variable.set(str(value))
        self.status_text.set(f"检测完成：共 {len(result.detections)} 个目标 · {result.backend_name}")
        self._redraw_current()

    def _redraw_current(self) -> None:
        if self.current_annotated is None:
            width = max(1, self.canvas.winfo_width())
            height = max(1, self.canvas.winfo_height())
            self.canvas.coords(self.canvas_message, width // 2, height // 2)
            return
        frame = cv2.cvtColor(self.current_annotated, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame)
        canvas_width = max(100, self.canvas.winfo_width())
        canvas_height = max(100, self.canvas.winfo_height())
        scale = min(canvas_width / image.width, canvas_height / image.height)
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=self.tk_image, anchor=tk.CENTER)

    def save_current(self) -> None:
        if self.current_annotated is None:
            messagebox.showinfo("没有结果", "请先完成一次检测。")
            return
        default_name = "detection_result.jpg"
        if self.current_source:
            default_name = f"{Path(self.current_source).stem}_detected.jpg"
        path = filedialog.asksaveasfilename(
            title="保存检测结果",
            defaultextension=".jpg",
            initialfile=default_name,
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png"), ("BMP", "*.bmp")],
        )
        if not path:
            return
        try:
            write_image(path, self.current_annotated)
            self.status_text.set(f"结果已保存：{path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def export_csv(self) -> None:
        if self.current_result is None:
            messagebox.showinfo("没有记录", "请先完成一次检测。")
            return
        path = filedialog.asksaveasfilename(
            title="导出检测记录",
            defaultextension=".csv",
            initialfile="detection_records.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["source", "class_id", "class_name", "confidence", "x1", "y1", "x2", "y2"])
                for detection in self.current_result.detections:
                    writer.writerow(
                        [
                            self.current_source,
                            detection.class_id,
                            CLASS_NAMES_ZH[detection.class_id],
                            f"{detection.confidence:.6f}",
                            *detection.box,
                        ]
                    )
            self.status_text.set(f"检测记录已导出：{path}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def close(self) -> None:
        self._save_settings()
        self.app_stop_event.set()
        self.stop_stream()
        if self.local_backend is not None:
            self.local_backend.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DetectionClient(root)
    root.mainloop()


if __name__ == "__main__":
    main()
