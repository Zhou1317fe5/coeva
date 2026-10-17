"""Chronicle Viewer: Read-only memory and slice archive window.

Provides an elegant, modern dark-themed secondary interface to review
accumulated user slices, conversation episodes, and unified evidence,
honoring the Clean Stage and Non-Judgmental Mirror disciplines.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.body.harvest_dialog import HarvestHistoryDialog
from src.core.chapters import ChapterEligibilityGate, ChapterGenerator, GrowthChapter
from src.core.hypotheses import (
    DevelopmentHypothesis,
    HypothesisEngine,
    HypothesisStatus,
)
from src.core.patterns import PatternBuilder
from src.core.self_model import (
    CalibrationResponse,
    InsightStatus,
    SelfModelManager,
)
from src.memory.store import SliceRecord

if TYPE_CHECKING:
    from src.memory.store import ChronicleStore, Episode


class ChronicleViewerWindow(QWidget):
    """Independent secondary window browsing the local Chronicle Store."""

    def __init__(self, store: ChronicleStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.model_mgr = SelfModelManager()
        self.chapter_generator = ChapterGenerator(self.store)
        self.setWindowTitle("📖 记忆与切片档案 (Chronicle Archive)")
        self.resize(880, 580)
        self.setMinimumSize(720, 480)

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

        self.harvest_btn = QPushButton("📦 导入历史会话...")
        self.harvest_btn.setFixedHeight(28)
        self.harvest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.harvest_btn.setStyleSheet(
            "background-color: #27272a; color: #10b981; "
            "border: 1px solid #059669; border-radius: 6px; padding: 0 10px;"
        )
        self.harvest_btn.clicked.connect(self._open_harvest_dialog)
        header_layout.addWidget(self.harvest_btn)

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
        self.nav_list.setFixedWidth(180)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_list.addItem("🌱 投喂切片 (Slices)")
        self.nav_list.addItem("🧭 经历会话 (Episodes)")
        self.nav_list.addItem("🔍 记忆检索 (Search)")
        self.nav_list.addItem("🌿 共同认知 (Self Model)")
        self.nav_list.addItem("📖 人生章节 (Chapters)")
        self.nav_list.currentRowChanged.connect(self._on_tab_changed)
        splitter.addWidget(self.nav_list)

        # Right Stacked Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_slices_page())
        self.stack.addWidget(self._build_episodes_page())
        self.stack.addWidget(self._build_search_page())
        self.stack.addWidget(self._build_self_model_page())
        self.stack.addWidget(self._build_chapters_page())
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
        self.episodes_list.itemClicked.connect(self._on_episode_selected)
        layout.addWidget(self.episodes_list, 1)

        # Episode Detail Box
        self.episode_detail = QTextEdit()
        self.episode_detail.setReadOnly(True)
        self.episode_detail.setFixedHeight(110)
        self.episode_detail.setPlaceholderText(
            "点击上方会话可查看完整起止时间、参与端与详细统计..."
        )
        layout.addWidget(self.episode_detail)

        return container

    def _build_search_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        search_bar = QHBoxLayout()
        search_bar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "输入关键词检索切片或历史会话/工具（如：代码、Bash、error、01a0）..."
        )
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

    def _build_self_model_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        tip = QLabel("伴生体基于真实经历谨慎提取的候选心智理解（需用户校准，绝不自封真理）：")
        tip.setStyleSheet("color: #9ca3af; font-size: 12px;")
        layout.addWidget(tip)

        # Hypotheses Section Header with Re-mine Button
        hyp_header = QHBoxLayout()
        hyp_title = QLabel("🌿 待校准心智假说 (Candidate Hypotheses)")
        hyp_title.setStyleSheet("font-weight: 600; color: #60a5fa; font-size: 13px;")
        hyp_header.addWidget(hyp_title)
        hyp_header.addStretch()

        self.btn_remine_patterns = QPushButton("🔄 基于最新经历重新挖掘")
        self.btn_remine_patterns.setFixedHeight(26)
        self.btn_remine_patterns.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remine_patterns.clicked.connect(self._re_mine_self_model)
        hyp_header.addWidget(self.btn_remine_patterns)
        layout.addLayout(hyp_header)

        self.hyp_list = QListWidget()
        self.hyp_list.setObjectName("dataList")
        layout.addWidget(self.hyp_list, 1)

        # Hyp Action Bar
        hyp_btn_row = QHBoxLayout()
        hyp_btn_row.setSpacing(8)

        self.btn_hyp_yes = QPushButton("✨ 认同该理解 (Yes)")
        self.btn_hyp_yes.clicked.connect(lambda: self._trigger_calibration(CalibrationResponse.YES))
        hyp_btn_row.addWidget(self.btn_hyp_yes)

        self.btn_hyp_partly = QPushButton("✏️ 补充校准 (Partly)")
        self.btn_hyp_partly.clicked.connect(
            lambda: self._trigger_calibration(CalibrationResponse.PARTLY)
        )
        hyp_btn_row.addWidget(self.btn_hyp_partly)

        self.btn_hyp_no = QPushButton("❌ 否定此判断 (No)")
        self.btn_hyp_no.clicked.connect(lambda: self._trigger_calibration(CalibrationResponse.NO))
        hyp_btn_row.addWidget(self.btn_hyp_no)

        layout.addLayout(hyp_btn_row)

        # Confirmed Insights Section
        ins_title = QLabel("🤝 双方已确认共识 (Confirmed Insights)")
        ins_title.setStyleSheet(
            "font-weight: 600; color: #34d399; font-size: 13px; margin-top: 6px;"
        )
        layout.addWidget(ins_title)

        self.ins_list = QListWidget()
        self.ins_list.setObjectName("dataList")
        self.ins_list.setFixedHeight(120)
        layout.addWidget(self.ins_list)

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
        elif index == 2:
            self._do_search()
        elif index == 3:
            self._refresh_self_model()
        elif index == 4:
            self._refresh_chapters()

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
        self._refresh_chapters()
        self._refresh_self_model()

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
        self.episode_detail.clear()
        episodes: list[Episode] = self.store.list_episodes(limit=200)

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
            item.setData(Qt.ItemDataRole.UserRole, ep)
            self.episodes_list.addItem(item)

    def _on_episode_selected(self, item: QListWidgetItem) -> None:
        ep: Episode | None = item.data(Qt.ItemDataRole.UserRole)
        if ep is not None:
            action_desc = (
                "用户主动下发了指令/提示词" if ep.has_user_action else "全程由 Agent 自主执行与修复"
            )
            agents_str = ", ".join(ep.agent_ids) if ep.agent_ids else "未知"
            self.episode_detail.setText(
                f"会话 ID: {ep.session_id}\n"
                f"参与终端: {agents_str}\n"
                f"起始时间: {ep.started_at}\n"
                f"结束时间: {ep.ended_at}\n"
                f"累计事件: {ep.event_count} 条客观行为记录\n"
                f"用户干预状态: {action_desc}"
            )

    def _do_search(self) -> None:
        kw = self.search_input.text().strip()
        self.search_results.clear()
        self.search_detail.clear()
        if not kw:
            return

        # 1. Search slices
        slice_results: list[SliceRecord] = self.store.search_slices(kw, limit=30)
        for s in slice_results:
            time_str = s.timestamp[:19].replace("T", " ")
            preview = s.content.replace("\n", " ")
            if len(preview) > 40:
                preview = preview[:40] + "..."
            list_item = QListWidgetItem(f"🌱 [切片] [{time_str}] {preview}")
            list_item.setData(Qt.ItemDataRole.UserRole, s)
            self.search_results.addItem(list_item)

        # 2. Search historical events
        event_results = self.store.search_events(kw, limit=50)
        for ev in event_results:
            time_str = ev["timestamp"][:19].replace("T", " ")
            agent = ev["agent_id"]
            etype = ev["event_type"]
            tname = ev.get("tool_name") or ""
            err = ev.get("error_message") or ""
            sid = ev["session_id"]
            sid_short = sid[:8] + "..." if len(sid) > 12 else sid
            extra = f"· 工具: {tname}" if tname else (f"· 报错: {err}" if err else "")
            disp = f"⚡ [{agent}] [{time_str}] {etype} {extra} (会话: {sid_short})"
            list_item = QListWidgetItem(disp)
            list_item.setData(Qt.ItemDataRole.UserRole, ev)
            self.search_results.addItem(list_item)

        if not slice_results and not event_results:
            empty_item = QListWidgetItem(f"未找到与 “{kw}” 相关的切片或事件")
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
        data: Any = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, SliceRecord):
            time_str = data.timestamp[:19].replace("T", " ")
            self.search_detail.setText(
                f"🌱 随手投喂切片\n时间: {time_str}\n情绪标签: {data.mood_flag}\n"
                f"来源: {data.source}\nID: {data.id}\n\n{data.content}"
            )
        elif isinstance(data, dict):
            time_str = data.get("timestamp", "")[:19].replace("T", " ")
            self.search_detail.setText(
                f"⚡ 遥测事件\n时间: {time_str}\nAgent: {data.get('agent_id')}\n"
                f"事件类型: {data.get('event_type')}\n工具名称: {data.get('tool_name')}\n"
                f"报错信息: {data.get('error_message')}\n会话 ID: {data.get('session_id')}"
            )

    def _re_mine_self_model(self) -> None:
        """Force re-run pattern builder on all latest episodes and re-synthesize hypotheses."""
        self._refresh_self_model(force_remine=True)
        stats = self.store.stats()
        ep_c = stats.get("episodes", 0)
        pats = PatternBuilder(self.store).build_patterns(min_episodes=2)
        QMessageBox.information(
            self,
            "挖掘完成",
            f"已根据当前 {ep_c} 个经历会话，成功挖掘出 {len(pats)} 个行为模式并生成候选假说！",
        )

    # ── Phase 2C Self Model Operations ──

    def _refresh_self_model(self, force_remine: bool = False) -> None:
        """Load candidate hypotheses, synthesize if empty or forced, and show confirmed insights."""
        self.hyp_list.clear()
        self.ins_list.clear()

        # 1. Hypotheses
        hyps = self.store.list_hypotheses(status=HypothesisStatus.CANDIDATE)
        if not hyps or force_remine:
            pats = PatternBuilder(self.store).build_patterns(min_episodes=2)
            fresh_hyps = HypothesisEngine().synthesize(pats)
            for h in fresh_hyps:
                self.store.save_hypothesis(h)
            hyps = self.store.list_hypotheses(status=HypothesisStatus.CANDIDATE)
        for h in hyps:
            lenses_str = " · ".join(f"[{lens.value}]" for lens in h.lenses)
            counter_tag = (
                f"⚠️ 反例: {len(h.counter_episodes)}处" if h.has_counter_evidence else "无反例"
            )
            item_text = (
                f"🌱 {h.statement}\n"
                f"   透镜: {lenses_str} | 置信度: {h.confidence.value} | "
                f"正例: {len(h.supporting_episodes)}处 | {counter_tag}"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, h)
            self.hyp_list.addItem(item)

        if not hyps:
            item = QListWidgetItem("暂无新的候选心智假说（当前经历样本不足，系统保持审慎沉默）")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.hyp_list.addItem(item)

        # 2. Confirmed Insights
        insights = self.store.list_insights(status=InsightStatus.ACTIVE)
        for ins in insights:
            item_text = (
                f"🤝 {ins.statement} (确认于 {ins.valid_from})\n"
                f"   批注: {ins.user_confirmation_text}"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, ins)
            self.ins_list.addItem(item)

        if not insights:
            item = QListWidgetItem("暂无双方确认的长期共识（需通过上方假说进行共同校准）")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.ins_list.addItem(item)

    def _on_hyp_selected(self, item: QListWidgetItem) -> None:
        pass

    def _trigger_calibration(self, response: CalibrationResponse) -> None:
        current_item = self.hyp_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先在上方列表中点击选中一条要校准的候选假说。")
            return

        hyp: DevelopmentHypothesis | None = current_item.data(Qt.ItemDataRole.UserRole)
        if not hyp or not isinstance(hyp, DevelopmentHypothesis):
            return

        user_comment = ""
        if response in (CalibrationResponse.PARTLY, CalibrationResponse.EXPLAIN):
            text, ok = QInputDialog.getText(
                self,
                "补充校准 (Calibration)",
                "这处理解有哪些需要补充或修正的细微之处？\n（例如：仅在特定场景成立）",
            )
            if not ok:
                return
            user_comment = text.strip()

        # Apply state machine
        updated_hyp, new_insight, revised_hyp = self.model_mgr.apply_calibration(
            hyp, response, user_comment=user_comment
        )

        self.store.save_hypothesis(updated_hyp)
        if new_insight:
            self.store.save_insight(new_insight)
        if revised_hyp:
            self.store.save_hypothesis(revised_hyp)

        action_names = {
            CalibrationResponse.YES: "已确认为长期共识！",
            CalibrationResponse.PARTLY: "已生成修正后的新假说！",
            CalibrationResponse.NO: "已永久否定并封存此判断，未来绝不再提。",
        }
        QMessageBox.information(self, "校准完成", action_names.get(response, "校准已记录"))
        self._refresh_self_model()

    def _open_harvest_dialog(self) -> None:
        """Open the historical session harvesting dialog and refresh upon completion."""
        dlg = HarvestHistoryDialog(self.store, parent=self)
        dlg.harvest_completed.connect(lambda _count: self.refresh_all())
        dlg.exec()

    # ── Page 5: Growth Chapters (Phase 2D) ──
    def _build_chapters_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        # Header: Title + Create Chapter Button
        top_row = QHBoxLayout()
        tip = QLabel("📖 人生章节：与伴生体共同经历凝练的成长纪实（由大模型与叙事防火墙共创）")
        tip.setStyleSheet("color: #9ca3af; font-size: 12px;")
        top_row.addWidget(tip)
        top_row.addStretch()

        self.btn_gen_chapter = QPushButton("✨ 共同撰写新章节...")
        self.btn_gen_chapter.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; "
            "border-radius: 6px; padding: 4px 12px;"
        )
        self.btn_gen_chapter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen_chapter.clicked.connect(self._generate_new_chapter)
        top_row.addWidget(self.btn_gen_chapter)
        layout.addLayout(top_row)

        # Chapter Splitter: Left chapter list, Right reading & reflection editor
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Left Column: Chapters List
        left_box = QWidget()
        l_layout = QVBoxLayout(left_box)
        l_layout.setContentsMargins(0, 0, 8, 0)
        l_layout.setSpacing(6)

        c_list_title = QLabel("📚 历史章节列表")
        c_list_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #60a5fa;")
        l_layout.addWidget(c_list_title)

        self.chapter_list = QListWidget()
        self.chapter_list.setObjectName("dataList")
        self.chapter_list.itemClicked.connect(self._on_chapter_selected)
        l_layout.addWidget(self.chapter_list, 1)
        splitter.addWidget(left_box)

        # Right Column: Chapter Content Viewer + Reflection Input
        right_box = QWidget()
        r_layout = QVBoxLayout(right_box)
        r_layout.setContentsMargins(8, 0, 0, 0)
        r_layout.setSpacing(8)

        # Title & Action bar for active chapter
        r_top = QHBoxLayout()
        self.chapter_title_label = QLabel("选择左侧章节查看正文")
        self.chapter_title_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #f3f4f6;"
        )
        r_top.addWidget(self.chapter_title_label)
        r_top.addStretch()

        self.btn_export_md = QPushButton("📤 导出 Markdown")
        self.btn_export_md.clicked.connect(self._export_chapter_markdown)
        r_top.addWidget(self.btn_export_md)
        r_layout.addLayout(r_top)

        # Markdown Text Browser
        self.chapter_content_view = QTextEdit()
        self.chapter_content_view.setReadOnly(True)
        r_layout.addWidget(self.chapter_content_view, 1)

        # Human Reflection Editor
        refl_title = QLabel("✍️ 用户手记与共同反思（双人共写留白 · 自动沉淀入章节）：")
        refl_title.setStyleSheet("font-size: 12px; color: #34d399; font-weight: 600;")
        r_layout.addWidget(refl_title)

        refl_row = QHBoxLayout()
        self.chapter_refl_edit = QLineEdit()
        self.chapter_refl_edit.setPlaceholderText(
            "在此写下这段时期你对工作方式或心智转变的真实感悟..."
        )
        refl_row.addWidget(self.chapter_refl_edit, 1)

        self.btn_save_refl = QPushButton("💾 保存手记")
        self.btn_save_refl.clicked.connect(self._save_chapter_reflection)
        refl_row.addWidget(self.btn_save_refl)
        r_layout.addLayout(refl_row)

        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self._active_chapter: GrowthChapter | None = None
        return container

    def _refresh_chapters(self) -> None:
        """Load and display all persisted growth chapters from disk."""
        self.chapter_list.clear()
        chapters = self.chapter_generator.list_chapters()
        for chap in chapters:
            item_text = f"📖 {chap.title}\n   周期: {chap.period_start} -> {chap.period_end}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, chap)
            self.chapter_list.addItem(item)

        if chapters and not self._active_chapter:
            self.chapter_list.setCurrentRow(0)
            self._on_chapter_selected(self.chapter_list.item(0))

    def _on_chapter_selected(self, item: QListWidgetItem) -> None:
        chap: GrowthChapter | None = item.data(Qt.ItemDataRole.UserRole)
        if not chap or not isinstance(chap, GrowthChapter):
            return
        self._active_chapter = chap
        self.chapter_title_label.setText(f"📖 {chap.title}")
        self.chapter_content_view.setMarkdown(chap.to_markdown())
        self.chapter_refl_edit.setText(chap.human_reflection)

    def _generate_new_chapter(self) -> None:
        """Evaluate eligibility gates and guide user through co-authoring a new chapter."""
        gate = ChapterEligibilityGate()
        eligible, report = gate.evaluate(self.store)

        if not eligible:
            s_info = report["sustained"]
            msg = (
                "当前尚未完全满足人生章节生成资格门（Chapter Eligibility Gates）：\n\n"
                f"• 持续性门: 会话数 {s_info['episodes_count']}/{s_info['min_episodes']}, "
                f"跨度 {s_info['span_days']}/{s_info['min_span_days']} 天\n"
                f"• 结构性门: 模式数 {report['structural']['patterns_count']}, "
                f"共识洞察 {report['structural']['insights_count']}\n"
                f"• 多样性门: 涵盖 Agent 终端 {report['diversity']['agents_count']} 种\n\n"
                "是否仍要强制触发撰写？"
            )
            reply = QMessageBox.question(
                self,
                "章节资格评估",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Prompt user for optional initial reflection note
        text, ok = QInputDialog.getMultiLineText(
            self,
            "共同撰写章节",
            "在这段工作周期里，你有什么想记录的心智转变或反思？\n（可留空，后续随时编辑补充）",
            "",
        )
        if not ok:
            return

        QMessageBox.information(
            self, "正在撰写", "伴生体正在调用大模型并流经叙事防火墙生成章节，请稍候..."
        )
        chapter, _ = self.chapter_generator.generate_chapter(
            force=True, user_reflection=text.strip()
        )

        if chapter:
            self._active_chapter = chapter
            self._refresh_chapters()
            self.chapter_title_label.setText(f"📖 {chapter.title}")
            self.chapter_content_view.setMarkdown(chapter.to_markdown())
            self.chapter_refl_edit.setText(chapter.human_reflection)
            QMessageBox.information(
                self, "章节生成成功", f"新章节《{chapter.title}》已生成并存入本地档案！"
            )
        else:
            QMessageBox.critical(self, "生成失败", "未能成功生成章节，请检查大模型配置是否连通。")

    def _save_chapter_reflection(self) -> None:
        if not self._active_chapter:
            QMessageBox.information(self, "提示", "请先在左侧选择一个章节。")
            return
        new_refl = self.chapter_refl_edit.text().strip()
        self._active_chapter.human_reflection = new_refl
        self._active_chapter.save(self.chapter_generator.chapters_dir)
        self.chapter_content_view.setMarkdown(self._active_chapter.to_markdown())
        QMessageBox.information(self, "保存成功", "用户手记已沉淀入该章节 Markdown 文件！")

    def _export_chapter_markdown(self) -> None:
        if not self._active_chapter:
            QMessageBox.information(self, "提示", "请先在左侧选择一个要导出的章节。")
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出章节 Markdown",
            f"chapter_{self._active_chapter.chapter_id}.md",
            "Markdown Files (*.md)",
        )
        if save_path:
            Path(save_path).write_text(self._active_chapter.to_markdown(), encoding="utf-8")
            QMessageBox.information(self, "导出成功", f"章节已导出至:\n{save_path}")
