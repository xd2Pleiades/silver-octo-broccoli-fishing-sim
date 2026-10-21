"""Pure decision rules for stranded-vessel tow assistance. No Pygame dependency."""
from __future__ import annotations


def is_unpowered_adrift(
    *,
    speed_through_water: float,
    engine_on: bool,
    engine_ok: bool,
    engine_power: float,
    fuel: float,
    anchor_deployed: bool,
    docked: bool,
    tow_in_transit: bool,
    speed_threshold: float = 8.0,
) -> bool:
    """Return whether no-propulsion, near-zero STW should accrue tow time.

    Ground movement is deliberately not an input: sea current and wind may move
    the hull without giving it useful way on or preventing a tow request.
    """
    no_propulsion = (
        not bool(engine_on)
        or not bool(engine_ok)
        or float(engine_power) <= 0.01
        or float(fuel) <= 0.0
    )
    return bool(
        not docked
        and not tow_in_transit
        and not anchor_deployed
        and no_propulsion
        and max(0.0, float(speed_through_water)) < max(0.0, float(speed_threshold))
    )


def tow_long_range_response_probability(
    *, distance: float, max_range: float, clarity: float, interference: float, failed_calls: int
) -> float:
    """Nonzero, escalating probability of a long-range tow call reaching a listener.

    Repeated unanswered calls raise the response pressure, capped to avoid an
    instant guarantee. Distance, operator/radio clarity, and weather still matter.
    A 4% safety floor replaces the old 0.4% floor, which could leave callers
    waiting many in-game days at offshore distances.
    """
    max_range = max(1.0, float(max_range))
    distance = max(0.0, float(distance))
    clarity = min(1.0, max(0.05, float(clarity)))
    interference = min(1.0, max(0.0, float(interference)))
    failed_calls = max(0, int(failed_calls))
    long_range_fade = (max_range / max(distance, max_range)) ** 1.5
    response_pressure = min(0.40, 0.12 + 0.035 * failed_calls)
    range_factor = 0.35 + 0.65 * long_range_fade
    raw_chance = response_pressure * clarity * range_factor - interference * 0.015
    return min(0.25, max(0.04, raw_chance))
