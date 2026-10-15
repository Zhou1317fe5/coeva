"""SpriteSheet loading and AnimationPlayer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap


class SpriteSheetError(RuntimeError):
    """Raised when a spritesheet cannot be loaded or sliced."""


class SpriteSheet:
    """A row of animation frames sliced horizontally from a single image."""

    def __init__(self, frames: list[QPixmap], *, frame_width: int, frame_height: int) -> None:
        if not frames:
            raise SpriteSheetError("A SpriteSheet must contain at least one frame.")
        self.frames = frames
        self.frame_width = frame_width
        self.frame_height = frame_height

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @classmethod
    def load(cls, path: Path, *, frames: int = 1) -> SpriteSheet:
        """Load an image from disk and slice it into `frames` equal horizontal slices."""
        if not path.is_file():
            raise SpriteSheetError(f"Sprite file does not exist: {path}")

        image = QImage(str(path))
        if image.isNull():
            raise SpriteSheetError(f"Failed to read image data from: {path}")

        total_width = image.width()
        total_height = image.height()

        if frames < 1:
            raise SpriteSheetError(f"Frame count must be at least 1, got {frames}")
        if total_width % frames != 0:
            raise SpriteSheetError(
                f"Image width ({total_width}px) is not divisible by frame count ({frames})"
            )

        frame_width = total_width // frames
        frame_height = total_height

        sliced: list[QPixmap] = []
        for i in range(frames):
            frame_image = image.copy(i * frame_width, 0, frame_width, frame_height)
            sliced.append(QPixmap.fromImage(frame_image))

        return cls(sliced, frame_width=frame_width, frame_height=frame_height)

    def scaled(self, factor: int) -> SpriteSheet:
        """Return a new SpriteSheet scaled using nearest-neighbor for crisp pixel art."""
        if factor <= 1:
            return self
        scaled_frames = [
            f.scaled(
                self.frame_width * factor,
                self.frame_height * factor,
                aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                mode=Qt.TransformationMode.FastTransformation,
            )
            for f in self.frames
        ]
        return SpriteSheet(
            scaled_frames,
            frame_width=self.frame_width * factor,
            frame_height=self.frame_height * factor,
        )


class AnimationPlayer(QObject):
    """Timer-driven player for a SpriteSheet."""

    frame_changed = Signal(QPixmap)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sheet: SpriteSheet | None = None
        self._current_index = 0
        self._loop = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    @property
    def current_frame(self) -> QPixmap | None:
        if self._sheet is None or not self._sheet.frames:
            return None
        return self._sheet.frames[self._current_index]

    def play(self, sheet: SpriteSheet, *, fps: int = 6, loop: bool = True) -> None:
        """Load sheet and start playback at given FPS."""
        self._timer.stop()
        self._sheet = sheet
        self._current_index = 0
        self._loop = loop

        if sheet.frame_count == 0:
            return

        interval_ms = max(10, int(1000 / max(1, fps)))
        self._timer.setInterval(interval_ms)
        self.frame_changed.emit(sheet.frames[0])

        if sheet.frame_count > 1 or not loop:
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _advance(self) -> None:
        if self._sheet is None or self._sheet.frame_count == 0:
            self._timer.stop()
            return

        next_index = self._current_index + 1
        if next_index >= self._sheet.frame_count:
            if self._loop:
                self._current_index = 0
            else:
                self._timer.stop()
                self.finished.emit()
                return
        else:
            self._current_index = next_index

        self.frame_changed.emit(self._sheet.frames[self._current_index])
