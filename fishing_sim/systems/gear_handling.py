"""Small deterministic helpers for Phase 6 longline gear wear and loading.

Kept independent of Pygame so the friction-drum/roller rules can be tested quickly.
"""

ROLLER_WORKING = "working"
ROLLER_BYPASSED = "bypassed"
ROLLER_JAMMED = "jammed"


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def roller_friction_multiplier(state):
    """Relative mainline chafe while gear passes the stern roller/bulwark."""
    return {
        ROLLER_WORKING: 1.0,
        ROLLER_BYPASSED: 5.0,
        ROLLER_JAMMED: 8.0,
    }.get(state, 1.0)


def line_wear_per_second(load, roller_state):
    """Persistent mainline condition loss per second, scaled by line load."""
    load = clamp(float(load), 0.0, 1.8)
    return (0.0025 + 0.0040 * load) * roller_friction_multiplier(roller_state)


def roller_snag_rate(load, roller_state, roller_condition=100.0):
    """Accumulation rate toward a short snag (meter units per simulation-second)."""
    load = clamp(float(load), 0.0, 1.8)
    condition = clamp(float(roller_condition), 0.0, 100.0) / 100.0
    if roller_state == ROLLER_BYPASSED:
        return 0.055 + 0.035 * load
    if roller_state == ROLLER_JAMMED:
        return 0.10 + 0.045 * load
    # A well-maintained working roller almost never snags; a worn roller becomes risky.
    return 0.003 + 0.035 * (1.0 - condition) ** 1.6 * (0.4 + load)


def calculate_hauler_slip(load, engine_power, working_hands, drum_condition=100.0):
    """Return 0..1 friction-drum slip from excessive line load / weak drive.

    Engine torque, healthy drum friction and crew assisting the winch all increase
    available pulling capacity. The function deliberately returns a smooth ramp
    instead of an all-or-nothing stop.
    """
    load = clamp(float(load), 0.0, 1.8)
    engine_power = clamp(float(engine_power), 0.0, 1.0)
    hands = clamp(float(working_hands), 0.0, 2.0)
    condition = clamp(float(drum_condition), 0.0, 100.0) / 100.0
    capacity = 0.28 + 0.58 * engine_power + 0.095 * hands + 0.17 * condition
    return clamp((load - capacity) / 0.72, 0.0, 1.0)
