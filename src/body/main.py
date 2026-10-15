"""Standalone desktop entrypoint for the Desktop Pet Body."""

from __future__ import annotations

import sys
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

    assets_root = Path("assets") / "pets" / "claw"
    if not assets_root.is_dir():
        # Fallback to local default if claw is not found
        assets_root = Path("assets") / "pets" / "dachshund"

    window = PetWindow(assets_root, scale=2)
    controller = BodyController(window)

    # System Tray
    tray = QSystemTrayIcon(window)
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

    quit_action = QAction("退出伴生体 (Quit)", window)
    quit_action.triggered.connect(app.quit)
    tray_menu.addAction(quit_action)

    tray.setContextMenu(tray_menu)
    tray.show()

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
