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

from src.core.paths import (
    get_body_position_path,
    get_chapters_dir,
    get_data_dir,
    get_db_path,
    get_first_seen_path,
    get_jsonl_path,
    get_settings_path,
)
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
from src.core.flags import (
    PRODUCTION_V2_CAPABILITIES,
    resolve_flags,
    validate_memory_v2_configuration,
)
from src.core.cold_start import ColdStartPolicy
from src.memory.v2.chapter import ChapterRepository
from src.memory.v2.compatibility import (
    CompatibilityReader,
    V2ChronicleStoreAdapter,
    V2EventStoreAdapter,
)
from src.memory.v2.consolidation_scheduler import ConsolidationScheduler
from src.memory.v2.jsonl_export import JsonlSliceExporter
from src.memory.v2.recall_gate import RecallContext, RecallGate
from src.memory.v2.retrieval.config import RetrievalConfig
from src.memory.v2.retrieval.models import RetrievalQueryContext
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import RetrievalRepository
from src.memory.v2.router import RawEvidenceRouter
from src.memory.v2.self_model import SlowPathSelfModelService
from src.memory.v2.store import ChronicleStoreV2
from src.memory.v2.write_service import RawEvidenceWriteService, WriteSliceCommand
from src.core.intervention import InterventionPolicy
from src.core.llm_client import CompanionAIEngine, LLMConfig
from src.core.personality import load_personality
from src.core.sanctuary import SanctuaryGuard
from src.core.state_watcher import StateWatcher
from src.feeder.contracts import RawSlice
from src.feeder.hotkey import DEFAULT_FEEDER_HOTKEY, GlobalHotkeyListener, hotkey_display
from src.feeder.storage import SliceStore
from src.memory.retriever import MemoryRetriever
from src.memory.store import ChronicleStore, SliceRecord

# Evidence decay runs at startup and once a day thereafter.
_PRUNE_INTERVAL_MS = 24 * 60 * 60 * 1000

# Low-frequency State Care intervention check (overwork & late-night nudge).
# Evaluates the 3 Gates every 5 minutes; stays 100% silent if in flight or quota full.
_CARE_CHECK_INTERVAL_MS = 5 * 60 * 1000
_IN_FLIGHT_COOLDOWN_SECONDS = 30.0


