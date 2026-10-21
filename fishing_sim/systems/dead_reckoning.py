"""Headless dead-reckoning helpers for V13V1-04.

The physical vessel position remains the simulation's source of truth. These
helpers calculate only the crew's estimated motion and displayed uncertainty;
they never mutate the ship or any physics state.
"""
from __future__ import annotations

import math

BASE_ERROR_UNITS_PER_MINUTE = 10.0
COMPASS_BIAS_SIGMA = 0.005
LOG_BIAS_SIGMA = 0.0005
BIAS_REGRESSION = 0.02
MAX_COMPASS_BIAS = math.radians(2.0)
MAX_LOG_BIAS = 0.02
TAU = math.tau


def _clamp(value, low, high):
    return max(low, min(high, value))


def evolve_biases(compass_bias, log_bias, dt, rng):
    """Advance the slowly varying compass/log errors using the plan's model.

    ``rng`` must expose ``gauss(mean, sigma)`` (the random module or a seeded
    ``random.Random`` both work). Biases are clamped to the plan's plausible
    bounds so a long session cannot create an unbounded numerical runaway.
    """
    dt = max(0.0, float(dt))
    if dt <= 0.0:
        return float(compass_bias), float(log_bias)
    regression = math.exp(-BIAS_REGRESSION * dt)
    compass = (float(compass_bias) + rng.gauss(0.0, COMPASS_BIAS_SIGMA) * dt) * regression
    log = (float(log_bias) + rng.gauss(0.0, LOG_BIAS_SIGMA) * dt) * regression
    return (
        _clamp(compass, -MAX_COMPASS_BIAS, MAX_COMPASS_BIAS),
        _clamp(log, -MAX_LOG_BIAS, MAX_LOG_BIAS),
    )


def advance_belief(x, y, true_heading, true_speed, dt, compass_bias, log_bias):
    """Return estimated x/y, heading, and speed for one motion interval."""
    dt = max(0.0, float(dt))
    estimated_heading = (float(true_heading) + float(compass_bias)) % TAU
    estimated_speed = max(0.0, float(true_speed) * (1.0 + float(log_bias)))
    distance = estimated_speed * dt
    return (
        float(x) + math.cos(estimated_heading) * distance,
        float(y) + math.sin(estimated_heading) * distance,
        estimated_heading,
        estimated_speed,
    )


def dr_error_rate(skill, sea_state, daylight, fog, rain):
    """Expected position uncertainty growth, in world units per game second."""
    skill = _clamp(float(skill), 0.0, 1.0)
    sea_state = _clamp(float(sea_state), 0.0, 1.0)
    daylight = _clamp(float(daylight), 0.0, 1.0)
    fog = _clamp(float(fog), 0.0, 1.0)
    rain = _clamp(float(rain), 0.0, 1.0)
    skill_factor = 2.0 - skill
    sea_factor = 1.0 + sea_state
    night_factor = 2.0 if daylight < 0.3 else 1.0
    weather_factor = 1.0 + 2.0 * fog + 0.5 * rain
    return (BASE_ERROR_UNITS_PER_MINUTE / 60.0) * skill_factor * sea_factor * night_factor * weather_factor


def format_fix_age(age_seconds):
    """Format elapsed game time since the last known-position fix."""
    seconds = max(0, int(age_seconds))
    if seconds >= 3600:
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        return "%dh%02dm" % (hours, minutes)
    if seconds >= 60:
        minutes, seconds = divmod(seconds, 60)
        return "%dm%02ds" % (minutes, seconds)
    return "%ds" % seconds
