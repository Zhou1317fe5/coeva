"""Standalone desktop entrypoint for the Desktop Pet Body."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.body.chronicle_window import ChronicleViewerWindow
from src.body.contracts import PetState
from src.body.controller import BodyController
from src.body.menu_style import get_menu_stylesheet
from src.body.settings_window import SettingsWindow
from src.body.window import PetWindow
from src.connectors.hook_manager import AgentHookManager
from src.connectors.settings import AgentSettingsStore
from src.feeder.hotkey import GlobalHotkeyListener
from src.memory.store import ChronicleStore


def main() -> int:
    existing_app = QApplication.instance()
    if isinstance(existing_app, QApplication):
        app = existing_app
    else:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Default pet is Vasu, with fallback to calico, claw
    preferred_pets = ["vasu", "calico", "claw"]
    assets_root: Path | None = None
    for pet_name in preferred_pets:
        cand = Path("assets") / "pets" / pet_name
        if cand.is_dir():
            assets_root = cand
            break

    if assets_root is None:
        assets_root = Path("assets") / "pets" / "vasu"

    settings_store = AgentSettingsStore()
    chronicle_store = ChronicleStore()
    hook_manager = AgentHookManager()

    window = PetWindow(assets_root)
    controller = BodyController(window)

    # Global hotkey for feeder input
    hotkey_spec = settings_store.feeder_hotkey
    hotkey_listener: GlobalHotkeyListener | None = None
    try:
        hotkey_listener = GlobalHotkeyListener(hotkey_spec, window.open_feeder_input)
        hotkey_listener.start()
    except Exception:
        hotkey_listener = None
    # System Tray
    tray = QSystemTrayIcon(window)
    idle_sheet = window._loaded_sheets.get("idle")
    if idle_sheet and idle_sheet.frames:
        tray.setIcon(QIcon(idle_sheet.frames[0]))
    else:
        icon_path = assets_root / "sprites" / "idle.png"
        if icon_path.is_file():
            tray.setIcon(QIcon(str(icon_path)))
        else:
            tray.setIcon(QIcon())
    tray_menu = QMenu(window)
    tray_menu.setStyleSheet(get_menu_stylesheet())


    # State Group
    sleep_action = QAction("休眠（免打扰）", window)

    def _toggle_sleep() -> None:
        if window._current_state == PetState.SLEEPING:
            controller.set_state(PetState.IDLE)
            controller.say("我醒啦！", ttl_ms=2000)
            sleep_action.setText("休眠（免打扰）")
        else:
            controller.set_state(PetState.SLEEPING)
            controller.say("晚安，有事随时叫我...", ttl_ms=2500)
            sleep_action.setText("唤醒伴生体")

    sleep_action.triggered.connect(_toggle_sleep)
    tray_menu.addAction(sleep_action)

    tray_menu.addSeparator()

    # Switch pet submenu
    switch_menu = tray_menu.addMenu("切换伴生体")
    switch_menu.setStyleSheet(tray_menu.styleSheet())
    available_pets = [
        ("🦦 Vasu (默认 · 小河獭)", Path("assets") / "pets" / "vasu"),
        ("🐱 Calico (三花小猫)", Path("assets") / "pets" / "calico"),
        ("🐾 Claw (经典小猫)", Path("assets") / "pets" / "claw"),
    ]

    def _make_switcher(target_dir: Path, label: str) -> Callable[[], None]:
        def _switch() -> None:
            if target_dir.is_dir():
                window.load_pet(target_dir)
                cur_idle = window._loaded_sheets.get("idle")
                if cur_idle and cur_idle.frames:
                    tray.setIcon(QIcon(cur_idle.frames[0]))
                clean_name = label.split()[1] if len(label.split()) > 1 else label
                controller.say(f"已切换为 {clean_name}")

        return _switch

    for label, pet_path in available_pets:
        if pet_path.is_dir():
            pet_action = QAction(label, window)
            pet_action.triggered.connect(_make_switcher(pet_path, label))
            switch_menu.addAction(pet_action)

    reset_pos_act = QAction("将桌宠拉回主屏", window)
    reset_pos_act.triggered.connect(window.reset_to_default_position)
    tray_menu.addAction(reset_pos_act)
    tray_menu.addSeparator()

    # Windows & Dialogs
    settings_dialog: SettingsWindow | None = None
    chronicle_dialog: ChronicleViewerWindow | None = None

    def _open_settings() -> None:
        nonlocal settings_dialog
        if settings_dialog is None:
            settings_dialog = SettingsWindow(settings_store, hook_manager)
            settings_dialog.hotkey_changed.connect(_on_hotkey_changed)
        settings_dialog.show()
        settings_dialog.raise_()
        settings_dialog.activateWindow()

    def _open_chronicle() -> None:
        nonlocal chronicle_dialog
        if chronicle_dialog is None:
            chronicle_dialog = ChronicleViewerWindow(chronicle_store)
        chronicle_dialog.show()
        chronicle_dialog.raise_()
        chronicle_dialog.activateWindow()

    def _on_hotkey_changed(new_spec: str) -> None:
        nonlocal hotkey_listener
        if hotkey_listener is not None:
            hotkey_listener.stop()
        try:
            hotkey_listener = GlobalHotkeyListener(new_spec, window.open_feeder_input)
            hotkey_listener.start()
        except Exception:
            hotkey_listener = None

    settings_act = QAction("⚙️ 偏好设置...", window)
    settings_act.triggered.connect(_open_settings)
    tray_menu.addAction(settings_act)

    chronicle_act = QAction("📖 成长生命档案...", window)
    chronicle_act.triggered.connect(_open_chronicle)
    tray_menu.addAction(chronicle_act)

    tray_menu.addSeparator()

    # Pet Visibility toggle
    vis_action = QAction("隐藏桌宠", window)

    def _toggle_visibility() -> None:
        if window.isVisible():
            window.hide()
            vis_action.setText("显示桌宠")
        else:
            window.show()
            window.raise_()
            vis_action.setText("隐藏桌宠")
    vis_action.triggered.connect(_toggle_visibility)
    tray_menu.addAction(vis_action)

    tray_menu.addSeparator()

    def _on_quit() -> None:
        if hotkey_listener is not None:
            hotkey_listener.stop()
        window.close()
        app.quit()

    quit_action = QAction("退出", window)
    quit_action.triggered.connect(_on_quit)
    tray_menu.addAction(quit_action)

    tray.setContextMenu(tray_menu)
    tray.show()

    # Pop up context menu when clicking pet body
    window.context_menu_requested.connect(lambda pos: tray_menu.popup(pos))

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
