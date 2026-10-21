"""Session-long fishing gut-book records (V13V1-14).

Each entry snapshots the crew's believed plot when the first lookout becomes
confident. Memories survive a school's expiry and later navigation fixes; they
are historical notes, not a live view of hidden fish positions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from fishing_sim.systems.hotspots import estimated_hotspot_destination

MAX_GUT_BOOK_ENTRIES = 100
GUT_BOOK_CONFIDENCE_THRESHOLD = 0.5


def believed_chart_position(spot_position, position_error, scale: float) -> tuple[float, float]:
    """Return the crew's chart plot (design units), not the physical school position."""
    safe_scale = max(0.001, float(scale))
    x, y = estimated_hotspot_destination(spot_position, position_error)
    return float(x) / safe_scale, float(y) / safe_scale


@dataclass
class GutBookEntry:
    entry_id: int
    date: str
    clock: str
    elapsed: float
    sailor: str
    skill: float
    species_guess: str
    x: float
    y: float
    confidence: float
    strength: float
    # In-session identity only; never rendered or compared as data.
    hotspot_ref: Any = field(default=None, repr=False, compare=False)

    @property
    def chart_position(self) -> tuple[float, float]:
        return self.x, self.y


def entry_is_active(entry: GutBookEntry, live_hotspots: Iterable[Any]) -> bool:
    """Whether this historical note's original school is still in the live set."""
    ref = getattr(entry, "hotspot_ref", None)
    return ref is not None and any(spot is ref for spot in live_hotspots)
