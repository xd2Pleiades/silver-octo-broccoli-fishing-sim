"""Pure policy helpers for dockside recovery and shore-party recall.

Kept independent of Pygame so the shore-leave rules can be regression-tested
without starting the graphical simulator.
"""
from __future__ import annotations


READY_HEALTH = 0.98
READY_FATIGUE = 0.10
READY_MORALE = 0.95


def shore_recovery_ready(sailor) -> bool:
    """Return whether a sailor has recovered enough to automatically re-embark."""
    return (
        sailor.health >= READY_HEALTH
        and sailor.fatigue <= READY_FATIGUE
        and sailor.morale >= READY_MORALE
    )


def returning_shore_crew(sailors, shore_mode):
    """Select only shore crew who have not been explicitly marked KEEP ASHORE."""
    return [
        sailor for sailor in sailors
        if sailor.mode == shore_mode and not getattr(sailor, "keep_ashore", False)
    ]


def shore_status_label(sailor, shore_mode) -> str:
    """Compact roster status that distinguishes recovery from a deliberate holdback."""
    if sailor.mode != shore_mode:
        return "NOT ASHORE"
    if getattr(sailor, "keep_ashore", False):
        return "KEEP ASHORE"
    return "READY" if shore_recovery_ready(sailor) else "RECOVERING"
