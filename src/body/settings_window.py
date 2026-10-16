"""Modern multi-agent and companion settings window inspired by Clawd on Desk."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFocusEvent, QFont, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.body.harvest_dialog import HarvestHistoryDialog
from src.connectors.hook_manager import AgentHookManager
from src.core.llm_client import PRESET_PROVIDERS, LLMClient, LLMConfig
from src.feeder.hotkey import DEFAULT_FEEDER_HOTKEY, hotkey_display, hotkey_from_qt
from src.memory.store import ChronicleStore

if TYPE_CHECKING:
    from src.connectors.settings import AgentSettingsStore
    from src.core.cold_start import ColdStartPolicy
    from src.core.sanctuary import SanctuaryGuard


class _HotkeyRecorderEdit(QLineEdit):
    """Read-only field that records a key chord the moment it has focus.

    Click it and press the chord: the canonical spec is emitted for the owner to
    persist. Esc abandons the recording and restores the displayed combination.
    """

    hotkey_captured = Signal(str)
    capture_rejected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self._recording = False
        self._current_spec = ""
        self.setPlaceholderText("点击此处，然后按下组合键")
        self.setToolTip("点击后直接按下想要的组合键；按 Esc 放弃录制")

    def set_current(self, spec: str) -> None:
        """Show the active combination without entering recording mode."""
        self._current_spec = spec
        if not self._recording:
            self.setText(hotkey_display(spec))

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._start_recording()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        self._stop_recording()
        self.setText(hotkey_display(self._current_spec))
        super().focusOutEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        super().mousePressEvent(event)
        self._start_recording()

    def _start_recording(self) -> None:
        self._recording = True
        self.clear()
        self.setPlaceholderText("请按下组合键… (Esc 放弃)")

    def _stop_recording(self) -> None:
        self._recording = False
        self.setPlaceholderText("点击此处，然后按下组合键")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self.capture_rejected.emit("已放弃录制，快捷键未改动")
            self.clearFocus()
            return
        spec = hotkey_from_qt(event.modifiers(), Qt.Key(event.key()))
        if spec is None:
            self.capture_rejected.emit("组合键无效：需包含 Ctrl / Alt / Shift / Win 修饰键")
            return
        # Show the result immediately; focus may never change (e.g. tests, or a
        # window that keeps focus), so the text must not depend on focus-out.
        self._stop_recording()
        self.set_current(spec.spec)
        self.hotkey_captured.emit(spec.spec)
        self.clearFocus()

class _LLMPingThread(QThread):
    """Background worker for testing LLM API connection without blocking GUI."""

    finished_ping = Signal(bool, str, float)

    def __init__(self, client: LLMClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client

    def run(self) -> None:
        ok, msg, lat = self.client.test_connection()
        self.finished_ping.emit(ok, msg, lat)


class SettingsWindow(QWidget):
    """Full-featured preferences and multi-agent management dialog."""
    pet_changed = Signal(str)
    scale_changed = Signal(float)
    hotkey_changed = Signal(str)


    def __init__(
        self,
        settings_store: AgentSettingsStore,
        hook_manager: AgentHookManager | None = None,
        parent: QWidget | None = None,
        *,
        sanctuary: SanctuaryGuard | None = None,
        cold_start: ColdStartPolicy | None = None,
        chronicle_store: ChronicleStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = settings_store
        self.hook_manager = hook_manager or AgentHookManager()
        self.chronicle = chronicle_store
        # Live Growth Core handles. When absent the page reports "未接入" instead of
        # pretending these switches are configurable (they are not: Sanctuary is a
        # safety floor, and the cold-start stage is derived from real elapsed days).
        self._sanctuary = sanctuary
        self._cold_start = cold_start
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
            ("🧠  大模型服务", "llm"),
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

        # Page 2: LLM Service Config (Phase 2D)
        self.llm_page = self._build_llm_page()
        self.stack.addWidget(self.llm_page)

        # Page 3: Body Preferences
        self.body_page = self._build_body_page()
        self.stack.addWidget(self.body_page)

        # Page 4: Mind & Sanctuary
        self.core_page = self._build_core_page()
        self.stack.addWidget(self.core_page)

        # Page 5: About
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
        item = self.nav_list.item(index)
        key = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
        if key == "agents":
            self.refresh_agents()
        elif key == "core":
            self.refresh_core_status()

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
        harvest_btn = QPushButton("📦 历史会话收割...")
        harvest_btn.setToolTip("从本机与 WSL 中收割历史会话客观事件入库")
        harvest_btn.clicked.connect(self._open_harvest_dialog)
        header_row.addWidget(harvest_btn)

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
        res = self.hook_manager.install_hook(agent_id, instance_id)
        if res.get("ok"):
            self.store.update_instance(agent_id, instance_id, enabled=True)
        else:
            err = res.get("error", "未知错误")
            QMessageBox.warning(
                self,
                "接入失败",
                f"无法为 {agent_id} ({instance_id}) 一键接入：\n{err}",
            )
        self.refresh_agents()

    def _uninstall_hook_and_refresh(self, agent_id: str, instance_id: str) -> None:
        res = self.hook_manager.uninstall_hook(agent_id, instance_id)
        if not res.get("ok"):
            err = res.get("error", "未知错误")
            QMessageBox.warning(
                self,
                "卸载失败",
                f"无法为 {agent_id} ({instance_id}) 卸载 Hook：\n{err}",
            )
        self.refresh_agents()

    def _scan_and_deploy_all_wsl(self) -> None:
        distros = self.hook_manager.get_wsl_distros()
        for distro in distros:
            iid = f"wsl:{distro}"
            for aid in ("hermes", "pi-cli", "codex", "claude-code"):
                self.hook_manager.install_hook(aid, iid)
                self.store.update_instance(aid, iid, enabled=True)
        self.refresh_agents()

    # ── Page 2: LLM Service Config (Phase 2D) ──
    def _build_llm_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("大模型服务与章节叙事配置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        header.setFont(title_font)
        layout.addWidget(header)

        desc = QLabel(
            "配置 OpenAI 兼容格式大模型接口，用于生成人生章节（Growth Chapters）与深度心智反思。\n"
            "支持官方 API、DeepSeek、本地 Ollama / vLLM 或第三方代理。Key 安全保存在本地。"
        )
        desc.setStyleSheet("color: #9ca3af; font-size: 12px; line-height: 1.4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Provider Quick Presets
        preset_box = QFrame()
        preset_box.setProperty("class", "cardFrame")
        p_layout = QVBoxLayout(preset_box)
        p_layout.setSpacing(8)

        p_title = QLabel("🚀 常用服务商快速预设 (Presets)")
        p_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #e4e4e7;")
        p_layout.addWidget(p_title)

        p_row = QHBoxLayout()
        p_row.setSpacing(8)
        for name, p_data in PRESET_PROVIDERS.items():
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            u_val = p_data["base_url"]
            m_val = p_data["default_model"]
            btn.clicked.connect(lambda _c, u=u_val, m=m_val: self._apply_llm_preset(u, m))
            p_row.addWidget(btn)
        p_row.addStretch()
        p_layout.addLayout(p_row)
        layout.addWidget(preset_box)

        # Parameters Card
        card = QFrame()
        card.setProperty("class", "cardFrame")
        c_layout = QVBoxLayout(card)
        c_layout.setSpacing(10)

        self.llm_config = LLMConfig.load()

        # Base URL
        url_lbl = QLabel("接口地址 (Base URL):")
        url_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
        c_layout.addWidget(url_lbl)
        self.llm_url_edit = QLineEdit(self.llm_config.base_url)
        self.llm_url_edit.setPlaceholderText("https://api.openai.com/v1 或 http://localhost:11434/v1")
        c_layout.addWidget(self.llm_url_edit)

        # API Key
        key_lbl = QLabel("API Key (密码掩码):")
        key_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
        c_layout.addWidget(key_lbl)
        key_row = QHBoxLayout()
        self.llm_key_edit = QLineEdit(self.llm_config.api_key)
        self.llm_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_key_edit.setPlaceholderText("sk-...")
        key_row.addWidget(self.llm_key_edit)
        self.btn_toggle_key = QPushButton("👁️")
        self.btn_toggle_key.setFixedWidth(36)
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.btn_toggle_key)
        c_layout.addLayout(key_row)

        # Model Name
        model_lbl = QLabel("模型名称 (Model):")
        model_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
        c_layout.addWidget(model_lbl)
        self.llm_model_edit = QLineEdit(self.llm_config.model)
        self.llm_model_edit.setPlaceholderText("例如: gpt-4o, deepseek-chat, gemini-3.8-flash")
        c_layout.addWidget(self.llm_model_edit)

        # Temperature & Max Tokens
        param_row = QHBoxLayout()
        param_row.setSpacing(16)

        temp_col = QVBoxLayout()
        temp_lbl = QLabel("温度 (Temperature):")
        temp_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
        temp_col.addWidget(temp_lbl)
        self.llm_temp_spin = QDoubleSpinBox()
        self.llm_temp_spin.setRange(0.0, 2.0)
        self.llm_temp_spin.setSingleStep(0.1)
        self.llm_temp_spin.setValue(self.llm_config.temperature)
        temp_col.addWidget(self.llm_temp_spin)
        param_row.addLayout(temp_col)

        tok_col = QVBoxLayout()
        tok_lbl = QLabel("单次最大 Token (Max Tokens):")
        tok_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
        tok_col.addWidget(tok_lbl)
        self.llm_tok_spin = QSpinBox()
        self.llm_tok_spin.setRange(256, 16384)
        self.llm_tok_spin.setValue(self.llm_config.max_tokens)
        tok_col.addWidget(self.llm_tok_spin)
        param_row.addLayout(tok_col)

        c_layout.addLayout(param_row)
        layout.addWidget(card)

        # Status badge & actions row
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.btn_test_llm = QPushButton("⚡ 测试连接 (Test Connection)")
        self.btn_test_llm.setFixedHeight(32)
        self.btn_test_llm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_llm.clicked.connect(self._test_llm_connection)
        action_row.addWidget(self.btn_test_llm)

        self.btn_save_llm = QPushButton("💾 保存配置 (Save)")
        self.btn_save_llm.setFixedHeight(32)
        self.btn_save_llm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_llm.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; "
            "border-radius: 6px; padding: 0 16px;"
        )
        self.btn_save_llm.clicked.connect(self._save_llm_config)
        action_row.addWidget(self.btn_save_llm)

        self.llm_status_badge = QLabel("就绪")
        self.llm_status_badge.setStyleSheet("color: #9ca3af; font-size: 12px;")
        action_row.addWidget(self.llm_status_badge)

        action_row.addStretch()
        layout.addLayout(action_row)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _apply_llm_preset(self, url: str, model: str) -> None:
        self.llm_url_edit.setText(url)
        self.llm_model_edit.setText(model)
        self.llm_status_badge.setText(f"已填入预设 ({model})，请输入 API Key 并保存")

    def _toggle_key_visibility(self) -> None:
        if self.llm_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.llm_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.llm_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _save_llm_config(self) -> None:
        cfg = LLMConfig(
            base_url=self.llm_url_edit.text().strip(),
            api_key=self.llm_key_edit.text().strip(),
            model=self.llm_model_edit.text().strip(),
            temperature=self.llm_temp_spin.value(),
            max_tokens=self.llm_tok_spin.value(),
        )
        cfg.save()
        self.llm_config = cfg
        self.llm_status_badge.setText("✅ 配置已安全保存至 data/llm_config.json")
        self.llm_status_badge.setStyleSheet("color: #10b981; font-weight: bold;")

    def _test_llm_connection(self) -> None:
        cfg = LLMConfig(
            base_url=self.llm_url_edit.text().strip(),
            api_key=self.llm_key_edit.text().strip(),
            model=self.llm_model_edit.text().strip(),
            temperature=0.0,
            timeout_seconds=10.0,
        )
        self.llm_status_badge.setText("⏳ 正在测试连通性...")
        self.llm_status_badge.setStyleSheet("color: #9ca3af;")
        self.btn_test_llm.setEnabled(False)
        self._llm_thread = _LLMPingThread(LLMClient(cfg), parent=self)
        self._llm_thread.finished_ping.connect(self._on_llm_ping_finished)
        self._llm_thread.start()

    def _on_llm_ping_finished(self, ok: bool, msg: str, latency: float) -> None:
        self.btn_test_llm.setEnabled(True)
        if ok:
            self.llm_status_badge.setText(f"✅ 连通正常！延迟: {latency:.0f}ms")
            self.llm_status_badge.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.llm_status_badge.setText(f"❌ 失败: {msg[:40]}")
            self.llm_status_badge.setStyleSheet("color: #ef4444;")

    # ── Page 3: Desktop Body Preferences ──
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
            "在任何软件或网页下即可随时唤起半透明磨砂输入弹窗，输入回车瞬时存盘，失焦秒隐。"
        )
        feed_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        feed_desc.setWordWrap(True)
        feed_layout.addWidget(feed_title)
        feed_layout.addWidget(feed_desc)

        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(8)
        self.hotkey_edit = _HotkeyRecorderEdit(feed_card)
        self.hotkey_edit.set_current(self.store.feeder_hotkey)
        self.hotkey_edit.setMinimumWidth(200)
        self.hotkey_edit.hotkey_captured.connect(self._on_hotkey_captured)
        self.hotkey_edit.capture_rejected.connect(self._on_hotkey_rejected)
        hotkey_row.addWidget(self.hotkey_edit, 1)

        reset_hotkey_btn = QPushButton("↺ 恢复默认")
        reset_hotkey_btn.setFixedHeight(30)
        reset_hotkey_btn.clicked.connect(self._on_hotkey_reset)
        hotkey_row.addWidget(reset_hotkey_btn)
        feed_layout.addLayout(hotkey_row)

        self.hotkey_hint = QLabel("")
        self.hotkey_hint.setStyleSheet("color: #9ca3af; font-size: 12px;")
        self.hotkey_hint.setWordWrap(True)
        feed_layout.addWidget(self.hotkey_hint)
        layout.addWidget(feed_card)

        layout.addStretch()
        return container

    # ── Feeder Hotkey Handlers ──
    def _on_hotkey_captured(self, spec: str) -> None:
        """Persist a freshly recorded hotkey and tell the app to re-register it.

        ``spec`` is already a validated canonical combination, so the store
        cannot reject it; the emitted signal is what makes it live without a
        restart.
        """
        self.store.set_feeder_hotkey(spec)
        self.hotkey_edit.set_current(spec)
        self.hotkey_hint.setText(f"✅ 已更新为 {hotkey_display(spec)}，立即生效，无需重启。")
        self.hotkey_changed.emit(spec)

    def _on_hotkey_rejected(self, message: str) -> None:
        """Surface why a recording attempt was refused, leaving the value intact."""
        self.hotkey_edit.set_current(self.store.feeder_hotkey)
        self.hotkey_hint.setText(f"⚠️ {message}")

    def _on_hotkey_reset(self) -> None:
        """Restore the shipped default combination."""
        self._on_hotkey_captured(DEFAULT_FEEDER_HOTKEY)
        self.hotkey_hint.setText(
            f"↺ 已恢复默认 {hotkey_display(DEFAULT_FEEDER_HOTKEY)}，立即生效。"
        )

    # ── Page 3: Growth Core & Sanctuary ──
    def _build_core_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = QLabel("长盛心智与避风港状态")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        header.setFont(title_font)
        layout.addWidget(header)

        note = QLabel(
            "以下为运行时的真实状态，供你确认系统当前的行为边界；"
            "这里不提供开关——避风港是安全底线，冷启动阶段按真实天数自动推进。"
        )
        note.setStyleSheet("color: #9ca3af; font-size: 12px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Sanctuary Card
        sanc_card = QFrame()
        sanc_card.setProperty("class", "cardFrame")
        sanc_layout = QVBoxLayout(sanc_card)
        sanc_title = QLabel("🍃 情绪避风港守卫 (Sanctuary Guard)")
        sanc_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.sanctuary_status = QLabel()
        self.sanctuary_status.setStyleSheet("font-size: 13px; font-weight: 600;")
        sanc_desc = QLabel(
            "激活时 100% 熔断一切分析、说教与 Agent 气泡，只保留安静陪伴。"
        )
        sanc_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        sanc_desc.setWordWrap(True)
        sanc_layout.addWidget(sanc_title)
        sanc_layout.addWidget(self.sanctuary_status)
        sanc_layout.addWidget(sanc_desc)
        layout.addWidget(sanc_card)

        # Cold start Card
        cold_card = QFrame()
        cold_card.setProperty("class", "cardFrame")
        cold_layout = QVBoxLayout(cold_card)
        cold_title = QLabel("🧊 冷启动破冰策略 (Cold Start)")
        cold_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.coldstart_status = QLabel()
        self.coldstart_status.setStyleSheet("font-size: 13px; font-weight: 600;")
        cold_desc = QLabel(
            "Day 1~3 每日主动发言上限 1 次；Day 4~7 上限 2 次；Day 8~14 上限 3 次；"
            "第 15 天起进入成熟期。上限同时约束 Agent 事件触发的气泡。"
        )
        cold_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        cold_desc.setWordWrap(True)
        cold_layout.addWidget(cold_title)
        cold_layout.addWidget(self.coldstart_status)
        cold_layout.addWidget(cold_desc)
        layout.addWidget(cold_card)

        layout.addStretch()
        self.refresh_core_status()
        return container

    def set_core_handles(
        self, sanctuary: SanctuaryGuard, cold_start: ColdStartPolicy
    ) -> None:
        """Attach the live Growth Core instances for the status page.

        Called after construction because the runner builds the settings window
        before it builds the Growth Core; the page then reports real state instead
        of static prose.
        """
        self._sanctuary = sanctuary
        self._cold_start = cold_start
        self.refresh_core_status()

    def refresh_core_status(self) -> None:
        """Re-read the Growth Core state, so the page never shows stale facts."""
        muted = "font-size: 13px; font-weight: 600; color: #9ca3af;"
        active = "font-size: 13px; font-weight: 600; color: #34d399;"

        if self._sanctuary is None:
            self.sanctuary_status.setText("⚪ 未接入（当前进程未提供避风港实例）")
            self.sanctuary_status.setStyleSheet(muted)
        elif self._sanctuary.is_active:
            self.sanctuary_status.setText("🟢 已激活 · 正在静默陪伴，暂停一切主动发言")
            self.sanctuary_status.setStyleSheet(active)
        else:
            self.sanctuary_status.setText("⚪ 未激活 · 常规观察中")
            self.sanctuary_status.setStyleSheet(muted)

        if self._cold_start is None:
            self.coldstart_status.setText("⚪ 未接入（当前进程未提供冷启动实例）")
            self.coldstart_status.setStyleSheet(muted)
            return

        policy = self._cold_start
        remaining = max(0, policy.daily_speech_quota - policy.speeches_today)
        stage_labels = {
            "stage_1_presence": "Stage 1 · 纯动作陪伴",
            "stage_2_fact_mirror": "Stage 2 · 状态关怀 + 切片回响",
            "stage_3_calibration": "Stage 3 · 允许一次试探性习惯询问",
            "stage_mature": "成熟期 · 完整发展策略",
        }
        stage = str(policy.stage)
        label = stage_labels.get(stage, stage)
        analysis = (
            "允许"
            if policy.allows_psychological_analysis
            else "禁止（前两阶段严禁心理分析）"
        )
        self.coldstart_status.setText(
            f"第 {policy.day_count} 天 · {label}\n"
            f"今日主动发言配额 {policy.daily_speech_quota} 次，剩余 {remaining} 次"
            f" · 深度心理分析：{analysis}"
        )
        self.coldstart_status.setStyleSheet("font-size: 13px; font-weight: 600; color: #60a5fa;")

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

    def _open_harvest_dialog(self) -> None:
        """Open the multi-agent historical session harvesting dialog."""
        store = self.chronicle or ChronicleStore()
        dlg = HarvestHistoryDialog(store, parent=self)
        dlg.exec()
