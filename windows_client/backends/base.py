from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class Detection:
    class_id: int
    label: str
    confidence: float
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class InferenceResult:
    detections: Sequence[Detection]
    elapsed_ms: float
    backend_name: str


class InferenceBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def detail(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def infer(self, image: np.ndarray, confidence: float, iou: float) -> InferenceResult:
        raise NotImplementedError

    def close(self) -> None:
        return None
