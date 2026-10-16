"""SpriteSheet loading and AnimationPlayer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap

# Alpha values at or below this are treated as transparent. Matches the mask
# threshold used when trimming empty frames.
_ALPHA_THRESHOLD = 8


class SpriteSheetError(RuntimeError):
    """Raised when a spritesheet cannot be loaded or sliced."""


def measure_art_padding(image: QImage, *, cols: int, rows: int) -> tuple[int, int]:
    """Return (left_pad, right_pad) of the union of all non-empty frames.

    Petdex atlases bake generous transparent margins around the artwork, so the
    frame edges are empty. Anything that reveals a fixed number of pixels from a
    frame edge therefore reveals *transparency* once the margin exceeds that
    number -- which is why a docked pet became invisible at larger scales.
    Callers use this to reveal margin + a visible sliver, instead of guessing.

    The scan is column-wise `max()` over Qt's own alpha buffer: measuring the
    whole atlas takes tens of milliseconds, versus seconds for a per-pixel loop.
    """
    if cols < 1 or rows < 1:
        raise SpriteSheetError(f"Atlas grid must be positive, got {cols}x{rows}")
    frame_w = image.width() // cols
    frame_h = image.height() // rows
    if frame_w < 1 or frame_h < 1:
        raise SpriteSheetError(
            f"Atlas {image.width()}x{image.height()} is smaller than its {cols}x{rows} grid"
        )
    alpha = image.convertToFormat(QImage.Format.Format_Alpha8)
    bytes_per_line = alpha.bytesPerLine()
    buffer = alpha.constBits()

    lefts: list[int] = []
    rights: list[int] = []
    for row in range(rows):
        y0 = row * frame_h
        for col in range(cols):
            x0 = col * frame_w
            frame_left: int | None = None
            frame_right = -1
            for offset in range(frame_w):
                column = buffer[x0 + offset :: bytes_per_line]
                if max(column[y0 : y0 + frame_h], default=0) > _ALPHA_THRESHOLD:
                    if frame_left is None:
                        frame_left = offset
                    frame_right = offset
            if frame_left is None:
                continue  # an entirely empty frame carries no artwork
            lefts.append(frame_left)
            rights.append(frame_w - 1 - frame_right)

    if not lefts:
        return 0, 0  # a fully transparent atlas has no margin to clear
    # The worst case over frames: whatever is displayed must clear the widest
    # margin that any frame in this sheet can have.
    return max(lefts), max(rights)


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

    def scaled(self, factor: float) -> SpriteSheet:
        """Return a new SpriteSheet scaled to given factor."""
        if abs(factor - 1.0) < 0.01:
            return self
        new_w = max(16, int(round(self.frame_width * factor)))
        new_h = max(16, int(round(self.frame_height * factor)))
        mode = (
            Qt.TransformationMode.SmoothTransformation
            if factor < 1.0
            else Qt.TransformationMode.FastTransformation
        )
        scaled_frames = [
            f.scaled(
                new_w,
                new_h,
                aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                mode=mode,
            )
            for f in self.frames
        ]
        return SpriteSheet(
            scaled_frames,
            frame_width=new_w,
            frame_height=new_h,
        )


class PetdexAtlasLoader:
    """Loader for standard Petdex 9-row atlas sprite sheets."""

    PETDEX_ROW_MAP: dict[int, str] = {
        0: "idle",
        1: "running-right",
        2: "running-left",
        3: "waving",
        4: "jumping",
        5: "failed",
        6: "waiting",
        7: "running",
        8: "review",
    }

    @classmethod
    def load_atlas(
        cls,
        image_path: Path,
        *,
        cols: int = 8,
        rows: int = 9,
        scale: float = 1.0,
        trim_empty_frames: bool = True,
    ) -> dict[str, SpriteSheet]:
        """Slice a unified Petdex sprite sheet into action-specific SpriteSheets."""
        if not image_path.is_file():
            raise SpriteSheetError(f"Atlas image not found: {image_path}")

        image = QImage(str(image_path))
        if image.isNull():
            raise SpriteSheetError(f"Cannot decode atlas image: {image_path}")

        total_w = image.width()
        total_h = image.height()

        frame_w = total_w // max(1, cols)
        frame_h = total_h // max(1, rows)

        sheets: dict[str, SpriteSheet] = {}
        for r_idx, action_name in cls.PETDEX_ROW_MAP.items():
            if r_idx >= rows:
                break
            raw_frames: list[tuple[QImage, bool]] = []
            for c_idx in range(cols):
                frame_img = image.copy(c_idx * frame_w, r_idx * frame_h, frame_w, frame_h)
                if trim_empty_frames:
                    alpha_img = frame_img.convertToFormat(QImage.Format.Format_Alpha8)
                    has_pixels = any(bytes(alpha_img.constBits()))
                else:
                    has_pixels = True
                raw_frames.append((frame_img, has_pixels))

            if trim_empty_frames:
                # Trim trailing empty frames, keeping at least 1 frame
                while len(raw_frames) > 1 and not raw_frames[-1][1]:
                    raw_frames.pop()

            pixmaps = [QPixmap.fromImage(item[0]) for item in raw_frames]
            sheet = SpriteSheet(pixmaps, frame_width=frame_w, frame_height=frame_h)
            if abs(scale - 1.0) >= 0.01:
                sheet = sheet.scaled(scale)
            sheets[action_name] = sheet

        return sheets

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
