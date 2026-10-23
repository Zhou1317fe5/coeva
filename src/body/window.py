"""Transparent, frameless, always-on-top window hosting the companion pet with edge peek docking."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QContextMenuEvent,
    QCursor,
    QEnterEvent,
    QHideEvent,
    QImage,
    QMouseEvent,
    QPixmap,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from src.body.animation import (
    AnimationPlayer,
    MiniModeConfig,
    NativeIdleConfig,
    PetdexAtlasLoader,
    SpriteSheet,
    SpriteSheetError,
    ThemeApngLoader,
    measure_art_padding,
)
from src.body.contracts import PetState
from src.body.speech_bubble import SpeechBubble
from src.core.behavior import (
    ActivityRegistry,
    ActivityTrait,
    ArbiterAction,
    BehaviorArbiter,
    BehaviorCategory,
    BehaviorDirection,
    BehaviorIntent,
    BehaviorPriority,
    BehaviorRequest,
    BehaviorSource,
    LifeContext,
    LifeScheduler,
    LoopMode,
    PetActivity,
    PetManifest,
    ProtectionLevel,
    VisualBinding,
    load_pet_manifest,
)
from src.core.circadian import get_schedule_for_time
from src.feeder.contracts import RawSlice
from src.feeder.overlay import SliceFeederBar
from src.feeder.storage import SliceStore

CLICK_DRAG_THRESHOLD_PX = 4
EDGE_SNAP_DISTANCE_PX = 30  # Snapping threshold set to 30px
# How much actual artwork stays on screen while docked to an edge. The reveal is
# computed from the sheet's own transparent margin (see `_peek_reveal_px`), not
# from a fixed pixel count: Petdex atlases bake wide margins, so a fixed 24px
# revealed pure transparency once the margin exceeded it, making a docked pet
# vanish entirely at larger scales.
PEEK_VISIBLE_ART_PX = 24  # artwork pixels left on screen when docked
# Shipped default size: 50%. A full-size Petdex frame (192x208 at 1.0) is large
# enough to feel intrusive on the desktop, so the companion starts small and the
# user can scale it up (settings panel, tray menu, or Ctrl + wheel).
DEFAULT_SCALE = 0.5
NATIVE_IDLE_DEFAULT_SCALE = 0.3
# Persisted window position and scale. Tests point this at tmp_path so they never
# read or overwrite the user's real file while constructing a PetWindow.
DEFAULT_POSITION_CONFIG_PATH = Path("data") / "body_position.json"
# Autonomous daily life routine: the pet spontaneously engages in its own
# activities (typing, sweeping, carpentry, juggling, thinking, yawning) when idle.
# Circadian Life Schedule: human-like calm pacing across 24 hours.
# Idle pauses are 2 - 8 minutes long; activities last 12 - 25 seconds.
NAP_DURATION_MS = 45_000
# Hover greeting cooldown: 120 seconds (2 minutes) to keep interaction minimal and gentle.
GREETING_COOLDOWN_MS = 120_000


class PetWindow(QWidget):
    """The desktop pet window with animation player, speech bubble, dragging,
    and half-hidden edge peek docking.
    """

    clicked = Signal()
    position_changed = Signal(int, int)
    scale_changed = Signal(float)
    context_menu_requested = Signal(QPoint)
    slice_fed = Signal(str)
    user_replied_to_bubble = Signal(str, str)  # (reply_text, original_pet_speech)
    native_blink_started = Signal(float)

    def __init__(
        self,
        pet_dir: Path,
        *,
        scale: float = DEFAULT_SCALE,
        position_config_path: Path | None = None,
        slice_store: SliceStore | None = None,
        feeder_bar: SliceFeederBar | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pet_dir = pet_dir
        self._scale = scale
        self._current_state = PetState.IDLE
        self._position_config_path = position_config_path or DEFAULT_POSITION_CONFIG_PATH
        # Worst-case transparent margin of the loaded sheets, measured once per
        # load/scale change. Docking reveals margin + a visible sliver of artwork.
        self._art_padding_px: tuple[int, int] = (0, 0)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)

        self._label = QLabel(self)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._label.setStyleSheet("background: transparent; border: 0;")
        self._label.setScaledContents(False)
        self._label.setMouseTracking(True)

        self._player = AnimationPlayer(self)
        self._player.frame_changed.connect(self._on_frame_changed)

        self._bubble = SpeechBubble()
        self._slice_store = slice_store or SliceStore()
        self._feeder_bar = feeder_bar or SliceFeederBar()
        self._feeder_bar.slice_submitted.connect(self._on_slice_submitted)
        self._feeder_bar.voice_clicked.connect(self._on_voice_clicked)
        self._bubble.user_replied.connect(self._on_bubble_user_replied)
        # Drag state
        self._drag_offset: QPoint | None = None
        self._press_pos: QPoint | None = None
        self._last_drag_x: int = 0
        self._current_drag_dir: str | None = None
        self._suppress_default_feedback = False
        self._has_moved = False

        # Hover jump (Codex hop on cursor hover)
        self._last_hover_jump_timestamp: float = 0.0
        self._jump_settle_timer = QTimer(self)
        self._jump_settle_timer.setSingleShot(True)
        self._jump_settle_timer.timeout.connect(self._finish_hover_jump)

        # Edge Docking (Peek Mode) state
        self._docked_edge: str | None = None  # "right", "left", or None
        self._is_peek_expanded = False
        self._mini_cfg = MiniModeConfig()
        self._retract_timer = QTimer(self)
        self._retract_timer.setSingleShot(True)
        self._retract_timer.timeout.connect(self._retract_to_dock)

        # Polling watcher to ensure reliable leave detection across OS window borders
        self._hover_poll_timer = QTimer(self)
        self._hover_poll_timer.setInterval(150)
        self._hover_poll_timer.timeout.connect(self._check_cursor_outside_polling)

        # Hover greeting: the pet waves once when it peeks out (DESIGN.md 2.1). The
        # one-shot timer restores the resting state after the gesture completes.
        self._wave_timer = QTimer(self)
        self._wave_timer.setSingleShot(True)
        self._wave_timer.timeout.connect(self._finish_greeting)
        self._greeting_active = False
        self._last_greet_timestamp = 0.0

        # Ambient awareness of user working with tools/agents
        self._is_user_working = False
        self._user_working_timer = QTimer(self)
        self._user_working_timer.setSingleShot(True)
        self._user_working_timer.setInterval(120_000)  # 2 minutes of active tool working vibe
        self._user_working_timer.timeout.connect(self._clear_user_working)
        # Ambient awareness of emotional sanctuary (meltdown protection) mode
        self._sanctuary_active = False
        # Autonomous daily life routine: the pet occasionally does its own activities
        self._autonomous_timer = QTimer(self)
        self._autonomous_timer.setSingleShot(True)
        self._autonomous_timer.timeout.connect(self._start_autonomous_routine)

        self._autonomous_done_timer = QTimer(self)
        self._autonomous_done_timer.setSingleShot(True)
        self._autonomous_done_timer.timeout.connect(self._finish_autonomous_routine)
        self._in_autonomous_routine = False

        # Nap timer: a sleeping pet takes a catnap, then naturally wakes up with a stretch
        self._nap_timer = QTimer(self)
        self._nap_timer.setSingleShot(True)
        self._nap_timer.timeout.connect(self._on_nap_timeout)

        self._native_idle_config: NativeIdleConfig | None = None
        self._native_idle_frames: tuple[QPixmap, QPixmap] | None = None
        self._native_idle_active = False
        self._native_blink_timer = QTimer(self)
        self._native_blink_timer.setSingleShot(True)
        self._native_blink_timer.timeout.connect(self._start_native_blink)
        self._native_blink_restore_timer = QTimer(self)
        self._native_blink_restore_timer.setSingleShot(True)
        self._native_blink_restore_timer.timeout.connect(self._finish_native_blink)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._loaded_sheets: dict[str, SpriteSheet] = {}
        self._init_arbiter()
        self._load_spritesheets()
        self.apply_state(PetState.IDLE, force=True)  # first paint of the sprite
        self._restore_position()
        # Schedule natural first action according to the circadian rhythm
        self._schedule_next_autonomous_routine(initial=True)

    @property
    def current_state(self) -> PetState:
        return self._current_state
    @property
    def arbiter(self) -> BehaviorArbiter:
        return self._arbiter

    @property
    def scheduler(self) -> LifeScheduler:
        return self._scheduler

    def _init_arbiter(self) -> None:
        """Initialize ActivityRegistry and BehaviorArbiter for current pet directory."""
        try:
            manifest = load_pet_manifest(self.pet_dir)
        except Exception:
            manifest = PetManifest(
                schema_version=2,
                id=self.pet_dir.name or "unknown",
                name=self.pet_dir.name or "Unknown",
                capabilities=frozenset({BehaviorCategory.IDLE}),
                activities=(
                    PetActivity(
                        id="fallback_idle",
                        category=BehaviorCategory.IDLE,
                        visual=VisualBinding(ref="idle"),
                    ),
                ),
            )
        self._registry = ActivityRegistry(manifest)
        self._arbiter = BehaviorArbiter(self._registry)
        self._scheduler = LifeScheduler()
        self._active_request_id: str | None = None
        self._wave_timer_req_id: str | None = None
        self._jump_settle_req_id: str | None = None
        self._drag_req_id: str | None = None
        self._autonomous_req_id: str | None = None
        self._drag_active: bool = False

    @property
    def scale_factor(self) -> float:
        return self._scale

    @property
    def feeder_bar(self) -> SliceFeederBar:
        return self._feeder_bar

    @property
    def bubble(self) -> SpeechBubble:
        return self._bubble

    def open_feeder_input(self) -> None:
        """Open and focus the feeder input bar directly beneath the pet."""
        if self._current_state == PetState.SLEEPING:
            self._wake_up()
        if self._docked_edge is not None and not self._is_peek_expanded:
            self._expand_from_dock()
        self._feeder_bar.show()
        self._feeder_bar.anchor_to_pet(self.pos(), self.width(), self.height())
        self._feeder_bar.expand_input()

    def _on_slice_submitted(self, content: str) -> None:
        slice_item = RawSlice.create(content)
        self._slice_store.save(slice_item)
        req_id = f"req_slice_{time.monotonic()}"
        intent = BehaviorIntent(
            category=BehaviorCategory.GREET,
            preferred_traits=(ActivityTrait.SOCIAL,),
        )
        resolution = self._registry.resolve(intent)
        request = BehaviorRequest(
            request_id=req_id,
            intent=intent,
            resolution=resolution,
            source=BehaviorSource.DIRECT_INTERACTION,
            priority=BehaviorPriority.P3_SAFETY,
            duration_ms=2500,
            resumable=False,
        )
        decision = self._arbiter.submit(request)
        if decision.accepted:
            self._active_request_id = req_id
            self.apply_state(PetState.HAPPY)
        if not self._suppress_default_feedback:
            feedbacks = ["记下啦~", "存进成长抽屉了", "好灵感！已记录", "已沉淀到记忆库~"]
            self.say(random.choice(feedbacks), ttl_ms=2500)
        self.slice_fed.emit(content)

    def _on_bubble_user_replied(self, reply: str, orig: str) -> None:
        self.user_replied_to_bubble.emit(reply, orig)

    def _on_voice_clicked(self, active: bool) -> None:
        if active:
            self.apply_state(PetState.THINKING)
            self.say("我在听呢...（可随手在左侧记下灵感，语音输入支持 Win+H）", ttl_ms=3500)
        else:
            self.apply_state(PetState.IDLE)
            self.say("好嘞~随时叫我。", ttl_ms=2000)

    def set_scale(self, scale: float) -> None:
        """Dynamically adjust pet scaling factor and refresh spritesheets."""
        clamped = max(0.4, min(3.0, round(scale, 2)))
        if abs(self._scale - clamped) < 0.01:
            return
        self._scale = clamped
        self._load_spritesheets()
        self.apply_state(self._current_state, force=True)  # sheets were re-sliced
        self._save_position()
        self.scale_changed.emit(self._scale)

    def load_pet(self, pet_dir: Path) -> None:
        """Switch to another pet directory dynamically and refresh animation."""
        self.pet_dir = pet_dir
        self._init_arbiter()
        self._loaded_sheets.clear()
        self._load_spritesheets()
        self.apply_state(self._current_state, force=True)  # sheets were replaced

    def _load_spritesheets(self) -> None:
        """Preload sprite sheets from Clawd on Desk theme, Petdex, or legacy sprites."""
        self._stop_native_idle()
        self._native_idle_config = NativeIdleConfig.load(self.pet_dir)
        self._native_idle_frames = None
        screen = self.screen() or QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0

        if self._native_idle_config is not None:
            self._load_native_idle_frames(dpr)

        # 0. Try Clawd on Desk APNG Theme (e.g. Calico with rich autonomous behaviors)
        theme_json = self.pet_dir / "theme.json"
        is_theme_format = theme_json.is_file()
        pet_json = self.pet_dir / "pet.json"
        if not is_theme_format and pet_json.is_file():
            try:
                p_meta = json.loads(pet_json.read_text("utf-8"))
                if p_meta.get("format") == "theme":
                    is_theme_format = True
            except Exception:
                pass

        if is_theme_format:
            try:
                sheets = ThemeApngLoader.load_theme(self.pet_dir, scale=self._scale, dpr=dpr)
                if sheets:
                    self._loaded_sheets.update(sheets)
                    # For Calico themes, viewport margins are around 15px unscaled
                    self._art_padding_px = (
                        int(round(15 * self._scale)),
                        int(round(15 * self._scale)),
                    )
                    self._mini_cfg = ThemeApngLoader.load_mini_config(self.pet_dir)
                    return
            except SpriteSheetError:
                pass

        # 1. Try Petdex / Codex unified atlas sheet
        atlas_candidate: Path | None = None
        cols = 8
        rows = 9

        if pet_json.is_file():
            try:
                meta = json.loads(pet_json.read_text(encoding="utf-8"))
                if "spritesheetPath" in meta:
                    candidate = self.pet_dir / str(meta["spritesheetPath"])
                    if candidate.is_file():
                        atlas_candidate = candidate
                cols = int(meta.get("cols", 8))
                rows = int(meta.get("rows", 9))
            except (json.JSONDecodeError, OSError):
                pass

        if atlas_candidate is None:
            for name in ("spritesheet.webp", "sprite.webp", "spritesheet.png", "sprite.png"):
                candidate = self.pet_dir / name
                if candidate.is_file():
                    atlas_candidate = candidate
                    break

        if atlas_candidate is not None:
            try:
                sheets = PetdexAtlasLoader.load_atlas(
                    atlas_candidate,
                    cols=cols,
                    rows=rows,
                    scale=self._scale,
                    dpr=dpr,
                    trim_empty_frames=True,
                )
                self._loaded_sheets.update(sheets)
                self._measure_art_padding(atlas_candidate, cols=cols, rows=rows, factor=self._scale)
                return
            except SpriteSheetError:
                pass

        # 2. Fallback to legacy single sprite files
        self._art_padding_px = (0, 0)
        sprites_dir = self.pet_dir / "sprites"
        if not sprites_dir.is_dir():
            return

        known_files = {
            "idle": (sprites_dir / "idle.png", 8, 6),
            "walk": (sprites_dir / "walk.png", 6, 8),
            "sleep": (sprites_dir / "sleep.png", 4, 3),
            "placeholder": (sprites_dir / "placeholder.png", 1, 1),
        }

        for state_key, (path, frames, _fps) in known_files.items():
            if path.is_file():
                try:
                    # Legacy 32px sprites scale with a 2x base multiplier
                    factor = 2.0 * self._scale
                    sheet = SpriteSheet.load(path, frames=frames).scaled(factor, dpr=dpr)
                    self._loaded_sheets[state_key] = sheet
                    self._accumulate_art_padding(path, cols=frames, rows=1, factor=factor)
                except SpriteSheetError:
                    pass

    def _load_native_idle_frames(self, dpr: float) -> None:
        config = self._native_idle_config
        if config is None:
            return
        try:
            neutral = SpriteSheet.load(config.neutral_path).scaled(self._scale, dpr=dpr)
            blink = SpriteSheet.load(config.blink_path).scaled(self._scale, dpr=dpr)
        except SpriteSheetError:
            self._native_idle_config = None
            return
        if neutral.frame_width != blink.frame_width or neutral.frame_height != blink.frame_height:
            self._native_idle_config = None
            return
        self._native_idle_frames = (neutral.frames[0], blink.frames[0])

    def _measure_art_padding(
        self, image_path: Path, *, cols: int, rows: int, factor: float
    ) -> None:
        """Record the scaled transparent margin of a Petdex atlas."""
        image = QImage(str(image_path))
        if image.isNull():
            self._art_padding_px = (0, 0)
            return
        scaled = image.scaled(
            max(1, int(round(image.width() * factor))),
            max(1, int(round(image.height() * factor))),
            aspectMode=Qt.AspectRatioMode.IgnoreAspectRatio,
            mode=Qt.TransformationMode.FastTransformation,
        )
        self._art_padding_px = measure_art_padding(scaled, cols=cols, rows=rows)

    def _accumulate_art_padding(
        self, image_path: Path, *, cols: int, rows: int, factor: float
    ) -> None:
        """Widen the recorded margin with a legacy sheet's own margin."""
        image = QImage(str(image_path))
        if image.isNull():
            return
        scaled = image.scaled(
            max(1, int(round(image.width() * factor))),
            max(1, int(round(image.height() * factor))),
            aspectMode=Qt.AspectRatioMode.IgnoreAspectRatio,
            mode=Qt.TransformationMode.FastTransformation,
        )
        left, right = measure_art_padding(scaled, cols=cols, rows=rows)
        current_left, current_right = self._art_padding_px
        self._art_padding_px = (max(current_left, left), max(current_right, right))

    def _peek_reveal_px(self, edge: str) -> int:
        """How many pixels of this window must stay on screen when docked.

        That is the frame's transparent margin on the docking side plus a fixed
        sliver of real artwork. Using the measured margin is what keeps the pet
        visible at every scale; a fixed 24px revealed only transparency once the
        margin grew past it, so a large docked pet disappeared completely.
        """
        left_pad, right_pad = self._art_padding_px
        margin = right_pad if edge == "right" else left_pad
        return margin + PEEK_VISIBLE_ART_PX

    def _get_mini_sheet(self, state_name: str) -> SpriteSheet | None:
        """Get the sprite sheet for a mini state, applying edge flip if needed."""
        if self._mini_cfg.flip_assets:
            should_flip = self._docked_edge == "right"
        else:
            should_flip = self._docked_edge == "left"
        if should_flip:
            flipped_key = f"{state_name}-flipped"
            if flipped_key in self._loaded_sheets:
                return self._loaded_sheets[flipped_key]
            base = self._loaded_sheets.get(state_name)
            if base is not None:
                flipped = base.mirrored(horizontal=True)
                self._loaded_sheets[flipped_key] = flipped
                return flipped
        return self._loaded_sheets.get(state_name)

    def apply_state(self, state: PetState, *, force: bool = False) -> None:
        """Switch the pet's animated state.

        Re-applying the state already playing is a no-op unless `force` is set.
        Agent telemetry repeats the same state many times per turn (one event per
        tool call), and replaying the sheet each time reset the frame index to 0,
        so the pet visibly stuttered back to the first frame instead of running.
        """
        if state == self._current_state and not force:
            return
        self._current_state = state
        if state == PetState.IDLE and self._native_idle_frames is not None:
            self._autonomous_timer.stop()
            self._autonomous_done_timer.stop()
            self._in_autonomous_routine = False
            self._activate_native_idle()
            return
        self._stop_native_idle()
        # Any state change means something happened: restart the idle countdown,
        # and let a wake-up clear the doze. Sleeping is the only state that is
        # allowed to persist, so it must not re-arm its own timer.
        if state == PetState.SLEEPING:
            self._autonomous_timer.stop()
            self._autonomous_done_timer.stop()
            self._in_autonomous_routine = False
            self._nap_timer.start(NAP_DURATION_MS)
        else:
            self._nap_timer.stop()
            if (
                state == PetState.IDLE
                and not self._in_autonomous_routine
                and self._docked_edge is None
            ):
                schedule = get_schedule_for_time()
                pause = (
                    random.randint(3000, 8000)
                    if schedule.is_work_phase
                    else random.randint(schedule.min_pause_ms, schedule.max_pause_ms)
                )
                self._autonomous_timer.start(pause)
            elif state != PetState.IDLE:
                self._autonomous_timer.stop()
                self._autonomous_done_timer.stop()
                self._in_autonomous_routine = False

        if (
            self._docked_edge is not None
            and self._mini_cfg.supported
            and "mini-idle" in self._loaded_sheets
        ):
            mini_map = {
                PetState.IDLE: "mini-idle",
                PetState.SLEEPING: "mini-sleep",
                PetState.HAPPY: "mini-happy",
            }
            mini_key = mini_map.get(state, "mini-idle")
            mini_sheet = self._get_mini_sheet(mini_key)
            if mini_sheet is not None:
                self._player.play(mini_sheet, loop=(state != PetState.HAPPY))
                return

        state_candidates: dict[PetState, tuple[list[str], int, bool]] = {
            PetState.IDLE: (["idle"], 6, True),
            PetState.SLEEPING: (["sleep", "idle"], 3, True),
            PetState.THINKING: (["review", "waiting", "idle"], 6, True),
            PetState.WORKING: (["running", "running-right", "walk", "idle"], 8, True),
            PetState.HAPPY: (["waving", "jumping", "idle"], 6, True),
            PetState.ERROR: (["failed", "idle"], 6, True),
            PetState.WAITING: (["waiting", "idle"], 6, True),
        }

        candidates, fps, loop = state_candidates.get(state, (["idle"], 6, True))

        sheet: SpriteSheet | None = None
        for key in candidates:
            if key in self._loaded_sheets:
                sheet = self._loaded_sheets[key]
                break

        if sheet is None:
            sheet = self._loaded_sheets.get("idle")

        if sheet is not None:
            # For 6-frame atlas pets (like Vasu, Tiko), pause 3.0~5.5s between loops
            # so the pet only blinks once naturally every few seconds (matching Codex).
            is_short_idle = state == PetState.IDLE and sheet.frame_count <= 8
            loop_delay = (3000, 5500) if is_short_idle else None
            self._player.play(sheet, fps=fps, loop=loop, loop_delay_range_ms=loop_delay)

    def _activate_native_idle(self) -> None:
        frames = self._native_idle_frames
        if frames is None:
            return
        self._player.stop()
        self._native_idle_active = True
        self._native_blink_restore_timer.stop()
        self._native_blink_timer.stop()
        self._on_frame_changed(frames[0])
        self._schedule_native_blink()

    def _stop_native_idle(self) -> None:
        self._native_idle_active = False
        self._native_blink_timer.stop()
        self._native_blink_restore_timer.stop()

    def _schedule_native_blink(self) -> None:
        config = self._native_idle_config
        if not self._native_idle_active or config is None:
            return
        self._native_blink_timer.start(
            random.randint(config.min_interval_ms, config.max_interval_ms)
        )

    def _start_native_blink(self) -> None:
        config = self._native_idle_config
        frames = self._native_idle_frames
        if not self._native_idle_active or config is None or frames is None:
            return
        self._on_frame_changed(frames[1])
        self.native_blink_started.emit(time.time())
        self._native_blink_restore_timer.start(config.blink_duration_ms)

    def _finish_native_blink(self) -> None:
        frames = self._native_idle_frames
        if not self._native_idle_active or frames is None:
            return
        self._on_frame_changed(frames[0])
        self._schedule_native_blink()

    def say(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display a speech bubble above the pet."""
        if self._current_state == PetState.SLEEPING:
            self._wake_up()  # a message is activity; a sleeping pet must answer
        if self._docked_edge is not None and not self._is_peek_expanded:
            self._expand_from_dock()
            self._retract_timer.start(ttl_ms + 1000)

        self._bubble.show_message(text, ttl_ms=ttl_ms)
        self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())

    def reset_to_default_position(self) -> None:
        """Emergency reset: brings the pet back to visible screen bottom-right corner."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            new_x = geom.right() - self.width() - 25
            new_y = geom.bottom() - self.height() - 15
            self._docked_edge = None
            self._is_peek_expanded = False
            self.move(new_x, new_y)
            self._save_position()
            if self._bubble.isVisible():
                self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())
            if self._feeder_bar.isVisible():
                self._feeder_bar.anchor_to_pet(self.pos(), self.width(), self.height())

    def _on_frame_changed(self, frame: QPixmap) -> None:
        self._label.setPixmap(frame)
        geom_size = frame.deviceIndependentSize().toSize()
        self.resize(geom_size)
        self._label.resize(geom_size)
        if self._bubble.isVisible():
            self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())
        if self._feeder_bar.isVisible():
            self._feeder_bar.anchor_to_pet(self.pos(), self.width(), self.height())

    def _get_config_path(self) -> Path:
        return self._position_config_path

    def _restore_position(self) -> None:
        cfg = self._get_config_path()
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            fallback_x = geom.right() - 220
            fallback_y = geom.bottom() - 200

            if cfg.is_file():
                try:
                    data = json.loads(cfg.read_text("utf-8"))
                    saved_x = int(data.get("x", fallback_x))
                    saved_y = int(data.get("y", fallback_y))
                    self._docked_edge = data.get("docked_edge", None)
                    if "scale" in data:
                        saved_scale = float(data["scale"])
                        if 0.3 <= saved_scale <= 3.0 and abs(self._scale - saved_scale) >= 0.01:
                            self._scale = saved_scale
                            self._load_spritesheets()

                    if self._mini_cfg.supported and "mini-idle" in self._loaded_sheets:
                        min_clamped_x = geom.left() - int(
                            round(self.width() * self._mini_cfg.offset_ratio)
                        )
                        max_clamped_x = geom.right() - int(
                            round(self.width() * (1 - self._mini_cfg.offset_ratio))
                        )
                    else:
                        min_clamped_x = geom.left() - self.width() + self._peek_reveal_px("left")
                        max_clamped_x = geom.right() - self._peek_reveal_px("right")
                    clamped_x = max(min_clamped_x, min(saved_x, max_clamped_x))
                    clamped_y = max(geom.top(), min(saved_y, geom.bottom() - self.height()))
                    self.move(clamped_x, clamped_y)
                    if self._docked_edge is not None:
                        self._retract_to_dock()
                    return
                except (json.JSONDecodeError, ValueError, OSError):
                    pass
            self.move(fallback_x, fallback_y)

    def _save_position(self) -> None:
        cfg = self._get_config_path()
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                json.dumps(
                    {
                        "x": self.x(),
                        "y": self.y(),
                        "docked_edge": self._docked_edge,
                        "scale": round(self._scale, 2),
                    }
                ),
                "utf-8",
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Peek Docking & Hover Animations
    # ------------------------------------------------------------------
    def _doze_off(self) -> None:
        """Manually put the pet to sleep (e.g., from DND/tray menu)."""
        if self._greeting_active:
            return
        req_id = f"req_explicit_sleep_{time.monotonic()}"
        intent = BehaviorIntent(category=BehaviorCategory.SLEEP)
        resolution = self._registry.resolve(intent)
        request = BehaviorRequest(
            request_id=req_id,
            intent=intent,
            resolution=resolution,
            source=BehaviorSource.EXPLICIT_USER,
            priority=BehaviorPriority.P4_EXPLICIT_USER,
            protection=ProtectionLevel.PROTECTED_SLEEP,
            interruptible=False,
            resumable=False,
        )
        decision = self._arbiter.submit(request)
        if decision.accepted:
            self._active_request_id = req_id
            self.apply_state(PetState.SLEEPING)

    def notify_user_working(self) -> None:
        """Ambiently record that user is actively working with tools/agents."""
        self._is_user_working = True
        self._user_working_timer.start()

    def notify_sanctuary_state(self, active: bool) -> None:
        """Ambiently record whether emotional sanctuary (meltdown) mode is active."""
        self._sanctuary_active = active

    def _clear_user_working(self) -> None:
        self._is_user_working = False

    def _on_nap_timeout(self) -> None:
        """Handle catnap timer timeout: only wake if sleep is NOT protected DND sleep."""
        if hasattr(self, "_arbiter") and self._arbiter.is_protected_sleep():
            return
        self._wake_up()

    def _wake_up(self) -> None:
        """Return to a resting, awake state after the pet had dozed off."""
        if self._current_state == PetState.SLEEPING:
            req_id = f"req_wake_{time.monotonic()}"
            intent = BehaviorIntent(category=BehaviorCategory.IDLE)
            resolution = self._registry.resolve(intent)
            request = BehaviorRequest(
                request_id=req_id,
                intent=intent,
                resolution=resolution,
                source=BehaviorSource.EXPLICIT_USER,
                priority=BehaviorPriority.P4_EXPLICIT_USER,
                protection=ProtectionLevel.UNPROTECTED,
                interruptible=True,
            )
            decision = self._arbiter.submit(request)
            if not decision.accepted:
                return

            self._active_request_id = req_id
            self._nap_timer.stop()
            self._in_autonomous_routine = False
            self._schedule_next_autonomous_routine()
            self._current_state = PetState.IDLE
            waking_sheet = self._loaded_sheets.get("waking")
            if waking_sheet is not None:
                self._player.play(waking_sheet, loop=False)
                self._wave_timer_req_id = req_id
                self._wave_timer.start(1600)
            else:
                self.apply_state(PetState.IDLE, force=True)
                self._arbiter.complete(req_id)
    def _schedule_next_autonomous_routine(
        self, *, initial: bool = False, delay_ms: int | None = None
    ) -> None:
        """Schedule the next consideration for autonomous daily life activities."""
        if delay_ms is not None:
            pause = delay_ms
        elif initial:
            pause = int(self._scheduler.config.consideration_min_sec * 1000)
        else:
            pause = int(
                random.uniform(
                    self._scheduler.config.consideration_min_sec,
                    self._scheduler.config.consideration_max_sec,
                )
                * 1000
            )
        self._autonomous_timer.start(pause)

    def _start_autonomous_routine(self) -> None:
        """Consider and potentially perform an independent daily life activity."""
        if (
            self._current_state != PetState.IDLE
            or self._docked_edge is not None
            or self._greeting_active
            or self._has_moved
            or self._in_autonomous_routine
        ):
            self._schedule_next_autonomous_routine()
            return

        if hasattr(self, "_arbiter") and self._arbiter.is_protected_sleep():
            return

        active_req = self._arbiter.active_request if hasattr(self, "_arbiter") else None
        phase = get_schedule_for_time().phase
        ctx = LifeContext(
            circadian_phase=phase,
            hour=time.localtime().tm_hour,
            agent_active=getattr(self, "_is_user_working", False),
            sanctuary_active=self._sanctuary_active,
            mini_mode_docked=(self._docked_edge is not None),
            feeder_active=self._feeder_bar.isVisible(),
            bubble_active=self._bubble.isVisible(),
        )
        intent, next_delay_sec = self._scheduler.consider(
            self._registry, active_request=active_req, context=ctx
        )
        next_delay_ms = max(4000, int(next_delay_sec * 1000))

        if intent is None:
            # Silence first: remain peacefully in quiet presence
            self._schedule_next_autonomous_routine(delay_ms=next_delay_ms)
            return

        resolution = self._registry.resolve(intent)
        if not resolution.candidates or resolution.no_op:
            self._schedule_next_autonomous_routine(delay_ms=next_delay_ms)
            return

        candidate = resolution.candidates[0]
        dur_sec = self._scheduler.sample_duration_sec()
        dur_ms = int(dur_sec * 1000)
        req_id = f"req_auto_{time.monotonic()}"

        request = BehaviorRequest(
            request_id=req_id,
            intent=intent,
            resolution=resolution,
            source=BehaviorSource.AUTONOMOUS,
            priority=BehaviorPriority.P1_AUTONOMOUS,
            duration_ms=dur_ms,
            interruptible=True,
            resumable=False,
        )
        decision = self._arbiter.submit(request)
        if not decision.accepted:
            self._schedule_next_autonomous_routine(delay_ms=next_delay_ms)
            return

        self._active_request_id = req_id
        self._autonomous_req_id = req_id
        self._in_autonomous_routine = True
        self._stop_native_idle()
        self._scheduler.record_activity_started(
            intent.category, intent.direction, dur_sec, candidate.activity.id
        )

        visual_ref = candidate.activity.visual.ref
        sheet = self._loaded_sheets.get(visual_ref)
        if sheet is not None:
            if candidate.mirror_required:
                sheet = sheet.mirrored(horizontal=True)
            self._player.play(sheet, loop=(candidate.activity.loop == LoopMode.LOOP))
            self._autonomous_done_timer.start(dur_ms)
        else:
            self._finish_autonomous_routine()

    def _finish_autonomous_routine(self) -> None:
        """Finish the daily life activity and settle back to resting idle."""
        self._in_autonomous_routine = False
        auto_req_id = getattr(self, "_autonomous_req_id", None)
        if auto_req_id and hasattr(self, "_arbiter"):
            self._arbiter.complete(auto_req_id)
        if hasattr(self, "_scheduler"):
            self._scheduler.record_activity_finished()

        if self._docked_edge is None and not self._has_moved:
            self.apply_state(PetState.IDLE, force=True)
        self._schedule_next_autonomous_routine()

    def play_poke_reaction(self) -> None:
        """Play short poke reaction if available, then return to current state."""
        if hasattr(self, "_arbiter") and self._arbiter.is_protected_sleep():
            return

        req_id = f"req_poke_{time.monotonic()}"
        intent = BehaviorIntent(
            category=BehaviorCategory.REACT,
            preferred_traits=(ActivityTrait.CASUAL,),
        )
        resolution = self._registry.resolve(intent)
        request = BehaviorRequest(
            request_id=req_id,
            intent=intent,
            resolution=resolution,
            source=BehaviorSource.DIRECT_INTERACTION,
            priority=BehaviorPriority.P2_DIRECT_INTERACTION,
            cooldown_key="poke_reaction",
            duration_ms=1200,
        )
        decision = self._arbiter.submit(request)
        if not decision.accepted:
            return

        self._active_request_id = req_id
        self._wave_timer_req_id = req_id
        if (
            self._docked_edge is not None
            and self._mini_cfg.supported
            and "mini-happy" in self._loaded_sheets
        ):
            poke_sheet = self._get_mini_sheet("mini-happy")
            if poke_sheet is not None:
                self._player.play(poke_sheet, loop=False)
                self._wave_timer.start(1500)
                return
        sheet = (
            self._loaded_sheets.get("react-poke")
            or self._loaded_sheets.get("poke")
            or self._loaded_sheets.get("jumping")
            or self._loaded_sheets.get("waving")
        )
        if sheet is not None:
            self._player.play(sheet, loop=False)
            self._wave_timer.start(1200)
    def test_action(self, action_name: str) -> bool:
        """Manually trigger and continuously play an action for smoothness testing."""
        sheet = self._loaded_sheets.get(action_name)
        if sheet is None:
            return False
        self._autonomous_timer.stop()
        self._autonomous_done_timer.stop()
        self._in_autonomous_routine = False
        fps = getattr(sheet, "default_fps", 6)
        durations = getattr(sheet, "frame_durations_ms", None)
        dur_str = f"{durations[0]}ms/帧" if durations else f"{fps} FPS"
        self._player.play(sheet, loop=True)
        self.say(f"🧪 动作测试: [{action_name}] · {sheet.frame_count}帧 ({dur_str})", ttl_ms=3000)
        return True

    def stop_action_test(self) -> None:
        """Exit action test mode and resume regular life rhythm."""
        self.apply_state(PetState.IDLE, force=True)
        self._schedule_next_autonomous_routine()
        self.say("⏹ 已退出测试模式，恢复自主生活节律", ttl_ms=2000)

    def _trigger_hover_jump(self) -> bool:
        """Trigger a lively hop when cursor hovers over the pet (Codex behavior)."""
        if self._docked_edge is not None:
            return False
        if hasattr(self, "_arbiter") and self._arbiter.is_protected_sleep():
            return False

        req_id = f"req_jump_{time.monotonic()}"
        intent = BehaviorIntent(
            category=BehaviorCategory.PLAY,
            preferred_traits=(ActivityTrait.ACTIVE,),
        )
        resolution = self._registry.resolve(intent)
        request = BehaviorRequest(
            request_id=req_id,
            intent=intent,
            resolution=resolution,
            source=BehaviorSource.DIRECT_INTERACTION,
            priority=BehaviorPriority.P2_DIRECT_INTERACTION,
            cooldown_key="hover_jump",
            duration_ms=700,
            resumable=False,
        )
        decision = self._arbiter.submit(request)
        if not decision.accepted:
            return False

        jump_sheet = self._loaded_sheets.get("jumping") or self._loaded_sheets.get("jump")
        if jump_sheet is not None:
            self._active_request_id = req_id
            self._jump_settle_req_id = req_id
            self._player.play(jump_sheet, fps=8, loop=False)
            dur_ms = max(400, int((jump_sheet.frame_count / 8.0) * 1000) + 80)
            self._jump_settle_timer.start(dur_ms)
            return True
        return False

    def _finish_hover_jump(self) -> None:
        """Settle back into current state after hover jump finishes."""
        timer_req_id = getattr(self, "_jump_settle_req_id", None)
        if timer_req_id and hasattr(self, "_arbiter"):
            decision = self._arbiter.complete(timer_req_id)
            if not decision.accepted or decision.action == ArbiterAction.NO_OP:
                return

        if self._docked_edge is None and not self._has_moved:
            self.apply_state(self._current_state, force=True)

    def _start_greeting(self, *, force: bool = False) -> None:
        """Wave hello once when the user's cursor reaches the pet, with measured cooldown."""
        if self._greeting_active:
            return
        if hasattr(self, "_arbiter") and self._arbiter.is_protected_sleep():
            return

        req_id = f"req_greet_{time.monotonic()}"
        intent = BehaviorIntent(
            category=BehaviorCategory.GREET,
            preferred_traits=(ActivityTrait.SOCIAL,),
        )
        resolution = self._registry.resolve(intent)
        priority = (
            BehaviorPriority.P4_EXPLICIT_USER if force else BehaviorPriority.P2_DIRECT_INTERACTION
        )
        request = BehaviorRequest(
            request_id=req_id,
            intent=intent,
            resolution=resolution,
            source=BehaviorSource.EXPLICIT_USER if force else BehaviorSource.DIRECT_INTERACTION,
            priority=priority,
            cooldown_key="hover_greet" if not force else None,
            duration_ms=1400,
            resumable=False,
        )
        decision = self._arbiter.submit(request)
        if not decision.accepted:
            return

        self._active_request_id = req_id
        self._wave_timer_req_id = req_id
        self._greeting_active = True
        if (
            self._docked_edge is not None
            and self._mini_cfg.supported
            and "mini-peek" in self._loaded_sheets
        ):
            peek_sheet = self._get_mini_sheet("mini-peek")
            if peek_sheet is not None:
                self._player.play(peek_sheet, loop=False)
        else:
            self.apply_state(PetState.HAPPY)
        self._wave_timer.start(1400)

    def _finish_greeting(self) -> None:
        """End the hover wave and settle back to resting."""
        self._greeting_active = False
        timer_req_id = getattr(self, "_wave_timer_req_id", None)
        if timer_req_id and hasattr(self, "_arbiter"):
            self._arbiter.complete(timer_req_id)

        if (
            self._docked_edge is not None
            and self._mini_cfg.supported
            and "mini-idle" in self._loaded_sheets
        ):
            sheet = self._get_mini_sheet("mini-idle")
            if sheet is not None:
                self._player.play(sheet, loop=True)
        else:
            self.apply_state(PetState.IDLE)

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        """Mouse hover: peek out if docked, wake up if sleeping, wave hello."""
        if hasattr(self, "_arbiter") and self._arbiter.is_protected_sleep():
            # Protected sleep (DND) must NEVER be interrupted by hover!
            event.accept()
            return

        if self._in_autonomous_routine:
            self._autonomous_done_timer.stop()
            self._in_autonomous_routine = False
        self._wake_up()
        if self._docked_edge is not None:
            self._retract_timer.stop()
            self._expand_from_dock()
        else:
            if not self._trigger_hover_jump():
                self._start_greeting()
        if self._docked_edge is None:
            self._feeder_bar.anchor_to_pet(self.pos(), self.width(), self.height())
            self._feeder_bar.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        """Mouse leave: schedule retracting back to docked peek state and handle bar."""
        if self._docked_edge is not None and not self._has_moved:
            if not self._retract_timer.isActive():
                self._retract_timer.start(800)
        cursor_pos = QCursor.pos()
        if not self._feeder_bar.geometry().contains(cursor_pos):
            if (
                self._feeder_bar.current_mode == "pill"
                and not self._feeder_bar.is_voice_active
                and hasattr(self._feeder_bar, "_retract_timer")
            ):
                self._feeder_bar._retract_timer.start(300)
        super().leaveEvent(event)

    def _check_cursor_outside_polling(self) -> None:
        """Reliable periodic check to detect cursor leaving pet and bubble area."""
        if self._docked_edge is not None and self._is_peek_expanded and not self._has_moved:
            cursor_pos = QCursor.pos()
            in_pet = self.geometry().contains(cursor_pos)
            in_bubble = self._bubble.isVisible() and self._bubble.geometry().contains(cursor_pos)
            in_feeder = self._feeder_bar.isVisible() and self._feeder_bar.geometry().contains(
                cursor_pos
            )
            if not in_pet and not in_bubble and not in_feeder:
                if not self._retract_timer.isActive():
                    self._retract_timer.start(800)  # retract after 800ms
            else:
                self._retract_timer.stop()

    def _expand_from_dock(self) -> None:
        """Slide fully out of the edge so user can see whole pet body."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None or self._docked_edge is None:
            return
        geom = screen.availableGeometry()
        if self._mini_cfg.supported and "mini-idle" in self._loaded_sheets:
            peek_dist = max(25, int(round(self.width() * 0.15)))
            if self._docked_edge == "right":
                base_x = geom.right() - int(round(self.width() * (1 - self._mini_cfg.offset_ratio)))
                self.move(base_x - peek_dist, self.y())
            elif self._docked_edge == "left":
                base_x = geom.left() - int(round(self.width() * self._mini_cfg.offset_ratio))
                self.move(base_x + peek_dist, self.y())
            peek_sheet = self._get_mini_sheet("mini-peek")
            if peek_sheet is not None:
                self._player.play(peek_sheet, loop=False)
        else:
            if self._docked_edge == "right":
                self.move(geom.right() - self.width() + 1, self.y())
            elif self._docked_edge == "left":
                self.move(geom.left(), self.y())
        self._is_peek_expanded = True
        self._hover_poll_timer.start()
        if self._bubble.isVisible():
            self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())
        self._feeder_bar.show()
        self._feeder_bar.anchor_to_pet(self.pos(), self.width(), self.height())

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Ctrl + Wheel: smoothly zoom in/out pet scale with instant bubble feedback."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            step = 0.1 if delta > 0 else -0.1
            new_scale = round(self._scale + step, 1)
            new_scale = max(0.5, min(2.5, new_scale))
            if abs(new_scale - self._scale) >= 0.04:
                self.set_scale(new_scale)
                percent = int(round(self._scale * 100))
                self.say(f"🔍 伴生体大小: {percent}%", ttl_ms=1500)
            event.accept()
            return
        super().wheelEvent(event)

    def _retract_to_dock(self) -> None:
        """Slide half-body into screen edge, leaving only the head peeking out."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None or self._docked_edge is None:
            return
        geom = screen.availableGeometry()
        if self._mini_cfg.supported and "mini-idle" in self._loaded_sheets:
            if self._docked_edge == "right":
                target_x = geom.right() - int(
                    round(self.width() * (1 - self._mini_cfg.offset_ratio))
                )
            else:
                target_x = geom.left() - int(round(self.width() * self._mini_cfg.offset_ratio))
            self.move(target_x, self.y())
            mini_state = "mini-sleep" if self._current_state == PetState.SLEEPING else "mini-idle"
            sheet = self._get_mini_sheet(mini_state)
            if sheet is not None:
                self._player.play(sheet, loop=True)
        else:
            if self._docked_edge == "right":
                self.move(geom.right() - self._peek_reveal_px("right"), self.y())
            elif self._docked_edge == "left":
                self.move(geom.left() - self.width() + self._peek_reveal_px("left"), self.y())
        self._is_peek_expanded = False
        self._feeder_bar.hide()
        self._hover_poll_timer.stop()
        self._save_position()

    # ------------------------------------------------------------------
    # Mouse interaction (Screen-clamped Dragging and Edge Snapping)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._in_autonomous_routine:
                self._autonomous_done_timer.stop()
                self._in_autonomous_routine = False
            self._wake_up()  # touching the pet is activity: it stops dozing
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
            self._last_drag_x = event.globalPosition().toPoint().x()
            self._current_drag_dir = None
            self._has_moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and self._press_pos is not None:
            cur_pos = event.globalPosition().toPoint()
            dist = (cur_pos - self._press_pos).manhattanLength()
            if dist >= CLICK_DRAG_THRESHOLD_PX:
                desired_pos = cur_pos - self._drag_offset
                if not getattr(self, "_drag_active", False):
                    self._drag_active = True
                    req_id = f"req_drag_{time.monotonic()}"
                    intent = BehaviorIntent(
                        category=BehaviorCategory.MOVE,
                        direction=BehaviorDirection.NONE,
                    )
                    resolution = self._registry.resolve(intent)
                    request = BehaviorRequest(
                        request_id=req_id,
                        intent=intent,
                        resolution=resolution,
                        source=BehaviorSource.EXPLICIT_USER,
                        priority=BehaviorPriority.P4_EXPLICIT_USER,
                        protection=ProtectionLevel.PROTECTED_INTERACTION,
                        interruptible=True,
                        resumable=False,
                    )
                    decision = self._arbiter.submit(request)
                    if decision.accepted:
                        self._active_request_id = req_id
                        self._drag_req_id = req_id
                # Directional running / drag animation (Codex running-right/left behavior)
                dx = cur_pos.x() - self._last_drag_x
                if dx > 1 and self._current_drag_dir != "right":
                    self._current_drag_dir = "right"
                    right_sheet = (
                        self._loaded_sheets.get("running-right")
                        or self._loaded_sheets.get("react-drag")
                        or self._loaded_sheets.get("drag")
                    )
                    if right_sheet is not None:
                        self._player.play(right_sheet, fps=8, loop=True)
                elif dx < -1 and self._current_drag_dir != "left":
                    self._current_drag_dir = "left"
                    left_sheet = (
                        self._loaded_sheets.get("running-left")
                        or self._loaded_sheets.get("react-drag")
                        or self._loaded_sheets.get("drag")
                    )
                    if left_sheet is not None:
                        self._player.play(left_sheet, fps=8, loop=True)
                elif not self._has_moved:
                    self._has_moved = True
                    drag_sheet = (
                        self._loaded_sheets.get("react-drag")
                        or self._loaded_sheets.get("running-right")
                        or self._loaded_sheets.get("drag")
                    )
                    if drag_sheet is not None:
                        self._player.play(drag_sheet, loop=True)

                self._last_drag_x = cur_pos.x()
                self._has_moved = True

                screen = self.screen() or QApplication.primaryScreen()
                if screen is not None:
                    geom = screen.availableGeometry()
                    if self._mini_cfg.supported and "mini-idle" in self._loaded_sheets:
                        min_x = geom.left() - int(round(self.width() * self._mini_cfg.offset_ratio))
                        max_x = geom.right() - int(
                            round(self.width() * (1 - self._mini_cfg.offset_ratio))
                        )
                    else:
                        min_x = geom.left() - self.width() + self._peek_reveal_px("left")
                        max_x = geom.right() - self._peek_reveal_px("right")
                    clamped_x = max(min_x, min(desired_pos.x(), max_x))
                    clamped_y = max(geom.top(), min(desired_pos.y(), geom.bottom() - self.height()))
                    self.move(clamped_x, clamped_y)
                    self.position_changed.emit(clamped_x, clamped_y)
                else:
                    self.move(desired_pos)

                if self._bubble.isVisible():
                    self._bubble.anchor_to_pet(self.pos(), self.width(), self.height())
                if self._feeder_bar.isVisible():
                    self._feeder_bar.anchor_to_pet(self.pos(), self.width(), self.height())
            event.accept()
        else:
            cursor_y = event.position().y()
            if cursor_y >= self.height() - 44:
                if self._feeder_bar.current_mode == "handle":
                    self._feeder_bar.show_pill()
            elif cursor_y < self.height() - 60:
                if (
                    self._feeder_bar.current_mode == "pill"
                    and not self._feeder_bar.is_voice_active
                    and hasattr(self._feeder_bar, "_retract_timer")
                ):
                    self._feeder_bar._retract_timer.start(300)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._current_drag_dir = None
            self._drag_offset = None
            if getattr(self, "_drag_active", False):
                self._drag_active = False
                drag_req_id = getattr(self, "_drag_req_id", None)
                if drag_req_id and hasattr(self, "_arbiter"):
                    self._arbiter.complete(drag_req_id)
            if self._has_moved:
                screen = self.screen() or QApplication.primaryScreen()
                if screen is not None:
                    geom = screen.availableGeometry()
                    cur_x = self.x()
                    cur_y = self.y()

                    # Check Right Edge Docking
                    if (
                        abs(geom.right() - self.width() - cur_x) < EDGE_SNAP_DISTANCE_PX
                        or cur_x > geom.right() - self.width()
                    ):
                        self._docked_edge = "right"
                        self._retract_to_dock()
                    # Check Left Edge Docking
                    elif abs(cur_x - geom.left()) < EDGE_SNAP_DISTANCE_PX or cur_x < geom.left():
                        self._docked_edge = "left"
                        self._retract_to_dock()
                    else:
                        self._docked_edge = None
                        if abs(geom.bottom() - self.height() - cur_y) < EDGE_SNAP_DISTANCE_PX:
                            cur_y = geom.bottom() - self.height()
                            self.move(cur_x, cur_y)
                        self._save_position()
                else:
                    self._save_position()
                # Restore state animation from drag suspension
                if self._docked_edge is None:
                    self.apply_state(self._current_state, force=True)
            else:
                self.play_poke_reaction()
                self.clicked.emit()
            # The drag is finished, so clear the flag: it only exists to suppress
            # auto-retract *during* a drag. Leaving it set disabled both the
            # leaveEvent path and the cursor poll for the rest of the session, so a
            # pet docked by dragging peeking out on hover and then never retracted.
            self._has_moved = False
            event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._hover_poll_timer.stop()
        self._retract_timer.stop()
        self._autonomous_timer.stop()
        self._autonomous_done_timer.stop()
        self._nap_timer.stop()
        self._user_working_timer.stop()
        self._wave_timer.stop()
        self._stop_native_idle()
        self._bubble.close()
        self._feeder_bar.close()
        self._player.stop()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._docked_edge is None or self._is_peek_expanded:
            self._feeder_bar.anchor_to_pet(self.pos(), self.width(), self.height())
            self._feeder_bar.show_handle()
            self._feeder_bar.show()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        self._feeder_bar.hide()
        self._bubble.hide()
        super().hideEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self.context_menu_requested.emit(event.globalPos())
        event.accept()
