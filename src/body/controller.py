"""BodyController implementing the Body Control Contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.body.contracts import PetState

if TYPE_CHECKING:
    from src.body.window import PetWindow

# Body Control Contract action vocabulary, plus the state names the PI-Desktop
# panel sends. The panel used to post `thinking` / `working` / `celebrating`,
# none of which the controller knew, so three of its four buttons silently did
# nothing but fall back to IDLE. Unknown ids are a contract violation, and
# `tests/test_body.py` fails when the panel and this table drift apart.
ACTION_STATES: dict[str, PetState] = {
    "jump": PetState.HAPPY,
    "wave": PetState.HAPPY,
    "celebrating": PetState.HAPPY,
    "work": PetState.WORKING,
    "working": PetState.WORKING,
    "think": PetState.THINKING,
    "thinking": PetState.THINKING,
    "error": PetState.ERROR,
    "sleep": PetState.SLEEPING,
    "rest": PetState.IDLE,
    "idle": PetState.IDLE,
}


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
        target_state = ACTION_STATES.get(action_id.lower(), PetState.IDLE)
        self.set_state(target_state)
