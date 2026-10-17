"""Main interactive runner for Co-evolving AI Companion (Phase 1)."""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.body.chronicle_window import ChronicleViewerWindow
from src.body.contracts import PetState
from src.body.controller import BodyController
from src.body.menu_style import get_menu_stylesheet
from src.body.settings_window import SettingsWindow
from src.body.window import PetWindow
from src.connectors.contracts import AgentEvent, AgentEventType
from src.connectors.event_bus import LocalEventBus
from src.connectors.hermes_connector import HermesConnector
from src.connectors.hook_manager import AgentHookManager
from src.connectors.http_server import CompanionHttpServer
from src.connectors.settings import AgentSettingsStore
from src.core.cold_start import ColdStartPolicy
from src.core.intervention import InterventionPolicy
from src.core.sanctuary import SanctuaryGuard
from src.core.state_watcher import StateWatcher
from src.feeder.contracts import RawSlice
from src.feeder.hotkey import DEFAULT_FEEDER_HOTKEY, GlobalHotkeyListener, hotkey_display
from src.feeder.overlay import SliceFeederOverlay
from src.feeder.storage import SliceStore
from src.memory.store import ChronicleStore, SliceRecord

# Evidence decay runs at startup and once a day thereafter.
_PRUNE_INTERVAL_MS = 24 * 60 * 60 * 1000

# Low-frequency State Care intervention check (overwork & late-night nudge).
# Evaluates the 3 Gates every 5 minutes; stays 100% silent if in flight or quota full.
_CARE_CHECK_INTERVAL_MS = 5 * 60 * 1000
_IN_FLIGHT_COOLDOWN_SECONDS = 30.0


