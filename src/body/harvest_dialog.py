"""GUI Dialog for scanning and harvesting historical Multi-Agent sessions into Chronicle."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.connectors.history.harvester import MultiAgentHistoryHarvester

if TYPE_CHECKING:
    from src.memory.store import ChronicleStore


class HarvestHistoryDialog(QDialog):
    """Modern dark-themed dialog for multi-agent historical session harvesting."""

    harvest_completed = Signal(int)  # Emits total events ingested

    def __init__(self, store: ChronicleStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.harvester = MultiAgentHistoryHarvester()

        self.setWindowTitle("📦 历史多 Agent 会话收割 (Historical Session Harvesting)")
        self.resize(620, 480)
        self.setMinimumSize(540, 400)

        self._setup_ui()
        self._apply_styling()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Title & Purpose Description
        title_label = QLabel("多 Agent 历史会话归因收割")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #f3f4f6;")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "自动扫描本机与 WSL 中的 AI 终端日志（Pi Desktop / CLI、Codex CLI、Hermes）。\n"
            "• 严格零 Prompt 隐私：绝对不提取任何指令文本、思维链或工具输出；\n"
            "• 真实陪伴天数守卫：收割数据仅作为后台客观样本储备，绝不快进前台破冰节奏。"
        )
        desc_label.setStyleSheet("color: #9ca3af; font-size: 12px; line-height: 1.4;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # 2. Source Filters & Limit Options
        opts_row = QHBoxLayout()
        opts_row.setSpacing(12)

        self.cb_pi = QCheckBox("Pi (Desktop & CLI)")
        self.cb_pi.setChecked(True)
        opts_row.addWidget(self.cb_pi)

        self.cb_codex = QCheckBox("Codex CLI")
        self.cb_codex.setChecked(True)
        opts_row.addWidget(self.cb_codex)

        self.cb_hermes = QCheckBox("Hermes")
        self.cb_hermes.setChecked(True)
        opts_row.addWidget(self.cb_hermes)

        opts_row.addStretch()

        limit_label = QLabel("每来源上限:")
        limit_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        opts_row.addWidget(limit_label)

        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 1000)
        self.spin_limit.setValue(30)
        self.spin_limit.setToolTip("每个来源最多扫描提取的最新会话数")
        opts_row.addWidget(self.spin_limit)

        layout.addLayout(opts_row)

        # 3. Status Output Log Display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setObjectName("harvestLog")
        self.log_display.setPlaceholderText("点击下方「🔍 扫描预览」查看可收割资产...")
        layout.addWidget(self.log_display)

        # 4. Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_preview = QPushButton("🔍 扫描预览 (Dry-Run)")
        self.btn_preview.setFixedHeight(32)
        self.btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        btn_row.addWidget(self.btn_preview)

        self.btn_import = QPushButton("📥 一键安全收割导入")
        self.btn_import.setFixedHeight(32)
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; "
            "border: none; border-radius: 6px; padding: 0 16px;"
        )
        self.btn_import.clicked.connect(self._on_import_clicked)
        btn_row.addWidget(self.btn_import)

        btn_row.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _selected_sources(self) -> list[str]:
        sources: list[str] = []
        if self.cb_pi.isChecked():
            sources.append("pi")
        if self.cb_codex.isChecked():
            sources.append("codex")
        if self.cb_hermes.isChecked():
            sources.append("hermes")
        return sources

    def _on_preview_clicked(self) -> None:
        sources = self._selected_sources()
        if not sources:
            QMessageBox.warning(self, "提示", "请至少勾选一个 Agent 来源。")
            return

        limit = self.spin_limit.value()
        self.log_display.append(f"🔍 正在扫描系统 Agent 会话日志 (上限 {limit} 个/源)...")
        summary = self.harvester.dry_run(sources=sources, limit_per_source=limit)

        text = [
            "================= 扫描预览结果 =================",
            f"扫描来源: {', '.join(sources)}",
            "------------------------------------------------",
        ]
        for src, info in summary["sources"].items():
            text.append(f"[{src}]")
            text.append(f"  会话数 (Sessions) : {info['sessions_count']}")
            text.append(f"  事件数 (Events)   : {info['events_count']}")
            text.append(f"  时间跨度          : {info['earliest']} -> {info['latest']}")
        text.append("------------------------------------------------")
        text.append(f"合计发现会话: {summary['total_sessions']} 个")
        text.append(f"合计行为事件: {summary['total_events']} 条")
        text.append(
            f"时间跨度范围: {summary['earliest_timestamp']} -> {summary['latest_timestamp']}"
        )
        text.append("================================================\n")
        self.log_display.setPlainText("\n".join(text))

    def _on_import_clicked(self) -> None:
        sources = self._selected_sources()
        if not sources:
            QMessageBox.warning(self, "提示", "请至少勾选一个 Agent 来源。")
            return

        limit = self.spin_limit.value()
        self.log_display.append(f"📥 正在导入客观事件至 ChronicleStore (各源上限 {limit})...")

        counts = self.harvester.ingest_into_store(
            self.store, sources=sources, limit_per_source=limit
        )
        total = counts.get("total", 0)

        log_lines = [
            "✨ 导入完成！",
            "各源入库事件计数:",
        ]
        for src, c in counts.items():
            if src != "total":
                log_lines.append(f"  • {src:<12}: {c} 条事件")
        log_lines.append(f"总计导入: {total} 条客观事件")
        log_lines.append(f"当前记忆库状态: {self.store.stats()}")
        self.log_display.append("\n".join(log_lines))

        self.harvest_completed.emit(total)
        QMessageBox.information(
            self,
            "收割入库完成",
            f"已成功将 {total} 条客观行为事件安全存入伴生体档案库！\n"
            f"当前底层已累计 {self.store.stats()['events']} 条事件。\n\n"
            f"（注：前台桌宠陪伴天数仍按真实相处自然递增，绝不打扰日常工作。）",
        )

    def _apply_styling(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                color: #e4e4e7;
            }
            QCheckBox {
                color: #e4e4e7;
                font-size: 13px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                background-color: #27272a;
            }
            QCheckBox::indicator:checked {
                background-color: #059669;
                border-color: #059669;
            }
            QSpinBox {
                background-color: #27272a;
                color: #ffffff;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 2px 6px;
                min-width: 60px;
            }
            #harvestLog {
                background-color: #121215;
                color: #a1a1aa;
                border: 1px solid #27272a;
                border-radius: 6px;
                font-family: Consolas, "Courier New", monospace;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton {
                background-color: #27272a;
                color: #e4e4e7;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
