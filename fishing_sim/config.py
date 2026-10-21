"""Shared configuration and compatibility exports.

The original prototype's rendering constants remain defined in core.game to preserve
runtime compatibility; this module exposes the stable public configuration surface.
"""
import math
from pygame import (
    K_COMMA as KEY_SEA_DOWN, K_PERIOD as KEY_SEA_UP,
    K_q as KEY_ELEV_UP, K_e as KEY_ELEV_DOWN,
)
from fishing_sim.core.game import (
    W, H, MIN_W, MIN_H, WORLD_SCALE, HARBOUR, TAU, LAYOUT,
    GRADES, AIR_TEMP, ICE_CAP, ICE_PRICE, SPECIES, DAY_LEN, START_HOUR,
    DEPTH_M, SLACK_MIN, SLACK_MAX, ECO, HABITAT, BAITS, BAIT_AFF,
    BAIT_CAP, BAIT_FILL, FUEL_CAP, FUEL_PRICE, GAFFS, GAFF_PRICE, TOW_FEE,
    clamp, lerp, smoothstep, lerp_angle, mix, hexc, closest_on_seg, in_poly,
    hash01, rect_has, thick_polyline,
)
RADIO_MAX_RANGE_NM = 120.0
RADIO_NOISE_FLOOR = 0.15
