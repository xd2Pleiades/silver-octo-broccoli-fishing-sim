"""Fallible-helmsman, rudder-lag, and old-fashioned engine-telegraph helpers."""
from __future__ import annotations

import math

TELEGRAPH_ORDERS = (
    (-1, "ASTERN"),
    (0, "STOP"),
    (1, "SLOW AHEAD"),
    (2, "HALF AHEAD"),
    (3, "FULL AHEAD"),
)


def shortest_angle(target: float, current: float) -> float:
    return (float(target) - float(current) + math.pi) % (2.0 * math.pi) - math.pi


def engine_order_label(throttle: float, prop_direction: int = 1,
                       reversing: bool = False) -> str:
    """Describe the telegraph order instead of exposing a throttle percentage."""
    if reversing:
        return "REVERSING — WAIT"
    if int(prop_direction) < 0:
        return "ASTERN" if float(throttle) > 0.035 else "STOP / ASTERN"
    level = max(0.0, min(1.0, float(throttle)))
    if level < 0.06:
        return "STOP"
    if level < 0.34:
        return "SLOW AHEAD"
    if level < 0.72:
        return "HALF AHEAD"
    return "FULL AHEAD"


def rudder_step(current: float, command: float, dt: float,
                rate_per_second: float = 0.72) -> float:
    """Move rudder toward its demanded angle at a finite mechanical rate."""
    now = max(-1.0, min(1.0, float(current)))
    wanted = max(-1.0, min(1.0, float(command)))
    step = max(0.0, float(dt)) * max(0.0, float(rate_per_second))
    if wanted > now:
        return min(wanted, now + step)
    return max(wanted, now - step)


def desired_track_heading(leg_heading: float, cross_track: float,
                          lookahead: float, skill: float,
                          elapsed_time: float = 0.0) -> float:
    """Aim down the desired track while correcting cross-track error imperfectly.

    A skilled helmsman corrects more decisively and has less natural wander; a poor
    hand oscillates slightly and may leave a steady residual offset.  The track is
    still only a reference: motion/current can and will carry the vessel off it.
    """
    skill = max(0.0, min(1.0, float(skill)))
    lookahead = max(1.0, float(lookahead))
    correction_strength = 0.62 + 0.72 * skill
    correction = math.atan2(float(cross_track) * correction_strength, lookahead)
    wander_amp = 0.008 + 0.045 * (1.0 - skill)
    wander = math.sin(float(elapsed_time) * (0.45 + 0.30 * (1.0 - skill))) * wander_amp
    return float(leg_heading) - correction + wander


def predicted_turn_arc(start, heading: float, desired_heading: float,
                       speed: float, turn_rate: float, *, dt: float = 0.18,
                       duration: float = 4.0, max_points: int = 28) -> list[tuple[float, float]]:
    """Predict a short turn path for UI feedback (not as a physics rail)."""
    x, y = float(start[0]), float(start[1])
    angle = float(heading)
    points = [(x, y)]
    step = max(0.04, float(dt))
    count = min(max(2, int(max_points)), max(2, int(max(0.0, duration) / step)))
    velocity = max(0.0, float(speed))
    max_turn = max(0.01, float(turn_rate))
    for _ in range(count):
        diff = shortest_angle(desired_heading, angle)
        angle += max(-max_turn * step, min(max_turn * step, diff))
        x += math.cos(angle) * velocity * step
        y += math.sin(angle) * velocity * step
        points.append((x, y))
        if abs(diff) < 0.035:
            # Continue a brief straight projection to make the arc readable.
            for _ in range(3):
                x += math.cos(angle) * velocity * step
                y += math.sin(angle) * velocity * step
                points.append((x, y))
            break
    return points