class CompanionApp:
    """Orchestrates Desktop Pet Body, Slice Feeder, and Growth Core in one process."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        # Guarantee current checkout is top-priority in sys.path
        repo_root = Path(__file__).parent.resolve()
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        existing_app = QApplication.instance()
        if isinstance(existing_app, QApplication):
            self.app = existing_app
        else:
            self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 0. Multi-Agent & Companion Settings (Unambiguous Data Root)
        self.data_dir = get_data_dir(data_dir)
        settings_path = get_settings_path(self.data_dir)
        db_path = get_db_path(self.data_dir)
        jsonl_path = get_jsonl_path(self.data_dir)
        chapters_dir = get_chapters_dir(self.data_dir)

        self.agent_settings = AgentSettingsStore(file_path=settings_path)
        self.flags = self.agent_settings.memory_v2_flags
        self.memory_v2_diag = validate_memory_v2_configuration(
            self.flags,
            capabilities=PRODUCTION_V2_CAPABILITIES,
        )
        self.hook_manager = AgentHookManager()
        self.settings_window = SettingsWindow(self.agent_settings, self.hook_manager)
        self.settings_window.pet_changed.connect(self._on_pet_changed)
        self.settings_window.scale_changed.connect(self._on_scale_changed)
        self.settings_window.hotkey_changed.connect(self._on_hotkey_changed)
        self.settings_window.llm_config_changed.connect(self._on_llm_config_changed)
        self.settings_window.action_test_requested.connect(self._on_action_test_requested)

        # 1. Desktop Body (Defaults to Vasu, or saved pet preference)
        selected_pet = self.agent_settings.selected_pet
        assets_dir = Path("assets") / "pets" / selected_pet
        if not assets_dir.is_dir():
            assets_dir = Path("assets") / "pets" / "vasu"
        if not assets_dir.is_dir():
            assets_dir = Path("assets") / "pets" / "calico"
        self.window = PetWindow(
            assets_dir,
            position_config_path=get_body_position_path(self.data_dir),
        )
        self.window._suppress_default_feedback = True
        self.personality = load_personality(assets_dir)
        self.ai_engine = CompanionAIEngine(config=self.agent_settings.llm_config)
        self.ai_engine.reply_ready.connect(self._on_ai_reply_ready)
        self.controller = BodyController(self.window)

        # 2. Slice Feeder & Chronicle Store (Storage & Retrieval Routing)
        self.store = SliceStore(jsonl_path)

        if self.flags.memory_v2_storage:
            self.v2_store: ChronicleStoreV2 | None = ChronicleStoreV2(db_path)
            self.exporter: JsonlSliceExporter | None = JsonlSliceExporter(jsonl_path)
            self.write_service: RawEvidenceWriteService | None = RawEvidenceWriteService(
                self.v2_store, exporter=self.exporter
            )
            self.router = RawEvidenceRouter(
                flags=self.flags,
                v1_store=None,
                v2_service=self.write_service,
            )
            self.compat_reader = CompatibilityReader(self.v2_store)
            self.chronicle: Any = V2ChronicleStoreAdapter(self.v2_store, self.compat_reader)
        else:
            self.v2_store = None
            self.exporter = None
            self.write_service = None
            self.router = RawEvidenceRouter(
                flags=self.flags,
                v1_store=None,
                v2_service=None,
            )
            self.chronicle = ChronicleStore(db_path)
            self.chronicle.import_slices_jsonl()

        # WP-7 & WP-8: Retrieval & Recall Gate
        if self.flags.memory_v2_retrieval and self.v2_store is not None:
            self.retrieval_repo: RetrievalRepository | None = RetrievalRepository(db_path)
            retrieval_cfg = RetrievalConfig(
                lexical_weight=0.6,
                surface_weight=0.4,
                confidence_threshold=0.16,
                rule_intent_boost=0.30,
                past_episode_boost=0.25,
                project_tech_boost=0.15,
                historical_superseded_boost=0.20,
                top_k=3,
            )
            self.retrieval_pipeline: TechnicalRetrievalPipeline | None = TechnicalRetrievalPipeline(
                self.retrieval_repo, config=retrieval_cfg
            )
            self.recall_gate: RecallGate | None = RecallGate(self.retrieval_pipeline)
            self.retriever: MemoryRetriever | None = None
        else:
            self.retrieval_repo = None
            self.retrieval_pipeline = None
            self.recall_gate = None
            self.retriever = MemoryRetriever(self.chronicle)

        # WP-5: Consolidation Scheduler
        if self.flags.memory_v2_consolidation and self.v2_store is not None:
            self.consolidation_scheduler: ConsolidationScheduler | None = ConsolidationScheduler(
                store=self.v2_store,
                db_path=db_path,
            )
            self.consolidation_scheduler.start()
        else:
            self.consolidation_scheduler = None

        # WP-6 / WP-9: Self-Model Slow Path & Chapter Repository
        if self.flags.memory_v2_self_model and self.v2_store is not None:
            self.self_model_service: SlowPathSelfModelService | None = SlowPathSelfModelService(
                self.v2_store
            )
            self.chapter_repo: ChapterRepository | None = ChapterRepository(
                self.v2_store, chapters_dir=chapters_dir
            )
        else:
            self.self_model_service = None
            self.chapter_repo = None

        self.chronicle_window = ChronicleViewerWindow(self.chronicle)
        self.overlay = self.window.feeder_bar
        self.window.slice_fed.connect(self._on_slice_submitted)
        self.window.user_replied_to_bubble.connect(self._on_user_reply_to_bubble)
        self._last_pet_speech: str = ""

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
        event_sink = (
            V2EventStoreAdapter(self.write_service)
            if (self.flags.memory_v2_storage and self.write_service is not None)
            else self.chronicle
        )
        self.bus = LocalEventBus(
            on_event_received=self._on_agent_event_received,
            store=event_sink,
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
            self.hotkey = GlobalHotkeyListener(spec, self.window.open_feeder_input)
            self.hotkey.start()
        except ValueError:
            self.hotkey = GlobalHotkeyListener(DEFAULT_FEEDER_HOTKEY, self.window.open_feeder_input)
            self.hotkey.start()

    def _on_hotkey_changed(self, spec: str) -> None:
        """Re-register the feeder hotkey in place, so a change needs no restart."""
        self.hotkey.stop()
        self.hotkey = GlobalHotkeyListener(spec, self.window.open_feeder_input)
        self.hotkey.start()
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
            if hasattr(self, "chronicle") and hasattr(self.chronicle, "prune"):
                self.chronicle.prune()
        except sqlite3.Error:
            # A locked database must not take the companion down; retry next interval.
            pass

    def _on_agent_event_received(self, event: AgentEvent) -> None:
        """Data Plane tap: record continuous activity and track busy/idle timing."""
        self.watcher.record_activity()
        if event.event_type in (AgentEventType.PRE_TOOL_USE, AgentEventType.USER_PROMPT):
            self._last_agent_active_at = datetime.now()
            if hasattr(self.window, "notify_user_working"):
                self.window.notify_user_working()

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
            if hasattr(self, "ai_engine") and hasattr(self, "personality"):
                is_late = getattr(self.watcher, "is_late_night", lambda: False)()
                cat = "state_care_late_night" if is_late else "state_care_overwork"
                ctx = "夜深了，用户仍在电脑前操作" if is_late else "用户已连续高负荷工作超3小时"
                self.ai_engine.request_reply(
                    ctx,
                    self.personality,
                    category=cat,
                    context_tag="state_care",
                )
            else:
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

        # ── 2. Work & Memory Group (打开足迹) ──
        archive_action = QAction("打开足迹", self.window)
        archive_action.triggered.connect(self._open_chronicle_archive)
        menu.addAction(archive_action)

        menu.addSeparator()

        # ── 3. Companion & Display Group ──
        switch_menu = menu.addMenu("切换伴生体")
        switch_menu.setStyleSheet(menu.styleSheet())
        available_pets = [
            ("🦦 Vasu (官方默认 · 小河獭)", "vasu"),
            ("🐱 Calico (三花小猫)", "calico"),
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

        # ── 3.5 Action Showcase / Testing Submenu ──
        test_menu = menu.addMenu("🧪 测试伴生体动作")
        test_menu.setStyleSheet(menu.styleSheet())

        action_labels: dict[str, str] = {
            "idle": "待机呼吸",
            "review": "代码复盘与深思",
            "waiting": "专注凝视等待",
            "running": "敏捷奔跑",
            "running-right": "向右欢快奔跑",
            "running-left": "向左欢快奔跑",
            "waving": "克制招手致意",
            "jumping": "欢快跳跃庆祝",
            "failed": "抱头受挫/沮丧",
            "working-typing": "专注敲键盘写代码",
            "working-building": "做木工锯木头",
            "working-sweeping": "小扫把打扫整理",
            "working-conducting": "挥舞指挥棒听音乐",
            "working-juggling": "抛彩球玩耍杂耍",
            "working-carrying": "搬运包裹箱子",
            "thinking": "托腮沉思构想",
            "yawning": "打个大大的哈欠",
            "dozing": "揉眼睛打瞌睡",
            "sleeping": "安详沉睡",
            "waking": "伸大懒腰坐起",
        }

        clean_actions = [
            k
            for k in self.window._loaded_sheets
            if not k.endswith("-flipped")
            and not k.startswith("react-")
            and k
            not in ("wave", "work", "think", "sleep", "yawn", "poke", "drag", "jump", "failed")
        ]
        # Ensure standard actions are present if in loaded sheets
        standard_candidates = (
            "review",
            "waiting",
            "running",
            "running-right",
            "running-left",
            "waving",
            "jumping",
            "failed",
        )
        for std in standard_candidates:
            if std in self.window._loaded_sheets and std not in clean_actions:
                clean_actions.append(std)
        ordered = ["idle"] + [k for k in clean_actions if k != "idle"]

        def _make_tester(act_id: str) -> Callable[[], None]:
            def _test() -> None:
                self.window.test_action(act_id)

            return _test

        for act in ordered:
            label_text = action_labels.get(act, act)
            sheet = self.window._loaded_sheets.get(act)
            f_count = sheet.frame_count if sheet else 0
            act_item = QAction(f"▶ {act} ({label_text} · {f_count}帧)", self.window)
            act_item.triggered.connect(_make_tester(act))
            test_menu.addAction(act_item)

        test_menu.addSeparator()
        stop_test_act = QAction("⏹ 退出测试，恢复自然节律", self.window)
        stop_test_act.triggered.connect(self.window.stop_action_test)
        test_menu.addAction(stop_test_act)
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

            def _sim_prompt() -> None:
                self.hermes.on_user_prompt("demo_session")
                self.controller.say("🤔 思考中：正在分析你的问题...", ttl_ms=3000)

            sim_prompt = QAction("1. 用户提问 (User Prompt → 思考)", self.window)
            sim_prompt.triggered.connect(_sim_prompt)
            sim_menu.addAction(sim_prompt)

            def _sim_tool() -> None:
                self.hermes.on_pre_tool_call("demo_session", "bash")
                self.controller.say("⚙️ 正在执行工具: bash", ttl_ms=2500)

            sim_tool = QAction("2. 调工具 (PreToolUse → 工作)", self.window)
            sim_tool.triggered.connect(_sim_tool)
            sim_menu.addAction(sim_tool)

            def _sim_err() -> None:
                self.hermes.on_tool_failure("demo_session", "bash", "SyntaxError")
                self.controller.say("⚠️ 工具报错: SyntaxError", ttl_ms=3000)

            sim_err = QAction("3. 工具报错 (ToolFailure → 报错)", self.window)
            sim_err.triggered.connect(_sim_err)
            sim_menu.addAction(sim_err)

            def _sim_done() -> None:
                self.hermes.on_task_complete("demo_session")
                self.controller.say("🎉 任务完成！所有检查通过！", ttl_ms=3000)

            sim_done = QAction("4. 任务完成 (TaskComplete → 开心)", self.window)
            sim_done.triggered.connect(_sim_done)
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

    def _on_ai_reply_ready(self, reply: str, tag: str) -> None:
        """Deliver AI or fallback generated response directly to the speech bubble."""
        if reply:
            self._last_pet_speech = reply
            self.controller.say(reply, ttl_ms=4000)

    def _recall_memories(
        self,
        text: str,
        *,
        limit: int = 3,
        exclude_ids: set[str] | None = None,
    ) -> tuple[str, ...]:
        """Extract relevant past memory snippets from ChronicleStore using MemoryRetriever or V2 Pipeline."""
        if (
            hasattr(self, "flags")
            and getattr(self.flags, "memory_v2_retrieval", False)
            and getattr(self, "recall_gate", None) is not None
            and getattr(self, "retrieval_pipeline", None) is not None
        ):
            from datetime import UTC, datetime

            from src.memory.v2.recall_gate import RecallContext
            from src.memory.v2.retrieval.models import RetrievalQueryContext

            q_ctx = RetrievalQueryContext(
                query_text=text,
                sanctuary_active=getattr(self.guard, "is_active", False),
                now=datetime.now(UTC),
            )
            retrieval_res = self.retrieval_pipeline.retrieve(q_ctx)
            recall_ctx = RecallContext(
                query_text=text,
                sanctuary_active=getattr(self.guard, "is_active", False),
                now=datetime.now(UTC),
                store=getattr(self, "v2_store", None),
            )
            decision = self.recall_gate.evaluate(retrieval_res, recall_ctx)
            return tuple(item.statement for item in decision.injection_context.items)

        if not hasattr(self, "retriever") or self.retriever is None:
            if hasattr(self, "chronicle") and self.chronicle is not None:
                self.retriever = MemoryRetriever(self.chronicle)
            else:
                return ()
        return self.retriever.recall(text, limit=limit, exclude_ids=exclude_ids)

    def _on_user_reply_to_bubble(self, reply_text: str, orig_pet_speech: str) -> None:
        """Handle user's direct reply to a message the pet said."""
        is_distressed = self.guard.evaluate_text(reply_text)
        mood = "frustrated" if is_distressed else "neutral"

        # 1. Save to chronicle
        if hasattr(self, "write_service") and self.write_service is not None:
            write_res = self.write_service.write_slice(
                WriteSliceCommand(
                    content=reply_text,
                    source="manual_feed",
                    scope="unresolved",
                )
            )
            exclude_ids = {write_res.entity.slice_id}
        else:
            slice_item = RawSlice.create(reply_text, mood_flag=mood)
            self.store.save(slice_item)
            self.chronicle.record_slice(
                SliceRecord(
                    id=slice_item.id,
                    timestamp=slice_item.timestamp,
                    content=slice_item.content,
                    mood_flag=slice_item.mood_flag,
                )
            )
            exclude_ids = {slice_item.id}

        # 2. Asynchronous reply with full two-way dialogue context
        memories = self._recall_memories(reply_text, limit=3, exclude_ids=exclude_ids)
        if is_distressed:
            self.controller.perform_action("rest")
            prompt_ctx = (
                f"伴生体刚才对用户说：'{orig_pet_speech}'\n用户心烦或受挫并回答：'{reply_text}'"
            )
            self.ai_engine.request_reply(
                prompt_ctx,
                self.personality,
                category="slice_distressed",
                context_tag="reply_distressed",
                memories=memories,
            )
        else:
            self.controller.perform_action("jump")
            prompt_ctx = f"伴生体刚才对用户说：'{orig_pet_speech}'\n用户回答道：'{reply_text}'"
            self.ai_engine.request_reply(
                prompt_ctx,
                self.personality,
                category="slice_normal",
                context_tag="reply_normal",
                memories=memories,
            )

    def _on_llm_config_changed(self, cfg: object) -> None:
        if isinstance(cfg, LLMConfig):
            self.ai_engine.update_config(cfg)

    def _on_pet_clicked(self) -> None:
        """Left clicking the pet shows a small status acknowledgment."""
        if self.guard.is_active:
            self.controller.say("（安静地陪着你）", ttl_ms=2500)
        else:
            self.ai_engine.request_reply(
                "用户轻戳了你的身体向你打招呼",
                self.personality,
                category="poke",
                context_tag="poke",
            )

    def _on_slice_submitted(self, text: str) -> None:
        """Handle incoming slice from overlay."""
        is_distressed = self.guard.evaluate_text(text)
        mood = "frustrated" if is_distressed else "neutral"

        # 1. Save to disk
        if hasattr(self, "write_service") and self.write_service is not None:
            write_res = self.write_service.write_slice(
                WriteSliceCommand(
                    content=text,
                    source="manual_feed",
                    scope="unresolved",
                )
            )
            exclude_ids = {write_res.entity.slice_id}
        else:
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
            exclude_ids = {slice_item.id}

        # 2. Check Sanctuary mode
        memories = self._recall_memories(text, limit=3, exclude_ids=exclude_ids)
        if is_distressed:
            # AC-4: Enter Sanctuary mode with a gentle, non-preaching acknowledgment bubble
            self.controller.perform_action("rest")
            ctx = (
                f"伴生体刚才说：'{self._last_pet_speech}'\n用户心烦或受挫并回复：'{text}'"
                if self._last_pet_speech
                else f"用户心烦受挫/死磕遇到阻力：'{text}'"
            )
            self.ai_engine.request_reply(
                ctx,
                self.personality,
                category="slice_distressed",
                context_tag="slice_distressed",
                memories=memories,
            )
        else:
            # AC-3: Acknowledge normal slice with gentle confirmation
            self.controller.perform_action("jump")
            ctx = (
                f"伴生体刚才说：'{self._last_pet_speech}'\n用户回复/交流道：'{text}'"
                if self._last_pet_speech
                else f"用户随手记下想法或与你交流：'{text}'"
            )
            self.ai_engine.request_reply(
                ctx,
                self.personality,
                category="slice_normal",
                context_tag="slice_normal",
                memories=memories,
            )

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
            self.personality = load_personality(pet_dir)
            cur_idle = self.window._loaded_sheets.get("idle")
            if cur_idle and cur_idle.frames:
                self.tray.setIcon(QIcon(cur_idle.frames[0]))
            names = {
                "vasu": "Vasu (小河獭)",
                "calico": "Calico (三花小猫)",
            }
            display_name = names.get(pet_id, pet_id)
            self.controller.say(f"伴生体已切换为 {display_name}")

    def _on_quit(self) -> None:
        if getattr(self, "consolidation_scheduler", None) is not None:
            try:
                self.consolidation_scheduler.stop()
            except Exception:
                pass
        if getattr(self, "retrieval_repo", None) is not None:
            try:
                self.retrieval_repo.close()
            except Exception:
                pass
        if getattr(self, "v2_store", None) is not None:
            try:
                self.v2_store.close()
            except Exception:
                pass
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
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone(1500)
        self.app.quit()

    def _on_scale_changed(self, scale: float) -> None:
        """Handle pet scale adjustments from Settings or Tray."""
        self.window.set_scale(scale)
        percent = int(round(scale * 100))
        self.controller.say(f"🔍 伴生体大小已调整为 {percent}%", ttl_ms=1800)

    def _on_action_test_requested(self, act_id: str) -> None:
        """Handle action test trigger from Settings Window."""
        if act_id == "STOP":
            self.window.stop_action_test()
        else:
            self.window.test_action(act_id)

    def run(self) -> int:
        self.window.show()
        return self.app.exec()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Coeva Co-evolving AI Companion")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Explicit production data directory (overrides default/env)",
    )
    args, _ = parser.parse_known_args(argv)
    companion = CompanionApp(data_dir=args.data_dir)
    return companion.run()


if __name__ == "__main__":
    sys.exit(main())
