"""Camera-level and peek helpers.

Camera behavior is currently owned by Game because view state, sailor selection,
and climbing input are tightly coupled. This module provides the stable enum/API
surface while preserving the original input semantics.
"""
from fishing_sim.core.game import Level

def peek_level(current_level, direction):
    """Return the adjacent visible level, bounded to the ship's three decks."""
    return Level(max(int(Level.BELOW), min(int(Level.WHEELHOUSE),
                                          int(current_level) + (1 if direction > 0 else -1))))
