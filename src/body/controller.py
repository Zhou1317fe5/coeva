"""BodyController implementing the Body Control Contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.body.contracts import PetState

if TYPE_CHECKING:
    from src.body.window import PetWindow


class BodyController:
    """Controller exposing high-level commands to control the pet body."""

    def __init__(self, window: PetWindow) -> None:
        self._window = window

    @property
    def current_state(self) -> PetState:
        return self._window.current_state

    def set_state(self, state: str | PetState) -> None:
        """Update the pet's animation state."""
        if isinstance(state, str):
            try:
                state = PetState(state.lower())
            except ValueError:
                state = PetState.IDLE
        self._window.apply_state(state)

    def say(self, text: str, *, ttl_ms: int = 4000) -> None:
        """Display an unobtrusive speech bubble above the pet."""
        clean_text = text.strip()
        if clean_text:
            self._window.say(clean_text, ttl_ms=ttl_ms)

    def perform_action(self, action_id: str) -> None:
        """Trigger a specific one-shot or sustained action."""
        action_map = {
            "jump": PetState.HAPPY,
            "wave": PetState.HAPPY,
            "work": PetState.WORKING,
            "think": PetState.THINKING,
            "error": PetState.ERROR,
            "sleep": PetState.SLEEPING,
            "rest": PetState.IDLE,
        }
        target_state = action_map.get(action_id.lower(), PetState.IDLE)
        self.set_state(target_state)
