"""Modern multi-agent and companion settings window inspired by Clawd on Desk."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.connectors.hook_manager import AgentHookManager

if TYPE_CHECKING:
    from src.connectors.settings import AgentSettingsStore


class SettingsWindow(QWidget):
    """Full-featured preferences and multi-agent management dialog."""
    pet_changed = Signal(str)
    scale_changed = Signal(float)


    def __init__(
        self,
        settings_store: AgentSettingsStore,
        hook_manager: AgentHookManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = settings_store
        self.hook_manager = hook_manager or AgentHookManager()
        self.setWindowTitle("桌面伴生体设置 (Companion Settings)")
        self.resize(720, 520)
        self.setMinimumSize(640, 460)

        # Apply dark modern design styling
        self._apply_styling()

        # Main layout: Left sidebar navigation + Right content stack
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Navigation Sidebar
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(180)
        self.nav_list.setObjectName("navSidebar")

        items = [
            ("🤖  多 Agent 接入", "agents"),
            ("🐾  桌面身体偏好", "body"),
            ("🍃  心智与避风港", "core"),
            ("ℹ️  关于与规范", "about"),
        ]
        for title, key in items:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav_list.addItem(item)

        self.nav_list.currentRowChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.nav_list)

        # 2. Right Stacked Area
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")

        # Page 1: Multi-Agent Telemetry
        self.agents_page = self._build_agents_page()
        self.stack.addWidget(self.agents_page)

        # Page 2: Body Preferences
        self.body_page = self._build_body_page()
        self.stack.addWidget(self.body_page)

        # Page 3: Mind & Sanctuary
        self.core_page = self._build_core_page()
        self.stack.addWidget(self.core_page)

        # Page 4: About
        self.about_page = self._build_about_page()
        self.stack.addWidget(self.about_page)

        main_layout.addWidget(self.stack, 1)

        self.nav_list.setCurrentRow(0)

    def _apply_styling(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e20;
                color: #e5e7eb;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
            }
            QListWidget#navSidebar {
                background-color: #161618;
                border: none;
                border-right: 1px solid #2e2e32;
                padding-top: 12px;
            }
            QListWidget#navSidebar::item {
                height: 38px;
                padding-left: 16px;
                margin: 2px 8px;
                border-radius: 6px;
                color: #9ca3af;
                font-weight: 500;
            }
            QListWidget#navSidebar::item:selected {
                background-color: #2a2a2e;
                color: #ffffff;
            }
            QListWidget#navSidebar::item:hover:!selected {
                background-color: #222226;
                color: #d1d5db;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            .cardFrame {
                background-color: #242428;
                border: 1px solid #323238;
                border-radius: 8px;
                padding: 14px;
            }
            .cardTitle {
                font-size: 15px;
                font-weight: 600;
                color: #f3f4f6;
            }
            .cardDesc {
                color: #9ca3af;
                font-size: 12px;
                margin-top: 2px;
            }
            QCheckBox {
                color: #e5e7eb;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #4b5563;
                background-color: #1f2937;
            }
            QCheckBox::indicator:checked {
                background-color: #10b981;
                border-color: #10b981;
            }
            QPushButton {
                background-color: #2a2a2e;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 12px;
                color: #f3f4f6;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #38383e;
            }
        """)

    def _on_tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.refresh_agents()

    # ── Page 1: Multi-Agent Management (Like Clawd on Desk) ──
    def _build_agents_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header = QLabel("多 Agent 遥测与接入控制")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        header.setFont(title_font)
        header_row.addWidget(header)
        header_row.addStretch()

        wsl_btn = QPushButton("🐧 扫描 WSL 并一键接入")
        wsl_btn.setToolTip("自动检测 WSL 并在 Linux 家目录下一键挂载伴生体 Hook")
        wsl_btn.clicked.connect(self._scan_and_deploy_all_wsl)
        header_row.addWidget(wsl_btn)
        layout.addLayout(header_row)

        desc = QLabel(
            "自动发现本机与 WSL 中的 AI 终端。支持一键安装 Hook 传感器，实现无感遥测。"
        )
        desc.setStyleSheet("color: #9ca3af; font-size: 12px; margin-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.cards_container = QVBoxLayout()
        self.cards_container.setSpacing(12)
        layout.addLayout(self.cards_container)

        layout.addStretch()

        self.refresh_agents()
        scroll.setWidget(container)
        return scroll
    def refresh_agents(self) -> None:
        """Re-render agent cards based on current settings store."""
        while self.cards_container.count():
            item = self.cards_container.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        for cfg in self.store.get_all():
            card = self._create_agent_card(cfg.agent_id)
            self.cards_container.addWidget(card)

    def _create_agent_card(self, agent_id: str) -> QWidget:
        cfg = self.store.get(agent_id)
        if cfg is None:
            return QWidget()

        card = QFrame()
        card.setProperty("class", "cardFrame")

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        # Header row: Name + Status Badge + Enable Toggle
        top_row = QHBoxLayout()

        name_label = QLabel(cfg.name)
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setBold(True)
        name_label.setFont(name_font)
        top_row.addWidget(name_label)

        # Status badge (Online / Idle / Disconnected)
        if cfg.last_seen:
            badge = QLabel("🟢 已接入 (Active)")
            badge.setStyleSheet("color: #10b981; font-weight: 500; font-size: 11px;")
        else:
            badge = QLabel("⚪ 未连接 (Idle)")
            badge.setStyleSheet("color: #6b7280; font-weight: 500; font-size: 11px;")
        top_row.addWidget(badge)
        top_row.addStretch()

        enable_cb = QCheckBox("启用接入")
        enable_cb.setChecked(cfg.enabled)
        enable_cb.toggled.connect(
            lambda checked, aid=agent_id: self.store.update_agent(aid, enabled=checked)
        )
        top_row.addWidget(enable_cb)

        card_layout.addLayout(top_row)

        # Description
        desc_label = QLabel(cfg.description or f"Agent 标识: {agent_id}")
        desc_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        card_layout.addWidget(desc_label)

        # Fine-grained controls
        sub_controls = QHBoxLayout()
        sub_controls.setSpacing(16)

        bubble_cb = QCheckBox("展示说话气泡")
        bubble_cb.setChecked(cfg.allow_bubble)
        bubble_cb.toggled.connect(
            lambda checked, aid=agent_id: self.store.update_agent(aid, allow_bubble=checked)
        )
        sub_controls.addWidget(bubble_cb)

        action_cb = QCheckBox("触发动作动效")
        action_cb.setChecked(cfg.allow_action)
        action_cb.toggled.connect(
            lambda checked, aid=agent_id: self.store.update_agent(aid, allow_action=checked)
        )
        sub_controls.addWidget(action_cb)
        sub_controls.addStretch()
        card_layout.addLayout(sub_controls)

        # Environment instances rows (Clawd style Windows vs WSL)
        if cfg.instances:
            inst_box = QFrame()
            inst_box.setStyleSheet(
                "background-color: #1a1a1c; border-radius: 6px; padding: 6px 10px; margin-top: 4px;"
            )
            inst_layout = QVBoxLayout(inst_box)
            inst_layout.setContentsMargins(4, 4, 4, 4)
            inst_layout.setSpacing(6)

            inst_header = QLabel("运行环境实例 (Environment Instances)")
            inst_header.setStyleSheet("color: #6b7280; font-size: 11px; font-weight: 600;")
            inst_layout.addWidget(inst_header)

            for iid, inst in cfg.instances.items():
                row = QHBoxLayout()
                row.setSpacing(8)

                icon_str = "🐧" if "wsl" in iid.lower() else "🖥️"
                lbl = QLabel(f"{icon_str}  {inst.label}")
                lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
                row.addWidget(lbl)
                h_info = self.hook_manager.check_hook_status(agent_id, iid)
                is_installed = h_info.get("installed", False)

                if is_installed:
                    hbadge = QLabel("HOOK 就绪")
                    hbadge.setStyleSheet(
                        "background-color: #064e3b; color: #34d399; "
                        "padding: 1px 6px; border-radius: 4px; font-size: 10px;"
                    )
                else:
                    hbadge = QLabel("HOOK 未安装")
                    hbadge.setStyleSheet(
                        "background-color: #451a03; color: #f59e0b; "
                        "padding: 1px 6px; border-radius: 4px; font-size: 10px;"
                    )
                row.addWidget(hbadge)

                if inst.last_seen:
                    ibadge = QLabel("🟢 活跃")
                    ibadge.setStyleSheet("color: #10b981; font-size: 10px;")
                else:
                    ibadge = QLabel("⚪ 未活动")
                    ibadge.setStyleSheet("color: #6b7280; font-size: 10px;")
                row.addWidget(ibadge)

                row.addStretch()

                if is_installed:
                    un_btn = QPushButton("卸载")
                    un_btn.setStyleSheet(
                        "padding: 2px 8px; font-size: 11px; background-color: #27272a;"
                    )
                    un_btn.clicked.connect(
                        lambda _, aid=agent_id, inst_id=iid: self._uninstall_hook_and_refresh(
                            aid, inst_id
                        )
                    )
                    row.addWidget(un_btn)
                else:
                    in_btn = QPushButton("一键接入")
                    in_btn.setStyleSheet(
                        "padding: 2px 8px; font-size: 11px; "
                        "background-color: #059669; color: white;"
                    )
                    in_btn.clicked.connect(
                        lambda _, aid=agent_id, inst_id=iid: self._install_hook_and_refresh(
                            aid, inst_id
                        )
                    )
                    row.addWidget(in_btn)

                ichk = QCheckBox("启用")
                ichk.setChecked(inst.enabled)
                ichk.toggled.connect(
                    lambda checked, aid=agent_id, inst_id=iid: self.store.update_instance(
                        aid, inst_id, enabled=checked
                    )
                )
                row.addWidget(ichk)
                inst_layout.addLayout(row)

            card_layout.addWidget(inst_box)
        return card

    def _install_hook_and_refresh(self, agent_id: str, instance_id: str) -> None:
        self.hook_manager.install_hook(agent_id, instance_id)
        self.store.update_instance(agent_id, instance_id, enabled=True)
        self.refresh_agents()

    def _uninstall_hook_and_refresh(self, agent_id: str, instance_id: str) -> None:
        self.hook_manager.uninstall_hook(agent_id, instance_id)
        self.refresh_agents()

    def _scan_and_deploy_all_wsl(self) -> None:
        distros = self.hook_manager.get_wsl_distros()
        for distro in distros:
            iid = f"wsl:{distro}"
            self.hook_manager.install_hook("hermes", iid)
            self.store.update_instance("hermes", iid, enabled=True)
            self.hook_manager.install_hook("pi-cli", iid)
            self.store.update_instance("pi-cli", iid, enabled=True)
        self.refresh_agents()

    # ── Page 2: Desktop Body Preferences ──
    def _build_body_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("桌面伴生体偏好设置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        header.setFont(title_font)
        layout.addWidget(header)
        # 0. Pet Appearance Selection
        pet_card = QFrame()
        pet_card.setProperty("class", "cardFrame")
        pet_layout = QVBoxLayout(pet_card)
        pet_layout.setSpacing(10)

        pet_title = QLabel("🐾 伴生体形象与外观 (Companion Pet)")
        pet_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        pet_desc = QLabel(
            "选择桌面常驻的桌宠形象。"
            "原生支持 Petdex / SpriteYard 标准精灵图规范，即选即换并自动保存。"
        )
        pet_desc.setWordWrap(True)
        pet_layout.addWidget(pet_title)
        pet_layout.addWidget(pet_desc)

        pet_options = [
            (
                "tiko",
                "🤖 Tiko (默认 · 好奇单眼工具机器人)",
                "来自 Petdex。自带单眼摄像头与履带，工坊并肩作战伙伴，80% 极简陪伴。",
            ),
            (
                "debug-duck",
                "🐥 Debug Duck (调试小黄鸭)",
                "来自 SpriteYard。经典小黄鸭调试法概念，质朴倾听排查思考。",
            ),
            (
                "wangcai",
                "🐱 Wangcai (温和布偶猫)",
                "来自 Petdex。蓝眼睛温和长毛猫，桌角安静蜷坐，陪伴感强。",
            ),
            (
                "claw",
                "🐾 Claw (复古经典猫咪)",
                "初版轻量 2D 像素猫咪形象。",
            ),
        ]

        current_pet = self.store.selected_pet
        self.pet_button_group = QButtonGroup(self)

        for pet_id, title_text, desc_text in pet_options:
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 4, 4, 4)
            row_layout.setSpacing(2)

            radio = QRadioButton(title_text)
            radio.setStyleSheet("font-weight: 500; font-size: 13px; color: #f3f4f6;")
            if pet_id == current_pet:
                radio.setChecked(True)

            def _make_handler(pid: str) -> Callable[[bool], None]:
                def _handler(checked: bool) -> None:
                    if checked:
                        self.store.set_selected_pet(pid)
                        self.pet_changed.emit(pid)
                return _handler

            radio.toggled.connect(_make_handler(pet_id))
            self.pet_button_group.addButton(radio)

            detail = QLabel(desc_text)
            detail.setStyleSheet("color: #9ca3af; font-size: 11px; margin-left: 20px;")
            detail.setWordWrap(True)

            row_layout.addWidget(radio)
            row_layout.addWidget(detail)
            pet_layout.addWidget(row_widget)

        layout.addWidget(pet_card)

        # 0.5 Scale Adjustment
        scale_card = QFrame()
        scale_card.setProperty("class", "cardFrame")
        scale_layout = QVBoxLayout(scale_card)
        scale_layout.setSpacing(10)

        scale_title = QLabel("🔍 伴生体缩放与尺寸调节 (Pet Scale)")
        scale_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        scale_desc = QLabel(
            "自由调节桌宠在桌面的显示大小。"
            "（提示：在桌面上直接按住 Ctrl + 鼠标滚轮 亦可实时快捷无级缩放）"
        )
        scale_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        scale_desc.setWordWrap(True)
        scale_layout.addWidget(scale_title)
        scale_layout.addWidget(scale_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        scale_presets = [
            ("50% (极小)", 0.5),
            ("75% (小巧)", 0.75),
            ("100% (标准)", 1.0),
            ("125% (适中)", 1.25),
            ("150% (醒目)", 1.5),
        ]

        def _make_scale_handler(val: float) -> Callable[[], None]:
            def _h() -> None:
                self.scale_changed.emit(val)
            return _h

        for label, s_val in scale_presets:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.clicked.connect(_make_scale_handler(s_val))
            btn_row.addWidget(btn)

        scale_layout.addLayout(btn_row)
        layout.addWidget(scale_card)

        # 1. Peek Docking
        peek_card = QFrame()
        peek_card.setProperty("class", "cardFrame")
        peek_layout = QVBoxLayout(peek_card)
        peek_title = QLabel("🧭 贴边探头与半身收纳 (Peek Mode)")
        peek_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        peek_desc = QLabel(
            "当桌宠拖拽至屏幕左右边缘（≤ 30px）时，"
            "会自动贴墙收纳仅露出 24px 半身，极大保护屏幕工作空间。\n"
            "鼠标悬停探头展开，鼠标离开 800ms 自动静默缩回。"
        )
        peek_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        peek_desc.setWordWrap(True)
        peek_layout.addWidget(peek_title)
        peek_layout.addWidget(peek_desc)
        layout.addWidget(peek_card)

        # 2. Slice Feeding Shortcut
        feed_card = QFrame()
        feed_card.setProperty("class", "cardFrame")
        feed_layout = QVBoxLayout(feed_card)
        feed_title = QLabel("🌱 随手投喂切片 (Slice Feeder)")
        feed_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        feed_desc = QLabel(
            "默认快捷键：Alt + Space。在任何软件或网页下即可随时唤起半透明磨砂输入弹窗，"
            "输入回车瞬时存盘，失焦秒隐。"
        )
        feed_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        feed_desc.setWordWrap(True)
        feed_layout.addWidget(feed_title)
        feed_layout.addWidget(feed_desc)
        layout.addWidget(feed_card)

        layout.addStretch()
        return container

    # ── Page 3: Growth Core & Sanctuary ──
    def _build_core_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("长盛心智与避风港哲学")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        header.setFont(title_font)
        layout.addWidget(header)

        # Sanctuary Card
        sanc_card = QFrame()
        sanc_card.setProperty("class", "cardFrame")
        sanc_layout = QVBoxLayout(sanc_card)
        sanc_title = QLabel("🍃 情绪避风港守卫 (Sanctuary Guard)")
        sanc_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        sanc_desc = QLabel(
            "当识别到剧烈挫败、崩溃或疲惫时，系统自动熔断 100% 的分析说教逻辑，"
            "转为温和静默陪伴。伴生体严禁扮演说教者。"
        )
        sanc_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        sanc_desc.setWordWrap(True)
        sanc_layout.addWidget(sanc_title)
        sanc_layout.addWidget(sanc_desc)
        layout.addWidget(sanc_card)

        # Cold start Card
        cold_card = QFrame()
        cold_card.setProperty("class", "cardFrame")
        cold_layout = QVBoxLayout(cold_card)
        cold_title = QLabel("🧊 前 14 天冷启动破冰策略 (Cold Start)")
        cold_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        cold_desc = QLabel(
            "严格控制初生期打扰频次：Day 1~3 每日最多主动发言 1 次；"
            "Day 4~7 每日 2 次；Day 8~14 每日 3 次。严禁热度泛滥。"
        )
        cold_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        cold_desc.setWordWrap(True)
        cold_layout.addWidget(cold_title)
        cold_layout.addWidget(cold_desc)
        layout.addWidget(cold_card)

        layout.addStretch()
        return container

    # ── Page 4: About ──
    def _build_about_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("关于 Co-evolving AI Companion")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        header.setFont(title_font)
        layout.addWidget(header)

        about_card = QFrame()
        about_card.setProperty("class", "cardFrame")
        about_layout = QVBoxLayout(about_card)
        about_desc = QLabel(
            "版本：v0.1.0 (Phase 1 MVP)\n"
            "架构原则：Body ≠ Brain ≠ Memory（极简小身体 + 独立大心智）\n"
            "核心理念：You shape it. It helps you shape yourself.\n"
            "遥测通信：127.0.0.1:17321"
        )
        about_desc.setStyleSheet("color: #9ca3af; font-size: 13px; line-height: 1.6;")
        about_layout.addWidget(about_desc)
        layout.addWidget(about_card)

        layout.addStretch()
        return container
