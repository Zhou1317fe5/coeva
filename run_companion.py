"""Main interactive runner for Co-evolving AI Companion (Phase 1)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.body.contracts import PetState
from src.body.controller import BodyController
from src.body.window import PetWindow
from src.connectors.event_bus import LocalEventBus
from src.connectors.hermes_connector import HermesConnector
from src.core.cold_start import ColdStartPolicy
from src.core.intervention import InterventionPolicy
from src.core.sanctuary import SanctuaryGuard
from src.core.state_watcher import StateWatcher
from src.feeder.contracts import RawSlice
from src.feeder.hotkey import GlobalHotkeyListener
from src.feeder.overlay import SliceFeederOverlay
from src.feeder.storage import SliceStore


class CompanionApp:
    """Orchestrates Desktop Pet Body, Slice Feeder, and Growth Core in one process."""

    def __init__(self) -> None:
        existing_app = QApplication.instance()
        if isinstance(existing_app, QApplication):
            self.app = existing_app
        else:
            self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 1. Desktop Body
        assets_dir = Path("assets") / "pets" / "claw"
        if not assets_dir.is_dir():
            assets_dir = Path("assets") / "pets" / "dachshund"

        self.window = PetWindow(assets_dir, scale=2)
        self.controller = BodyController(self.window)

        # 2. Slice Feeder & Store
        self.store = SliceStore(Path("data") / "raw_slices.jsonl")
        self.overlay = SliceFeederOverlay()
        self.overlay.slice_submitted.connect(self._on_slice_submitted)

        # 3. Growth Core & Sanctuary
        self.guard = SanctuaryGuard()
        self.cold_start = ColdStartPolicy(day_count=1)
        self.watcher = StateWatcher(overwork_threshold_hours=3.0)
        self.intervention = InterventionPolicy(
            sanctuary=self.guard,
            cold_start=self.cold_start,
            watcher=self.watcher,
        )

        # 4. Connectors & Event Bus
        self.bus = LocalEventBus(
            on_event_received=lambda e: self.watcher.record_activity(),
            on_state_suggested=lambda s: self.controller.set_state(s),
        )
        self.hermes = HermesConnector(self.bus)

        # Pet click interaction
        self.window.clicked.connect(self._on_pet_clicked)

        # Setup System Tray & Hotkey
        self._setup_tray(assets_dir)
        self._setup_hotkey()

    def _setup_hotkey(self) -> None:
        """Register global hotkey <alt>+<space> to summon the slice feeder."""
        try:
            self.hotkey = GlobalHotkeyListener("<alt>+<space>", self.overlay.toggle_or_show)
            self.hotkey.start()
        except Exception:
            pass

    def _setup_tray(self, assets_dir: Path) -> None:
        """Create a full-featured tray menu for manual inspection and testing."""
        self.tray = QSystemTrayIcon(self.window)
        icon_path = assets_dir / "sprites" / "idle.png"
        if icon_path.is_file():
            self.tray.setIcon(QIcon(str(icon_path)))
        else:
            self.tray.setIcon(QIcon())

        menu = QMenu()

        # 1. Feeder trigger
        feed_action = QAction("🌱 随手投喂切片 (Alt+Space)", self.window)
        feed_action.triggered.connect(self.overlay.toggle_or_show)
        menu.addAction(feed_action)

        menu.addSeparator()

        # 2. Agent state simulation tests with clear visual bubble feedback
        sim_menu = menu.addMenu("⚡ 测试: 模拟 Hermes Agent 事件")

        def _sim_prompt() -> None:
            self.hermes.on_user_prompt("demo_session")
            self.controller.say("🤔 思考中：正在分析你的问题...", ttl_ms=3000)

        prompt_act = QAction("1. 用户提问 (User Prompt → 思考)", self.window)
        prompt_act.triggered.connect(_sim_prompt)
        sim_menu.addAction(prompt_act)

        def _sim_tool() -> None:
            self.hermes.on_pre_tool_call("demo_session", "bash")
            self.controller.say("⚙️ 正在执行工具: bash", ttl_ms=2500)

        tool_act = QAction("2. 调工具 (PreToolUse → 工作)", self.window)
        tool_act.triggered.connect(_sim_tool)
        sim_menu.addAction(tool_act)

        def _sim_error() -> None:
            self.hermes.on_tool_failure("demo_session", "bash", "SyntaxError")
            self.controller.say("⚠️ 工具报错: SyntaxError", ttl_ms=3000)

        err_act = QAction("3. 工具报错 (ToolFailure → 报错)", self.window)
        err_act.triggered.connect(_sim_error)
        sim_menu.addAction(err_act)

        def _sim_done() -> None:
            self.hermes.on_task_complete("demo_session")
            self.controller.say("🎉 任务完成！所有检查通过！", ttl_ms=3000)

        done_act = QAction("4. 任务完成 (TaskComplete → 开心)", self.window)
        done_act.triggered.connect(_sim_done)
        sim_menu.addAction(done_act)

        menu.addSeparator()

        # 3. Direct state controls & Position Recovery
        idle_act = QAction("💤 恢复待机 (Idle)", self.window)
        idle_act.triggered.connect(lambda: self.controller.set_state(PetState.IDLE))
        menu.addAction(idle_act)

        sleep_act = QAction("🌙 哄它睡觉 (Sleep)", self.window)
        sleep_act.triggered.connect(lambda: self.controller.set_state(PetState.SLEEPING))
        menu.addAction(sleep_act)

        bubble_act = QAction("💬 测试气泡 (Say)", self.window)
        bubble_act.triggered.connect(lambda: self.controller.say("今天也是并肩作战的一天！"))
        menu.addAction(bubble_act)

        reset_pos_act = QAction("📍 唤回伴生体 (居中重置)", self.window)
        reset_pos_act.triggered.connect(self.window.reset_to_default_position)
        menu.addAction(reset_pos_act)

        menu.addSeparator()

        # 4. Quit
        quit_act = QAction("🚪 退出伴生体", self.window)
        quit_act.triggered.connect(self._on_quit)
        menu.addAction(quit_act)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _on_pet_clicked(self) -> None:
        """Left clicking the pet shows a small status acknowledgment."""
        if self.guard.is_active:
            self.controller.say("（安静地陪着你）", ttl_ms=2500)
        else:
            self.controller.say("我在呢。按 Alt+Space 可以随手喂我想法~", ttl_ms=3000)

    def _on_slice_submitted(self, text: str) -> None:
        """Handle incoming slice from overlay."""
        is_distressed = self.guard.evaluate_text(text)
        mood = "frustrated" if is_distressed else "neutral"

        # 1. Save to disk
        slice_item = RawSlice.create(text, mood_flag=mood)
        self.store.save(slice_item)

        # 2. Check Sanctuary mode
        if is_distressed:
            # AC-4: Enter Sanctuary mode with a gentle, non-preaching acknowledgment bubble
            self.controller.perform_action("rest")
            self.controller.say("🍃 收到。先放一放，我陪着你...", ttl_ms=3500)
        else:
            # AC-3: Acknowledge normal slice with gentle confirmation
            self.controller.perform_action("jump")
            self.controller.say("✨ 记下了，存进档案库了", ttl_ms=2500)

    def _on_quit(self) -> None:
        try:
            self.hotkey.stop()
        except Exception:
            pass
        self.window.close()
        self.app.quit()

    def run(self) -> int:
        self.window.show()
        return self.app.exec()


def main() -> int:
    companion = CompanionApp()
    return companion.run()


if __name__ == "__main__":
    sys.exit(main())
