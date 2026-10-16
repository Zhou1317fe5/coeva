"""Attribution Gate: classifies agent events into evidence provenance tiers.

This is the only place where the Phase 2 invariant "Agent Behavior != User Behavior"
(see docs/specs/phase-2-chronicle-and-growth-chapters/SPEC.md, section 2.2) becomes code.

Pure function, no state, no I/O, no LLM.
"""

from __future__ import annotations

from enum import StrEnum

from src.connectors.contracts import AgentEventType


class Provenance(StrEnum):
    """How much attribution weight an evidence record carries."""

    USER_EXPLICIT = "user_explicit"  # user's own words (manual slice)
    USER_ACTION = "user_action"  # a user-initiated decision, content not captured
    AGENT_CONTEXT = "agent_context"  # agent-autonomous activity: context only


class RetentionClass(StrEnum):
    """How long an evidence record is kept before `prune()` may drop it."""

    DURABLE = "durable"  # never pruned
    TRANSIENT = "transient"  # pruned after the TTL


def classify(event_type: str) -> tuple[Provenance, RetentionClass]:
    """Map an agent event type to its provenance and retention class.

    Only `user_prompt` carries user attribution; every other event type -- including
    any type not yet known to this build -- is agent context. Unknown types fall to
    the *conservative* branch on purpose: a new connector event must never be granted
    user attribution by accident.
    """
    if event_type == AgentEventType.USER_PROMPT:
        return Provenance.USER_ACTION, RetentionClass.DURABLE
    return Provenance.AGENT_CONTEXT, RetentionClass.TRANSIENT