class CompanionApp:
    """Orchestrates Desktop Pet Body, Slice Feeder, and Growth Core in one process."""

    def __init__(self) -> None:
        existing_app = QApplication.instance()
        if isinstance(existing_app, QApplication):
            self.app = existing_app
        else:
            self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 0. Multi-Agent & Companion Settings
        self.agent_settings = AgentSettingsStore()
        self.hook_manager = AgentHookManager()
        self.settings_window = SettingsWindow(self.agent_settings, self.hook_manager)
        self.settings_window.pet_changed.connect(self._on_pet_changed)
        self.settings_window.scale_changed.connect(self._on_scale_changed)
        self.settings_window.hotkey_changed.connect(self._on_hotkey_changed)

        # 1. Desktop Body (Defaults to Calico, or saved pet preference)
        selected_pet = self.agent_settings.selected_pet
        assets_dir = Path("assets") / "pets" / selected_pet
        if not assets_dir.is_dir():
            assets_dir = Path("assets") / "pets" / "calico"
        if not assets_dir.is_dir():
            assets_dir = Path("assets") / "pets" / "tiko"
        if not assets_dir.is_dir():
            assets_dir = Path("assets") / "pets" / "claw"

        self.window = PetWindow(assets_dir)
        self.controller = BodyController(self.window)

        # 2. Slice Feeder & Chronicle Store
        self.store = SliceStore(Path("data") / "raw_slices.jsonl")
        self.chronicle = ChronicleStore()
        self.chronicle.import_slices_jsonl()
        self.chronicle_window = ChronicleViewerWindow(self.chronicle)
        self.overlay = SliceFeederOverlay()
        self.overlay.slice_submitted.connect(self._on_slice_submitted)

        # 3. Growth Core & Sanctuary
        self.guard = SanctuaryGuard()
        self.cold_start = ColdStartPolicy.from_persisted_first_seen()
        self.watcher = StateWatcher(overwork_threshold_hours=3.0)
        self.intervention = InterventionPolicy(
            sanctuary=self.guard,
            cold_start=self.cold_start,
            watcher=self.watcher,
        )
        # Page 3 reports these live states, so it must share the real instances.
        self.settings_window.set_core_handles(sanctuary=self.guard, cold_start=self.cold_start)
        self.settings_window.chronicle = self.chronicle

        # 4. Connectors & Event Bus
        # Data Plane: Agent events record rhythm (watcher) and persist evidence (chronicle).
        # Control Plane is decoupled: agent events NEVER directly drive pet body state,
        # preventing state thrashing and multi-agent posture collisions (AGENTS.md section 4).
        self._last_agent_active_at: datetime | None = None
        self.bus = LocalEventBus(
            on_event_received=self._on_agent_event_received,
            store=self.chronicle,
        )
        self.hermes = HermesConnector(self.bus)

        # 5. Local HTTP Server
        self.http_server = CompanionHttpServer(
            self.bus,
            self.controller,
            settings_store=self.agent_settings,
            hook_manager=self.hook_manager,
            store=self.chronicle,
            intervention=self.intervention,
        )
        self.http_server.start()
        # Pet click interaction
        self.window.clicked.connect(self._on_pet_clicked)

        # Setup System Tray & Hotkey
        self._setup_tray(assets_dir)
        self._setup_hotkey()
        self._setup_decay()
        self._setup_state_care()

    def _setup_hotkey(self) -> None:
        """Register the configured global hotkey that summons the slice feeder.

        The combination is user-owned (settings window), so an unusable stored
        value falls back to the default rather than leaving the feeder
        unreachable.
        """
        spec = self.agent_settings.feeder_hotkey
        try:
            self.hotkey = GlobalHotkeyListener(spec, self.overlay.toggle_or_show)
            self.hotkey.start()
        except ValueError:
            self.hotkey = GlobalHotkeyListener(DEFAULT_FEEDER_HOTKEY, self.overlay.toggle_or_show)
            self.hotkey.start()

    def _on_hotkey_changed(self, spec: str) -> None:
        """Re-register the feeder hotkey in place, so a change needs no restart."""
        self.hotkey.stop()
        self.hotkey = GlobalHotkeyListener(spec, self.overlay.toggle_or_show)
        self.hotkey.start()
        self.feed_action.setText(f"🌱 随手投喂切片 ({hotkey_display(spec)})")
        self.controller.say(f"⌨️ 投喂快捷键已更新为 {hotkey_display(spec)}", ttl_ms=2500)

    def _setup_decay(self) -> None:
        """Prune expired transient evidence once at startup and then daily.

        Without this the events table grows without bound, and the retention
        contract in the Phase 2 spec would be nominal only.
        """
        self._run_prune()
        self.prune_timer = QTimer(self.window)
        self.prune_timer.setInterval(_PRUNE_INTERVAL_MS)
        self.prune_timer.timeout.connect(self._run_prune)
        self.prune_timer.start()

    def _run_prune(self) -> None:
        """Drop transient events past the retention TTL. Never touches durable rows."""
        try:
            self.chronicle.prune()
        except sqlite3.Error:
            # A locked database must not take the companion down; retry next interval.
            pass

    def _on_agent_event_received(self, event: AgentEvent) -> None:
        """Data Plane tap: record continuous activity and track busy/idle timing."""
        self.watcher.record_activity()
        if event.event_type in (AgentEventType.PRE_TOOL_USE, AgentEventType.USER_PROMPT):
            self._last_agent_active_at = datetime.now()

    def _is_task_in_flight(self, now: datetime | None = None) -> bool:
        """Timing Gate: true when an agent is actively executing tools or reasoning.

        Intervention nudges MUST stay silent during active high-cognitive tasks
        so user flow is never broken (DESIGN.md 2.3, Timing Gate).
        """
        if self._last_agent_active_at is None:
            return False
        current = now or datetime.now()
        elapsed = (current - self._last_agent_active_at).total_seconds()
        return elapsed < _IN_FLIGHT_COOLDOWN_SECONDS

    def _setup_state_care(self) -> None:
        """Low-frequency check for overwork and late-night health nudges."""
        self.care_timer = QTimer(self.window)
        self.care_timer.setInterval(_CARE_CHECK_INTERVAL_MS)
        self.care_timer.timeout.connect(self._check_state_care)
        self.care_timer.start()

    def _check_state_care(self) -> None:
        """Evaluate the 3 Gates; speak gently only when overworking or late night."""
        in_flight = self._is_task_in_flight()
        nudge = self.intervention.evaluate_intervention(is_task_in_flight=in_flight)
        if nudge:
            self.controller.perform_action("rest")
            self.controller.say(nudge, ttl_ms=4500)

    def _setup_tray(self, assets_dir: Path) -> None:
        """Create a Clawd-on-Desk inspired context menu and system tray."""
        self.tray = QSystemTrayIcon(self.window)
        idle_sheet = self.window._loaded_sheets.get("idle")
        if idle_sheet and idle_sheet.frames:
            self.tray.setIcon(QIcon(idle_sheet.frames[0]))
        else:
            icon_path = assets_dir / "sprites" / "idle.png"
            if icon_path.is_file():
                self.tray.setIcon(QIcon(str(icon_path)))
            else:
                self.tray.setIcon(QIcon())

        self.context_menu = self._build_context_menu()
        self.tray.setContextMenu(self.context_menu)
        self.tray.show()

        # Allow right-clicking pet body directly to pop up the context menu (Clawd on Desk feature)
        self.window.context_menu_requested.connect(self._popup_context_menu)

    def _build_context_menu(self) -> QMenu:
        """Construct clean context menu adhering to Clawd on Desk UI hierarchy."""
        menu = QMenu(self.window)
        menu.setStyleSheet(get_menu_stylesheet())

        # ── 1. State Group (Clawd on Desk: 极简模式 + 休眠/唤醒) ──
        is_sleeping = self.window._current_state == PetState.SLEEPING
        self.sleep_action = QAction("唤醒伴生体" if is_sleeping else "休眠（免打扰）", self.window)
        self.sleep_action.triggered.connect(self._toggle_sleep_wake)
        menu.addAction(self.sleep_action)

        menu.addSeparator()

        # ── 2. Work & Memory Group (Clawd on Desk: 随手切片 + 打开足迹) ──
        self.feed_action = QAction(
            f"随手投喂切片 ({hotkey_display(self.agent_settings.feeder_hotkey)})", self.window
        )
        self.feed_action.triggered.connect(self.overlay.toggle_or_show)
        menu.addAction(self.feed_action)

        archive_action = QAction("打开足迹", self.window)
        archive_action.triggered.connect(self._open_chronicle_archive)
        menu.addAction(archive_action)

        menu.addSeparator()

        # ── 3. Companion & Display Group ──
        switch_menu = menu.addMenu("切换伴生体")
        switch_menu.setStyleSheet(menu.styleSheet())
        available_pets = [
            ("Calico (默认 · 三花小猫)", "calico"),
            ("Tiko (小机器人)", "tiko"),
            ("Debug Duck (调试小黄鸭)", "debug-duck"),
            ("Wangcai (布偶猫)", "wangcai"),
            ("Claw (经典小猫)", "claw"),
        ]

        def _make_switcher(pid: str) -> Callable[[], None]:
            def _switch() -> None:
                self.agent_settings.set_selected_pet(pid)
                self._on_pet_changed(pid)

            return _switch

        for label, pid in available_pets:
            if (Path("assets") / "pets" / pid).is_dir():
                pet_action = QAction(label, self.window)
                pet_action.triggered.connect(_make_switcher(pid))
                switch_menu.addAction(pet_action)

        scale_menu = menu.addMenu("伴生体大小")
        scale_menu.setStyleSheet(menu.styleSheet())
        scale_presets = [
            ("50% 极小", 0.5),
            ("75% 小巧", 0.75),
            ("100% 标准", 1.0),
            ("125% 适中", 1.25),
            ("150% 醒目", 1.5),
        ]

        def _make_scale_changer(val: float) -> Callable[[], None]:
            def _change() -> None:
                self._on_scale_changed(val)

            return _change

        for s_label, s_val in scale_presets:
            s_action = QAction(s_label, self.window)
            s_action.triggered.connect(_make_scale_changer(s_val))
            scale_menu.addAction(s_action)

        reset_pos_act = QAction("将桌宠拉回主屏", self.window)
        reset_pos_act.triggered.connect(self.window.reset_to_default_position)
        menu.addAction(reset_pos_act)

        menu.addSeparator()

        # ── 4. App & Settings Group ──
        settings_action = QAction("设置…", self.window)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        self.vis_action = QAction("隐藏桌宠", self.window)
        self.vis_action.triggered.connect(self._toggle_pet_visibility)
        menu.addAction(self.vis_action)

        # Optional Developer Debug Menu (Only active when COMPANION_DEBUG=1)
        if os.environ.get("COMPANION_DEBUG") == "1":
            menu.addSeparator()
            sim_menu = menu.addMenu("开发者调试")
            sim_menu.setStyleSheet(menu.styleSheet())
            sim_prompt = QAction("1. 用户提问 (User Prompt → 思考)", self.window)
            sim_prompt.triggered.connect(
                lambda: (
                    self.hermes.on_user_prompt("demo_session"),
                    self.controller.say("🤔 思考中：正在分析你的问题...", ttl_ms=3000),
                )
            )
            sim_menu.addAction(sim_prompt)
            sim_tool = QAction("2. 调工具 (PreToolUse → 工作)", self.window)
            sim_tool.triggered.connect(
                lambda: (
                    self.hermes.on_pre_tool_call("demo_session", "bash"),
                    self.controller.say("⚙️ 正在执行工具: bash", ttl_ms=2500),
                )
            )
            sim_menu.addAction(sim_tool)
            sim_err = QAction("3. 工具报错 (ToolFailure → 报错)", self.window)
            sim_err.triggered.connect(
                lambda: (
                    self.hermes.on_tool_failure("demo_session", "bash", "SyntaxError"),
                    self.controller.say("⚠️ 工具报错: SyntaxError", ttl_ms=3000),
                )
            )
            sim_menu.addAction(sim_err)
            sim_done = QAction("4. 任务完成 (TaskComplete → 开心)", self.window)
            sim_done.triggered.connect(
                lambda: (
                    self.hermes.on_task_complete("demo_session"),
                    self.controller.say("🎉 任务完成！所有检查通过！", ttl_ms=3000),
                )
            )
            sim_menu.addAction(sim_done)
        menu.addSeparator()

        # ── 5. Quit Group ──
        quit_act = QAction("退出", self.window)
        quit_act.triggered.connect(self._on_quit)
        menu.addAction(quit_act)

        return menu

    def _toggle_sleep_wake(self) -> None:
        if self.window._current_state == PetState.SLEEPING:
            self.controller.set_state(PetState.IDLE)
            self.controller.say("我醒啦！", ttl_ms=2000)
        else:
            self.controller.set_state(PetState.SLEEPING)
            self.controller.say("晚安，有事随时叫我...", ttl_ms=2500)
        self._refresh_menu_labels()

    def _toggle_pet_visibility(self) -> None:
        """Toggle visibility of the companion pet."""
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.show()
            self.window.raise_()
        self._refresh_menu_labels()

    def _refresh_menu_labels(self) -> None:
        """Keep dynamic menu labels in sync with real window/state."""
        if hasattr(self, "sleep_action"):
            is_sleeping = self.window._current_state == PetState.SLEEPING
            self.sleep_action.setText("唤醒伴生体" if is_sleeping else "休眠（免打扰）")
        if hasattr(self, "vis_action"):
            self.vis_action.setText("显示桌宠" if self.window.isHidden() else "隐藏桌宠")

    def _popup_context_menu(self, pos: QPoint) -> None:
        """Pop up the context menu at global coordinate."""
        self._refresh_menu_labels()
        self.context_menu.popup(pos)

    def _on_pet_clicked(self) -> None:
        """Left clicking the pet shows a small status acknowledgment."""
        if self.guard.is_active:
            self.controller.say("（安静地陪着你）", ttl_ms=2500)
        else:
            display = hotkey_display(self.agent_settings.feeder_hotkey)
            self.controller.say(f"我在呢。按 {display} 可以随手喂我想法~", ttl_ms=3000)

    def _on_slice_submitted(self, text: str) -> None:
        """Handle incoming slice from overlay."""
        is_distressed = self.guard.evaluate_text(text)
        mood = "frustrated" if is_distressed else "neutral"

        # 1. Save to disk
        slice_item = RawSlice.create(text, mood_flag=mood)
        self.store.save(slice_item)
        self.chronicle.record_slice(
            SliceRecord(
                id=slice_item.id,
                timestamp=slice_item.timestamp,
                content=slice_item.content,
                mood_flag=slice_item.mood_flag,
            )
        )

        # 2. Check Sanctuary mode
        if is_distressed:
            # AC-4: Enter Sanctuary mode with a gentle, non-preaching acknowledgment bubble
            self.controller.perform_action("rest")
            self.controller.say("🍃 收到。先放一放，我陪着你...", ttl_ms=3500)
        else:
            # AC-3: Acknowledge normal slice with gentle confirmation
            self.controller.perform_action("jump")
            self.controller.say("✨ 记下了，存进档案库了", ttl_ms=2500)

    def _open_settings(self) -> None:
        """Open the modern multi-agent and companion settings window."""
        self.settings_window.refresh_agents()
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _open_chronicle_archive(self) -> None:
        """Open the read-only memory and slice archive window."""
        self.chronicle_window.refresh_all()
        self.chronicle_window.show()
        self.chronicle_window.raise_()
        self.chronicle_window.activateWindow()

    def _on_pet_changed(self, pet_id: str) -> None:
        """Handle dynamic pet switching from Settings or Tray."""
        pet_dir = Path("assets") / "pets" / pet_id
        if pet_dir.is_dir():
            self.window.load_pet(pet_dir)
            cur_idle = self.window._loaded_sheets.get("idle")
            if cur_idle and cur_idle.frames:
                self.tray.setIcon(QIcon(cur_idle.frames[0]))
            names = {
                "calico": "Calico (三花小猫)",
                "tiko": "Tiko (小机器人)",
                "debug-duck": "Debug Duck (小黄鸭)",
                "wangcai": "Wangcai (布偶猫)",
                "claw": "Claw",
            }
            display_name = names.get(pet_id, pet_id)
            self.controller.say(f"伴生体已切换为 {display_name}")

    def _on_quit(self) -> None:
        try:
            self.hotkey.stop()
        except Exception:
            pass
        try:
            self.http_server.stop()
        except Exception:
            pass
        self.chronicle_window.close()
        self.window.close()
        self.app.quit()

    def _on_scale_changed(self, scale: float) -> None:
        """Handle pet scale adjustments from Settings or Tray."""
        self.window.set_scale(scale)
        percent = int(round(scale * 100))
        self.controller.say(f"🔍 伴生体大小已调整为 {percent}%", ttl_ms=1800)

    def run(self) -> int:
        self.window.show()
        return self.app.exec()


def main() -> int:
    companion = CompanionApp()
    return companion.run()


if __name__ == "__main__":
    sys.exit(main())
