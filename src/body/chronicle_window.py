"""Chronicle Viewer: Read-only memory and slice archive window.

Provides an elegant, modern dark-themed secondary interface to review
accumulated user slices, conversation episodes, and unified evidence,
honoring the Clean Stage and Non-Judgmental Mirror disciplines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src.memory.store import ChronicleStore, Episode, SliceRecord


class ChronicleViewerWindow(QWidget):
    """Independent secondary window browsing the local Chronicle Store."""

    def __init__(self, store: ChronicleStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("📖 记忆与切片档案 (Chronicle Archive)")
        self.resize(760, 560)
        self.setMinimumSize(600, 420)

        self._setup_ui()
        self._apply_styling()
        self.refresh_all()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── 1. Header Bar: Title, Stats & Refresh ──
        header_bar = QWidget()
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        title_label = QLabel("📖 伴生体生命档案库")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #f3f4f6;")
        header_layout.addWidget(title_label)

        self.stats_badge = QLabel("载入中...")
        self.stats_badge.setStyleSheet(
            "background-color: #26262a; color: #9ca3af; "
            "border: 1px solid #333338; border-radius: 6px; "
            "padding: 4px 10px; font-size: 12px;"
        )
        header_layout.addWidget(self.stats_badge)
        header_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setFixedHeight(28)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_all)
        header_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(header_bar)

        # ── 2. Content Splitter: Left Sidebar Tabs, Right Details ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Left Nav List
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("chronicleNav")
        self.nav_list.setFixedWidth(160)
        self.nav_list.addItem("🌱 投喂切片 (Slices)")
        self.nav_list.addItem("🧭 经历会话 (Episodes)")
        self.nav_list.addItem("🔍 记忆检索 (Search)")
        self.nav_list.currentRowChanged.connect(self._on_tab_changed)
        splitter.addWidget(self.nav_list)

        # Right Stacked Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_slices_page())
        self.stack.addWidget(self._build_episodes_page())
        self.stack.addWidget(self._build_search_page())
        splitter.addWidget(self.stack)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        self.nav_list.setCurrentRow(0)

    def _build_slices_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        tip = QLabel("记录用户通过随手投喂（Alt+Space）写下的真实思考与状态切片：")
        tip.setStyleSheet("color: #9ca3af; font-size: 12px;")
        layout.addWidget(tip)

        self.slices_list = QListWidget()
        self.slices_list.setObjectName("dataList")
        self.slices_list.itemClicked.connect(self._on_slice_selected)
        layout.addWidget(self.slices_list, 1)

        # Detail Box
        self.slice_detail = QTextEdit()
        self.slice_detail.setReadOnly(True)
        self.slice_detail.setFixedHeight(110)
        self.slice_detail.setPlaceholderText("点击上方切片可查看完整原文字句与时间戳...")
        layout.addWidget(self.slice_detail)

        return container

    def _build_episodes_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        tip = QLabel("按工作会话（Session）天然聚合的经历序列，记录伴生体陪伴的客观痕迹：")
        tip.setStyleSheet("color: #9ca3af; font-size: 12px;")
        layout.addWidget(tip)

        self.episodes_list = QListWidget()
        self.episodes_list.setObjectName("dataList")
        layout.addWidget(self.episodes_list, 1)

        return container

    def _build_search_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        search_bar = QHBoxLayout()
        search_bar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词实时检索历史切片（如：代码、疲惫、灵感）...")
        self.search_input.setFixedHeight(32)
        self.search_input.returnPressed.connect(self._do_search)
        search_bar.addWidget(self.search_input, 1)

        search_btn = QPushButton("搜索")
        search_btn.setFixedHeight(32)
        search_btn.clicked.connect(self._do_search)
        search_bar.addWidget(search_btn)
        layout.addLayout(search_bar)

        self.search_results = QListWidget()
        self.search_results.setObjectName("dataList")
        self.search_results.itemClicked.connect(self._on_search_selected)
        layout.addWidget(self.search_results, 1)

        self.search_detail = QTextEdit()
        self.search_detail.setReadOnly(True)
        self.search_detail.setFixedHeight(100)
        layout.addWidget(self.search_detail)

        return container

    def _apply_styling(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1e;
                color: #e5e7eb;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
            }
            QListWidget#chronicleNav {
                background-color: #141416;
                border: none;
                border-right: 1px solid #28282c;
                padding-top: 8px;
            }
            QListWidget#chronicleNav::item {
                height: 36px;
                padding-left: 12px;
                margin: 2px 6px;
                border-radius: 6px;
                color: #9ca3af;
                font-weight: 500;
            }
            QListWidget#chronicleNav::item:selected {
                background-color: #27272b;
                color: #60a5fa;
                font-weight: 600;
            }
            QListWidget#dataList {
                background-color: #202024;
                border: 1px solid #2e2e34;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget#dataList::item {
                border-bottom: 1px solid #2b2b30;
                padding: 8px 6px;
                border-radius: 4px;
            }
            QListWidget#dataList::item:hover {
                background-color: #292930;
            }
            QListWidget#dataList::item:selected {
                background-color: #2d3748;
                color: #f3f4f6;
            }
            QLineEdit, QTextEdit {
                background-color: #202024;
                border: 1px solid #2e2e34;
                border-radius: 6px;
                color: #f3f4f6;
                padding: 6px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background-color: #2e2e34;
                border: 1px solid #3b3b42;
                border-radius: 6px;
                color: #e5e7eb;
                padding: 4px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3b3b44;
                color: #ffffff;
            }
        """)

    def _on_tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 0:
            self._refresh_slices()
        elif index == 1:
            self._refresh_episodes()

    def refresh_all(self) -> None:
        """Reload all statistics and active list data from the database."""
        stats = self.store.stats()
        self.stats_badge.setText(
            f"🌱 投喂切片: {stats.get('slices', 0)} 条  ·  "
            f"⚡ 遥测事件: {stats.get('events', 0)} 条  ·  "
            f"🧭 经历会话: {stats.get('episodes', 0)} 个"
        )
        self._refresh_slices()
        self._refresh_episodes()

    def _refresh_slices(self) -> None:
        self.slices_list.clear()
        slices: list[SliceRecord] = self.store.list_slices(limit=100)
        mood_emojis = {
            "neutral": "⚪",
            "frustrated": "🌧️ 烦躁/受挫",
            "reflective": "🍃 反思",
            "joyful": "✨ 喜悦",
        }

        for item in slices:
            time_str = item.timestamp[:19].replace("T", " ")
            mood_tag = mood_emojis.get(item.mood_flag, f"⚪ {item.mood_flag}")
            # Truncate preview
            preview = item.content.replace("\n", " ")
            if len(preview) > 42:
                preview = preview[:42] + "..."

            display_text = f"[{time_str}] {mood_tag} | {preview}"
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.slices_list.addItem(list_item)

    def _refresh_episodes(self) -> None:
        self.episodes_list.clear()
        episodes: list[Episode] = self.store.list_episodes(limit=50)

        for ep in episodes:
            start_str = ep.started_at[:19].replace("T", " ")
            end_str = ep.ended_at[11:19]
            agents_str = ",".join(ep.agent_ids) if ep.agent_ids else "agent"
            action_badge = "👤 包含用户主动提示" if ep.has_user_action else "🤖 纯 Agent 自动执行"

            sid_short = ep.session_id
            if len(sid_short) > 24:
                sid_short = sid_short[:10] + "..." + sid_short[-8:]

            text = (
                f"会话: {sid_short} ({start_str} ~ {end_str})\n"
                f"  共计 {ep.event_count} 次事件 · 参与端: [{agents_str}] · {action_badge}"
            )
            item = QListWidgetItem(text)
            self.episodes_list.addItem(item)

    def _do_search(self) -> None:
        kw = self.search_input.text().strip()
        self.search_results.clear()
        self.search_detail.clear()
        if not kw:
            return

        results: list[SliceRecord] = self.store.search_slices(kw, limit=50)
        for item in results:
            time_str = item.timestamp[:19].replace("T", " ")
            preview = item.content.replace("\n", " ")
            if len(preview) > 45:
                preview = preview[:45] + "..."
            list_item = QListWidgetItem(f"[{time_str}] {preview}")
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.search_results.addItem(list_item)

        if not results:
            empty_item = QListWidgetItem(f"未找到与 “{kw}” 相关的切片记忆")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.search_results.addItem(empty_item)

    def _on_slice_selected(self, item: QListWidgetItem) -> None:
        record: SliceRecord | None = item.data(Qt.ItemDataRole.UserRole)
        if record is not None:
            time_str = record.timestamp[:19].replace("T", " ")
            self.slice_detail.setText(
                f"时间: {time_str}\n"
                f"情绪标签: {record.mood_flag} (来源: {record.source})\n"
                f"ID: {record.id}\n\n"
                f"{record.content}"
            )

    def _on_search_selected(self, item: QListWidgetItem) -> None:
        record: SliceRecord | None = item.data(Qt.ItemDataRole.UserRole)
        if record is not None:
            time_str = record.timestamp[:19].replace("T", " ")
            self.search_detail.setText(
                f"时间: {time_str} | ID: {record.id}\n\n{record.content}"
            )
