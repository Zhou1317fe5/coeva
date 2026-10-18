"""Cached native-idle renderer for the real PySide desktop body."""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap

_ALPHA_THRESHOLD = 8


def _alpha_bbox(image: QImage) -> tuple[int, int, int, int] | None:
    left = image.width()
    top = image.height()
    right = -1
    bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > _ALPHA_THRESHOLD:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
    if right < 0:
        return None
    return left, top, right + 1, bottom + 1


def _union_bbox(*boxes: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    valid = [box for box in boxes if box is not None]
    if not valid:
        return None
    return (
        min(box[0] for box in valid),
        min(box[1] for box in valid),
        max(box[2] for box in valid),
        max(box[3] for box in valid),
    )


class NativeIdlePlayer(QObject):
    """Render cached native layers with continuous breathing and irregular blinks."""

    frame_ready = Signal(QPixmap)

    def __init__(
        self,
        rig_dir: Path,
        *,
        display_size: int = 320,
        tick_ms: int = 50,
        breathing_period_s: float = 6.0,
        breathing_amplitude: float = 0.0015,
        blink_min_interval_s: float = 4.5,
        blink_max_interval_s: float = 8.5,
        blink_duration_s: float = 0.14,
        seed: int | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.rig_dir = rig_dir
        self.display_size = display_size
        self.tick_ms = tick_ms
        self.breathing_period_s = breathing_period_s
        self.breathing_amplitude = breathing_amplitude
        self.blink_min_interval_s = blink_min_interval_s
        self.blink_max_interval_s = blink_max_interval_s
        self.blink_duration_s = blink_duration_s
        self._random = random.Random(seed)
        self._anchor_y = 952.0 * display_size / 1024.0
        self._layers = self._load_layers()
        self._open_bbox = _union_bbox(
            _alpha_bbox(self._layers["body"]),
            _alpha_bbox(self._layers["head-base"]),
            _alpha_bbox(self._layers["eyes-open"]),
        )
        self._closed_bbox = _union_bbox(
            _alpha_bbox(self._layers["body"]),
            _alpha_bbox(self._layers["eyes-closed"]),
        )
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self._tick)
        self._running = False
        self._started_at = 0.0
        self._next_blink_at = 0.0
        self._blink_until = 0.0
        self._metrics_path: Path | None = None
        self._last_metrics_at = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def layer_bboxes(self) -> dict[str, tuple[int, int, int, int] | None]:
        return {name: _alpha_bbox(image) for name, image in self._layers.items()}

    def set_metrics_path(self, path: Path | None) -> None:
        self._metrics_path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def _append_metric(self, event: dict[str, object]) -> None:
        if self._metrics_path is None:
            return
        with self._metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._started_at = time.monotonic()
        self._last_metrics_at = self._started_at - 1.0
        self._blink_until = 0.0
        self._next_blink_at = self._started_at + self._next_blink_interval()
        self._timer.start()
        self._tick()

    def stop(self) -> None:
        self._timer.stop()
        self._running = False

    def _load_layers(self) -> dict[str, QImage]:
        layers: dict[str, QImage] = {}
        for name in ("body", "head-base", "eyes-open", "eyes-closed"):
            path = self.rig_dir / "layers" / f"{name}.png"
            source = QImage(str(path))
            if source.isNull():
                raise RuntimeError(f"Failed to load native idle layer: {path}")
            layers[name] = source.scaled(
                self.display_size,
                self.display_size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return layers

    def _next_blink_interval(self) -> float:
        return self._random.uniform(
            self.blink_min_interval_s,
            self.blink_max_interval_s,
        )

    def _scale_y(self, elapsed_s: float) -> float:
        return 1.0 + self.breathing_amplitude * math.sin(
            math.tau * elapsed_s / self.breathing_period_s
        )

    def _transformed_bbox(
        self,
        bbox: tuple[int, int, int, int] | None,
        scale_y: float,
    ) -> tuple[int, int, int, int] | None:
        if bbox is None:
            return None
        top = self._anchor_y + (bbox[1] - self._anchor_y) * scale_y
        bottom = self._anchor_y + (bbox[3] - self._anchor_y) * scale_y
        return bbox[0], round(top), bbox[2], round(bottom)

    def _draw_layer(self, painter: QPainter, image: QImage, scale_y: float) -> None:
        painter.save()
        painter.translate(0.0, self._anchor_y)
        painter.scale(1.0, scale_y)
        painter.translate(0.0, -self._anchor_y)
        painter.drawImage(0, 0, image)
        painter.restore()

    def _render(self, elapsed_s: float, blink_closed: bool) -> QPixmap:
        scale_y = self._scale_y(elapsed_s)
        image = QImage(
            self.display_size,
            self.display_size,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._draw_layer(painter, self._layers["body"], scale_y)
        if blink_closed:
            self._draw_layer(painter, self._layers["eyes-closed"], scale_y)
        else:
            self._draw_layer(painter, self._layers["eyes-open"], scale_y)
        painter.end()
        self._write_metrics(elapsed_s, scale_y, blink_closed)
        return QPixmap.fromImage(image)

    def _write_metrics(self, elapsed_s: float, scale_y: float, blink_closed: bool) -> None:
        if self._metrics_path is None:
            return
        wall_time = time.monotonic()
        if wall_time - self._last_metrics_at < 1.0:
            return
        self._last_metrics_at = wall_time
        bbox = self._closed_bbox if blink_closed else self._open_bbox
        transformed = self._transformed_bbox(bbox, scale_y)
        event = {
            "wall_time_s": wall_time,
            "elapsed_s": elapsed_s,
            "blink_closed": blink_closed,
            "breathing_scale_y": scale_y,
            "bbox": list(transformed) if transformed else None,
            "visible_height": transformed[3] - transformed[1] if transformed else 0,
            "baseline_y": transformed[3] if transformed else None,
        }
        with self._metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    def _tick(self) -> None:
        if not self._running:
            return
        now = time.monotonic()
        if now >= self._next_blink_at and now >= self._blink_until:
            self._blink_until = now + self.blink_duration_s
            self._next_blink_at = now + self.blink_duration_s + self._next_blink_interval()
            self._append_metric(
                {
                    "event": "blink_start",
                    "elapsed_s": now - self._started_at,
                    "duration_s": self.blink_duration_s,
                }
            )
        blink_closed = now < self._blink_until
        self.frame_ready.emit(self._render(now - self._started_at, blink_closed))
