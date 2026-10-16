"""Standalone desktop entrypoint for the Desktop Pet Body."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.body.controller import BodyController
from src.body.window import PetWindow


def main() -> int:
    existing_app = QApplication.instance()
    if isinstance(existing_app, QApplication):
        app = existing_app
    else:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Default pet is Tiko, with fallback to debug-duck, wangcai, or claw
    preferred_pets = ["tiko", "debug-duck", "wangcai", "claw"]
    assets_root: Path | None = None
    for pet_name in preferred_pets:
        cand = Path("assets") / "pets" / pet_name
        if cand.is_dir():
            assets_root = cand
            break

    if assets_root is None:
        assets_root = Path("assets") / "pets" / "tiko"

    window = PetWindow(assets_root, scale=1)
    controller = BodyController(window)

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
    tray_menu = QMenu()

    # Quick state changes
    idle_action = QAction("💤 待机 (Idle)", window)
    idle_action.triggered.connect(lambda: controller.perform_action("rest"))
    tray_menu.addAction(idle_action)

    work_action = QAction("💻 工作 (Working)", window)
    work_action.triggered.connect(lambda: controller.perform_action("work"))
    tray_menu.addAction(work_action)

    sleep_action = QAction("🌙 睡觉 (Sleep)", window)
    sleep_action.triggered.connect(lambda: controller.perform_action("sleep"))
    tray_menu.addAction(sleep_action)

    tray_menu.addSeparator()

    # Say hello demo
    say_action = QAction("💬 打招呼 (Say)", window)
    say_action.triggered.connect(lambda: controller.say("你好！我在桌角陪你。"))
    tray_menu.addAction(say_action)

    tray_menu.addSeparator()

    # Switch pet submenu
    switch_menu = tray_menu.addMenu("🔄 切换伴生体 (Switch Pet)")
    available_pets = [
        ("🤖 Tiko (默认 · 小机器人)", Path("assets") / "pets" / "tiko"),
        ("🐥 Debug Duck (调试小黄鸭)", Path("assets") / "pets" / "debug-duck"),
        ("🐱 Wangcai (布偶猫)", Path("assets") / "pets" / "wangcai"),
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

    quit_action = QAction("退出伴生体 (Quit)", window)
    quit_action.triggered.connect(app.quit)
    tray_menu.addAction(quit_action)

    tray.setContextMenu(tray_menu)
    tray.show()

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
