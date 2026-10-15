"""Contracts and data models for Desktop Body."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PetState(StrEnum):
    """Core animated states for the desktop companion."""

    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    HAPPY = "happy"
    ERROR = "error"
    SLEEPING = "sleeping"
    WAITING = "waiting"


@dataclass(frozen=True)
class SpeechBubbleRequest:
    """Request to display a speech bubble above the pet."""

    text: str
    ttl_ms: int = 4000
    priority: int = 1


@dataclass(frozen=True)
class PetWindowConfig:
    """Layout and display configuration for the pet window."""

    scale: int = 2
    default_x: int = -1
    default_y: int = -1
    click_through: bool = True
