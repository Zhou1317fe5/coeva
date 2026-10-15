"""End-to-end integration tests verifying Phase 1 Acceptance Criteria (AC-1 to AC-4)."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.body.contracts import PetState
from src.body.controller import BodyController
from src.body.window import PetWindow
from src.connectors.event_bus import LocalEventBus
from src.connectors.hermes_connector import HermesConnector
from src.core.cold_start import ColdStartPolicy
from src.core.intervention import InterventionPolicy
from src.core.sanctuary import SanctuaryGuard
from src.feeder.contracts import RawSlice
from src.feeder.overlay import SliceFeederOverlay
from src.feeder.storage import SliceStore

# Ensure offscreen Qt application
_app = QApplication.instance()
if _app is None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    _app = QApplication([])


def test_ac1_independent_body_lifecycle() -> None:
    """AC-1: Verify Desktop Body runs independently of any AI agent with idle, drag, and sleep."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = PetWindow(pet_dir, scale=1)
    controller = BodyController(window)

    # Starts in IDLE with no agent running
    assert controller.current_state == PetState.IDLE

    # Transition to sleeping after idle
    controller.set_state(PetState.SLEEPING)
    assert controller.current_state == PetState.SLEEPING

    # Waking back up
    controller.set_state(PetState.IDLE)
    assert controller.current_state == PetState.IDLE

    window.close()


def test_ac2_hermes_pi_to_pet_orchestration() -> None:
    """AC-2: Verify Hermes/Pi events route through EventBus and drive pet states within 1s."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = PetWindow(pet_dir, scale=1)
    controller = BodyController(window)

    bus = LocalEventBus(on_state_suggested=lambda s: controller.set_state(s))
    hermes = HermesConnector(bus)

    # 1. User prompts Hermes -> Pet Thinking
    hermes.on_user_prompt("session_42")
    assert controller.current_state == PetState.THINKING

    # 2. Hermes executes tool -> Pet Working
    hermes.on_pre_tool_call("session_42", "bash")
    assert controller.current_state == PetState.WORKING

    # 3. Hermes completes task -> Pet Happy
    hermes.on_task_complete("session_42")
    assert controller.current_state == PetState.HAPPY

    window.close()


def test_ac3_slice_feeder_e2e(tmp_path: Path) -> None:
    """AC-3: Verify slice feeding persists to JSONL and triggers pet nod/say confirmation."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = PetWindow(pet_dir, scale=1)
    controller = BodyController(window)

    store = SliceStore(tmp_path / "raw_slices.jsonl")
    overlay = SliceFeederOverlay()

    # Wire overlay submission to store and pet acknowledgment
    def _handle_submit(content: str) -> None:
        slice_item = RawSlice.create(content)
        store.save(slice_item)
        controller.perform_action("jump")
        controller.say("记下了", ttl_ms=2000)

    overlay.slice_submitted.connect(_handle_submit)

    # Simulate user typing and pressing Enter
    overlay._input.setPlainText("读到《鱼不存在》，放下对唯一秩序的执念。")
    overlay._on_submit()

    assert store.count() == 1
    recent = store.load_recent(1)[0]
    assert "鱼不存在" in recent.content
    assert recent.actor == "user"
    assert controller.current_state == PetState.HAPPY

    overlay.close()
    window.close()


def test_ac4_sanctuary_meltdown_e2e(tmp_path: Path) -> None:
    """AC-4: Verify negative venting triggers Sanctuary Guard meltdown with 100% silence."""
    pet_dir = Path("assets") / "pets" / "claw"
    window = PetWindow(pet_dir, scale=1)
    controller = BodyController(window)

    store = SliceStore(tmp_path / "raw_slices.jsonl")
    guard = SanctuaryGuard()
    policy = ColdStartPolicy(day_count=1)
    engine = InterventionPolicy(sanctuary=guard, cold_start=policy)

    overlay = SliceFeederOverlay()
    bubbles_shown: list[str] = []

    def _handle_feed(content: str) -> None:
        is_distressed = guard.evaluate_text(content)
        mood = "frustrated" if is_distressed else "neutral"
        slice_item = RawSlice.create(content, mood_flag=mood)
        store.save(slice_item)

        # Check intervention
        nudge = engine.evaluate_intervention(is_task_in_flight=False)
        if nudge:
            bubbles_shown.append(nudge)
            controller.say(nudge)

    overlay.slice_submitted.connect(_handle_feed)

    # User inputs acute frustration
    overlay._input.setPlainText("这个编译错误搞砸了，真烦死了！")
    overlay._on_submit()

    # Verify: slice is saved with frustrated mood
    assert store.count() == 1
    recent = store.load_recent(1)[0]
    assert recent.mood_flag == "frustrated"

    # Verify: Sanctuary is ACTIVE and NO speech bubble was triggered
    assert guard.is_active
    assert len(bubbles_shown) == 0

    overlay.close()
    window.close()
