"""SpriteSheet loading and AnimationPlayer."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QTransform

# Alpha values at or below this are treated as transparent. Matches the mask
# threshold used when trimming empty frames.
_ALPHA_THRESHOLD = 8


class SpriteSheetError(RuntimeError):
    """Raised when a spritesheet cannot be loaded or sliced."""


@dataclass(frozen=True)
class MiniModeConfig:
    """Theme configuration for edge docking and mini-mode peek behaviors."""

    supported: bool = False
    flip_assets: bool = False
    offset_ratio: float = 0.4
    peek_offset_ratio: float = 0.08


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

    def __init__(
        self,
        frames: list[QPixmap],
        *,
        frame_width: int,
        frame_height: int,
        default_fps: int = 6,
        frame_durations_ms: list[int] | None = None,
    ) -> None:
        if not frames:
            raise SpriteSheetError("A SpriteSheet must contain at least one frame.")
        self.frames = frames
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.default_fps = default_fps
        self.frame_durations_ms = frame_durations_ms
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
    def mirrored(self, *, horizontal: bool = True, vertical: bool = False) -> SpriteSheet:
        """Return a new SpriteSheet with all frames mirrored horizontally/vertically."""
        if not horizontal and not vertical:
            return self
        transform = QTransform()
        transform.scale(-1.0 if horizontal else 1.0, -1.0 if vertical else 1.0)
        mirrored_frames = [f.transformed(transform) for f in self.frames]
        return SpriteSheet(
            mirrored_frames,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            default_fps=self.default_fps,
            frame_durations_ms=self.frame_durations_ms,
        )

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
            default_fps=self.default_fps,
            frame_durations_ms=self.frame_durations_ms,
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

    CODEX_ROW_DURATIONS: dict[str, list[int]] = {
        "idle": [280, 110, 110, 140, 140, 320],
        "running-right": [120, 120, 120, 120, 120, 120, 120, 220],
        "running-left": [120, 120, 120, 120, 120, 120, 120, 220],
        "waving": [140, 140, 140, 280],
        "jumping": [140, 140, 140, 140, 280],
        "failed": [140, 140, 140, 140, 140, 140, 140, 240],
        "waiting": [150, 150, 150, 150, 150, 260],
        "running": [120, 120, 120, 120, 120, 220],
        "review": [150, 150, 150, 150, 150, 280],
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
            durations = cls.CODEX_ROW_DURATIONS.get(action_name)
            sheet = SpriteSheet(
                pixmaps,
                frame_width=frame_w,
                frame_height=frame_h,
                frame_durations_ms=durations,
            )
            if abs(scale - 1.0) >= 0.01:
                sheet = sheet.scaled(scale)
            sheets[action_name] = sheet

        return sheets


class ThemeApngLoader:
    """Loader for Clawd on Desk APNG themes (e.g. Calico)."""

    @classmethod
    def load_apng_as_spritesheet(
        cls, apng_path: Path, *, scale: float = 1.0
    ) -> SpriteSheet:
        """Decode an animated PNG into a SpriteSheet with exact frame rate."""
        if not apng_path.is_file():
            raise SpriteSheetError(f"APNG file not found: {apng_path}")

        try:
            im = Image.open(apng_path)
        except Exception as e:
            raise SpriteSheetError(f"Failed to read APNG: {apng_path}: {e}") from e

        pixmaps: list[QPixmap] = []
        durations: list[float] = []

        for frame in ImageSequence.Iterator(im):
            frame_rgba = frame.convert("RGBA")
            raw_bytes = frame_rgba.tobytes()
            w, h = frame_rgba.size
            qimg = QImage(raw_bytes, w, h, QImage.Format.Format_RGBA8888)
            pixmaps.append(QPixmap.fromImage(qimg))
            durations.append(float(frame.info.get("duration", 125.0)))

        if not pixmaps:
            raise SpriteSheetError(f"No frames decoded from {apng_path}")

        avg_dur_ms = sum(durations) / len(durations) if durations else 125.0
        fps = max(1, min(60, int(round(1000.0 / max(10.0, avg_dur_ms)))))

        sheet = SpriteSheet(
            pixmaps,
            frame_width=pixmaps[0].width(),
            frame_height=pixmaps[0].height(),
            default_fps=fps,
        )
        if abs(scale - 1.0) >= 0.01:
            sheet = sheet.scaled(scale)
        return sheet

    @classmethod
    def load_mini_config(cls, theme_dir: Path) -> MiniModeConfig:
        """Load miniMode configuration from a theme directory if available."""
        theme_json_path = theme_dir / "theme.json"
        if not theme_json_path.is_file():
            return MiniModeConfig()
        try:
            meta = json.loads(theme_json_path.read_text(encoding="utf-8"))
            mini_cfg = meta.get("miniMode", {})
            if not isinstance(mini_cfg, dict):
                return MiniModeConfig()
            supported = bool(mini_cfg.get("supported", False))
            flip_assets = bool(mini_cfg.get("flipAssets", False))
            offset_ratio = float(mini_cfg.get("offsetRatio", 0.4))
            peek_cfg = mini_cfg.get("peek", {})
            peek_ratio = (
                float(peek_cfg.get("offsetRatio", 0.08))
                if isinstance(peek_cfg, dict)
                else 0.08
            )
            return MiniModeConfig(
                supported=supported,
                flip_assets=flip_assets,
                offset_ratio=offset_ratio,
                peek_offset_ratio=peek_ratio,
            )
        except Exception:
            return MiniModeConfig()

    @classmethod
    def load_theme(
        cls, theme_dir: Path, *, scale: float = 1.0
    ) -> dict[str, SpriteSheet]:
        """Load all APNG animation sheets declared in a Clawd on Desk theme directory."""
        theme_json_path = theme_dir / "theme.json"
        assets_dir = theme_dir / "assets"
        if not assets_dir.is_dir():
            assets_dir = theme_dir

        sheets: dict[str, SpriteSheet] = {}
        file_to_sheet: dict[str, SpriteSheet] = {}

        # 1. Scan and load all apng files
        for apng_file in assets_dir.glob("*.apng"):
            try:
                sheet = cls.load_apng_as_spritesheet(apng_file, scale=scale)
                file_to_sheet[apng_file.name] = sheet
                # Register by clean file action name, e.g. "calico-idle.apng" -> "idle"
                clean_name = apng_file.stem
                for prefix in ("calico-", "clawd-", "theme-"):
                    if clean_name.startswith(prefix):
                        clean_name = clean_name[len(prefix) :]
                sheets[clean_name] = sheet
            except SpriteSheetError:
                continue

        # 2. Parse theme.json mappings if available
        if theme_json_path.is_file():
            try:
                meta = json.loads(theme_json_path.read_text(encoding="utf-8"))
                states = meta.get("states", {})
                for state_name, file_list in states.items():
                    if isinstance(file_list, list) and file_list:
                        fname = str(file_list[0])
                        if fname in file_to_sheet:
                            sheets[state_name] = file_to_sheet[fname]

                # Map reactions
                reactions = meta.get("reactions", {})
                for r_name, r_conf in reactions.items():
                    if isinstance(r_conf, dict) and "file" in r_conf:
                        rfname = str(r_conf["file"])
                        if rfname in file_to_sheet:
                            sheets[f"react-{r_name}"] = file_to_sheet[rfname]

                # Map miniMode
                mini_cfg = meta.get("miniMode", {})
                mini_states = mini_cfg.get("states", {})
                flip_assets = bool(mini_cfg.get("flipAssets", False))
                for m_name, m_list in mini_states.items():
                    if isinstance(m_list, list) and m_list:
                        mfname = str(m_list[0])
                        if mfname in file_to_sheet:
                            sh = file_to_sheet[mfname]
                            sheets[m_name] = sh
                            if flip_assets:
                                sheets[f"{m_name}-flipped"] = sh.mirrored(horizontal=True)
            except Exception:
                pass

        # 3. Ensure Core PetState standard candidates are established
        aliases = {
            "idle": ["idle", "calico-idle"],
            "sleeping": ["sleeping", "collapsing", "dozing"],
            "thinking": ["thinking", "review"],
            "working": ["working-typing", "working", "typing", "running"],
            "happy": ["happy", "mini-happy", "waving", "notification"],
            "error": ["error", "failed"],
            "waiting": ["thinking", "waiting", "mini-idle"],
            "waving": ["happy", "notification", "mini-happy"],
            "wave": ["happy", "notification"],
            "work": ["working-typing", "working"],
            "think": ["thinking"],
            "sleep": ["sleeping"],
            "yawn": ["yawning"],
            "poke": ["react-poke", "react-clickLeft"],
            "drag": ["react-drag"],
        }
        for target, cand_list in aliases.items():
            if target not in sheets:
                for c in cand_list:
                    if c in sheets:
                        sheets[target] = sheets[c]
                        break

        return sheets


class AnimationPlayer(QObject):
    """Timer-driven player for a SpriteSheet."""

    frame_changed = Signal(QPixmap)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sheet: SpriteSheet | None = None
        self._current_index = 0
        self._effective_fps = 6
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._loop_delay_timer = QTimer(self)
        self._loop_delay_timer.setSingleShot(True)
        self._loop_delay_timer.timeout.connect(self._resume_after_delay)

    @property
    def current_frame(self) -> QPixmap | None:
        if self._sheet is None or not self._sheet.frames:
            return None
        return self._sheet.frames[self._current_index]

    def _frame_interval_ms(self, idx: int, fallback_fps: int = 6) -> int:
        """Return exact duration for frame `idx` if declared, else 1000/fps."""
        if (
            self._sheet is not None
            and self._sheet.frame_durations_ms
            and idx < len(self._sheet.frame_durations_ms)
        ):
            return max(10, self._sheet.frame_durations_ms[idx])
        return max(10, int(1000 / max(1, fallback_fps)))

    def play(
        self,
        sheet: SpriteSheet,
        *,
        fps: int | None = None,
        loop: bool = True,
        loop_delay_range_ms: tuple[int, int] | None = None,
    ) -> None:
        """Load sheet and start playback at given FPS (defaults to sheet's own fps)."""
        self._timer.stop()
        self._loop_delay_timer.stop()
        self._sheet = sheet
        self._current_index = 0
        self._loop = loop
        self._loop_delay_range_ms = loop_delay_range_ms

        if sheet.frame_count == 0:
            return

        self._effective_fps = fps if fps is not None else getattr(sheet, "default_fps", 6)
        interval_ms = self._frame_interval_ms(0, self._effective_fps)
        self._timer.setInterval(interval_ms)
        self.frame_changed.emit(sheet.frames[0])

        if sheet.frame_count > 1 or not loop:
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._loop_delay_timer.stop()

    def _resume_after_delay(self) -> None:
        if self._sheet is not None and self._loop:
            self._current_index = 1 if self._sheet.frame_count > 1 else 0
            self._timer.setInterval(
                self._frame_interval_ms(self._current_index, self._effective_fps)
            )
            self.frame_changed.emit(self._sheet.frames[self._current_index])
            self._timer.start()

    def _advance(self) -> None:
        if self._sheet is None or self._sheet.frame_count == 0:
            self._timer.stop()
            return

        next_index = self._current_index + 1
        if next_index >= self._sheet.frame_count:
            if self._loop:
                self._current_index = 0
                self.frame_changed.emit(self._sheet.frames[0])
                if self._loop_delay_range_ms is not None:
                    self._timer.stop()
                    min_d, max_d = self._loop_delay_range_ms
                    delay = random.randint(min(min_d, max_d), max(min_d, max_d))
                    self._loop_delay_timer.start(delay)
                    return
            else:
                self._timer.stop()
                self.finished.emit()
                return
        else:
            self._current_index = next_index

        self._timer.setInterval(
            self._frame_interval_ms(self._current_index, self._effective_fps)
        )
        self.frame_changed.emit(self._sheet.frames[self._current_index])
