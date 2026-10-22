#!/usr/bin/env python3
"""
Japanese Deep Sea Fishing Simulator 1962  --  single-file prototype
Requires:  pip install pygame
Run:       python fishing_sim.py

Hauling: when a big fish is alongside the hauler fights it. The crew work the brake on their own;
hold  Z  to ease off and  X  to tighten if you want to take it yourself.
D = autodock (sail to the quay, auction and pay).  Day and night turn on their own.
Longline: the line is a physical rope that sags with the slack you give it ( [ and ] ), hooks hang at real depths,
and what bites depends on depth, water temperature, the hour and the bait (K).  A tired fish is gaffed at the rail
(hold G to heave).  Fuel, bait and gaffs cost money; Y toggles safety harnesses for the open stern and hauler rail.
Weather rolls in (W changes it): wind builds the sea, rain soaks the deck, fog hides the coast, storms flash and rumble.
Each species (albacore, yellowfin, bigeye, swordfish, blue shark) has its own sprite.
The harbour town (market, ice house, school, shrine, boatyard, paddies and hills) lines the coast; its lamps and windows glow at night.
"""
import heapq
import math
import random
import re
from collections import OrderedDict
from functools import lru_cache
from enum import IntEnum
import sys
from pathlib import Path

import pygame
from pygame.math import Vector2 as V

from fishing_sim.systems.radio import RadioSystem
from fishing_sim.systems.broadcasts import (
    BroadcastDirector, BroadcastConversation, BroadcastTurn, PRIORITY_LOW, PRIORITY_MEDIUM, PRIORITY_HIGH, PRIORITY_CRITICAL,
)
from fishing_sim.systems.almanac import (
    START_DATE, forecast_for_date, forecast_range, game_date, season_name, season_note,
    HAKODATE_MEAN_TEMP_C,
)
from fishing_sim.systems.market_weather import add_storm_surge, decay_storm_surge, storm_price_index
from fishing_sim.systems.shore_leave import (
    shore_recovery_ready, returning_shore_crew, shore_status_label,
)
from fishing_sim.systems.sea_foam import SeaFoamSystem, world_to_view
from fishing_sim.systems.sea_interaction import (
    HullWaveInteraction, RippleSystem, FloodingModel, deck_to_world,
)
from fishing_sim.systems.hotspots import (
    HOTSPOT_SPECIES, MAX_ACTIVE_HOTSPOTS, AUTO_HUNT_MIN_STRENGTH,
    Hotspot, find_spawn_position, hotspot_multiplier,
    select_detected_hotspot, estimated_hotspot_destination,
)
from fishing_sim.systems.fishing_reports import (
    FishingSpotReport, create_fishing_report, report_map_color, MAX_CHART_REPORTS,
)
from fishing_sim.systems.fishing_gut_book import (
    GutBookEntry, MAX_GUT_BOOK_ENTRIES, GUT_BOOK_CONFIDENCE_THRESHOLD,
    believed_chart_position, entry_is_active,
)
from fishing_sim.systems.marine_collisions import (
    resolve_circle_polygon, resolve_circle_segment, route_around_rect,
)
from fishing_sim.systems.gear_handling import (
    ROLLER_WORKING, ROLLER_BYPASSED, ROLLER_JAMMED,
    calculate_hauler_slip, line_wear_per_second, roller_snag_rate,
)
from fishing_sim.systems.hotspot_visuals import (
    flotsam_visible, follow_bird_count, lookout_confidence_rate, lookout_detection_range,
    ripples_visible, screen_edge_intersection, working_bird_count,
    working_bird_half_span, working_bird_orbit_radius,
    slick_visible, baitfish_fleck_count, boil_count,
)
from fishing_sim.systems.seabirds import SeabirdFlock, sprite_frame, FLAP_FRAMES, FRAME_GLIDE, FRAME_FOLD
from fishing_sim.systems.dead_reckoning import (
    advance_belief, dr_error_rate, evolve_biases, format_fix_age,
)
from fishing_sim.systems.navigation_chart import (
    CHART_BOUNDS, CHART_PALETTE, KNOWN_AREA_RADIUS, chart_transform, chart_to_pixel,
    clamp_to_chart_bounds, clip_segment_to_bounds, generate_soundings, within_chart_bounds,
    pixel_to_chart, WaypointRoute, MAX_CHART_WAYPOINTS,
)
from fishing_sim.systems.navigation import (
    bearing_degrees, cross_track_error, eta_minutes, heading_radians, leg_metrics,
    world_units_per_nautical_mile,
)
from fishing_sim.systems.helm import (
    desired_track_heading, engine_order_label, rudder_step, shortest_angle,
)
from fishing_sim.systems.tow_assistance import (
    is_unpowered_adrift, tow_long_range_response_probability,
)
from fishing_sim.systems.tow_escort import (
    TowEscort, CHECKIN_INTERVAL, STALE_TOW_REPORT, DEPART_DELAY,
    LINE_RISK_SEA_STATE, TOW_ESCORT_SEPARATION_NM, TOW_ESCORT_HANDOVER_SECONDS,
    format_chart_position, dashed_segments, tow_intercept_position, lerp_chart_position,
)
from fishing_sim.ui.ocean_plot import (
    clamp_relative_distance, extend_edge_target, screen_to_relative,
    visibility_allows_ocean_plot,
)
from fishing_sim.systems.navigation_fixes import (
    assess_landmark_bearing, assess_sextant, assess_rdf, assess_echo_sounder,
    charted_depth_at, sample_position_error, sample_rdf_error,
)
from fishing_sim.systems.crew_reports import (
    report_bearing, report_distance, report_speed, bearing_difference_degrees,
    SECOND_OPINION_WINDOW_SECONDS,
)
from fishing_sim.diagnostics import (
    install_diagnostics, get_logger, log_event, set_active_context,
    write_exception_report, game_context_snapshot,
)
from fishing_sim.world.traffic import (
    AIShip, TrafficWorld, Activity as TrafficActivity,
    Archetype as TrafficArchetype, MOTHERSHIP_CLUSTER_CENTERS_NM,
)
from fishing_sim.world.coordinates import (
    HIGH_SEAS_PROJECTION, PHASE_A_PROJECTION, PHASE_B_BOUNDS_NM,
)
from fishing_sim.world.phase_adapter import (
    legacy_nm_to_phase_b_nm, phase_b_nm_to_legacy_nm,
    legacy_design_to_phase_b_nm, phase_b_nm_to_legacy_design,
    phase_b_legacy_design_bounds, phase_b_chart_bounds,
)
from fishing_sim.world.weather_grid import WeatherGrid
from fishing_sim.world.career_save import (
    build_envelope as build_career_save_envelope,
    validate_envelope as validate_career_save_envelope,
    atomic_write as atomic_write_career_save,
    read_envelope as read_career_save_envelope,
)
from fishing_sim.systems.ship_radio import ShipRadioService, RadioExchange
from fishing_sim.systems.distress_dispatcher import DistressDispatcher
from fishing_sim.systems.rescue_missions import PlayerRescueMissionManager, RESCUE_ON_SCENE_RADIUS_NM
from fishing_sim.systems.ai_rescue import AIDistressResponseManager
from fishing_sim.systems.ambient_ship_radio import AmbientShipRadioDirector
from fishing_sim.systems.relationship_dynamics import RelationshipDynamics

W, H = 1280, 800                 # default size; the window is resizable and these follow it
MIN_W, MIN_H = 640, 420
CENTER = V(W / 2, H / 2)
WORLD_SCALE = 3.0
HARBOUR = V(0, 0)
TAU = math.tau


# ------------------------------------------------------------------ helpers

def clamp(x, a, b):
    return max(a, min(b, x))


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(a, b, x):
    t = clamp((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp_angle(a, b, t):
    d = (b - a + math.pi) % TAU - math.pi
    return a + d * t


def mix(c1, c2, t):
    return tuple(int(lerp(x, y, t)) for x, y in zip(c1, c2))


def hexc(s, a=None):
    s = s.lstrip("#")
    c = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    return c if a is None else c + (a,)


def closest_on_seg(p, a, b):
    ab = b - a
    l2 = ab.length_squared()
    if l2 == 0:
        return V(a)
    return a + ab * clamp((p - a).dot(ab) / l2, 0.0, 1.0)


def in_poly(p, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        a, b = poly[i], poly[j]
        if (a.y > p.y) != (b.y > p.y) and p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x:
            inside = not inside
        j = i
    return inside


def hash01(x, y, salt):
    n = (x * 374761393 + y * 668265263 + salt * 2147483647) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    n ^= n >> 16
    return (n & 0xFFFFFF) / 0xFFFFFF


@lru_cache(maxsize=8192)
def _foam_seeded(seed, index, salt=0):
    """Cache deterministic foam texture values; they do not change after spawn."""
    n = math.sin(seed * 0.000173 + index * 17.173 + salt * 91.719) * 43758.5453
    return n - math.floor(n)


@lru_cache(maxsize=2048)
def _foam_shape_template(kind, seed, phase):
    """Return normalized, seeded foam vertices shared by redraws of a patch."""
    count = 12 if kind in ("crest", "wake") else 10
    seed_phase = (seed % 997) * 0.013
    points = []
    for idx in range(count):
        theta = (math.tau * idx / count) + phase
        irregular = (1.0 + 0.18 * math.sin(theta * 3.0 + seed_phase)
                     + 0.095 * math.sin(theta * 5.0 - seed_phase * 0.7)
                     + 0.045 * math.sin(theta * 7.0 + seed_phase * 1.8))
        along_frac = math.cos(theta)
        across_frac = math.sin(theta)
        if kind in ("wake", "side"):
            taper = 0.80 + 0.20 * (0.5 + 0.5 * along_frac)
        elif kind == "crest":
            taper = 0.88 + 0.12 * math.cos(theta * 2.0 + seed_phase)
        else:
            taper = 1.0
        points.append((along_frac * irregular, across_frac * irregular * taper))
    return tuple(points)


def rect_has(r, p):
    return r[0] <= p.x <= r[0] + r[2] and r[1] <= p.y <= r[1] + r[3]


def bounds_of_points(points):
    """Return immutable (xmin, xmax, ymin, ymax) bounds for world/local points."""
    coords = [(float(p[0]), float(p[1])) if not hasattr(p, "x") else (float(p.x), float(p.y))
              for p in points]
    if not coords:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    return min(xs), max(xs), min(ys), max(ys)


def within_expanded_bounds(x, y, bounds, padding=0.0):
    """Cheap point broad-phase before polygon/capsule collision checks."""
    return (bounds[0] - padding <= x <= bounds[1] + padding
            and bounds[2] - padding <= y <= bounds[3] + padding)


def segment_overlaps_bounds(a, b, bounds, padding=0.0):
    """AABB broad phase for a swept line segment."""
    ax, ay = (float(a.x), float(a.y)) if hasattr(a, "x") else (float(a[0]), float(a[1]))
    bx, by = (float(b.x), float(b.y)) if hasattr(b, "x") else (float(b[0]), float(b[1]))
    return (min(ax, bx) <= bounds[1] + padding and max(ax, bx) >= bounds[0] - padding
            and min(ay, by) <= bounds[3] + padding and max(ay, by) >= bounds[2] - padding)


class CachedFont:
    """Bounded LRU around a Pygame font; repeated labels reuse rasterized glyph surfaces."""
    def __init__(self, font, render_limit=768, size_limit=1536):
        self._font = font
        self._render_limit = max(64, int(render_limit))
        self._size_limit = max(128, int(size_limit))
        self._renders = OrderedDict()
        self._sizes = OrderedDict()

    @staticmethod
    def _colour_key(value):
        try:
            return tuple(value)
        except TypeError:
            return value

    def render(self, text, antialias, color, background=None):
        text = str(text)
        key = (text, bool(antialias), self._colour_key(color),
               None if background is None else self._colour_key(background))
        found = self._renders.get(key)
        if found is not None:
            self._renders.move_to_end(key)
            return found
        result = (self._font.render(text, antialias, color) if background is None
                  else self._font.render(text, antialias, color, background))
        self._renders[key] = result
        if len(self._renders) > self._render_limit:
            self._renders.popitem(last=False)
        return result

    def size(self, text):
        key = str(text)
        found = self._sizes.get(key)
        if found is not None:
            self._sizes.move_to_end(key)
            return found
        result = self._font.size(key)
        self._sizes[key] = result
        if len(self._sizes) > self._size_limit:
            self._sizes.popitem(last=False)
        return result

    def __getattr__(self, name):
        return getattr(self._font, name)


def thick_polyline(surf, color, pts, width):
    pygame.draw.lines(surf, color, False, pts, width)
    for p in pts:
        pygame.draw.circle(surf, color, p, width // 2)


# the catch: what buyers pay for is quality, which is made or lost between the hook and the auction
GRADES = [(0.88, "Sashimi", 1.5), (0.72, "A", 1.15), (0.50, "B", 0.8), (0.30, "C", 0.5), (0.0, "Scrap", 0.2)]
AIR_TEMP = 22.0                  # deg C on deck
ICE_CAP, ICE_PRICE = 100.0, 30   # units of flake ice the hold takes, yen per unit
SPECIES = {"albacore": 0.35, "yellowfin": 0.55, "bigeye": 0.70, "swordfish": 0.90, "blue shark": 0.60}   # how hard they fight
DAY_LEN, START_HOUR = 600.0, 6.5     # real seconds per game day, and the hour the game starts
DEPTH_M = 0.4                        # metres of water per world pixel of line depth
SLACK_MIN, SLACK_MAX = 1.05, 1.50    # line paid out per unit of distance: sets how deep the hooks hang
# ecology: depth (m) and spread, water temperature (C) and spread, feeding gain by day and by night
ECO = {"albacore": (120, 90, 16, 5, 1.5, 1.0), "yellowfin": (90, 80, 21, 5, 1.1, 0.9), "bigeye": (260, 110, 10, 5, 0.9, 1.3),
       "swordfish": (300, 130, 9, 6, 0.5, 3.0), "blue shark": (70, 110, 17, 7, 1.0, 1.8)}
HABITAT = {"albacore": (40, 200), "yellowfin": (40, 200), "bigeye": (150, 450), "swordfish": (150, 450), "blue shark": (0, 1)}   # seabed depth (m) they need under them
BAITS = {"squid": 60, "saury": 35, "mackerel": 25}                 # yen a hook
BAIT_AFF = {"albacore": {"saury": 1.0, "mackerel": 0.8, "squid": 0.6}, "yellowfin": {"saury": 1.0, "squid": 0.8, "mackerel": 0.7},
            "bigeye": {"squid": 1.1, "saury": 0.7, "mackerel": 0.6}, "swordfish": {"squid": 1.4, "mackerel": 0.6, "saury": 0.4},
            "blue shark": {"mackerel": 1.2, "saury": 1.0, "squid": 0.8}}
BAIT_CAP, BAIT_FILL = 60.0, 40.0                                   # units the bait boxes hold; what the quay tops up to
FUEL_CAP, FUEL_PRICE = 700.0, 18                                   # litres the tank takes, yen a litre
# Automatic assistance thresholds. DAY_LEN is the actual simulation-time duration
# of one in-game day, so six in-game hours is 1/4 of DAY_LEN (not 21,600 wall seconds).
TOW_TRIGGER_FUEL_FRACTION = 0.05
TOW_TRIGGER_DRIFT_HOURS = 6.0
TOW_TRIGGER_DRIFT_SECONDS = DAY_LEN * TOW_TRIGGER_DRIFT_HOURS / 24.0
TOW_ADRIFT_SPEED = 8.0                                                # world units/s; below this the ship has no useful way on
GAFFS, GAFF_PRICE, TOW_FEE = 3, 300, 6000


def grade_of(q):
    for lo, name, mult in GRADES:
        if q >= lo:
            return name, mult
    return GRADES[-1][1], GRADES[-1][2]


# ------------------------------------------------------------------ fish art
# Each species is drawn top-down, head to the left: the build, the fins and the markings that tell them apart.
FISH_SIZE = {"albacore": 0.84, "yellowfin": 1.0, "bigeye": 1.15, "swordfish": 1.36, "blue shark": 1.3}   # body length, relative
FISH_DOT = {"albacore": (120, 160, 205), "yellowfin": (236, 200, 60), "bigeye": (150, 120, 130), "swordfish": (150, 130, 175), "blue shark": (70, 130, 220)}
_FISH_W, _FISH_H, _BODY_X0, _BODY_L = 340, 130, 95, 150
_fish_cache = {}
_fish_rotation_cache = OrderedDict()
_FISH_ROTATION_CACHE_LIMIT = 768
_FISH_ROTATION_BUCKETS = 48  # 7.5-degree bins; avoids rotozooming every animated fish every frame.
_FISH_SPEC = {
    "albacore":   dict(back=(30, 58, 96), belly=(206, 214, 220), maxw=15.0, peak=0.30, tip=0.10, ped=0.07, eye=3.5),
    "yellowfin":  dict(back=(28, 50, 86), belly=(198, 200, 190), maxw=17.0, peak=0.36, tip=0.10, ped=0.06, eye=3.5),
    "bigeye":     dict(back=(44, 50, 76), belly=(212, 205, 190), maxw=21.0, peak=0.30, tip=0.14, ped=0.07, eye=5.5),
    "swordfish":  dict(back=(62, 56, 76), belly=(170, 166, 172), maxw=18.0, peak=0.42, tip=0.06, ped=0.05, eye=4.5),
    "blue shark": dict(back=(44, 100, 176), belly=(226, 232, 238), maxw=13.5, peak=0.35, tip=0.04, ped=0.05, eye=3.0),
}


def _prof(t, peak, tip, ped):
    """Half-girth along the body, 0 at the snout to 1 at the thickest point and down to the tail wrist."""
    if t < peak:
        return tip + (1.0 - tip) * math.sin(t / peak * math.pi / 2) ** 0.8
    return ped + (1.0 - ped) * math.cos((t - peak) / (1.0 - peak) * math.pi / 2) ** 1.25


def _render_fish(name, tint, deep):
    sf = pygame.Surface((_FISH_W, _FISH_H), pygame.SRCALPHA)
    sp = _FISH_SPEC[name]
    cx, cy, L = _BODY_X0, _FISH_H / 2, _BODY_L
    xt = cx + L

    def col(c):                                                   # a tired fish goes dull; a deep one is darker
        return mix(mix(c, (150, 146, 128), tint), (26, 44, 72), deep) + (255,)

    def hw(t):
        return sp["maxw"] * _prof(t, sp["peak"], sp["tip"], sp["ped"])

    def at(t, k=1.0):
        return cx + L * t, hw(t) * k

    def outline(k):
        ts = [i / 24.0 for i in range(25)]
        return [(cx + L * t, cy - hw(t) * k) for t in ts] + [(cx + L * t, cy + hw(t) * k) for t in reversed(ts)]

    back, belly = sp["back"], sp["belly"]
    fin = mix(back, (255, 255, 255), 0.06)
    pw = hw(0.97) + 1
    # tail
    if name == "blue shark":
        tail = [(xt - 6, cy - pw), (xt + 52, cy - 26), (xt + 30, cy - 4), (xt + 38, cy + 17), (xt - 6, cy + pw)]
    else:
        tl, tw = {"albacore": (36, 20), "yellowfin": (38, 21), "bigeye": (40, 24), "swordfish": (46, 32)}[name]
        tail = [(xt - 6, cy - pw), (xt + tl, cy - tw), (xt + tl * 0.55, cy), (xt + tl, cy + tw), (xt - 6, cy + pw)]
    pygame.draw.polygon(sf, col(mix(back, (0, 0, 0), 0.15)), tail)
    # pectoral fins
    plen, pt, pbase, pang = {"albacore": (64, 0.26, 4, 0.5), "yellowfin": (36, 0.27, 4, 0.7), "bigeye": (32, 0.25, 5, 0.7),
                             "swordfish": (32, 0.30, 3, 0.8), "blue shark": (68, 0.24, 9, 0.55)}[name]
    for s in (-1, 1):
        px, py = at(pt, 0.92)
        py = cy + s * py
        tipx, tipy = px + plen * math.cos(pang), py + s * plen * math.sin(pang)
        pygame.draw.polygon(sf, col(fin), [(px - pbase, py), (px + pbase * 1.6, py), (tipx, tipy)])
    if name == "swordfish":                                      # the bill
        pygame.draw.polygon(sf, col((70, 72, 80)), [(cx + 8, cy - 4.5), (cx - 56, cy), (cx + 8, cy + 4.5)])
        pygame.draw.line(sf, col((150, 150, 158)), (cx + 6, cy + 2), (cx - 50, cy + 0.5), 1)
    pygame.draw.polygon(sf, col(belly), outline(1.0))
    pygame.draw.polygon(sf, col(back), outline(0.78))
    pygame.draw.lines(sf, col(mix(back, (0, 0, 0), 0.35)), False, [(cx + L * t, cy) for t in (0.04, 0.5, 0.97)], 2)
    # markings
    if name == "albacore":
        for s in (-1, 1):
            pygame.draw.lines(sf, col((96, 156, 214)), False, [(cx + L * t, cy + s * hw(t) * 0.48) for t in (0.2, 0.45, 0.7, 0.9)], 2)
        for t in (0.82, 0.86, 0.9, 0.94):
            pygame.draw.circle(sf, col((214, 200, 90)), (cx + L * t, cy), 1.6)
    elif name == "yellowfin":
        for s in (-1, 1):
            pygame.draw.lines(sf, col((238, 198, 42)), False, [(cx + L * t, cy + s * hw(t) * 0.52) for t in (0.18, 0.4, 0.7, 0.95)], 3)
        pygame.draw.polygon(sf, col((242, 204, 52)), [(cx + L * 0.52, cy - 2.5), (cx + L * 0.7, cy - 2), (xt + 12, cy - 0.5), (xt + 12, cy + 0.5), (cx + L * 0.7, cy + 2), (cx + L * 0.52, cy + 2.5)])
        for t in (0.84, 0.88, 0.92, 0.96):
            pygame.draw.circle(sf, col((244, 210, 60)), (cx + L * t, cy), 1.8)
    elif name == "bigeye":
        for s in (-1, 1):
            pygame.draw.lines(sf, col((86, 120, 170)), False, [(cx + L * t, cy + s * hw(t) * 0.5) for t in (0.2, 0.5, 0.9)], 2)
        pygame.draw.lines(sf, col(mix(back, (0, 0, 0), 0.4)), False, [(cx + L * 0.2, cy - hw(0.2) * 0.8), (cx + L * 0.23, cy), (cx + L * 0.2, cy + hw(0.2) * 0.8)], 2)
    elif name == "swordfish":
        pygame.draw.polygon(sf, col(mix(back, (0, 0, 0), 0.4)), [(cx + L * 0.28, cy - 2.5), (cx + L * 0.5, cy - 1.5), (cx + L * 0.5, cy + 1.5), (cx + L * 0.28, cy + 2.5)])
        for s in (-1, 1):
            pygame.draw.line(sf, col(mix(back, (0, 0, 0), 0.3)), (xt - 8, cy + s * 3), (xt + 4, cy + s * 8), 2)
    elif name == "blue shark":
        for k in range(5):
            t = 0.2 + k * 0.025
            for s in (-1, 1):
                pygame.draw.line(sf, col((70, 120, 190)), (cx + L * t, cy + s * hw(t) * 0.55), (cx + L * t + 2, cy + s * hw(t) * 0.9), 1)
        pygame.draw.polygon(sf, col(mix(back, (0, 0, 0), 0.3)), [(cx + L * 0.42, cy - 2), (cx + L * 0.52, cy), (cx + L * 0.42, cy + 2)])
    for s in (-1, 1):                                            # the eyes, either side of the head
        ex, ey = at(0.11, 0.74)
        er = sp["eye"]
        pygame.draw.circle(sf, col((228, 228, 214)), (ex, cy + s * ey), er + 1)
        pygame.draw.circle(sf, (10, 10, 14, 255), (ex, cy + s * ey), er)
    return sf


def draw_fish(surf, name, center, angle, base_px, quality=1.0, deep=0.0, bled=False):
    """A fish seen from above, head towards -x before `angle` is applied. base_px is the yellowfin body length."""
    if name not in FISH_SIZE:
        name = "yellowfin"
    qb = 0 if quality >= 0.72 else 1 if quality >= 0.5 else 2 if quality >= 0.3 else 3
    db = min(3, int(clamp(deep, 0.0, 1.0) * 4))
    key = (name, qb, db)
    spr = _fish_cache.get(key)
    if spr is None:
        spr = _fish_cache[key] = _render_fish(name, (0.0, 0.3, 0.55, 0.8)[qb], (0.0, 0.25, 0.5, 0.7)[db])
    k = base_px * FISH_SIZE[name] / _BODY_L
    if k < 0.04:
        return
    # Rotation/scale transforms are expensive and usually repeat for the same
    # species, depth/quality bucket, zoom, and nearby animated angles. Quantized
    # rotations are visually smooth at game scale and stay inside a bounded LRU.
    angle_bin = int(round(((-math.degrees(angle)) % 360.0) / 360.0 * _FISH_ROTATION_BUCKETS)) % _FISH_ROTATION_BUCKETS
    angle_deg = angle_bin * 360.0 / _FISH_ROTATION_BUCKETS
    scale_key = round(k, 3)
    rkey = (key, scale_key, angle_bin)
    img = _fish_rotation_cache.get(rkey)
    if img is None:
        img = pygame.transform.rotozoom(spr, angle_deg, scale_key)
        _fish_rotation_cache[rkey] = img
        if len(_fish_rotation_cache) > _FISH_ROTATION_CACHE_LIMIT:
            _fish_rotation_cache.popitem(last=False)
    else:
        _fish_rotation_cache.move_to_end(rkey)
    surf.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))
    if bled:
        gill = V(center) + V(-0.3 * _BODY_L * k, 0).rotate_rad(angle)
        pygame.draw.circle(surf, (165, 40, 40), gill, max(2, int(4 * k * 1.6)))


# ------------------------------------------------------------------ seabird art
# Birds are drawn top-down, head toward +x before `angle` is applied (like the fish, cached and rotated in bins).
_BIRD_CANVAS, _BIRD_HALF = 120, 50.0         # canvas px; full wing half-span px
_BIRD_PALETTE = {
    "gull": dict(wing=(176, 186, 192), back=(150, 161, 169), tip=(30, 34, 38), body=(246, 246, 240),
                 tail=(248, 248, 242), beak=(230, 172, 50), edge=(70, 78, 84)),
    "shearwater": dict(wing=(70, 68, 68), back=(52, 50, 51), tip=(30, 30, 33), body=(104, 100, 96),
                       tail=(50, 48, 49), beak=(42, 42, 46), edge=(16, 16, 18)),
}
_bird_cache = {}
_bird_rotation_cache = OrderedDict()
_BIRD_ROTATION_CACHE_LIMIT = 768
_BIRD_ROTATION_BUCKETS = 36                  # 10-degree bins


def _render_seabird(kind, frame, bank):
    """One pose of a gull seen from above: frames 0-7 flap, 8 soaring glide, 9 folded plunge-dive."""
    pal = _BIRD_PALETTE[kind]
    S = _BIRD_CANVAS
    sf = pygame.Surface((S, S), pygame.SRCALPHA)
    cx = cy = S / 2.0
    if frame < FLAP_FRAMES:                       # the wings sweep through an arc, so the span foreshortens
        ph = frame / FLAP_FRAMES * TAU
        span, sweep = math.cos(math.sin(ph) * 0.95), 0.5 + 0.5 * math.cos(ph)
    elif frame == FRAME_GLIDE:
        span, sweep = 0.97, 0.15
    else:                                         # plunge: wings swept back along the body
        span, sweep = 0.42, 1.0

    def lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def rgba(c, a=255):
        return (c[0], c[1], c[2], a)

    def wing(side):
        L = _BIRD_HALF * span * (1.0 - 0.14 * bank * side)       # the inside wing of a turn looks shorter
        lead = [(cx + 7, cy + side * 5), (cx + 5 - 4 * sweep, cy + side * L * 0.42),
                (cx - 6 - 12 * sweep, cy + side * L)]
        trail = [(cx - 18 - 12 * sweep, cy + side * L * 0.97), (cx - 16 - 4 * sweep, cy + side * L * 0.62),
                 (cx - 13, cy + side * L * 0.40), (cx - 15, cy + side * 5)]
        outline = lead + trail
        pygame.draw.polygon(sf, rgba(pal["wing"]), outline)
        arm = [lead[0], lerp(lead[0], lead[1], 0.9), lerp(trail[3], trail[2], 0.9), trail[3]]
        pygame.draw.polygon(sf, rgba(pal["back"]), arm)               # darker mantle-side coverts
        hand = [lerp(lead[1], lead[2], 0.62), lead[2], trail[0], lerp(trail[1], trail[0], 0.62)]
        pygame.draw.polygon(sf, rgba(pal["tip"]), hand)               # black wing-tips
        for j in (0.3, 0.55, 0.8):                                    # primary feather separations
            a = lerp(trail[1], trail[0], j)
            b = lerp(a, lerp(lead[1], lead[2], j), 0.42)
            pygame.draw.line(sf, rgba(pal["tip"], 200), a, b, 1)
        pygame.draw.polygon(sf, rgba(pal["edge"], 210), outline, 1)

    # forked tail first so the body overlaps its root
    tail = [(cx - 18, cy - 4), (cx - 37, cy - 8), (cx - 32, cy), (cx - 37, cy + 8), (cx - 18, cy + 4)]
    pygame.draw.polygon(sf, rgba(pal["tail"]), tail)
    pygame.draw.polygon(sf, rgba(pal["edge"], 170), tail, 1)
    wing(-1)
    wing(1)
    xs = (16, 10, 2, -6, -14, -21)                # teardrop body: narrow neck, full chest, tapering rump
    hw = (3.2, 5.0, 6.2, 5.6, 3.6, 1.8)
    body = [(cx + x, cy - w) for x, w in zip(xs, hw)] + [(cx + x, cy + w) for x, w in reversed(list(zip(xs, hw)))]
    pygame.draw.polygon(sf, rgba(pal["body"]), body)
    saddle = [(cx + 7, cy - 3.2), (cx - 12, cy - 3.0), (cx - 12, cy + 3.0), (cx + 7, cy + 3.2)]
    pygame.draw.polygon(sf, rgba(pal["back"], 235), saddle)
    pygame.draw.polygon(sf, rgba(pal["edge"], 150), body, 1)
    pygame.draw.circle(sf, rgba(pal["body"]), (cx + 19, cy), 4.6)
    pygame.draw.polygon(sf, rgba(pal["beak"]), [(cx + 22.5, cy - 1.9), (cx + 31, cy), (cx + 22.5, cy + 1.9)])
    for side in (-1, 1):
        pygame.draw.circle(sf, (20, 20, 24, 255), (cx + 20.5, cy + side * 2.8), 1.1)
    return sf


def draw_seabird(surf, kind, center, angle, half_span_px, frame, bank=0.0, alpha=255):
    """Blit a cached, rotated top-down seabird. `angle` is the heading in screen radians (y down)."""
    k = float(half_span_px) / _BIRD_HALF
    if k < 0.10 or kind not in _BIRD_PALETTE:
        return
    bank_bin = -1 if bank < -0.3 else (1 if bank > 0.3 else 0)
    key = (kind, int(frame), bank_bin)
    spr = _bird_cache.get(key)
    if spr is None:
        spr = _bird_cache[key] = _render_seabird(kind, int(frame), bank_bin)
    angle_bin = int(round(((-math.degrees(angle)) % 360.0) / 360.0 * _BIRD_ROTATION_BUCKETS)) % _BIRD_ROTATION_BUCKETS
    scale_key = round(k, 2)
    rkey = (key, scale_key, angle_bin)
    img = _bird_rotation_cache.get(rkey)
    if img is None:
        img = pygame.transform.rotozoom(spr, angle_bin * 360.0 / _BIRD_ROTATION_BUCKETS, scale_key)
        _bird_rotation_cache[rkey] = img
        if len(_bird_rotation_cache) > _BIRD_ROTATION_CACHE_LIMIT:
            _bird_rotation_cache.popitem(last=False)
    else:
        _bird_rotation_cache.move_to_end(rkey)
    img.set_alpha(max(0, min(255, int(alpha))))
    surf.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))


DECK = hexc("#6b5640")
PLANK = hexc("#5a4733")
RAIL = hexc("#2b2118")
RAIL_HI = hexc("#4a3a2a")
STEEL = hexc("#8d9399")
COAMING = hexc("#6f757b")      # bare steel fittings standing out of the planking
WHITE = hexc("#d8d2c4")
RED = hexc("#a63d2f")
GOLD = hexc("#c9a227")
SHALLOW = hexc("#3f8a8c")
DEEP = hexc("#16395a")
STORM = hexc("#34495a")
LAND = hexc("#6a7547")


# -------------------------------------------------------------------- waves

class WaveField:
    # (wavelength px, amplitude px, direction offset rad, phase rad)
    COMPONENTS = [(1600, 46, 0.0, 0.0), (900, 26, 0.5, 1.7), (520, 14, -0.8, 4.1), (300, 7, 1.7, 2.6)]
    G = 200.0

    def __init__(self, scale):
        self.scale = scale
        self.strength = 0.4
        self.base_angle = 2.2
        self.time = 0.0

    def count(self):
        return len(self.COMPONENTS)

    def wavelength(self, i):
        return self.COMPONENTS[i][0] * self.scale

    def k(self, i):
        return TAU / self.wavelength(i)

    def omega(self, i):
        return math.sqrt(self.G * self.k(i))

    def amp(self, i):
        return self.COMPONENTS[i][1] * self.scale * self.strength

    def dir(self, i):
        return V(1, 0).rotate_rad(self.base_angle + self.COMPONENTS[i][2])

    def phase(self, i):
        return self.COMPONENTS[i][3]

    def height(self, p):
        h = 0.0
        for i in range(self.count()):
            h += self.amp(i) * math.sin(self.k(i) * self.dir(i).dot(p) - self.omega(i) * self.time + self.phase(i))
        return h


# --------------------------------------------------------------------- ship

class Level(IntEnum):
    """Vertical levels of the ship (Phase 0: only MAIN is in use)."""
    BELOW = -1        # engine room and ice hold
    MAIN = 0          # the working deck
    WHEELHOUSE = 1    # forward superstructure


# All deck layout numbers live here so later phases only edit data.
# Rects are (x, y, w, h): x and w are fractions of ship length L, y and h are fractions of beam B.
# Points are (x, y) in the same fractions; markers add a pixel offset (dx, dy) on top.
# Bow is +x, starboard is +y, origin at the ship's centre.
LAYOUT = {
    "wheelhouse":   (0.10, -0.15, 0.14, 0.30),
    # Working stations are fractions of L/B, spaced to stay distinct and reachable
    # with the wheelhouse's 47-unit crew-clearance rule. The guide's raw helm/compass
    # coordinates overlap visually, so throttle and compass are placed on separate sides.
    "wheelhouse_stations": {
        # Sailors are 53 px across, so stations sit >= ~46 px from the helm (the captain's post)
        # and the radio stays > 27 px from the ladder landing (an operator must not block the door).
        "helm":     (0.220,  0.000),   # centreline
        "throttle": (0.178,  0.075),   # starboard, abaft the helm
        "compass":  (0.178, -0.075),   # port, abaft the helm
        "radio":    (0.136, -0.075),   # aft, port side, clear of the ladder landing
    },
    "hauler":       (-0.34, 0.37, 0.04, 0.12),            # starboard quarter, centre at x -0.32 L
    "lifeboat":     (0.0, -0.47, 0.12, 0.12),
    "bait_boxes":   [(-0.46, -0.40, 0.06, 0.20), (-0.46, 0.20, 0.06, 0.20)],
    # Fish/ice-hold hatches are grouped over the amidships hold, not spread into the engine room.
    "hatches":      [(-0.13, -0.14, 0.075, 0.28), (-0.065, -0.14, 0.075, 0.28)],
    "table":        (-0.15, -0.35, 0.06, 0.10),           # cutting table, port side beside the hatches
    "hose_station": (-0.105, -0.205),                    # seawater hose stand beside the cutting table
    "engine_hatch": (-0.285, -0.12, 0.07, 0.24),          # aft engine-room grating
    "post":         (0.30, 0.0),
    "openings":     [(0.0, 0.3, 0.14, 0.5)],              # gaps in the rail (x, y in L, B; w in L, h in B)
    # Crew stairwell (companionway) abaft the wheelhouse: the only way into the crew cabin.
    "companionway": (0.022, -0.085, 0.050, 0.170),
    # The lower deck is a real compartment plan, stern to bow, split by athwartships bulkheads:
    #   aft stores | ENGINE ROOM | ICE HOLD | CREW CABIN | forepeak
    # There is NO alleyway through the middle. The engine room and the ice hold are each
    # entered only from the deck above (engine ladder, hold ladder). The crew cabin has its own
    # companionway. The aft stores open off the engine room through a watertight door, and the
    # forepeak opens off the cabin the same way. Sizes are chosen for a sailor who is ~70 px
    # across the shoulders: aisles >= 100 px, berths 115 x 59 px, ladder wells 54 px wide.
    "below": {
        "aft_stores": (-0.470, -0.42, 0.085, 0.84),
        "engine_room": (-0.385, -0.45, 0.190, 0.90),
        "ice_hold": (-0.195, -0.45, 0.215, 0.90),
        # Main engine sits to port of the ladder well, directly under the deck grating.
        "casing": (-0.355, -0.31, 0.120, 0.21),
        "crew_quarters": (0.020, -0.45, 0.315, 0.90),
        "forepeak": (0.335, -0.20, 0.135, 0.40),
        # Six full-length berths, three a side, heads to the hull, a 100 px aisle between them.
        "bunks": [
            (0.08, -0.26, 0.07, 0.14),
            (0.08,  0.12, 0.07, 0.14),
            (0.16, -0.26, 0.07, 0.14),
            (0.16,  0.12, 0.07, 0.14),
            (0.24, -0.26, 0.07, 0.14),
            (0.24,  0.12, 0.07, 0.14),
        ],
        # One approach point in the aisle beside each berth (port berths: port half of the aisle).
        "bunk_stands": [
            (0.115, -0.05), (0.115, 0.05),
            (0.195, -0.05), (0.195, 0.05),
            (0.275, -0.05), (0.275, 0.05),
        ],
        "generator": (-0.355, 0.17, 0.050, 0.14),
        "switchboard": (-0.240, 0.12, 0.045, 0.22),
        # Bulkheads: (x frac L, door centre y frac B or None, door width px). None = solid bulkhead.
        "bulkheads": [(-0.385, 0.0, 96.0), (-0.195, None, 0.0), (0.020, None, 0.0), (0.335, 0.0, 96.0)],
        # Insulated fish pens in the ice hold, one block each side of a clear centre aisle.
        "ice_bins": [(-0.185, -0.42, 0.19, 0.23), (-0.185, 0.19, 0.19, 0.23)],
        "stores_racks": [(-0.455, -0.40, 0.055, 0.16), (-0.455, 0.24, 0.055, 0.16)],
    },
    # access links between levels: (name, kind, level a, point a, level b, point b); points as (x frac L, y frac B, dx px, dy px)
    "links": [
        # The wheelhouse landing is set well inside the walkable floor. The deck-side
        # endpoint stays at the outside of the wall; this offset avoids landing a sailor
        # directly on the wheelhouse's blocking boundary.
        ("wheelhouse ladder", "wall", Level.MAIN, (0.12, 0.205, 0, 0), Level.WHEELHOUSE, (0.12, 0.095, 0, 0)),
        ("engine ladder", "hatch", Level.MAIN, (-0.25, 0.0, 0, 0), Level.BELOW, (-0.25, 0.0, 0, 0)),
        ("hold ladder", "hatch", Level.MAIN, (-0.0925, 0.06, 0, 0), Level.BELOW, (-0.0925, 0.06, 0, 0)),
        # Open stairwell (no cover to dog) down into the crew cabin aisle.
        ("crew companionway", "hatch", Level.MAIN, (0.047, 0.0, 0, 0), Level.BELOW, (0.047, 0.0, 0, 0)),
    ],
    # markers that are not on the main deck
    "marker_levels": {"engine": Level.BELOW, "captain_post": Level.WHEELHOUSE},
    "forepeak": {"bitts": [(0.41, -0.11), (0.41, 0.11)], "anchor": (0.445, 0.0)},   # mooring bitts and the anchor
    # markers: (x frac of L, y frac of B, dx px, dy px)
    "markers": {
        "stern_set":    (-0.5, 0.0, 50, 0),
        "haul_station": (-0.32, 0.30, 0, 0),              # inboard of the starboard-quarter hauler
        "captain_post": (0.22, 0.0, 0, 0),               # qualified skipper stands at the helm
        "bow_lookout":  (0.40, 0.0, 0, 0),
        "rest_spot":    (-0.05, -0.25, 0, 0),            # main-deck idle/standby position
        "table_stand":  (-0.12, -0.155, 0, 0),            # where the cutter stands, inboard of the table
        "landing":      (-0.32, 0.30, 35, -10),           # where hauled fish land
        "engine":       (-0.215, -0.17, 0, 0),           # engineer stands at the forward end of the main engine (below deck)
        "hatch_1":      (-0.0925, -0.08, 0, 0),          # drop points: stand here to send a fish below
        "hatch_2":      (-0.0275, -0.08, 0, 0),
    },
}


class Link:
    """A way between two levels: a ladder or a hatch with a spot to stand on each side."""

    def __init__(self, name, kind, la, pa, lb, pb):
        self.name, self.kind = name, kind
        self.ends = {la: V(pa), lb: V(pb)}

    def pos(self, level):
        return self.ends[level]

    def other(self, level):
        return next(l for l in self.ends if l != level)


def rect_walls(r):
    x, y, w, h = r
    c = [V(x, y), V(x + w, y), V(x + w, y + h), V(x, y + h)]
    return [(c[i], c[(i + 1) % 4]) for i in range(4)]


class NavMap:
    """One level's walkable space: a coarse grid of safe cells searched with A*, plus wall and solid collision."""
    NAV = 12.0
    NEIGH = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]

    def __init__(self, extent, inside, walls, solids, clear, post=None, open_edges=()):
        L, B = extent
        self.walls, self.solids, self.post = walls, solids, post
        self.inside, self.clear = inside, float(clear)
        self.nav = {}
        c = self.NAV
        for i in range(int(-L / 2 / c) - 1, int(L / 2 / c) + 2):
            for j in range(int(-B / 2 / c) - 1, int(B / 2 / c) + 2):
                p = self._centre((i, j))
                if not inside(p):
                    continue
                wall_clearance = min((p.distance_to(closest_on_seg(p, a, b)) for a, b in walls), default=999.0)
                solid_clearance = min((self._rect_dist(p, r) for r in solids), default=999.0)
                if wall_clearance < clear or solid_clearance < clear:
                    continue
                if post is not None and p.distance_to(post) < clear + 9:
                    continue
                dopen = min((p.distance_to(closest_on_seg(p, a, b)) for a, b in open_edges), default=999.0)
                # Stay comfortably clear of the hull, machinery and bunks rather than
                # merely squeezing through every cell which clears the hard radius.
                clearance = min(wall_clearance, solid_clearance)
                scrape_cost = max(0.0, 64.0 - clearance) / 16.0
                edge_cost = max(0.0, 90.0 - dopen) / 10.0
                self.nav[(i, j)] = 1.0 + scrape_cost + edge_cost

        self._label()

    def _label(self):
        """Flood-fill the walkable grid so level links can route across connected spaces."""
        self.comp, n = {}, 0
        for start in self.nav:
            if start in self.comp:
                continue
            n += 1
            stack = [start]
            self.comp[start] = n
            while stack:
                cur = stack.pop()
                for dx, dy in self.NEIGH:
                    nb = (cur[0] + dx, cur[1] + dy)
                    if nb in self.nav and nb not in self.comp:
                        if dx and dy and ((cur[0] + dx, cur[1]) not in self.nav or (cur[0], cur[1] + dy) not in self.nav):
                            continue
                        self.comp[nb] = n
                        stack.append(nb)

    def connected(self, a, b):
        if not self.nav:
            return False
        return self.comp.get(self.nearest_cell(V(a))) == self.comp.get(self.nearest_cell(V(b)))

    @staticmethod
    def _rect_dist(p, r):
        dx = max(r[0] - p.x, 0.0, p.x - (r[0] + r[2]))
        dy = max(r[1] - p.y, 0.0, p.y - (r[1] + r[3]))
        return math.hypot(dx, dy)

    def _cell(self, p):
        return (math.floor(p.x / self.NAV), math.floor(p.y / self.NAV))

    def _centre(self, c):
        return V((c[0] + 0.5) * self.NAV, (c[1] + 0.5) * self.NAV)

    def nearest_cell(self, p):
        c = self._cell(p)
        if c in self.nav:
            return c
        return min(self.nav, key=lambda k: (self._centre(k) - p).length_squared())

    def point_safe(self, point):
        """Check a target point itself, not only the centre of its grid cell."""
        p = V(point)
        if not self.nav or self._cell(p) not in self.nav or not self.inside(p):
            return False
        if any(p.distance_to(closest_on_seg(p, a, b)) < self.clear for a, b in self.walls):
            return False
        if any(self._rect_dist(p, solid) < self.clear for solid in self.solids):
            return False
        return not (self.post is not None and p.distance_to(self.post) < self.clear + 9)

    def _line_ok(self, a, b, obstacles=()):
        ca, cb = self.nav.get(self._cell(a), 1.0), self.nav.get(self._cell(b), 1.0)
        limit = max(1.5, ca, cb)
        n = max(1, int(a.distance_to(b) / 8))
        for i in range(n + 1):
            t = i / n
            p = a.lerp(b, t)
            cost = self.nav.get(self._cell(p))
            if cost is None or cost > limit:
                return False
            # String-pulling must not erase a crowd-aware detour through another sailor.
            # Ignore the very first/final stretch so an already-nearby coworker or the
            # intended endpoint doesn't make every short approach impossible.
            if obstacles and p.distance_to(a) > 30.0 and p.distance_to(b) > 42.0:
                if any(p.distance_to(op) < radius * 0.72 for op, radius in obstacles):
                    return False
        return True

    def find_path(self, a, b, obstacles=()):
        """A* route planning with optional soft costs around moving crew.

        Static wall/solid collision remains authoritative. Nearby sailors add a route
        cost instead of becoming hard walls, so crew can still pass through narrow
        spaces when necessary and work stations remain reachable.
        """
        a, b = V(a), V(b)
        if not self.nav:
            return [b]
        s, requested_t = self.nearest_cell(a), self.nearest_cell(b)
        start_component = self.comp.get(s)
        t = requested_t
        # A target can land just beyond a bulkhead or in a bow cell excluded by
        # hull clearance. Select the nearest cell in the sailor's actual connected
        # component instead of returning an empty route that is retried forever.
        if start_component is not None and self.comp.get(requested_t) != start_component:
            reachable = [cell for cell, component in self.comp.items() if component == start_component]
            if reachable:
                t = min(reachable, key=lambda cell: (self._centre(cell) - b).length_squared())
        crowd_cost = {}
        if obstacles:
            for cell in self.nav:
                p = self._centre(cell)
                penalty = 0.0
                for op, radius in obstacles:
                    d = p.distance_to(op)
                    if d < radius:
                        # Strongest in another sailor's personal space, fading smoothly.
                        penalty += 18.0 * (1.0 - d / radius) ** 2
                if penalty:
                    crowd_cost[cell] = penalty
        # Exact task coordinates can fall in a walkable cell but too close to a
        # wall/solid for a sailor's body radius. Use the centre of the nearest safe
        # cell as the final approach point in that case.
        goal_is_reachable = (self.point_safe(b) and self._cell(b) in self.nav
                             and self.comp.get(self._cell(b)) == start_component)
        goal = V(b) if goal_is_reachable and t == requested_t else self._centre(t)
        if s == t:
            return [goal]
        best, came = {s: 0.0}, {}
        frontier = [(math.hypot(s[0] - t[0], s[1] - t[1]), 0.0, s)]
        while frontier:
            _, queued_g, cur = heapq.heappop(frontier)
            # A cell can be discovered several times; do not expand stale, more
            # expensive entries after a better route has already reached it.
            if queued_g > best.get(cur, math.inf) + 1e-9:
                continue
            if cur == t:
                break
            for dx, dy in self.NEIGH:
                nb = (cur[0] + dx, cur[1] + dy)
                if nb not in self.nav:
                    continue
                if dx and dy and ((cur[0] + dx, cur[1]) not in self.nav or (cur[0], cur[1] + dy) not in self.nav):
                    continue
                ng = best[cur] + (1.414 if dx and dy else 1.0) * self.nav[nb] + crowd_cost.get(nb, 0.0)
                if ng < best.get(nb, 1e18):
                    best[nb], came[nb] = ng, cur
                    heuristic = math.hypot(nb[0] - t[0], nb[1] - t[1])
                    heapq.heappush(frontier, (ng + heuristic, ng, nb))
        if t not in came:
            return []
        cells, cur = [], t
        while cur != s:
            cells.append(self._centre(cur))
            cur = came[cur]
        cells.reverse()
        # Include the real goal in the string-pull checks. The old implementation
        # appended it after smoothing, so the final centre-to-target segment could
        # cut through a bunk, engine casing, wall, or crowd despite the A* route.
        pts = [V(a)] + cells + [V(goal)]
        out, i = [], 0
        while i < len(pts) - 1:          # skip waypoints only when the whole segment is clear
            j = len(pts) - 1
            while j > i + 1 and not self._line_ok(pts[i], pts[j], obstacles):
                j -= 1
            out.append(pts[j])
            i = j
        return out

    def collide(self, pos, vel, r):
        pos, vel = V(pos), V(vel)
        for a, b in self.walls:
            c = closest_on_seg(pos, a, b)
            d = pos - c
            dist = d.length()
            if dist < r:
                n = d / dist if dist > 1e-6 else ((-c).normalize() if c.length() > 1e-6 else V(1, 0))
                pos = c + n * r
                vn = vel.dot(n)
                if vn < 0:
                    vel -= n * vn
        for (x, y, w, h) in self.solids:
            cx, cy = clamp(pos.x, x, x + w), clamp(pos.y, y, y + h)
            d = pos - V(cx, cy)
            dist = d.length()
            if dist < r:
                if dist > 1e-6:
                    n = d / dist
                    pos = V(cx, cy) + n * r
                else:   # centre inside the box: push out through the nearest side
                    opts = [(pos.x - x, V(-1, 0)), (x + w - pos.x, V(1, 0)), (pos.y - y, V(0, -1)), (y + h - pos.y, V(0, 1))]
                    dd, n = min(opts, key=lambda o: o[0])
                    pos = pos + n * (dd + r)
                vn = vel.dot(n)
                if vn < 0:
                    vel -= n * vn
        if self.post is not None:
            d = pos - self.post
            if d.length() < r + 9:
                n = d.normalize() if d.length() > 1e-6 else V(1, 0)
                pos = self.post + n * (r + 9)
        return pos, vel


class Wash:
    """A wave breaking over the rail: a sheet of green water that sweeps across the deck and drains."""
    DIRS = {"stbd": V(0, -1), "port": V(0, 1), "bow": V(-1, 0), "stern": V(1, 0)}

    def __init__(self, side, cx, width, depth):
        self.side, self.cx, self.width, self.depth = side, cx, width, depth
        self.dir = self.DIRS[side]
        self.age, self.life = 0.0, 3.4

    def strength(self):
        return clamp(self.age / 0.15, 0.0, 1.0) * math.exp(-0.9 * max(self.age - 0.5, 0.0))

    def rect(self, ship):
        L, B = ship.length, ship.beam
        f = min(self.depth, 420.0 * self.age)
        if self.side == "stbd":
            return (self.cx - self.width / 2, B / 2 - f, self.width, f)
        if self.side == "port":
            return (self.cx - self.width / 2, -B / 2, self.width, f)
        if self.side == "bow":
            return (L / 2 - f, -self.width / 2, f, self.width)
        return (-L / 2, -self.width / 2, f, self.width)

    def front(self, ship):
        x, y, w, h = self.rect(ship)
        return {"stbd": ((x, y), (x + w, y)), "port": ((x, y + h), (x + w, y + h)),
                "bow": ((x, y), (x, y + h)), "stern": ((x + w, y), (x + w, y + h))}[self.side]

    def contains(self, ship, p):
        return rect_has(self.rect(ship), p)


class Ship:
    """Deck coordinates: origin at the ship's centre, bow toward +x, starboard +y."""

    def __init__(self, length=1650.0, beam=420.0):
        self.length = length
        self.beam = beam
        self.Level = Level
        self.slope = V(0, 0)
        self.wet, self.flood = 0.0, 0.0      # damp deck / standing water
        self.engine_flood = 0.0          # bilge water in the engine room
        self.bucket_count = 4
        self.washes, self.spray = [], []
        self.deck_foam = []                  # v13.2.05: foam streaks left on the deck by boarding seas
        self.last_flood_report = None
        FloodingModel.attach(self)           # list, freeboard, pump and flooding-state fields
        self.hull = []
        self._build_hull()
        self._layout()
        self._build_art()                    # redesign: cache rail/floor polygons and compartment shapes
        # Dogged-closed by default: the crew open these only when access or stowing fish requires it.
        # Keeping the engine-room and ice-hold openings shut makes them an actual flooding control.
        self.hatch_states = {"engine": False, "hold_1": False, "hold_2": False}
        self.hold_flood = 0.0
        n = len(self.hull)
        self.walls = [(self.hull[i], self.hull[(i + 1) % n]) for i in range(n) if not self.is_open(i)]
        self.solids = [self.wheelhouse, self.hauler, self.lifeboat, self.table] + self.bait_boxes
        self.open_edges = [(self.hull[i], self.hull[(i + 1) % n]) for i in range(n) if self.is_open(i)]
        self._build_nav()
        self.planks = []
        y = -beam * 0.5 + 8
        while y < beam * 0.5:
            for x0, x1 in self._scan(y):
                self.planks.append((x0, x1, y))
            y += 18

    def _half_width(self, u):
        w = 1.0
        if u < 0.15:
            w = lerp(0.82, 1.0, smoothstep(0.0, 0.15, u))
        elif u > 0.6:
            w = 1.0 - ((u - 0.6) / 0.4) ** 1.8
        return w * self.beam * 0.5

    def _build_hull(self):
        n = 28
        top = [V(-self.length * 0.5 + i / n * self.length, self._half_width(i / n)) for i in range(n + 1)]
        bottom = [V(-self.length * 0.5 + i / n * self.length, -self._half_width(i / n)) for i in range(n - 1, -1, -1)]
        self.hull = top + bottom   # last edge (port stern -> starboard stern) is the open stern

    def _layout(self):
        L, B = self.length, self.beam
        D = LAYOUT

        def rect(r):
            return (L * r[0], B * r[1], L * r[2], B * r[3])

        self.wheelhouse = rect(D["wheelhouse"])
        self.wheelhouse_stations = {k: V(L * x, B * y) for k, (x, y) in D["wheelhouse_stations"].items()}
        self.hauler = rect(D["hauler"])
        self.lifeboat = rect(D["lifeboat"])
        self.bait_boxes = [rect(r) for r in D["bait_boxes"]]
        self.hatches = [rect(r) for r in D["hatches"]]
        self.table = rect(D["table"])
        self.engine_hatch = rect(D["engine_hatch"])
        self.hose_station = V(L * D["hose_station"][0], B * D["hose_station"][1])
        self.post = V(L * D["post"][0], B * D["post"][1])
        self.openings = [rect(r) for r in D["openings"]]
        self.markers = {k: V(L * x + dx, B * y + dy) for k, (x, y, dx, dy) in D["markers"].items()}
        fp = D["forepeak"]
        self.bitts = [V(L * x, B * y) for x, y in fp["bitts"]]
        self.anchor_pos = V(L * fp["anchor"][0], B * fp["anchor"][1])
        self.roller = (-L * 0.5 - 4, -B * 0.10, 10, B * 0.2)
        self.marker_level = dict(D["marker_levels"])
        self.links = [Link(n, k, la, V(L * a[0] + a[2], B * a[1] + a[3]), lb, V(L * b[0] + b[2], B * b[1] + b[3]))
                      for n, k, la, a, lb, b in D["links"]]
        bl = D["below"]
        # Compartment rectangles drive rendering/work semantics. The navigation map below
        # adds the actual watertight bulkheads and door gaps, so rooms are distinct spaces.
        self.below_rooms = [rect(bl["engine_room"]), rect(bl["ice_hold"])]
        self.below_aft_stores = rect(bl["aft_stores"])
        self.crew_quarters = rect(bl["crew_quarters"])
        self.below_forepeak = rect(bl["forepeak"])
        self.below_casing = rect(bl["casing"])
        self.bunks = [rect(r) for r in bl.get("bunks", [])]
        self.bunk_centres = [V(x + w * 0.5, y + h * 0.5) for x, y, w, h in self.bunks]
        self.bunk_stands = [V(L * x, B * y) for x, y in bl.get("bunk_stands", [])]
        self.below_generator = rect(bl["generator"])
        self.below_switchboard = rect(bl["switchboard"])
        self.ice_bins = [rect(r) for r in bl["ice_bins"]]
        self.stores_racks = [rect(r) for r in bl["stores_racks"]]
        self.companionway = rect(D["companionway"])
        # Athwartships bulkheads: (x, door centre y or None, door width). Each becomes real wall
        # segments in the lower nav map, with a gap where there is a door.
        self.bulkheads = [(L * x, None if dy is None else B * dy, dw) for x, dy, dw in bl["bulkheads"]]
        # Bunks and machinery are solid to walking crew. A sailor explicitly sleeping
        # in a bunk is a special state handled by the crew collision solver.
        self.below_solids = ([self.below_casing, self.below_generator, self.below_switchboard]
                             + self.ice_bins + self.stores_racks + self.bunks)

        def grow(r, g):
            return (r[0] - g, r[1] - g, r[2] + 2 * g, r[3] + 2 * g)
        # bare steel standing proud of the planking: slick when wet (hatch coamings, engine casing, roller, hauler base)
        self.steel = [grow(r, 5) for r in self.hatches] + [grow(self.engine_hatch, 5), grow(self.roller, 22), grow(self.hauler, 12)]

    def steel_grip(self, p):
        """Footing at p: planks grip; wet steel does not."""
        if not any(rect_has(r, p) for r in self.steel):
            return 1.0
        return 1.0 - 0.55 * clamp(self.wet + self.flood, 0.0, 1.0)

    # --- walking routes: every level has its own map; links join them
    LINK_REACH = 45.0       # how close to a ladder or hatch a sailor must be to climb it by hand

    def _build_nav(self):
        L, B = self.length, self.beam
        main = NavMap((L, B), lambda p: in_poly(p, self.hull), self.walls, self.solids, 19.0, self.post, self.open_edges)
        wx, wy, ww, wh = self.wheelhouse
        floor = (wx + 3, wy + 3, ww - 6, wh - 6)
        # The lower deck uses the inboard hull footprint, with watertight bulkheads
        # forming real compartment boundaries. Door gaps and each room's own ladder
        # are the only intended routes between/into these spaces.
        below_walls = [(self.hull[i], self.hull[(i + 1) % len(self.hull)])
                       for i in range(len(self.hull))]
        # Watertight bulkheads cut the lower deck into compartments. Only the doors let people through,
        # so nobody can walk through the ice hold or the engine room on the way somewhere else.
        reach = B * 0.5 + 40.0
        for bx, door_y, door_w in self.bulkheads:
            if door_y is None:
                below_walls.append((V(bx, -reach), V(bx, reach)))
            else:
                below_walls.append((V(bx, -reach), V(bx, door_y - door_w * 0.5)))
                below_walls.append((V(bx, door_y + door_w * 0.5), V(bx, reach)))
        self.below_walls = below_walls
        below_inside = lambda p: in_poly(p, self.hull) and (-L * 0.47 < p.x < L * 0.47)
        self.maps = {
            Level.MAIN: main,
            Level.WHEELHOUSE: NavMap((L, B), lambda p: rect_has(floor, p), rect_walls(floor), [], 17.0),
            Level.BELOW: NavMap((L, B), below_inside, below_walls, self.below_solids, 17.0),
        }
        self.wheelhouse_floor = floor
        self.nav = main.nav

    def find_path(self, a, b, level=Level.MAIN, obstacles=()):
        return self.maps[level].find_path(a, b, obstacles)

    STATION_HIT_R = 22.0    # deck units: how close a right-click must be to count as "on" a station

    def station_at(self, p, radius=None):
        """(name, pos) of the wheelhouse station within `radius` of p, or None."""
        r = self.STATION_HIT_R if radius is None else radius
        best = None
        for name, pos in self.wheelhouse_stations.items():
            d = pos.distance_to(p)
            if d <= r and (best is None or d < best[2]):
                best = (name, pos, d)
        return (best[0], best[1]) if best else None

    def wheelhouse_floor_point(self, p):
        """p clamped into the walkable wheelhouse floor, inset by the nav clearance."""
        fx, fy, fw, fh = self.wheelhouse_floor
        m = 18.0
        return V(clamp(p.x, fx + m, fx + fw - m), clamp(p.y, fy + m, fy + fh - m))

    def wheelhouse_entry_space(self, goal, sailor):
        """Check that the wheelhouse landing is valid and not actively obstructed.

        The wheelhouse is small, but station occupants elsewhere in the room must not
        lock the entrance. Only a sailor physically using or standing in the doorway
        reserves it; reservations far from the door caused permanent deadlocks before.
        """
        goal = V(goal)
        if not rect_has(self.wheelhouse_floor, goal):
            return False
        nav = self.maps[Level.WHEELHOUSE]
        entry_link = next((lk for lk in self.links
                           if Level.MAIN in lk.ends and Level.WHEELHOUSE in lk.ends), None)
        if entry_link is None:
            return False
        entry = V(entry_link.pos(Level.WHEELHOUSE))
        if not nav.connected(entry, goal):
            return False

        door_clearance = 27.0
        for other in sailor.g.sailors:
            if other is sailor or other.mode in (other.DEAD, other.SWIMMING):
                continue
            occupied = []
            if other.ladder is not None:
                lk = other.ladder.get("link")
                if lk is not None and Level.WHEELHOUSE in lk.ends:
                    occupied.append(V(lk.pos(Level.WHEELHOUSE)))
            elif other.mode == other.ABOARD and other.level == Level.WHEELHOUSE:
                occupied.append(V(other.pos))
            if any(point.distance_to(entry) < door_clearance for point in occupied):
                return False
        return True

    @staticmethod
    def hatch_key_for_link(link):
        """Return the hatch state controlling a physical hatch link, or None for an open stair/wall."""
        if link.name in ("engine ladder", "engine-room companionway"):
            return "engine"
        if link.name == "hold ladder":
            # The ladder is physically aligned with the aft of the two hold covers.
            # It used to operate hold_2, which was the forward cover, leaving the
            # actual cover beside the ladder out of sync with the hatch graph.
            return "hold_1"
        return None

    def hatch_is_open(self, key):
        return bool(self.hatch_states.get(key, False))

    def hatch_interaction_points(self, level):
        """Accessible handles for the engine and hold hatch covers on the currently viewed level."""
        points = []
        if level == Level.MAIN:
            x, y, w, h = self.engine_hatch
            points.append(("engine", "engine-room hatch", V(x + w / 2, y + h / 2)))
            for i, r in enumerate(self.hatches):
                x, y, w, h = r
                key = "hold_%d" % (i + 1)
                points.append((key, "ice-hold hatch %d" % (i + 1), V(x + w / 2, y + h / 2)))
        elif level == Level.WHEELHOUSE:
            # The companionway to the forward cabin is a passage, not the watertight
            # engine-room cover; operating it must not change the engine hatch/bilge.
            pass
        else:
            # At the lower end, each compartment has its own hatch landing; the two hold covers
            # are also independently serviceable from inside the ice room.
            for link in self.links:
                key = self.hatch_key_for_link(link)
                if key and level in link.ends:
                    points.append((key, "engine-room hatch" if key == "engine" else "ice-hold hatch 2", V(link.pos(level))))
            for i, r in enumerate(self.hatches):
                x, y, w, h = r
                key = "hold_%d" % (i + 1)
                points.append((key, "ice-hold hatch %d" % (i + 1), V(x + w / 2, y + h / 2)))
        return points

    def next_link(self, la, lb, pos, goal):
        """The first ladder or hatch to take to get from (level la, pos) to (level lb, goal), or None.
        A tiny graph search: levels are nodes, links are edges, and walking to a link costs its distance."""
        best = [1e18, None]

        def go(level, p, cost, first, used):
            if level == lb and self.maps[level].connected(p, goal):
                tot = cost + p.distance_to(goal)
                if tot < best[0]:
                    best[0], best[1] = tot, first
            for lk in self.links:
                if level not in lk.ends or lk.name in used:
                    continue
                if not self.maps[level].connected(p, lk.pos(level)):      # a bulkhead between him and that ladder
                    continue
                o = lk.other(level)
                go(o, lk.pos(o), cost + p.distance_to(lk.pos(level)) + 60.0, first or lk, used | {lk.name})
        go(la, V(pos), 0.0, None, frozenset())
        return best[1]

    def link_near(self, level, pos, direction):
        """The ladder or hatch within reach that leads one level up (direction +1) or down (-1), or None."""
        best, bd = None, self.LINK_REACH
        for lk in self.links:
            if level not in lk.ends:
                continue
            o = lk.other(level)
            if (o - level) * direction <= 0:
                continue
            d = pos.distance_to(lk.pos(level))
            if d <= bd:
                best, bd = lk, d
        return best

    def hull_frame(self, p):
        """Nearest bit of rail to p: (point, along-the-rail direction, inward direction)."""
        best, best_d, best_i = V(0, 0), 1e18, 0
        n = len(self.hull)
        for i in range(n):
            c = closest_on_seg(p, self.hull[i], self.hull[(i + 1) % n])
            d = p.distance_to(c)
            if d < best_d:
                best, best_d, best_i = c, d, i
        ab = self.hull[(best_i + 1) % n] - self.hull[best_i]
        tan = ab.normalize() if ab.length() > 0 else V(1, 0)
        return best, tan, (-best).normalize() if best.length() > 0 else V(-1, 0)

    def spawn_wash(self, side, intensity, g, cx=None):
        """Green water over a rail. ``cx`` is where along the ship it came aboard (None = random)."""
        L, B = self.length, self.beam
        if side in ("stbd", "port"):
            if cx is None:
                cx = random.uniform(-L * 0.32, L * 0.38)
            cx = clamp(cx, -L * 0.34, L * 0.40)
            w = Wash(side, cx, random.uniform(170, 260) + 120 * intensity, B * (0.34 + 0.46 * intensity))
            ex, ey = (w.cx, B / 2 if side == "stbd" else -B / 2)
        else:
            w = Wash(side, 0, random.uniform(120, 200) + 60 * intensity, L * (0.08 + 0.12 * intensity))
            ex, ey = ((L / 2 - 40, 0) if side == "bow" else (-L / 2 + 5, 0))
        self.washes.append(w)
        if side == "stbd" and intensity > 0.6 and g.gaffs > 0 and random.random() < 0.3:
            g.gaffs -= 1
            g.crew.say("The sea took a gaff over the rail! %d left." % g.gaffs)
        self.wet = min(1.0, self.wet + 0.2 + 0.2 * intensity)
        FloodingModel.boarded(self, side, intensity)          # volume, list and freeboard feedback
        along = V(0, 1) if side in ("bow", "stern") else V(1, 0)
        for _ in range(26):                                   # spray
            pos = V(ex, ey) + along * random.uniform(-w.width / 2, w.width / 2)
            vel = w.dir * random.uniform(120, 340) + along * random.uniform(-40, 40)
            self.spray.append([pos, vel, 0.0, random.uniform(0.5, 1.0)])
        for _ in range(int(8 + 14 * intensity)):              # foam streaks carried across the planking
            pos = V(ex, ey) + along * random.uniform(-w.width / 2, w.width / 2) + w.dir * random.uniform(0, 36)
            self.deck_foam.append([pos, w.dir * random.uniform(150, 400) * (0.6 + 0.6 * intensity),
                                   0.0, random.uniform(3.5, 8.5), random.uniform(18, 64), random.uniform(2.5, 6.5)])
        del self.deck_foam[:-110]
        if intensity > 0.8 and g.time_since_wave_msg > 20:
            g.crew.say("A sea comes green over the %s!" % {"stbd": "starboard rail", "port": "port rail", "bow": "bow", "stern": "stern"}[side])
            g.time_since_wave_msg = 0.0

    def splash_out(self, strike):
        """Spray thrown up on the *outside* of the rail where a wave breaks against the hull."""
        e = strike.energy
        n = V(strike.nx, strike.ny)
        t = V(-strike.ny, strike.nx)
        base = V(strike.local_x, strike.local_y) + n * 6.0
        for _ in range(int(10 + 22 * e)):
            vel = n * random.uniform(60, 130 + 260 * e) + t * random.uniform(-90, 90)
            self.spray.append([base + t * random.uniform(-50, 50), vel, 0.0, random.uniform(0.45, 0.95)])
        del self.spray[:-260]

    def update_water(self, dt, g):
        strength = g.world.waves.strength
        sl = self.slope
        self.wet = max(self.wet - 0.02 * dt, 0.0)
        # Deck water drains through the scuppers inside FloodingModel.step below: head-driven,
        # choked as the hull settles, and reversed when the rail is awash.
        # Bilge seepage is slow with the engine hatch dogged shut. Leaving it open lets
        # green water from the wet deck enter the engine room; a high sea makes this costly.
        sea = clamp(strength, 0.0, 1.5)
        engine_inflow = 0.00025 + 0.0010 * sea + 0.00025 * self.flood
        if self.hatch_is_open("engine"):
            engine_inflow += 0.0016 + 0.0060 * sea + 0.0040 * self.flood
        self.engine_flood = clamp(self.engine_flood + engine_inflow * dt, 0.0, 1.0)
        # Open hold covers admit a little wash water too. Water in the ice room warms the
        # hold and consumes ice faster until the covers are shut and hands bail it out.
        open_hold_count = sum(1 for key in ("hold_1", "hold_2") if self.hatch_is_open(key))
        hold_inflow = 0.00004 * sea
        if open_hold_count:
            hold_inflow += open_hold_count * (0.0008 + 0.0035 * sea + 0.0020 * self.flood)
        self.hold_flood = clamp(self.hold_flood + hold_inflow * dt, 0.0, 1.0)
        # v13.2.05: scuppers, free-surface list, bilge pump and the flooding state machine.
        pump_power = 0.0
        if getattr(g, "engine_ok", False) and getattr(g, "fuel", 0.0) > 0.0:
            pump_power = clamp(getattr(g, "engine_power", 0.0), 0.0, 1.0)
        hull_waves = getattr(g.world, "hull_waves", None)
        immersion = max(hull_waves.immersion.values()) if hull_waves is not None else 0.0
        self.last_flood_report = FloodingModel.step(
            self, dt, sea=sea, slope_y=sl.y, engine_hatch_open=self.hatch_is_open("engine"),
            open_hold_hatches=open_hold_count, pump_power=pump_power, immersion=immersion)
        # Waves that actually reached the rail this step (detected by HullWaveInteraction).
        for st in getattr(g.world, "hull_strikes", ()):
            if st.kind == "overtop":
                self.spawn_wash(st.zone, st.energy, g, cx=st.local_x if st.zone in ("stbd", "port") else None)
            else:
                self.splash_out(st)
        for w in self.washes:
            w.age += dt
        self.washes = [w for w in self.washes if w.age < w.life]
        for p in self.spray:
            p[0] += p[1] * dt
            p[1] *= math.exp(-2.5 * dt)
            p[2] += dt
        self.spray = [p for p in self.spray if p[2] < p[3]]
        for f in self.deck_foam:                               # foam rides the sheet, then slows and fades
            f[0] += f[1] * dt
            f[1] *= math.exp(-1.7 * dt)
            f[2] += dt
        self.deck_foam = [f for f in self.deck_foam if f[2] < f[3] and self.on_deck(f[0])]

    def wash_push(self, p):
        """Sum of the sweep of every wash covering point p (a vector, 0 when dry)."""
        push = V(0, 0)
        for w in self.washes:
            if w.contains(self, p):
                push += w.dir * w.strength()
        return push

    def _draw_pool(self, g):
        """Standing deck water: it pools on the low side, so a listing ship visibly carries it to leeward."""
        S, ov = g.SS, g.ov_d
        hb = self.beam * 0.5
        f = clamp(self.flood, 0.0, 1.0)
        lat = clamp(self.list_lat, -1.0, 1.0) * min(1.0, f * 2.5)
        step = 14.0
        y = -hb
        while y < hb:
            ym = y + step * 0.5
            depth = clamp(f * 1.1 + lat * (ym / hb) * 0.6, 0.0, 1.0)
            if depth > 0.03:
                col = (50, 112, 162, int(34 + 104 * depth))
                for x0, x1 in self._scan(ym):
                    pygame.draw.polygon(ov, col, [S(V(x0, y)), S(V(x1, y)), S(V(x1, y + step)), S(V(x0, y + step))])
            y += step
        if f > 0.06:
            t = g.world.time
            line_a = int(120 * min(f * 1.6, 1.0))
            for k in range(7):
                x = -self.length * 0.45 + k * self.length * 0.15
                pts = [S(V(x + 14 * math.sin(t * 1.6 + k + j * 0.9) + 10 * lat * math.sin(t * 0.9 + j),
                           -hb * 0.9 + hb * 1.8 * j / 8)) for j in range(9)]
                pygame.draw.lines(ov, (190, 225, 245, line_a), False, pts, 2)

    def draw_water(self, g):
        S, ov = g.SS, g.ov_d
        hull = [S(p) for p in self.hull]
        if self.wet > 0.02:
            pygame.draw.polygon(ov, (15, 30, 45, int(95 * self.wet)), hull)
        if self.flood > 0.04:
            self._draw_pool(g)
        if abs(self.list_trim) > 0.04:
            # Heeled over, the low flank rolls into view: dark bottom paint above a ragged waterline.
            sign = 1.0 if self.list_trim > 0 else -1.0
            depth = 6.0 + 46.0 * min(1.0, abs(self.list_trim) / 0.5)
            flank = [p for p in self.hull if p.y * sign > 60.0]
            if len(flank) > 3:
                outer = [p + V(0, sign) * depth * clamp(p.y * sign / (self.beam * 0.5), 0.3, 1.0) for p in flank]
                pygame.draw.polygon(ov, (92, 40, 36, 200), [S(p) for p in flank + outer[::-1]])
                pygame.draw.lines(ov, (225, 240, 245, 150), False, [S(p) for p in outer], max(1, int(2 * g.zoom)))
        t = g.world.time
        for w in self.washes:
            x, y, ww, hh = w.rect(self)
            a = w.strength()
            quad = [S(V(x, y)), S(V(x + ww, y)), S(V(x + ww, y + hh)), S(V(x, y + hh))]
            pygame.draw.polygon(ov, (70, 130, 180, int(128 * a)), quad)
            fr = w.front(self)
            p0, p1 = V(fr[0]), V(fr[1])
            n = 10
            pts, roots = [], []
            for k in range(n + 1):
                base = p0.lerp(p1, k / n)
                jag = math.sin(t * 7.0 + k * 2.3 + w.cx * 0.01) * (5.0 + 9.0 * a) + math.sin(k * 5.1 + w.age * 3.0) * 4.0
                pts.append(S(base + w.dir * jag))
                roots.append(base)
            pygame.draw.lines(ov, (240, 248, 255, int(235 * a)), False, pts, max(2, int(5 * g.zoom)))
            for k in range(1, n, 2):                        # streaks trailing behind the breaking front
                ln = (34 + 70 * ((k * 37) % 11) / 11.0) * (0.4 + 0.6 * a)
                pygame.draw.line(ov, (225, 242, 250, int(150 * a)), S(roots[k]), S(roots[k] - w.dir * ln),
                                 max(1, int(2.5 * g.zoom)))
        for f in self.deck_foam:
            pos, vel, age, life, ln, wd = f
            fade = clamp(1.0 - age / life, 0.0, 1.0) ** 0.8 * clamp(age / 0.2, 0.0, 1.0)
            d = vel.normalize() if vel.length() > 6.0 else V(1, 0)
            pygame.draw.line(ov, (236, 247, 250, int(150 * fade)), S(pos), S(pos - d * ln * (0.5 + 0.5 * fade)),
                             max(1, int(wd * 0.5 * g.zoom)))
        for pos, vel, age, life in self.spray:
            pygame.draw.circle(ov, (240, 248, 255, int(200 * (1 - age / life))), S(pos), max(1, int(4 * g.zoom)))

    def _scan(self, y):
        xs = []
        n = len(self.hull)
        for i in range(n):
            a, b = self.hull[i], self.hull[(i + 1) % n]
            if (a.y <= y < b.y) or (b.y <= y < a.y):
                xs.append(a.x + (y - a.y) / (b.y - a.y) * (b.x - a.x))
        xs.sort()
        return list(zip(xs[0::2], xs[1::2]))

    def is_open(self, i):
        if i == len(self.hull) - 1:
            return True
        mid = (self.hull[i] + self.hull[i + 1]) * 0.5
        return any(rect_has(r, mid) for r in self.openings)

    def on_deck(self, p):
        return in_poly(p, self.hull)

    def nearest_hull_point(self, p):
        best, best_d = V(0, 0), 1e18
        n = len(self.hull)
        for i in range(n):
            c = closest_on_seg(p, self.hull[i], self.hull[(i + 1) % n])
            d = p.distance_to(c)
            if d < best_d:
                best, best_d = c, d
        return best

    def collide(self, pos, vel, r, level=Level.MAIN):
        return self.maps[level].collide(pos, vel, r)

    @staticmethod
    def _inset_poly(points, d):
        """A convex polygon moved inwards by d (mitred at the corners, with the mitre length capped)."""
        n = len(points)
        area = sum(points[i].x * points[(i + 1) % n].y - points[(i + 1) % n].x * points[i].y for i in range(n))
        sign = 1.0 if area > 0 else -1.0
        out = []
        for i in range(n):
            p0, p1, p2 = points[i - 1], points[i], points[(i + 1) % n]
            e1, e2 = p1 - p0, p2 - p1
            if e1.length() < 1e-6 or e2.length() < 1e-6:
                out.append(V(p1))
                continue
            e1, e2 = e1.normalize(), e2.normalize()
            n1, n2 = V(-e1.y, e1.x) * sign, V(-e2.y, e2.x) * sign
            bis = n1 + n2
            if bis.length() < 1e-6:
                out.append(p1 + n1 * d)
                continue
            bis = bis.normalize()
            out.append(p1 + bis * (d / max(0.35, bis.dot(n1))))
        return out

    @staticmethod
    def _clip_x(points, x0, x1):
        """A convex polygon clipped to the vertical strip x0 <= x <= x1."""
        def clip(pts, keep, cut):
            out = []
            for i in range(len(pts)):
                a, b = pts[i - 1], pts[i]
                ka, kb = keep(a), keep(b)
                if kb:
                    if not ka:
                        out.append(cut(a, b))
                    out.append(b)
                elif ka:
                    out.append(cut(a, b))
            return out

        def at(x):
            return lambda a, b: V(x, a.y + (b.y - a.y) * (x - a.x) / (b.x - a.x))
        pts = clip(list(points), lambda p: p.x >= x0, at(x0))
        return clip(pts, lambda p: p.x <= x1, at(x1)) if pts else []

    @staticmethod
    def _spans(points, axis, v):
        """Where the line axis == v (axis 1: y == v, axis 0: x == v) crosses a polygon, as (lo, hi) pairs."""
        a_i, b_i = (1, 0) if axis == 1 else (0, 1)
        hits = []
        n = len(points)
        for i in range(n):
            a, b = points[i], points[(i + 1) % n]
            pa, pb = (a.y, b.y) if axis == 1 else (a.x, b.x)
            if (pa <= v < pb) or (pb <= v < pa):
                qa, qb = (a.x, b.x) if axis == 1 else (a.y, b.y)
                hits.append(qa + (v - pa) / (pb - pa) * (qb - qa))
        hits.sort()
        return list(zip(hits[0::2], hits[1::2]))

    def _build_art(self):
        """Pre-compute the hull offsets and compartment floors that the renderers share."""
        L = self.length
        self.cap_poly = self._inset_poly(self.hull, 4.0)       # outer rail cap / sheer strake
        self.rail_poly = self._inset_poly(self.hull, 15.0)     # inside face of the bulwark
        self.floor_poly = self._inset_poly(self.hull, 11.0)    # lower deck: inside of the plating
        edges = [-L * 0.485] + [bx for bx, _, _ in self.bulkheads] + [L * 0.5]
        names = ["aft_stores", "engine_room", "ice_hold", "crew_quarters", "forepeak"]
        self.zone_polys = {name: self._clip_x(self.floor_poly, edges[i], edges[i + 1])
                           for i, name in enumerate(names)}

    def _stairs(self, g, a, b, width):
        """Outside companion steps up to the wheelhouse door: wooden treads between two cheeks."""
        S, z, s = g.SS, g.zoom, g.screen
        a, b = V(a), V(b)
        d = b - a
        ax = d.normalize()
        pr = V(-ax.y, ax.x)
        hw = width * 0.5
        quad = [S(a + pr * hw), S(b + pr * hw), S(b - pr * hw), S(a - pr * hw)]
        pygame.draw.polygon(s, hexc("#2a2f33"), quad)
        steps = 6
        for i in range(steps):
            t0, t1 = i / steps, (i + 0.78) / steps
            p0, p1 = a + d * t0, a + d * t1
            tread = [S(p0 + pr * (hw - 4)), S(p1 + pr * (hw - 4)), S(p1 - pr * (hw - 4)), S(p0 - pr * (hw - 4))]
            pygame.draw.polygon(s, mix(hexc("#8a7556"), hexc("#d7c8a4"), i / (steps - 1)), tread)
            pygame.draw.polygon(s, hexc("#4a3b28"), tread, 1)
        for side in (-1, 1):
            pygame.draw.line(s, hexc("#d8dcdf"), S(a + pr * hw * side), S(b + pr * hw * side), max(2, int(4 * z)))

    def _label_stack(self, g, anchor, lines, step=15):
        """Short labels stacked in screen space so they never collide whatever the zoom."""
        p = g.SS(anchor)
        for i, (text, col) in enumerate(lines):
            g.text(text, (p[0], p[1] + i * step), col)

    def _draw_lower_deck(self, g):
        """The below-deck plan: aft stores | engine room | ice hold | crew cabin | forepeak.

        Real athwartships bulkheads separate the compartments; the only openings are the watertight
        doors (aft stores, forepeak) and the ladders from the deck above. Nothing runs through the
        engine room or the ice hold.
        """
        s, z, S, ov = g.screen, g.zoom, g.SS, g.ov_d
        L, B = self.length, self.beam
        zp = self.zone_polys
        running = g.engine_running()
        label = (255, 235, 170)

        def sp(pts):
            return [S(p) for p in pts]

        def poly(r, grow=0.0):
            x, y, w, h = r
            x, y, w, h = x - grow, y - grow, w + 2 * grow, h + 2 * grow
            return [S(V(x, y)), S(V(x + w, y)), S(V(x + w, y + h)), S(V(x, y + h))]

        def line(col, a, b, w=1.0):
            pygame.draw.line(s, col, S(V(a)), S(V(b)), max(1, int(w * z)))

        def hatch_lines(zone, step, col, w=1.0, axis=1, skip=None):
            pts = zp[zone]
            lo = min(p.y if axis == 1 else p.x for p in pts)
            hi = max(p.y if axis == 1 else p.x for p in pts)
            v = math.ceil(lo / step) * step
            while v < hi:
                for a, b in self._spans(pts, axis, v):
                    if axis == 1:
                        line(col, (a, v), (b, v), w)
                    else:
                        line(col, (v, a), (v, b), w)
                v += step

        # ---- hull plating, then each compartment's floor
        pygame.draw.polygon(s, hexc("#1f282c"), sp(self.hull))
        pygame.draw.polygon(s, hexc("#8f8670"), sp(self.hull), max(2, int(3 * z)))
        ice_col = mix((92, 104, 112), (190, 218, 234), 0.7 * clamp(g.ice / ICE_CAP * 2.0, 0.0, 1.0))
        floors = {"aft_stores": hexc("#39413f"), "engine_room": hexc("#3e4648"), "ice_hold": ice_col,
                  "crew_quarters": hexc("#5b4a37"), "forepeak": hexc("#44423b")}
        for name, col in floors.items():
            pygame.draw.polygon(s, col, sp(zp[name]))
        hatch_lines("aft_stores", 18, hexc("#2f3634"))
        hatch_lines("engine_room", 14, hexc("#343c3e"))                       # steel floor plates
        hatch_lines("engine_room", 28, hexc("#343c3e"), axis=0)
        hatch_lines("crew_quarters", 14, hexc("#4b3c2b"))                     # timber floor
        hatch_lines("forepeak", 18, hexc("#3a3832"))
        hatch_lines("ice_hold", 20, mix(ice_col, (255, 255, 255), 0.12))
        # ---- frames (ribs) round the inside of the hull
        for frac in [i * 0.05 - 0.45 for i in range(19)]:
            xx = L * frac
            strip = self._clip_x(self.hull, xx - 1, xx + 1)
            if strip:
                lo, hi = min(p.y for p in strip), max(p.y for p in strip)
                for yy0, yy1 in ((lo, lo + 22), (hi - 22, hi)):
                    line(hexc("#58625f"), (xx, yy0), (xx, yy1), 3)

        # ---- ice hold: insulated pens either side of a clear aisle, filled with ice and fish
        frost = clamp(g.ice / ICE_CAP * 2.0, 0.0, 1.0)
        for pen in self.ice_bins:
            pygame.draw.polygon(s, hexc("#2e2a25"), poly(pen, 3))
            pygame.draw.polygon(s, mix(hexc("#6a6258"), hexc("#d7e8f0"), 0.35 + 0.55 * frost), poly(pen))
            pygame.draw.polygon(s, hexc("#9a8d78"), poly(pen), max(1, int(3 * z)))
            px, py, pw, ph = pen
            for k in (1, 2):                                                      # pen boards
                line(hexc("#9a8d78"), (px + pw * k / 3, py), (px + pw * k / 3, py + ph), 3)
            for k in range(1, 4):
                line(mix(hexc("#6a6258"), hexc("#ffffff"), 0.25), (px + 4, py + ph * k / 4), (px + pw - 4, py + ph * k / 4), 1)
        for i in range(min(len(g.hold), 30)):                                     # the catch below
            pen = self.ice_bins[i % 2]
            col, row = (i // 2) % 5, (i // 10) % 3
            fx = pen[0] + pen[2] * (0.10 + 0.16 * col) + (hash01(i, 3, 5) - 0.5) * 8
            fy = pen[1] + pen[3] * (0.2 + 0.28 * row) + (hash01(i, 7, 9) - 0.5) * 8
            pygame.draw.polygon(s, mix((120, 130, 138), (190, 200, 208), hash01(i, 1, 1)),
                                [S(V(fx + math.cos(TAU * j / 8) * 15, fy + math.sin(TAU * j / 8) * 6)) for j in range(8)])
        if g.ship.hold_flood > 0.02:
            a = int(120 * clamp(g.ship.hold_flood, 0.0, 1.0))
            pygame.draw.polygon(ov, (46, 116, 157, a), sp(zp["ice_hold"]))
            s.blit(ov, (0, 0))
            ov.fill((0, 0, 0, 0))

        # ---- engine room: main engine to port, aux generator, switchboard on the bulkhead
        er = self.below_rooms[0]
        eng = self.below_casing
        pygame.draw.polygon(s, hexc("#1b2123"), poly(eng, 6))                      # bed plate
        pygame.draw.polygon(s, hexc("#8b613a") if running else hexc("#2f3a3d"), poly(eng))
        pygame.draw.polygon(s, RAIL, poly(eng), max(1, int(3 * z)))
        ex, ey, ew, eh = eng
        pygame.draw.polygon(s, hexc("#556467") if not running else hexc("#a9794a"),
                            poly((ex + 8, ey + 8, ew - 52, eh - 16)))                  # rocker covers
        for k in range(6):
            cx0 = ex + 14 + k * (ew - 62) / 6.0
            pygame.draw.polygon(s, hexc("#2a3234"), poly((cx0, ey + 14, (ew - 62) / 6.0 - 8, eh - 28)))
            pygame.draw.polygon(s, hexc("#8d969a"), poly((cx0, ey + 14, (ew - 62) / 6.0 - 8, eh - 28)), 1)
        pygame.draw.polygon(s, hexc("#202628"), poly((ex + ew - 40, ey + 6, 34, eh - 12)))   # gearbox
        pygame.draw.polygon(s, STEEL, poly((ex + ew - 40, ey + 6, 34, eh - 12)), 1)
        pygame.draw.polygon(s, hexc("#2c3336"), poly((ex - 28, ey + eh * 0.5 - 7, 28, 14)))   # prop shaft, aft
        gen = self.below_generator
        pygame.draw.polygon(s, hexc("#1b2123"), poly(gen, 4))
        pygame.draw.polygon(s, hexc("#4d5d52"), poly(gen))
        pygame.draw.polygon(s, RAIL, poly(gen), max(1, int(2 * z)))
        gx0, gy0, gw, gh = gen
        pygame.draw.circle(s, hexc("#7f8c82"), S(V(gx0 + gw * 0.7, gy0 + gh * 0.5)), max(3, int(18 * z)))
        pygame.draw.circle(s, hexc("#2d3730"), S(V(gx0 + gw * 0.7, gy0 + gh * 0.5)), max(2, int(10 * z)))
        # switchboard with the three analogue gauges the engineer watches
        sb = self.below_switchboard
        pygame.draw.polygon(s, hexc("#2c3235"), poly(sb))
        pygame.draw.polygon(s, STEEL, poly(sb), max(1, int(2 * z)))
        readings = [("OIL", g.engine_oil), ("COOL", g.cooling_intake), ("SEAL", g.shaft_seal)]
        sx, sy, sw, sh = sb
        for i, (name, value) in enumerate(readings):
            by = sy + 10 + i * (sh - 14) / 3.0
            bar = (sx + 8, by + 12, sw - 16, 9)
            pygame.draw.polygon(s, (24, 26, 27), poly(bar))
            color = (185, 70, 55) if value < 25 else ((205, 160, 63) if value < 55 else (100, 165, 112))
            pygame.draw.polygon(s, color, poly((bar[0], bar[1], bar[2] * clamp(value / 100.0, 0.0, 1.0), bar[3])))
            pygame.draw.polygon(s, STEEL, poly(bar), 1)
            if z >= 0.45:
                g.text("%s %02d" % (name, round(value)), S(V(sx + 6, by - 4)), (248, 238, 208))
        if g.ship.engine_flood > 0.02:
            a = int(130 * clamp(g.ship.engine_flood, 0.0, 1.0))
            pygame.draw.polygon(ov, (46, 116, 157, a), sp(zp["engine_room"]))
            s.blit(ov, (0, 0))
            ov.fill((0, 0, 0, 0))

        # ---- aft stores: racks of line, spare gear and drums
        for rk in self.stores_racks:
            pygame.draw.polygon(s, hexc("#4a3d2e"), poly(rk))
            pygame.draw.polygon(s, hexc("#9a8c72"), poly(rk), max(1, int(2 * z)))
            rx, ry, rw_, rh_ = rk
            for k in range(1, 4):
                line(hexc("#9a8c72"), (rx, ry + rh_ * k / 4), (rx + rw_, ry + rh_ * k / 4), 1)
            pygame.draw.circle(s, hexc("#b79b6a"), S(V(rx + rw_ * 0.5, ry + rh_ * 0.38)), max(3, int(14 * z)), max(2, int(5 * z)))

        # ---- crew cabin: six full-length berths (heads forward), lockers, and the stair landing
        for i, r in enumerate(self.bunks):
            x0, y0, bw, bh = r
            pygame.draw.polygon(s, hexc("#2e2419"), poly(r, 3))
            pygame.draw.polygon(s, hexc("#6b5236"), poly(r))
            pygame.draw.polygon(s, hexc("#a99576"), poly(r), max(1, int(2 * z)))
            mat = (x0 + 5, y0 + 5, bw - 10, bh - 10)
            pygame.draw.polygon(s, hexc("#b9b4a0"), poly(mat))
            pygame.draw.polygon(s, hexc("#7e7966"), poly(mat), max(1, int(z)))
            for k in range(1, 5):
                line(hexc("#a39e8a"), (x0 + 5 + (bw - 10) * k / 5.0, y0 + 5), (x0 + 5 + (bw - 10) * k / 5.0, y0 + bh - 5), 1)
            pillow = (x0 + bw - 28, y0 + 9, 20, bh - 18)                                # head end is forward (+x)
            pygame.draw.polygon(s, hexc("#eee6d2"), poly(pillow))
            pygame.draw.polygon(s, hexc("#b4ab94"), poly(pillow), max(1, int(z)))
        cq = self.crew_quarters
        for side in (-1, 1):                                                          # lockers on the bulkheads
            ly = -B * 0.40 if side < 0 else B * 0.40 - 30
            pygame.draw.polygon(s, hexc("#4a3d2e"), poly((cq[0] + 6, ly, 34, 30)))
            pygame.draw.polygon(s, hexc("#9a8c72"), poly((cq[0] + 6, ly, 34, 30)), 1)

        # ---- forepeak: chain locker and stores
        fp = self.below_forepeak
        chain_centre = V(fp[0] + fp[2] * 0.70, fp[1] + fp[3] * 0.5)
        pygame.draw.circle(s, hexc("#2b2a26"), S(chain_centre), max(4, int(46 * z)))
        for ci in range(7):
            a = ci * 0.9
            cc = S(chain_centre + V(math.cos(a), math.sin(a)) * (4 + ci * 5.5))
            pygame.draw.circle(s, STEEL, cc, max(3, int(8 * z)), max(1, int(2 * z)))
        pygame.draw.polygon(s, hexc("#4a3d2e"), poly((fp[0] + 12, fp[1] + 28, 40, 44)))
        pygame.draw.polygon(s, hexc("#9a8c72"), poly((fp[0] + 12, fp[1] + 28, 40, 44)), 1)

        # ---- bulkheads: solid steel with watertight doors where people may pass
        for bx, door_y, door_w in self.bulkheads:
            strip = self._clip_x(self.hull, bx - 1, bx + 1)
            if not strip:
                continue
            lo, hi = min(p.y for p in strip), max(p.y for p in strip)
            col = hexc("#b5ac94")
            if door_y is None:
                line(col, (bx, lo + 6), (bx, hi - 6), 7)
                line(hexc("#6f6957"), (bx, lo + 6), (bx, hi - 6), 2)
            else:
                d0, d1 = door_y - door_w * 0.5, door_y + door_w * 0.5
                line(col, (bx, lo + 6), (bx, d0), 7)
                line(col, (bx, d1), (bx, hi - 6), 7)
                for yy in (d0, d1):
                    pygame.draw.circle(s, hexc("#d9d1b8"), S(V(bx, yy)), max(3, int(6 * z)))
                leaf_end = V(bx + 8, d0) + V(math.cos(1.0), math.sin(1.0)) * (door_w * 0.55)
                pygame.draw.line(s, hexc("#7f8a8e"), S(V(bx, d0)), S(leaf_end), max(2, int(5 * z)))   # door standing open

        # ---- ladders and stairwells, drawn at full size (66 x 54) where each one lands
        hatch_panels = [("engine", self.engine_hatch, "ENGINE ACCESS"),
                        ("hold_1", self.hatches[0], "HOLD 1"),
                        ("hold_2", self.hatches[1], "HOLD 2")]
        for key, r, title in hatch_panels:
            x0, y0, ww, hh = r
            is_open = self.hatch_is_open(key)
            panel = (x0 + ww * 0.1, y0 + hh * 0.1, ww * 0.8, hh * 0.8)
            ov_col = (14, 22, 26, 150) if is_open else (96, 112, 120, 120)
            pygame.draw.polygon(ov, ov_col, poly(panel))
            s.blit(ov, (0, 0))
            ov.fill((0, 0, 0, 0))
            pygame.draw.polygon(s, GOLD if is_open else STEEL, poly(panel), max(1, int(2 * z)))
            if z >= 0.45 and key == "hold_2":
                g.text("HOLD 2 %s" % ("OPEN" if is_open else "DOGGED"), S(V(x0 + 2, y0 - 18)),
                       (255, 174, 101) if is_open else (222, 216, 196))
        for lk in self.links:
            if Level.BELOW in lk.ends and lk.kind == "hatch":
                self._ladder(g, lk.pos(Level.BELOW), 66, 54)
                if z >= 0.45:
                    hk = self.hatch_key_for_link(lk)
                    lines = [(lk.name.upper().replace("CREW COMPANIONWAY", "CREW STAIRS"), (200, 230, 255))]
                    if hk:
                        op = self.hatch_is_open(hk)
                        lines.append(("HATCH %s" % ("OPEN" if op else "DOGGED"),
                                      (255, 174, 101) if op else (222, 216, 196)))
                    self._label_stack(g, lk.pos(Level.BELOW) + (V(-122, 30) if lk.name == "engine ladder" else V(-36, 36)), lines)

        # ---- compartment names and live readouts (stacked in screen space, so they never overlap)
        if z >= 0.40:
            self._label_stack(g, V(L * -0.466, -B * 0.43), [("STORES", label)])
            self._label_stack(g, V(er[0] + 12, -B * 0.43), [
                ("ENGINE ROOM", label),
                ("ENGINE TRIPPED" if not g.engine_ok else ("ENGINE RUNNING" if running else "ENGINE STOPPED"),
                 (255, 120, 100) if not g.engine_ok else (214, 226, 205)),
                ("BILGE %.0f%%" % (100 * g.ship.engine_flood),
                 (255, 160, 116) if g.ship.engine_flood > 0.45 else (214, 226, 205))])
            ice_room = self.below_rooms[1]
            self._label_stack(g, V(ice_room[0] + 12, -B * 0.43), [
                ("ICE HOLD", label),
                ("HOLD WATER %.0f%%" % (100 * g.ship.hold_flood),
                 (255, 160, 116) if g.ship.hold_flood > 0.25 else (214, 226, 205))])
            self._label_stack(g, V(cq[0] + 52, -B * 0.43), [("CREW CABIN  -  SIX BERTHS", (240, 222, 188))])
            self._label_stack(g, V(fp[0] + 10, fp[1] + 6), [("FOREPEAK", label), ("CHAIN LOCKER", (214, 226, 205))])

    def _ladder(self, g, centre, length, width, axis=(1.0, 0.0), alpha=255, rung=9.0, rail_col=None):
        """A ladder / companion stair: two stringers with evenly spaced treads, centred on `centre`.

        length runs along `axis`; width is the clear width between stringers. A sailor is ~70 units
        across, so the standard well is 66 x 54.
        """
        S, z, s = g.SS, g.zoom, g.screen
        c, ax = V(centre), V(axis).normalize()
        pr = V(-ax.y, ax.x)
        hl, hw = length * 0.5, width * 0.5
        rail_col = rail_col or hexc("#aeb5ba")
        surf = s if alpha >= 255 else g.ov_d
        ca = (lambda col: col) if alpha >= 255 else (lambda col: tuple(col[:3]) + (alpha,))
        for side in (-1, 1):                                          # stringers with a lit edge
            a, b = c - ax * hl + pr * (hw * side), c + ax * hl + pr * (hw * side)
            pygame.draw.line(surf, ca(hexc("#2a2f33")), S(a + pr * side * 1.5), S(b + pr * side * 1.5), max(2, int(7 * z)))
            pygame.draw.line(surf, ca(rail_col), S(a), S(b), max(1, int(4 * z)))
        steps = max(3, int(length / rung))
        for i in range(steps + 1):
            t = -hl + length * i / steps
            a, b = c + ax * t - pr * hw, c + ax * t + pr * hw
            pygame.draw.line(surf, ca(hexc("#2a2f33")), S(a + ax * 1.5), S(b + ax * 1.5), max(2, int(4 * z)))
            pygame.draw.line(surf, ca(hexc("#c3c9cc")), S(a), S(b), max(1, int(2.5 * z)))
        if alpha < 255:
            s.blit(g.ov_d, (0, 0))
            g.ov_d.fill((0, 0, 0, 0))

    def draw_level_view(self, g, vl):
        """Draw a localized wheelhouse roof cutaway or a veiled below-deck section.

        The wheelhouse is a cutaway in the same top-down ship view, not a second
        vertically offset ship. Crew still use Level.WHEELHOUSE for navigation and
        station ownership; only the rendering is integrated with the main deck.
        """
        s, z, S, ov = g.screen, g.zoom, g.SS, g.ov_d
        # Geometry dimensions are required by both the wheelhouse and lower-deck
        # renderers. Keep them local here; using bare L/B caused a NameError as
        # soon as the lower-deck cutaway tried to draw its frames/hallway.
        L, B = self.length, self.beam
        if vl != Level.WHEELHOUSE:
            pygame.draw.polygon(ov, (6, 12, 24, 215), [S(p) for p in self.hull])
            s.blit(ov, (0, 0))
            ov.fill((0, 0, 0, 0))
        # For Level.WHEELHOUSE, leave the surrounding main deck unobscured. The
        # floor/window/wall artwork drawn below replaces only the roof footprint.

        def poly(r):
            x, y, w, h = r
            return [S(V(x, y)), S(V(x + w, y)), S(V(x + w, y + h)), S(V(x, y + h))]

        label = (255, 235, 170)
        if vl == Level.WHEELHOUSE:
            x, y, w, h = self.wheelhouse
            fl = self.wheelhouse_floor
            pygame.draw.polygon(s, hexc("#8a7f6a"), poly(fl))
            for k in range(1, 8):
                xx = fl[0] + fl[2] * k / 8
                pygame.draw.line(s, hexc("#776d5a"), S(V(xx, fl[1])), S(V(xx, fl[1] + fl[3])), 1)
            # Forward glazing: clear of the bow spray line, with stout 1960s framing.
            pygame.draw.polygon(s, hexc("#27414f"), poly((x + w - 12, y + 8, 6, h - 16)))
            for yy in (y + h * 0.33, y + h * 0.66):
                pygame.draw.line(s, STEEL, S(V(x + w - 14, yy)), S(V(x + w - 2, yy)), max(1, int(2 * z)))
            pygame.draw.polygon(s, RAIL, poly((x, y, w, h)), 4)

            stations = self.wheelhouse_stations
            # Wooden console and binnacle.
            helm = S(stations["helm"])
            radius = max(5, int(14 * z))
            pygame.draw.circle(s, hexc("#3a281c"), helm, radius + max(1, int(3 * z)))
            pygame.draw.circle(s, STEEL, helm, radius, max(1, int(2 * z)))
            pygame.draw.circle(s, hexc("#303238"), helm, max(2, int(3 * z)))
            for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                pygame.draw.line(s, STEEL, helm + V(0, 0), helm + V(radius - 1, 0).rotate_rad(a), max(1, int(2 * z)))
            g.text("HELM", S(stations["helm"]) + V(-10, 15), (248, 238, 208))

            # Magnetic compass: heading shown is a bearing, not a fictitious electronic fix.
            cp = S(stations["compass"])
            cr = max(5, int(10 * z))
            pygame.draw.circle(s, hexc("#c7b77c"), cp, cr)
            pygame.draw.circle(s, hexc("#292c2d"), cp, cr, max(1, int(2 * z)))
            bearing = (math.degrees(g.world.heading) + 90.0) % 360.0
            needle = V(0, -cr + max(2, int(2 * z))).rotate_rad(-g.world.heading)
            pygame.draw.line(s, RED, cp, cp + needle, max(1, int(2 * z)))
            pygame.draw.circle(s, (230, 225, 205), cp, max(1, int(2 * z)))
            g.text("HDG %03d" % int(bearing), S(stations["compass"]) + V(-65, 5), (248, 238, 208))

            # Mechanical throttle quadrant, neutral-to-full ahead; no electronic engine display.
            tp = S(stations["throttle"])
            tw, th = max(10, int(22 * z)), max(8, int(16 * z))
            pygame.draw.rect(s, hexc("#4b4030"), (int(tp.x - tw // 2), int(tp.y - th // 2), tw, th), border_radius=2)
            pygame.draw.rect(s, STEEL, (int(tp.x - tw // 2), int(tp.y - th // 2), tw, th), 1, border_radius=2)
            lever_end = tp + V(0, -th * 0.36).rotate_rad(-g.world.throttle * 1.35)
            pygame.draw.line(s, hexc("#c9b88b"), tp, lever_end, max(2, int(3 * z)))
            pygame.draw.circle(s, RED, (int(lever_end.x), int(lever_end.y)), max(2, int(3 * z)))
            g.text("ENGINE ORDER", S(stations["throttle"]) + V(-48, -3), (248, 238, 208))
            g.text(g.world.engine_order_text(), S(stations["throttle"]) + V(-48, 17), (255, 211, 126))

            # Vacuum-tube AM/SSB wireless set: knobs, dial and warm valve glow.
            rp = S(stations["radio"])
            rw, rh = max(15, int(32 * z)), max(8, int(17 * z))
            pygame.draw.rect(s, hexc("#292a29"), (int(rp.x - rw // 2), int(rp.y - rh // 2), rw, rh), border_radius=2)
            pygame.draw.rect(s, STEEL, (int(rp.x - rw // 2), int(rp.y - rh // 2), rw, rh), 1, border_radius=2)
            pygame.draw.rect(s, hexc("#7e8b79"), (int(rp.x - rw * 0.34), int(rp.y - rh * 0.28), max(1, int(rw * 0.40)), max(1, int(rh * 0.42))), 1)
            pygame.draw.circle(s, hexc("#c79b48"), (int(rp.x + rw * 0.28), int(rp.y)), max(2, int(2.5 * z)))
            pygame.draw.circle(s, hexc("#c79b48"), (int(rp.x + rw * 0.28), int(rp.y + rh * 0.22)), max(2, int(2.5 * z)))
            g.text("AM / SSB 2182", S(stations["radio"]) + V(-23, 25), (248, 238, 208))
            g.text("WHEELHOUSE", S(V(x + 6, y + 3)), label)
            for lk in self.links:
                if Level.WHEELHOUSE in lk.ends:
                    a = lk.pos(Level.WHEELHOUSE)
                    g.text("stairs down", S(a + V(-26, 24)), (200, 230, 255))
        else:
            self._draw_lower_deck(g)

    def draw(self, g):
        s, z, S = g.screen, g.zoom, g.SS      # SS = ship frame, includes the rocking

        def poly(r, grow=0.0):
            x, y, w, h = r
            x, y, w, h = x - grow, y - grow, w + 2 * grow, h + 2 * grow
            return [S(V(x, y)), S(V(x + w, y)), S(V(x + w, y + h)), S(V(x, y + h))]

        def box(r, fill, edge=None, ew=2, grow=0.0):
            p = poly(r, grow)
            pygame.draw.polygon(s, fill, p)
            if edge:
                pygame.draw.polygon(s, edge, p, ew)
            return p

        def ln(col, a, b, w=1.0):
            pygame.draw.line(s, col, S(V(a)), S(V(b)), max(1, int(w * z)))

        n = len(self.hull)
        # ---- hull, deck planking, bulwarks
        pygame.draw.polygon(s, DECK, [S(p) for p in self.hull])
        for k, (x0, x1, y) in enumerate(self.planks):
            pygame.draw.line(s, PLANK if k % 2 == 0 else mix(PLANK, DECK, 0.45), S(V(x0, y)), S(V(x1, y)), 1)
            bx = x0 + 40 + hash01(k, 11, 3) * 90                                   # staggered butt joints
            while bx < x1 - 10:
                pygame.draw.line(s, PLANK, S(V(bx, y)), S(V(bx, y + 17)), 1)
                bx += 150 + hash01(k, int(bx), 5) * 120
        bulwark, cap = hexc("#d6cfba"), hexc("#5a4028")
        for i in range(n):
            if self.is_open(i):
                continue
            h0, h1 = self.hull[i], self.hull[(i + 1) % n]
            c0, c1 = self.cap_poly[i], self.cap_poly[(i + 1) % n]
            r0, r1 = self.rail_poly[i], self.rail_poly[(i + 1) % n]
            pygame.draw.polygon(s, cap, [S(h0), S(h1), S(c1), S(c0)])
            pygame.draw.polygon(s, bulwark, [S(c0), S(c1), S(r1), S(r0)])
            pygame.draw.line(s, hexc("#8c846f"), S(r0), S(r1), max(1, int(2 * z)))
            pygame.draw.line(s, hexc("#8a6a46"), S(h0), S(h1), max(1, int(2 * z)))
            seg = h1 - h0
            if seg.length() > 8:                                                   # freeing ports in the bulwark
                mid = (c0 + c1 + r0 + r1) * 0.25
                nrm = V(-seg.y, seg.x).normalize()
                inward = -1.0 if nrm.dot(-mid) < 0 else 1.0
                pygame.draw.line(s, hexc("#4b4638"), S(mid - nrm * inward * 4), S(mid + nrm * inward * 4), max(1, int(3 * z)))
        # open edges: the stern sill and the starboard gate (posts and a chain)
        open_pts = [i for i in range(n) if self.is_open(i) and i != n - 1]
        if open_pts:
            first, last = self.hull[open_pts[0]], self.hull[(open_pts[-1] + 1) % n]
            for post in (first, last):
                pygame.draw.circle(s, STEEL, S(post), max(3, int(9 * z)))
                pygame.draw.circle(s, RAIL, S(post), max(2, int(4 * z)))
            for k, drop in enumerate((10.0, 26.0)):
                pts = [S(first.lerp(last, t / 8.0) + V(0, -drop - 7 * math.sin(math.pi * t / 8.0))) for t in range(9)]
                pygame.draw.lines(s, GOLD if k == 0 else STEEL, False, pts, max(1, int(2 * z)))
        sill_a, sill_b = self.hull[n - 1], self.hull[0]
        pygame.draw.line(s, hexc("#555b60"), S(sill_a + V(6, 0)), S(sill_b + V(6, 0)), max(3, int(10 * z)))
        pygame.draw.line(s, STEEL, S(sill_a + V(6, 0)), S(sill_b + V(6, 0)), max(1, int(3 * z)))

        line = getattr(g, "line", None)
        roller_fill = (RED if line and line.roller_jammed else
                       (GOLD if line and line.roller_bypassed else STEEL))
        box(self.roller, roller_fill)   # roller color is a live gear-state indicator
        pygame.draw.line(s, RAIL, S(V(self.roller[0] + 5, self.roller[1])), S(V(self.roller[0] + 5, self.roller[1] + self.roller[3])), 1)
        if line is not None and z >= 0.46:
            roller_label = ("ROLLER JAMMED" if line.roller_jammed else
                            ("ROLLER BYPASSED" if line.roller_bypassed else "ROLLER OK"))
            roller_color = RED if line.roller_jammed else (GOLD if line.roller_bypassed else (222, 224, 212))
            g.text(roller_label, S(V(-self.length * 0.48, -self.beam * 0.16)), roller_color)

        # ---- ice-hold hatches: timber boards under a tarpaulin edge, steel dogs
        frost = clamp(g.ice / ICE_CAP * 2.0, 0.0, 1.0)
        for i, r in enumerate(self.hatches):
            key = "hold_%d" % (i + 1)
            is_open = self.hatch_is_open(key)
            box(r, COAMING, RAIL, 1, grow=6)
            p = box(r, (hexc("#0f1519") if is_open else mix(hexc("#5b4731"), hexc("#b9d6e6"), 0.35 * frost)), RAIL)
            x0, y0, ww, hh = r
            if is_open:
                for q in (0.25, 0.5, 0.75):
                    ln(hexc("#222c31"), (x0 + 6, y0 + hh * q), (x0 + ww - 6, y0 + hh * q), 1)
            else:
                for k in range(1, 6):                                              # hatch boards
                    ln(hexc("#44341f"), (x0, y0 + hh * k / 6.0), (x0 + ww, y0 + hh * k / 6.0), 1)
                for k in (0.22, 0.78):                                             # battens + dogs
                    ln(hexc("#3a2d1c"), (x0 + ww * k, y0 + 2), (x0 + ww * k, y0 + hh - 2), 3)
                    for q in (0.2, 0.5, 0.8):
                        pygame.draw.circle(s, STEEL, S(V(x0 + ww * k, y0 + hh * q)), max(1, int(3 * z)))
            if z >= 0.42:
                label_col = (255, 180, 95) if is_open else (230, 224, 201)
                g.text("H%d %s" % (i + 1, "OPEN" if is_open else "SHUT"),
                       S(V(r[0] - 2, r[1] + r[3] + 8)), label_col)
        hold_link = next((lk for lk in self.links if lk.name == "hold ladder"), None)
        if hold_link is not None:
            self._ladder(g, hold_link.pos(Level.MAIN), 66, 54, alpha=255 if self.hatch_is_open("hold_1") else 70)

        # ---- engine-room hatch (skylight grating over the engine) with its ladder well
        running = g.engine_running()
        engine_open = self.hatch_is_open("engine")
        box(self.engine_hatch, COAMING, RAIL, 1, grow=6)
        p = box(self.engine_hatch, hexc("#11181b") if engine_open else ((104, 54, 28) if running else (44, 47, 51)), RAIL)
        ex, ey, ew, eh = self.engine_hatch
        for k in range(1, 9):
            ln((90, 96, 102) if not engine_open else (60, 70, 76), (ex + ew * k / 9.0, ey + 3), (ex + ew * k / 9.0, ey + eh - 3), 2)
        engine_link = next((lk for lk in self.links if lk.name == "engine ladder"), None)
        if engine_link is not None:
            self._ladder(g, engine_link.pos(Level.MAIN), 66, 54, alpha=255 if engine_open else 70)
        engine_label = "ENGINE HATCH OPEN" if engine_open else ("ENGINE FAULT" if not g.engine_ok else ("ENGINE RUNNING" if running else "ENGINE HATCH SHUT"))
        g.text(engine_label, S(V(self.engine_hatch[0] - 10, self.engine_hatch[1] - 26)),
               (255, 140, 90) if engine_open or not g.engine_ok else (255, 235, 170))

        # ---- bait boxes: slatted crates with rope handles
        for r in self.bait_boxes:
            p = box(r, hexc("#7a6a52"), RAIL)
            bx, by, bw, bh = r
            for k in range(1, 5):
                ln(hexc("#5b4e3a"), (bx, by + bh * k / 5.0), (bx + bw, by + bh * k / 5.0), 1)
            box((bx + 6, by + 6, bw - 12, bh - 12), hexc("#8b7a5f"), hexc("#4f4332"), 1)
            ln(hexc("#d7c8a4"), (bx + bw * 0.35, by + bh * 0.5), (bx + bw * 0.65, by + bh * 0.5), 3)
        hx, hy, hw, hh = self.hatches[1]
        g.text("HOLD %d  ICE %d" % (len(g.hold), int(g.ice)), V(S(V(hx - 6, hy + hh + 24))), (255, 235, 170))

        # ---- bow: mooring bitts, hawse pipes and the anchor
        for bp in self.bitts:
            pygame.draw.circle(s, hexc("#1d2023"), S(bp), max(4, int(15 * z)))
            pygame.draw.circle(s, RAIL, S(bp), max(3, int(11 * z)))
            pygame.draw.circle(s, STEEL, S(bp), max(2, int(7 * z)))
        ap, iron = self.anchor_pos, (74, 78, 84)
        pygame.draw.line(s, iron, S(ap + V(-26, 0)), S(ap + V(26, 0)), max(2, int(6 * z)))
        pygame.draw.line(s, iron, S(ap + V(-17, -18)), S(ap + V(-17, 18)), max(2, int(5 * z)))
        pygame.draw.polygon(s, iron, [S(ap + V(29, 0)), S(ap + V(10, -18)), S(ap + V(10, 18))])
        pygame.draw.circle(s, iron, S(ap + V(-30, 0)), max(2, int(7 * z)), 2)

        # ---- cutting table
        tx, ty, tw, th = self.table
        box(self.table, mix(hexc("#a9aeb2"), (150, 30, 30), 0.7 * clamp(g.table_blood, 0.0, 1.0)), RAIL)
        box((tx + 4, ty + 4, tw - 8, th - 8), mix(hexc("#c3c8cb"), (150, 30, 30), 0.6 * clamp(g.table_blood, 0.0, 1.0)), None)
        pygame.draw.line(s, (120, 125, 130), S(V(tx + 4, ty + th * 0.5)), S(V(tx + tw - 4, ty + th * 0.5)), 1)
        pygame.draw.circle(s, hexc("#2a3033"), S(V(tx + tw - 10, ty + th * 0.5)), max(2, int(4 * z)))   # drain
        for i, c in enumerate(g.table.raw):
            fx, fy = tx + tw * (i + 0.5) / g.table.CAP, ty + th * 0.5
            pygame.draw.polygon(s, mix((150, 148, 130), (176, 186, 194), clamp(c.quality, 0.0, 1.0)),
                                [S(V(fx + math.cos(TAU * j / 10) * 9, fy + math.sin(TAU * j / 10) * 4)) for j in range(10)])
            if c.bled:
                pygame.draw.circle(s, (165, 40, 40), S(V(fx - 8, fy)), max(1, int(2 * z)))
            if c.gutted:
                pygame.draw.line(s, (235, 205, 195), S(V(fx - 6, fy + 1)), S(V(fx + 6, fy + 1)), 1)
        g.text("CUTTING TABLE", V(S(V(tx - 6, ty + th + 4))), (255, 235, 170))

        # ---- seawater hose reel
        hose = S(self.hose_station)
        pygame.draw.circle(s, hexc("#2a3a40"), hose, max(5, int(13 * z)))
        pygame.draw.circle(s, hexc("#3f6a5a"), hose, max(4, int(10 * z)), max(1, int(4 * z)))
        pygame.draw.circle(s, STEEL, hose, max(2, int(4 * z)))
        if z >= 0.42:
            g.text("SEAWATER HOSE [F]", hose + V(12, -8), (210, 230, 229))
        hose_user = next((person for person in g.sailors
                          if person.deck_action is not None and person.deck_action.get("kind") == "hose"), None)
        if hose_user is not None:
            pygame.draw.line(s, hexc("#8dc8d8"), S(hose_user.pos), hose, max(2, int(3 * z)))
            pygame.draw.line(s, hexc("#d0f0f6"), hose, S(V(self.table[0] + self.table[2] * 0.5,
                                                              self.table[1] + self.table[3] * 0.5)), max(2, int(2 * z)))

        # ---- lifeboat on davits, port side
        if g.rescue_boat_state is None or g.rescue_boat_state.get("phase") == "launching":
            bx, by, bw, bh = self.lifeboat
            cx, cy = bx + bw * 0.5, by + bh * 0.5

            def boat(scale):
                pts = []
                for k in range(28):
                    a = TAU * k / 28
                    ca, sa = math.cos(a), math.sin(a)
                    pts.append(S(V(cx + ca * bw * 0.5 * scale,
                                   cy + sa * bh * 0.5 * scale * (1.0 - 0.55 * abs(ca) ** 3))))
                return pts
            pygame.draw.polygon(s, hexc("#d9d2bd"), boat(1.0))
            pygame.draw.polygon(s, RED, boat(1.0), max(2, int(3 * z)))
            pygame.draw.polygon(s, hexc("#c4672f"), boat(0.82))
            for k in (-0.28, 0.0, 0.28):                                            # thwarts
                ln(hexc("#6c4a2c"), (cx + bw * k, cy - bh * 0.38), (cx + bw * k, cy + bh * 0.38), 3)
            ln(hexc("#6c4a2c"), (cx - bw * 0.42, cy), (cx + bw * 0.42, cy), 1)
            for dxr in (-0.34, 0.34):                                                # davit arms to the rail
                pygame.draw.line(s, STEEL, S(V(cx + bw * dxr, cy - bh * 0.5)), S(V(cx + bw * dxr, by - 12)), max(2, int(4 * z)))
                pygame.draw.circle(s, STEEL, S(V(cx + bw * dxr, by - 12)), max(2, int(5 * z)))

        # ---- starboard-quarter line hauler
        box(self.hauler, COAMING, RAIL, 1, grow=12)      # the hauler's steel base
        p = box(self.hauler, STEEL, RAIL)
        drum_center = S(V(self.hauler[0] + self.hauler[2] / 2, self.hauler[1] + self.hauler[3] / 2))
        slip = clamp(getattr(g.line, "hauler_slip", 0.0), 0.0, 1.0)
        drum_color = mix(RAIL, RED, slip)
        pygame.draw.circle(s, drum_color, drum_center, max(2, int(self.hauler[3] * 0.35 * z)))
        pygame.draw.circle(s, hexc("#c9b88b"), drum_center, max(2, int(self.hauler[3] * 0.18 * z)), max(1, int(2 * z)))
        for bolt in ((self.hauler[0] - 8, self.hauler[1] - 8), (self.hauler[0] + self.hauler[2] + 8, self.hauler[1] - 8),
                     (self.hauler[0] - 8, self.hauler[1] + self.hauler[3] + 8), (self.hauler[0] + self.hauler[2] + 8, self.hauler[1] + self.hauler[3] + 8)):
            pygame.draw.circle(s, hexc("#444a4f"), S(V(bolt)), max(1, int(3 * z)))
        if z >= 0.46 and slip >= 0.18:
            g.text("DRUM SLIP %d%%" % round(slip * 100), S(V(self.hauler[0] - 15, self.hauler[1] - 20)), RED)

        # ---- crew companionway (open stairwell abaft the wheelhouse) and the wheelhouse steps
        cw = self.companionway
        box(cw, COAMING, RAIL, 1, grow=6)
        box(cw, hexc("#0d1215"), RAIL)
        crew_link = next((lk for lk in self.links if lk.name == "crew companionway"), None)
        if crew_link is not None:
            self._ladder(g, crew_link.pos(Level.MAIN), 66, 54)
        if z >= 0.50:
            g.text("CREW STAIRS", S(V(cw[0] - 8, cw[1] - 22)), (230, 224, 201))

        # ---- wheelhouse: roof, funnel, searchlight and the outside steps
        x, y, w, h = self.wheelhouse
        sh = [S(V(x + 12, y + 16)), S(V(x + w + 14, y + 16)), S(V(x + w + 14, y + h + 16)), S(V(x + 12, y + h + 16))]
        pygame.draw.polygon(s, mix(DECK, (0, 0, 0), 0.5), sh)      # the roof stands proud of the deck: a drop shadow
        for lk in self.links:                                      # the steps are drawn first: the house stands over them
            if lk.kind == "wall" and Level.MAIN in lk.ends:
                a = lk.pos(Level.MAIN)           # the door is on the side of the house nearest this landing
                if a.y > y + h:
                    wall, out = V(a.x, y + h), V(0, 1)
                elif a.y < y:
                    wall, out = V(a.x, y), V(0, -1)
                elif a.x < x:
                    wall, out = V(x, a.y), V(-1, 0)
                else:
                    wall, out = V(x + w, a.y), V(1, 0)
                self._stairs(g, wall + out * 52, wall, 54)
        box(self.wheelhouse, WHITE, RAIL, 3)
        box((x + 7, y + 7, w - 14, h - 14), hexc("#c4bdae"))
        box((x + 14, y + 14, w - 52, h - 28), hexc("#cdc7b8"), hexc("#a79f8c"), 1)      # non-skid roof panel
        box((x + w - 12, y + 8, 6, h - 16), hexc("#27414f"))
        pygame.draw.circle(s, hexc("#3a3f44"), S(V(x + w - 26, y + h * 0.5)), max(3, int(8 * z)))      # searchlight
        pygame.draw.circle(s, hexc("#e8dfa8"), S(V(x + w - 26, y + h * 0.5)), max(2, int(4 * z)))
        fp_ = S(V(x + w * 0.28, 0))
        pygame.draw.circle(s, hexc("#7c2b21"), fp_, int(25 * z))
        pygame.draw.circle(s, RED, fp_, int(22 * z))
        pygame.draw.circle(s, hexc("#e4ddc9"), fp_, int(16 * z), max(1, int(3 * z)))
        pygame.draw.circle(s, (28, 28, 28), fp_, int(12 * z))
        pp = S(self.post)
        for corner in (V(x + w, y), V(x + w, y + h), self.hull[28]):
            pygame.draw.line(s, (60, 45, 35), pp, S(corner), 1)
        pygame.draw.circle(s, hexc("#1d2023"), pp, max(3, int(13 * z)))
        pygame.draw.circle(s, STEEL, pp, max(2, int(9 * z)))
        pygame.draw.circle(s, RAIL, pp, max(1, int(4 * z)))



# ------------------------------------------------------------------- world

class World:
    ZONES = ["HARBOUR", "COASTAL", "DEEP SEA"]

    def __init__(self, g):
        self.g = g
        self.scale = WORLD_SCALE
        self.ship_pos = V(350, -120) * self.scale
        self.heading = 0.0
        self.speed = 0.0
        # V13V1-04: navigation belief is separate from physical truth. Physics,
        # collisions, land avoidance, and existing AI continue to use ship_pos.
        self.believed_pos = V(self.ship_pos)
        self.believed_heading = self.heading
        self.believed_speed = self.speed
        self.last_fix = 0.0
        self.last_fix_method = "DEPARTURE"
        self.position_error = V(0, 0)  # hidden true error vector; never drawn directly
        self.compass_bias = 0.0
        self.log_bias = 0.0
        self.dr_uncertainty = 0.0      # crew-facing doubt estimate, not exact truth error
        self.throttle = 0.0
        self.manual_helm = False              # arrows operate the physical helm/throttle while a hand is at the station
        self.max_speed = 500.0                # full ahead maps to about 10 knots in the HUD
        self.turn_rate = 0.35
        # Mechanical telegraph and rudder response: the screw cannot reverse instantly,
        # rudder takes time to go over, and speed through water is not speed over ground.
        self.prop_direction = 1                # +1 ahead, -1 astern
        self.requested_prop_direction = 1
        self.reversing_elapsed = 0.0
        self.engine_reversing = False
        self.rudder_angle = 0.0                # -1 hard port, +1 hard starboard
        self.sea_state = 0.35
        self.auto_weather = True
        self.wave_direction = 2.2
        self.tilt_gain = 1.8
        self.time = 0.0
        self.zone = 0
        self.destination = None       # world point the helm is steering for
        self.route_waypoints = []     # committed manual route, remaining world-space Vector2 targets
        self.route_origin = None      # last believed/estimated fix or reached waypoint; track is not a rail
        self.route_arrival_hold = False
        self.last_cross_track_error = 0.0
        self.ocean_quick_target = None
        self.cruise = 0.9             # throttle used when sailing to a destination
        self.hold = False             # the captain is holding her still
        self.arrive = 450.0
        self.ap_heading, self.ap_t = None, 0.0
        self.berth = V(700, -500)     # where the ship lies in the harbour (world coords); far enough off the quay to swing round
        self.dock_state = None        # autodock: None / "approach" / "final"
        self.dock_side, self.dock_wp, self.dock_result = 1, V(0, 0), None   # result: arrived / cancelled / failed
        self.dock_retries = 0
        self.dock_phase_elapsed = 0.0
        self.dock_stall_elapsed = 0.0
        self.dock_best_distance = None
        self.brake = False            # all stop (man overboard)
        self.rescue_to = None         # world point of a swimmer the ship should creep towards
        self.waves = WaveField(self.scale)
        self.foam = SeaFoamSystem(max_particles=SeaFoamSystem.DEFAULT_CAP, seed=1962)
        # v13.2.05: waves meeting the hull, and ripples spreading from it.
        self.ripples = RippleSystem()
        self.hull_waves = None             # built on first update from the ship's real dimensions
        self.hull_strikes = []             # HullStrike events produced this step; consumed by Ship.update_water
        # V13V1-01: temporary world-space fish concentrations. These do not
        # alter ship physics; only the existing bite weights read their effect.
        self.hotspots = []
        self.hotspot_cd = random.uniform(10.0, 18.0)
        # V13V1-12: imperfect fleet/harbour intelligence about productive water.
        # Reports are deliberately separate from live hotspots and never expose truth.
        self.fishing_reports: list[FishingSpotReport] = []
        self.fishing_report_cd = random.uniform(25.0, 50.0)
        self.next_fishing_report_id = 1
        land = [(-4000, -4000), (4000, -4000), (4000, -900), (2600, -850), (2100, -700), (1700, -640),
                (1300, -560), (1000, -500), (700, -430), (500, -390), (-100, -380), (-400, -420),
                (-800, -520), (-1400, -640), (-2200, -760), (-4000, -900)]
        self.land = [V(p) for p in land]
        self.land_w = [p * self.scale for p in self.land]
        self.coast_w = self.land_w[2:]
        self.bw_a = V(1000, -500) * self.scale
        self.bw_b = V(1500, -330) * self.scale
        # v13v1-16: collision geometry is immutable; prepare coordinate tuples
        # and broad-phase bounds once instead of rebuilding polygon lists for
        # every rope particle in every solver constraint pass.
        self._land_collision_polygon = tuple((p.x, p.y) for p in self.land_w)
        self._land_collision_bounds = bounds_of_points(self._land_collision_polygon)
        self._reef_collision_segment = ((self.bw_a.x, self.bw_a.y), (self.bw_b.x, self.bw_b.y))
        self._reef_collision_bounds = bounds_of_points(self._reef_collision_segment)
        self._hull_collision_polygon = tuple((p.x, p.y) for p in self.g.ship.hull)
        self._hull_collision_bounds = bounds_of_points(self._hull_collision_polygon)
        self._hull_collision_radius = max((math.hypot(x, y) for x, y in self._hull_collision_polygon), default=0.0)
        self.town = self._build_town()

    # --- frames of reference
    def deck_of(self, w):
        return (w - self.ship_pos).rotate_rad(-self.heading)

    def world_of(self, d):
        return self.ship_pos + d.rotate_rad(self.heading)

    def dsp(self, p):          # design-unit point -> screen
        return self.g.S(self.deck_of(V(p) * self.scale))

    @property
    def speed_through_water(self):
        """Hull speed from propulsion/inertia; current and wind drift are applied separately."""
        return max(0.0, float(self.speed))

    def dist(self):
        return self.ship_pos.distance_to(HARBOUR) / self.scale

    def exposure(self):
        return lerp(0.12, 1.0, smoothstep(300, 4500, self.dist()))

    # --- the water column: warm mixed layer, a thermocline, cold deep water, and a seabed that falls away from the coast
    def surface_temp(self, d):
        return 17.0 + 7.0 * smoothstep(500, 5000, d) + 1.0 * math.sin((self.hour() - 9.0) / 24.0 * TAU)

    def thermocline(self, d):
        return 40.0 + 90.0 * smoothstep(500, 5500, d) + 8.0 * math.sin(self.time * 0.006)

    def temp_at(self, depth_m, d):
        th = self.thermocline(d)
        mixed = 1.0 - smoothstep(th - 30.0, th + 80.0, depth_m)
        return 5.0 + (self.surface_temp(d) - 5.0) * (0.12 + 0.88 * mixed)

    def bottom_m(self, d):
        return 25.0 + 700.0 * smoothstep(300, 4500, d)

    def current(self, depth_m):
        """Drift (world px/s) at a depth: the wind drift at the top, a slowly turning deep current below."""
        surf = V(1, 0).rotate_rad(self.wave_direction) * 6.0 * self.scale
        deep = V(1, 0).rotate_rad(0.9 + 0.35 * math.sin(self.time * 0.004)) * 5.0 * self.scale
        return surf.lerp(deep, smoothstep(20.0, 200.0, depth_m))

    # --- simulation
    def engine_order_text(self):
        return engine_order_label(self.throttle, self.prop_direction, self.engine_reversing)

    def _update_propulsion_direction(self, dt):
        """Use a short neutral interval and low speed before reversing the single screw."""
        requested = 1 if self.requested_prop_direction >= 0 else -1
        if requested == self.prop_direction:
            self.reversing_elapsed = 0.0
            self.engine_reversing = False
            return
        self.engine_reversing = True
        self.throttle = 0.0
        self.reversing_elapsed += max(0.0, float(dt))
        # The shaft is unloaded first; the screw does not bite astern until the hull
        # has lost most of its headway and the telegraph has spent time in neutral.
        if self.speed <= 22.0 and self.reversing_elapsed >= 2.4:
            self.prop_direction = requested
            self.reversing_elapsed = 0.0
            self.engine_reversing = False

    def set_destination(self, p, keep_dock=False, preserve_route=False):
        # Leaving the berth is the clear boundary for recalling shore-leave crew.
        # Kept-ashore employees stay behind until the player brings them aboard.
        if not keep_dock and self.g.docked():
            self.g._recall_shore_leave(departure=True)
        self.manual_helm = False
        self.requested_prop_direction = 1
        self.route_arrival_hold = False
        if not preserve_route:
            self.route_waypoints.clear()
            self.route_origin = None
            self.ocean_quick_target = None
        self.destination = V(p)
        self.ap_t = 0.0
        if not keep_dock and self.dock_state is not None:     # a new course from the player cancels the autodock
            self.cancel_dock()

    # --- the clock: one game day is DAY_LEN seconds
    def hour(self):
        return (START_HOUR + self.time / DAY_LEN * 24.0) % 24.0

    def day_number(self):
        # A calendar day is exactly DAY_LEN simulated seconds. START_HOUR defines
        # the time of day on Day 1; it must not shorten the first calendar date.
        return int(max(0.0, self.time) // DAY_LEN) + 1

    def calendar_date(self):
        return game_date(self.day_number(), START_DATE)

    def calendar_date_text(self):
        return self.calendar_date().strftime("%d %b %Y").upper()

    def season(self):
        return season_name(self.calendar_date().month)

    def daylight(self):
        """0 in the dead of night, 1 in full day, with a long dusk and dawn."""
        sun = math.sin((self.hour() - 6.0) / 24.0 * TAU)
        return smoothstep(-0.18, 0.28, sun)

    def clock_text(self):
        h, d = self.hour(), self.daylight()
        name = "night" if d < 0.1 else ("day" if d > 0.9 else ("dawn" if h < 12 else "dusk"))
        return "Day %d %02d:%02d (%s)" % (self.day_number(), int(h), int((h % 1.0) * 60), name)

    # --- autodock: lead in along the quay, then ease up to the berth
    def start_dock(self):
        # Berthing is a higher-priority navigation mode than a plotted route.
        self.route_waypoints.clear()
        self.manual_helm = False
        to = self.berth - self.ship_pos
        self.dock_side = 1 if self.ship_pos.x > self.berth.x else -1
        self.dock_wp = self.berth + V(self.dock_side * 1500.0, 0)
        self.dock_result = None
        self.dock_retries = 0
        self.dock_phase_elapsed = self.dock_stall_elapsed = 0.0
        lined_up = abs(self.ship_pos.y - self.berth.y) < 350 and 0 < (self.ship_pos.x - self.berth.x) * self.dock_side < 2200
        if lined_up or to.length() < 500:
            self.dock_state = "final"
            self.destination = None
            self.dock_best_distance = to.length()
        else:
            self.dock_state = "approach"
            self.dock_best_distance = self.ship_pos.distance_to(self.dock_wp)
            self.set_destination(self.dock_wp, keep_dock=True)

    def cancel_dock(self):
        if self.dock_state is not None:
            self.dock_state, self.dock_result = None, "cancelled"
            self.dock_phase_elapsed = self.dock_stall_elapsed = 0.0
            self.dock_best_distance = None

    def _retry_dock_approach(self, reason="approach blocked"):
        """Bounded autodock recovery: try the opposite lead-in instead of circling forever."""
        if self.dock_retries >= 2:
            self.dock_state, self.dock_result = None, "failed"
            self.destination = None
            self.throttle = 0.0
            self.g.crew.say("Captain: Berth approach is blocked. Autodock stopped safely; set a new course and retry.")
            return False
        self.dock_retries += 1
        self.dock_side *= -1
        self.dock_wp = self.berth + V(self.dock_side * 1500.0, 0)
        self.dock_state = "approach"
        self.dock_phase_elapsed = self.dock_stall_elapsed = 0.0
        self.dock_best_distance = self.ship_pos.distance_to(self.dock_wp)
        self.set_destination(self.dock_wp, keep_dock=True)
        self.g.crew.say("Captain: Final approach stalled. Trying the other side of the berth (%d/2)." % self.dock_retries)
        return True

    def _dock(self, dt, helm_ok, engine_ok):
        if self.dock_state is None or self.brake or self.rescue_to is not None:
            return                                         # man overboard takes priority; docking resumes afterwards
        if not (helm_ok and engine_ok):
            # Do not burn retries while a required station/engine is temporarily unavailable.
            return
        self.dock_phase_elapsed += max(0.0, dt)
        if self.dock_state == "approach":
            distance = self.ship_pos.distance_to(self.dock_wp)
            if self.dock_best_distance is None or distance < self.dock_best_distance - 35.0:
                self.dock_best_distance = distance
                self.dock_stall_elapsed = 0.0
            else:
                self.dock_stall_elapsed += max(0.0, dt)
            if self.destination is None:
                if distance < self.arrive + 150:
                    self.dock_state = "final"
                    self.dock_phase_elapsed = self.dock_stall_elapsed = 0.0
                    self.dock_best_distance = self.ship_pos.distance_to(self.berth)
                else:
                    self.set_destination(self.dock_wp, keep_dock=True)
            if self.dock_phase_elapsed > 40.0 and self.dock_stall_elapsed > 8.0:
                self._retry_dock_approach("lead-in blocked")
            return
        to = self.berth - self.ship_pos
        d = to.length()
        if self.dock_best_distance is None or d < self.dock_best_distance - 22.0:
            self.dock_best_distance = d
            self.dock_stall_elapsed = 0.0
        else:
            self.dock_stall_elapsed += max(0.0, dt)
        want = 0.0 if self.dock_side < 0 else math.pi      # lie parallel to the quay, facing the way we came in
        tgt = 0.0
        if helm_ok and engine_ok:
            aim = math.atan2(to.y, to.x) if d > 350 else want
            diff = (aim - self.heading + math.pi) % TAU - math.pi
            self.heading += clamp(diff * 1.5, -1.0, 1.0) * self.turn_rate * 0.8 * dt
            tgt = clamp(d / 2600.0, 0.0, 0.3) * (1.0 - 0.7 * clamp(abs(diff), 0.0, 1.0))
        self.throttle = lerp(self.throttle, tgt, 1 - math.exp(-1.2 * dt))
        if d < 90 and self.speed < 80:
            self.dock_state, self.dock_result = None, "arrived"
            self.throttle = 0.0
            self.destination = None
            self.g.arrival_done = False                    # so the auction and pay run once we are alongside
            self.reset_position_fix("BERTH")
            self.g.crew.say("Captain: Alongside. Make her fast.")
        elif self.dock_stall_elapsed > 10.0 or (self.dock_phase_elapsed > 55.0 and d > 180.0):
            self._retry_dock_approach("berth approach blocked")

    def fishing_ground(self):
        return V(3900, 5200) * self.scale

    def _hotspot_water_ok(self, x, y):
        """True only for deep offshore water, away from charted coast/reef."""
        pos = V(float(x), float(y))
        if in_poly(pos, self.land_w):
            return False
        distance = pos.distance_to(HARBOUR) / self.scale
        if distance < 1500.0 or self.bottom_m(distance) < 150.0:
            return False
        coast_clearance = 500.0 * self.scale
        for a, b in zip(self.coast_w, self.coast_w[1:]):
            if pos.distance_to(closest_on_seg(pos, a, b)) < coast_clearance:
                return False
        reef_clearance = 150.0 + 20.0 * self.scale
        if pos.distance_to(closest_on_seg(pos, self.bw_a, self.bw_b)) < reef_clearance:
            return False
        return True

    def collide_longline_point(self, position, radius=8.0, ignore_ship=False, depth_m=0.0):
        """Resolve line gear only against nearby obstacles, using prepared geometry."""
        p = position if isinstance(position, V) else V(position)
        hit = False
        if within_expanded_bounds(p.x, p.y, self._land_collision_bounds, radius):
            corrected, contact = resolve_circle_polygon(
                (p.x, p.y), radius, self._land_collision_polygon)
            if contact:
                p, hit = V(corrected), True
        reef_radius = radius + 20.0
        if within_expanded_bounds(p.x, p.y, self._reef_collision_bounds, reef_radius):
            corrected, contact = resolve_circle_segment(
                (p.x, p.y), reef_radius, *self._reef_collision_segment)
            if contact:
                p, hit = V(corrected), True
        if not ignore_ship:
            # Rotation preserves distance from the vessel origin. Most line
            # particles are far offshore, so reject them before the deck-space
            # transform and local polygon test.
            hull_r = self._hull_collision_radius + radius
            dx, dy = p.x - self.ship_pos.x, p.y - self.ship_pos.y
            if dx * dx + dy * dy <= hull_r * hull_r:
                local = self.deck_of(p)
                if within_expanded_bounds(local.x, local.y, self._hull_collision_bounds, radius):
                    corrected, contact = resolve_circle_polygon(
                        (local.x, local.y), radius, self._hull_collision_polygon)
                    if contact:
                        p = self.world_of(V(corrected))
                        hit = True
        # A deployed rescue craft only obstructs surface/near-surface gear.
        boat = getattr(self.g, "rescue_boat_state", None)
        if boat and boat.get("phase") in ("out", "pickup", "return") and float(depth_m) <= 3.0:
            center = boat["pos"]
            clearance = radius + 40.0
            if (p.x - center.x) ** 2 + (p.y - center.y) ** 2 < clearance * clearance:
                corrected, contact = resolve_circle_segment(
                    (p.x, p.y), clearance, (center.x, center.y), (center.x, center.y))
                if contact:
                    p, hit = V(corrected), True
        return p, hit

    def collide_longline_segment(self, start, end, radius=6.0, ignore_ship=False, depth_m=0.0):
        """Sweep rope interiors, but skip sampling if the segment is far from all obstacles."""
        a, b = V(start), V(end)
        pad = max(14.0, float(radius))
        candidates = (
            segment_overlaps_bounds(a, b, self._land_collision_bounds, pad),
            segment_overlaps_bounds(a, b, self._reef_collision_bounds, pad + 20.0),
        )
        hull_r = self._hull_collision_radius + pad
        hull_bounds = (self.ship_pos.x - hull_r, self.ship_pos.x + hull_r,
                       self.ship_pos.y - hull_r, self.ship_pos.y + hull_r)
        hull_candidate = not ignore_ship and segment_overlaps_bounds(a, b, hull_bounds)
        boat = getattr(self.g, "rescue_boat_state", None)
        boat_candidate = False
        if boat and boat.get("phase") in ("out", "pickup", "return") and float(depth_m) <= 3.0:
            center = boat["pos"]
            br = pad + 40.0
            boat_candidate = segment_overlaps_bounds(
                a, b, (center.x - br, center.x + br, center.y - br, center.y + br))
        if not any(candidates) and not hull_candidate and not boat_candidate:
            return b, b, False
        distance = a.distance_to(b)
        step = max(14.0, float(radius) * 1.75)
        samples = max(2, int(math.ceil(distance / step)))
        for i in range(1, samples):
            sample = a.lerp(b, i / samples)
            corrected, hit = self.collide_longline_point(
                sample, radius, ignore_ship=ignore_ship, depth_m=depth_m)
            if hit:
                return V(corrected), sample, True
        return b, b, False

    def collide_rescue_boat_position(self, position, radius=38.0):
        """Resolve a rescue-boat position with broad-phase checks around each obstacle."""
        p = position if isinstance(position, V) else V(position)
        hit = False
        if within_expanded_bounds(p.x, p.y, self._land_collision_bounds, radius):
            corrected, contact = resolve_circle_polygon(
                (p.x, p.y), radius, self._land_collision_polygon)
            if contact:
                p, hit = V(corrected), True
        reef_radius = radius + 22.0
        if within_expanded_bounds(p.x, p.y, self._reef_collision_bounds, reef_radius):
            corrected, contact = resolve_circle_segment(
                (p.x, p.y), reef_radius, *self._reef_collision_segment)
            if contact:
                p, hit = V(corrected), True
        hull_r = self._hull_collision_radius + radius
        dx, dy = p.x - self.ship_pos.x, p.y - self.ship_pos.y
        if dx * dx + dy * dy <= hull_r * hull_r:
            local = self.deck_of(p)
            if within_expanded_bounds(local.x, local.y, self._hull_collision_bounds, radius):
                corrected, contact = resolve_circle_polygon(
                    (local.x, local.y), radius, self._hull_collision_polygon)
                if contact:
                    p, hit = self.world_of(V(corrected)), True
        line = getattr(self.g, "line", None)
        if line is not None:
            # Do cheap expanded-AABB checks before segment-distance math. Only
            # surface and near-surface gear can obstruct the rescue launch.
            for left, right in zip(line.pts, line.pts[1:]):
                left_float, right_float = bool(left.get("float")), bool(right.get("float"))
                left_depth = float(left.get("z", 0.0)) * DEPTH_M
                right_depth = float(right.get("z", 0.0)) * DEPTH_M
                if not (left_float or right_float or min(left_depth, right_depth) <= 3.0):
                    continue
                a, b = left["pos"], right["pos"]
                clearance = radius + (26.0 if left_float or right_float else 12.0)
                if not segment_overlaps_bounds(
                    a, b, (p.x - clearance, p.x + clearance, p.y - clearance, p.y + clearance)):
                    continue
                corrected, contact = resolve_circle_segment(
                    (p.x, p.y), clearance, (a.x, a.y), (b.x, b.y))
                if contact:
                    p, hit = V(corrected), True
            for point in line.pts:
                depth_m = float(point.get("z", 0.0)) * DEPTH_M
                if not point.get("float") and depth_m > 3.0:
                    continue
                buoy = point["pos"]
                clearance = radius + (28.0 if point.get("float") else 12.0)
                dx, dy = p.x - buoy.x, p.y - buoy.y
                if dx * dx + dy * dy >= clearance * clearance:
                    continue
                corrected, contact = resolve_circle_segment(
                    (p.x, p.y), clearance, (buoy.x, buoy.y), (buoy.x, buoy.y))
                if contact:
                    p, hit = V(corrected), True
        return p, hit

    def _spawn_hotspot(self):
        """Spawn a temporary species school in validated offshore water.

        Try the broad offshore annulus first, then try a deterministic search
        around the normal fishing grounds. The fallback prevents a failed set
        of random samples from leaving the game with no productive water.
        """
        if len(self.hotspots) >= MAX_ACTIVE_HOTSPOTS:
            return False
        pos = None
        ship_distance = self.ship_pos.distance_to(HARBOUR) / self.scale
        # Once offshore, seed schools around the vessel's current fishing area
        # first. This makes the world-space cues something the player can actually
        # encounter rather than several remote spots hidden beyond the camera.
        # The same water validator still enforces distance from harbour, depth,
        # coastline, land, and reef.
        if ship_distance >= 3000.0:
            pos = find_spawn_position(
                random, self.scale, self._hotspot_water_ok,
                harbour=(self.ship_pos.x, self.ship_pos.y),
                min_distance=1000.0, max_distance=3600.0, attempts=32,
            )
        if pos is None:
            pos = find_spawn_position(
                random, self.scale, self._hotspot_water_ok,
                harbour=(HARBOUR.x, HARBOUR.y), min_distance=4000.0,
                max_distance=9000.0, attempts=48,
            )
        if pos is None:
            center = self.fishing_ground()
            # Fixed golden-angle sweep: deterministic coverage after the random
            # sampler has failed, without accepting land, reef, or shallow water.
            for radius_units in (1400.0, 1800.0, 2300.0, 2900.0, 3600.0, 4300.0):
                for i in range(32):
                    angle = i * 2.399963229728653
                    candidate = center + V(math.cos(angle), math.sin(angle)) * (radius_units * self.scale)
                    if self._hotspot_water_ok(candidate.x, candidate.y):
                        pos = (candidate.x, candidate.y)
                        break
                if pos is not None:
                    break
        if pos is None:
            # The reference fishing ground itself is valid offshore water in the
            # shipped world layout; keep this check rather than force a bad spawn.
            center = self.fishing_ground()
            if self._hotspot_water_ok(center.x, center.y):
                pos = (center.x, center.y)
        if pos is None:
            return False
        species = random.choices(
            HOTSPOT_SPECIES, weights=(0.30, 0.30, 0.15, 0.10, 0.15), k=1,
        )[0]
        strength = random.uniform(0.4, 1.0)
        radius = random.uniform(1200.0, 2200.0)
        life = random.uniform(420.0, 900.0)
        drift_angle = random.uniform(0.0, TAU)
        drift_speed = random.uniform(2.0, 8.0)
        self.hotspots.append(Hotspot(
            pos[0], pos[1], species, strength, radius, life,
            drift_x=math.cos(drift_angle) * drift_speed,
            drift_y=math.sin(drift_angle) * drift_speed,
            phase=random.uniform(0.0, TAU),
        ))
        return True

    def _update_hotspots(self, dt):
        """Age schools and retry quickly after a failed spawn instead of going dark."""
        alive = []
        for spot in self.hotspots:
            if spot.update(dt, self._hotspot_water_ok):
                alive.append(spot)
        self.hotspots = alive
        self.hotspot_cd -= max(0.0, dt)
        if self.hotspot_cd > 0.0:
            return
        if len(self.hotspots) >= MAX_ACTIVE_HOTSPOTS:
            self.hotspot_cd = random.uniform(35.0, 55.0)
            return
        spawned = self._spawn_hotspot()
        if spawned:
            self.hotspot_cd = random.uniform(45.0, 75.0)
        else:
            # A blocked sample must retry soon, never defer the next chance by
            # another full 90–150 second interval.
            self.hotspot_cd = random.uniform(6.0, 12.0)

    def _update_fishing_reports(self, dt):
        """Age report leads and periodically add an uncertain chart annotation."""
        alive = []
        for report in self.fishing_reports:
            if report.update(dt):
                alive.append(report)
        self.fishing_reports = alive
        self.fishing_report_cd -= max(0.0, float(dt))
        if self.fishing_report_cd > 0.0:
            return
        self.fishing_report_cd = random.uniform(180.0, 300.0)
        report = create_fishing_report(
            random, self.hotspots, self.scale, self._hotspot_water_ok,
            self.next_fishing_report_id,
        )
        if report is None:
            return
        self.next_fishing_report_id += 1
        self.fishing_reports.append(report)
        if len(self.fishing_reports) > MAX_CHART_REPORTS:
            self.fishing_reports.sort(key=lambda item: item.age)
            self.fishing_reports = self.fishing_reports[:MAX_CHART_REPORTS]
        # This is a report/event, not a spoken line. Keep it in the notebook only.
        recorder = getattr(self.g, "record_log_entry", None)
        if recorder is not None:
            recorder("Chart fishing report R%02d: %s activity reported by %s (%d%% source confidence); unconfirmed." % (
                report.report_id, report.species.replace("_", " "), report.source,
                round(report.confidence * 100),
            ))

    def reset_position_fix(self, method="FIX"):
        """Reset the crew estimate after a confirmed physical position fix."""
        self.believed_pos = V(self.ship_pos)
        self.believed_heading = self.heading % TAU
        self.believed_speed = max(0.0, self.speed)
        self.last_fix = self.time
        self.last_fix_method = str(method).upper()
        self.position_error = V(0, 0)
        self.compass_bias = 0.0
        self.log_bias = 0.0
        self.dr_uncertainty = 0.0

    def apply_approximate_position_fix(self, estimate, method, accuracy_world_units):
        """Apply a measured position without changing physical ship truth.

        The estimate is allowed to retain measurement error. Its uncertainty ring
        reports the method's nominal accuracy, never the hidden true error vector.
        """
        self.believed_pos = V(estimate)
        self.last_fix = self.time
        self.last_fix_method = str(method).upper()
        self.position_error = self.believed_pos - self.ship_pos  # internal only
        self.compass_bias = 0.0
        self.log_bias = 0.0
        self.dr_uncertainty = max(0.0, float(accuracy_world_units))

    def _update_dead_reckoning(self, dt, helm_ok):
        """Advance only the crew estimate; never change physical ship state."""
        dt = max(0.0, float(dt))
        if dt <= 0.0:
            self.position_error = self.believed_pos - self.ship_pos
            return
        helm = getattr(self.g, "helm_operator", None) if helm_ok else None
        if helm is not None and getattr(helm, "mode", Sailor.ABOARD) == Sailor.ABOARD:
            skill = float(getattr(helm, "skill", 0.15))
        else:
            skill = 0.15
        wx = self.g.weather
        rate = dr_error_rate(skill, self.sea_state, self.daylight(), wx.fog, wx.rain)
        self.compass_bias, self.log_bias = evolve_biases(
            self.compass_bias, self.log_bias, dt, random
        )
        bx, by, self.believed_heading, self.believed_speed = advance_belief(
            self.believed_pos.x, self.believed_pos.y, self.heading, self.speed, dt,
            self.compass_bias, self.log_bias
        )
        self.believed_pos = V(bx, by)
        self.position_error = self.believed_pos - self.ship_pos
        travel_factor = clamp(self.speed / max(1.0, self.max_speed), 0.0, 1.0)
        self.dr_uncertainty = min(1000000.0, self.dr_uncertainty + rate * dt * travel_factor)

    def fix_age_text(self):
        return format_fix_age(self.time - self.last_fix)

    def dr_error_rate(self, helm_ok=True):
        helm = getattr(self.g, "helm_operator", None) if helm_ok else None
        skill = float(getattr(helm, "skill", 0.15)) if helm is not None else 0.15
        wx = self.g.weather
        return dr_error_rate(skill, self.sea_state, self.daylight(), wx.fog, wx.rain)

    def update(self, dt, keys, helm_ok=True, engine_ok=True, engine_power=1.0):
        dt = max(0.0, float(dt))
        self.time += dt
        stop = bool(keys[pygame.K_SPACE]) or self.brake or bool(getattr(self.g, "anchor_deployed", False))
        # A vacant wheelhouse is a hard control interlock: no residual manual
        # throttle or autopilot command may keep driving the vessel.
        if not helm_ok:
            self.manual_helm = False
        if keys[pygame.K_SPACE]:
            self.cancel_dock()
        if stop:
            self.destination = None
            self.throttle = 0.0
        if keys[pygame.K_COMMA]:
            self.auto_weather = False
            self.sea_state = max(self.sea_state - 0.3 * dt, 0.0)
        if keys[pygame.K_PERIOD]:
            self.auto_weather = False
            self.sea_state = min(self.sea_state + 0.3 * dt, 1.0)
        if self.auto_weather:
            t, wx = self.time, self.g.weather
            target = clamp(0.18 + 0.58 * wx.wind + 0.10 * math.sin(t * 0.021) + 0.05 * math.sin(t * 0.0537 + 2), 0.05, 1.0)
            self.sea_state = lerp(self.sea_state, target, 1 - math.exp(-0.5 * dt))
            self.wave_direction = lerp_angle(self.wave_direction, wx.wind_dir, 1 - math.exp(-0.3 * dt))

        # Arrow keys are a physical helm wheel and telegraph, not an instant speed
        # slider. Holding Down past STOP calls for astern; reversing takes time.
        manual_keys = any(keys[k] for k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN))
        if manual_keys and helm_ok and self.destination is None and self.dock_state is None and self.rescue_to is None and not stop:
            self.manual_helm = True
        manual_rudder = None
        if self.manual_helm and helm_ok and not stop and self.destination is None and self.dock_state is None:
            if keys[pygame.K_UP]:
                if self.prop_direction < 0 or self.requested_prop_direction < 0 or self.engine_reversing:
                    self.requested_prop_direction = 1
                    self.throttle = 0.0
                else:
                    self.throttle = clamp(self.throttle + 0.22 * dt, 0.0, 1.0)
            if keys[pygame.K_DOWN]:
                if self.prop_direction < 0 and self.requested_prop_direction < 0 and not self.engine_reversing:
                    self.throttle = clamp(self.throttle + 0.18 * dt, 0.0, 0.32)
                else:
                    self.throttle = max(0.0, self.throttle - 0.30 * dt)
                    if self.throttle <= 0.035 and self.speed <= 36.0:
                        self.requested_prop_direction = -1
            manual_rudder = int(bool(keys[pygame.K_RIGHT])) - int(bool(keys[pygame.K_LEFT]))
        elif not self.manual_helm and self.destination is None and self.dock_state is None and self.rescue_to is None:
            # Returning to ordinary travel clears a stale astern telegraph order.
            self.requested_prop_direction = 1

        h0 = self.heading
        self._autopilot(dt, helm_ok, engine_ok)
        self._rescue_steer(dt, helm_ok, engine_ok, bool(keys[pygame.K_SPACE]))
        self._dock(dt, helm_ok, engine_ok)
        demanded_heading = self.heading
        if manual_rudder is not None and self.manual_helm:
            rudder_command = float(manual_rudder)
        else:
            delta_command = shortest_angle(demanded_heading, h0)
            command_authority = clamp(self.speed / (self.max_speed * 0.18), 0.18, 1.0)
            if self.g.mob_rescue_mode == "ship_turn":
                command_authority = max(command_authority, 0.34)
            rudder_command = clamp(delta_command / max(1e-5, self.turn_rate * command_authority * max(dt, 1e-4)), -1.0, 1.0)
        # Rudder moves at a finite rate and the hull responds at speed-dependent
        # authority. Backing down is less effective and slightly asymmetric.
        self.rudder_angle = rudder_step(self.rudder_angle, rudder_command, dt, 0.95)
        turn_authority = clamp(self.speed / (self.max_speed * 0.19), 0.12, 1.0)
        if self.prop_direction < 0:
            turn_authority *= 0.62
        if self.g.mob_rescue_mode == "ship_turn":
            turn_authority = max(turn_authority, 0.34)
        self.heading = (h0 + self.rudder_angle * self.turn_rate * turn_authority * dt) % TAU
        if self.heading != h0 and self.blocked(self.ship_pos) and not self.blocked(self.ship_pos, h0):
            self.heading = h0                  # the helmsman won't swing the stern into the quay
            self.rudder_angle = 0.0

        self._update_propulsion_direction(dt)
        rate = 2.8 if stop else (0.55 if self.prop_direction > 0 else 0.75)
        head_sea = max(0.0, -math.cos(self.heading - self.wave_direction))
        sea_f = 1.0 - 0.3 * self.waves.strength * head_sea
        reverse_factor = 0.30 if self.prop_direction < 0 else 1.0
        target_speed = self.throttle * self.max_speed * engine_power * sea_f * reverse_factor
        self.speed = lerp(self.speed, target_speed, 1 - math.exp(-rate * dt))

        forward = V(1, 0).rotate_rad(self.heading)
        current_set = self.current(0.0) * 0.42
        wx = self.g.weather
        crosswind = math.sin(wx.wind_dir - self.heading)
        wind_leeway = V(0, 1).rotate_rad(self.heading) * (crosswind * wx.wind * 24.0 * self.scale)
        # The single screw walks the stern sideways while astern; it is deliberately
        # modest, but the boat's reverse path is not a mirror image of ahead.
        prop_walk = V(0, 1).rotate_rad(self.heading) * (-1.0 if self.prop_direction < 0 else 0.10) * (self.speed / max(1.0, self.max_speed)) * 12.0 * self.scale
        drift = current_set + wind_leeway + prop_walk
        nxt = self.ship_pos + (forward * self.speed * self.prop_direction + drift) * dt
        if getattr(self.g, "anchor_deployed", False):
            # The anchor arrests most current/wind drift without snapping the hull to a new position.
            nxt = self.ship_pos.lerp(nxt, 0.012)
            self.speed = min(self.speed, 1.5)
            self.throttle = 0.0
        if self.blocked(nxt) and not self.blocked(self.ship_pos):
            self.speed = 0.0
            self.throttle = 0.0
        else:
            self.ship_pos = nxt
        # Keep navigation belief parallel to true physics; do not replace ship_pos.
        self._update_dead_reckoning(dt, helm_ok)
        d = self.dist()
        self.zone = 0 if d < 900 else (1 if d < 5000 else 2)
        self.waves.time = self.time
        self.waves.base_angle = self.wave_direction
        self.waves.strength = self.sea_state * self.exposure()
        self._update_hotspots(dt)
        self._update_fishing_reports(dt)
        current = self.current(0.0)
        visible_radius = math.hypot(W, H) * 0.56 / max(0.08, self.g.zoom) + 160.0
        self.foam.update(
            dt,
            ship_position=(self.ship_pos.x, self.ship_pos.y),
            heading=self.heading,
            ship_speed_fraction=self.speed / max(1.0, self.max_speed),
            sea_state=self.sea_state,
            wave_strength=self.waves.strength,
            wave_direction=self.wave_direction,
            ship_length=self.g.ship.length,
            ship_beam=self.g.ship.beam,
            current_velocity=(current.x, current.y),
            visible_radius=visible_radius,
            wave_height=lambda x, y: self.waves.height(V(x, y)),
            wind_strength=self.g.weather.wind,
            wind_direction=self.g.weather.wind_dir,
        )
        self._update_hull_waves(dt, current, visible_radius)

    def _update_hull_waves(self, dt, current, visible_radius):
        """v13.2.05: detect waves that reach the rails, then turn them into foam and ripples."""
        ship = self.g.ship
        if self.hull_waves is None or self.hull_waves.length != ship.length or self.hull_waves.beam != ship.beam:
            self.hull_waves = HullWaveInteraction(ship.length, ship.beam)
        self.hull_strikes = []
        if self.waves.strength > 0.05:
            self.hull_strikes = self.hull_waves.update(
                dt, ship_position=(self.ship_pos.x, self.ship_pos.y), heading=self.heading,
                wave_height=lambda x, y: self.waves.height(V(x, y)),
                freeboard_factor=ship.freeboard_factor, list_bias=ship.list_trim)
        else:
            self.hull_waves.reset()
            self.hull_waves.immersion = dict.fromkeys(self.hull_waves.immersion, 0.0)
        sea = clamp(self.waves.strength * 1.5, 0.0, 1.0)
        wind = self.g.weather.wind
        wvec = (math.cos(self.g.weather.wind_dir) * wind, math.sin(self.g.weather.wind_dir) * wind)
        for st in self.hull_strikes:
            self.foam.emit_strike(self.ship_pos.x, self.ship_pos.y, self.heading, zone=st.zone, kind=st.kind,
                                  energy=st.energy, local_x=st.local_x, local_y=st.local_y, nx=st.nx, ny=st.ny,
                                  current=(current.x, current.y), wind=wvec, sea=sea)
            self.ripples.emit_impact(self.ship_pos.x, self.ship_pos.y, self.heading, st)
        self.ripples.update(
            dt, ship_position=(self.ship_pos.x, self.ship_pos.y), heading=self.heading,
            speed_fraction=self.speed / max(1.0, self.max_speed), throttle=self.throttle, sea_state=sea,
            roll_rate=getattr(self.g, "roll_v", 0.0), ship_length=ship.length, ship_beam=ship.beam,
            current_velocity=(current.x, current.y), keep_radius=visible_radius * 1.2)

    def _autopilot(self, dt, helm_ok, engine_ok=True):
        """Track a fallible estimated-position leg rather than snapping onto its line."""
        if self.manual_helm and self.dock_state is None and self.destination is None:
            return
        if self.dock_state == "final":
            return
        tgt = 0.18 if self.route_arrival_hold and helm_ok and engine_ok else 0.0  # slow ahead only with a live helm
        if self.route_waypoints and self.destination is None and self.dock_state is None:
            self.destination = V(self.route_waypoints[0])
        if self.destination is not None and not self.hold and engine_ok:
            to = self.destination - self.ship_pos
            dist = to.length()
            if dist < self.arrive:
                if self.route_waypoints:
                    reached = V(self.route_waypoints.pop(0))
                    self.route_origin = reached
                    self.g.record_log_entry("Helm reached a plotted waypoint; %d remain." % len(self.route_waypoints))
                    while self.route_waypoints and self.ship_pos.distance_to(self.route_waypoints[0]) < self.arrive:
                        reached = V(self.route_waypoints.pop(0))
                        self.route_origin = reached
                        self.g.record_log_entry("Helm reached a plotted waypoint; %d remain." % len(self.route_waypoints))
                    self.destination = V(self.route_waypoints[0]) if self.route_waypoints else None
                    if not self.route_waypoints:
                        self.route_arrival_hold = True
                        self.ocean_quick_target = None
                        self.route_origin = None  # completed A→B geometry is discarded, not left as a stale plot
                        self.g.record_log_entry("Helm completed the plotted course; plot erased, slow ahead, holding heading for orders.")
                        self.g.crew.say("Helm: Leg reached. Plot cleared; slow ahead, holding this heading for orders.")
                    self.ap_t = 0.0
                else:
                    self.destination = None
                    self.throttle = 0.0
                    if self.ocean_quick_target is not None:
                        self.ocean_quick_target = None
                        self.route_origin = None  # no stale course origin after the temporary mark is reached
                        self.g.record_log_entry("Quick steering mark reached; plot erased, holding heading for orders.")
                        self.g.crew.say("Helm: Mark reached. Holding heading for orders.")
                if self.destination is not None:
                    to = self.destination - self.ship_pos
                    dist = to.length()
                else:
                    tgt = 0.18 if self.route_arrival_hold else 0.0
            if self.destination is not None and helm_ok:
                self.ap_t -= dt
                if self.ap_t <= 0:
                    self.ap_t = 0.18
                    # Cross-track is measured against the crew's estimated fix. A
                    # stale/degraded fix can make a perfectly followed belief-line wrong.
                    if self.route_waypoints:
                        origin = V(self.route_origin) if self.route_origin is not None else V(self.believed_pos)
                        xte = cross_track_error(self.believed_pos, origin, self.destination)
                        self.last_cross_track_error = xte / max(1.0, self.scale)
                        leg_heading = heading_radians(origin, self.destination)
                        helm = getattr(self.g, "helm_operator", None)
                        skill = float(getattr(helm, "skill", 0.2)) if helm_ok and helm is not None else 0.1
                        lookahead = clamp(680.0 + self.speed * 1.6, 500.0, 1800.0)
                        self.ap_heading = desired_track_heading(leg_heading, xte, lookahead, skill, self.time)
                    else:
                        self.last_cross_track_error = 0.0
                        self.ap_heading = self._clear_heading(math.atan2(to.y, to.x))
                if self.ap_heading is not None:
                    diff = shortest_angle(self.ap_heading, self.heading)
                    way = clamp(self.speed / (self.max_speed * 0.30), 0.25, 1.0)
                    # Wider turns at speed; the rudder and hull response are lagged in update().
                    self.heading += clamp(diff * 1.35, -1.0, 1.0) * self.turn_rate * way * dt
                    tgt = self.cruise * clamp(dist / 2500.0, 0.14, 1.0) * (1.0 - 0.52 * clamp(abs(diff), 0.0, 1.0))
            elif self.destination is not None:
                tgt = 0.0                          # no helmsman, no autonomous execution
        elif self.destination is not None and not helm_ok:
            tgt = 0.0
        # When the line is at the winch, finish the approach with the starboard
        # aft quarter presented to the roller. The local pickup point is the same
        # one used by Longline._haul_world; the hull still turns with finite rudder
        # authority while it slows, rather than snapping to an exact heading.
        line = getattr(self.g, "line", None)
        if (self.destination is None and helm_ok and engine_ok and line is not None
                and line.phase == Longline.HAULING and line.pts):
            head_pos = V(line.pts[0]["pos"])
            roller_local = V(-self.g.ship.length * 0.32, self.g.ship.beam * 0.5)
            target_local = self.deck_of(head_pos)
            pickup_gap = target_local.distance_to(roller_local)
            if pickup_gap <= max(620.0, self.g.ship.length * 0.58):
                from fishing_sim.systems.gear_handling import starboard_roller_heading
                bearing = math.atan2(head_pos.y - self.ship_pos.y, head_pos.x - self.ship_pos.x)
                desired = starboard_roller_heading(bearing, self.g.ship.length, self.g.ship.beam)
                diff = shortest_angle(desired, self.heading)
                authority = clamp(self.speed / (self.max_speed * 0.22), 0.16, 0.62)
                self.heading = (self.heading + clamp(diff * 1.15, -1.0, 1.0)
                                * self.turn_rate * authority * dt) % TAU
        if self.destination is not None:
            self.requested_prop_direction = 1
        self.throttle = lerp(self.throttle, tgt, 1 - math.exp(-0.8 * dt))

    def _rescue_steer(self, dt, helm_ok, engine_ok, hold):
        """Come about while slowing, then creep around to present the starboard rail."""
        if (self.g.mob_rescue_mode != "ship_turn" or self.rescue_to is None
                or not (helm_ok and engine_ok)):
            return
        self.destination = None
        self.route_waypoints.clear()
        self.route_origin = None
        self.ocean_quick_target = None
        # Do not just wait with the bow pointing away. Begin the turn at once while
        # momentum bleeds off, then advance only when the new approach heading is safe.
        if self.speed > 28.0:
            self.throttle = 0.0
        to_swimmer = self.rescue_to - self.ship_pos
        distance = to_swimmer.length()
        if distance < 1e-6:
            self.throttle = 0.0
            return
        bearing = math.atan2(to_swimmer.y, to_swimmer.x)
        approach_radius = self.g.ship.beam * 0.5 + 105.0
        if distance > approach_radius + 18.0:
            approach_point = self.rescue_to - to_swimmer.normalize() * approach_radius
            to_approach = approach_point - self.ship_pos
            aim = math.atan2(to_approach.y, to_approach.x) if to_approach.length() > 1e-6 else bearing
            safe_aim = self._clear_heading(aim)
            if safe_aim is None:
                self.throttle = 0.0
                return
            aim = safe_aim
            diff = shortest_angle(aim, self.heading)
            self.heading += clamp(diff * 1.3, -1.0, 1.0) * self.turn_rate * 0.62 * dt
            if self.speed <= 28.0:
                self.throttle = 0.09 if abs(diff) < 0.48 else 0.025
        else:
            starboard_heading = bearing - math.pi / 2.0
            safe_heading = self._clear_heading(starboard_heading)
            if safe_heading is not None:
                starboard_heading = safe_heading
            diff = shortest_angle(starboard_heading, self.heading)
            self.heading += clamp(diff * 1.55, -1.0, 1.0) * self.turn_rate * 0.7 * dt
            self.throttle = 0.0

    def _clear_heading(self, desired):
        for off in (0, 0.25, -0.25, 0.5, -0.5, 0.8, -0.8, 1.1, -1.1, 1.5, -1.5):
            h = desired + off
            f = V(1, 0).rotate_rad(h)
            if not any(self.blocked(self.ship_pos + f * d, h) for d in (500, 1100, 1800)):
                return h
        return None

    def blocked(self, pos, heading=None):
        f = V(1, 0).rotate_rad(self.heading if heading is None else heading)
        half = self.g.ship.length * 0.5
        for off in (-0.9, -0.45, 0.0, 0.45, 0.95):
            p = pos + f * half * off
            if in_poly(p, self.land_w):
                return True
            for a, b in zip(self.coast_w, self.coast_w[1:]):
                if p.distance_to(closest_on_seg(p, a, b)) < 150:
                    return True
            if p.distance_to(closest_on_seg(p, self.bw_a, self.bw_b)) < 150 + 20 * self.scale:
                return True
        return False

    def deck_slope(self):
        L, B = self.g.ship.length, self.g.ship.beam
        sx, sy = L * 0.28, B * 0.5
        fwd = V(1, 0).rotate_rad(self.heading)
        stbd = V(0, 1).rotate_rad(self.heading)
        h = self.waves.height
        hb, hs = h(self.ship_pos + fwd * sx), h(self.ship_pos - fwd * sx)
        hp, hst = h(self.ship_pos - stbd * sy), h(self.ship_pos + stbd * sy)
        return V((hs - hb) / (2 * sx), (hp - hst) / (2 * sy)) * self.tilt_gain

    # ------------------------------------------------------------ the town
    # Everything is laid out in "depth" from the coast (design units inland of the shoreline), so streets and
    # house rows follow the curve of the bay.  Built once in __init__, drawn each frame with distance culling.
    def coast_y(self, x):
        pts = self.land[2:]
        if x >= pts[0].x:
            return pts[0].y
        for a, b in zip(pts, pts[1:]):
            if b.x <= x <= a.x:
                return lerp(a.y, b.y, (x - a.x) / (b.x - a.x))
        return pts[-1].y

    def _build_town(self):
        rnd = random.Random(1962)
        cy = self.coast_y
        on = lambda x, d: V(x, cy(x) - d)
        T = {k: [] for k in ("ground", "plots", "roads", "bld", "trees", "poles", "lamps", "deco", "labels", "lit")}
        edge = lambda x: 880 + 70 * math.sin(x * 0.0041) + 40 * math.sin(x * 0.0113 + 1.0)
        xs = list(range(-1900, 2501, 100))
        T["ground"].append(("poly", [on(x, edge(x)) for x in xs] + [on(x, 3000) for x in reversed(xs)], hexc("#566f3c")))
        T["ground"].append(("poly", [on(x, 1900 + 90 * math.sin(x * 0.003)) for x in xs] + [on(x, 3000) for x in reversed(xs)], hexc("#4a6034")))

        def field(x0, x1, d0, d1):
            T["ground"].append(("cell", [on(x0, d0), on(x1, d0), on(x1, d1), on(x0, d1)], hexc("#8d8f5a")))
            d = d0 + 6
            while d + 28 < d1:
                x = x0 + 6
                while x < x1 - 30:
                    xe = min(x + rnd.uniform(70, 200), x1 - 6)
                    col = rnd.choice(("#7fa05a", "#8fae55", "#a3a95a", "#6f9b6c", "#86a8a0"))   # young rice, ripe rice, flooded
                    T["ground"].append(("cell", [on(x, d), on(xe, d), on(xe, d + 28), on(x, d + 28)], hexc(col)))
                    x = xe + 6
                d += 38
        field(-1600, -300, 980, 1520)
        field(640, 1700, 1000, 1400)
        no_tree = [(-1650, -250, 940, 1560), (600, 1750, 960, 1460), (0, 200, 700, 1500)]

        # streets
        sx = [-1350, -1050, -750, -450, -230, 100, 420, 880, 1180, 1480, 1780]
        T["roads"].append(([on(x, 120) for x in range(-1500, 2001, 100)], 46))                 # the waterfront road
        T["roads"].append(([on(x, 640) for x in range(-1350, 1801, 100)], 22))                 # the back street
        for x in sx:
            T["roads"].append(([on(x, 120), on(x, 790 if x == 100 else 760)], 44 if x == 100 else 26))
        T["ground"].append(("cell", [on(20, 1240), on(180, 1240), on(180, 1420), on(20, 1420)], hexc("#9a9484")))   # shrine clearing

        res = []                                    # reserved (x0, x1, depth0, depth1): the town's landmarks
        def special(x0, x1, d, h, kind, col, label=None, lit=0):
            res.append((x0 - 4, x1 + 4, d - 4, d + h + 4))
            y = cy((x0 + x1) / 2) - d - h
            T["bld"].append((x0, y, x1 - x0, h, kind, hexc(col)))
            if label:
                T["labels"].append((label, V((x0 + x1) / 2 - 8 * len(label), y - 22)))
            if lit:
                T["lit"].append((V((x0 + x1) / 2, y + h / 2), lit))
        def plot(x0, x1, d0, d1, col):
            res.append((x0, x1, d0, d1))
            T["plots"].append(([on(x0, d0), on(x1, d0), on(x1, d1), on(x0, d1)], hexc(col)))

        special(520, 790, 150, 100, "market", "#b9b5a6", "FISH MARKET / AUCTION", 90)
        special(-150, -40, 150, 80, "icehouse", "#c8cdc9", "ICE HOUSE", 50)
        special(130, 166, 150, 32, "koban", "#7d8a72", "KOBAN", 30)
        special(-560, -480, 175, 66, "sento", "#5d4a3e", "BATHHOUSE", 50)
        T["deco"].append(("chimney", on(-552, 258)))
        plot(-1000, -800, 138, 330, "#8a7a5c")
        special(-990, -930, 270, 52, "tin", "#6a7f8a", "BOATYARD")
        T["deco"] += [("boat", on(-880, 200), 150, "#2f4a6b", 0.08), ("boat", on(-870, 255), 120, "#8a3b2f", -0.05)]
        plot(1200, 1450, 138, 270, "#8b7e62")
        T["deco"].append(("racks", [(on(1215, d), on(1435, d)) for d in (160, 190, 220, 250)]))
        T["labels"].append(("FISH DRYING", on(1250, 285)))
        plot(-1020, -780, 430, 600, "#a99d7c")
        special(-1020, -790, 610, 70, "school", "#c9c3ae", "SCHOOL", 70)
        special(-900, -810, 440, 60, "gym", "#8d9aa5")
        T["deco"].append(("flag", on(-960, 520)))
        plot(910, 1150, 430, 700, "#9a9484")
        special(980, 1080, 560, 80, "temple", "#3d4350", "TEMPLE", 40)
        T["deco"] += [("pagoda", on(1120, 520)), ("gate", on(1030, 440), 60)]
        special(55, 145, 1270, 50, "shrinehall", "#5f8f7a", "SHRINE")
        special(70, 130, 1340, 50, "shrine", "#5f8f7a")
        T["deco"].append(("steps", on(100, 780), on(100, 1240), 38))
        for d, w in ((830, 70), (1010, 60), (1190, 54)):
            T["deco"].append(("torii", on(100, d), w))
        for d in (900, 1050, 1200):
            T["deco"] += [("lantern", on(70, d)), ("lantern", on(130, d))]
        for p in ((-20, 1300), (195, 1280), (-30, 1410), (205, 1390), (60, 1460), (145, 1455)):
            T["trees"].append((on(*p), 34, hexc("#3f5a2e")))
        for _ in range(16):                                                                  # gear on the quay apron
            x = rnd.choice((rnd.uniform(-230, 20), rnd.uniform(100, 320), rnd.uniform(380, 560)))
            y = rnd.uniform(-470, -425)
            r = rnd.random()
            if r < 0.55:
                T["deco"].append(("crate", V(x, y), rnd.uniform(10, 17), rnd.choice(("#7a6246", "#9a7a50", "#6b5640"))))
            elif r < 0.85:
                T["deco"].append(("barrel", V(x, y), rnd.uniform(6, 9), rnd.choice(("#3d5568", "#7a3b2f", "#5b5b50"))))
            else:
                T["deco"].append(("net", V(x, y), rnd.uniform(14, 20)))

        # the houses: rows along every block, in two tiers (below and above the back street)
        def free(x0, x1, d0, d1):
            return not any(x0 < r[1] and x1 > r[0] and d0 < r[3] and d1 > r[2] for r in res)
        tiles = ("#4a4f57", "#3e4349", "#55575c", "#464a4f")
        tins = ("#8a4a38", "#5d6f7a", "#7d3c30", "#6a7f8a")
        for a, b in zip(sx, sx[1:]):
            for d_start, d_max in ((175, 600), (675, 745)):
                d = d_start
                while d < d_max:
                    rh = rnd.uniform(36, 60)
                    if d + rh > d_max:
                        break
                    x = a + 30
                    while x < b - 30:
                        w = rnd.uniform(34, 68)
                        if x + w > b - 30:
                            break
                        h = rh * rnd.uniform(0.82, 1.0)
                        if free(x, x + w, d, d + rh):
                            if rnd.random() < 0.12:
                                if rnd.random() < 0.6:
                                    T["trees"].append((on(x + w / 2, d + h / 2), rnd.uniform(14, 22), mix(hexc("#4a6a34"), hexc("#6a8a44"), rnd.random())))
                            else:
                                r = rnd.random()
                                kind, col = (("concrete", "#aaa79b") if r < 0.08 else ("tin", rnd.choice(tins)) if r < 0.35 else ("house", rnd.choice(tiles)))
                                y = cy(x + w / 2) - d - h
                                T["bld"].append((x, y, w, h, kind, hexc(col)))
                                if rnd.random() < 0.4:
                                    T["lit"].append((V(x + w / 2, y + h / 2), 40))
                        x += w + rnd.uniform(6, 14)
                    d += rh + rnd.uniform(14, 22)

        for i, x in enumerate(range(-1400, 1001, 140)):                                      # utility poles and street lamps
            T["poles"].append(on(x, 86))
            if i % 2 == 0:
                T["lamps"].append(on(x, 86))
        for k, d in enumerate(range(220, 1250, 150)):
            T["lamps"].append(on(100 + (34 if k % 2 else -34), d))
        for _ in range(600):                                                                 # the wooded hills
            x, d = rnd.uniform(-1900, 2500), rnd.uniform(900, 2900)
            if d < edge(x) + 25 or any(r[0] < x < r[1] and r[2] < d < r[3] for r in no_tree):
                continue
            T["trees"].append((on(x, d), rnd.uniform(14, 30), mix(hexc("#3e5a2c"), hexc("#5f7d3d"), rnd.random())))
        return T

    def town_lights(self, g):
        out, z, sc = [], g.zoom, self.scale
        vr = math.hypot(W, H) * 0.5 / z + 300
        for p in self.town["lamps"]:
            if (p * sc - self.ship_pos).length() < vr:
                out.append((self.dsp(p), 90 * sc * z))
        for p, r in self.town["lit"]:
            if (p * sc - self.ship_pos).length() < vr:
                out.append((self.dsp(p), r * sc * z))
        return out

    def _town_ground(self, g):
        s, z, sc, T = g.screen, g.zoom, self.scale, self.town
        self._vr = math.hypot(W, H) * 0.5 / z * 1.05 + 60
        cl = lambda p: (clamp(p[0], -30000, 30000), clamp(p[1], -30000, 30000))
        near = lambda c, r: (c * sc - self.ship_pos).length() < self._vr + r * sc
        self._near = near
        for kind, pts, col in T["ground"]:
            if kind == "cell":
                if not near((pts[0] + pts[2]) * 0.5, (pts[2] - pts[0]).length() * 0.5 + 40):
                    continue
            pygame.draw.polygon(s, col, [cl(self.dsp(p)) for p in pts])
        for pts, col in T["plots"]:
            pygame.draw.polygon(s, col, [cl(self.dsp(p)) for p in pts])
        for pts, w in T["roads"]:
            sp = [cl(self.dsp(p)) for p in pts]
            wpx = max(2, int(w * sc * z))
            thick_polyline(s, hexc("#6e6858"), sp, wpx + 4)
            thick_polyline(s, hexc("#8a8372"), sp, wpx)
        for d in T["deco"]:
            if d[0] == "steps" and near((d[1] + d[2]) * 0.5, (d[2] - d[1]).length() * 0.5 + 40):
                a, b, w = d[1], d[2], d[3]
                dirv = (b - a).normalize()
                perp = V(-dirv.y, dirv.x) * (w * 0.5)
                for i in range(int((b - a).length() / 12)):
                    c = a + dirv * (i * 12)
                    pygame.draw.line(s, hexc("#b9b5a8") if i % 2 == 0 else hexc("#8e8a7e"), self.dsp(c - perp), self.dsp(c + perp), max(1, int(6 * sc * z)))

    def _hip(self, g, x, y, w, h, col):
        """A hipped temple roof: broad eaves, a stepped crown and a ridge."""
        s, dark = g.screen, hexc("#2b2118")
        pygame.draw.polygon(s, col, [self.dsp(p) for p in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))])
        i = min(w, h) * 0.22
        pygame.draw.polygon(s, mix(col, (255, 255, 255), 0.18), [self.dsp(p) for p in ((x + i, y + i), (x + w - i, y + i), (x + w - i, y + h - i), (x + i, y + h - i))])
        pygame.draw.line(s, mix(col, (0, 0, 0), 0.35), self.dsp((x + i * 1.6, y + h / 2)), self.dsp((x + w - i * 1.6, y + h / 2)), max(1, int(4 * self.scale * g.zoom)))
        pygame.draw.polygon(s, dark, [self.dsp(p) for p in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))], 2)

    def _building(self, g, b):
        x, y, w, h, kind, col = b
        s, z, sc, dark = g.screen, g.zoom, self.scale, hexc("#2b2118")
        rect = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        if kind in ("concrete", "market", "icehouse", "school"):          # tall, so a shadow falls on the ground
            pygame.draw.polygon(s, hexc("#58633b"), [self.dsp((px + 7, py + 6)) for px, py in rect])
        if kind in ("temple", "shrine", "shrinehall"):
            self._hip(g, x, y, w, h, col)
            return
        sp = [self.dsp(p) for p in rect]
        pygame.draw.polygon(s, col, sp)
        lw = max(1, int(3 * sc * z))
        if kind in ("house", "tin", "sento", "koban"):                       # gable: the far half of the roof is in shade
            shade = mix(col, (0, 0, 0), 0.22)
            if w >= h:
                pygame.draw.polygon(s, shade, [self.dsp(p) for p in ((x, y + h / 2), (x + w, y + h / 2), (x + w, y + h), (x, y + h))])
                pygame.draw.line(s, mix(col, (0, 0, 0), 0.4), self.dsp((x, y + h / 2)), self.dsp((x + w, y + h / 2)), lw)
            else:
                pygame.draw.polygon(s, shade, [self.dsp(p) for p in ((x + w / 2, y), (x + w, y), (x + w, y + h), (x + w / 2, y + h))])
                pygame.draw.line(s, mix(col, (0, 0, 0), 0.4), self.dsp((x + w / 2, y)), self.dsp((x + w / 2, y + h)), lw)
            if kind == "tin" and w * sc * z > 40:                              # corrugations
                for k in range(1, int(w / 9)):
                    pygame.draw.line(s, mix(col, (255, 255, 255), 0.12), self.dsp((x + k * 9, y + 2)), self.dsp((x + k * 9, y + h - 2)), 1)
            if kind == "koban":
                pygame.draw.circle(s, (230, 60, 50), self.dsp((x + w / 2, y + h * 0.8)), max(2, int(5 * sc * z)))
        elif kind == "concrete":
            pygame.draw.polygon(s, mix(col, (0, 0, 0), 0.25), [self.dsp(p) for p in ((x + 4, y + 4), (x + w - 4, y + 4), (x + w - 4, y + h - 4), (x + 4, y + h - 4))], 2)
            pygame.draw.circle(s, hexc("#6b5a48"), self.dsp((x + w * 0.7, y + h * 0.35)), max(3, int(8 * sc * z)))         # water tank
        elif kind == "market":
            for k in range(0, int(w / 30)):                                   # saw-tooth roof lights
                c = hexc("#8aa0ad") if k % 2 == 0 else hexc("#a9b4b8")
                pygame.draw.polygon(s, c, [self.dsp(p) for p in ((x + k * 30, y), (x + k * 30 + 30, y), (x + k * 30 + 30, y + h), (x + k * 30, y + h))])
            pygame.draw.line(s, hexc("#5b6f7a"), self.dsp((x, y + h + 3)), self.dsp((x + w, y + h + 3)), max(2, int(8 * sc * z)))   # loading canopy
        elif kind == "icehouse":
            for k in range(1, int(h / 14)):
                pygame.draw.line(s, hexc("#9bb7c4"), self.dsp((x + 4, y + k * 14)), self.dsp((x + w - 4, y + k * 14)), max(1, int(4 * sc * z)))
            pygame.draw.circle(s, hexc("#8a8e8c"), self.dsp((x + w - 14, y + 14)), max(3, int(8 * sc * z)))                  # stack
        elif kind == "school":
            pygame.draw.polygon(s, mix(col, (0, 0, 0), 0.2), [self.dsp(p) for p in ((x + 5, y + 5), (x + w - 5, y + 5), (x + w - 5, y + h - 5), (x + 5, y + h - 5))], 2)
            tw = 26
            pygame.draw.polygon(s, hexc("#9c978a"), [self.dsp(p) for p in ((x + w / 2 - tw / 2, y - 10), (x + w / 2 + tw / 2, y - 10), (x + w / 2 + tw / 2, y + 16), (x + w / 2 - tw / 2, y + 16))])  # clock tower
        elif kind == "gym":
            for k in range(1, 8):
                pygame.draw.line(s, mix(col, (0, 0, 0), 0.25), self.dsp((x, y + k * h / 8)), self.dsp((x + w, y + k * h / 8)), 1)
        pygame.draw.polygon(s, dark, sp, 2 if kind in ("market", "school", "icehouse", "concrete") else 1)

    def _town_deco(self, g, d):
        s, z, sc, dark = g.screen, g.zoom, self.scale, hexc("#2b2118")
        k, p = d[0], d[1]
        if k == "crate":
            q = d[2]
            pts = [self.dsp(p + V(a, b)) for a, b in ((0, 0), (q, 0), (q, q), (0, q))]
            pygame.draw.polygon(s, hexc(d[3]), pts)
            pygame.draw.polygon(s, dark, pts, 1)
        elif k == "barrel":
            c = self.dsp(p)
            pygame.draw.circle(s, hexc(d[3]), c, max(2, int(d[2] * sc * z)))
            pygame.draw.circle(s, dark, c, max(2, int(d[2] * sc * z)), 1)
        elif k == "net":
            c, r = self.dsp(p), max(3, int(d[2] * sc * z))
            pygame.draw.circle(s, (86, 104, 84), c, r)
            pygame.draw.line(s, (60, 76, 60), c + V(-r, -r // 2), c + V(r, r // 2), 1)
            pygame.draw.line(s, (60, 76, 60), c + V(-r, r // 2), c + V(r, -r // 2), 1)
        elif k == "boat":
            ln = d[2]
            shape = [(ln * .5, 0), (ln * .2, -ln * .17), (-ln * .45, -ln * .17), (-ln * .5, -ln * .1), (-ln * .5, ln * .1), (-ln * .45, ln * .17), (ln * .2, ln * .17)]
            pts = [self.dsp(p + V(a, b).rotate_rad(d[4])) for a, b in shape]
            pygame.draw.polygon(s, hexc(d[3]), pts)
            pygame.draw.polygon(s, dark, pts, 2)
            pygame.draw.line(s, hexc("#d8d2c4"), self.dsp(p + V(-ln * .35, 0).rotate_rad(d[4])), self.dsp(p + V(ln * .4, 0).rotate_rad(d[4])), 1)
        elif k == "racks":
            for a, b in d[1]:
                pygame.draw.line(s, hexc("#6b5640"), self.dsp(a), self.dsp(b), max(1, int(3 * sc * z)))
                for i in range(int((b - a).length() / 14)):
                    c = a + (b - a).normalize() * (6 + i * 14)
                    pygame.draw.line(s, (205, 210, 214), self.dsp(c), self.dsp(c + V(0, 7)), max(1, int(3 * sc * z)))
        elif k == "chimney":
            c, r = self.dsp(p), max(3, int(8 * sc * z))
            pygame.draw.circle(s, dark, c, r)
            pygame.draw.circle(s, hexc("#8a6a58"), c, max(2, r - 2))
        elif k == "pagoda":
            for size, col in ((46, "#3d4350"), (36, "#4a5260"), (26, "#586272"), (16, "#6a7585")):
                pts = [self.dsp(p + V(a, b) * size / 2) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                pygame.draw.polygon(s, hexc(col), pts)
                pygame.draw.polygon(s, dark, pts, 1)
            pygame.draw.circle(s, GOLD, self.dsp(p), max(2, int(3 * sc * z)))
        elif k == "gate":
            w = d[2]
            pygame.draw.line(s, hexc("#4a3a2a"), self.dsp(p + V(-w / 2 - 8, 0)), self.dsp(p + V(w / 2 + 8, 0)), max(3, int(14 * sc * z)))
            pygame.draw.line(s, hexc("#2b2118"), self.dsp(p + V(-w / 2 - 8, 0)), self.dsp(p + V(w / 2 + 8, 0)), max(1, int(3 * sc * z)))
        elif k == "torii":
            w = d[2]
            for sgn in (-1, 1):
                pygame.draw.circle(s, hexc("#7a2a22"), self.dsp(p + V(sgn * w / 2, 0)), max(2, int(5 * sc * z)))
            pygame.draw.line(s, RED, self.dsp(p + V(-w / 2 - 8, 0)), self.dsp(p + V(w / 2 + 8, 0)), max(2, int(8 * sc * z)))
            pygame.draw.line(s, dark, self.dsp(p + V(-w / 2 - 8, 0)), self.dsp(p + V(w / 2 + 8, 0)), 1)
        elif k == "lantern":
            pts = [self.dsp(p + V(a, b) * 5) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            pygame.draw.polygon(s, hexc("#9a968a"), pts)
            pygame.draw.polygon(s, dark, pts, 1)
        elif k == "flag":
            c = self.dsp(p)
            pygame.draw.circle(s, hexc("#8a8a84"), c, max(2, int(3 * sc * z)))
            fl = [self.dsp(p + V(a, b)) for a, b in ((0, -3), (20, -3), (20, 9), (0, 9))]
            pygame.draw.polygon(s, (235, 235, 230), fl)
            pygame.draw.circle(s, (200, 40, 40), self.dsp(p + V(10, 3)), max(2, int(3.5 * sc * z)))

    def _town_up(self, g):
        s, z, sc, T = g.screen, g.zoom, self.scale, self.town
        near = self._near
        for d in T["deco"]:
            if d[0] in ("crate", "barrel", "net", "boat", "racks") and near(d[1] if d[0] != "racks" else d[1][0][0], 160):
                self._town_deco(g, d)
        for b in T["bld"]:
            if near(V(b[0] + b[2] / 2, b[1] + b[3] / 2), max(b[2], b[3]) * 0.7 + 12):
                self._building(g, b)
        for d in T["deco"]:
            if d[0] in ("chimney", "pagoda", "gate", "torii", "lantern", "flag") and near(d[1], 60):
                self._town_deco(g, d)
        wire = hexc("#2b2118")
        pp = T["poles"]
        for a, b in zip(pp, pp[1:]):
            if near((a + b) * 0.5, 100):
                pygame.draw.line(s, wire, self.dsp(a), self.dsp(b), 1)
        night = self.daylight() < 0.5
        for p in pp:
            if near(p, 20):
                c = self.dsp(p)
                pygame.draw.line(s, hexc("#3a2e22"), c + V(-5, 0), c + V(5, 0), 2)
                pygame.draw.circle(s, hexc("#3a2e22"), c, max(2, int(3 * sc * z)))
        for p in T["lamps"]:
            if night and near(p, 20):
                pygame.draw.circle(s, (255, 232, 160), self.dsp(p), max(2, int(4 * sc * z)))
        for tp, r, col in T["trees"]:
            if near(tp, r + 10):
                c, rr = self.dsp(tp), max(3, int(r * sc * z))
                pygame.draw.circle(s, mix(col, (0, 0, 0), 0.3), c + V(rr * 0.25, rr * 0.25), rr)
                pygame.draw.circle(s, col, c, rr)
                pygame.draw.circle(s, mix(col, (255, 255, 255), 0.14), c + V(-rr * 0.2, -rr * 0.2), max(1, rr // 2))
        for text, p in T["labels"]:
            if near(p, 160):
                g.text(text, self.dsp(p), (255, 235, 170))

    # --- drawing
    def draw(self, g):
        """Render expensive water/coast/background artwork at 30 Hz and blit between refreshes.

        The simulation and foreground actors continue at the normal game tick. The
        sea pattern already consists of distant environmental decoration, so a
        bounded 30 Hz refresh avoids rebuilding hundreds of strokes and shoreline
        details on every displayed frame without tying physics to the render cache.
        """
        screen = g.screen
        elapsed = min(0.10, max(0.0, g.clock.get_time() / 1000.0))
        age = float(getattr(g, "_world_background_age", 1.0)) + elapsed
        size = screen.get_size()
        state = (size, round(g.zoom, 4))
        # v13.2.05: with no coast, town or breakwater in view the expensive land pass is skipped,
        # which lets the sea layer refresh every frame (no 30 Hz stutter against the 60 Hz hull).
        coast_visible = self._coast_in_view(g)
        g._world_background_interval = (1.0 / 30.0) if coast_visible else 0.0
        cache = getattr(g, "_world_background_cache", None)
        if (cache is None or cache.get_size() != size
                or state != getattr(g, "_world_background_state", None)
                or age >= g._world_background_interval):
            target = getattr(g, "_world_background_target", None)
            if target is None or target.get_size() != size:
                target = pygame.Surface(size).convert()
                g._world_background_target = target
            g.screen = target
            try:
                col = mix(SHALLOW, DEEP, smoothstep(400, 6000, self.dist()))
                target.fill(mix(col, STORM, self.sea_state * 0.45))
                ov = g.ov_w
                ov.fill((0, 0, 0, 0))
                self._waves(g, ov)
                self._coast_bands(g, ov)
                self._flecks(g, ov)
                self._ripples(g, ov)
                self._wake(g, ov)
                self._hull_foam(g, ov)
                heave = self.hull_waves.heave if self.hull_waves is not None else 0.0
                shadow = [g.S(p + g.ship.slope * 14 + V(0, 8.0 + clamp(heave * 0.05, -6.0, 6.0))) for p in g.ship.hull]
                pygame.draw.polygon(ov, (0, 0, 0, 70), shadow)
                target.blit(ov, (0, 0))
                if coast_visible:
                    self._land(g)
            finally:
                g.screen = screen
            g._world_background_cache = target
            g._world_background_state = state
            g._world_background_age = 0.0
        else:
            g._world_background_age = age
        screen.blit(g._world_background_cache, (0, 0))

    def _waves(self, g, ov):
        w, z = self.waves, g.zoom
        r = math.hypot(W, H) * 0.5 / z * 1.05 + 60
        vis = clamp(0.06 + w.strength * 0.9, 0.0, 0.45)
        for i in range(w.count()):
            k, lam, dw = w.k(i), w.wavelength(i), w.dir(i)
            d = dw.rotate_rad(-self.heading)
            p = V(d.y, -d.x)
            phase0 = k * dw.dot(self.ship_pos) - w.omega(i) * self.time + w.phase(i)
            n0 = math.ceil((-k * r + phase0 - math.pi / 2) / TAU) - 1
            n1 = math.floor((k * r + phase0 - math.pi / 2) / TAU) + 1
            a = vis * (1 - 0.15 * i)
            steps = int(math.ceil(2 * r / 80))
            for n in range(n0, n1 + 1):
                sc = (math.pi / 2 + TAU * n - phase0) / k
                if i < 2:
                    sa, sb = sc + lam * 0.25, sc + lam * 0.75
                    quad = [d * sa + p * -r, d * sa + p * r, d * sb + p * r, d * sb + p * -r]
                    pygame.draw.polygon(ov, (0, 0, 0, int(255 * (0.05 + 0.06 * vis))), [g.S(q) for q in quad])
                pts = []
                for j in range(steps + 1):
                    u = -r + 2 * r * j / steps
                    wob = math.sin(u * 0.012 + n * 1.9 + self.time * 0.7) * lam * 0.035
                    pts.append(g.S(d * (sc + wob) + p * u))
                pygame.draw.lines(ov, (255, 255, 255, int(255 * a)), False, pts, max(1, 3 - i))

    def _coast_bands(self, g, ov):
        pts = [g.S(self.deck_of(q)) for q in self.coast_w]
        thick_polyline(ov, (140, 217, 204, 115), pts, int(300 * g.zoom))
        thick_polyline(ov, (230, 225, 204, 255), pts, int(52 * g.zoom))

    def _flecks(self, g, ov):
        cell = 120 * self.scale
        r = math.hypot(W, H) * 0.5 / g.zoom
        wc = self.ship_pos
        dens = 0.12 + 0.55 * self.waves.strength
        wind = V(1, 0).rotate_rad(self.wave_direction).rotate_rad(-self.heading)
        for cx in range(math.floor((wc.x - r) / cell), math.floor((wc.x + r) / cell) + 1):
            for cy in range(math.floor((wc.y - r) / cell), math.floor((wc.y + r) / cell) + 1):
                if hash01(cx, cy, 1) > dens:
                    continue
                wp = V((cx + hash01(cx, cy, 2)) * cell, (cy + hash01(cx, cy, 3)) * cell)
                if in_poly(wp, self.land_w):
                    continue
                sp = self.deck_of(wp)
                ln = (10 + 20 * hash01(cx, cy, 4)) * self.scale
                tw = 0.5 + 0.5 * math.sin(self.time * 1.3 + hash01(cx, cy, 5) * TAU)
                pygame.draw.line(ov, (255, 255, 255, int(255 * (0.1 + 0.25 * tw))),
                                 g.S(sp - wind * ln * 0.5), g.S(sp + wind * ln * 0.5), max(1, int(2 * self.scale * g.zoom)))

    def _wake(self, g, ov):
        """Render persistent foam as layered wash, broken crests, and spray flecks.

        All shape variation is derived from each patch's seed, so texture is stable
        between frames rather than sparkling randomly. The system remains bounded
        by SeaFoamSystem's patch cap and draws onto the existing water overlay.
        """
        if not self.foam.patches:
            return

        def seeded(seed, index, salt=0):
            # These values are fixed for a patch; cache the expensive trig hash.
            return _foam_seeded(int(seed), int(index), int(salt))

        for patch in self.foam.patches:
            local = V(*world_to_view(patch.x, patch.y, self.ship_pos.x,
                                     self.ship_pos.y, self.heading))
            # Convert the recorded world angle to the current ship-centred camera.
            angle = patch.angle - self.heading
            fade = patch.opacity
            if fade <= 0.01:
                continue

            age = patch.normalized_age
            # Old foam breaks into smaller islands as well as fading away.
            size_fade = 0.80 + 0.20 * (1.0 - age)
            length = max(2.0, patch.length * size_fade)
            width = max(1.5, patch.width * (0.82 + 0.18 * (1.0 - age)))
            screen_width = max(1.0, width * g.zoom)
            alpha = int(clamp(255.0 * fade, 0.0, 230.0))
            ca, sa = math.cos(angle), math.sin(angle)

            def shape_points(scale, phase=0.0):
                # Immutable normalized outlines are cached by kind/seed/phase;
                # current patch size, age and orientation are still applied live.
                template = _foam_shape_template(patch.kind, int(patch.seed), float(phase))
                points = []
                for along_frac, across_frac in template:
                    along = along_frac * length * 0.5 * scale
                    across = across_frac * width * 0.5 * scale
                    points.append(g.S(local + V(ca * along - sa * across,
                                                sa * along + ca * across)))
                return points

            # Three value layers: cool water halo, blue-green transition, and a
            # broken bright core. This reads as foam sitting on water, not white paint.
            fringe_alpha = int(alpha * (0.30 if patch.kind != "spray" else 0.22))
            pygame.draw.polygon(ov, (80, 183, 199, fringe_alpha), shape_points(1.55, 0.08))
            mid_alpha = int(alpha * (0.42 if patch.kind == "spray" else 0.48))
            pygame.draw.polygon(ov, (178, 226, 229, mid_alpha), shape_points(1.20, -0.04))
            core_scale = 0.78 if patch.kind in ("crest", "spray") else 0.84
            core_alpha = int(alpha * (0.64 if patch.kind == "spray" else 0.91))
            pygame.draw.polygon(ov, (238, 250, 249, core_alpha), shape_points(core_scale, 0.0))

            if patch.kind in ("wake", "side", "bow"):
                # Two offset, interrupted foam seams mimic converging turbulence.
                seam_alpha = int(alpha * (0.40 + 0.16 * (1.0 - age)))
                for side in (-1, 1):
                    offset = width * (0.15 + 0.10 * seeded(patch.seed, side + 2, 1)) * side
                    start_x = -length * (0.28 + 0.08 * seeded(patch.seed, side + 3, 2))
                    end_x = length * (0.10 + 0.12 * seeded(patch.seed, side + 4, 3))
                    p0 = local + V(ca * start_x - sa * (offset - width * 0.06),
                                  sa * start_x + ca * (offset - width * 0.06))
                    p1 = local + V(ca * (-length * 0.04) - sa * offset,
                                  sa * (-length * 0.04) + ca * offset)
                    p2 = local + V(ca * end_x - sa * (offset + width * 0.04),
                                  sa * end_x + ca * (offset + width * 0.04))
                    # Draw separate segments with small gaps, not a continuous ribbon.
                    pygame.draw.line(ov, (251, 255, 255, seam_alpha), g.S(p0), g.S(p1),
                                     max(1, int(min(2.5, screen_width * 0.13))))
                    if seeded(patch.seed, side + 8, 4) > 0.26:
                        pygame.draw.line(ov, (255, 255, 255, int(seam_alpha * 0.82)),
                                         g.S(p1), g.S(p2), max(1, int(min(2.0, screen_width * 0.10))))
            elif patch.kind == "crest":
                # Ragged whitecap lips: uneven connected crests plus a detached lobe.
                lip = [
                    g.S(local + V(ca * along - sa * across,
                                  sa * along + ca * across))
                    for along, across in ((-length * 0.38, -width * 0.03),
                                          (-length * 0.22, width * 0.19),
                                          (-length * 0.02, width * 0.07),
                                          (length * 0.12, width * 0.24),
                                          (length * 0.31, width * 0.02))
                ]
                pygame.draw.lines(ov, (255, 255, 255, int(alpha * 0.70)), False, lip,
                                  max(1, int(min(3.0, screen_width * 0.15))))
                detached = local + V(ca * length * 0.22 - sa * width * 0.38,
                                     sa * length * 0.22 + ca * width * 0.38)
                pygame.draw.circle(ov, (246, 255, 255, int(alpha * 0.54)), g.S(detached),
                                   max(1, int(screen_width * 0.15)))
            else:  # spray/spindrift: thin, wind-blown streaks which rapidly dissolve
                p0 = local + V(ca * (-length * 0.38), sa * (-length * 0.38))
                p1 = local + V(ca * (length * 0.34), sa * (length * 0.34))
                pygame.draw.line(ov, (250, 255, 255, int(alpha * 0.66)), g.S(p0), g.S(p1),
                                 max(1, int(min(2.0, screen_width * 0.22))))

            # Seeded micro-froth breaks the silhouette and varies the surface texture.
            # Spray receives fewer flecks; older patches retain fewer bright points.
            fleck_count = 2 if patch.kind == "spray" else (5 if patch.kind == "crest" else 4)
            fleck_alpha = int(alpha * (0.26 + 0.24 * (1.0 - age)))
            for idx in range(fleck_count):
                along = (seeded(patch.seed, idx, 5) - 0.5) * length * 0.95
                across = (seeded(patch.seed, idx, 6) - 0.5) * width * 1.9
                # Flecks are slightly more likely to sit at the broken edge than centre.
                if abs(across) < width * 0.28:
                    across = math.copysign(width * (0.30 + 0.30 * seeded(patch.seed, idx, 7)),
                                           across if across else (1 if idx % 2 else -1))
                point = local + V(ca * along - sa * across,
                                  sa * along + ca * across)
                radius = max(1, int((0.8 + 1.5 * seeded(patch.seed, idx, 8)) * g.zoom))
                pygame.draw.circle(ov, (245, 253, 252, fleck_alpha), g.S(point), radius)

            # A few small air bubbles on the energetic side of moving-water patches.
            if patch.kind in ("wake", "bow") and age < 0.78 and screen_width > 2.2:
                for idx in range(2):
                    along = length * (0.08 + 0.25 * seeded(patch.seed, idx, 9))
                    across = width * (0.35 + 0.30 * seeded(patch.seed, idx, 10)) * (1 if idx else -1)
                    point = local + V(ca * along - sa * across,
                                      sa * along + ca * across)
                    pygame.draw.circle(ov, (252, 255, 255, int(alpha * 0.46)),
                                       g.S(point), max(1, int(screen_width * 0.11)))

    def _coast_in_view(self, g):
        """True when land, the town, the berth or the breakwater could be on screen."""
        reach = math.hypot(W, H) * 0.5 / max(0.05, g.zoom) * 1.3 + 700.0 * self.scale
        p = self.ship_pos
        if in_poly(p, self.land_w):
            return True
        for a, b in zip(self.coast_w, self.coast_w[1:]):
            if p.distance_to(closest_on_seg(p, a, b)) < reach:
                return True
        if p.distance_to(closest_on_seg(p, self.bw_a, self.bw_b)) < reach:
            return True
        return p.distance_to(self.berth) < reach

    def _ripples(self, g, ov):
        """Expanding rings from the hull, propeller and wave slaps (world-anchored, ship-frame drawn)."""
        if not self.ripples.ripples:
            return
        reach = math.hypot(W, H) * 0.5 / max(0.05, g.zoom) * 1.1
        for rp in self.ripples.ripples:
            op = rp.opacity
            if op <= 0.02:
                continue
            c = V(*world_to_view(rp.x, rp.y, self.ship_pos.x, self.ship_pos.y, self.heading))
            if c.length() - rp.radius * 1.4 > reach:
                continue
            ang = rp.stretch_angle - self.heading
            ca, sa = math.cos(ang), math.sin(ang)
            for ring, (scale, fade) in enumerate(((1.0, 1.0), (0.62, 0.55))):
                r = rp.radius * scale
                if r < 3.0:
                    continue
                pts = []
                steps = 18
                for k in range(steps):
                    th = TAU * k / steps
                    wob = 1.0 + 0.07 * math.sin(3.0 * th + rp.seed * 0.0001 + ring) + 0.04 * math.sin(5.0 * th - rp.seed * 0.00007)
                    u = r * wob * (1.0 + rp.stretch) * math.cos(th)
                    v = r * wob * (1.0 - 0.5 * rp.stretch) * math.sin(th)
                    pts.append(g.S(c + V(ca * u - sa * v, sa * u + ca * v)))
                alpha = int(150 * op * fade)
                if alpha > 3:
                    pygame.draw.lines(ov, (222, 243, 247, alpha), True, pts, max(1, int((2.4 - 0.9 * ring) * g.zoom)))

    def _hull_foam(self, g, ov):
        """Foam collar where the hull meets the sea: a broken white line that thickens with sea, speed, roll and strikes."""
        ship = g.ship
        hull = ship.hull
        n = len(hull)
        t = self.time
        sea = clamp(self.waves.strength * 1.5, 0.0, 1.0)
        speed = clamp(self.speed / max(1.0, self.max_speed), 0.0, 1.0)
        roll = clamp(abs(getattr(g, "roll_v", 0.0)) * 0.35, 0.0, 1.0)
        imm = self.hull_waves.immersion if self.hull_waves is not None else {}
        base = 0.04 + 0.50 * sea + 0.30 * speed + 0.25 * roll + 0.35 * (1.0 - ship.freeboard_factor)
        L = ship.length
        for i in range(n):
            a, b = hull[i], hull[(i + 1) % n]
            seg = b - a
            ln = seg.length()
            if ln < 1.0:
                continue
            tan = seg / ln
            nrm = V(tan.y, -tan.x)
            mid = (a + b) * 0.5
            if nrm.dot(mid) < 0:
                nrm = -nrm
            zone = "bow" if mid.x > L * 0.30 else ("stern" if mid.x < -L * 0.47 else ("stbd" if mid.y > 0 else "port"))
            local = base + 0.9 * imm.get(zone, 0.0) + (0.40 * speed if zone == "bow" else 0.0)
            if local < 0.07:
                continue
            dashes = max(1, int(ln / 30.0))
            for j in range(dashes):
                h = hash01(i, j, 11)
                wv = 0.5 + 0.5 * math.sin(t * (0.9 + 0.8 * h) + h * TAU)
                strength = local * (0.35 + 0.95 * wv) - 0.22 * h
                if strength <= 0.06:
                    continue
                u0 = (j + 0.1 + 0.3 * hash01(i, j, 12)) / dashes
                u1 = min(1.0, u0 + (0.40 + 0.55 * hash01(i, j, 13)) / dashes)
                out = 4.0 + 10.0 * strength + 5.0 * h
                p0 = a + seg * u0 + nrm * out
                p1 = a + seg * u1 + nrm * (out + (h - 0.5) * 4.0)
                alpha = int(clamp(255 * strength, 0, 240))
                wd = max(1, int((2.0 + 4.0 * strength) * g.zoom))
                pygame.draw.line(ov, (120, 200, 212, alpha // 4), g.S(p0 + nrm * 4.0), g.S(p1 + nrm * 4.0), wd + 4)
                pygame.draw.line(ov, (244, 252, 252, alpha), g.S(p0), g.S(p1), wd)

    def _land(self, g):
        s = g.screen
        pygame.draw.polygon(s, LAND, [g.S(self.deck_of(q)) for q in self.land_w])
        self._town_ground(g)
        dark = hexc("#2b2118")
        pygame.draw.polygon(s, hexc("#9a968a"), [self.dsp(p) for p in
                            [(-250, -400), (-100, -380), (500, -390), (600, -410), (600, -480), (-250, -480)]])
        for (x, y, w, h) in [(40, -384, 30, 86), (330, -392, 30, 92)]:
            pts = [self.dsp(p) for p in [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]
            pygame.draw.polygon(s, hexc("#6b5640"), pts)
            pygame.draw.polygon(s, dark, pts, 2)
        self._town_up(g)
        for (px, py, ln, c) in [(130, -345, 90, "#8a3b2f"), (210, -340, 110, "#2f4a6b"), (440, -348, 100, "#c9c1ad")]:
            shape = [(ln * .5, 0), (ln * .2, -ln * .17), (-ln * .45, -ln * .17), (-ln * .5, -ln * .1),
                     (-ln * .5, ln * .1), (-ln * .45, ln * .17), (ln * .2, ln * .17)]
            pts = [self.dsp((px + a, py + b)) for a, b in shape]
            pygame.draw.polygon(s, hexc(c), pts)
            pygame.draw.polygon(s, dark, pts, 2)
        bx, by = self.berth.x / self.scale, self.berth.y / self.scale          # the berth: four mooring piles round the ship
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            c = self.dsp((bx + sx * 205, by + sy * 70))
            pygame.draw.circle(s, hexc("#2b2118"), c, max(3, int(11 * self.scale * g.zoom)))
            pygame.draw.circle(s, hexc("#7a6a52"), c, max(2, int(7 * self.scale * g.zoom)))
        g.text("BERTH  (D: autodock)", self.dsp((bx - 60, by + 85)), (255, 235, 170))
        a, b = self.dsp((1000, -500)), self.dsp((1500, -330))
        pygame.draw.line(s, hexc("#7d7a72"), a, b, max(3, int(40 * self.scale * g.zoom)))
        pygame.draw.line(s, hexc("#a09c92"), a, b, max(2, int(26 * self.scale * g.zoom)))
        pygame.draw.circle(s, hexc("#e8e4d8"), b, int(24 * self.scale * g.zoom))
        pygame.draw.circle(s, RED, b, int(14 * self.scale * g.zoom))
        if self.time % 4.0 < 0.6:
            pygame.draw.circle(s, (255, 242, 150), b, int(8 * self.scale * g.zoom))


# ------------------------------------------------------------------ slime

class Patch:
    """Something slippery on the deck. Slime comes off the hauled line; blood comes from the cutting table."""

    def __init__(self, pos, kind="slime", radius=None):
        self.pos = V(pos)
        self.kind = kind
        self.radius = radius if radius is not None else (random.uniform(55, 85) if kind == "slime" else random.uniform(22, 38))
        self.grip = 0.15 if kind == "slime" else 0.4
        self.life = 150.0 if kind == "slime" else 260.0
        self.age = 0.0
        self.cleaning = 0.0
        self.claimed_by = None
        self.shape = [V(1, 0).rotate_rad(TAU * i / 14) * self.radius * random.uniform(0.78, 1.05) for i in range(14)]

    def free_for(self, s):
        return self.claimed_by is None or self.claimed_by is s or self.claimed_by.mode != Sailor.ABOARD

    def update(self, dt):
        self.age += dt

    def draw(self, g):
        a = clamp(1 - self.cleaning, 0, 1) * clamp((self.life - self.age) / 30.0, 0, 1)
        if self.kind == "blood":                      # fresh blood is bright, and dries dark
            col = mix((170, 24, 24), (88, 22, 20), clamp(self.age / 120.0, 0.0, 1.0))
            pygame.draw.polygon(g.ov_d, col + (int(255 * 0.7 * a),), [g.SS(self.pos + p) for p in self.shape])
            pygame.draw.circle(g.ov_d, (230, 90, 80, int(255 * 0.22 * a)),
                               g.SS(self.pos + V(-self.radius * 0.2, -self.radius * 0.2)), max(1, int(self.radius * 0.22 * g.zoom)))
            return
        pygame.draw.polygon(g.ov_d, (107, 153, 102, int(255 * 0.55 * a)), [g.SS(self.pos + p) for p in self.shape])
        pygame.draw.circle(g.ov_d, (204, 242, 204, int(255 * 0.25 * a)),
                           g.SS(self.pos + V(-self.radius * 0.2, -self.radius * 0.2)), max(1, int(self.radius * 0.25 * g.zoom)))


# --------------------------------------------------------------- longline

class Catch:
    """One fish on its way from the hook to the auction. Quality (0..1) is what the buyers pay for."""

    def __init__(self, name, value, quality=1.0):
        self.name, self.value, self.quality = name, value, quality
        self.core = 17.0                      # core temperature, deg C
        self.bled = self.gutted = self.sliced = False
        self.alive = True                     # landed fish remain lively until the first bleed cut
        self.deck_exposure = 0.0
        self.rough_handling = 0.0
        self.claimed_by = None                # the sailor cutting it

    @classmethod
    def landed(cls, name, value, hooked_for, fought=0.0, rough=0.0, gaffed=0.0, no_gaff=False):
        """A fish that fought on the hook for a long time comes aboard already stressed. A long fight at the winch
        costs more, and more again if the brake was handled badly (rough = share of the fight spent too slack or too tight)."""
        q = 1.0 - 0.3 * clamp(hooked_for / 600.0, 0.0, 1.0) - 0.18 * clamp(fought / 45.0, 0.0, 1.0) - 0.12 * clamp(rough, 0.0, 1.0)
        q -= 0.06 * clamp(gaffed / 15.0, 0.0, 1.0) + (0.05 if no_gaff else 0.0)       # a long struggle at the rail bruises the flesh
        return cls(name, value, q - random.uniform(0.0, 0.04))

    def tick(self, dt, env, cooling, in_hold=False, on_deck=False):
        """Core temperature follows its surroundings; warmth, blood, rough handling and deck exposure reduce value."""
        tau = (90.0 if self.gutted else 420.0) if cooling else (250.0 if in_hold else (450.0 if self.gutted else 600.0))
        self.core += (env - self.core) * (1.0 - math.exp(-dt / tau))
        rate = 0.00003 * 2.0 ** (self.core / 4.0)
        if not self.bled:
            rate += 0.001                     # lactic acid and stress hormones souring the meat
        if not self.gutted:
            rate *= 1.6                       # gut bacteria
        if on_deck:
            self.deck_exposure += dt
            # Extra loss is modest at first, but living/unprocessed fish worsen if left out.
            rate += 0.00012
            if self.alive:
                rate += 0.00018
            if self.deck_exposure > 45.0:
                rate += min(0.00030, (self.deck_exposure - 45.0) * 0.0000015)
        self.quality = max(0.0, self.quality - rate * dt)

    def damage_from_handling(self, amount):
        """Apply a bounded quality hit from impact or rough handling; return the actual loss."""
        loss = clamp(float(amount), 0.0, 0.08)
        old = self.quality
        self.quality = max(0.0, self.quality - loss)
        self.rough_handling = min(1.0, self.rough_handling + loss * 2.0)
        return old - self.quality

    def grade(self):
        return grade_of(self.quality)[0]

    def sale_value(self):
        return self.value * grade_of(self.quality)[1] * (1.0 if self.bled else 0.85) * (1.0 if self.gutted else 0.8)


class Table:
    """The cutting table: fish wait here to be bled, then gutted and de-gilled."""
    CAP = 6

    def __init__(self):
        self.raw = []

    def room(self):
        return len(self.raw) < self.CAP

    def _free(self, f, s):
        return f.claimed_by is None or f.claimed_by is s or f.claimed_by.mode != Sailor.ABOARD

    def has_work(self, s=None):
        return any(self._free(f, s) for f in self.raw)

    def take(self, s):
        for f in self.raw:
            if self._free(f, s):
                f.claimed_by = s
                return f
        return None


class FishItem:
    """A fish lying on the deck, waiting to be picked up."""

    def __init__(self, pos, fish):
        self.pos, self.fish = V(pos), fish
        self.claimed_by = None
        self.angle = random.uniform(0, TAU)
        self.thrash_timer = random.uniform(3.5, 6.5)
        self.thrash_anim = 0.0
        self.thrash_count = 0

    def free_for(self, s):
        return self.claimed_by is None or self.claimed_by is s or self.claimed_by.mode != Sailor.ABOARD

    def draw(self, g):
        c, z = g.SS(self.pos), g.zoom
        angle = self.angle
        if self.thrash_anim > 0.0:
            angle += math.sin(g.world.time * 34.0 + self.angle) * 0.42 * self.thrash_anim
        draw_fish(g.screen, self.fish.name, c, angle, 78 * z, clamp(self.fish.quality, 0.0, 1.0), 0.0, self.fish.bled)


class Fight:
    """A big fish alongside, fighting the hauler. Line tension runs 0..1.3 and the green band is the safe one.

    The fish pulls (in surges and the odd hard run), the swell heaves the ship, and the brake sets how much the winch
    resists. Too slack and the fish throws the hook; too tight and the snood parts, or the whole mainline if it is
    held there. Fish tire fastest while the tension sits in the band, so a steady hand ends it sooner and lands a
    fish in better condition. The crew work the brake on their own (a skilled hand holds it steadier);
    Z (ease off) and X (tighten) take over.
    """
    LO, HI = 0.35, 0.80

    def __init__(self, hook):
        self.hook, self.name = hook, hook["name"]
        self.strength = SPECIES.get(self.name, 0.5)
        self.stamina, self.time, self.rough = 1.0, 0.0, 0.0
        self.tension, self.seen, self.drag = 0.45, 0.45, 0.5
        self.slack_t = self.strain_t = self.over_t = 0.0
        self.phase = random.uniform(0, TAU)
        self.run_t, self.run_left, self.run_f = random.uniform(2.0, 4.0), 0.0, 1.0
        self.manual = False

    def pull(self):
        wob = 0.78 + 0.22 * math.sin(self.time * (1.3 + self.strength) + self.phase)
        return self.strength * (0.45 + 0.35 * self.stamina) * wob * self.run_f

    def update(self, dt, w, skill, keys, load=0.0):
        """Returns None while the fight goes on, or "tired" / "escaped" / "snood" / "parted".
        load is how taut the physical line is at the winch: a ship steaming away from a fish loads the brake."""
        self.time += dt
        if self.run_left > 0:
            self.run_left -= dt
        else:
            self.run_t -= dt
            if self.run_t <= 0:
                self.run_left = random.uniform(0.9, 1.6)
                self.run_t = random.uniform(3.0, 6.0)
        self.run_f = lerp(self.run_f, 1.8 if self.run_left > 0 else 1.0, 1 - math.exp(-6.0 * dt))
        up, down = keys[pygame.K_x], keys[pygame.K_z]
        self.manual = bool(up or down or keys[pygame.K_SPACE])
        if keys[pygame.K_SPACE]:
            self.drag = min(1.0, self.drag + 0.65 * dt)  # hold SPACE to work the brake
        elif up:
            self.drag = min(1.0, self.drag + 0.9 * dt)
        elif down:
            self.drag = max(0.0, self.drag - 0.9 * dt)
        else:                                              # the crewman on the brake: he feels the line a moment late
            self.seen = lerp(self.seen, self.tension, 1 - math.exp(-dt / (0.2 + 0.9 * (1.0 - skill))))
            self.drag += (0.58 - self.seen) * (0.9 + 0.6 * skill) * dt + random.gauss(0.0, 0.45 * (1.0 - skill)) * math.sqrt(dt)
            self.drag = clamp(self.drag, 0.0, 1.0)
        surge = 0.40 * w.waves.strength * math.sin(w.time * 1.9 + self.phase)          # the ship heaving on the swell
        target = (0.60 * self.pull() + 0.50 * self.drag + surge + 0.14 * (load - 0.4)
                  + 0.25 * load * clamp(w.speed / w.max_speed, 0.0, 1.0))
        self.tension = clamp(lerp(self.tension, target, 1 - math.exp(-4.0 * dt)), 0.0, 1.3)
        t = self.tension
        self.slack_t = self.slack_t + dt if t < 0.28 else max(0.0, self.slack_t - 0.8 * dt)
        self.strain_t = self.strain_t + dt if t > 0.92 else max(0.0, self.strain_t - 0.6 * dt)
        self.over_t = self.over_t + dt if t > 1.2 else max(0.0, self.over_t - dt)
        if t > 0.88 or t < 0.25:
            self.rough += dt
        zone = 1.0 if self.LO <= t <= self.HI else (1.35 if t > self.HI else 0.3)
        self.stamina -= 0.07 * zone / (0.4 + self.strength) * dt
        if self.over_t > 0.8:
            return "parted"
        if self.strain_t > 1.3:
            return "snood"
        if self.slack_t > 2.2:
            return "escaped"
        if self.stamina <= 0.12:
            return "tired"
        return None


class Longline:
    """The mainline as a chain of particles (position-based Verlet). Every point carries a depth z (world px, down).
    Floats ride the surface; the hooks between them sink until the line goes taut, which gives the sag. Currents move
    each point at its own depth, hooked fish pull on their hook, and the winch holds the head while hauling."""
    IDLE, SETTING, SOAKING, HAULING = range(4)
    FISH = [("albacore", 2400), ("yellowfin", 3800), ("bigeye", 5200), ("swordfish", 6500), ("blue shark", 600)]
    CAP = {"stern": 2, "hauler": 2, "gaff": 2, "carry": 1, "engine": 1, "dress": 2}
    FLOAT_EVERY = 8
    NORM = 1.6               # scales the summed species weights into a bite rate

    def __init__(self, g):
        self.g = g
        self.phase = self.IDLE
        self.pts = []                    # dicts: pos (WORLD coords), z, vel, vz, link, float, bait, fresh, fish, value, name
        self.claims = {k: [] for k in self.CAP}
        self.spacing, self.max_points = 260.0, 24
        self.bite_rate, self.haul_speed = 0.004, 160.0
        self.reach, self.snap = 700.0, 1500.0
        self.fight_range = 300.0         # a hooked fish this close to the hauler starts fighting
        self.fight = None
        self.gaff = None                 # the rail struggle once a tired fish is alongside
        self.slack = 1.25                # line paid out per unit of distance: more slack, deeper hooks
        self.dock_started = False
        self.soak_time = 0.0
        self.engaged = False
        self.landed = 0
        # the crew fishing on their own
        self.auto = False
        self.trip_end, self.trip_start, self.trip_days = None, 0.0, 0     # a captain-ordered trip: world time it ends / began, length in days
        self.stage = "off"               # off / travel / set / soak / haul / return
        self.stage_t = 0.0
        self.soak_goal = 60.0
        self.skip = False
        self.retries = 0
        # V13V1-11: retain the school and the plotted (belief-based) destination
        # during an auto-fishing transit so stale schools can be abandoned safely.
        self.auto_hotspot_target = None
        self.auto_hotspot_destination = None
        # Phase 6: durable gear state. The line is reusable, so chafe carries between sets.
        self.roller_bypassed = False
        self.roller_jammed = False
        self.roller_condition = 100.0
        self.line_condition = 100.0
        self.hauler_slip = 0.0
        self.hauler_drum_condition = 100.0
        self.roller_snag_timer = 0.0
        self.roller_snag_meter = 0.0
        self.buoy_snag_meter = 0.0
        self.last_buoy_snag_kind = ""
        self.roller_stress_time = 0.0
        self.line_strain_time = 0.0
        self._roller_warned = False
        self._slip_warned = False

    # ---- crew slots
    def wants(self, job):
        return (job == "stern" and self.phase == self.SETTING) or (job == "hauler" and self.phase == self.HAULING)

    def room(self, job, s):
        return s in self.claims[job] or len(self.claims[job]) < self.CAP[job]

    def claim(self, job, s):
        if s in self.claims[job]:
            return True
        if len(self.claims[job]) >= self.CAP[job]:
            return False
        self.claims[job].append(s)
        return True

    def release(self, s):
        for lst in self.claims.values():
            if s in lst:
                lst.remove(s)

    def power(self, job):
        k = 0.85 if self.g.harness else 1.0          # clipped on, they work a little slower
        return k * sum(0.6 + 0.8 * s.skill for s in self.claims[job] if s.working and s.mode == Sailor.ABOARD)

    @property
    def roller_state(self):
        if self.roller_jammed:
            return ROLLER_JAMMED
        return ROLLER_BYPASSED if self.roller_bypassed else ROLLER_WORKING

    def operate_roller(self, sailor=None):
        """M/context menu: clear a fouled line/buoy, clear a jam, or bypass the roller."""
        g = self.g
        if self.roller_snag_timer > 0.0 and not self.roller_jammed:
            target = V(-g.ship.length * 0.45, g.ship.beam * 0.08)
            worker = any(
                s.mode == Sailor.ABOARD and s.level == Level.MAIN and s.ladder is None
                and s.health > 0.0 and s.pos.distance_to(target) <= 245.0
                for s in g.sailors
            )
            if not worker:
                g.crew.say("Captain: The buoy/mainline is fouled at the stern gear. Send a deckhand aft, then clear it.")
                return False
            self.roller_snag_timer = 0.0
            self.roller_snag_meter = 0.0
            self.buoy_snag_meter = 0.0
            self._roller_warned = False
            g.record_log_entry("Deckhand cleared a fouled buoy/mainline from the stern roller.")
            g.crew.say("Deckhand frees the buoy/mainline from the stern roller. Ease the load as hauling resumes.")
            return True
        if self.roller_jammed:
            target = V(-g.ship.length * 0.45, 0.0)
            worker = any(
                s.mode == Sailor.ABOARD and s.level == Level.MAIN and s.ladder is None
                and s.health > 0.0 and s.pos.distance_to(target) <= 245.0
                for s in g.sailors
            )
            if not worker:
                g.crew.say("Captain: The stern roller is jammed. Send a deckhand aft, then press M to clear it.")
                return False
            self.roller_jammed = False
            self.roller_bypassed = False
            self.roller_condition = max(35.0, self.roller_condition)
            self.roller_snag_timer = 0.0
            self.roller_snag_meter = 0.0
            self.roller_stress_time = 0.0
            self._roller_warned = False
            g.crew.say("Deck crew clear the stern roller. The line is still worn; keep the load easy.")
            return True
        self.roller_bypassed = not self.roller_bypassed
        if self.roller_bypassed:
            g.crew.say("Captain: Bypass the stern roller. Watch the line—bulwark chafe and snags are more likely.")
        else:
            g.crew.say("Captain: Stern roller engaged. Keep the line seated in the roller.")
        return True

    def _line_load(self, head=None):
        """Estimate load at the stern/winch from line geometry, fish and sea state."""
        g, w = self.g, self.g.world
        sea = clamp(w.waves.strength + 0.8 * abs(g.eff_tilt()), 0.0, 1.6)
        speed = clamp(abs(w.speed) / max(w.max_speed, 1.0), 0.0, 1.0)
        load = 0.18 + 0.34 * self.head_load() + 0.12 * sea
        if self.phase == self.SETTING:
            load += 0.36 * speed
        elif self.phase == self.HAULING and head:
            if head.get("fish") and not head.get("tired"):
                load += 0.28 + 0.28 * SPECIES.get(head.get("name", "yellowfin"), 0.5)
            if self.fight is not None:
                load += 0.48 * clamp(self.fight.tension / 1.3, 0.0, 1.0)
        return clamp(load, 0.0, 1.8)

    def _part_line_from_chafe(self):
        g = self.g
        lost = len(self.pts)
        g.crew.say("The chafed mainline parts under load at the stern gear! Lost %d hooks." % lost)
        exposed = self.claims["stern"] + self.claims["hauler"]
        if not g.harness:
            for sailor in exposed:
                if sailor.mode == Sailor.ABOARD and random.random() < 0.42:
                    sailor.hurt(0.10 + 0.10 * max(0.0, 1.0 - self.line_condition / 20.0),
                                "whipped by a parted longline")
                    g.crew.say("%s is struck by the whipping line." % sailor.name)
        self.pts = []
        self.phase, self.stage = self.IDLE, "off"
        self.auto = False
        self.trip_end = None
        self.fight = self.gaff = None
        self.roller_snag_timer = 0.0
        self.line_strain_time = 0.0

    def _buoy_line_snag_exposure(self):
        """0..1 exposure when a marker buoy or a non-leading line span fouls the quarter roller."""
        if self.phase != self.HAULING or len(self.pts) < 3:
            return 0.0
        g, w = self.g, self.g.world
        # The roller is aft; the active hauler is set on the starboard quarter.
        roller = V(-g.ship.length * 0.32, g.ship.beam * 0.50)
        exposure = 0.0
        for index, point in enumerate(self.pts):
            if index == 0 or not point.get("float"):
                continue
            local = w.deck_of(point["pos"])
            d = local.distance_to(roller)
            if d < 132.0:
                exposure = max(exposure, clamp((132.0 - d) / 112.0, 0.0, 1.0))
        # The leading segment is intentionally attached to the winch. Other spans
        # near the roller can ride over the rail if the line and buoy sweep around.
        for index in range(2, len(self.pts)):
            a = w.deck_of(self.pts[index - 1]["pos"])
            b = w.deck_of(self.pts[index]["pos"])
            nearest = closest_on_seg(roller, a, b)
            d = nearest.distance_to(roller)
            if d < 46.0:
                exposure = max(exposure, clamp((46.0 - d) / 32.0, 0.0, 1.0))
        return exposure

    def _update_roller_and_line(self, dt):
        """Phase 6: line chafe, stern-roller snags/jams, and overload snap risk."""
        if dt <= 0.0:
            return
        if self.roller_snag_timer > 0.0:
            self.roller_snag_timer = max(0.0, self.roller_snag_timer - dt)
            if self.roller_snag_timer == 0.0:
                if self.last_buoy_snag_kind:
                    self.g.crew.say("The %s is free of the stern roller. Take the load gently." % self.last_buoy_snag_kind)
                    self.last_buoy_snag_kind = ""
                else:
                    self.g.crew.say("The line is free of the stern-gear snag. Take the load gently.")
        if self.phase not in (self.SETTING, self.HAULING) or not self.pts:
            self.hauler_slip = max(0.0, self.hauler_slip * math.exp(-2.0 * dt))
            self._roller_warned = False
            self._slip_warned = False
            return

        head = self.pts[0] if self.pts else None
        load = self._line_load(head)
        state = self.roller_state
        self.line_condition = max(0.0, self.line_condition - line_wear_per_second(load, state) * dt)
        if state == ROLLER_WORKING:
            sea = clamp(self.g.world.waves.strength, 0.0, 1.6)
            self.roller_condition = max(0.0, self.roller_condition - (0.0025 + 0.0035 * load + 0.0018 * sea) * dt)
            jam_threshold = 0.90 + 0.0025 * self.roller_condition
            if load > jam_threshold:
                self.roller_stress_time += (load - jam_threshold) * dt
            else:
                self.roller_stress_time = max(0.0, self.roller_stress_time - 0.8 * dt)
            if self.roller_condition < 35.0 and self.roller_stress_time > 4.0:
                self.roller_jammed = True
                self.roller_snag_timer = 0.0
                if not self._roller_warned:
                    self.g.crew.say("The stern roller has seized under load! Stop hauling and send a hand aft to clear it.")
                    self._roller_warned = True
                return
        else:
            self.roller_stress_time = max(0.0, self.roller_stress_time - 0.5 * dt)

        if not self.roller_jammed:
            self.roller_snag_meter += roller_snag_rate(load, state, self.roller_condition) * dt
            if self.roller_snag_meter >= 8.0:
                self.roller_snag_meter -= 8.0
                self.roller_snag_timer = random.uniform(1.2, 2.8)
                self.line_condition = max(0.0, self.line_condition - 0.8 * (2.0 if state != ROLLER_WORKING else 1.0))
                if not self._roller_warned or state != ROLLER_WORKING:
                    self.g.crew.say("The line snags at the %s stern gear! Ease the load." % ("bypassed" if state == ROLLER_BYPASSED else "worn"))
                    self._roller_warned = True
                workers = self.claims["stern"] if self.phase == self.SETTING else self.claims["hauler"]
                if not self.g.harness and load > 0.8:
                    for sailor in workers:
                        if sailor.mode == Sailor.ABOARD and random.random() < 0.16 * min(load, 1.4):
                            sailor.hurt(0.04 + 0.045 * load, "struck by line chafe at the stern gear")
                            self.g.crew.say("%s is struck by a whipping section of line." % sailor.name)

        # A marker buoy can foul the starboard-quarter roller and the bight of the
        # mainline can ride over the rail. This is spatially triggered, pauses the
        # winch for a short clearing interval, and can be manually cleared by a hand aft.
        exposure = self._buoy_line_snag_exposure() if self.phase == self.HAULING else 0.0
        if exposure > 0.05 and self.roller_snag_timer <= 0.0 and not self.roller_jammed:
            self.buoy_snag_meter += exposure * (0.45 + 0.55 * clamp(load, 0.0, 1.4)) * dt
        else:
            self.buoy_snag_meter = max(0.0, self.buoy_snag_meter - 0.75 * dt)
        if self.buoy_snag_meter >= 2.0 and self.roller_snag_timer <= 0.0 and not self.roller_jammed:
            self.buoy_snag_meter = 0.0
            self.roller_snag_timer = random.uniform(1.8, 3.2)
            self.last_buoy_snag_kind = "marker buoy" if any(
                p.get("float") and p is not self.pts[0]
                and self.g.world.deck_of(p["pos"]).distance_to(V(-self.g.ship.length * 0.32, self.g.ship.beam * 0.50)) < 132.0
                for p in self.pts) else "mainline"
            self.line_condition = max(0.0, self.line_condition - 0.45)
            self.g.record_log_entry("A %s fouled the starboard stern gear; the hauler paused for clearing." % self.last_buoy_snag_kind)
            self.g.crew.say("A %s fouls the starboard-quarter drum roller! Ease the load while the deckhand clears it." % self.last_buoy_snag_kind.capitalize())
            self._roller_warned = True

        if self.line_condition < 18.0 and load > 1.12:
            self.line_strain_time += dt
        else:
            self.line_strain_time = max(0.0, self.line_strain_time - 0.9 * dt)
        if self.line_strain_time > 2.2:
            self._part_line_from_chafe()

    # ---- orders from the player
    def toggle_auto(self):
        say = self.g.crew.say
        self.auto = not self.auto
        if self.auto:
            say("Captain: Right, we fish. Crew, get to it.")
        else:
            self.trip_end = None
            self.auto_hotspot_target = None
            self.auto_hotspot_destination = None
            say("Captain: Stand down once this one's finished." if self.stage != "off" else "Captain: Standing down.")

    def begin_manual_set(self):
        """Start one player-ordered longline set without enabling auto-fishing.

        The normal line state machine still handles the ship's slow setting run,
        automatic crew assignment, soaking, and the following haul.  Unlike L,
        this is a one-shot order: when the haul finishes, fishing remains stopped.
        """
        g, w = self.g, self.g.world
        log_event("manual_line_set_requested", {
            "auto": bool(self.auto), "stage": self.stage, "phase": self.phase,
            "distance_from_harbour": round(float(w.dist()), 2),
        })
        if self.auto:
            g.crew.say("Captain: Stand down auto-fishing before ordering a manual set.")
            return False
        if self.stage != "off" or self.phase != self.IDLE:
            g.crew.say("Captain: The line is already out. Finish the current operation first.")
            return False
        if g.crew.alarm_target is not None or w.dock_state is not None or w.rescue_to is not None:
            g.crew.say("Captain: We can't set the line during docking or a rescue.")
            return False
        if w.dist() < 900:
            g.crew.say("Not in the harbour. Take her out first.")
            return False

        # A set run needs a straight, uninterrupted stretch of water. Discard
        # only the committed course; the player's selected depth and bait remain.
        if w.route_waypoints:
            w.route_waypoints.clear()
            g.record_log_entry("Manual chart route cancelled to begin a manual line set.")
        w.destination = None
        w.manual_helm = False
        self._begin_set()
        if self.phase == self.SETTING and self.stage == "set":
            g.record_log_entry("Manual line setting started. Auto-fishing remains disabled.")
            log_event("manual_line_set_started", {
                "phase": self.phase, "stage": self.stage,
                "destination_set": w.destination is not None,
                "crew_at_roller": len(getattr(self, "claims", {}).get("stern", ())),
            })
            return True
        return False

    def haul_now(self):
        if self.stage == "soak":
            self.skip = True

    def adjust_slack(self, d):
        self.slack = clamp(round(self.slack + d, 2), SLACK_MIN, SLACK_MAX)
        self.g.crew.say("Line depth setting: x%.2f (%s). Applies to hooks set from now on." % (
            self.slack, "shallow" if self.slack < 1.15 else ("medium" if self.slack < 1.35 else "deep")))

    # ---- the particles
    def _new_point(self, pos, link):
        bait, fresh = self.g.take_bait()
        return {"pos": V(pos), "z": 0.0, "vel": V(0, 0), "vz": 0.0, "link": link, "float": len(self.pts) % self.FLOAT_EVERY == 0,
                "bait": bait, "fresh": fresh, "bottom": False, "fish": False, "value": 0, "name": ""}

    def _reverse(self):
        n = len(self.pts)
        links = [p["link"] for p in self.pts]
        self.pts.reverse()
        for j in range(1, n):                      # a segment's rest length belongs to its far end
            self.pts[j]["link"] = links[n - j]

    def head_load(self):
        """How taut the line is at the winch, 0..1: what the fish's pull (and a ship steaming away) feels like to the brake."""
        if len(self.pts) < 2:
            return 0.0
        a, b = self.pts[0], self.pts[1]
        d = math.sqrt((a["pos"] - b["pos"]).length_squared() + (a["z"] - b["z"]) ** 2)
        return smoothstep(0.80, 1.0, d / max(b["link"], 1.0))

    def hook_depth(self, p):
        return p["z"] * DEPTH_M

    def _inv_mass(self, i, p, hauling):
        if i == 0 and hauling:
            return 0.0                              # the winch holds the head
        if p["float"]:
            return 0.5 if hauling else 0.0          # floats are dragged in with the line, but ride the surface otherwise
        return 1.0

    def _physics(self, dt):
        w = self.g.world
        pts, n = self.pts, len(self.pts)
        if n == 0 or dt <= 0:
            return
        hauling = self.phase == self.HAULING
        sc = w.scale
        old = []
        # Keep the particle index in scope: setting/hauling enters this path as soon
        # as the first hook is emitted.  A plain ``for p in pts`` left ``i`` unset
        # and raised UnboundLocalError on the first physics tick, closing the game.
        for i, p in enumerate(pts):
            old.append((p["pos"].x, p["pos"].y, p["z"]))
            if i == 0 and hauling:
                p["pos"] += w.current(0.0) * dt * 0.3
                p["vel"], p["vz"] = V(0, 0), 0.0
                continue
            if p["float"] and not hauling:
                p["pos"] += w.current(0.0) * dt
                p["z"], p["vz"], p["vel"] = 0.0, 0.0, V(0, 0)
                continue
            target = V(w.current(p["z"] * DEPTH_M))
            vz_push = 0.0
            if p["fish"] and not p.get("tired"):          # a hooked fish swims off and dives, and the line feels it
                sp = SPECIES.get(p["name"], 0.5)
                p["sw"] = p.get("sw", random.uniform(0, TAU)) + random.gauss(0.0, 1.2) * math.sqrt(dt)
                target += V(1, 0).rotate_rad(p["sw"]) * (25.0 + 55.0 * sp)
                vz_push = 25.0 * math.sin(w.time * 0.9 + p["sw"] * 2.0)
            p["vel"] = p["vel"].lerp(target, 1.0 - math.exp(-1.6 * dt))
            if p["float"]:
                p["vz"] = 0.0
            else:
                p["vz"] += (150.0 * (1.15 if p["fish"] else 1.0) + vz_push) * dt
                p["vz"] *= math.exp(-3.2 * dt)
            p["pos"] += p["vel"] * dt
            p["z"] += p["vz"] * dt
        collided_points = set()
        for _ in range(6):                              # rope: it can go slack but never stretch
            for i in range(1, n):
                a, b = pts[i - 1], pts[i]
                ia, ib = self._inv_mass(i - 1, a, hauling), self._inv_mass(i, b, hauling)
                tot = ia + ib
                if tot <= 0:
                    continue
                dp, dz = b["pos"] - a["pos"], b["z"] - a["z"]
                d = math.sqrt(dp.length_squared() + dz * dz)
                rest = b["link"]
                if d <= rest or d < 1e-6:
                    continue
                k = (d - rest) / d / tot
                a["pos"] += dp * (k * ia)
                a["z"] += dz * (k * ia)
                b["pos"] -= dp * (k * ib)
                b["z"] -= dz * (k * ib)
            # Surface gear cannot pass through the coast, reef, hull, or a deployed
            # rescue boat. Leave point zero anchored at the winch/stern connection.
            for i, p in enumerate(pts):
                if i > 0:
                    radius = 27.0 if p["float"] else 8.0
                    corrected, contact = w.collide_longline_point(
                        p["pos"], radius, depth_m=float(p["z"]) * DEPTH_M)
                    if contact:
                        p["pos"] = corrected
                        collided_points.add(i)
                # Clamp in the same pass; the former extra full-list pass did
                # this six times without affecting any constraint calculation.
                if p["float"] or p["z"] < 0:
                    p["z"] = 0.0
        # Point contacts alone are insufficient for a 260-unit rope segment: a
        # long edge could straddle a narrow reef/beach without any particle landing
        # inside it. Sweep segment interiors after constraint solving and move the
        # adjacent particles clear on contact. Keep the stern attachment anchored.
        for i in range(1, n):
            a, b = pts[i - 1], pts[i]
            radius = 20.0 if (a["float"] or b["float"]) else 6.0
            depth_m = (float(a["z"]) + float(b["z"])) * 0.5 * DEPTH_M
            fixed, sample, contact = w.collide_longline_segment(
                a["pos"], b["pos"], radius, ignore_ship=(i == 1), depth_m=depth_m)
            if contact:
                shift = fixed - sample
                if i == 1:
                    b["pos"] += shift
                else:
                    a["pos"] -= shift * 0.5
                    b["pos"] += shift * 0.5
                collided_points.add(i - 1)
                collided_points.add(i)
        for i, p in enumerate(pts):
            floor = w.bottom_m(p["pos"].distance_to(HARBOUR) / sc) / DEPTH_M      # the seabed stops the hooks
            p["bottom"] = (not p["float"]) and p["z"] >= floor
            if p["bottom"]:
                p["z"] = floor
            kin = (i == 0 and hauling) or (p["float"] and not hauling)
            if kin:
                continue
            ox, oy, oz = old[i]
            v = V((p["pos"].x - ox) / dt, (p["pos"].y - oy) / dt)
            if v.length() > 400.0:
                v.scale_to_length(400.0)
            p["vel"] = V(0, 0) if i in collided_points else v
            p["vz"] = clamp((p["z"] - oz) / dt, -200.0, 200.0)

    # ---- line phases
    def _begin_set(self):
        g, w, say = self.g, self.g.world, self.g.crew.say
        self.auto_hotspot_target = None
        self.auto_hotspot_destination = None
        if w.dist() < 900:
            say("Not in the harbour. Take her out first.")
            self.auto = False
            self.stage = "off"
            return
        if self.auto:                                  # the crew pick a depth for the hour and the bait they have most of
            self.slack = 1.35 if w.daylight() < 0.4 else 1.2
            g.auto_bait()
        self.pts = []
        self.landed = 0
        self.gaff = None
        self.phase = self.SETTING
        self.stage = "set"
        w.destination = w.ship_pos + V(1, 0).rotate_rad(w.heading) * 40000
        w.ap_t = 0.0
        say("Captain: Setting the line. Hands to the stern.")

    def _end_setting(self, msg):
        if not self.pts:
            self.phase = self.IDLE
            self.g.crew.say("Nothing was set.")
            return
        self.pts[-1]["float"] = True                   # the end of the line carries a buoy
        self.phase = self.SOAKING
        self.soak_time = 0.0
        self.g.crew.say(msg)

    def _begin_haul(self):
        hp = self._haul_world()
        if len(self.pts) > 1 and hp.distance_to(self.pts[-1]["pos"]) < hp.distance_to(self.pts[0]["pos"]):
            self._reverse()
        self.engaged = False
        self.fight = None
        self.gaff = None
        self.phase = self.HAULING
        self.stage = "haul"
        self.g.crew.say("Captain: Hauling. Bring her round to the buoy.")

    def _best_detected_hotspot(self):
        """Return a live, strong hotspot seen confidently by an active main-deck lookout."""
        w = self.g.world
        lookouts = [s for s in self.g.sailors
                    if s.mode == Sailor.ABOARD and s.level == Level.MAIN
                    and s.ladder is None and s.health > 0.0]
        return select_detected_hotspot(lookouts, w.hotspots)

    def _route_to_hotspot(self, spot, announce=True):
        """Steer toward the crew's plotted school position, including DR error."""
        w = self.g.world
        target = V(estimated_hotspot_destination(spot.pos, w.position_error))
        self.auto_hotspot_target = spot
        self.auto_hotspot_destination = V(target)
        w.set_destination(target)
        if announce:
            self.g.crew.say("Captain: The lookout has found birds. Let's work that water.")

    def _route_to_best_hotspot_or_grounds(self, announce=True):
        """Prefer a crew-detected school, otherwise use the established grounds route."""
        spot = self._best_detected_hotspot()
        if spot is None:
            self.auto_hotspot_target = None
            self.auto_hotspot_destination = None
            self.g.world.set_destination(self.g.world.fishing_ground())
            if announce:
                self.g.crew.say("Captain: Heading for the fishing grounds.")
            return None
        self._route_to_hotspot(spot, announce=announce)
        return spot

    def _auto_hotspot_is_live(self):
        """Do not continue pursuing an expired or no-longer-productive school."""
        target = self.auto_hotspot_target
        if target is None:
            return False
        return (any(spot is target for spot in self.g.world.hotspots)
                and float(getattr(target, "strength_now", 0.0)) > AUTO_HUNT_MIN_STRENGTH)

    def _trip_over(self):
        """At the end of a haul on a multi-day trip: is it time to go home? (Says why, once.)"""
        g, w, say = self.g, self.g.world, self.g.crew.say
        if w.time >= self.trip_end:
            say("Captain: That's the time. Home we go.")
        elif g.fuel < w.dist() * 0.024 * 1.3 + 120:
            say("Captain: Fuel's getting low. Back to the quay.")
        elif g.bait_total() < self.max_points:
            say("Captain: The bait's about gone. Time to head in.")
        elif g.hold and g.ice < 0.15 * ICE_CAP:
            say("Captain: The ice is nearly gone. In we go, before the catch spoils.")
        else:
            return False
        return True

    def trip_hud(self):
        """'TRIP 1.4/3d' while a captain-ordered trip is running, else ''."""
        if self.trip_end is None:
            return ""
        day = clamp((self.g.world.time - self.trip_start) / DAY_LEN, 0.0, float(self.trip_days))
        return "TRIP %.1f/%dd" % (day, self.trip_days)

    def _auto(self, dt):
        g, w, say = self.g, self.g.world, self.g.crew.say
        if g.crew.alarm_target is not None:        # man overboard: nothing else matters until he's out
            return
        w.cruise = 0.5 if self.stage == "set" else 0.9
        if self.stage != "set":
            w.hold = False
        if not self.auto and self.trip_end is not None:
            self.trip_end = None                       # however fishing stopped (fuel, dock cancelled, stand down), the trip is over
        if self.stage == "off":
            if not self.auto:
                return
            if self.trip_end is not None and w.time >= self.trip_end and w.dist() >= 900:
                say("Captain: That's the time. Home we go.")          # the clock ran out between lines
                self.stage, self.dock_started = "return", False
                return
            if w.dist() < 5200:
                if not g.fuel_ok_for_trip():
                    say("Captain: Not enough fuel for the grounds and back. Standing down.")
                    self.auto = False
                    self.auto_hotspot_target = None
                    self.auto_hotspot_destination = None
                    return
                self.stage, self.retries = "travel", 0
                self._route_to_best_hotspot_or_grounds()
            else:
                # If already offshore, hunt a confident lookout contact before
                # starting another set. A nearby school does not require needless
                # manoeuvring; the set is long enough to work water close by.
                spot = self._best_detected_hotspot()
                if spot is not None:
                    target = V(estimated_hotspot_destination(spot.pos, w.position_error))
                    if w.ship_pos.distance_to(target) > max(w.arrive * 1.5, 650.0):
                        self.stage, self.retries = "travel", 0
                        self._route_to_hotspot(spot)
                    else:
                        self._begin_set()
                else:
                    self.auto_hotspot_target = None
                    self.auto_hotspot_destination = None
                    self._begin_set()
        elif self.stage == "travel":
            if not self.auto:
                self.stage = "off"
                self.auto_hotspot_target = None
                self.auto_hotspot_destination = None
                w.destination = None
            elif g.fuel < w.dist() * 0.024 * 1.3 + 40:
                say("Captain: Fuel's getting low. Back to the quay.")
                w.destination = None
                self.auto_hotspot_target = None
                self.auto_hotspot_destination = None
                self.stage, self.dock_started = "return", False
            elif self.auto_hotspot_target is not None and not self._auto_hotspot_is_live():
                # The school expired or weakened below the useful threshold while
                # under way. Retarget another currently detected school, or resume
                # the normal grounds route; never chase an obsolete coordinate.
                replacement = self._best_detected_hotspot()
                if replacement is not None:
                    self._route_to_hotspot(replacement)
                else:
                    self.auto_hotspot_target = None
                    self.auto_hotspot_destination = None
                    w.set_destination(w.fishing_ground())
                    say("Captain: That school has faded. We'll search the usual grounds.")
            elif w.destination is None:
                if self.auto_hotspot_target is not None and self._auto_hotspot_is_live():
                    target = self.auto_hotspot_destination
                    if target is not None and w.ship_pos.distance_to(target) <= max(w.arrive * 1.5, 650.0):
                        self._begin_set()
                    elif target is not None:
                        # A diversion cleared the destination before arrival; resume
                        # the stored plot rather than setting far away from the school.
                        w.set_destination(target)
                    else:
                        self._route_to_hotspot(self.auto_hotspot_target, announce=False)
                elif w.dist() >= 5000:
                    self._begin_set()
                elif self.retries < 4:                 # e.g. we stopped for a man overboard: carry on
                    self.retries += 1
                    w.set_destination(w.fishing_ground())
                else:
                    say("Captain: Can't make the grounds from here. Standing down.")
                    self.auto, self.stage = False, "off"
                    self.auto_hotspot_target = None
                    self.auto_hotspot_destination = None
        elif self.stage == "set":
            if self.phase != self.SETTING:
                w.hold = False
                w.destination = None
                self.stage = "soak" if self.pts else "off"
                self.stage_t = 0.0
                if self.pts:
                    say("Captain: Line's out. We wait.")
            else:
                w.hold = self.power("stern") <= 0        # don't move off until someone is on the roller
                if w.destination is None:
                    w.destination = w.ship_pos + V(1, 0).rotate_rad(w.heading) * 40000
        elif self.stage == "soak":
            self.stage_t += dt
            w.destination = None
            if self.stage_t >= self.soak_goal or self.skip:
                self.skip = False
                self._begin_haul()
        elif self.stage == "haul":
            if self.phase == self.IDLE:
                w.destination = None
                if self.auto and self.trip_end is not None:
                    # A multi-day trip: set again out here and keep the catch in the ice hold, until time, fuel, bait or ice say go home.
                    if self._trip_over():
                        self.stage, self.dock_started = "return", False
                    else:
                        self.stage = "off"
                elif self.auto and (g.hold or g.items or g.table.raw or self.landed):
                    self.stage, self.dock_started = "return", False       # a catch to sell: back to the quay
                else:
                    self.stage = "off"
            elif self.pts:
                head = self.pts[0]["pos"]
                haul_offset = V(-g.ship.length * 0.32, g.ship.beam * 0.5).rotate_rad(w.heading)
                # destination is the ship centre; targeting the underwater hook
                # directly leaves the hauler station permanently offset from it.
                station_gap = self._haul_world().distance_to(head)
                if station_gap > 320.0:
                    w.destination = V(head) - haul_offset
                else:
                    w.destination = None
        elif self.stage == "return":
            busy = g.items or g.table.raw or any(s.carry for s in g.sailors)
            if not self.auto:
                self.stage = "off"
            elif not self.dock_started:
                if not busy:                                              # get the catch below first
                    self.dock_started = g.begin_autodock()
                    if not self.dock_started:
                        self.stage = "off"
            elif w.dock_result == "arrived" and g.arrival_done:           # alongside, sold and paid
                self.stage, self.dock_started = "off", False
                if self.trip_end is not None:
                    self.auto, self.trip_end = False, None
                    say("Captain: That's the trip done. Sold up and paid.")
                    g.record_log_entry("Trip complete: back alongside, catch sold, crew paid.")
                else:
                    say("Captain: Sold up and paid. Back out we go.")
            elif w.dock_state is None and w.dock_result != "arrived":     # the dock was cancelled
                self.auto, self.stage, self.dock_started = False, "off", False
                say("Captain: Standing down.")

    def update(self, dt, keys):
        for k in self.claims:
            self.claims[k] = [s for s in self.claims[k] if s.mode == Sailor.ABOARD]
        self._auto(dt)
        self._update_roller_and_line(dt)
        if self.phase == self.SETTING:
            self._tick_setting()
        elif self.phase == self.SOAKING:
            self._tick_soaking(dt)
        elif self.phase == self.HAULING:
            self._tick_hauling(dt, keys)
        if self.phase != self.IDLE:
            self._physics(dt)

    def _stern_world(self):
        return self.g.world.world_of(V(-self.g.ship.length * 0.5, 0))

    def _haul_world(self):
        return self.g.world.world_of(V(self.g.ship.length * -0.32, self.g.ship.beam * 0.5))

    def _tick_setting(self):
        if self.roller_jammed or self.roller_snag_timer > 0.0:
            return
        stern = self._stern_world()
        gap = self.spacing
        if self.pts:
            gap = stern.distance_to(self.pts[-1]["pos"])
            if gap > self.spacing * 3.5:
                self._end_setting("Nobody on the roller. The line ends here.")
                return
        if self.power("stern") <= 0 or self.g.world.speed < 40:
            return
        if not self.pts or gap >= self.spacing:
            self.pts.append(self._new_point(stern, max(gap, self.spacing) * self.slack))
            if len(self.pts) >= self.max_points:
                self._end_setting("Line set, %d hooks." % len(self.pts))

    # ---- ecology: what bites depends on how deep the hook hangs, the water there, the hour and the bait
    def bite_weights(self, p, hd):
        w = self.g.world
        dm = self.hook_depth(p)
        temp = w.temp_at(dm, hd)
        night = 1.0 - w.daylight()
        bottom = w.bottom_m(hd)
        out = []
        for name, _ in self.FISH:
            dpt, dsd, tm, ts, dg, ng = ECO[name]
            lo, hi = HABITAT[name]
            s = math.exp(-0.5 * ((dm - dpt) / dsd) ** 2) * math.exp(-0.5 * ((temp - tm) / ts) ** 2)
            s *= lerp(dg, ng, night) * smoothstep(lo, hi, bottom)
            aff = BAIT_AFF[name].get(p["bait"], 0.25) if p["bait"] else 0.25
            base_weight = s * aff * (0.35 + 0.65 * p["fresh"])
            # Hotspots modulate the existing species/ecology/bait result; they
            # do not bypass it or stack multiple schools without a bound.
            out.append(base_weight * hotspot_multiplier(w.hotspots, p["pos"], name))
        return out

    def _tick_soaking(self, dt):
        self.soak_time += dt
        w = self.g.world
        for p in self.pts:
            if p["bait"]:
                p["fresh"] = max(0.0, p["fresh"] - 0.0012 * dt)       # bait washes out in the water
            if p["fish"] or p["float"] or p["bottom"]:
                continue
            hd = p["pos"].distance_to(HARBOUR) / w.scale
            mult = 1.6 if hd >= 5000 else (0.5 if hd >= 900 else 0.0)
            if mult <= 0:
                continue
            weights = self.bite_weights(p, hd)
            tot = sum(weights)
            if tot > 0 and random.random() < self.bite_rate * mult * self.g.weather.bite_mod() * tot / self.NORM * dt:
                name, value = random.choices(self.FISH, weights)[0]
                p.update(fish=True, value=value, name=name, bite=w.time, bait=None)

    def _finish_head(self):
        self.pts.pop(0)
        self.engaged = False
        self.fight = None
        self.gaff = None

    def _land(self, head, gaffed):
        g = self.g
        m = g.ship.markers
        fish = Catch.landed(head["name"], head["value"], g.world.time - head.get("bite", g.world.time),
                            head.get("fought", 0.0), head.get("rough", 0.0), gaffed, g.gaffs <= 0)
        g.items.append(FishItem(m["landing"] + V(random.uniform(-25, 25), random.uniform(-15, 15)), fish))
        g.splash_blood(m["landing"], 4)
        g.patches.append(Patch(m["haul_station"] + V(random.uniform(-70, 70), random.uniform(-70, -10))))
        self.landed += 1
        if head["value"] >= 5000:
            g.crew.say("A %s comes over the rail!" % head["name"])

    def _tick_gaff(self, dt, keys, head, hands):
        """A tired fish alongside: get the gaff or tail rope into it and heave it over the roller. It thrashes, the ship
        rolls, and a hand can be struck. Returns None, "landed" or "lost"."""
        g, w = self.g, self.g.world
        gf = self.gaff
        sp = SPECIES.get(head["name"], 0.5)
        if not hands:
            return None                                        # nobody on the rail: the fish just lies there
        skill = sum(s.skill for s in hands) / len(hands)
        sea = clamp(w.waves.strength + 1.2 * g.eff_tilt(), 0.0, 1.6)
        gf["t"] += dt
        gf["manual"] = bool(keys[pygame.K_SPACE])
        if gf["thrash"] > 0:                                   # it throws itself about and gains back what we won
            gf["thrash"] -= dt
            gf["prog"] -= 0.11 * gf["power"] * dt
        else:
            tool = 1.0 if g.gaffs > 0 else 0.55                # no gaff left: a tail rope and bare hands
            rate = (0.10 + 0.22 * skill) * tool * (0.6 + 0.5 * min(len(hands), 2)) / (0.5 + 1.2 * sp)
            if gf["manual"]:
                rate *= 1.6
            gf["prog"] += rate * dt
            gf["next"] -= dt
            if gf["next"] <= 0:
                gf["thrash"] = random.uniform(0.7, 1.4)
                gf["power"] = sp * random.uniform(0.7, 1.3) * (1.0 + 0.6 * sea)
                gf["next"] = random.uniform(1.6, 3.2)
                g.splash_blood(g.ship.markers["landing"], 2)
                p_hit = clamp(0.30 * gf["power"] * (1.15 - skill) * (1.0 if g.gaffs > 0 else 1.5), 0.0, 0.85)
                if random.random() < p_hit:
                    v = random.choice(hands)
                    v.hurt(0.05 + 0.18 * gf["power"], "struck by a thrashing %s" % head["name"])
                    g.crew.say("%s is struck by the thrashing %s!" % (v.name, head["name"]))
        gf["prog"] = clamp(gf["prog"], -0.3, 1.0)
        if gf["prog"] >= 1.0:
            return "landed"
        if gf["prog"] <= -0.25 or gf["t"] > 30.0:
            return "lost"
        return None

    def _tick_hauling(self, dt, keys):
        g = self.g
        if not self.pts:
            self.phase = self.IDLE
            self.gaff = None
            g.crew.say("Haul complete: %d fish landed. Get them stowed." % self.landed)
            g.crew.headcount()
            return
        hp = self._haul_world()
        head = self.pts[0]
        dist = hp.distance_to(head["pos"])
        if dist <= self.reach:
            self.engaged = True
        if self.engaged and dist > self.snap:
            g.crew.say("The line parted! Lost %d hooks." % len(self.pts))
            self.pts = []
            self.phase = self.IDLE
            self.gaff = None
            return
        if not g.engine_running() or not g.engine_ok:
            if not g.hauler_engine_warned:
                g.crew.say("The hauler belt is slack; the main engine is stopped.")
                g.hauler_engine_warned = True
            return
        g.hauler_engine_warned = False
        if self.roller_jammed:
            if not self._roller_warned:
                g.crew.say("The seized stern roller is holding the line. Clear the jam before hauling can continue.")
                self._roller_warned = True
            return
        if self.roller_snag_timer > 0.0:
            return
        crew_power = self.power("hauler")
        base_power = crew_power * clamp(g.engine_power, 0.0, 1.0)
        load = self._line_load(head)
        working_hands = sum(1 for s in self.claims["hauler"] if s.working and s.mode == Sailor.ABOARD)
        requested_slip = calculate_hauler_slip(load, g.engine_power, working_hands, self.hauler_drum_condition)
        self.hauler_slip = lerp(self.hauler_slip, requested_slip, 1.0 - math.exp(-3.2 * dt))
        # Repeated slipping heats/glazes the friction drum and reduces its available bite.
        if self.hauler_slip > 0.42:
            self.hauler_drum_condition = max(35.0, self.hauler_drum_condition - (0.012 + self.hauler_slip * 0.028) * dt)
            if not self._slip_warned:
                g.crew.say("The hauler friction drum is slipping under load. Reduce strain or improve engine power.")
                self._slip_warned = True
        elif self.hauler_slip < 0.18:
            self._slip_warned = False
            self.hauler_drum_condition = min(100.0, self.hauler_drum_condition + 0.004 * dt)
        power = base_power * (1.0 - 0.72 * self.hauler_slip)
        if power <= 0 or dist > self.reach:
            return
        if head["fish"] and not head.get("tired") and dist <= self.fight_range:
            if self.fight is None or self.fight.hook is not head:        # the fish is alongside and fights the winch
                self.fight = Fight(head)
                if head["value"] >= 5000:
                    g.crew.say("A %s on the line! Mind the brake." % head["name"])
            hands = [s for s in self.claims["hauler"] if s.working and s.mode == Sailor.ABOARD]
            skill = sum(s.skill for s in hands) / max(len(hands), 1)
            f = self.fight
            head["z"] = max(0.0, head["z"] - 40.0 * dt)                   # it is coming up as it tires
            res = f.update(dt, g.world, skill, keys, self.head_load())
            if res == "tired":
                head["tired"], head["fought"], head["rough"] = True, f.time, f.rough / max(f.time, 1.0)
                self.fight = None
            elif res == "escaped":
                g.crew.say("The %s threw the hook." % head["name"])
                head["fish"], self.fight = False, None
            elif res == "snood":
                g.crew.say("The snood parted. We lost the %s." % head["name"])
                head["fish"], self.fight = False, None
            elif res == "parted":
                g.crew.say("The mainline parted under the strain! Lost %d hooks." % len(self.pts))
                self.pts, self.fight = [], None
                self.phase = self.IDLE
            return
        if head["bottom"] and not head.get("snagchk"):                   # a hook lying on the seabed may foul
            head["snagchk"] = True
            if random.random() < 0.12:
                g.crew.say("A hook fouled the bottom and was lost.")
                self._finish_head()
                return
        v = hp - head["pos"]
        step = self.haul_speed * power * dt
        head["pos"] = hp if v.length() <= step else head["pos"] + v.normalize() * step
        head["z"] = max(0.0, head["z"] - 150.0 * power * dt)             # the winch lifts it as well as drawing it in
        if head["pos"].distance_to(hp) < 50 and head["z"] < 25.0:
            if head["fish"]:
                if self.gaff is None or self.gaff["hook"] is not head:   # at the rail: gaff it
                    self.gaff = {"hook": head, "prog": 0.12, "t": 0.0, "thrash": 0.0, "power": 0.0,
                                 "next": random.uniform(1.0, 2.2), "manual": False}
                    g.crew.say("The %s is alongside. Gaff!" % head["name"] if g.gaffs > 0 else
                               "The %s is alongside and there's no gaff! Tail rope!" % head["name"])
                head["pos"] = V(hp)
                hands = [s for s in self.claims["hauler"] if s.working and s.mode == Sailor.ABOARD]
                res = self._tick_gaff(dt, keys, head, hands)
                if res == "landed":
                    self._land(head, self.gaff["t"])
                    self._finish_head()
                elif res == "lost":
                    g.crew.say("The %s tore free of the gaff and slid away." % head["name"])
                    self._finish_head()
                return
            self._finish_head()

    def status_text(self):
        n = len(self.pts)
        busy = ""
        if self.fight:
            busy = " - fighting a %s" % self.fight.name
        elif self.gaff and self.pts and self.pts[0] is self.gaff["hook"]:
            busy = " - gaffing a %s" % self.gaff["hook"]["name"]
        base = {self.IDLE: "Line: out of the water",
                self.SETTING: "Line: being set, %d hooks" % n,
                self.SOAKING: "Line: soaking %ds, %d hooks" % (int(self.soak_time), n),
                self.HAULING: "Line: hauling, %d hooks left%s" % (n, busy)}[self.phase]
        roller = "JAM" if self.roller_jammed else ("BYPASS" if self.roller_bypassed else "OK")
        return "%s | Auto: %s%s | Roller %s %d%% | Line %d%% | Drum slip %d%%" % (
            base, "ON" if self.auto else "off", " (%s)" % self.stage if self.stage != "off" else "",
            roller, round(self.roller_condition), round(self.line_condition), round(100 * self.hauler_slip))

    def draw(self, g):
        if not self.pts:
            return
        s, z = g.screen, g.zoom
        D = lambda w: g.S(g.world.deck_of(w))
        path = [D(p["pos"]) for p in self.pts]
        zs = [p["z"] for p in self.pts]
        if self.phase == self.SETTING:
            path.append(D(self._stern_world()))
            zs.append(0.0)
        elif self.phase == self.HAULING:
            path.insert(0, D(self._haul_world()))
            zs.insert(0, 0.0)
        for i in range(len(path) - 1):                         # deeper line is darker and thinner
            dz = clamp((zs[i] + zs[i + 1]) * 0.5 / 600.0, 0.0, 1.0)
            pygame.draw.line(s, mix((235, 230, 210), (80, 118, 150), dz), path[i], path[i + 1], max(1, int((5 - 2.5 * dz) * z)))
        gf = self.gaff if (self.gaff is not None and self.phase == self.HAULING and self.pts and self.pts[0] is self.gaff["hook"]) else None
        for i, p in enumerate(self.pts):
            c = D(p["pos"])
            amp = 0.0
            if self.fight is not None and p is self.fight.hook:        # thrashing at the end of the line
                amp = 10 + 40 * self.fight.pull()
            elif gf is not None and p is gf["hook"]:
                amp = (6 + 34 * gf["power"]) if gf["thrash"] > 0 else 3.0
            if amp:
                k = amp * z
                c = (c[0] + math.sin(g.world.time * 23) * k, c[1] + math.cos(g.world.time * 19) * k * 0.7)
            if gf is not None and p is gf["hook"]:                   # the gaff pole from the hauler
                hpt = D(self._haul_world())
                pygame.draw.line(s, (110, 80, 50), hpt, c, max(2, int(4 * z)))
                pygame.draw.circle(s, (200, 200, 205), c, max(2, int(6 * z)), 2)
            dk = clamp(p["z"] / 600.0, 0.0, 1.0)
            if p["fish"]:
                tm = g.world.time
                if p.get("tired"):
                    ang, q = 0.12 * math.sin(tm * 1.5 + i), 0.8              # worn out: hangs on the line
                else:
                    thrash = 0.35 + (0.9 * self.fight.pull() if (self.fight is not None and p is self.fight.hook) else 0.0)
                    ang, q = math.sin(tm * (4.0 + 6.0 * thrash) + i * 1.7) * thrash, 1.0
                draw_fish(s, p.get("name") or "yellowfin", c, ang + (math.pi if i % 2 else 0.0), 92 * z, q, dk)
            elif not p["float"] and i % 3 == 0:
                pygame.draw.circle(s, mix(GOLD, (90, 100, 110), dk), c, max(2, int(6 * z)))
            if p["float"] or i == 0 or i == len(self.pts) - 1:
                pygame.draw.circle(s, (217, 83, 30), c, max(3, int(24 * z)))
                pygame.draw.circle(s, (232, 228, 216), c, max(2, int(10 * z)))
                pygame.draw.line(s, (43, 33, 24), c, (c[0], c[1] - 52 * z), 2)
                pygame.draw.polygon(s, (217, 83, 30), [(c[0], c[1] - 52 * z), (c[0] + 26 * z, c[1] - 44 * z), (c[0], c[1] - 36 * z)])

    def end_buoys(self):
        return [self.pts[0]["pos"], self.pts[-1]["pos"]] if self.pts else []


# -------------------------------------------------------------------- crew

class Crew:
    def __init__(self, g):
        self.g = g
        self.status = {}            # name -> aboard / overboard / dead (the truth; the player only learns it at a headcount)
        self.known_lost = set()
        self.log = []
        self.alarm_target = None
        # A falling sailor is a hidden event until an onboard observer sees him.
        self.unseen_overboard = set()
        self.sighting_timers = {}
        self.catch_count = 0
        self.catch_value = 0

    def _bubble_speaker(self, text):
        """Choose the sailor delivering a log line and remove an explicit speaker label."""
        sailors = getattr(self.g, "sailors", [])
        if not sailors:
            return None, text

        # Explicit labels are the most reliable attribution: "Takeda: ..." or "Captain: ...".
        match = re.match(r"^([^:]{1,40}):\s*(.*)$", text.strip())
        if match:
            label, body = match.group(1).strip().lower(), match.group(2).strip()
            aliases = {"captain": "captain ishida", "ishida": "captain ishida"}
            label = aliases.get(label, label)
            for sailor in sailors:
                if sailor.mode != Sailor.SHORE and label in (sailor.name.lower(), sailor.name.lower().removeprefix("captain ")):
                    return sailor, body

        aboard = [s for s in sailors if s.mode in (Sailor.ABOARD, Sailor.SWIMMING, Sailor.CLIMBING)]
        if not aboard:
            return None, text

        lower = text.lower()
        # Route work-related calls to a deckhand actually working the line when possible.
        if any(word in lower for word in ("line", "haul", "hook", "gaff", "fish on", "alongside the hauler")):
            workers = [s for s in aboard if s.mode == Sailor.ABOARD and
                       (s.task in ("haul", "set") or s.duty in ("haul", "set"))]
            if workers:
                return workers[0], text
            veteran = next((s for s in aboard if s.role == Sailor.VETERAN), None)
            if veteran:
                return veteran, text

        # Navigation and machinery calls naturally come from the captain or engineer.
        if any(word in lower for word in ("engine", "fuel", "helm", "captain", "harbour", "harbor", "alongside")):
            engineer = next((s for s in aboard if s.mode == Sailor.ABOARD and s.at_engine), None)
            if engineer and any(word in lower for word in ("engine", "fuel")):
                return engineer, text
            captain = next((s for s in aboard if s.role == Sailor.CAPTAIN), None)
            if captain:
                return captain, text

        # Prefer the selected sailor for general notices; fall back to the captain or an able hand.
        selected = next((s for s in aboard if s.selected and s.mode == Sailor.ABOARD), None)
        captain = next((s for s in aboard if s.role == Sailor.CAPTAIN and s.mode == Sailor.ABOARD), None)
        return selected or captain or next((s for s in aboard if s.mode == Sailor.ABOARD), aboard[0]), text

    @staticmethod
    def _emphasize_speech(text):
        """Make questions look questioning and shouted/exclamatory lines look loud."""
        text = text.strip()
        text = re.sub(r"\?+", "???", text)
        text = re.sub(r"!+", "!!!", text)
        return text

    @staticmethod
    def _should_show_speech_bubble(text):
        """Show spoken lines in-world; keep action/context notices in the notebook.

        Every message still passes through the dated crew log. This filter only
        controls the transient bubble, preventing status panels, narrated motion,
        and system feedback from being attributed to whichever sailor is selected.
        Explicit crew dialogue, questions, commands and urgent warnings remain
        eligible for a bubble.
        """
        raw = str(text).strip()
        if not raw:
            return False
        lower = raw.lower()

        # These prefixes are system/context records, not lines a nearby sailor is
        # meant to be seen saying. Real spoken crew reports use the sailor's name.
        log_only_prefixes = (
            "line depth setting:", "nothing was set.", "haul complete:",
            "catch stowed:", "headcount:", "headcount complete:",
            "engine strain is building:", "engine checks are overdue.",
            "unattended engine fault:", "engine room:", "engine trip:",
            "engineer ", "auction:", "auction house:", "auction session complete:",
            "navigation:", "navigator:", "market watch:", "helm:",
            "wheelhouse access is controlled:", "wheelhouse landing is occupied.",
            "wheelhouse stations are assigned:", "only captain ishida or",
            "only the captain or", "helm watch stays at the wheel.",
            "radio watch stays on", "radio watch cannot leave", "relief helm stays manned",
            "the helmsman stays on watch", "captain's duty is the helm.",
            "radio call still in progress", "no engineer below.", "nobody at the helm.",
            "the swimmer is within davit-lifeline range.",
        )
        if lower.startswith(log_only_prefixes):
            return False

        # Explicit captain status updates are useful in the log but become noisy
        # when repeated as bubbles during autonomous travel and route transitions.
        if re.match(r"^(captain|ishida):", lower):
            body = lower.split(":", 1)[1].strip()
            status_phrases = (
                "heading for the fishing grounds", "line's out. we wait",
                "auto-fishing takes priority", "auto-fishing has priority",
                "manual waypoint route cancelled", "manual chart course cleared",
                "chart course committed", "chart course cleared",
                "sold up and paid", "final approach stalled", "berth approach is blocked",
                "can't make the grounds from here", "route not committed",
            )
            if any(phrase in body for phrase in status_phrases):
                return False

        # Events and system feedback that describe what just happened rather than
        # something a sailor is actually saying belong in the crew activity log.
        event_patterns = (
            r"^the sea took a gaff over the rail",
            r"^a sea comes green over the ",
            r"^a .+ comes over the rail!",
            r"^.+ loses footing on the wet deck and slips over the side!",
            r"^.+ is struck by the thrashing ",
            r"^.+ bleeds out the ",
            r"^.+ has gone under\.",
            r"^.+ is dead\s*-",
            r"^.+ is missing\.",
            r"^.+ reports for headcount\.",
            r"^.+ spots the ship through the spray and starts swimming",
            r"^.+ is (?:run down by the ship|struck by the hull)!?",
            r"^the live .+ thrashes on deck!",
            r"^a hook fouled the bottom and was lost\.",
            r"^the .+ threw the hook\.",
            r"^the .+ tore free of the gaff and slid away\.",
            r"^the mainline parted under the strain! lost \d+ hooks\.",
            r"^thunder rolls across the water\.",
            r"^the coast guard (?:cut the line away|tows us in)",
            r"^the ship is stopped\. the deckhands are lowering the rescue boat",
            r"^the rescue launch is returning to the davit",
            r"^the rescue boat is away from the davit\.",
            r"^the launch is alongside .+\. the crew are pulling",
            r"^.+ is aboard the rescue boat\. the launch is turning back",
            r"^the launch is secured\. the ship is turning back",
            r"^the rescue boat is alongside; the survivor is climbing aboard\.",
            r"^the launch returned without the swimmer\.",
            r"^a hand below bails water from the engine-room bilge",
            r"^rough handling bruises the ",
            r"^the tank is dry! the engine has stopped\.",
        )
        if any(re.search(pattern, lower) for pattern in event_patterns):
            return False

        # NPC/system-labelled logistics are durable context. Radio has its own
        # screen-space channel and is handled before this filter in say().
        # The dockmaster can have actual harbour dialogue. Only the listed
        # operational/status lines are log-only; conversational dockside turns
        # remain visible as speech.
        labelled = re.match(r"^([^:]{1,40}):\s*(.*)$", raw)
        if labelled:
            label = labelled.group(1).strip().lower()
            body = labelled.group(2).strip().lower()
            if label == "dockmaster" and any(phrase in body for phrase in (
                "return automatically on departure", "shore leave is available only while alongside",
                "bring crew aboard while alongside", "has gone into town to recover",
                "has gone into town", "is back aboard", "shore party recovered",
                "returning hands are aboard", "recalled from shore leave",
            )):
                return False
            if label in {"auctioneer", "navigator", "navigation"}:
                return False

        # Keep real attributed lines (named crew, Captain, Mate, weather calls) and
        # conversational text. For unlabelled third-person narration, log only.
        match = re.match(r"^([^:]{1,40}):\s*(.*)$", raw)
        if match:
            label = match.group(1).strip().lower()
            body = match.group(2).strip().lower()
            if label in {"captain", "ishida", "mate", "weather observer"}:
                return True
            # Explicitly named crew/broadcast speakers may use names not known to
            # this static helper, so preserve attributed statements by default.
            if body and label not in {"ship", "system", "status", "crew log", "event"}:
                return True

        conversational = (
            r"\b(i|i'm|i've|we|we're|we've|our|you|you're|your|let's|please)\b",
            r"\b(bring|mind|keep|hold|take|watch|send|look|turn|throw|stand by|report in|hands to|gaff|tail rope|all stop|man overboard)\b",
        )
        if any(re.search(pattern, lower) for pattern in conversational) or "?" in raw:
            return True
        return False

    def say(self, text):
        # Retain the short diagnostic tail, and keep a separate dated career log.
        # Radio traffic is routed into the radio transcript rather than duplicated
        # on the crew activity pages.
        recorder = getattr(self.g, "record_log_entry", None)
        if recorder is not None:
            recorder(text)
        self.log.append(text)
        self.log = self.log[-7:]
        if text.strip().lower().startswith("radio:"):
            show_radio = getattr(self.g, "show_radio_dialogue", None)
            if show_radio is not None:
                show_radio(text)
                return
        if not self._should_show_speech_bubble(text):
            return
        speaker, bubble = self._bubble_speaker(text)
        if speaker is not None and bubble:
            speaker.speech_bubble = self._emphasize_speech(bubble)
            # Longer calls stay visible a little longer, without hanging over the scene indefinitely.
            speaker.speech_t = clamp(2.6 + len(speaker.speech_bubble) * 0.035, 2.8, 5.2)

    def add_catch(self, value):
        self.catch_count += 1
        self.catch_value += value
        for s in self.g.sailors:
            if s.mode == Sailor.ABOARD:
                s.add_morale(0.03)

    def on_fell(self, s):
        """Record the fall without broadcasting it; a crewmate must visually spot him."""
        self.status[s.name] = "overboard"
        self.unseen_overboard.add(s)
        self.sighting_timers[s] = 0.0

    def update_sightings(self, dt):
        """Check each observer's weather-limited forward view and raise a call when seen."""
        if self.alarm_target is not None:
            return
        for swimmer in list(self.unseen_overboard):
            if swimmer.mode != Sailor.SWIMMING:
                self.unseen_overboard.discard(swimmer)
                self.sighting_timers.pop(swimmer, None)
                continue
            target_pos = self.g.world.deck_of(swimmer.wpos)
            observers = [o for o in self.g.sailors
                         if o is not swimmer and o.mode == Sailor.ABOARD
                         and o.can_see_position(target_pos)]
            if not observers:
                self.sighting_timers[swimmer] = 0.0
                continue
            # Require a brief, continuous sighting instead of a same-frame global reaction.
            self.sighting_timers[swimmer] = self.sighting_timers.get(swimmer, 0.0) + max(0.0, dt)
            if self.sighting_timers[swimmer] >= 0.35:
                observers.sort(key=lambda o: o.pos.distance_to(target_pos))
                self._raise_mob_alarm(swimmer, observers)
                return

    def _raise_mob_alarm(self, swimmer, noticers):
        """Only called after at least one sailor has held the swimmer in their view."""
        if self.alarm_target is not None or swimmer.mode != Sailor.SWIMMING or not noticers:
            return
        self.unseen_overboard.discard(swimmer)
        self.sighting_timers.pop(swimmer, None)
        self.say("%s: Man overboard! It's %s!" % (noticers[0].name, swimmer.name))
        self.alarm_target = swimmer
        self.g.begin_mob_rescue(swimmer)
        # Calm-sea long-distance cases use the boat crew, not a deckhand throwing a line
        # from too far away. Close and heavy-weather cases use the lifeline/ship-turn procedure.
        rescuers = []
        if self.g.mob_rescue_mode not in ("boat_assembly", "boat_launching", "boat_out", "boat_pickup", "boat_return"):
            rescuers = [o for o in noticers if o.role != Sailor.CAPTAIN
                        and o is not self.g.helm_operator and o is not self.g.radio_operator][:2]
            if not rescuers:
                hands = [o for o in self.g.sailors
                         if o is not swimmer and o.mode == Sailor.ABOARD
                         and o.role != Sailor.CAPTAIN and o is not self.g.helm_operator
                         and o is not self.g.radio_operator]
                rescuers = sorted(hands, key=lambda o: o.pos.distance_to(swimmer.pos))[:1]
            for o in rescuers:
                o.start_rescue(swimmer)
        # Others react to the shouted alarm, not to hidden game state.
        for o in self.g.sailors:
            if o is not swimmer and o.mode == Sailor.ABOARD and o not in rescuers and o not in self.g.rescue_boat_hands and o.role != Sailor.CAPTAIN:
                delay = 0.4 + o.pos.distance_to(swimmer.pos) / 700 + random.uniform(0.0, 0.8)
                if o.level == Level.BELOW:
                    delay += 1.2 + (1.8 if o.sleeping_in_bunk else 0.0)
                o.alert(swimmer, delay)

    def on_back(self, s):
        self.unseen_overboard.discard(s)
        self.sighting_timers.pop(s, None)
        self.status[s.name] = "aboard"
        if self.alarm_target is s:
            self.alarm_target = None
            self.g.finish_mob_rescue(s, survivor=True)
            self.say("%s is back aboard, half drowned." % s.name)

    def on_drowned(self, s):
        was_unseen = s in self.unseen_overboard and self.alarm_target is not s
        self.unseen_overboard.discard(s)
        self.sighting_timers.pop(s, None)
        self.status[s.name] = "dead"
        if self.alarm_target is s:
            self.alarm_target = None
            self.g.finish_mob_rescue(s, survivor=False)
            self.say("%s has gone under." % s.name)
            self._mark(s.name, False)
        elif not was_unseen:
            self.say("%s has gone under." % s.name)
            self._mark(s.name, False)

    def on_killed(self, s, cause):
        was_unseen = s in self.unseen_overboard and self.alarm_target is not s
        self.unseen_overboard.discard(s)
        self.sighting_timers.pop(s, None)
        self.status[s.name] = "dead"
        if not was_unseen:
            self.say("%s is dead - %s." % (s.name, cause))
            self._mark(s.name, False)
        if self.alarm_target is s:
            self.alarm_target = None
            self.g.finish_mob_rescue(s, survivor=False)

    def headcount(self):
        aboard = sum(1 for v in self.status.values() if v == "aboard")
        ashore = sum(1 for v in self.status.values() if v == "shore")
        self.say("Headcount: %d aboard, %d on shore, %d lost or unaccounted for." %
                 (aboard, ashore, max(0, len(self.status) - aboard - ashore)))
        for n, v in self.status.items():
            if v not in ("aboard", "shore"):
                self._mark(n, True)

    def _mark(self, name, announce):
        if name in self.known_lost:
            return
        self.known_lost.add(name)
        if announce:
            self.say("%s is missing." % name)
        for s in self.g.sailors:
            if s.mode == Sailor.ABOARD:
                s.add_morale(-0.2)


# ------------------------------------------------------------------ sailor

class Sailor:
    DECKHAND, VETERAN, CAPTAIN = range(3)
    ABOARD, SWIMMING, CLIMBING, DEAD, SHORE, RESCUE_BOAT = range(6)
    ROLE_NAMES = ["deckhand", "veteran", "captain"]
    VIEW_HALF_ANGLE = math.radians(55.0)  # 110-degree forward field of view
    VISIBILITY_UNITS_PER_KM = 100.0

    def vision_range(self):
        """Deck-space sight distance derived from the same visibility value shown in weather HUD."""
        km = self.g.weather.visibility_km()
        level_scale = 0.78 if self.level == Level.WHEELHOUSE else 1.0
        return min(1000.0, max(45.0, km * self.VISIBILITY_UNITS_PER_KM)) * level_scale

    def can_see_position(self, target_pos):
        """Whether target_pos falls inside this sailor's forward cone and visible range."""
        if self.mode != self.ABOARD or self.level == Level.BELOW or self.ladder is not None:
            return False
        delta = V(target_pos) - self.pos
        distance = delta.length()
        if distance < 1e-6 or distance > self.vision_range():
            return False
        bearing = math.atan2(delta.y, delta.x)
        difference = abs((bearing - self.facing + math.pi) % TAU - math.pi)
        # A nearby person at the rail still has to be inside the forward view cone.
        return difference <= self.VIEW_HALF_ANGLE

    def __init__(self, g, name, role, pos):
        self.g, self.name, self.role = g, name, role
        self.pos, self.vel = V(pos), V(0, 0)
        self.scale = 2.2
        self.radius = 7.5 * self.scale            # for walls
        self.body_r = 12 * self.scale             # personal space, for other sailors
        self.mode = self.ABOARD
        self.keep_ashore = False       # dock-sheet preference: do not automatically re-embark
        self.shore_since = 0.0
        self.wheelhouse_exit_elapsed = 0.0
        self.wheelhouse_exit_attempts = 0
        self.selected = False
        self.target, self.has_target = V(0, 0), False
        self.order_hold, self.ordering = 0.0, False
        self.fatigue, self.morale, self.breath = 0.1, 0.7, 1.0
        self.task, self.duty, self.working = "idle", "", False
        self.grip_mult = 1.0
        self.facing = random.uniform(0, TAU)
        self.phase, self.flail, self.time = 0.0, 0.0, 0.0
        self.think_t = random.uniform(0, 0.35)
        self.spot_off = V(random.uniform(-35, 35), random.uniform(-35, 35))
        self.wander_t, self.loiter = 0.0, None
        self.social_cd, self.chat_partner, self.chat_t = 0.0, None, 0.0
        self.clean_patch = None
        self.rescue_target, self.rescue_t = None, 0.0
        self.carry, self.item = [], None          # fish in hand / fish being fetched
        self.dress_fish = None                    # the fish he is cutting
        self.hatch_idx = None                     # which hold hatch he is carrying a dressed fish to
        self.deck_action = None                   # timed hatch, hose, or ice-trimming action
        self.auto_close_hatch = None              # AI hatch opened for a level transition; dog it after crossing
        self.hatch_order = None                   # queued context-menu order: {key, open, level, pos}
        self.gear_order = None                    # queued stern-gear clear, completed at the roller
        self.hatch_wait_warning_t = 0.0
        self.drip_t = 0.0                         # a bloody fish drips as it is carried
        self.stuck_t = 0.0
        self.no_progress_t = 0.0
        self.progress_distance = None
        self.stage, self.work_t, self.at_post, self.at_engine = "fetch", 0.0, False, False
        self.alert_target, self.alert_delay = None, 0.0
        self.wash_push = V(0, 0)
        self.path, self.path_goal, self.last_plan = [], None, -99.0
        self.path_target = None               # safe reachable endpoint for an awkward task coordinate
        self.wpos = V(0, 0)
        self.swim_goal = None
        self.speech_bubble, self.speech_t = "", 0.0
        self.gut_spot, self.gut_confidence, self.gut_last_comment = None, 0.0, -99.0
        self.level = Level.MAIN                   # which deck level he is on
        self.ladder = None                        # set while he is on a ladder: {link, to, t, from, dest, flipped}
        self.level_goal = None                    # reserved standing spot when heading for the wheelhouse
        self.at_radio = False
        self.rest_bunk_index = None
        self.sleeping_in_bunk = False
        self.order_goal, self.order_level, self.order_planned = V(0, 0), Level.MAIN, False
        self.muster_target = None
        self.bucket_slot = None
        self.climb_t, self.climb_to, self.dead_t = 0.0, V(0, 0), 0.0
        self.health = 1.0                         # hurt by the hull, healed in the harbour
        self.lifeline, self.line_state = None, ""
        self.wvel, self.hit_cd, self.hit_say = V(0, 0), 0.0, -99.0     # shoved about by the ship
        self.wage = {self.CAPTAIN: 6000, self.VETERAN: 4500, self.DECKHAND: 2500}[role]   # yen per trip
        self.owed = 0.0
        if role == self.CAPTAIN:
            self.skill, self.caution = 0.7, 0.8
            self.jacket, self.hair = hexc("#1f2f45"), hexc("#2a2a2a")
        elif role == self.VETERAN:
            self.skill, self.caution = 0.8, random.uniform(0.6, 0.9)
            self.jacket = random.choice([hexc("#4c5a3c"), hexc("#6b4f2f"), hexc("#2f4a6b")])
            self.hair = hexc("#9a9a9a")
        else:
            self.skill, self.caution = random.uniform(0.1, 0.3), random.uniform(0.2, 0.6)
            self.jacket = random.choice([hexc("#2f4a6b"), hexc("#3d5c4a"), hexc("#7a3f35"), hexc("#c9a227")])
            self.hair = random.choice([hexc("#1b1b1b"), hexc("#2a1f18")])
        self.skin = random.choice([hexc("#d9a577"), hexc("#c98f62"), hexc("#e2b58a"), hexc("#b9794f")])

    def alert(self, sw, delay):
        if self.mode == self.ABOARD:
            self.alert_target, self.alert_delay = sw, delay

    def add_morale(self, a):
        self.morale = clamp(self.morale + a, 0.0, 1.0)

    # --- player commands
    def order_to(self, deck_pos, level=Level.MAIN):
        if self.mode == self.ABOARD:
            if self.ladder is not None:
                return                                    # he is on a ladder: ask again when he is off it
            deck_pos = V(deck_pos)
            g = self.g
            if level == Level.WHEELHOUSE:
                hit = g.ship.station_at(deck_pos, radius=34.0)
                if hit is not None and hit[0] == "radio":
                    g.assign_radio_operator(self, announce=True)
                    return
                if hit is not None and hit[0] == "helm":
                    if not g._set_helm_operator(self):
                        g.crew.say("Only Captain Ishida or the veteran relief can take the helm.")
                        return
                    g.captain_resting = self.role != self.CAPTAIN
                    g.captain_rest_elapsed = 0.0
                    g._update_station_roles(0.0)
                    return
                if not g.wheelhouse_goal_allowed(self, deck_pos):
                    g.crew.say("Wheelhouse stations are assigned: captain/relief at the helm, one hand at the radio.")
                    return
            if self.level == Level.WHEELHOUSE and level != Level.WHEELHOUSE and (self is g.helm_operator or self is g.radio_operator):
                g.request_wheelhouse_exit(self, deck_pos)
                return
            if self is g.helm_operator:
                helm = g.ship.wheelhouse_stations["helm"]
                if level != Level.WHEELHOUSE or deck_pos.distance_to(helm) > 42.0:
                    g.crew.say("Helm watch stays at the wheel. Order the captain to rest to hand over to the veteran.")
                    return
            if self is g.radio_operator:
                radio = g.ship.wheelhouse_stations["radio"]
                if level != Level.WHEELHOUSE or deck_pos.distance_to(radio) > 42.0:
                    g.crew.say("Radio watch stays on 2182 kHz until another hand is assigned.")
                    return
            self._release()
            self.level_goal = V(deck_pos) if level == Level.WHEELHOUSE else None
            self.task, self.working = "order", False
            self.order_goal, self.order_level, self.order_planned = V(deck_pos), level, False
            self.target, self.has_target = V(deck_pos), False
            self.path, self.path_goal = [], None
            self.no_progress_t, self.progress_distance = 0.0, None
            self.ordering, self.order_hold = True, 999.0
        elif self.mode == self.SWIMMING:
            self.swim_goal = self.g.world.world_of(V(deck_pos))

    CLIMB_TIME = 1.3

    def start_climb(self, link):
        to = link.other(self.level)
        if to == Level.WHEELHOUSE and not self.g.can_enter_wheelhouse(self):
            return
        if self.level == Level.WHEELHOUSE and to != Level.WHEELHOUSE and self in (self.g.helm_operator, self.g.radio_operator):
            # Station keepers never leave by an accidental ladder command.
            return
        self.ladder = {"link": link, "to": to, "t": 0.0, "from": V(self.pos), "dest": V(link.pos(to)), "flipped": False}
        self.working = self.at_post = self.at_engine = False       # no work while on a ladder
        self.has_target, self.path, self.vel = False, [], V(0, 0)

    def _ladder_step(self, dt):
        L = self.ladder
        L["t"] += dt
        k = clamp(L["t"] / (self.CLIMB_TIME * lerp(1.0, 0.75, self.skill)), 0.0, 1.0)
        self.pos = L["from"].lerp(L["dest"], k * k * (3.0 - 2.0 * k))
        # Keep the sailor on the departure level throughout the ladder animation;
        # switch deck/camera ownership only when both feet reach the destination.
        # Flipping at 50% made selected sailors appear to teleport between deck views.
        if k >= 1.0:
            self.pos, self.level, self.vel = V(L["dest"]), L["to"], V(0, 0)
            self.ladder = None
            self.wheelhouse_exit_elapsed = self.wheelhouse_exit_attempts = 0.0
            self.think_t = 0.0
            self.g._update_station_roles(0.0)
            if self.auto_close_hatch is not None:
                self.g._close_hatch_after_crossing(self, self.auto_close_hatch)
                self.auto_close_hatch = None

    def set_duty(self, duty):
        g = self.g
        if self.mode != self.ABOARD:
            return
        if duty == "post":
            if self.role == self.CAPTAIN:
                g.captain_resting, g.captain_rest_elapsed = False, 0.0
                g._update_station_roles(0.0)
                self.duty, self.task = "", "idle"
                self.think_t = 0.0
                return
            if self.role != self.VETERAN or (not g.captain_resting and g.helm_operator is not self):
                g.crew.say("Only the captain or the assigned veteran relief can take the helm.")
                return
            if self is not g.helm_operator:
                if not g._set_helm_operator(self):
                    return
            self.duty, self.task, self.think_t = "post", "idle", 0.0
            return
        if duty == "radio":
            g.assign_radio_operator(self)
            return
        if self is g.radio_operator and duty:
            g.crew.say("Radio watch cannot leave the wireless until another hand takes over.")
            return
        if self is g.helm_operator and self.role != self.CAPTAIN and duty == "rest":
            g.crew.say("Relief helm stays manned until the captain is rested and back on watch.")
            return
        if self is g.helm_operator and duty not in ("", "rest"):
            g.crew.say("The helmsman stays on watch; only the captain can request a rest handover.")
            return
        if self.role == self.CAPTAIN and duty not in ("", "rest"):
            g.crew.say("Captain's duty is the helm. Assign deck work to another sailor.")
            return
        if duty == "rest" and self.role == self.CAPTAIN:
            g.captain_resting, g.captain_rest_elapsed = True, 0.0
            self.duty = "rest"
            g._update_station_roles(0.0)
        elif duty == "" and self is g.radio_operator:
            if g.pending_radio_calls or g.radio_calls:
                g.crew.say("Radio call still in progress; keep the set manned.")
                return
            g.radio_operator, g.radio_duty_active = None, False
            self.duty = ""
        else:
            self.duty = duty
        self.think_t, self.order_hold, self.ordering = 0.0, 0.0, False

    # --- update
    def update(self, dt):
        self.time += dt
        self.speech_t = max(0.0, self.speech_t - dt)
        if self.speech_t <= 0.0:
            self.speech_bubble = ""
        if self.mode == self.ABOARD:
            self._aboard(dt)
        elif self.mode == self.SWIMMING:
            self._swim(dt)
        elif self.mode == self.CLIMBING:
            self._climb(dt)
        elif self.mode == self.SHORE:
            # Shore leave is an off-ship simulation state: recover without walking around the vessel.
            self.shore_since += dt
            self.health = min(1.0, self.health + 0.075 * dt)
            self.fatigue = max(0.0, self.fatigue - 0.055 * dt)
            self.morale = min(1.0, self.morale + 0.018 * dt)
            self.vel = V(0, 0)
        elif self.mode == self.RESCUE_BOAT:
            # Boat crew and the rescued sailor are moved by Game._update_rescue_operation().
            self.vel = V(0, 0)
        else:
            self._dead(dt)

    def _aboard(self, dt):
        g = self.g
        self.order_hold = max(self.order_hold - dt, 0.0)
        if self.ordering and not self.has_target and self.order_planned and self.ladder is None:
            self.ordering, self.order_hold = False, 3.0
        # Quiet cabin rest gradually treats injuries, but prolonged fishing trips cap
        # passive recovery at 60%; full recovery still requires harbour medical rest.
        cabin = g.ship.crew_quarters  # (x, y, width, height) in below-deck coordinates
        cx, cy, cw, ch = cabin
        in_cabin = (self.level == Level.BELOW
                    and cx <= self.pos.x <= cx + cw
                    and cy <= self.pos.y <= cy + ch
                    and not self.working and not self.has_target and self.fatigue < 0.82)
        if in_cabin and self.health < 0.60:
            self.health = min(0.60, self.health + 0.0011 * dt)
        # needs
        effort = 0.0003 + (0.003 if self.working else (0.0012 if self.has_target else 0.0))
        self.fatigue = clamp(self.fatigue + effort * dt, 0, 1)
        self.morale = clamp(self.morale - (0.0012 + 0.004 * g.world.waves.strength) * dt, 0, 1)
        self.social_cd = max(self.social_cd - dt, 0.0)
        if self.ladder is not None:                          # on a ladder: nothing else happens until he is off it
            self._ladder_step(dt)
            return
        self.hatch_wait_warning_t = max(0.0, self.hatch_wait_warning_t - dt)
        if self.deck_action is not None:
            # A hatch/sluice/ice operation occupies the sailor; tasks and station ownership pause.
            self.vel = V(0, 0)
            self.working = True
            self.at_post = self.at_engine = self.at_radio = False
            self.deck_action["elapsed"] += dt
            if self.deck_action["elapsed"] >= self.deck_action["duration"]:
                self.g._finish_deck_action(self)
            return
        if self.level == Level.MAIN:                         # slime, seas and wet steel are all deck matters
            slime = min((p.grip for p in g.patches if self.pos.distance_to(p.pos) < p.radius), default=1.0)
            self.wash_push = g.ship.wash_push(self.pos)
            wet = max(0.3, 1.0 - 0.5 * g.ship.wet - 0.3 * g.ship.flood)
            self.grip_mult = min(slime, wet, g.ship.steel_grip(self.pos), 0.35 if self.wash_push.length() > 0.05 else 1.0)
        else:
            self.wash_push, self.grip_mult = V(0, 0), 1.0
        # A context-menu snag order is a real crew task: the selected hand walks aft
        # and works at the roller, rather than the menu magically clearing the gear.
        if (self.gear_order == "clear_snag" and self.mode == self.ABOARD
                and self.level == Level.MAIN and self.ladder is None and self.deck_action is None):
            stern_work = V(-self.g.ship.length * 0.45, 0.0)
            if self.pos.distance_to(stern_work) <= 245.0:
                if self.g.line.roller_snag_timer > 0.0 or self.g.line.roller_jammed:
                    self.g.line.operate_roller(self)
                self.gear_order = None
        # Context-menu hatch orders are queued while the sailor walks to the cover.
        # Execute only on the correct deck and within arm's reach; never toggle a
        # remote hatch through walls or while another sailor is on its ladder.
        if self.hatch_order is not None and self.ladder is None and self.deck_action is None:
            order = self.hatch_order
            if self.level == order.get("level") and self.pos.distance_to(order.get("pos", self.pos)) <= 58.0:
                key, should_open = order["key"], bool(order["open"])
                if self.g.ship.hatch_is_open(key) == should_open:
                    self.hatch_order = None
                elif self.g._start_hatch_action(self, key, automatic=False):
                    self.hatch_order = None
                    return
        self.alert_delay = max(self.alert_delay - dt, 0.0)
        if self.alert_target is not None and self.alert_delay <= 0 and self.task != "rush":
            self.order_hold, self.ordering, self.think_t = 0.0, False, 0.0      # drop everything
        self.think_t -= dt
        if self.think_t <= 0 and self.order_hold <= 0:
            self.think_t = 0.35
            self._think()
        self._do_task(dt)
        self._move(dt)
        if self.level == Level.WHEELHOUSE and self.ladder is None and self.task == "order" and self.order_level != Level.WHEELHOUSE:
            # Track elapsed exit time, not instantaneous velocity: shoving/avoidance
            # can keep velocity nonzero even while the sailor makes no useful progress.
            self.wheelhouse_exit_elapsed += dt
            if self.wheelhouse_exit_elapsed >= 2.4:
                self.wheelhouse_exit_elapsed = 0.0
                g._recover_wheelhouse_exit(self)
        else:
            self.wheelhouse_exit_elapsed = 0.0
            if self.level != Level.WHEELHOUSE:
                self.wheelhouse_exit_attempts = 0
        if self.mode == self.ABOARD and self.level == Level.MAIN and not g.ship.on_deck(self.pos):
            self._fall()

    def _plan_path(self, start, goal, level=None, ignore_crew=False):
        """Plan around nearby crew, with a crowd-escape retry for stalled sailors."""
        level = self.level if level is None else level
        goal = V(goal)
        obstacles = []
        for other in (() if ignore_crew else self.g.sailors):
            if (other is self or other.mode != self.ABOARD or other.ladder is not None
                    or other.level != level or (other.sleeping_in_bunk and other.task == "rest")):
                continue
            # Don't make the destination unreachable when a crewmate is already near it.
            if other.pos.distance_to(goal) <= 62.0:
                continue
            obstacles.append((V(other.pos), max(72.0, other.body_r + 58.0)))
        return self.g.ship.find_path(start, goal, level, obstacles)

    def _move(self, dt):
        g = self.g
        if self.sleeping_in_bunk and self.task == "rest" and self.mode == self.ABOARD and self.level == Level.BELOW:
            self.vel = V(0, 0)
            self.has_target, self.path = False, []
            return
        slope = g.ship.slope
        if self.has_target:                      # judge progress toward the goal, not speed alone
            remaining = self.pos.distance_to(self.target)
            if self.progress_distance is None or remaining < self.progress_distance - 10.0:
                self.progress_distance = remaining
                self.no_progress_t = 0.0
            else:
                self.no_progress_t += dt
            self.stuck_t = self.stuck_t + dt if self.vel.length() < 25 else 0.0
            # A sailor can be moving quickly while pressed against a wall or pushing
            # into a crowd. Replan when the goal distance stops improving, even if
            # collision/avoidance leaves some sideways velocity.
            if ((self.stuck_t > 0.8 or self.no_progress_t > 1.0)
                    and self.time - self.last_plan >= 0.35):
                # Crowded narrow passages can make the same otherwise-valid route
                # fail repeatedly. On a stall, retry against the ship's static map
                # without dynamic crew blockers so the sailor can escape the crowd.
                self.path = self._plan_path(self.pos, self.target, self.level, ignore_crew=True)
                self.path_goal, self.last_plan = V(self.target), self.time
                self.stuck_t = self.no_progress_t = 0.0
                self.progress_distance = remaining
        else:
            self.stuck_t = self.no_progress_t = 0.0
            self.progress_distance = None
        wish = V(0, 0)
        if self.has_target:
            while len(self.path) > 1 and self.pos.distance_to(self.path[0]) < 16:
                self.path.pop(0)
            # An empty route means A* could not currently reach the target. Do not
            # steer in a straight line through the engine casing/bunks; slow down and
            # let _walk's timed re-plan try again as crew/hatch state changes.
            if not self.path:
                self.vel *= math.exp(-8.0 * dt)
                self.stuck_t += dt
                if self.stuck_t > 0.8:
                    self.stuck_t = 0.0
                    self.path = self._plan_path(self.pos, self.target, self.level)
                    self.path_goal = V(self.target)
                return
            goal = self.path[0]
            to = goal - self.pos
            if to.length() > 8:
                wish = to.normalize()
            else:
                self.path.pop(0)
                if not self.path and self.pos.distance_to(self.target) <= 12:
                    self.has_target = False
        # Reciprocal collision avoidance: react both to close bodies and to a likely
        # future crossing, before the personal-space solver has to separate the pair.
        avoid = V(0, 0)
        side_bias = V(0, 0)
        for o in self.g.sailors:
            if (o is self or o.mode != self.ABOARD or o.level != self.level
                    or o.ladder is not None or (o.sleeping_in_bunk and o.task == "rest")):
                continue
            d = self.pos - o.pos
            dist = d.length()
            if 1e-6 < dist < 150.0:
                urgency = clamp((150.0 - dist) / 150.0, 0.0, 1.0)
                away = d / dist
                avoid += away * urgency ** 1.35
                # Predict whether our relative motion will intersect within 0.7 seconds.
                relative_v = self.vel - o.vel
                vv = relative_v.length_squared()
                if vv > 1e-6:
                    t_closest = clamp(-d.dot(relative_v) / vv, 0.0, 0.7)
                    future = d + relative_v * t_closest
                    future_dist = future.length()
                    clearance = self.body_r + o.body_r + 12.0
                    if future_dist < clearance:
                        future_away = future / future_dist if future_dist > 1e-6 else away
                        avoid += future_away * (1.0 - future_dist / clearance) * 1.4
                # Keep to the right of our travel direction. Opposing sailors then
                # naturally choose opposite sides instead of converging on one side.
                if wish.length() > 0 and dist < 125.0:
                    side = V(wish.y, -wish.x)
                    side_bias += side * (0.55 * urgency)
        if wish.length() > 0:
            if avoid.length() > 0.02 or side_bias.length() > 0.02:
                wish = wish + avoid * 2.3 + side_bias
                if wish.length() > 1e-6:
                    wish = wish.normalize()
        elif avoid.length() > 0.35 and not (self.working or self.at_post or self.at_engine):
            wish = avoid.normalize() * 0.4
        danger = clamp(slope.length() / 0.7 + (0.6 if self.grip_mult < 0.5 else 0.0), 0, 1)
        sp = 300.0 * lerp(1.0, 0.5, self.caution * danger) * lerp(1.0, 0.7, self.fatigue) * (0.8 if self.carry else 1.0) * (1.0 - 0.25 * self.g.ship.flood) * lerp(0.55, 1.0, self.health)
        grip = 8.0 * self.grip_mult
        self.vel = self.vel.lerp(wish * sp, clamp(grip * dt, 0.0, 1.0))
        self.vel += slope * 500.0 * dt + self.wash_push * 300.0 * dt
        if self.level == Level.MAIN and self.mode == Sailor.ABOARD and self.grip_mult < 0.22 and self.pos.length() > 0:
            # A bad slip near an open rail can carry a sailor off the side, not just collide with the hull boundary.
            edge, edge_d = None, 1e9
            for ea, eb in g.ship.open_edges:
                cp = closest_on_seg(self.pos, ea, eb)
                dd = self.pos.distance_to(cp)
                if dd < edge_d:
                    edge, edge_d = cp, dd
            if edge is not None and edge_d < 18 and random.random() < 0.12 * dt:
                outward = edge.normalize() if edge.length() else V(0, 1)
                self.pos = V(edge) + outward * 35
                self.vel = self.vel + outward * 90
                g.crew.say("%s loses footing on the wet deck and slips over the side!" % self.name)
                self._fall()
                return
        self.pos += self.vel * dt
        self.pos, self.vel = self.g.ship.collide(self.pos, self.vel, self.radius, self.level)
        desired = self.facing
        if wish.length() > 0:
            desired = math.atan2(wish.y, wish.x)
        elif self.vel.length() > 30:
            desired = math.atan2(self.vel.y, self.vel.x)
        self.facing = lerp_angle(self.facing, desired, 1 - math.exp(-(6.0 if self.grip_mult < 0.5 else 12.0) * dt))
        speed = self.vel.length()
        if speed > 15:
            self.phase += speed * dt * 0.09
        self.flail = lerp(self.flail, 1.0 if (self.grip_mult < 0.5 and speed > 30) else 0.0, 1 - math.exp(-8 * dt))

    # --- AI
    def _think(self):
        # Rescue-boat launch orders hold while selected hands assemble at the davit point.
        if (self in self.g.rescue_boat_hands
                and self.g.mob_rescue_mode in ("boat_assembly", "boat_launching")):
            self._enter("boat_launch")
            return
        # Station assignments are exclusive and outrank ordinary fatigue/social/work AI.
        # The relief helmsman and radio operator cannot be pulled away by background jobs.
        if self is self.g.helm_operator:
            self._enter("post")
            return
        if self is self.g.radio_operator:
            self._enter("radio")
            return
        if self.role == self.CAPTAIN and self.g.captain_resting:
            self._enter("rest")
            return
        if self.role == self.CAPTAIN and self.fatigue >= 0.78:
            self.g.captain_resting, self.g.captain_rest_elapsed = True, 0.0
            self.g._update_station_roles(0.0)
            self._enter("rest")
            return
        if self.g.rescue_engineer is self:          # the ship is being brought round: this man is on the engine, not at the rail
            self.alert_target = None
            self._enter("engine")
            return
        t = self.rescue_target
        if t is not None and t.mode == self.SWIMMING:
            self._enter("rescue")
            return
        self.rescue_target = None
        a = self.alert_target
        if a is not None:
            if a.mode == self.SWIMMING and self.g.crew.alarm_target is a:
                if self.alert_delay <= 0:
                    self._enter("rush")
                    return
            else:
                self.alert_target = None
        # Fresh catch outranks optional cleaning, socialising, rest and standby.
        # Keep the helm, radio, engine watch, active line work, rescue, and an
        # already-started fish-handling task under their existing assignments.
        critical_task = self.task in ("set", "haul", "engine", "rescue", "rush", "gaff", "dress")
        critical_station = self in (self.g.helm_operator, self.g.radio_operator) or self.at_engine
        if self.role != self.CAPTAIN and not critical_task and not critical_station:
            if self.duty not in ("engine", "haul", "set"):
                if self.g.table.has_work(self) and self.g.line.room("dress", self):
                    self._enter("dress")
                    return
                if self.g.table.room() and self.g.find_loose_fish(self) is not None and self.g.line.room("gaff", self):
                    self._enter("gaff")
                    return
        # Once assigned to the bucket line, remain on the job while water is hazardous.
        # Catch processing above still outranks this emergency maintenance task.
        if self.task == "bucket" and self.g._bucket_water_needed():
            self._enter("bucket")
            return
        self._enter(self.duty if self.duty else self._pick_task())

    def _pick_task(self):
        g, ln = self.g, self.g.line
        if self is g.helm_operator:
            return "post"
        if self is g.radio_operator:
            return "radio"
        if self.role == self.CAPTAIN:
            if g.captain_resting or self.fatigue >= 0.78:
                if not g.captain_resting:
                    g.captain_resting, g.captain_rest_elapsed = True, 0.0
                    g._update_station_roles(0.0)
                return "rest"
            return "post"
        if self.task == "gaff" and (self.carry or self.item is not None):
            return "gaff"                       # finish what we've started
        if self.task == "dress" and (self.dress_fish is not None or self.carry or g.table.has_work(self)):
            return "dress"
        if self.task == "rest" and self.fatigue > 0.15:
            return "rest"
        if self.fatigue > 0.8:
            return "rest"
        if self.role != self.CAPTAIN:
            # The engineer keeps watch underway and is recalled immediately for a neglected check.
            checks_due = min(g.engine_oil, g.cooling_intake, g.shaft_seal) < 80.0 or not g.engine_ok
            if g.engine_hold > 0 and ln.room("engine", self) and (self.role == self.VETERAN or g.engine_wait > 4.0 or checks_due):
                return "engine"
            if ln.wants("stern") and ln.room("stern", self):
                return "set"
            if ln.wants("hauler") and ln.room("hauler", self):
                return "haul"
            if g.table.has_work(self) and ln.room("dress", self):
                return "dress"
            if g.find_loose_fish(self) is not None and g.table.room() and ln.room("gaff", self):
                return "gaff"
            if self._find_patch() is not None:
                return "clean"
            # Helm relief is selected centrally when the captain actually rests;
            # an unattended helm never summons every deckhand into the wheelhouse.
        if self.morale < 0.45 and self.social_cd <= 0:
            return "social"
        if self.fatigue > 0.55:
            return "rest"
        return "post" if self.role == self.CAPTAIN else "idle"

    def _enter(self, t):
        if t == self.task and t != "idle":
            return
        if self.sleeping_in_bunk and t != "rest":
            idx = self.rest_bunk_index
            if idx is not None and 0 <= idx < len(self.g.ship.bunk_stands):
                self.pos = V(self.g.ship.bunk_stands[idx])
            self.sleeping_in_bunk = False
            self.vel = V(0, 0)
            self.has_target, self.path = False, []
            self.path_goal = None
        self._release()
        self.level_goal = None
        if t == "set" and not self.g.line.claim("stern", self):
            t = "idle"
        elif t == "haul" and not self.g.line.claim("hauler", self):
            t = "idle"
        elif t == "clean":
            self.clean_patch = self._find_patch()
            if self.clean_patch is None:
                t = "idle"
            else:
                self.clean_patch.claimed_by = self
        elif t == "engine":
            if not self.g.line.claim("engine", self):
                t = "idle"
        elif t == "gaff":
            self.item = self.g.find_loose_fish(self)
            if self.item is None or not self.g.line.claim("gaff", self):
                self.item, t = None, "idle"
            else:
                self.item.claimed_by = self
                self.stage, self.work_t = "fetch", 0.0
        elif t == "dress":
            if not self.g.table.has_work(self) or not self.g.line.claim("dress", self):
                t = "idle"
        elif t == "social":
            self.chat_partner = self._find_partner()
            if self.chat_partner is None:
                self.social_cd, t = 15.0, "idle"
            else:
                self.chat_t = 0.0
        self.task, self.working = t, False

    def _release(self):
        g = self.g
        g.line.release(self)
        if self.carry:                       # put down whatever we were carrying
            for c in self.carry:
                g.items.append(FishItem(self.pos, c))
            self.carry = []
        self.hatch_idx = None
        if self.item is not None and self.item.claimed_by is self:
            self.item.claimed_by = None
        self.item = None
        if self.dress_fish is not None:          # leave the fish on the table, with whatever has been done to it
            if self.dress_fish.claimed_by is self:
                self.dress_fish.claimed_by = None
            self.dress_fish = None
        if self.clean_patch is not None and self.clean_patch.claimed_by is self:
            self.clean_patch.claimed_by = None
        self.clean_patch, self.chat_partner = None, None

    def _go_to(self, pos, tol, level=Level.MAIN):
        """Walk to pos on the given level, changing levels only when the destination has space."""
        pos = V(pos)
        if level == Level.WHEELHOUSE and not self.g.wheelhouse_goal_allowed(self, pos):
            self.has_target, self.path = False, []
            self.vel *= 0.25
            return False
        if self is self.g.helm_operator:
            helm = self.g.ship.wheelhouse_stations["helm"]
            if level != Level.WHEELHOUSE or pos.distance_to(helm) > 42.0:
                return False
        if self is self.g.radio_operator:
            radio = self.g.ship.wheelhouse_stations["radio"]
            if level != Level.WHEELHOUSE or pos.distance_to(radio) > 42.0:
                return False
        if level == Level.WHEELHOUSE:
            self.level_goal = V(pos)
        elif self.level != level:
            self.level_goal = None

        if self._needs_hop(pos, level):
            # Never climb into a full/blocked wheelhouse. Stop the approach rather than
            # walking into the ladder forever; the task can retry when the space opens.
            if level == Level.WHEELHOUSE and not self.g.ship.wheelhouse_entry_space(pos, self):
                self.has_target, self.path = False, []
                self.vel *= 0.25
                return False
            lk = self.g.ship.next_link(self.level, level, self.pos, pos)
            if lk is None:
                return False
            ent = lk.pos(self.level)
            if self.pos.distance_to(ent) <= 30:
                hatch_key = self.g.ship.hatch_key_for_link(lk)
                if hatch_key and not self.g.ship.hatch_is_open(hatch_key):
                    self.g._start_hatch_action(self, hatch_key, automatic=True)
                    return False
                if hatch_key:
                    self.auto_close_hatch = hatch_key if self.auto_close_hatch is None else self.auto_close_hatch
                self.start_climb(lk)
            else:
                self._walk(ent, 24)
            return False
        return self._walk(pos, tol)

    def _needs_hop(self, pos, level):
        """True if pos is on another level, or in a compartment he cannot walk to from here."""
        return self.level != level or not self.g.ship.maps[level].connected(self.pos, pos)

    def _walk(self, pos, tol):
        requested = V(pos)
        same_goal = (self.path_goal is not None and self.path_goal.distance_to(requested) <= 30.0
                     and self.path_target is not None)
        target = V(self.path_target) if same_goal else requested
        # Check arrival against the *reachable* endpoint. Previously find_path
        # could snap an unsafe bow/hatch coordinate to the nearest walkable cell,
        # while the sailor kept measuring distance to the unreachable original.
        if self.pos.distance_to(target) <= tol:
            self.has_target, self.path = False, []
            return True
        self.target, self.has_target = V(target), True
        stale = self.path_goal is None or self.path_goal.distance_to(requested) > 30 or not self.path
        if stale and self.time - self.last_plan > 0.25:       # replan at most 4x a second
            planned = self._plan_path(self.pos, requested, self.level)
            self.path, self.path_goal, self.last_plan = planned, V(requested), self.time
            # The final node is either the true safe goal or the closest safe cell
            # in this connected component. Persist it across retries and task ticks.
            self.path_target = V(planned[-1]) if planned else V(requested)
            self.target = V(self.path_target)
            self.no_progress_t = 0.0
            self.progress_distance = self.pos.distance_to(self.target)
            if self.pos.distance_to(self.target) <= tol:
                self.has_target, self.path = False, []
                return True
        return False

    def _do_task(self, dt):
        m = self.g.ship.markers
        self.working = False
        self.at_post = False
        was_at_engine = self.at_engine          # remembered for the engine watch's hysteresis below
        self.at_engine = False
        self.at_radio = False
        t = self.task
        if t == "set":
            self.working = self._go_to(m["stern_set"] + V(40, self.spot_off.y * 1.5), 40)
        elif t == "haul":
            self.working = self._go_to(m["haul_station"] + self.spot_off * 0.5, 40)
        elif t == "clean":
            self._task_clean(dt)
        elif t == "rush":
            self._task_rush(dt)
        elif t == "order":
            if self._needs_hop(self.order_goal, self.order_level):
                self._go_to(self.order_goal, 10, self.order_level)       # by ladder
            elif not self.order_planned:                                 # on the right level: the last stretch
                self.order_planned = True
                self.target, self.has_target = V(self.order_goal), True
                self.path, self.path_goal = self._plan_path(self.pos, self.order_goal, self.level), V(self.order_goal)
        elif t == "engine":
            station = m["engine"] + V(0, self.spot_off.y * 0.4)
            station_level = self.g.ship.marker_level.get("engine", Level.MAIN)
            was_on_watch = was_at_engine
            self.at_engine = self._go_to(station, 30, station_level)
            # Hysteresis: deck tilt nudges him a few units off his spot. He steps back to it, but
            # stays on watch (and keeps the engine staffed) while he is still close.
            if (not self.at_engine and was_on_watch and self.level == station_level
                    and self.pos.distance_to(station) < 48.0):
                self.at_engine = True
            self.working = self.at_engine
        elif t == "radio":
            station = self.g.ship.wheelhouse_stations["radio"]
            self.at_radio = self._go_to(station, 24, Level.WHEELHOUSE)
            self.working = False  # standing wireless watch is not heavy labour
        elif t == "muster":
            if self.muster_target is None or not self.g.muster_active:
                self._enter("idle")
            elif self._go_to(self.muster_target, 28, Level.MAIN):
                self.vel *= 0.0
                self.g._muster_arrive(self)
        elif t == "bucket":
            self._task_bucket(dt)
        elif t == "boat_launch":
            target = self.g._rescue_boat_launch_spot()
            self.working = self._go_to(target + self.spot_off * 0.12, 24, Level.MAIN)
        elif t == "gaff":
            self._task_gaff(dt)
        elif t == "dress":
            self._task_dress(dt)
        elif t == "rest":
            # Rest duty uses the aisle to approach a reserved full-size berth, then the
            # sailor's physical position moves onto the mattress. sleeping_in_bunk bypasses
            # both obstacle response and crew separation until an urgent task wakes him.
            rest_pos = self.g.rest_bunk_for(self)
            approach = self.g.rest_bunk_approach_for(self)
            if self.sleeping_in_bunk:
                self.vel = V(0, 0)
            elif self._go_to(approach, 10, Level.BELOW):
                self.pos = V(rest_pos)
                self.vel = V(0, 0)
                self.has_target, self.path = False, []
                self.path_goal = None
                self.sleeping_in_bunk = True
            asleep = self.sleeping_in_bunk
            self.fatigue = max(self.fatigue - (0.045 if asleep else 0.028) * dt, 0.0)
            self.morale = min(self.morale + (0.008 if asleep else 0.005) * dt, 1.0)
        elif t == "social":
            self._task_social(dt)
        elif t == "post":
            station_level = self.g.ship.marker_level.get("captain_post", Level.MAIN)
            self.at_post = self._go_to(m["captain_post"], 18, station_level)
        elif t == "rescue":
            self._task_rescue(dt)
        elif t == "idle":
            if self.level == Level.BELOW and not self.sleeping_in_bunk:
                # Nobody lingers in the cabin or the engine room between jobs (the engineer included, once his checks are
                # done): back up to the deck standby, where the next job on deck will find him.
                self._go_to(m["rest_spot"] + self.spot_off * 0.25, 40, Level.MAIN)
                return
            if self.level != Level.MAIN:
                return                                       # idle in the wheelhouse: he stays put until there is work on deck
            self.wander_t -= dt
            if self.wander_t <= 0:
                base = m[random.choice(["bow_lookout", "rest_spot"])]   # keep idle hands away from the open gap
                self.loiter = base + V(random.uniform(-60, 20), random.uniform(-45, 45))
                self.wander_t = random.uniform(5, 10)
            if self.loiter is not None:
                self._go_to(self.loiter, 40)

    def _task_rush(self, dt):
        """Everyone runs to the rail nearest the man in the water and stands there, watching."""
        sw = self.alert_target
        if sw is None or sw.mode != self.SWIMMING or self.g.crew.alarm_target is not sw:
            self.alert_target = None
            self._enter("idle")
            return
        pt, tan, inward = self.g.ship.hull_frame(sw.pos)
        slot = (sum(map(ord, self.name)) % 5) - 2            # spread along the rail instead of piling up
        post = pt + inward * 45 * self.scale + tan * slot * 60
        if self._go_to(post, 40):
            d = sw.pos - self.pos
            self.facing = lerp_angle(self.facing, math.atan2(d.y, d.x), 1 - math.exp(-6 * dt))

    def _task_gaff(self, dt):
        """Take a fish off the deck and lay it on the cutting table."""
        g = self.g
        if self.stage == "fetch":
            it = self.item
            if it is None or it not in g.items:
                self.item = None
                self._enter("idle")
                return
            if self._go_to(it.pos, 30):
                self.working = True
                self.work_t += dt
                if self.work_t >= 1.0 - 0.5 * self.skill:
                    g.items.remove(it)
                    self.carry = [it.fish]
                    self.item = None
                    self.stage, self.work_t = "deliver", 0.0
        elif self._go_to(g.ship.markers["table_stand"] + V(self.spot_off.x * 0.6, 0), 34) and g.table.room():    # wait here if the table is full
            self.working = True
            self.work_t += dt
            if self.work_t >= 0.8:
                g.table.raw.extend(self.carry)
                self.carry = []
                self._enter("idle")

    def _task_dress(self, dt):
        """Bleed, gut/de-gill, slice, then carry the finished fish through an open hold hatch into the ice."""
        g, tb, m = self.g, self.g.table, self.g.ship.markers
        if self.carry:                                        # a dressed fish: down through an open hatch to the ice
            if self.hatch_idx is None:
                self.hatch_idx = g.pick_hatch()
            hatch_key = "hold_%d" % (self.hatch_idx + 1)
            if not g.ship.hatch_is_open(hatch_key) and g.ship.hatch_is_open("hold_%d" % (2 - self.hatch_idx)):
                self.hatch_idx = 1 - self.hatch_idx
                hatch_key = "hold_%d" % (self.hatch_idx + 1)
            if self._go_to(m["hatch_%d" % (self.hatch_idx + 1)], 30):
                if not g.ship.hatch_is_open(hatch_key):
                    # Fish processing is a normal deck workflow: the hand at the
                    # hatch dogs it open, stows the catch, then closes it again.
                    self.working = False
                    self.work_t = 0.0
                    if not g._start_hatch_action(self, hatch_key, automatic=True):
                        if self.hatch_wait_warning_t <= 0.0:
                            g.crew.say("%s: I can't work this hold cover yet; clearing the landing first." % self.name)
                            self.hatch_wait_warning_t = 8.0
                    return
                self.working = True
                self.work_t += dt
                if self.work_t >= 1.2 - 0.6 * self.skill:
                    for c in self.carry:
                        g.stow(c, hatch_idx=self.hatch_idx)
                        g.crew.add_catch(c.value)
                        g.crew.say("Catch stowed: %s (%s grade, quality %d%%)." % (c.name, c.grade(), round(c.quality * 100)))
                    self.carry, self.work_t, self.hatch_idx = [], 0.0, None
                    # A hatch opened for stowing is a temporary opening, not a
                    # permanent flooding hazard. Dog it once the fish is below.
                    if g.ship.hatch_is_open(hatch_key) and not g._hatch_in_use(hatch_key, self):
                        g._start_hatch_action(self, hatch_key, automatic=True)
            elif self.vel.length() > 40:
                self.drip_t -= dt
                if self.drip_t <= 0:
                    self.drip_t = 0.22
                    g.splats.append([V(self.pos) + V(random.uniform(-6, 6), random.uniform(-6, 6)), V(0, 0), 0.0, 14.0, random.uniform(2.0, 3.5)])
            return
        stand = m["table_stand"] + V(self.spot_off.x * 0.6, 0)
        if not self._go_to(stand, 28):
            return
        f = self.dress_fish
        if f is None or f not in tb.raw:
            f = self.dress_fish = tb.take(self)
            self.work_t = 0.0
            if f is None:
                self._enter("idle")
                return
        self.working = True
        self.work_t += dt
        sloppy = 0.05 * (1.0 - self.skill)
        if not f.bled:
            if self.work_t >= 2.2 - 1.2 * self.skill:
                f.bled, f.quality, self.work_t = True, f.quality - sloppy, 0.0
                f.alive = False
                g.crew.say("%s bleeds out the %s; it stops thrashing." % (self.name, f.name))
                g.cut_blood(stand, 1.0)
        elif not f.gutted:
            if self.work_t >= 3.6 - 2.0 * self.skill:
                f.gutted, f.quality, self.work_t = True, f.quality - sloppy, 0.0
                g.cut_blood(stand, 1.6)
        elif not f.sliced:
            if self.work_t >= 2.0 - 0.7 * self.skill:
                f.sliced = True
                f.quality = max(0.0, f.quality - sloppy * 0.35)
                self.work_t = 0.0
                g.cut_blood(stand, 0.45)
                g.crew.say("%s finishes slicing the %s for the hold." % (self.name, f.name))
        else:                                                 # fully dressed: pick it up and take it below
            tb.raw.remove(f)
            f.claimed_by = None
            self.carry = [f]
            self.dress_fish, self.work_t = None, 0.0

    def _task_bucket(self, dt):
        """Walk to the stern bucket-line station, then pass/throw water over the open rail."""
        g = self.g
        slot = 1 if self.bucket_slot is None else int(self.bucket_slot)
        target = V(-g.ship.length * 0.5 + 100.0, (slot - 1) * 52.0)
        if self.level != Level.MAIN:
            return
        if self._go_to(target, 28.0, Level.MAIN):
            self.working = True
            self.work_t += dt
            self.facing = lerp_angle(self.facing, math.pi, 1.0 - math.exp(-4.0 * dt))

    def _task_clean(self, dt):
        p = self.clean_patch
        if p is None or p not in self.g.patches:
            self.clean_patch = None
            self._enter("idle")
            return
        if self._go_to(p.pos, 40):
            self.working = True
            p.cleaning += dt / (3.5 - 1.5 * self.skill)
            if p.cleaning >= 1.0:
                self.g.patches.remove(p)
                self.clean_patch = None
                self.add_morale(0.02)
                self._enter("idle")

    def _find_patch(self):
        best, best_d = None, 1e18
        for p in self.g.patches:
            if p.free_for(self):
                d = self.pos.distance_to(p.pos)
                if d < best_d:
                    best, best_d = p, d
        return best

    def _find_partner(self):
        best, best_s = None, 1e18
        for o in self.g.sailors:
            if o is self or o.mode != self.ABOARD:
                continue
            if o.level != self.level or o.sleeping_in_bunk:
                continue
            score = self.pos.distance_to(o.pos) - 500 * o.morale
            if o.role == self.VETERAN and self.role == self.DECKHAND:
                score -= 300
            if score < best_s:
                best, best_s = o, score
        return best

    def _task_social(self, dt):
        p = self.chat_partner
        if p is None or p.mode != self.ABOARD:
            self.social_cd = 15.0
            self._enter("idle")
            return
        if self._go_to(p.pos, 80, p.level):
            self.chat_t += dt
            self.add_morale((0.03 + 0.05 * p.morale) * dt)       # company cheers people up
            p.add_morale(0.02 * dt)
            self.caution = lerp(self.caution, p.caution, 1 - math.exp(-0.04 * dt))   # philosophy bleeds both ways
            p.caution = lerp(p.caution, self.caution, 1 - math.exp(-0.02 * dt))
            if p.role == self.VETERAN and self.role == self.DECKHAND:
                self.skill = min(self.skill + 0.01 * p.skill * dt, 1.0)               # mentoring
            if self.chat_t > 8:
                self.social_cd = 30.0
                self._enter("idle")

    # --- rescue
    def start_rescue(self, sw):
        if self.mode != self.ABOARD:
            return
        self.rescue_target, self.rescue_t = sw, 0.0
        self.order_hold, self.ordering = 0.0, False
        self._enter("rescue")

    def _rail_post(self, from_pos):
        best = self.g.ship.nearest_hull_point(from_pos)
        return best + (-best).normalize() * 45 * self.scale

    LINE_RANGE = 330.0

    def throw_time(self):
        return 1.2 - 0.6 * self.skill

    def _task_rescue(self, dt):
        """Throw a lifeline to the man in the water and reel him in. Out of reach? The ship is brought round (Game.update)."""
        g, w = self.g, self.g.world
        sw = self.rescue_target
        if sw is None or sw.mode != self.SWIMMING:
            if sw is not None and sw.lifeline is self:
                sw.lifeline = None
            self.rescue_target, self.line_state = None, ""
            self._enter("idle")
            return
        if not self._go_to(self._rail_post(sw.pos), 30):
            self.line_state = ""
            return
        self.working = True
        reach = self.pos.distance_to(sw.pos)
        if sw.lifeline is self:                              # he has the line: haul away
            if reach > self.LINE_RANGE * 1.4 or w.speed > 220:
                sw.lifeline, self.line_state, self.rescue_t = None, "adjust", 0.0
                g.crew.say("%s: The line's come up short! Bring her closer!" % self.name)
                return
            self.line_state = "haul"
            hp = g.ship.nearest_hull_point(sw.pos)
            gap = hp - sw.pos
            step = V(0, 0)
            if gap.length() > 1e-6:
                step = gap.normalize() * min((60.0 + 70.0 * self.skill) * dt, gap.length())
            sw.wpos += step.rotate_rad(w.heading)
            sw.pos = w.deck_of(sw.wpos)
            if sw.pos.distance_to(hp) < 45:
                sw.pull_aboard(self.pos)
                self.rescue_target, self.line_state = None, ""
                self.add_morale(0.15)
                g.crew.say("%s hauls %s back aboard." % (self.name, sw.name))
            return
        if sw.lifeline is not None:                          # a shipmate already has him on the line
            self.line_state = ""
            return
        if reach > self.LINE_RANGE or w.speed >= 140:        # out of range / still carrying way: wait for the ship to be adjusted
            self.rescue_t, self.line_state = 0.0, "adjust"
            return
        self.line_state = "throw"
        self.rescue_t += dt
        if self.rescue_t >= self.throw_time():
            sw.lifeline = self
            self.line_state = "haul"
            g.crew.say("%s throws a lifeline to %s - he's got it!" % (self.name, sw.name))

    # --- falling, swimming, dying
    def _fall(self):
        g = self.g
        self.carry = []            # whatever he was carrying goes with him
        self._release()
        self.mode, self.task = self.SWIMMING, "swim"
        self.has_target, self.working, self.ordering, self.order_hold = False, False, False, 0.0
        self.path, self.path_goal = [], None
        self.wpos = g.world.world_of(self.pos)
        self.breath = clamp(1.0 - self.fatigue, 0.0, 1.0)      # stamina: swimming wears it down
        self.vel = V(0, 0)
        self.swim_goal = None
        self.lifeline, self.wvel, self.hit_cd, self.line_state = None, V(0, 0), 0.0, ""
        self.climb_t = 0.0
        self.add_morale(-0.2)
        g.crew.on_fell(self)

    def _hull_push(self):
        """If the ship has run into a person in the water, the hull shoves him aside instead of passing over him.
        Returns (impact 0..1, depth) on contact, otherwise None."""
        g, w, ship = self.g, self.g.world, self.g.ship
        if not ship.on_deck(self.pos):
            return None
        pt = ship.nearest_hull_point(self.pos)
        out = pt - self.pos
        depth = out.length()
        if depth > 1e-6:
            out = out / depth
        else:
            out = pt.normalize() if pt.length() > 1e-6 else V(0, 1)
        self.pos = pt + out * 12.0
        self.wpos = w.world_of(self.pos)
        impact = clamp(w.speed / w.max_speed, 0.0, 1.0)
        self.wvel += out.rotate_rad(w.heading) * (30.0 + 200.0 * impact) * 0.3
        if self.wvel.length() > 380.0:
            self.wvel.scale_to_length(380.0)
        return impact, depth

    def hurt(self, amount, cause="struck by the ship"):
        if self.mode == self.DEAD or amount <= 0:
            return
        self.health = clamp(self.health - amount, 0.0, 1.0)
        if self.health <= 0:
            self.mode, self.selected, self.dead_t = self.DEAD, False, 0.0
            self.lifeline = None
            self.g.crew.on_killed(self, cause)

    def _swim(self, dt):
        g, w = self.g, self.g.world
        strength = w.waves.strength
        if self.lifeline is not None and (self.lifeline.mode != self.ABOARD or self.lifeline.rescue_target is not self):
            self.lifeline = None
        self.hit_cd = max(self.hit_cd - dt, 0.0)
        hull_pt = g.ship.nearest_hull_point(self.pos)
        d_hull = self.pos.distance_to(hull_pt)
        held = self.lifeline is not None
        v = V(0, 0)
        # A fallen sailor does not magically know where the ship is. He scans
        # forward using his own visibility cone, and only then commits to swimming
        # toward the hull. Once sighted, the target is refreshed as the ship moves.
        ship_world = V(w.ship_pos)
        if self.swim_goal is None:
            delta_ship = ship_world - self.wpos
            distance_ship = delta_ship.length()
            # Sailor facing is ship-local; transform the world bearing back into
            # the deck frame before testing the forward cone.
            bearing_world = math.atan2(delta_ship.y, delta_ship.x) if distance_ship > 1e-6 else w.heading + self.facing
            bearing = (bearing_world - w.heading) % TAU
            diff = abs((bearing - self.facing + math.pi) % TAU - math.pi)
            sight_range = min(1000.0, max(45.0, g.weather.visibility_km() * self.VISIBILITY_UNITS_PER_KM))
            if distance_ship <= sight_range and diff <= self.VIEW_HALF_ANGLE:
                self.swim_goal = V(w.ship_pos)
                g.crew.say("%s spots the ship through the spray and starts swimming for the hull." % self.name)
            else:
                # Slow scan while treading water; wave drift remains active.
                self.facing = (self.facing + 0.45 * dt) % TAU
        else:
            self.swim_goal = V(w.ship_pos)
        goal = self.swim_goal if self.swim_goal is not None else self.wpos
        to_goal = goal - self.wpos
        if not held and self.swim_goal is not None and to_goal.length() > 15:
            v = to_goal.normalize() * 90.0 * lerp(1.0, 0.25, self.fatigue) * lerp(0.6, 1.0, self.health)
        drift = V(1, 0).rotate_rad(w.wave_direction) * (12 + 40 * strength) * w.scale * 0.33
        self.wvel *= math.exp(-2.0 * dt)
        self.wpos += (v + drift + self.wvel) * dt
        self.pos = w.deck_of(self.wpos)
        hit = self._hull_push()                           # the ship pushes him aside; a fast ship hurts
        if hit is not None and hit[0] > 0.12:
            impact, depth = hit
            self.hurt(0.25 * impact * dt)                 # grinding along the hull
            if self.mode != self.SWIMMING:
                return
            if self.hit_cd <= 0:
                self.hit_cd = 0.7
                run_over = depth > 30
                self.hurt(0.04 + 0.45 * impact + (0.15 if run_over else 0.0))
                if self.mode != self.SWIMMING:
                    return
                if self.time - self.hit_say > 6.0:
                    self.hit_say = self.time
                    g.crew.say("%s is %s!" % (self.name, "run down by the ship" if run_over or impact > 0.5 else "struck by the hull"))
        want = w.deck_of(goal) - self.pos
        if want.length() > 5:
            self.facing = lerp_angle(self.facing, math.atan2(want.y, want.x), 1 - math.exp(-6 * dt))
        # Swimming never drowns him outright: it wears him out. Holding a line costs almost nothing.
        if held:
            rate = 0.0015
        else:
            rate = (1.0 / 110.0) * (1.0 + strength) * (1.0 + 0.6 * (1.0 - self.health)) * (1.0 if v.length() > 1 else 0.6)
        self.fatigue = clamp(self.fatigue + rate * dt, 0.0, 1.0)
        self.breath = 1.0 - self.fatigue
        if self.fatigue >= 1.0 and not held:              # too tired to keep his head up
            self.mode, self.selected, self.dead_t = self.DEAD, False, 0.0
            self.lifeline = None
            g.crew.on_drowned(self)
            return
        if d_hull < 110 and w.speed < 90:
            self.climb_t += dt
            if self.climb_t >= 3.0 - 1.5 * self.skill:
                self.climb_to = self._rail_post(self.pos)
                self.mode = self.CLIMBING
                self.lifeline = None
        else:
            self.climb_t = max(self.climb_t - dt, 0.0)

    def pull_aboard(self, from_pos):
        if self.mode == self.SWIMMING:
            self.climb_to = V(from_pos) + V(random.uniform(-20, 20), random.uniform(-20, 20))
            self.mode = self.CLIMBING
            self.lifeline = None

    def _climb(self, dt):
        self.pos = self.pos.lerp(self.climb_to, 1 - math.exp(-8 * dt))
        if self.pos.distance_to(self.climb_to) < 12:
            self.pos = V(self.climb_to)
            self.mode, self.task, self.vel = self.ABOARD, "idle", V(0, 0)
            self.swim_goal = None
            self.fatigue = clamp(self.fatigue + 0.25, 0, 1)
            self.add_morale(-0.1)
            self.order_hold = 0.0
            self.g.crew.on_back(self)

    def _dead(self, dt):
        w = self.g.world
        self.dead_t += dt
        self.wvel *= math.exp(-2.0 * dt)
        self.wpos += (V(1, 0).rotate_rad(w.wave_direction) * (12 + 40 * w.waves.strength) * w.scale * 0.2 + self.wvel) * dt
        self.pos = w.deck_of(self.wpos)
        self._hull_push()                                 # the ship doesn't pass over the body either

    def _health_bar(self, g, c, y_off):
        if self.health >= 0.995:
            return
        bw = 40
        x, y = c[0] - bw / 2, c[1] - y_off * self.scale * g.zoom
        pygame.draw.rect(g.screen, (20, 20, 20), (x, y, bw, 5))
        pygame.draw.rect(g.screen, (90, 200, 90) if self.health > 0.4 else (225, 70, 50), (x, y, bw * clamp(self.health, 0, 1), 5))

    # --- drawing
    def shadow(self, g):
        sc, f = self.scale, self.facing
        sl = g.ship.slope
        sh = [g.SS(self.pos + sl * 5 * sc + V(0, 3 * sc) + V(math.cos(TAU * i / 18) * 10, math.sin(TAU * i / 18) * 17).rotate_rad(f) * sc)
              for i in range(18)]
        pygame.draw.polygon(g.ov_d, (0, 0, 0, 64), sh)

    def draw(self, g):
        if self.mode in (self.SHORE, self.RESCUE_BOAT):
            return                    # represented on the Crew & Shore sheet / rescue boat, not on deck
        if self.mode == self.ABOARD and self.level == Level.BELOW and self.sleeping_in_bunk and self.task == "rest":
            return self._draw_sleeping_in_bunk(g)
        if self.mode == self.DEAD:
            return self._draw_dead(g)
        if self.mode in (self.SWIMMING, self.CLIMBING):
            return self._draw_swimmer(g)
        s, z, sc = g.screen, g.zoom, self.scale
        f = self.facing

        def P(x, y):
            return g.SS(self.pos + V(x, y).rotate_rad(f) * sc)

        def R(r):
            return max(1, int(r * sc * z))

        def ell(cx, cy, rx, ry, n=18):
            return [P(cx + math.cos(TAU * i / n) * rx, cy + math.sin(TAU * i / n) * ry) for i in range(n)]

        if self.selected:
            pygame.draw.circle(s, hexc("#f2d04b"), g.SS(self.pos), R(24), 2)
        step = math.sin(self.phase)
        dark = tuple(int(c * 0.65) for c in self.jacket)
        pygame.draw.polygon(s, hexc("#1d1a17"), ell(step * 10, 6, 6, 3.5, 12))
        pygame.draw.polygon(s, hexc("#1d1a17"), ell(-step * 10, -6, 6, 3.5, 12))
        spread = 1 + 0.45 * self.flail
        swing = step * 9
        wob = math.sin(self.time * 16) * 7 * self.flail
        ha, hb = (-swing + wob, -17 * spread), (swing - wob, 17 * spread)
        if self.carry:                       # both hands forward on whatever he's carrying
            ha, hb = (10, -9), (10, 9)
        arm = tuple(int(c * 0.85) for c in self.jacket)
        pygame.draw.line(s, arm, P(0, -12), P(*ha), R(6))
        pygame.draw.line(s, arm, P(0, 12), P(*hb), R(6))
        pygame.draw.circle(s, self.skin, P(*ha), R(3.5))
        pygame.draw.circle(s, self.skin, P(*hb), R(3.5))
        body_shape = ell(0, 0, 9, 16)
        pygame.draw.polygon(s, self.jacket, body_shape)
        pygame.draw.polygon(s, dark, body_shape, max(1, R(1.2)))
        # Uniform details add clear highlights and a readable silhouette at normal zoom.
        jacket_light = mix(self.jacket, (245, 235, 205), 0.24)
        pygame.draw.line(s, jacket_light, P(-4, -10), P(-3, 5), max(1, R(1.5)))
        pygame.draw.line(s, dark, P(-5, -10), P(-5, 10), max(1, R(1.2)))
        collar = [P(-5, -13), P(0, -8), P(5, -13), P(2, -5), P(-2, -5)]
        pygame.draw.polygon(s, mix(self.jacket, (232, 223, 201), 0.58), collar)
        pygame.draw.line(s, dark, P(1.5, -5), P(2, 8), max(1, R(1.0)))
        for button_y in (-2, 3, 8):
            pygame.draw.circle(s, (229, 208, 157), P(2, button_y), max(1, R(1.2)))
        pocket = [P(-7, -3), P(-2.5, -3), P(-2.5, 2), P(-7, 2)]
        pygame.draw.polygon(s, mix(self.jacket, (0, 0, 0), 0.15), pocket)
        pygame.draw.lines(s, jacket_light, True, pocket, max(1, R(0.9)))
        if self.role == self.CAPTAIN:
            pygame.draw.line(s, GOLD, P(-8, -9), P(-4, -7), max(1, R(1.5)))
            pygame.draw.line(s, GOLD, P(4, -7), P(8, -9), max(1, R(1.5)))
        else:
            pygame.draw.line(s, mix(dark, (30, 25, 20), 0.35), P(-6, 9), P(7, 9), max(1, R(1.8)))
        if self.carry:                       # a single fish, bloody if it has been cut
            c0 = self.carry[0]
            draw_fish(s, c0.name, P(15, 0), f + math.pi, 24 * sc * z, clamp(c0.quality, 0.0, 1.0), 0.0, c0.bled)
            if c0.gutted:
                pygame.draw.line(s, (235, 205, 195), P(11, 0.5), P(20, 0.5), 1)
        if self.task == "bucket":
            # A clearly readable, hand-sized pail; retain a minimum pixel size at normal zoom.
            bp = P(13, 7)
            bw = max(10, int(18 * sc * z))
            bh = max(12, int(20 * sc * z))
            x0, y0 = int(bp.x - bw * 0.50), int(bp.y - bh * 0.30)
            x1, y1 = int(bp.x + bw * 0.50), int(bp.y + bh * 0.46)
            bucket_pts = [(x0, y0), (x1, y0),
                          (int(bp.x + bw * 0.35), y1),
                          (int(bp.x - bw * 0.35), y1)]
            # Dark body, wooden staves, heavy rim, and a visible water surface.
            pygame.draw.polygon(s, (116, 78, 43), bucket_pts)
            pygame.draw.polygon(s, (178, 132, 78), bucket_pts, max(1, int(1.5 * z)))
            pygame.draw.line(s, (224, 194, 145), (x0 + 1, y0 + 2), (x1 - 1, y0 + 2), max(2, int(2 * z)))
            pygame.draw.line(s, (76, 49, 29), (int(bp.x), y0 + 3), (int(bp.x), y1 - 1), 1)
            pygame.draw.arc(s, (236, 216, 173),
                            (x0 - 1, y0 - max(5, bh // 2), bw + 2, max(9, bh)), math.pi, TAU,
                            max(1, int(1.5 * z)))
            pygame.draw.ellipse(s, (104, 184, 202),
                                (x0 + 2, y0 + 2, max(4, bw - 4), max(2, int(3 * z))))
        self._head(g, P, R, 1.0, 0.0)
        self._health_bar(g, g.SS(self.pos), 27)
        if self.selected:
            g.text(self.name, g.SS(self.pos) + V(-40, -30 * sc * z), (255, 255, 255))
            if self.has_target:
                tt = g.SS(self.target)
                pygame.draw.line(s, hexc("#f2d04b"), (tt[0] - 6, tt[1] - 6), (tt[0] + 6, tt[1] + 6), 2)
                pygame.draw.line(s, hexc("#f2d04b"), (tt[0] - 6, tt[1] + 6), (tt[0] + 6, tt[1] - 6), 2)

    def _draw_sleeping_in_bunk(self, g):
        """Draw a compact, horizontal sleeping pose sized to the sailor's timber berth."""
        s, z, sc = g.screen, g.zoom, self.scale
        center = g.SS(self.pos)

        def P(x, y):
            return g.SS(self.pos + V(x * sc, y * sc))

        def R(r):
            return max(1, int(r * sc * z))

        # Body lies along the ship's length; the head and shoulders stay within the bed.
        body = [P(math.cos(TAU * i / 20) * 16.0, math.sin(TAU * i / 20) * 6.2) for i in range(20)]
        pygame.draw.polygon(s, hexc("#231f1a"), [P(math.cos(TAU * i / 20) * 17.0, math.sin(TAU * i / 20) * 7.0) for i in range(20)])
        pygame.draw.polygon(s, self.jacket, body)
        pygame.draw.lines(s, mix(self.jacket, (235, 224, 198), 0.28), True, body, max(1, R(0.8)))
        pygame.draw.line(s, mix(self.jacket, (224, 216, 191), 0.24), P(-7, -2), P(7, -2), max(1, R(1.5)))
        pygame.draw.line(s, mix(self.jacket, (30, 25, 21), 0.38), P(-4, 3), P(9, 3), max(1, R(1.2)))
        # A wool blanket over the lower body, tucked in along the berth.
        blanket = [P(-18.0, -8.5), P(7.0, -8.5), P(7.0, 8.5), P(-18.0, 8.5)]
        pygame.draw.polygon(s, hexc("#55664f"), blanket)
        pygame.draw.polygon(s, hexc("#2f3b2c"), blanket, max(1, R(0.8)))
        for k in (-12.0, -4.0):
            pygame.draw.line(s, hexc("#8a9a7e"), P(k, -8.0), P(k, 8.0), max(1, R(0.8)))
        head = P(16.0, 0.0)
        pygame.draw.circle(s, self.skin, head, R(4.0))
        pygame.draw.circle(s, self.hair if self.role != self.CAPTAIN else hexc("#1b1b1b"), head, R(4.6), max(1, R(1.0)))
        # A subtle breathing tick conveys sleep without adding animation-heavy particles.
        pygame.draw.line(s, hexc("#d9cfb5"), P(-9, -4.5), P(-3, -4.5), max(1, R(1.0)))
        if self.selected:
            pygame.draw.ellipse(s, hexc("#f2d04b"), (center[0] - R(22), center[1] - R(14), R(44), R(28)), max(1, R(1.0)))
            g.text(self.name, V(center) + V(-34, -24 * sc * z), (255, 255, 255))

    def draw_faint(self, g):
        """A sailor on another level than the one on screen: just a ghost of a marker."""
        c = g.SS(self.pos)
        r = max(4, int(13 * self.scale * g.zoom))
        pygame.draw.circle(g.ov_d, self.jacket + (110,), c, r)
        pygame.draw.circle(g.ov_d, (240, 240, 240, 120), c, r, 2)
        if self.selected:
            pygame.draw.circle(g.ov_d, (242, 208, 75, 230), c, r + 5, 2)
            g.text(self.name, V(c) + V(-40, -r - 22), (255, 255, 255))

    def _head(self, g, P, R, hx, hy):
        s, z, sc = g.screen, g.zoom, self.scale
        pygame.draw.circle(s, self.skin, P(hx - 1, hy - 8.5), R(2.5))
        pygame.draw.circle(s, self.skin, P(hx - 1, hy + 8.5), R(2.5))
        cream = hexc("#e8e4d8")
        if self.role == self.CAPTAIN:
            brim = [P(hx + 8 + math.cos(TAU * i / 14) * 5, hy + math.sin(TAU * i / 14) * 7) for i in range(14)]
            pygame.draw.polygon(s, (20, 20, 20), brim)
            pygame.draw.circle(s, cream, P(hx, hy), R(9))
            pygame.draw.circle(s, (31, 47, 69), P(hx, hy), R(9), 1)
            pygame.draw.circle(s, GOLD, P(hx + 5, hy), R(1.8))
        else:
            pygame.draw.circle(s, self.hair, P(hx, hy), R(8))
            pygame.draw.circle(s, cream, P(hx, hy), R(6.5), R(3.5))
            pygame.draw.polygon(s, cream, [P(hx - 13, hy - 2), P(hx - 7, hy - 2), P(hx - 7, hy + 2), P(hx - 13, hy + 2)])
            pygame.draw.line(s, cream, P(hx - 13, hy), P(hx - 17, hy - 3), 2)
            pygame.draw.line(s, cream, P(hx - 13, hy), P(hx - 17, hy + 3), 2)

    def _draw_swimmer(self, g):
        s, z, sc = g.screen, g.zoom, self.scale
        f = self.facing
        c = g.S(self.pos)
        for i in range(3):
            fr = (self.time * 2 + i / 3) % 1.0
            pygame.draw.circle(g.ov_d, (255, 255, 255, int(90 * (1 - fr))), c, max(2, int((14 + 30 * fr) * sc * z)), 2)

        def P(x, y):
            return g.S(self.pos + V(x, y).rotate_rad(f) * sc)

        def R(r):
            return max(1, int(r * sc * z))

        st = math.sin(self.time * 7)
        pygame.draw.line(s, self.jacket, P(2, -8), P(10 + 8 * st, -15), R(5))
        pygame.draw.line(s, self.jacket, P(2, 8), P(10 - 8 * st, 15), R(5))
        body = [P(math.cos(TAU * i / 16) * 7, math.sin(TAU * i / 16) * 13) for i in range(16)]
        pygame.draw.polygon(s, tuple(int(x * 0.8) for x in self.jacket), body)
        self._head(g, P, R, 2.0, 0.0)
        if self.selected:
            pygame.draw.circle(s, hexc("#f2d04b"), c, R(24), 2)
        bw = 48
        x, y = c[0] - bw / 2, c[1] - 34 * sc * z
        pygame.draw.rect(s, (20, 20, 20), (x, y, bw, 6))
        pygame.draw.rect(s, (80, 200, 230) if self.breath > 0.35 else (220, 60, 50), (x, y, bw * clamp(self.breath, 0, 1), 6))
        self._health_bar(g, c, 25)
        if self.selected:
            g.text(self.name, V(c) + V(-40, -48 * sc * z), (255, 255, 255))

    def _draw_dead(self, g):
        s, z, sc = g.screen, g.zoom, self.scale
        a = clamp((30 - self.dead_t) / 10, 0.0, 1.0)
        if a <= 0:
            return
        f = self.facing + 0.2 * math.sin(self.time * 0.8)
        R = lambda r: max(1, int(r * sc * z))
        P = lambda x, y: g.S(self.pos + V(x, y).rotate_rad(f) * sc)
        col = tuple(int(c * 0.55 * a + 22 * (1 - a)) for c in self.jacket)
        pygame.draw.line(s, col, P(0, -10), P(7, -19), R(5))
        pygame.draw.line(s, col, P(0, 10), P(7, 19), R(5))
        pygame.draw.polygon(s, col, [P(math.cos(TAU * i / 16) * 9, math.sin(TAU * i / 16) * 15) for i in range(16)])
        pygame.draw.circle(s, tuple(int(c * 0.6 * a) for c in self.hair), P(1, 0), R(8))


# -------------------------------------------------------------------- game

# ------------------------------------------------------------------ weather
class Weather:
    """Fronts roll through every few minutes: clear, overcast, fog, drizzle, rain, thunderstorm.  The sky eases from one
    to the next.  Wind drives the sea state and swings the swell; rain soaks the deck; fog shrinks the view; the air
    temperature (and so how fast the catch spoils on deck) and how well the fish bite follow the sky."""
    #            cloud  rain  fog   wind  storm
    KINDS = {"clear":   (0.08, 0.00, 0.00, 0.18, 0.0), "cloudy": (0.65, 0.00, 0.00, 0.34, 0.0),
             "fog":     (0.80, 0.00, 0.85, 0.08, 0.0), "drizzle": (0.80, 0.30, 0.10, 0.36, 0.0),
             "rain":    (0.92, 0.68, 0.05, 0.56, 0.0), "storm":   (1.00, 1.00, 0.00, 0.95, 1.0)}
    NAMES = {"clear": "Clear", "cloudy": "Overcast", "fog": "Fog", "drizzle": "Drizzle", "rain": "Rain", "storm": "Thunderstorm"}
    ORDER = ["clear", "cloudy", "fog", "drizzle", "rain", "storm"]
    SAYS = {"clear": "Captain: The sky's clearing.", "cloudy": "Captain: Cloud's building up from the west.",
            "fog": "Captain: Fog's coming down. Keep an eye out for the buoys.", "drizzle": "Captain: Drizzle. The deck will be slick.",
            "rain": "Captain: Rain's setting in. Mind your footing.", "storm": "Captain: Storm! Keep off the rails and lash down anything loose!"}
    NEXT = {"clear": {"cloudy": 1.0, "fog": 0.25}, "cloudy": {"clear": 0.7, "drizzle": 0.6, "fog": 0.2, "rain": 0.3},
            "fog": {"clear": 0.6, "cloudy": 0.8}, "drizzle": {"cloudy": 0.6, "rain": 0.7, "clear": 0.2},
            "rain": {"drizzle": 0.7, "storm": 0.45, "cloudy": 0.4}, "storm": {"rain": 1.0}}

    def __init__(self, g, start=None):
        self.g = g
        self.outlook_date = g.world.calendar_date()
        self.day_outlook = forecast_for_date(self.outlook_date)
        # Start in a climate-plausible regime for the campaign's date (1 April 1962).
        self.kind = start if start in self.KINDS else self.day_outlook.condition
        self.cloud, self.rain, self.fog, self.wind, self.storm = self.KINDS[self.kind]
        self.wind_dir = g.world.wave_direction          # the way the wind blows towards (radians, y down)
        self.hold = random.uniform(120.0, 220.0)
        self.flash, self.bolt, self.bolt_t = 0.0, None, 0.0
        self.next_bolt, self.pending = random.uniform(3.0, 8.0), []

    def forecast(self, days=5):
        return forecast_range(self.g.world.calendar_date(), days)

    def pick_next(self):
        hour = self.g.world.hour()
        opts = dict(self.NEXT[self.kind])
        if "fog" in opts:
            opts["fog"] *= 2.2 if 3.0 <= hour < 9.0 else 0.5        # fog forms in the small hours
        # The dated outlook nudges the fast-moving local fronts toward the day's
        # prevailing regime without locking every minute to a single condition.
        target = self.day_outlook.condition
        if target in opts:
            opts[target] *= 3.0
        if target == "storm" and "rain" in opts:
            opts["rain"] *= 1.7
        elif target in ("rain", "drizzle") and "storm" in opts:
            opts["storm"] *= 0.7
        elif target == "fog" and "cloudy" in opts:
            opts["cloudy"] *= 1.2
        return random.choices(list(opts), list(opts.values()))[0]

    def set(self, kind, say=True):
        previous = self.kind
        if kind != previous and say:
            self.g.crew.say(self.SAYS[kind])
        self.kind = kind
        if kind != previous:
            handler = getattr(self.g, "on_weather_transition", None)
            if handler is not None:
                handler(previous, kind)
        self.hold = random.uniform(70.0, 130.0) if kind == "storm" else random.uniform(110.0, 250.0)

    def cycle(self):
        """W key: jump to the next kind of weather."""
        self.set(self.ORDER[(self.ORDER.index(self.kind) + 1) % len(self.ORDER)])
        self.hold = 240.0

    def update(self, dt):
        current_date = self.g.world.calendar_date()
        if current_date != self.outlook_date:
            self.outlook_date = current_date
            self.day_outlook = forecast_for_date(current_date)
        self.hold -= dt
        if self.hold <= 0.0:
            self.set(self.pick_next())
        tgt = self.KINDS[self.kind]
        k, kw = 1.0 - math.exp(-0.10 * dt), 1.0 - math.exp(-0.16 * dt)
        self.cloud += (tgt[0] - self.cloud) * k
        self.rain += (tgt[1] - self.rain) * k
        self.fog += (tgt[2] - self.fog) * k
        self.wind += (tgt[3] - self.wind) * kw
        self.storm += (tgt[4] - self.storm) * k
        t = self.g.world.time
        self.wind_dir += (math.sin(t * 0.013) + 0.6 * math.sin(t * 0.041 + 1.0)) * 0.01 * dt     # the wind veers slowly
        self.flash = max(0.0, self.flash - dt * 4.5)
        self.bolt_t = max(0.0, self.bolt_t - dt)
        for i in range(len(self.pending) - 1, -1, -1):             # a second flicker, and the thunder that follows
            self.pending[i][0] -= dt
            if self.pending[i][0] <= 0.0:
                kind = self.pending.pop(i)[1]
                if kind == "flash":
                    self.flash = 0.85
                elif random.random() < 0.3:
                    self.g.crew.say("Thunder rolls across the water.")
        if self.storm > 0.5:
            self.next_bolt -= dt
            if self.next_bolt <= 0.0:
                self.strike()
                self.next_bolt = random.uniform(2.5, 9.0)

    def strike(self):
        self.flash, self.bolt_t = 1.0, 0.22
        x, pts = random.uniform(0.1, 0.9), []
        for i in range(9):
            pts.append((x + random.uniform(-0.04, 0.04) * (i > 0), 0.04 + 0.1 * i * random.uniform(0.8, 1.2)))
            x += random.uniform(-0.03, 0.03)
        self.bolt = pts
        if random.random() < 0.6:
            self.pending.append([random.uniform(0.08, 0.2), "flash"])
        self.pending.append([random.uniform(0.6, 3.5), "thunder"])

    # --- what the sky does to everything else
    def bite_mod(self):
        return max(0.3, 1.0 + 0.3 * self.cloud * (1.0 - self.rain) + 0.2 * self.rain * (1.0 - self.storm) - 0.5 * self.storm)

    def air_temp(self):
        # Coastal Hakodate/North Pacific climate analogue, with small local sky and
        # diurnal adjustments. It deliberately replaces the old fixed 22 C deck air.
        day = self.g.world.calendar_date()
        seasonal_mean = HAKODATE_MEAN_TEMP_C[day.month - 1]
        daylight = self.g.world.daylight()
        diurnal = 2.2 * daylight * (1.0 - self.cloud) - 1.2 * self.rain - 1.0 * (1.0 - daylight)
        return seasonal_mean + diurnal

    def visibility_km(self):
        return lerp(10.0, 0.5, clamp(self.fog, 0.0, 1.0)) * (1.0 - 0.45 * self.rain)

    def wind_kt(self):
        return int(round(self.wind * 45.0))

    def wind_from(self):
        a = self.wind_dir
        bearing = (math.degrees(math.atan2(math.cos(a), -math.sin(a))) + 180.0) % 360.0
        return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((bearing + 22.5) // 45) % 8]

    def label(self):
        return self.NAMES[self.kind]

    def text(self):
        return "Weather: %s | wind %s %d kt | visibility %.1f km | air %dC   (W: change)" % (
            self.label(), self.wind_from(), self.wind_kt(), self.visibility_km(), round(self.air_temp()))


class _NoGameplayKeys:
    """Indexable key-state shim used while the navigation chart UI is open."""
    def __getitem__(self, _key):
        return False


_NO_GAMEPLAY_KEYS = _NoGameplayKeys()


class FollowBird:
    """A sea bird following the stern while the crew are actively fishing."""

    def __init__(self, pos):
        self.pos = V(pos)
        self.vel = V(random.uniform(-22.0, 22.0), random.uniform(-18.0, 18.0))
        self.flutter = random.uniform(0.0, TAU)
        self.dive_t = random.uniform(0.0, 5.0)


class Game:
    PAD = 10                                     # HUD panel inner padding
    LINE_H = 19                                  # HUD panel line pitch (fixed, so lines never collide)
    HEAD_H = 22                                  # HUD panel header row height
    PANEL_BG = (8, 12, 18, 178)
    PANEL_BORDER = (150, 150, 140)

    def __init__(self):
        pygame.init()
        info = pygame.display.Info()          # open at a size that fits the desktop, then let the user resize
        w0 = min(W, max(MIN_W, info.current_w - 80)) if info.current_w > 0 else W
        h0 = min(H, max(MIN_H, info.current_h - 120)) if info.current_h > 0 else H
        self.screen = pygame.display.set_mode((w0, h0), pygame.RESIZABLE)
        pygame.display.set_caption("Japanese Deep Sea Fishing Simulator 1962 — v13.2.11 Phase B Campaign")
        self.clock = pygame.time.Clock()
        # Bounded caches are reset on resize; immutable UI surfaces and static
        # artwork are reused between frames instead of repeatedly rasterized.
        self._ui_surface_cache = OrderedDict()
        self._world_background_cache = None
        self._world_background_target = None
        self._world_background_age = 1.0
        self._world_background_state = None
        self._world_background_interval = 1.0 / 30.0
        self._ship_static_cache = None
        self._ship_static_cache_rect = None
        self._ship_static_target_surface = None
        self._ship_static_cache_age = 1.0
        self._ship_static_cache_state = None
        self._ship_static_cache_interval = 1.0 / 30.0
        self._profile_background_cache = OrderedDict()
        self.resize(w0, h0)
        self._glows = {}
        font_names = "consolas,menlo,dejavusansmono,couriernew"
        self.font = CachedFont(pygame.font.SysFont(font_names, 16))
        self.hud_compact_font = CachedFont(pygame.font.SysFont(font_names, 14))
        self.chart_title_font = CachedFont(pygame.font.SysFont(font_names, 19, bold=True))
        self.chart_header_font = CachedFont(pygame.font.SysFont(font_names, 13, bold=True))
        self.chart_font = CachedFont(pygame.font.SysFont(font_names, 11))
        self.chart_small_font = CachedFont(pygame.font.SysFont(font_names, 9))
        self.chart_italic_font = CachedFont(pygame.font.SysFont(font_names, 11, italic=True))
        self.auction_font = CachedFont(pygame.font.SysFont(font_names, 16))
        self.auction_title_font = CachedFont(pygame.font.SysFont(font_names, 18, bold=True))
        self.chart_open = False
        self._chart_base_surface = None
        self._chart_cache_size = None
        self._chart_transform = None
        self._chart_dim_surface = None
        self._chart_map_rect = None
        self._chart_outer_rect = None
        self._phase_b_chart_base_surface = None
        self._phase_b_chart_base_size = None
        self._phase_b_chart_transform = None
        self.chart_route_editor = None
        self.chart_move_index = None
        self.chart_status = ""
        self._chart_phase_button_rects = {}
        self._phase_b_contact_hitboxes = []
        self.phase_b_chart_selected_contact_id = None
        # Shift + right-drag builds the same persistent waypoint route as the chart.
        self.ocean_plot_drag_start = None
        self.ocean_plot_drag_start_screen = None
        self.ocean_plot_preview_world = None
        self.ocean_plot_edit_index = None
        self.ocean_plot_edge_extended = False
        self.context_menu = None  # right-click actions for crew, hatches, hauler and loose gear
        self.navigation_fix_last_attempt = {"landmark": -1e9, "sextant": -1e9, "rdf": -1e9, "sounder": -1e9}
        self.navigation_fix_cooldowns = {"landmark": 15.0, "sextant": 45.0, "rdf": 30.0, "sounder": 15.0}
        # V13V1-10: one short-lived request allows a second sailor to give an
        # independent observation of the same target, followed by a comparison card.
        self.crew_report_pending = None
        self.crew_report_display = None
        # The persistent HUD is deliberately critical-only; F1 opens the detailed sheet.
        self.hud_mode = "navigation"       # F7 toggles navigation / operations summary
        self.telemetry_tab = "telemetry"   # retained for compatibility with older save/test contracts
        self.telemetry_visible = True
        self.telemetry_panel_rect = pygame.Rect(10, 10, 226, 54)
        self.telemetry_tab_hitboxes = {}
        self.info_sheet_tab = "ship_catch" # ship_catch / telemetry / crew / controls
        self.info_sheet_scroll = 0
        self.show_controls = True
        self.show_fishing_minigame = True
        self.longline_minimap_debug = False
        self.sinking_elapsed = 0.0
        self.abandon_ship_started = False
        self.tow_retry_elapsed = 0.0
        self.tow_request_active = False       # persistent until a tug delivers us or we are docked
        self.tow_failed_call_count = 0        # repeated unanswered calls raise the response pressure offshore
        self.adrift_elapsed = 0.0             # no-power, no-way-on timer in simulation seconds
        self.tow_debug_enabled = False        # F12 writes a once-per-simulation-second diagnostic to the console
        self.tow_debug_elapsed = 0.0
        self.tow_debug_sample_elapsed = 0.0
        self.tow_debug_last_ship_pos = None
        self.tow_transit_active = False
        self.tow_transit_elapsed = 0.0
        self.tow_transit_target = None
        self.tow_transit_distance_start = 0.0
        self.tow_escort = None
        self._tow_escort_synced_id = None
        self.tow_escort_status_message = ""
        self.tow_escort_status_t = 0.0
        self.anchor_deployed = False
        self.anchor_hud_rect = pygame.Rect(0, 0, 0, 0)
        self.last_ship_pos_for_teleport_check = None
        self.zoom = 0.6
        self.rock_ang, self.rock_shift = 0.0, V(0, 0)
        self.timescale, self.helm_warned, self.no_helm_t = 1, False, 0.0
        self.arrow_helm_warn_t = 0.0     # cooldown: don't spam "nobody at the helm" on held arrow
        self.engine_hold, self.engine_wait, self.engine_warned, self._engine_on = 0.0, 0.0, False, False
        # Phase 4: three analogue engine-room checks. Values are condition/availability,
        # not electronics; low readings reduce output and critical readings trip the diesel.
        self.engine_oil, self.cooling_intake, self.shaft_seal = 100.0, 100.0, 100.0
        self.engine_ok, self.engine_power = True, 1.0
        self.engine_runtime = 0.0
        self.engine_unattended_time = 0.0
        self.engine_unattended_warning_stage = 0
        self.engine_fault_count = 0
        self.engine_service_component, self.engine_service_t = None, 0.0
        self.engine_condition_warnings = set()
        self._engine_bilge_trip = False
        self.hauler_engine_warned = False
        self.hatch_bail_t = 0.0
        self.hold_bail_t = 0.0
        self.ice_trimmed_time = 0.0
        self.smoke, self.smoke_t = [], 0.0
        self.time_since_wave_msg = 99.0
        self.cash, self.earned, self.market = 25000, 0, 1.0       # effective harbour price index
        self.market_base = 1.0
        self.market_storm_surge = 0.0
        self.auction_active = False
        self.auction_index = 0
        self.auction_session_sold = 0
        self.auction_session_total = 0
        self._auction_resolving = False
        self.auction_offers = []
        self.arrival_done, self.dock_t = True, 0.0
        self.dock_shore_leave_started = False
        self.shore_radio_operator = None
        self.shore_wait_active = False
        self.shore_wait_previous_timescale = 1
        self.crew_sheet_open = False
        self.crew_sheet_tab = "crew"
        self.crew_sheet_scroll = 0
        self.crew_sheet_hitboxes = []
        self.hire_candidates = []
        self.rescue_engineer = None
        # Man-overboard recovery is a state machine, not an instant teleport.
        self.mob_rescue_mode = "idle"       # idle/lifeline/ship_turn/boat_assembly/boat_launching/boat_out/boat_pickup/boat_return/recovering
        self.rescue_boat_state = None        # water-frame position, heading, phase, casualty, and crew
        self.rescue_boat_hands = set()
        self.rescue_boat_passenger = None
        self.rescue_boat_assembly_elapsed = 0.0
        self.peek, self.climb_used = None, False                       # Q/E held away from a ladder: look at another level
        self.hatch_flip = 0                                            # the hold hatches take fish in turn
        self.ice, self.hold_temp, self.ice_warn = ICE_CAP, 0.5, 0     # the hold: flake ice and its temperature
        self.fuel, self.fuel_warn, self.tow_t = FUEL_CAP, 0, 0.0      # logistics: fuel, bait and gaffs
        # Station ownership is explicit. Only the captain (or named veteran relief)
        # may hold the helm; one designated crewmember owns the radio until relieved.
        self.helm_operator = None
        self.relief_helmsman = None
        self._helm_previous_duty = ""
        self.captain_resting = False
        self.captain_rest_elapsed = 0.0
        self.radio_operator = None
        self.radio_duty_active = False
        self.pending_radio_calls = []
        self.radio_bubble_text, self.radio_bubble_t = "", 0.0
        self.radio_bubble_speaker = "COAST / FLEET RADIO"
        # Radio replies are shown turn-by-turn; never overwrite an entire exchange in one frame.
        self.radio_transcript_queue = []
        self.radio_transcript_priority = 0
        self.broadcast_director = BroadcastDirector()
        self.broadcast_visible_priority = 0
        self.broadcast_visible_channel = ""
        self.broadcast_visible_source = ""
        self.broadcast_crew_chatter_timer = random.uniform(80.0, 130.0)
        self.broadcast_intercom_timer = random.uniform(125.0, 210.0)
        self.broadcast_harbour_extra_timer = random.uniform(100.0, 180.0)
        self.broadcast_harbour_gossip_count = 0
        self._broadcast_was_docked = None
        self.notebook_open = False
        self.notebook_section = 0   # 0 crew log, 1 radio log, 2 calendar, 3 forecast, 4 gut book
        self.notebook_page = 0
        self.notebook_hitboxes = {}
        self.crew_log_entries = []
        self.radio_log_entries = []
        # Gut-book memories survive hotspot expiry and are included in the v13.2.07 career save.
        self.gut_book_entries: list[GutBookEntry] = []
        self.next_gut_book_id = 1
        self.gut_book_entry_limit = MAX_GUT_BOOK_ENTRIES
        # Phase 3 radio state must exist before the first Game.update() call.
        self.radio_message, self.radio_message_t = "", 0.0
        self.radio = RadioSystem(self)
        self.navigation_mode = "dead_reckoning"  # Phase 3: compass-only navigation
        self.radio_calls = []
        self.tow_arrival_t = 0.0
        self.bait = {k: 0.0 for k in BAITS}
        self.bait_fresh = {k: 1.0 for k in BAITS}
        self.bait["saury"] = BAIT_FILL
        self.bait_sel, self.bait_warned = "saury", False
        self.gaffs, self.harness = GAFFS, False
        self.roll, self.roll_v = 0.0, 0.0                              # the ship's roll, a damped spring driven by the swell
        self.ship = Ship()
        self.world = World(self)
        # v13.2.11: the campaign can switch between the regional A plane and the
        # high-seas B projection. Legacy hull physics stays in the Hakodate-local
        # plane; phase_adapter maps it to/from each fleet/weather coordinate system.
        self.campaign_phase = "A"
        self.traffic_world = TrafficWorld(world_seed=1962, active_cap=30, phase="A")
        self._phase_traffic_worlds = {"A": self.traffic_world}
        self.relationship_dynamics = RelationshipDynamics(world_seed=1962)
        self.relationship_dynamics.seed_baseline(self.traffic_world, 0.0)
        self._phase_relationship_dynamics = {"A": self.relationship_dynamics}
        self.ship_radio_service = ShipRadioService(world_seed=1962)
        self.distress_dispatcher = DistressDispatcher(world_seed=1962)
        # M9: one physical player-vessel rescue commitment at a time. This mission shares
        # the same AIShip identity as the chart/radio contact and is career-save aware.
        self.player_rescue_manager = PlayerRescueMissionManager()
        # M9 extension: a separate autonomous fleet responder assists incidents the
        # player has not committed to, reusing a scheduled vessel identity.
        self.ai_rescue_manager = AIDistressResponseManager()
        # M11: low-frequency overheard ship-to-ship traffic. It owns its cadence
        # and cooldowns so it cannot spam, perturb fishing RNG, or backlog while busy.
        self.ambient_ship_radio = AmbientShipRadioDirector(world_seed=1962)
        self.last_mayday_source_id = None
        self.traffic_hail_status = ""
        self.traffic_hail_status_t = 0.0
        # v13.2.02: selectable, modal ship-to-ship radio UI. Histories are kept
        # per stable vessel ID so the player can swap contacts and return later.
        self.radio_ui_open = False
        self.radio_ui_contacts = []
        self.radio_ui_selected_ship_id = None
        self.radio_ui_scroll = 0
        self.radio_ui_hitboxes = {}
        self.radio_ui_histories = {}
        self.radio_ui_active_end = {}
        self.radio_ui_status = "Select a vessel, choose a topic, then advance each radio turn."
        self.radio_hud_rect = pygame.Rect(0, 0, 0, 0)
        self._drops, self._ripples, self._fog_cache, self._cloud = [], [], {}, None
        self.crew = Crew(self)
        # The notebook is bounded so long-running careers cannot grow memory forever.
        self.log_entry_limit = 600
        self.muster_active = False
        self.muster_elapsed = 0.0
        self.muster_expected = set()
        self.muster_reports = set()
        self.muster_unavailable = {}
        self.bucket_chain_active = False
        self.bucket_chain_hands = set()
        self.bucket_work_t = 0.0
        self.bucket_log_t = 0.0
        self.engine_bail_t = 0.0
        self.hold_bail_t = 0.0
        self.engine_room_damage = 0.0
        self.ice_trimmed_time = 0.0
        self.line = Longline(self)
        self.follow_birds = []
        self.seabird_flocks = {}      # id(hotspot) -> SeabirdFlock: flight-modelled birds working each school
        self.weather = Weather(self, start=None)
        # v13.2.03: spatial weather for remote traffic / reports. The existing
        # shipboard Weather remains authoritative for the player vessel itself.
        self.world_weather_grid = WeatherGrid(world_seed=1962, phase="A")
        self._phase_weather_grids = {"A": self.world_weather_grid}
        self.world_weather_grid.observe_local(
            self._traffic_player_position_nm(), cloud=self.weather.cloud, precipitation=self.weather.rain,
            fog=self.weather.fog, wind_speed_kt=self.weather.wind_kt(),
            wind_direction_rad=self.weather.wind_dir, sea_state=float(self.world.sea_state))
        self.patches, self.items, self.hold = [], [], []
        self.table = Table()
        self.splats = []                        # blood spots: [deck pos, vel, age, life, size]
        self.table_blood = 0.0                  # how bloody the cutting table is, 0..1
        self.sailors = []
        m = self.ship.markers
        for name, role, pos in [
            ("Captain Ishida", Sailor.CAPTAIN, m["captain_post"]),
            ("Takeda", Sailor.VETERAN, m["haul_station"] + V(-100, -40)),
            ("Yamamoto", Sailor.DECKHAND, m["stern_set"] + V(100, -70)),
            ("Sato", Sailor.DECKHAND, m["stern_set"] + V(100, 70)),
            ("Kondo", Sailor.DECKHAND, m["bow_lookout"] + V(-100, 0)),
            ("Mori", Sailor.DECKHAND, m["rest_spot"]),
        ]:
            sailor = Sailor(self, name, role, pos)
            if name == "Captain Ishida":
                sailor.level = self.ship.marker_level.get("captain_post", Level.MAIN)
            self.sailors.append(sailor)
            self.crew.status[name] = "aboard"
        self.sailors[0].selected = True
        self.helm_operator = self.sailors[0]                 # Captain Ishida owns the helm initially.
        self.relief_helmsman = next((s for s in self.sailors if s.role == Sailor.VETERAN), None)
        self._refresh_hire_candidates()

    # ---- v13.2.07 career persistence ---------------------------------------
    CAREER_GAME_FIELDS = (
        "cash", "earned", "market", "market_base", "market_storm_surge", "ice",
        "hold_temp", "ice_warn", "fuel", "fuel_warn", "tow_t", "gaffs", "harness",
        "roll", "roll_v", "timescale", "helm_warned", "no_helm_t", "engine_hold",
        "engine_wait", "engine_warned", "_engine_on", "engine_oil", "cooling_intake",
        "shaft_seal", "engine_ok", "engine_power", "engine_runtime",
        "engine_unattended_time", "engine_unattended_warning_stage", "engine_fault_count",
        "engine_service_component", "engine_service_t", "_engine_bilge_trip",
        "hauler_engine_warned", "hatch_bail_t", "hold_bail_t", "ice_trimmed_time",
        "engine_room_damage", "table_blood", "sinking_elapsed", "abandon_ship_started",
        "tow_retry_elapsed", "tow_request_active", "tow_failed_call_count", "adrift_elapsed",
        "tow_debug_enabled", "tow_debug_elapsed", "tow_debug_sample_elapsed",
        "tow_transit_active", "tow_transit_elapsed", "tow_transit_distance_start", "tow_transit_target",
        "tow_escort_status_message", "tow_escort_status_t", "anchor_deployed", "tow_arrival_t",
        "navigation_mode", "arrival_done", "dock_t", "dock_shore_leave_started",
        "shore_wait_active", "shore_wait_previous_timescale", "captain_resting",
        "captain_rest_elapsed", "radio_duty_active", "muster_active", "muster_elapsed",
        "bucket_chain_active", "bucket_work_t", "bucket_log_t", "engine_bail_t",
        "mob_rescue_mode", "rescue_boat_assembly_elapsed", "hatch_flip",
        "bait", "bait_fresh", "bait_sel", "bait_warned",
        "broadcast_crew_chatter_timer", "broadcast_intercom_timer", "broadcast_harbour_extra_timer",
        "broadcast_harbour_gossip_count", "_broadcast_was_docked", "radio_message", "radio_message_t",
        "broadcast_visible_priority", "broadcast_visible_channel", "broadcast_visible_source",
        "traffic_hail_status", "traffic_hail_status_t", "auction_session_sold",
        "auction_session_total", "last_mayday_source_id", "campaign_phase",
    )
    CAREER_WORLD_SCALARS = (
        "heading", "speed", "believed_heading", "believed_speed", "last_fix", "last_fix_method",
        "compass_bias", "log_bias", "dr_uncertainty", "throttle", "manual_helm", "max_speed",
        "turn_rate", "prop_direction", "requested_prop_direction", "reversing_elapsed",
        "engine_reversing", "rudder_angle", "sea_state", "auto_weather", "wave_direction",
        "tilt_gain", "time", "zone", "route_arrival_hold", "last_cross_track_error",
        "cruise", "hold", "arrive", "ap_heading", "ap_t", "dock_state", "dock_side",
        "dock_result", "dock_retries", "dock_phase_elapsed", "dock_stall_elapsed",
        "dock_best_distance", "brake", "hotspot_cd", "fishing_report_cd", "next_fishing_report_id",
    )
    CAREER_WORLD_VECTORS = (
        "ship_pos", "believed_pos", "position_error", "destination", "route_origin",
        "ocean_quick_target", "berth", "dock_wp", "rescue_to",
    )
    CAREER_SHIP_FIELDS = (
        "wet", "flood", "engine_flood", "hold_flood", "bucket_count", "list_lat", "slope",
        "list_trim", "freeboard_factor", "pump_flow", "flood_net", "flood_state",
        "flood_taking_t", "flood_calm_t", "hatch_states", "deck_foam",
    )
    CAREER_LINE_FIELDS = (
        "phase", "spacing", "max_points", "bite_rate", "haul_speed", "reach", "snap",
        "fight_range", "slack", "dock_started", "soak_time", "engaged", "landed",
        "auto", "trip_end", "trip_start", "trip_days", "stage", "stage_t", "soak_goal",
        "skip", "retries", "roller_bypassed", "roller_jammed", "roller_condition",
        "line_condition", "hauler_slip", "hauler_drum_condition", "roller_snag_timer",
        "roller_snag_meter", "buoy_snag_meter", "last_buoy_snag_kind", "roller_stress_time",
        "line_strain_time", "_roller_warned", "_slip_warned",
    )
    CAREER_SAILOR_FIELDS = (
        "mode", "keep_ashore", "shore_since", "wheelhouse_exit_elapsed", "wheelhouse_exit_attempts",
        "selected", "has_target", "order_hold", "ordering", "fatigue", "morale", "breath",
        "task", "duty", "working", "grip_mult", "facing", "phase", "flail", "time",
        "think_t", "wander_t", "social_cd", "chat_t", "hatch_wait_warning_t", "drip_t",
        "stuck_t", "no_progress_t", "progress_distance", "stage", "work_t", "at_post",
        "at_engine", "gut_confidence", "gut_last_comment", "level", "at_radio",
        "rest_bunk_index", "sleeping_in_bunk", "climb_t", "dead_t", "health", "line_state",
        "hit_cd", "hit_say", "wage", "owed", "skill", "caution", "alert_delay",
        "jacket", "hair", "skin", "hatch_order", "gear_order", "deck_action", "bucket_slot",
    )
    CAREER_SAILOR_VECTORS = (
        "pos", "vel", "target", "order_goal", "spot_off", "wpos", "wvel", "swim_goal",
        "gut_spot", "path_goal", "path_target", "level_goal", "climb_to", "muster_target",
    )

    @staticmethod
    def _career_encode(value):
        """Encode only JSON-safe data and explicit pygame vectors; reject hidden objects."""
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("career state contains a non-finite number")
            return value
        if isinstance(value, V):
            if not (math.isfinite(float(value.x)) and math.isfinite(float(value.y))):
                raise ValueError("career state contains a non-finite vector")
            return {"__vector2__": [float(value.x), float(value.y)]}
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if isinstance(key, (str, int, float, bool)):
                    out[str(key)] = Game._career_encode(item)
            return out
        if isinstance(value, (list, tuple)):
            return [Game._career_encode(item) for item in value]
        if isinstance(value, set):
            return [Game._career_encode(item) for item in sorted(value, key=str)]
        raise ValueError("unsupported object in career state: %s" % type(value).__name__)

    @staticmethod
    def _career_decode(value):
        if isinstance(value, list):
            return [Game._career_decode(item) for item in value]
        if isinstance(value, dict):
            if set(value) == {"__vector2__"}:
                raw = value["__vector2__"]
                if not isinstance(raw, list) or len(raw) != 2:
                    raise ValueError("invalid vector in career save")
                x, y = float(raw[0]), float(raw[1])
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError("non-finite vector in career save")
                return V(x, y)
            return {str(k): Game._career_decode(v) for k, v in value.items()}
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite number in career save")
        return value

    @staticmethod
    def _career_pack_fish(fish):
        if fish is None:
            return None
        return {name: getattr(fish, name) for name in (
            "name", "value", "quality", "core", "bled", "gutted", "sliced", "alive",
            "deck_exposure", "rough_handling") if hasattr(fish, name)}

    @staticmethod
    def _career_unpack_fish(data):
        if not isinstance(data, dict) or not data.get("name"):
            raise ValueError("invalid fish entry in career save")
        fish = Catch(str(data["name"]), float(data.get("value", 0.0)), float(data.get("quality", 1.0)))
        for name in ("core", "bled", "gutted", "sliced", "alive", "deck_exposure", "rough_handling"):
            if name in data:
                setattr(fish, name, data[name])
        return fish

    def _career_snapshot(self):
        """Capture durable career state; caches, particles and display surfaces are omitted."""
        # Flush observed trust changes before serializing traffic and the social baseline.
        # This makes a save taken immediately after a radio/MAYDAY decision idempotent on load.
        if hasattr(self, "relationship_dynamics") and hasattr(self, "traffic_world"):
            social_events = self.relationship_dynamics.advance(self.traffic_world, self.world.time)
            for event in social_events:
                self.record_log_entry("Fleet gossip: dealings with %s reached %s (%s report)." % (
                    event["source_callsign"], event["target_callsign"], event["direction"]))
        gstate = {name: self._career_encode(getattr(self, name)) for name in self.CAREER_GAME_FIELDS
                  if hasattr(self, name)}
        world = self.world
        wstate = {name: self._career_encode(getattr(world, name)) for name in self.CAREER_WORLD_SCALARS
                  if hasattr(world, name)}
        wvectors = {name: self._career_encode(getattr(world, name)) for name in self.CAREER_WORLD_VECTORS
                    if hasattr(world, name)}
        wstate.update(wvectors)
        wstate["route_waypoints"] = self._career_encode(world.route_waypoints)
        wstate["hotspots"] = []
        for hotspot in world.hotspots:
            detected_by = getattr(hotspot, "detected_by", None)
            if detected_by is not None and hasattr(detected_by, "name"):
                detected_by = str(detected_by.name)
            hotspot_data = {k: getattr(hotspot, k) for k in (
                "x", "y", "species", "strength", "strength_now", "radius", "life", "age",
                "drift_x", "drift_y", "phase", "detected_at") if hasattr(hotspot, k)}
            hotspot_data["detected_by"] = detected_by
            wstate["hotspots"].append(hotspot_data)
        wstate["fishing_reports"] = [
            {k: getattr(r, k) for k in ("report_id", "x", "y", "species", "source", "confidence",
                 "accuracy_radius", "lifetime", "grounded", "age") if hasattr(r, k)}
            for r in world.fishing_reports]

        ship_fields = {name: self._career_encode(getattr(self.ship, name))
                       for name in self.CAREER_SHIP_FIELDS if hasattr(self.ship, name)}
        weather_fields = {name: self._career_encode(getattr(self.weather, name)) for name in (
            "kind", "cloud", "rain", "fog", "wind", "storm", "wind_dir", "hold", "flash",
            "bolt", "bolt_t", "next_bolt", "pending") if hasattr(self.weather, name)}

        sailors = []
        for sailor in self.sailors:
            entry = {"name": str(sailor.name), "role": int(sailor.role)}
            for name in self.CAREER_SAILOR_FIELDS + self.CAREER_SAILOR_VECTORS:
                if hasattr(sailor, name):
                    try:
                        entry[name] = self._career_encode(getattr(sailor, name))
                    except ValueError:
                        # References to other live entities are intentionally not persisted.
                        continue
            entry["path"] = self._career_encode(getattr(sailor, "path", []))
            entry["carry"] = [self._career_pack_fish(f) for f in getattr(sailor, "carry", [])]
            entry["references"] = {
                "lifeline": getattr(getattr(sailor, "lifeline", None), "name", None),
                "rescue_target": getattr(getattr(sailor, "rescue_target", None), "name", None),
                "alert_target": getattr(getattr(sailor, "alert_target", None), "name", None),
            }
            ladder = getattr(sailor, "ladder", None)
            entry["ladder_state"] = None
            if isinstance(ladder, dict):
                link_index = next((i for i, link in enumerate(self.ship.links)
                                   if link is ladder.get("link")), None)
                if link_index is None:
                    raise ValueError("sailor is using an unknown ladder link")
                entry["ladder_state"] = {
                    "link_index": link_index, "to": int(ladder.get("to", sailor.level)),
                    "t": float(ladder.get("t", 0.0)),
                    "from": self._career_encode(ladder.get("from", sailor.pos)),
                    "dest": self._career_encode(ladder.get("dest", sailor.pos)),
                    "flipped": bool(ladder.get("flipped", False)),
                }
            # Work items are rebound by the crew AI after restore; raw object references never enter JSON.
            sailors.append(entry)

        line = {name: self._career_encode(getattr(self.line, name)) for name in self.CAREER_LINE_FIELDS
                if hasattr(self.line, name)}
        point_fields = ("pos", "z", "vel", "vz", "link", "float", "bait", "fresh", "bottom", "fish", "value", "name")
        line["pts"] = [{k: self._career_encode(p[k]) for k in point_fields if k in p} for p in self.line.pts]
        line["claims_by_role"] = {k: [s.name for s in roster] for k, roster in self.line.claims.items()}
        line["auto_hotspot_target_index"] = next((i for i, h in enumerate(world.hotspots)
                                                   if h is self.line.auto_hotspot_target), None)
        line["auto_hotspot_destination"] = self._career_encode(self.line.auto_hotspot_destination)
        line["fight"] = None
        if self.line.fight is not None:
            fight = self.line.fight
            hook_index = next((i for i, p in enumerate(self.line.pts) if p is getattr(fight, "hook", None)), None)
            line["fight"] = {"hook_index": hook_index, **{k: self._career_encode(getattr(fight, k))
                           for k in ("strength", "stamina", "time", "rough", "tension", "seen", "drag",
                                     "slack_t", "strain_t", "over_t", "phase", "run_t", "run_left",
                                     "run_f", "manual") if hasattr(fight, k)}}
        line["gaff"] = None
        if isinstance(self.line.gaff, dict):
            gf = self.line.gaff
            hi = next((i for i, p in enumerate(self.line.pts) if p is gf.get("hook")), None)
            line["gaff"] = {"hook_index": hi, **{k: self._career_encode(v) for k, v in gf.items() if k != "hook"
                                                and isinstance(v, (type(None), bool, int, float, str, list, tuple, dict))}}

        catch_state = {
            "hold": [self._career_pack_fish(f) for f in self.hold],
            "table": [self._career_pack_fish(f) for f in self.table.raw],
            "items": [{"pos": self._career_encode(item.pos), "fish": self._career_pack_fish(item.fish),
                       "angle": item.angle, "thrash_timer": item.thrash_timer, "thrash_anim": item.thrash_anim,
                       "thrash_count": item.thrash_count} for item in self.items],
            "patches": [{"pos": self._career_encode(p.pos), "kind": p.kind, "radius": p.radius,
                         "grip": p.grip, "life": p.life, "age": p.age, "cleaning": p.cleaning,
                         "shape": self._career_encode(p.shape)} for p in self.patches],
            "table_blood": self.table_blood,
        }
        crew_state = {
            "status": self._career_encode(self.crew.status),
            "known_lost": self._career_encode(self.crew.known_lost),
            "log": self._career_encode(self.crew.log[-600:]),
            "catch_count": int(self.crew.catch_count), "catch_value": float(self.crew.catch_value),
            "crew_log_entries": self._career_encode(self.crew_log_entries[-600:]),
            "radio_log_entries": self._career_encode(self.radio_log_entries[-600:]),
            "radio_transcript_queue": self._career_encode(self.radio_transcript_queue[-100:]),
            "radio_transcript_priority": int(self.radio_transcript_priority),
            "radio_bubble_text": str(self.radio_bubble_text), "radio_bubble_t": float(self.radio_bubble_t),
            "radio_bubble_speaker": str(self.radio_bubble_speaker),
            "radio_ui_histories": self._career_encode(self.radio_ui_histories),
            "radio_ui_active_end": self._career_encode(self.radio_ui_active_end),
            "radio_ui_selected_ship_id": self.radio_ui_selected_ship_id,
            "radio_ui_status": str(self.radio_ui_status),
            "radio_message": str(self.radio_message), "radio_message_t": float(self.radio_message_t),
            "helm_operator": getattr(self.helm_operator, "name", None),
            "relief_helmsman": getattr(self.relief_helmsman, "name", None),
            "radio_operator": getattr(self.radio_operator, "name", None),
            "alarm_target": getattr(self.crew.alarm_target, "name", None),
            "unseen_overboard": sorted(getattr(s, "name", str(s)) for s in self.crew.unseen_overboard),
            "sighting_timers": {getattr(s, "name", str(s)): float(t)
                                 for s, t in self.crew.sighting_timers.items()},
        }
        # Object references in rescue/muster state are stored as stable sailor names.
        # The in-flight launch's vectors and route remain explicit JSON data.
        rescue_boat = None
        if self.rescue_boat_state is not None:
            boat = self.rescue_boat_state
            boat_fields = {k: self._career_encode(v) for k, v in boat.items()
                           if k not in ("target", "crew", "passenger")}
            rescue_boat = {
                "fields": boat_fields,
                "target": getattr(boat.get("target"), "name", None),
                "crew": [getattr(s, "name", str(s)) for s in boat.get("crew", [])],
                "passenger": getattr(boat.get("passenger"), "name", None),
            }
        rescue_state = {
            "mode": str(self.mob_rescue_mode),
            "boat": rescue_boat,
            "hands": sorted(getattr(s, "name", str(s)) for s in self.rescue_boat_hands),
            "passenger": getattr(self.rescue_boat_passenger, "name", None),
            "engineer": getattr(self.rescue_engineer, "name", None),
            "assembly_elapsed": float(self.rescue_boat_assembly_elapsed),
        }
        drill_state = {
            "muster_expected": sorted(getattr(s, "name", str(s)) for s in self.muster_expected),
            "muster_reports": sorted(getattr(s, "name", str(s)) for s in self.muster_reports),
            "muster_unavailable": self._career_encode(self.muster_unavailable),
            "bucket_chain_hands": sorted(getattr(s, "name", str(s)) for s in self.bucket_chain_hands),
        }
        def pack_conversation(conversation):
            if conversation is None:
                return None
            return {
                "turns": [{"delay": float(turn.delay), "speaker": turn.speaker,
                           "text": turn.text, "channel": turn.channel} for turn in conversation.turns],
                "priority": int(conversation.priority), "source": str(conversation.source),
                "sequence": int(conversation.sequence), "index": int(conversation.index),
                "timer": float(conversation.timer),
            }

        director_state = {
            "active": pack_conversation(self.broadcast_director.active),
            "pending": [pack_conversation(c) for c in self.broadcast_director.pending],
            "sequence": int(self.broadcast_director._sequence),
            "interrupted_count": int(self.broadcast_director.interrupted_count),
            "completed_count": int(self.broadcast_director.completed_count),
            "emitted_count": int(self.broadcast_director.emitted_count),
        }
        radio_state = {name: self._career_encode(getattr(self.radio, name)) for name in (
            "frequency_khz", "signal_quality", "last_bulletin", "tow_called", "broadcast_timer",
            "conversation_timer", "distress_checked", "panpan_checked", "broadcasts_received",
            "broadcasts_missed") if hasattr(self.radio, name)}
        gut_book_state = {
            "next_id": int(self.next_gut_book_id),
            "entries": [{k: getattr(entry, k) for k in (
                "entry_id", "date", "clock", "elapsed", "sailor", "skill", "species_guess",
                "x", "y", "confidence", "strength")}
                | {"hotspot_index": next((i for i, h in enumerate(world.hotspots)
                                          if h is getattr(entry, "hotspot_ref", None)), None)}
                for entry in self.gut_book_entries[-MAX_GUT_BOOK_ENTRIES:]],
        }
        # Keep the inactive phase worlds too. The active phase is stored in the
        # established top-level sections for backward compatibility; this optional
        # map preserves any previously visited alternate projection across a load.
        inactive_phase_worlds = {}
        active_phase = str(getattr(self, "campaign_phase", "A")).upper()
        for phase, traffic_world in getattr(self, "_phase_traffic_worlds", {}).items():
            phase = str(phase).upper()
            if phase == active_phase:
                continue
            grid = getattr(self, "_phase_weather_grids", {}).get(phase)
            dynamics = getattr(self, "_phase_relationship_dynamics", {}).get(phase)
            if phase not in ("A", "B") or grid is None:
                continue
            inactive_phase_worlds[phase] = {
                "traffic_contacts": traffic_world.snapshot_contacts(),
                "world_weather_grid": grid.snapshot(),
                "relationship_dynamics": dynamics.snapshot() if dynamics is not None else None,
            }
        return {
            "payload_schema_version": 1,
            "game_state": gstate, "world": wstate, "ship": ship_fields, "weather": weather_fields,
            "world_weather_grid": self.world_weather_grid.snapshot(),
            "world_waves": {"strength": float(self.world.waves.strength),
                            "base_angle": float(self.world.waves.base_angle),
                            "time": float(self.world.waves.time)},
            "traffic_contacts": self.traffic_world.snapshot_contacts(),
            "relationship_dynamics": self.relationship_dynamics.snapshot(),
            "inactive_phase_worlds": inactive_phase_worlds,
            "ambient_ship_radio": self.ambient_ship_radio.snapshot(),
            "ship_radio_service": self.ship_radio_service.snapshot(),
            "distress_dispatcher": {
                "world_seed": int(self.distress_dispatcher.world_seed),
                "interval_s": float(self.distress_dispatcher.interval_s),
                "last_slot": self.distress_dispatcher._last_slot,
                "events_emitted": int(self.distress_dispatcher.events_emitted),
                "decisions_applied": int(self.distress_dispatcher.decisions_applied),
            },
            "player_rescue_mission": self.player_rescue_manager.snapshot(),
            "ai_rescue_mission": self.ai_rescue_manager.snapshot(),
            "tow_escort": {"schema_version": 1, "escort": self.tow_escort.snapshot() if self.tow_escort else None},
            "radio_calls": self._career_encode(self.radio_calls),
            "pending_radio_calls": self._career_encode(self.pending_radio_calls),
            "broadcast_director": director_state, "radio_system": radio_state,
            "gut_book": gut_book_state, "rescue_operation": rescue_state, "crew_drills": drill_state,
            "crew": crew_state, "sailors": sailors, "longline": line, "catch": catch_state,
            "random_state": self._career_encode(random.getstate()),
        }

    @staticmethod
    def _career_tupleize(value):
        if isinstance(value, list):
            return tuple(Game._career_tupleize(v) for v in value)
        return value

    def _validate_career_snapshot(self, snapshot):
        if not isinstance(snapshot, dict) or int(snapshot.get("payload_schema_version", 0)) != 1:
            raise ValueError("unsupported career payload schema")
        for section in ("game_state", "world", "ship", "weather", "crew", "longline", "catch",
                        "world_weather_grid", "tow_escort", "broadcast_director", "radio_system",
                        "distress_dispatcher", "gut_book", "rescue_operation", "crew_drills"):
            if not isinstance(snapshot.get(section), dict):
                raise ValueError("career save section %s is missing or invalid" % section)
        for section in ("traffic_contacts",):
            if not isinstance(snapshot.get(section), dict):
                raise ValueError("career save section %s is missing or invalid" % section)
        # v13.2.07 saves predate the optional M11 ambient radio director; treat
        # an absent section as a clean initial state, but fully validate it if present.
        ambient_snapshot = snapshot.get("ambient_ship_radio")
        if ambient_snapshot is not None:
            AmbientShipRadioDirector(world_seed=1962).restore(ambient_snapshot)
        # v13.2.08 adds repeat-topic radio cooldowns; earlier career saves may omit it.
        radio_service_snapshot = snapshot.get("ship_radio_service")
        if radio_service_snapshot is not None:
            ShipRadioService(world_seed=1962).restore(radio_service_snapshot)
        relationship_snapshot = snapshot.get("relationship_dynamics")
        for section in ("sailors", "radio_calls", "pending_radio_calls"):
            if not isinstance(snapshot.get(section), list):
                raise ValueError("career save section %s is missing or invalid" % section)
        if not isinstance(snapshot.get("random_state"), (dict, list)):
            raise ValueError("career save random state is missing or invalid")
        gut_book = snapshot["gut_book"]
        gut_entries = gut_book.get("entries", [])
        if not isinstance(gut_entries, list) or len(gut_entries) > MAX_GUT_BOOK_ENTRIES:
            raise ValueError("invalid gut-book entries in career save")
        for entry in gut_entries:
            if not isinstance(entry, dict):
                raise ValueError("invalid gut-book entry in career save")
            try:
                int(entry["entry_id"])
                for number_field in ("elapsed", "skill", "x", "y", "confidence", "strength"):
                    number = float(entry[number_field])
                    if not math.isfinite(number):
                        raise ValueError("non-finite gut-book value in career save")
                if entry.get("hotspot_index") is not None and not isinstance(entry.get("hotspot_index"), int):
                    raise ValueError("invalid gut-book hotspot identity")
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("invalid gut-book entry in career save") from exc
        rescue = snapshot["rescue_operation"]
        rescue_modes = {"idle", "lifeline", "ship_turn", "boat_assembly", "boat_launching",
                        "boat_out", "boat_pickup", "boat_return", "recovering"}
        if rescue.get("mode", "idle") not in rescue_modes:
            raise ValueError("invalid rescue operation mode in career save")
        if not isinstance(rescue.get("hands", []), list) or len(rescue.get("hands", [])) > 10:
            raise ValueError("invalid rescue hands in career save")
        if any(not isinstance(name, str) for name in rescue.get("hands", [])):
            raise ValueError("invalid rescue hand identity in career save")
        try:
            assembly_elapsed = float(rescue.get("assembly_elapsed", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid rescue assembly timer") from exc
        if not math.isfinite(assembly_elapsed) or assembly_elapsed < 0:
            raise ValueError("invalid rescue assembly timer")
        boat = rescue.get("boat")
        if boat is not None:
            if not isinstance(boat, dict) or not isinstance(boat.get("fields"), dict):
                raise ValueError("invalid rescue boat snapshot")
            if not isinstance(boat.get("crew", []), list) or len(boat.get("crew", [])) > 10:
                raise ValueError("invalid rescue boat crew")
            if any(not isinstance(n, str) for n in boat.get("crew", [])):
                raise ValueError("invalid rescue boat crew identity")
        drills = snapshot["crew_drills"]
        for field in ("muster_expected", "muster_reports", "bucket_chain_hands"):
            names = drills.get(field, [])
            if not isinstance(names, list) or len(names) > 100 or any(not isinstance(n, str) for n in names):
                raise ValueError("invalid crew drill identity list: %s" % field)
        if not isinstance(drills.get("muster_unavailable", {}), dict):
            raise ValueError("invalid muster unavailable map")
        director = snapshot["broadcast_director"]
        pending_conversations = director.get("pending", [])
        if not isinstance(pending_conversations, list) or len(pending_conversations) > 500:
            raise ValueError("invalid broadcast queue in career save")
        def validate_conversation(raw):
            if raw is None:
                return
            if not isinstance(raw, dict):
                raise ValueError("invalid conversation in career save")
            turns = raw.get("turns", [])
            if not isinstance(turns, list) or len(turns) > 250:
                raise ValueError("invalid conversation turns in career save")
            try:
                priority = int(raw.get("priority", PRIORITY_LOW))
                sequence = int(raw.get("sequence", 0))
                cursor = int(raw.get("index", 0))
                timer = float(raw.get("timer", 0.0))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid conversation clock in career save") from exc
            if priority < PRIORITY_LOW or priority > PRIORITY_CRITICAL or sequence < 0:
                raise ValueError("invalid conversation priority or sequence")
            if cursor < 0 or cursor > len(turns) or not math.isfinite(timer) or timer < 0:
                raise ValueError("invalid conversation cursor or timer")
            for turn in turns:
                if not isinstance(turn, dict) or not isinstance(turn.get("speaker"), str) or not isinstance(turn.get("text"), str):
                    raise ValueError("invalid broadcast line in career save")
                try:
                    delay = float(turn.get("delay", 0.0))
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid broadcast delay in career save") from exc
                if not math.isfinite(delay) or delay < 0:
                    raise ValueError("invalid broadcast delay in career save")
        validate_conversation(director.get("active"))
        for raw_conversation in pending_conversations:
            validate_conversation(raw_conversation)
        if len(snapshot["radio_calls"]) > 500 or len(snapshot["pending_radio_calls"]) > 100:
            raise ValueError("radio queue exceeds career-save safety limit")
        for call in snapshot["radio_calls"]:
            if not isinstance(call, dict) or str(call.get("kind", "")) not in ("weather", "auction", "tow"):
                raise ValueError("invalid pending radio call in career save")
            try:
                timer = float(call.get("timer", -1.0))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid radio timer in career save") from exc
            if not math.isfinite(timer):
                raise ValueError("invalid radio timer in career save")
        if any(not isinstance(kind, str) or kind not in ("weather", "auction", "tow")
               for kind in snapshot["pending_radio_calls"]):
            raise ValueError("invalid queued radio request in career save")
        # Validate PRNG structure before any live field is changed.
        probe_rng = random.Random()
        probe_rng.setstate(self._career_tupleize(self._career_decode(snapshot["random_state"])))
        # Validate active phase + snapshots before changing any live state. Older saves
        # predate campaign_phase and therefore safely default to their Phase A snapshot.
        traffic_snapshot = snapshot["traffic_contacts"]
        active_phase = str(snapshot["game_state"].get(
            "campaign_phase", traffic_snapshot.get("phase", "A"))).upper()
        if active_phase not in ("A", "B"):
            raise ValueError("invalid saved campaign phase")
        snapshot_phase = str(traffic_snapshot.get("phase", "A")).upper()
        if snapshot_phase != active_phase:
            raise ValueError("campaign phase and traffic snapshot phase disagree")
        active_grid_probe = WeatherGrid.from_snapshot(snapshot["world_weather_grid"])
        if active_grid_probe.phase != active_phase:
            raise ValueError("campaign phase and weather-grid phase disagree")
        temp_world = TrafficWorld(
            world_seed=int(traffic_snapshot.get("world_seed", 1962)), active_cap=30, phase=active_phase)
        temp_world.restore_contacts(traffic_snapshot)
        if relationship_snapshot is not None:
            validated_relationships = RelationshipDynamics.from_snapshot(relationship_snapshot)
            # Baseline and trusted traffic values must agree to prevent old contacts
            # being reinterpreted as fresh gossip after a phase-aware load.
            for vessel_id, baseline_trust in validated_relationships.last_seen_trust.items():
                restored_ship = temp_world.by_id(vessel_id)
                if restored_ship is not None and abs(restored_ship.trust - baseline_trust) > 1e-6:
                    raise ValueError("relationship baseline disagrees with saved traffic trust for %s" % vessel_id)

        inactive_phase_worlds = snapshot.get("inactive_phase_worlds", {})
        if not isinstance(inactive_phase_worlds, dict) or len(inactive_phase_worlds) > 1:
            raise ValueError("invalid inactive phase-world mapping")
        for inactive_phase, phase_payload in inactive_phase_worlds.items():
            inactive_phase = str(inactive_phase).upper()
            if inactive_phase not in ("A", "B") or inactive_phase == active_phase:
                raise ValueError("invalid inactive campaign phase key")
            if not isinstance(phase_payload, dict):
                raise ValueError("invalid inactive phase-world section")
            phase_traffic = phase_payload.get("traffic_contacts")
            phase_weather = phase_payload.get("world_weather_grid")
            if not isinstance(phase_traffic, dict) or not isinstance(phase_weather, dict):
                raise ValueError("inactive phase-world snapshot is incomplete")
            if str(phase_traffic.get("phase", "A")).upper() != inactive_phase:
                raise ValueError("inactive phase and traffic snapshot disagree")
            inactive_grid_probe = WeatherGrid.from_snapshot(phase_weather)
            if inactive_grid_probe.phase != inactive_phase:
                raise ValueError("inactive phase and weather snapshot disagree")
            inactive_world_probe = TrafficWorld(
                world_seed=int(phase_traffic.get("world_seed", 1962)), active_cap=30,
                phase=inactive_phase)
            inactive_world_probe.restore_contacts(phase_traffic)
            inactive_relationships = phase_payload.get("relationship_dynamics")
            if inactive_relationships is not None:
                inactive_dynamics_probe = RelationshipDynamics.from_snapshot(inactive_relationships)
                for vessel_id, baseline_trust in inactive_dynamics_probe.last_seen_trust.items():
                    restored_ship = inactive_world_probe.by_id(vessel_id)
                    if restored_ship is not None and abs(restored_ship.trust - baseline_trust) > 1e-6:
                        raise ValueError("inactive relationship baseline disagrees for %s" % vessel_id)
        distress = snapshot["distress_dispatcher"]
        try:
            distress_seed = int(distress.get("world_seed", -1))
            distress_interval = float(distress.get("interval_s", 0.0))
            last_slot = distress.get("last_slot")
            events_emitted = int(distress.get("events_emitted", 0))
            decisions_applied = int(distress.get("decisions_applied", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid distress dispatcher state") from exc
        if (distress_seed != temp_world.world_seed or not math.isfinite(distress_interval)
                or distress_interval < 1.0 or events_emitted < 0 or decisions_applied < 0
                or (last_slot is not None and (not isinstance(last_slot, int) or last_slot < -1))):
            raise ValueError("invalid distress dispatcher state")
        from fishing_sim.world.persistence import restore_tow_escort_snapshot
        restore_tow_escort_snapshot(snapshot["tow_escort"])
        rescue_mission_snapshot = snapshot.get("player_rescue_mission")
        if rescue_mission_snapshot is not None:
            rescue_clean = PlayerRescueMissionManager.validate_snapshot(rescue_mission_snapshot)
            rescue_mission = rescue_clean.get("mission")
            if rescue_mission and rescue_mission.get("state") in ("en_route", "on_scene"):
                rescue_target = temp_world.by_id(rescue_mission["target_vessel_id"])
                if rescue_target is None:
                    raise ValueError("active rescue mission target is absent from traffic snapshot")
                if rescue_target.distress_decision != "assist" or not rescue_target.mayday_sent:
                    raise ValueError("active rescue mission target has no matching ASSIST decision")
                if rescue_target.distress_assistance_status not in ("en_route", "on_scene", "awaiting_dispatch"):
                    raise ValueError("active rescue mission and distress assistance status disagree")
        # M9 AI response state is optional for backward compatibility with earlier
        # v13.2.13 saves, but active missions must point at matching saved contacts.
        ai_rescue_snapshot = snapshot.get("ai_rescue_mission")
        if ai_rescue_snapshot is not None:
            ai_rescue_clean = AIDistressResponseManager.validate_snapshot(ai_rescue_snapshot)
            ai_mission = ai_rescue_clean.get("mission")
            if ai_mission and ai_mission.get("state") in ("en_route", "on_scene", "returning"):
                player_snapshot_clean = (PlayerRescueMissionManager.validate_snapshot(rescue_mission_snapshot)
                                         if rescue_mission_snapshot is not None else {"mission": None})
                active_player_mission = player_snapshot_clean.get("mission")
                active_player_target_id = (active_player_mission.get("target_vessel_id")
                                           if active_player_mission
                                           and active_player_mission.get("state") in ("en_route", "on_scene")
                                           else None)
                if active_player_target_id == ai_mission["target_vessel_id"]:
                    raise ValueError("player and AI rescue missions cannot claim the same distress target")
                ai_target = temp_world.by_id(ai_mission["target_vessel_id"])
                ai_responder = temp_world.by_id(ai_mission["responder_vessel_id"])
                if ai_target is None or ai_responder is None:
                    raise ValueError("active AI rescue mission contact is absent from traffic snapshot")
                if ai_responder.runtime_kind != "scheduled":
                    raise ValueError("AI rescue responder is not a scheduled fleet identity")
                if ai_mission["state"] in ("en_route", "on_scene"):
                    if (not ai_target.mayday_sent or ai_target.activity_override != TrafficActivity.DISTRESSED
                            or ai_target.position_override_nm is None):
                        raise ValueError("active AI rescue target has no matching frozen distress scene")
                    expected_status = "en_route" if ai_mission["state"] == "en_route" else "on_scene"
                    if ai_target.distress_assistance_status != expected_status:
                        raise ValueError("AI rescue mission and target status disagree")
                else:
                    if ai_target.distress_assistance_status != "completed":
                        raise ValueError("returning AI responder has no completed distress outcome")
                if ai_responder.position_override_nm is None or ai_responder.activity_override is None:
                    raise ValueError("active AI rescue responder has no physical route override")
        if not isinstance(snapshot.get("sailors"), list) or len(snapshot["sailors"]) > 100:
            raise ValueError("invalid saved crew roster")
        sailor_entries = snapshot["sailors"]
        if any(not isinstance(entry, dict) or not isinstance(entry.get("name"), str)
               or not entry.get("name", "").strip() for entry in sailor_entries):
            raise ValueError("invalid sailor identity in career save")
        sailor_names = [entry["name"] for entry in sailor_entries]
        if len(set(sailor_names)) != len(sailor_names):
            raise ValueError("duplicate sailor identity in career save")
        saved_names = set(sailor_names)
        def validate_sailor_ref(name, field):
            if name is not None and (not isinstance(name, str) or name not in saved_names):
                raise ValueError("unknown sailor reference in career save: %s" % field)
        for entry in sailor_entries:
            refs = entry.get("references", {})
            if not isinstance(refs, dict):
                raise ValueError("invalid sailor references in career save")
            for ref_field in ("lifeline", "rescue_target", "alert_target"):
                validate_sailor_ref(refs.get(ref_field), "sailor." + ref_field)
            ladder = entry.get("ladder_state")
            if ladder is not None:
                if not isinstance(ladder, dict):
                    raise ValueError("invalid ladder state in career save")
                try:
                    link_index = int(ladder.get("link_index", -1))
                    climb_t = float(ladder.get("t", -1.0))
                    target_level = int(ladder.get("to", -1))
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid ladder state in career save") from exc
                def is_encoded_vector(raw):
                    if not isinstance(raw, dict) or set(raw) != {"__vector2__"}:
                        return False
                    pair = raw.get("__vector2__")
                    if not isinstance(pair, list) or len(pair) != 2:
                        return False
                    try:
                        return all(math.isfinite(float(v)) for v in pair)
                    except (TypeError, ValueError):
                        return False
                if (link_index < 0 or link_index >= len(self.ship.links)
                        or not math.isfinite(climb_t) or climb_t < 0 or target_level < 0
                        or not is_encoded_vector(ladder.get("from"))
                        or not is_encoded_vector(ladder.get("dest"))):
                    raise ValueError("invalid ladder state in career save")
        rescue = snapshot["rescue_operation"]
        for ref_field in ("passenger", "engineer"):
            validate_sailor_ref(rescue.get(ref_field), "rescue." + ref_field)
        for name in rescue.get("hands", []):
            validate_sailor_ref(name, "rescue.hands")
        if rescue.get("boat") is not None:
            boat = rescue["boat"]
            for ref_field in ("target", "passenger"):
                validate_sailor_ref(boat.get(ref_field), "rescue.boat." + ref_field)
            for name in boat.get("crew", []):
                validate_sailor_ref(name, "rescue.boat.crew")
            phase = boat.get("fields", {}).get("phase")
            if phase not in ("launching", "out", "pickup", "return"):
                raise ValueError("invalid rescue boat phase in career save")
            route = boat.get("fields", {}).get("route", [])
            if isinstance(route, list) and len(route) > 500:
                raise ValueError("rescue route exceeds career-save safety limit")
        for field in ("alarm_target",):
            validate_sailor_ref(snapshot["crew"].get(field), "crew." + field)
        for field in ("unseen_overboard",):
            refs = snapshot["crew"].get(field, [])
            if not isinstance(refs, list) or any(not isinstance(n, str) or n not in saved_names for n in refs):
                raise ValueError("invalid sailor identity list in crew save: %s" % field)
        timers = snapshot["crew"].get("sighting_timers", {})
        if not isinstance(timers, dict):
            raise ValueError("invalid sighting timers in career save")
        for name, timer in timers.items():
            validate_sailor_ref(name, "crew.sighting_timers")
            value = float(timer)
            if not math.isfinite(value) or value < 0:
                raise ValueError("invalid sighting timer in career save")
        for field in ("muster_expected", "muster_reports", "bucket_chain_hands"):
            for name in snapshot["crew_drills"].get(field, []):
                validate_sailor_ref(name, "crew_drills." + field)
        if not isinstance(snapshot["longline"].get("pts", []), list) or len(snapshot["longline"].get("pts", [])) > 1000:
            raise ValueError("invalid saved longline particle list")
        # Recursively decode to validate every scalar/vector and reject NaN/Infinity.
        self._career_decode(snapshot)

    def _restore_career_snapshot(self, snapshot):
        self._validate_career_snapshot(snapshot)
        data = self._career_decode(snapshot)
        # Old saves have no campaign_phase; use the phase of their traffic snapshot,
        # then fall back to Phase A. Set this before any coordinate conversion runs.
        traffic_phase = str(data.get("traffic_contacts", {}).get("phase", "A")).upper()
        saved_phase = str(data.get("game_state", {}).get("campaign_phase", traffic_phase)).upper()
        if saved_phase not in ("A", "B"):
            raise ValueError("unsupported campaign phase in career save")
        self.campaign_phase = saved_phase
        for name, value in data["game_state"].items():
            if name in self.CAREER_GAME_FIELDS and hasattr(self, name):
                setattr(self, name, value)

        # World positions/navigation are restored before weather so date-dependent outlooks are correct.
        wstate = data["world"]
        for name, value in wstate.items():
            if name in self.CAREER_WORLD_SCALARS or name in self.CAREER_WORLD_VECTORS or name == "route_waypoints":
                if hasattr(self.world, name):
                    setattr(self.world, name, value)
        from fishing_sim.systems.hotspots import Hotspot
        self.world.hotspots = []
        for raw in wstate.get("hotspots", []):
            h = Hotspot(raw["x"], raw["y"], raw["species"], raw.get("strength", 1.0),
                        raw.get("radius", 1000.0), raw.get("life", 600.0), raw.get("drift_x", 0.0),
                        raw.get("drift_y", 0.0), raw.get("phase", 0.0))
            h.age = float(raw.get("age", 0.0)); h.strength_now = float(raw.get("strength_now", h.strength))
            h.detected_by = raw.get("detected_by"); h.detected_at = raw.get("detected_at")
            self.world.hotspots.append(h)
        from fishing_sim.systems.fishing_reports import FishingSpotReport
        self.world.fishing_reports = [FishingSpotReport(**raw) for raw in wstate.get("fishing_reports", [])]

        for name, value in data["ship"].items():
            if name in self.CAREER_SHIP_FIELDS and hasattr(self.ship, name):
                setattr(self.ship, name, value)
        weather = data["weather"]
        for name, value in weather.items():
            if name in ("kind", "cloud", "rain", "fog", "wind", "storm", "wind_dir", "hold",
                        "flash", "bolt", "bolt_t", "next_bolt", "pending"):
                setattr(self.weather, name, value)
        # Forecast selection is derived from restored date/condition, not from a stale constructor date.
        self.weather.outlook_date = self.world.calendar_date()
        self.weather.day_outlook = forecast_for_date(self.weather.outlook_date)
        from fishing_sim.world.persistence import restore_tow_escort_snapshot
        self.tow_escort = restore_tow_escort_snapshot(data["tow_escort"])
        # Rebuild the active phase schedule fleet rather than applying sparse deltas
        # over a later live session. WeatherGrid.from_snapshot constructs the matching
        # phase directly, so loading A while currently in B (or vice versa) is safe.
        traffic_data = data["traffic_contacts"]
        saved_phase = str(data.get("game_state", {}).get(
            "campaign_phase", traffic_data.get("phase", "A"))).upper()
        old_active_cap = int(getattr(getattr(self.traffic_world, "lod", None), "active_cap", 30))
        date = self.world.calendar_date()
        active_world = TrafficWorld(
            world_seed=int(traffic_data.get("world_seed", 1962)), active_cap=old_active_cap,
            phase=saved_phase)
        active_world.advance(
            self.world.time, focus_nm=self._player_position_nm_for_phase(saved_phase), month=date.month,
            day=date.day, hour=self.world.hour(), force=True)
        active_grid = WeatherGrid.from_snapshot(data["world_weather_grid"])
        self.campaign_phase = saved_phase
        self.traffic_world = active_world
        self.world_weather_grid = active_grid
        self._phase_traffic_worlds = {saved_phase: active_world}
        self._phase_weather_grids = {saved_phase: active_grid}
        self._phase_relationship_dynamics = {}
        self._tow_escort_synced_id = None
        self._sync_tow_escort_world_entity()
        # Register the runtime launch first so its saved contact delta is not dropped.
        self.traffic_world.restore_contacts(traffic_data)
        # M9: restore the physical rescue commitment after its target contact exists.
        # Older career saves without this optional section simply have no active mission.
        self.player_rescue_manager = PlayerRescueMissionManager.from_snapshot(
            data.get("player_rescue_mission"))
        self.ai_rescue_manager = AIDistressResponseManager.from_snapshot(data.get("ai_rescue_mission"))
        restored_rescue = self.player_rescue_manager.mission
        if restored_rescue and self.player_rescue_manager.has_active_mission:
            self.traffic_world.promote_rescue_contact(restored_rescue["target_vessel_id"])
        restored_ai = self.ai_rescue_manager.mission
        if restored_ai and self.ai_rescue_manager.has_active_mission:
            self.traffic_world.promote_rescue_contact(restored_ai["target_vessel_id"])
            self.traffic_world.promote_rescue_contact(restored_ai["responder_vessel_id"])
        # Apply any restored physical overrides immediately so chart/index positions
        # and a resumed rescue controller agree before the next regular traffic tick.
        restore_date = self.world.calendar_date()
        self.traffic_world.advance(
            self.world.time, focus_nm=self._player_position_nm_for_phase(saved_phase),
            month=restore_date.month, day=restore_date.day, hour=self.world.hour(), force=True)
        relationship_snapshot = data.get("relationship_dynamics")
        self.relationship_dynamics = RelationshipDynamics(world_seed=1962)
        if relationship_snapshot is not None:
            self.relationship_dynamics.restore(relationship_snapshot)
        else:
            # v13.2.08 and older saves have no social baseline. Seed it from restored
            # trust values rather than treating all historical relationships as new news.
            self.relationship_dynamics.seed_baseline(self.traffic_world, self.world.time)
        self._phase_relationship_dynamics[saved_phase] = self.relationship_dynamics

        # Restore any other phase the career previously visited. Its fixed schedules
        # are regenerated at the saved game time before contact deltas are applied.
        for inactive_phase, phase_payload in data.get("inactive_phase_worlds", {}).items():
            phase = str(inactive_phase).upper()
            if phase == saved_phase or phase not in ("A", "B"):
                continue
            phase_traffic_data = phase_payload["traffic_contacts"]
            phase_world = TrafficWorld(
                world_seed=int(phase_traffic_data.get("world_seed", 1962)),
                active_cap=old_active_cap, phase=phase)
            phase_world.advance(
                self.world.time, focus_nm=self._player_position_nm_for_phase(phase), month=date.month,
                day=date.day, hour=self.world.hour(), force=True)
            phase_world.restore_contacts(phase_traffic_data)
            phase_grid = WeatherGrid.from_snapshot(phase_payload["world_weather_grid"])
            phase_dynamics_snapshot = phase_payload.get("relationship_dynamics")
            phase_dynamics = RelationshipDynamics(world_seed=1962)
            if phase_dynamics_snapshot is not None:
                phase_dynamics.restore(phase_dynamics_snapshot)
            else:
                phase_dynamics.seed_baseline(phase_world, self.world.time)
            self._phase_traffic_worlds[phase] = phase_world
            self._phase_weather_grids[phase] = phase_grid
            self._phase_relationship_dynamics[phase] = phase_dynamics
        distress_data = data["distress_dispatcher"]
        self.distress_dispatcher = DistressDispatcher(
            world_seed=int(distress_data["world_seed"]), interval_s=float(distress_data["interval_s"]))
        self.distress_dispatcher._last_slot = distress_data.get("last_slot")
        self.distress_dispatcher.events_emitted = int(distress_data.get("events_emitted", 0))
        self.distress_dispatcher.decisions_applied = int(distress_data.get("decisions_applied", 0))
        ambient_snapshot = data.get("ambient_ship_radio")
        self.ambient_ship_radio = AmbientShipRadioDirector(world_seed=1962)
        if ambient_snapshot is not None:
            self.ambient_ship_radio.restore(ambient_snapshot)
        radio_service_snapshot = data.get("ship_radio_service")
        self.ship_radio_service = ShipRadioService(world_seed=1962)
        if radio_service_snapshot is not None:
            self.ship_radio_service.restore(radio_service_snapshot)

        # Restore the named roster by identity. Transient cross-object assignments (a hand's
        # current fish-fetch target, for example) are cleared and the crew AI reacquires them.
        existing = {s.name: s for s in self.sailors}
        restored_sailors = []
        for entry in data["sailors"]:
            name = str(entry.get("name", "")).strip()
            if not name:
                raise ValueError("saved sailor has no name")
            role = int(entry.get("role", Sailor.DECKHAND))
            if role not in (Sailor.DECKHAND, Sailor.VETERAN, Sailor.CAPTAIN):
                raise ValueError("invalid saved sailor role")
            sailor = existing.get(name) or Sailor(self, name, role, V(0, 0))
            sailor.role = role
            for field in self.CAREER_SAILOR_FIELDS + self.CAREER_SAILOR_VECTORS:
                if field in entry and hasattr(sailor, field):
                    value = entry[field]
                    if field in ("jacket", "hair", "skin") and value is not None:
                        value = tuple(value)
                    setattr(sailor, field, value)
            sailor.path = entry.get("path", [])
            sailor.carry = [self._career_unpack_fish(f) for f in entry.get("carry", []) if f is not None]
            sailor.item = None; sailor.dress_fish = None; sailor.chat_partner = None
            sailor.clean_patch = None; sailor.lifeline = None; sailor.rescue_target = None
            sailor.alert_target = None; sailor.ladder = None
            restored_sailors.append(sailor)
        if restored_sailors:
            self.sailors = restored_sailors
        by_name = {s.name: s for s in self.sailors}
        for entry in data["sailors"]:
            sailor = by_name.get(entry.get("name"))
            if sailor is None:
                continue
            refs = entry.get("references", {})
            sailor.lifeline = by_name.get(refs.get("lifeline"))
            sailor.rescue_target = by_name.get(refs.get("rescue_target"))
            sailor.alert_target = by_name.get(refs.get("alert_target"))
            # Rebind climbing hands to the matching stable Link object in this ship.
            ladder = entry.get("ladder_state")
            if isinstance(ladder, dict):
                link_index = int(ladder.get("link_index", -1))
                if 0 <= link_index < len(self.ship.links):
                    sailor.ladder = {
                        "link": self.ship.links[link_index], "to": int(ladder["to"]),
                        "t": float(ladder["t"]), "from": ladder["from"],
                        "dest": ladder["dest"], "flipped": bool(ladder.get("flipped", False)),
                    }
        for hotspot in self.world.hotspots:
            detected_by = getattr(hotspot, "detected_by", None)
            if isinstance(detected_by, str) and detected_by in by_name:
                hotspot.detected_by = by_name[detected_by]
        cstate = data["crew"]
        self.crew.status = dict(cstate.get("status", {}))
        self.crew.known_lost = set(cstate.get("known_lost", []))
        self.crew.log = cstate.get("log", [])[-600:]
        self.crew.catch_count = int(cstate.get("catch_count", 0))
        self.crew.catch_value = float(cstate.get("catch_value", 0.0))
        self.crew.alarm_target = by_name.get(cstate.get("alarm_target"))
        self.crew.unseen_overboard = {by_name[n] for n in cstate.get("unseen_overboard", []) if n in by_name}
        self.crew.sighting_timers = {by_name[n]: float(t) for n, t in cstate.get("sighting_timers", {}).items()
                                     if n in by_name}
        self.crew_log_entries = cstate.get("crew_log_entries", [])[-600:]
        self.radio_log_entries = cstate.get("radio_log_entries", [])[-600:]
        self.radio_transcript_queue = cstate.get("radio_transcript_queue", [])[-100:]
        self.radio_transcript_priority = int(cstate.get("radio_transcript_priority", 0))
        self.radio_bubble_text = str(cstate.get("radio_bubble_text", ""))
        self.radio_bubble_t = float(cstate.get("radio_bubble_t", 0.0))
        self.radio_bubble_speaker = str(cstate.get("radio_bubble_speaker", "COAST / FLEET RADIO"))
        self.radio_ui_histories = cstate.get("radio_ui_histories", {})
        self.radio_ui_active_end = cstate.get("radio_ui_active_end", {})
        self.radio_ui_selected_ship_id = cstate.get("radio_ui_selected_ship_id")
        self.radio_ui_status = str(cstate.get("radio_ui_status", "Career loaded."))
        self.helm_operator = by_name.get(cstate.get("helm_operator"))
        self.relief_helmsman = by_name.get(cstate.get("relief_helmsman"))
        self.radio_operator = by_name.get(cstate.get("radio_operator"))
        rescue_data = data.get("rescue_operation", {})
        self.mob_rescue_mode = str(rescue_data.get("mode", "idle"))
        self.rescue_boat_assembly_elapsed = float(rescue_data.get("assembly_elapsed", 0.0))
        self.rescue_boat_hands = {by_name[n] for n in rescue_data.get("hands", []) if n in by_name}
        self.rescue_boat_passenger = by_name.get(rescue_data.get("passenger"))
        self.rescue_engineer = by_name.get(rescue_data.get("engineer"))
        raw_boat = rescue_data.get("boat")
        if raw_boat is None:
            self.rescue_boat_state = None
        else:
            self.rescue_boat_state = dict(raw_boat.get("fields", {}))
            self.rescue_boat_state["target"] = by_name.get(raw_boat.get("target"))
            self.rescue_boat_state["crew"] = [by_name[n] for n in raw_boat.get("crew", []) if n in by_name]
            self.rescue_boat_state["passenger"] = by_name.get(raw_boat.get("passenger"))
        drill_data = data.get("crew_drills", {})
        self.muster_expected = {by_name[n] for n in drill_data.get("muster_expected", []) if n in by_name}
        self.muster_reports = {by_name[n] for n in drill_data.get("muster_reports", []) if n in by_name}
        self.muster_unavailable = dict(drill_data.get("muster_unavailable", {}))
        self.bucket_chain_hands = {by_name[n] for n in drill_data.get("bucket_chain_hands", []) if n in by_name}
        self.radio_ui_open = False; self.radio_ui_contacts = []; self.radio_ui_hitboxes = {}
        self.radio_calls = data.get("radio_calls", [])
        self.pending_radio_calls = data.get("pending_radio_calls", [])
        self.radio_message = str(cstate.get("radio_message", ""))
        self.radio_message_t = float(cstate.get("radio_message_t", 0.0))
        for name, value in data.get("radio_system", {}).items():
            if name in ("frequency_khz", "signal_quality", "last_bulletin", "tow_called", "broadcast_timer",
                        "conversation_timer", "distress_checked", "panpan_checked", "broadcasts_received",
                        "broadcasts_missed") and hasattr(self.radio, name):
                setattr(self.radio, name, value)
        director_data = data.get("broadcast_director", {})
        def unpack_conversation(raw):
            if raw is None:
                return None
            turns = tuple(BroadcastTurn(max(0.0, float(t["delay"])), str(t["speaker"]),
                                        str(t["text"]), str(t.get("channel", "radio")))
                          for t in raw.get("turns", []))
            conv = BroadcastConversation(turns, int(raw.get("priority", PRIORITY_LOW)),
                                         str(raw.get("source", "broadcast")), int(raw.get("sequence", 0)),
                                         int(raw.get("index", 0)), max(0.0, float(raw.get("timer", 0.0))))
            if conv.index < 0 or conv.index > len(conv.turns):
                raise ValueError("invalid broadcast cursor in career save")
            return conv
        self.broadcast_director = BroadcastDirector()
        self.broadcast_director.active = unpack_conversation(director_data.get("active"))
        self.broadcast_director.pending = [unpack_conversation(raw) for raw in director_data.get("pending", [])]
        self.broadcast_director.pending = [conv for conv in self.broadcast_director.pending if conv is not None]
        self.broadcast_director._sequence = int(director_data.get("sequence", 0))
        self.broadcast_director.interrupted_count = int(director_data.get("interrupted_count", 0))
        self.broadcast_director.completed_count = int(director_data.get("completed_count", 0))
        self.broadcast_director.emitted_count = int(director_data.get("emitted_count", 0))

        # Restore the notebook's historical fishing-school entries and reconnect only
        # references to live schools; expired schools remain historical records.
        gut_book_state = data.get("gut_book", {})
        self.gut_book_entries = []
        for raw in gut_book_state.get("entries", []):
            if not isinstance(raw, dict):
                raise ValueError("invalid gut-book entry in career save")
            hotspot_index = raw.get("hotspot_index")
            hotspot_ref = (self.world.hotspots[hotspot_index]
                           if isinstance(hotspot_index, int) and 0 <= hotspot_index < len(self.world.hotspots)
                           else None)
            self.gut_book_entries.append(GutBookEntry(
                entry_id=int(raw["entry_id"]), date=str(raw["date"]), clock=str(raw["clock"]),
                elapsed=float(raw["elapsed"]), sailor=str(raw["sailor"]), skill=float(raw["skill"]),
                species_guess=str(raw["species_guess"]), x=float(raw["x"]), y=float(raw["y"]),
                confidence=float(raw["confidence"]), strength=float(raw["strength"]),
                hotspot_ref=hotspot_ref))
        self.gut_book_entries = self.gut_book_entries[-MAX_GUT_BOOK_ENTRIES:]
        self.next_gut_book_id = max(int(gut_book_state.get("next_id", 1)),
                                    max((entry.entry_id for entry in self.gut_book_entries), default=0) + 1)

        # Restore fish inventories and deck objects with proper Python types.
        catch_state = data["catch"]
        self.hold = [self._career_unpack_fish(f) for f in catch_state.get("hold", []) if f is not None]
        self.table.raw = [self._career_unpack_fish(f) for f in catch_state.get("table", []) if f is not None]
        self.items = []
        for raw in catch_state.get("items", []):
            item = FishItem(raw.get("pos", V(0, 0)), self._career_unpack_fish(raw["fish"]))
            for field in ("angle", "thrash_timer", "thrash_anim", "thrash_count"):
                if field in raw: setattr(item, field, raw[field])
            self.items.append(item)
        self.patches = []
        for raw in catch_state.get("patches", []):
            patch = Patch(raw.get("pos", V(0, 0)), raw.get("kind", "slime"), raw.get("radius"))
            for field in ("grip", "life", "age", "cleaning"):
                if field in raw: setattr(patch, field, raw[field])
            if "shape" in raw: patch.shape = raw["shape"]
            self.patches.append(patch)
        self.table_blood = float(catch_state.get("table_blood", 0.0))

        line_data = data["longline"]
        for name, value in line_data.items():
            if name in self.CAREER_LINE_FIELDS and hasattr(self.line, name):
                setattr(self.line, name, value)
        self.line.pts = []
        for raw in line_data.get("pts", []):
            if not isinstance(raw, dict):
                raise ValueError("invalid longline point in career save")
            self.line.pts.append(dict(raw))
        by_name = {s.name: s for s in self.sailors}
        raw_claims = line_data.get("claims_by_role", {})
        self.line.claims = {k: [by_name[n] for n in raw_claims.get(k, []) if n in by_name]
                            for k in self.line.CAP}
        target_index = line_data.get("auto_hotspot_target_index")
        self.line.auto_hotspot_target = (self.world.hotspots[target_index]
            if isinstance(target_index, int) and 0 <= target_index < len(self.world.hotspots) else None)
        self.line.auto_hotspot_destination = line_data.get("auto_hotspot_destination")
        for s in self.sailors:
            s.item = None
            for carry_item in s.carry:
                pass
        self.line.fight = None
        fight_data = line_data.get("fight")
        if isinstance(fight_data, dict):
            hook_index = fight_data.get("hook_index")
            if isinstance(hook_index, int) and 0 <= hook_index < len(self.line.pts):
                fight = Fight(self.line.pts[hook_index])
                for name in ("strength", "stamina", "time", "rough", "tension", "seen", "drag",
                             "slack_t", "strain_t", "over_t", "phase", "run_t", "run_left", "run_f", "manual"):
                    if name in fight_data: setattr(fight, name, fight_data[name])
                self.line.fight = fight
        gaff_data = line_data.get("gaff")
        self.line.gaff = None
        if isinstance(gaff_data, dict):
            hook_index = gaff_data.get("hook_index")
            if isinstance(hook_index, int) and 0 <= hook_index < len(self.line.pts):
                self.line.gaff = {k: v for k, v in gaff_data.items() if k != "hook_index"}
                self.line.gaff["hook"] = self.line.pts[hook_index]

        # Wave time/phase belongs to the sea simulation rather than the render cache.
        wave_state = data.get("world_waves", {})
        for name in ("strength", "base_angle", "time"):
            if name in wave_state:
                setattr(self.world.waves, name, float(wave_state[name]))

        # Rebuild derived caches/claims instead of loading render buffers or object references.
        self.follow_birds = []
        self.seabird_flocks = {}
        self._world_background_cache = None; self._ship_static_cache = None
        self._chart_base_surface = None; self._chart_transform = None
        self._ui_surface_cache.clear()
        self.last_ship_pos_for_teleport_check = V(self.world.ship_pos)
        self.last_mayday_source_id = cstate.get("last_mayday_source_id", self.last_mayday_source_id)
        self._refresh_hire_candidates()
        self._update_station_roles(0.0)
        # Restore global randomness after reconstruction and all derived-state refreshes.
        rng_state = self._career_tupleize(self._career_decode(snapshot["random_state"]))
        random.setstate(rng_state)

    def save_career(self):
        """Write an atomic versioned career save (Ctrl+S)."""
        try:
            payload = self._career_snapshot()
            envelope = build_career_save_envelope(payload, "13.2.13")
            target = Path(__file__).resolve().parents[2] / "saves" / "career_v13_2.json"
            atomic_write_career_save(target, envelope, keep_backup=True)
            self.crew.say("Career saved. Last-good backup kept when available.")
            self.record_log_entry("Career save written: %s" % target)
            return True
        except Exception as exc:
            get_logger().exception("Career save failed")
            self.crew.say("Career save failed: %s" % exc)
            return False

    def load_career(self):
        """Restore a versioned career; if primary is corrupt, try its last-good backup."""
        target = Path(__file__).resolve().parents[2] / "saves" / "career_v13_2.json"
        try:
            envelope, used_backup = read_career_save_envelope(target, allow_backup=True)
            payload = validate_career_save_envelope(envelope)
            self._validate_career_snapshot(payload)
            # Keep the current voyage intact if a cross-system reconstruction error
            # escapes validation. Restore from an in-memory snapshot on failure.
            before = self._career_snapshot()
            try:
                self._restore_career_snapshot(payload)
            except Exception:
                get_logger().exception("Career restore failed; attempting to roll back live state")
                try:
                    self._restore_career_snapshot(before)
                except Exception:
                    get_logger().exception("Career restore rollback failed")
                raise
            source = "backup" if used_backup else "career save"
            self.crew.say("Loaded %s from %s." % (envelope.get("game_version", "older version"), source))
            self.record_log_entry("Career restored from %s: %s" % (source, target))
            return True
        except FileNotFoundError:
            self.crew.say("No saved career yet. Press Ctrl+S to save this voyage.")
        except Exception as exc:
            get_logger().exception("Career load failed")
            self.crew.say("Career load failed; current voyage left unchanged where possible: %s" % exc)
        return False

    def resize(self, w, h):
        """The window changed size: re-centre the view and rebuild everything sized to the screen."""
        global W, H, CENTER
        self._win = (w, h)
        W, H = max(w, 320), max(h, 240)
        CENTER = V(W / 2, H / 2)
        self.ov_w = pygame.Surface((W, H), pygame.SRCALPHA)
        self.ov_d = pygame.Surface((W, H), pygame.SRCALPHA)
        self.hotspot_overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        self.money_hud_rect = pygame.Rect(W - 220, 10, 210, 44)
        self.profile_rect = pygame.Rect(W - 250, 82, 240, 110)
        self.night_layer = pygame.Surface((W, H), pygame.SRCALPHA)
        self.wx_tint = pygame.Surface((W, H))
        self.wx_flash = pygame.Surface((W, H))
        self.wx_flash.fill((232, 238, 255))
        self._fog_cache = {}
        # Screen-sized cached layers must never survive a resize.
        if hasattr(self, "_ui_surface_cache"):
            self._ui_surface_cache.clear()
            self._profile_background_cache.clear()
            self._world_background_cache = None
            self._world_background_target = pygame.Surface((W, H)).convert()
            self._world_background_age = 1.0
            self._world_background_state = None
            self._ship_static_cache = None
            self._ship_static_cache_rect = None
            self._ship_static_target_surface = pygame.Surface((W, H), pygame.SRCALPHA).convert_alpha()
            self._ship_static_cache_age = 1.0
            self._ship_static_cache_state = None
        # Rebuild cached cartography only after a chart viewport resize.
        self._chart_base_surface = None
        self._chart_cache_size = None
        self._chart_transform = None
        self._chart_dim_surface = None
        self._chart_map_rect = None
        self._chart_outer_rect = None
        # HUD geometry: keep a clear play area of >=600px or 70% of the width (whichever is
        # larger) in the centre of the screen. The two side columns share whatever is left,
        # clamped to a readable range, and every HUD panel is sized off these two numbers so
        # nothing drifts out of alignment as the window is resized.
        center_min = max(600, int(W * 0.70))
        avail = max(0, W - center_min - 36)            # 36 = outer margins + the centre gutter
        col = int(clamp(avail / 2, 190, 320))
        self.hud_left_w = col
        self.hud_right_w = col

    # --- coordinate frames
    def S(self, d):
        """Water / world frame: the sea does not rock."""
        return CENTER + V(d) * self.zoom

    def SS(self, d):
        """Ship frame: includes the rocking (a little roll, pitch and sway from the deck tilt)."""
        sl = self.ship.slope
        v = V(d[0] * (1 + 0.012 * sl.x), d[1] * (1 - 0.02 * abs(sl.y))).rotate_rad(self.rock_ang)
        return CENTER + (v + self.rock_shift) * self.zoom

    def unSS(self, px):
        sl = self.ship.slope
        v = ((V(px) - CENTER) / self.zoom - self.rock_shift).rotate_rad(-self.rock_ang)
        return V(v.x / (1 + 0.012 * sl.x), v.y / (1 - 0.02 * abs(sl.y)))

    def text(self, s, pos, color=(240, 240, 240)):
        self.screen.blit(self.font.render(s, True, (0, 0, 0)), (pos[0] + 1, pos[1] + 1))
        self.screen.blit(self.font.render(s, True, color), pos)

    def _fit(self, s, maxw):
        """Truncate s with an ellipsis so it never overflows a panel column."""
        if self.font.size(s)[0] <= maxw:
            return s
        while s and self.font.size(s + "...")[0] > maxw:
            s = s[:-1]
        return (s.rstrip() + "...") if s else "..."

    def _cached_panel_surface(self, size, fill, border=None, border_width=1, radius=0):
        """Return a bounded-cache reusable transparent panel surface."""
        size = (max(1, int(size[0])), max(1, int(size[1])))
        fill = tuple(fill)
        border = None if border is None else tuple(border)
        key = (size, fill, border, int(border_width), int(radius))
        cache = self._ui_surface_cache
        found = cache.get(key)
        if found is not None:
            cache.move_to_end(key)
            return found
        surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
        surface.fill((0, 0, 0, 0))
        pygame.draw.rect(surface, fill, surface.get_rect(), border_radius=max(0, int(radius)))
        if border is not None:
            pygame.draw.rect(surface, border, surface.get_rect(), max(1, int(border_width)),
                             border_radius=max(0, int(radius)))
        cache[key] = surface
        if len(cache) > 32:
            cache.popitem(last=False)
        return surface

    def panel(self, rect, lines, header=None, header_color=GOLD):
        """A HUD cluster: a semi-transparent dark card with a fixed-pitch stack of text lines.

        The card's height comes from rect (set by the caller from a fixed line count), and
        every line is drawn at a fixed y-offset and clipped to the card, so dynamic text
        (names, numbers, radio chatter) can never push one line into another or spill into
        a neighbouring panel.
        """
        bg = self._cached_panel_surface((rect.w, rect.h), self.PANEL_BG,
                                        border=(255, 255, 255, 30), border_width=1)
        self.screen.blit(bg, rect.topleft)
        pygame.draw.rect(self.screen, self.PANEL_BORDER, rect, 1)
        yy = rect.y + self.PAD
        if header:
            self.text(self._fit(header, rect.w - 2 * self.PAD), (rect.x + self.PAD, yy), header_color)
            yy += self.HEAD_H
        clip = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-2, -2))
        for ln in lines:
            self.text(self._fit(ln, rect.w - 2 * self.PAD), (rect.x + self.PAD, yy))
            yy += self.LINE_H
        self.screen.set_clip(clip)

    def panel_rect(self, x, y, w, n_lines, header=None):
        h = 2 * self.PAD + n_lines * self.LINE_H + (self.HEAD_H if header else 0)
        return pygame.Rect(x, y, w, h)

    # --- fish handling queries used by the crew AI
    def engine_running(self):
        return self._engine_on

    def engine_status(self):
        """Readable status for the HUD and engine-room cutaway."""
        if not self.engine_ok:
            return "TRIPPED"
        return "RUNNING" if self._engine_on else "STOPPED"

    def _reserve_bunk_index(self, sailor):
        """Reserve one unique bunk index for a resting sailor for the duration of the rest."""
        centres = getattr(self.ship, "bunk_centres", ())
        occupied = {
            other.rest_bunk_index for other in self.sailors
            if other is not sailor and other.mode == Sailor.ABOARD
            and other.task == "rest" and other.rest_bunk_index is not None
        }
        idx = getattr(sailor, "rest_bunk_index", None)
        if idx is None or idx in occupied or not (0 <= idx < len(centres)):
            try:
                preferred = self.sailors.index(sailor) % max(1, len(centres))
            except ValueError:
                preferred = 0
            order = [(preferred + i) % len(centres) for i in range(len(centres))] if centres else []
            idx = next((i for i in order if i not in occupied), preferred)
            sailor.rest_bunk_index = idx
        return idx

    def rest_bunk_for(self, sailor):
        """Return the centre of this sailor's reserved bed (the actual sleeping position)."""
        centres = getattr(self.ship, "bunk_centres", ())
        if not centres:
            return V(self.ship.markers["rest_spot"])
        idx = self._reserve_bunk_index(sailor)
        return V(centres[idx])

    def rest_bunk_approach_for(self, sailor):
        """Return the collision-free point in the centre aisle used to approach a bunk."""
        stands = getattr(self.ship, "bunk_stands", ())
        if not stands:
            return V(self.ship.markers["rest_spot"])
        idx = self._reserve_bunk_index(sailor)
        return V(stands[idx])

    def update_engine_room(self, dt, engineer):
        """Wear the diesel's three service points down at sea and let an engineer repair them.

        An engineer must physically reach the below-deck engine station. Each service
        action takes a short check interval and restores one neglected component.
        """
        sea = clamp(self.world.waves.strength, 0.0, 1.0)
        demand = (self.world.throttle > 0.025 or self.world.speed > 25.0
                  or self.world.destination is not None or self.world.rescue_to is not None
                  or self.world.dock_state is not None
                  or self.line.phase in (Longline.SETTING, Longline.HAULING))
        # The diesel keeps turning while demanded even if its watchkeeper leaves; the
        # absence of an engineer means the checks are neglected, not an instant shutdown.
        running = self.fuel > 0 and self.engine_ok and demand
        staffed = bool(engineer is not None and engineer.mode == Sailor.ABOARD and engineer.at_engine)
        if running:
            self.engine_runtime += dt
            load = clamp(0.25 + 0.45 * self.world.throttle
                         + 0.25 * (self.world.speed / max(1.0, self.world.max_speed))
                         + 0.10 * sea, 0.0, 1.25)
            if staffed:
                # A qualified hand at the station checks the engine and steadily clears built-up strain.
                self.engine_unattended_time = max(0.0, self.engine_unattended_time - 2.5 * dt)
                if self.engine_unattended_time < 30.0:
                    self.engine_unattended_warning_stage = 0
                wear_multiplier = 0.68
            else:
                self.engine_unattended_time += dt
                wear_multiplier = 1.35
            # Running wear remains gradual; an empty station accelerates wear but does not stop the engine by itself.
            self.engine_oil = max(0.0, self.engine_oil - (0.010 + 0.009 * sea) * wear_multiplier * dt)
            self.cooling_intake = max(0.0, self.cooling_intake - (0.006 + 0.020 * sea + 0.006 * self.ship.flood) * wear_multiplier * dt)
            self.shaft_seal = max(0.0, self.shaft_seal - (0.004 + 0.014 * sea) * wear_multiplier * dt)
            if not staffed:
                if self.engine_unattended_time >= 300.0 and self.engine_unattended_warning_stage < 2:
                    self.engine_unattended_warning_stage = 2
                    self.crew.say("Engine strain is building: the station has been unattended for five minutes. Fault risk is rising.")
                elif self.engine_unattended_time >= 120.0 and self.engine_unattended_warning_stage < 1:
                    self.engine_unattended_warning_stage = 1
                    self.crew.say("Engine checks are overdue. Unattended running is increasing wear and fault risk.")
                # A fault is a chance, not a timer that guarantees breakdown. Risk rises with
                # load and with the length of time the engine has been left without a watch.
                exposure = min(3.0, 0.5 + self.engine_unattended_time / 300.0)
                fault_rate = (0.00004 + 0.00008 * load) * exposure
                if random.random() < 1.0 - math.exp(-fault_rate * dt):
                    attr, label = random.choice((("engine_oil", "oil pressure"),
                                                 ("cooling_intake", "cooling-water intake"),
                                                 ("shaft_seal", "shaft seal")))
                    before = getattr(self, attr)
                    damage = random.uniform(5.0, 12.0) * (0.7 + 0.6 * load)
                    setattr(self, attr, max(0.0, before - damage))
                    self.engine_fault_count += 1
                    self.crew.say("Unattended engine fault: %s is deteriorating (%d%%). Send a qualified hand below." %
                                   (label.capitalize(), round(getattr(self, attr))))
                    self.queue_broadcast_conversation([
                        (0.0, "ENGINE ROOM", "Bridge, engine room! %s is deteriorating. We need a qualified hand below. Over." % label.capitalize(), "intercom"),
                        (3.0, "Captain Ishida", "Acknowledged. Keep her steady and report the next reading. Over.", "intercom"),
                    ], priority=PRIORITY_HIGH, source="engine_alert")
        elif staffed:
            self.engine_unattended_time = max(0.0, self.engine_unattended_time - 2.5 * dt)
            if self.engine_unattended_time < 30.0:
                self.engine_unattended_warning_stage = 0

        # A flooded engine-room bilge slows the drive and can trip the diesel if the
        # crew leave the hatch open in a heavy sea. It can only be restored after bailing.
        if self.ship.engine_flood >= 0.90 and self.engine_ok:
            self.engine_ok = False
            self._engine_bilge_trip = True
            self.crew.say("ENGINE TRIP: water has reached the machinery in the engine-room bilge. Dog the hatch and bail her down before restarting.")
        # Give the engineer a useful automatic maintenance loop, but only while physically
        # at the station. Forced deck duties can therefore leave the machinery unattended.
        components = {
            "oil": (self.engine_oil, "engine_oil", "lubricating oil"),
            "cooling intake": (self.cooling_intake, "cooling_intake", "cooling-water intake"),
            "shaft seal": (self.shaft_seal, "shaft_seal", "shaft seal"),
        }
        low = [(value, label, attr) for label, (value, attr, _desc) in components.items() if value < 80.0]
        if engineer is not None and engineer.at_engine and low:
            value, label, attr = min(low, key=lambda item: item[0])
            if label != self.engine_service_component:
                self.engine_service_component, self.engine_service_t = label, 0.0
            self.engine_service_t += dt
            if self.engine_service_t >= 2.4:
                old = getattr(self, attr)
                setattr(self, attr, min(100.0, old + 34.0 + 12.0 * engineer.skill))
                new_value = getattr(self, attr)
                self.engine_service_t = 0.0
                desc = components[label][2]
                self.crew.say("Engineer %s checks the %s (%d%%)." % (engineer.name, desc, round(new_value)))
                if new_value >= 80.0:
                    self.engine_service_component = None
        else:
            self.engine_service_component, self.engine_service_t = None, 0.0

        # Notify when a reading first becomes poor; reset the notification if maintained.
        for key, label, value in (("oil", "Oil level", self.engine_oil),
                                  ("cooling", "Cooling-water intake", self.cooling_intake),
                                  ("seal", "Shaft seal", self.shaft_seal)):
            if value < 45.0 and key not in self.engine_condition_warnings:
                self.engine_condition_warnings.add(key)
                self.crew.say("Engine room: %s is low (%d%%). Send the engineer below." % (label, round(value)))
            elif value > 60.0 and key in self.engine_condition_warnings:
                self.engine_condition_warnings.remove(key)

        # A critical loss trips the engine. The latch clears only after an engineer brings
        # all three checks out of the danger band, preventing a fault from self-healing.
        if self.engine_ok and (self.engine_oil <= 7.0 or self.cooling_intake <= 7.0 or self.shaft_seal <= 4.0):
            self.engine_ok = False
            if self.cooling_intake <= 7.0:
                cause = "cooling-water failure"
            elif self.engine_oil <= 7.0:
                cause = "oil starvation"
            else:
                cause = "shaft-seal failure"
            self._prepare_broadcast_priority(PRIORITY_HIGH)
            self.crew.say("ENGINE TRIP: %s. Propulsion and the hauler have stopped." % cause.capitalize())
            self.queue_broadcast_conversation([
                (0.0, "ENGINE ROOM", "Bridge, engine room! The diesel has tripped. Propulsion is lost. Do not restart until the fault is found. Over.", "intercom"),
                (3.5, "Captain Ishida", "Understood. Hold the machinery safe. We will deal with the heading and the line first. Out.", "intercom"),
            ], priority=PRIORITY_HIGH, source="engine_trip")
        elif (not self.engine_ok and engineer is not None and engineer.at_engine
              and min(self.engine_oil, self.cooling_intake, self.shaft_seal) > 25.0
              and self.ship.engine_flood < 0.60):
            self.engine_ok = True
            self._engine_bilge_trip = False
            self.crew.say("Engineer %s restores the engine. Keep the three checks in hand." % engineer.name)

        oil_factor = 0.55 + 0.45 * clamp(self.engine_oil / 100.0, 0.0, 1.0)
        cooling_factor = 0.40 + 0.60 * clamp(self.cooling_intake / 100.0, 0.0, 1.0)
        seal_factor = 0.70 + 0.30 * clamp(self.shaft_seal / 100.0, 0.0, 1.0)
        bilge_factor = 1.0 - 0.42 * clamp((self.ship.engine_flood - 0.30) / 0.60, 0.0, 1.0)
        self.engine_power = min(oil_factor, cooling_factor, seal_factor) if self.engine_ok else 0.0
        if self.engine_ok:
            self.engine_power *= bilge_factor
        self._engine_on = bool(running and self.engine_ok and self.fuel > 0)

    def separate_crew(self):
        """Separate walking crew; sleepers occupy their bunks without body/bed collision response."""
        crew = [s for s in self.sailors if s.mode == Sailor.ABOARD
                and not (s.sleeping_in_bunk and s.task == "rest")]
        for i in range(len(crew)):
            for j in range(i + 1, len(crew)):
                a, b = crew[i], crew[j]
                if a.level != b.level or a.ladder is not None or b.ladder is not None:
                    continue
                d = a.pos - b.pos
                dist = d.length()
                min_d = a.body_r + b.body_r
                if dist >= min_d:
                    continue
                n = d / dist if dist > 1e-6 else V(1, 0).rotate_rad(random.uniform(0, TAU))
                over = min_d - dist
                wa = 3.0 if (a.working or a.at_post or a.at_engine) else 1.0
                wb = 3.0 if (b.working or b.at_post or b.at_engine) else 1.0
                a.pos += n * over * (wb / (wa + wb))
                b.pos -= n * over * (wa / (wa + wb))
                rel = (a.vel - b.vel).dot(n)
                if rel < 0:
                    a.vel -= n * rel * (wb / (wa + wb))
                    b.vel += n * rel * (wa / (wa + wb))
        for s in crew:
            if s.ladder is None:
                s.pos, s.vel = self.ship.collide(s.pos, s.vel, s.radius, s.level)

    # --- the harbour: heal, auction the catch, pay the crew
    def docked(self):
        w = self.world
        return (w.zone == 0 and w.speed < 60 and self.crew.alarm_target is None
                and w.dock_state is None and w.destination is None)

    def _auction_build_offers(self, fish):
        """Direct-offer Model A: stable buyer offers for one fish."""
        grade_mult = {"Sashimi": 1.5, "A": 1.15, "B": 0.8, "C": 0.5, "Scrap": 0.2}.get(fish.grade(), 0.2)
        species = fish.name.lower()
        clean = 1.2 if fish.bled and fish.gutted else 0.6
        chef_species = {"swordfish": 1.3, "bigeye": 1.2, "yellowfin": 1.1, "albacore": 1.0, "blue shark": 0.4}
        canner_species = {"albacore": 1.4, "yellowfin": 1.0, "bigeye": 0.9, "swordfish": 0.7, "blue shark": 1.2}
        base = fish.value * (1.0 if fish.bled else 0.85) * (1.0 if fish.gutted else 0.8) * self.market
        offers = []
        chef_count = sum(1 for f in self.hold if f is not fish)  # chef can take one fish per session
        if self.auction_session_sold == 0:
            chef_grade = {"Sashimi": 2.2, "A": 1.5, "B": 1.0, "C": 0.5, "Scrap": 0.3}.get(fish.grade(), 0.3)
            offers.append(("Sashimi Chef", int(base * chef_grade * clean * chef_species.get(species, 1.0)), "Kuroda, restaurant buyer"))
        canner_clean = 1.0 if fish.bled and fish.gutted else 0.6
        offers.append(("Canner", int(base * canner_clean * canner_species.get(species, 1.0)), "Hakodate Cannery"))
        lot_count = sum(1 for f in self.hold if f.name.lower() == species)
        if lot_count >= 3:
            pref = {"albacore": 1.2, "yellowfin": 1.2, "bigeye": 1.0, "swordfish": 0.8, "blue shark": 1.0}.get(species, 1.0)
            offers.append(("Wholesaler", int(base * 1.1 * pref * (1.0 + 0.05 * (lot_count - 3))), "Bulk lot buyer"))
        offers.append(("Harbour Trader", int(base * 0.85), "Quay-side floor offer"))
        if not getattr(self, "auction_collector_present", False):
            self.auction_collector_present = random.random() < 0.15
        if self.auction_collector_present and ((species == "swordfish" and fish.grade() in ("A", "Sashimi")) or (species == "bigeye" and fish.quality > 0.9) or species == "blue shark"):
            mult = 1.8 if species == "swordfish" else 1.6 if species == "bigeye" else 0.5
            offers.append(("Collector", int(base * mult), "Visiting specialist"))
        return sorted(offers, key=lambda row: row[1], reverse=True)

    def _open_auction(self):
        if self.auction_active or not self.hold:
            return False
        if not self.docked():
            self.crew.say("Auction: Bring the vessel alongside before opening the fish block.")
            return False
        self.auction_active = True
        self.auction_index = 0
        self.auction_session_sold = 0
        self.auction_session_total = 0
        self.auction_collector_present = random.random() < 0.15
        self.market_base = clamp(lerp(self.market_base, 1.0, 0.3) + random.uniform(-0.15, 0.15), 0.7, 1.3)
        self._refresh_market_index()
        self.auction_offers = self._auction_build_offers(self.hold[0])
        self.crew.say("Auction house: Buyers are ready. Review each fish; 1-4 sells to a buyer, K keeps it, A accepts all remaining offers.")
        return True

    def _auction_advance(self):
        if self.auction_index >= len(self.hold):
            self._close_auction()
            return
        self.auction_offers = self._auction_build_offers(self.hold[self.auction_index])

    def _auction_sell_current(self, buyer_index=0):
        if not self.auction_active or self.auction_index >= len(self.hold):
            return
        offers = self.auction_offers
        if not offers:
            return
        buyer_index = int(clamp(buyer_index, 0, len(offers) - 1))
        buyer, price, _ = offers[buyer_index]
        fish = self.hold.pop(self.auction_index)
        self.cash += max(0, price)
        self.earned += max(0, price)
        self.auction_session_total += max(0, price)
        self.auction_session_sold += 1
        self.crew.say("Auction: %s sold to %s for %d yen (%s grade)." % (fish.name, buyer, price, fish.grade()))
        self._auction_advance()

    def _auction_keep_current(self):
        if not self.auction_active or self.auction_index >= len(self.hold):
            return
        fish = self.hold[self.auction_index]
        fish.quality = max(0.0, fish.quality - 0.015)
        fish.deck_exposure = getattr(fish, "deck_exposure", 0.0)
        self.crew.say("Auction: %s kept for another session; quality may decay while stored." % fish.name)
        self.auction_index += 1
        self._auction_advance()

    def _auction_accept_all(self):
        while self.auction_active and self.auction_index < len(self.hold):
            offers = self.auction_offers or self._auction_build_offers(self.hold[self.auction_index])
            self.auction_offers = offers
            self._auction_sell_current(0)
        if self.auction_active:
            self._close_auction()

    def _close_auction(self):
        self.auction_active = False
        self.auction_offers = []
        self.auction_index = 0
        self.crew.say("Auction session complete: %d fish sold for %d yen; %d fish kept in the hold." %
                      (self.auction_session_sold, self.auction_session_total, len(self.hold)))
        # Continue the original settlement contract only after the modal auction.
        self._auction_resolving = True
        try:
            self.settle(manual=False)
        finally:
            self._auction_resolving = False

    def settle(self, manual=False):
        say = self.crew.say
        if not self.docked():
            if manual:
                say("Captain: We're not alongside. Take her into the harbour first.")
            return
        if self.hold and not self._auction_resolving:
            self._open_auction()
            return
        self.arrival_done = True
        crew = [s for s in self.sailors if s.mode == Sailor.ABOARD]
        due = sum(int(s.owed) for s in crew)
        if (not self.hold and due <= 0 and self.ice >= ICE_CAP - 1 and self.fuel >= FUEL_CAP - 1 and self.gaffs >= GAFFS
                and self.bait_total() >= BAIT_FILL - 1 and not manual):
            self._start_dock_shore_leave()
            return
        if self.hold and not self._auction_resolving:
            # Report handling outcomes before the sale clears the hold inventory.
            for report_line in self.catch_report_lines(limit=4):
                say(report_line)
            self.market_base = clamp(lerp(self.market_base, 1.0, 0.3) + random.uniform(-0.15, 0.15), 0.7, 1.3)
            self._refresh_market_index()
            total, counts = 0, {}
            for c in self.hold:
                total += int(c.sale_value() * self.market * random.uniform(0.9, 1.1))
                counts[c.grade()] = counts.get(c.grade(), 0) + 1
            say("Auction: %d fish (%s) sold for %d yen, market x%.2f." % (
                len(self.hold), ", ".join("%d %s" % (counts[n], n) for _, n, _ in GRADES if n in counts), total, self.market))
            self.hold.clear()
            self.cash += total
            self.earned += total
        elif manual:
            say("Auction: nothing in the hold to sell.")
        buy = min(ICE_CAP - self.ice, self.cash / ICE_PRICE)          # fill the hold with ice for the next trip
        if buy >= 1:
            self.ice += buy
            self.cash -= int(buy * ICE_PRICE)
            self.ice_warn = 0
            say("Ice: loaded %d units for %d yen." % (buy, int(buy * ICE_PRICE)))
        buy = min(FUEL_CAP - self.fuel, max(0.0, self.cash) / FUEL_PRICE)
        if buy >= 1:
            self.fuel += buy
            self.cash -= int(buy * FUEL_PRICE)
            self.fuel_warn = 0
            say("Fuel: took on %d litres for %d yen." % (buy, int(buy * FUEL_PRICE)))
        if self.gaffs < GAFFS and self.cash >= GAFF_PRICE:
            n = min(GAFFS - self.gaffs, int(self.cash // GAFF_PRICE))
            self.gaffs += n
            self.cash -= n * GAFF_PRICE
            say("Gear: %d new gaff%s for %d yen." % (n, "" if n == 1 else "s", n * GAFF_PRICE))
        t = self.bait_sel                                  # top the boxes up with the chosen bait
        want = min(BAIT_FILL - self.bait_total(), max(0.0, self.cash) / BAITS[t])
        if want >= 1:
            have = self.bait[t]
            self.bait_fresh[t] = (have * self.bait_fresh[t] + want) / (have + want)
            self.bait[t] += want
            self.cash -= int(want * BAITS[t])
            self.bait_warned = False
            say("Bait: %d %s for %d yen." % (want, t, int(want * BAITS[t])))
        if due > 0:
            k = min(1.0, self.cash / due)
            paid = 0
            for s in crew:
                pay = int(s.owed * k)
                paid += pay
                s.owed = 0.0 if k >= 0.999 else s.owed - pay
                s.add_morale(0.12 if k >= 0.999 else -0.1)
            self.cash -= paid
            say("Crew paid %d yen%s. Cash: %d yen." % (paid, "" if k >= 0.999 else " - SHORT, the rest is owed", self.cash))
        self._start_dock_shore_leave()

    def _refresh_hire_candidates(self):
        """Create a modest dock hiring board without consuming cash until the player hires someone."""
        names = ["Kato", "Fujita", "Nakamura", "Hayashi", "Watanabe", "Ishikawa", "Okada", "Arai",
                 "Shimizu", "Matsuda", "Endo", "Miyazaki", "Ueda", "Sakai"]
        used = {s.name for s in getattr(self, "sailors", [])}
        self.hire_candidates = []
        available = [n for n in names if n not in used]
        random.shuffle(available)
        for name in available[:4]:
            skill = random.uniform(0.22, 0.78)
            self.hire_candidates.append({
                "name": name, "skill": skill, "caution": random.uniform(0.35, 0.85),
                "fee": int(3500 + skill * 4500), "wage": 2500,
            })

    def _send_sailor_ashore(self, sailor, keep_ashore=False, announce=True, automatic=False):
        """Transfer a sailor to shore leave; only deckhands may be permanently retained ashore."""
        if sailor is None or sailor not in self.sailors or sailor.mode != Sailor.ABOARD:
            return False
        if sailor.role != Sailor.DECKHAND and not automatic:
            if announce:
                self.crew.say("Dockmaster: The captain and veteran return automatically on departure and cannot be kept ashore permanently.")
            return False
        if sailor.role != Sailor.DECKHAND and keep_ashore:
            return False
        if not self.docked():
            if announce:
                self.crew.say("Dockmaster: Shore leave is available only while alongside.")
            return False
        if sailor.ladder is not None or sailor.mode != Sailor.ABOARD:
            return False
        if sailor is self.radio_operator:
            self.shore_radio_operator = sailor if not keep_ashore else None
            self.radio_operator = None
            self.radio_duty_active = False
        if sailor is self.helm_operator:
            self.helm_operator = None   # docked and stationary; ownership is reassigned when the crew returns
        sailor._release()
        sailor.mode = Sailor.SHORE
        sailor.keep_ashore = bool(keep_ashore)
        sailor.shore_since = 0.0
        sailor.level = Level.MAIN
        sailor.ladder = None
        sailor.has_target = sailor.ordering = False
        sailor.path, sailor.path_goal, sailor.level_goal = [], None, None
        sailor.vel = V(0, 0)
        sailor.task, sailor.duty, sailor.working = "shore", "", False
        sailor.at_post = sailor.at_engine = sailor.at_radio = False
        sailor.rescue_target = sailor.alert_target = None
        sailor.speech_bubble, sailor.speech_t = "", 0.0
        if sailor.selected:
            sailor.selected = False
            fallback = next((x for x in self.sailors if x.mode == Sailor.ABOARD and x.role == Sailor.CAPTAIN), None)
            if fallback is None:
                fallback = next((x for x in self.sailors if x.mode == Sailor.ABOARD), None)
            if fallback is not None:
                fallback.selected = True
        self.crew.status[sailor.name] = "shore"
        if announce:
            self.crew.say("Dockmaster: %s has gone into town to recover." % sailor.name)
        return True

    def _bring_sailor_aboard(self, sailor, announce=True):
        """Return a shore employee to a safe, spaced main-deck start point."""
        if sailor is None or sailor not in self.sailors or sailor.mode != Sailor.SHORE:
            return False
        if not self.docked():
            if announce:
                self.crew.say("Dockmaster: Bring crew aboard while alongside; set course to recall the automatic shore party.")
            return False
        was_radio_operator = sailor is self.shore_radio_operator
        sailor.mode = Sailor.ABOARD
        sailor.keep_ashore = False
        sailor.shore_since = 0.0
        sailor.level = Level.MAIN
        sailor.ladder = None
        # Spread the returning shore party over a safe patch of main deck; spawning
        # everyone at one point caused the same crowding that the wheelhouse fix avoids.
        onboard_index = sum(1 for other in self.sailors if other is not sailor and other.mode == Sailor.ABOARD)
        embark_offsets = (V(-78, -34), V(-28, -34), V(25, -34), V(75, -34),
                          V(-78, 34), V(-28, 34), V(25, 34), V(75, 34))
        sailor.pos = V(self.ship.markers["rest_spot"]) + embark_offsets[onboard_index % len(embark_offsets)]
        sailor.vel = V(0, 0)
        sailor._release()
        sailor.task, sailor.duty = "idle", ""
        sailor.has_target = sailor.ordering = False
        sailor.path, sailor.path_goal, sailor.level_goal = [], None, None
        sailor.think_t = 0.0
        self.crew.status[sailor.name] = "aboard"
        # If the player brings the stored wireless operator back individually, restore
        # that station too. A deliberately assigned replacement takes precedence.
        if was_radio_operator:
            self.shore_radio_operator = None
            if self.radio_operator is None:
                self.assign_radio_operator(sailor, announce=False)
        if announce:
            self.crew.say("Dockmaster: %s is back aboard." % sailor.name)
        return True

    def _shore_returning_crew(self):
        """Crew who should be recalled by the wait action; retained shore staff are excluded."""
        return returning_shore_crew(self.sailors, Sailor.SHORE)

    def _stop_shore_wait(self, message=None):
        """Stop accelerated shore waiting and restore the timescale captured at start."""
        if not self.shore_wait_active:
            return False
        self.shore_wait_active = False
        restore = self.shore_wait_previous_timescale
        self.timescale = restore if restore in (1, 3, 6) else 1
        if message:
            self.crew.say(message)
        return True

    def _start_dock_shore_leave(self):
        """At each settled dock, send the active crew ashore; deckhands may remain there permanently."""
        if self.dock_shore_leave_started or not self.docked():
            return
        self.dock_shore_leave_started = True
        # The vessel is stationary at the quay. Preserve the operator for the next departure.
        op = self.radio_operator
        if op is not None and op.mode == Sailor.ABOARD and not op.keep_ashore:
            self.shore_radio_operator = op
        self.radio_operator = None
        self.radio_duty_active = False
        sent = 0
        for sailor in list(self.sailors):
            if sailor.mode == Sailor.ABOARD and not sailor.keep_ashore:
                if self._send_sailor_ashore(sailor, keep_ashore=False, announce=False, automatic=True):
                    sent += 1
        if sent:
            self.crew.say("Dockmaster: %d sailor%s ashore for medical care and leave. Open F1 for the crew sheet." %
                          (sent, "s" if sent != 1 else ""))

    def _recall_shore_leave(self, departure=False):
        """Recall automatic shore leave; keep retained staff ashore and make departure idempotent."""
        if departure:
            self._stop_shore_wait("Dockmaster: Shore wait stopped; recalling the crew for departure.")
        returned = []
        for sailor in list(self.sailors):
            if sailor.mode == Sailor.SHORE and not sailor.keep_ashore:
                if self._bring_sailor_aboard(sailor, announce=False):
                    returned.append(sailor)
        # Clear the dock event latch only at a real departure. Readiness completion
        # and repeated input polling must not make the next settlement send crew ashore twice.
        if departure:
            self.dock_shore_leave_started = False
        if returned and not any(s.selected and s.mode == Sailor.ABOARD for s in self.sailors):
            captain = next((s for s in self.sailors if s.role == Sailor.CAPTAIN and s.mode == Sailor.ABOARD), None)
            if captain is not None:
                captain.selected = True
        if returned:
            self.crew.say("Dockmaster: %d crewman%s recalled from shore leave. All hands aboard." %
                          (len(returned), "" if len(returned) == 1 else "s"))

    def hire_from_dock(self, candidate_index, stay_ashore=False):
        """Hire a prospect aboard or keep the newly hired sailor ashore."""
        if not self.docked():
            self.crew.say("Dockmaster: Hiring is only available at the quay.")
            return False
        if not (0 <= candidate_index < len(self.hire_candidates)):
            return False
        candidate = self.hire_candidates[candidate_index]
        if self.cash < candidate["fee"]:
            self.crew.say("Dockmaster: Not enough cash. Recruitment costs %d yen." % candidate["fee"])
            return False
        if any(s.name == candidate["name"] for s in self.sailors):
            self._refresh_hire_candidates()
            return False
        self.cash -= candidate["fee"]
        onboard_index = sum(1 for other in self.sailors if other.mode == Sailor.ABOARD)
        embark_offsets = (V(-78, -34), V(-28, -34), V(25, -34), V(75, -34),
                          V(-78, 34), V(-28, 34), V(25, 34), V(75, 34))
        spawn = V(self.ship.markers["rest_spot"]) + embark_offsets[onboard_index % len(embark_offsets)]
        sailor = Sailor(self, candidate["name"], Sailor.DECKHAND, spawn)
        sailor.skill = candidate["skill"]
        sailor.caution = candidate["caution"]
        sailor.wage = candidate["wage"]
        sailor.fatigue = random.uniform(0.08, 0.28)
        sailor.morale = random.uniform(0.58, 0.86)
        sailor.selected = False
        self.sailors.append(sailor)
        self.crew.status[sailor.name] = "aboard"
        if stay_ashore and not self._send_sailor_ashore(sailor, keep_ashore=True, announce=False):
            # Roll back cleanly if a state transition made shore leave unavailable.
            self.sailors.remove(sailor)
            self.crew.status.pop(sailor.name, None)
            self.cash += candidate["fee"]
            return False
        self.hire_candidates.pop(candidate_index)
        if not self.hire_candidates:
            self._refresh_hire_candidates()
        self.crew.say("Dockmaster: Hired %s for %d yen%s." %
                      (sailor.name, candidate["fee"], " — staying ashore until recalled" if stay_ashore else " — added to the crew"))
        return True

    def _sheet_action(self, action, value=None):
        if action == "close":
            self.crew_sheet_open = False
            return
        if action == "info_tab":
            self.info_sheet_tab = value if value in ("ship_catch", "telemetry", "crew", "controls") else "ship_catch"
            self.info_sheet_scroll = 0
            self.crew_sheet_scroll = 0
            return
        if action == "wait_shore":
            if self.shore_wait_active:
                self._stop_shore_wait("Dockmaster: Waiting cancelled.")
            elif not self.docked():
                self.crew.say("Dockmaster: Shore leave can only be waited out alongside.")
            else:
                eligible = self._shore_returning_crew()
                if not eligible:
                    self.crew.say("Dockmaster: No automatic shore party is waiting to return.")
                else:
                    self.shore_wait_active = True
                    self.shore_wait_previous_timescale = self.timescale
                    self.timescale = 6
                    self.crew.say("Dockmaster: Standing by until the shore party has recovered. Time accelerated; press CANCEL WAIT to stop.")
            return
        if action == "tab":
            self.crew_sheet_tab = value
            self.crew_sheet_scroll = 0
            return
        if action == "send_ashore":
            self._send_sailor_ashore(value, keep_ashore=True)
        elif action == "bring_aboard":
            self._bring_sailor_aboard(value)
        elif action == "toggle_shore":
            value.keep_ashore = not value.keep_ashore
            self.crew.say("Dockmaster: %s will %s." % (value.name,
                           "remain ashore when the ship departs" if value.keep_ashore else "return on the next departure"))
        elif action == "hire_aboard":
            self.hire_from_dock(value, stay_ashore=False)
        elif action == "hire_shore":
            self.hire_from_dock(value, stay_ashore=True)

    def _handle_crew_sheet_click(self, pos):
        for rect, action, value, enabled in reversed(self.crew_sheet_hitboxes):
            if rect.collidepoint(pos):
                if enabled:
                    self._sheet_action(action, value)
                elif action not in ("tab", "close"):
                    self.crew.say("Dockmaster: Crew changes are available only while the ship is alongside.")
                return True
        # The sheet is modal; click outside its card closes it, preventing accidental course/crew orders.
        self.crew_sheet_open = False
        return True

    def _recover_wheelhouse_exit(self, sailor):
        """Retry a blocked wheelhouse exit; after a second failed route, use the actual ladder as a failsafe."""
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.level != Level.WHEELHOUSE or sailor.ladder is not None:
            return False
        link = next((lk for lk in self.ship.links if Level.WHEELHOUSE in lk.ends and Level.MAIN in lk.ends), None)
        if link is None:
            return False
        # Relinquish station ownership before routing out; otherwise the helm/radio guard rejects the route.
        if sailor is self.helm_operator:
            captain = next((x for x in self.sailors if x.role == Sailor.CAPTAIN and x.mode == Sailor.ABOARD and x is not sailor), None)
            veteran = next((x for x in self.sailors if x.role == Sailor.VETERAN and x.mode == Sailor.ABOARD and x is not sailor and x is not self.radio_operator), None)
            if sailor.role == Sailor.CAPTAIN:
                if veteran is not None:
                    self.captain_resting, self.captain_rest_elapsed = True, 0.0
                    sailor.duty = "rest"
                    self._set_helm_operator(veteran)
                else:
                    self.captain_resting = True
                    self._set_helm_operator(None)
            elif captain is not None and not self.captain_resting:
                self._set_helm_operator(captain)
            else:
                self._set_helm_operator(None)
        if sailor is self.radio_operator:
            # An explicit escape request can cancel an abandoned local call rather than trap the operator.
            self.pending_radio_calls.clear()
            self.radio_calls.clear()
            self.radio_transcript_queue.clear()
            self.radio_operator, self.radio_duty_active = None, False
            sailor.duty = ""
        sailor._release()
        sailor.wheelhouse_exit_attempts += 1
        entry = self.ship.wheelhouse_floor_point(link.pos(Level.WHEELHOUSE))
        if sailor.wheelhouse_exit_attempts >= 2:
            # Last-resort reposition is only to the wheelhouse's own ladder landing, never to another deck/room.
            sailor.pos = V(entry)
            sailor.vel = V(0, 0)
            sailor.has_target = sailor.ordering = False
            sailor.path, sailor.path_goal = [], None
            sailor.task, sailor.duty = "idle", ""
            sailor.start_climb(link)
            self.crew.say("Crew: The wheelhouse passage was blocked; clearing the ladder landing to get out safely.")
            return True
        sailor.task = "order"
        sailor.order_goal, sailor.order_level, sailor.order_planned = V(link.pos(Level.MAIN)), Level.MAIN, False
        sailor.ordering, sailor.order_hold, sailor.think_t = True, 999.0, 0.0
        sailor.target, sailor.has_target = V(entry), True
        sailor.path = sailor._plan_path(sailor.pos, entry, Level.WHEELHOUSE)
        if not sailor.path:
            sailor.path = [V(entry)]
        sailor.path_goal = V(entry)
        sailor.stuck_t = 0.0
        self.crew.say("Crew: The wheelhouse exit is blocked; trying the ladder route again.")
        return True

    def request_wheelhouse_exit(self, sailor, destination=None, link=None):
        """Hand over a station safely, then route the sailor through the wheelhouse ladder."""
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.level != Level.WHEELHOUSE:
            return False
        if sailor is self.helm_operator:
            captain = next((x for x in self.sailors if x.role == Sailor.CAPTAIN and x.mode == Sailor.ABOARD and x is not sailor), None)
            veteran = next((x for x in self.sailors if x.role == Sailor.VETERAN and x.mode == Sailor.ABOARD and x is not sailor and x is not self.radio_operator), None)
            if sailor.role == Sailor.CAPTAIN:
                if veteran is not None:
                    self.captain_resting, self.captain_rest_elapsed = True, 0.0
                    sailor.duty = "rest"
                    self._set_helm_operator(veteran)
                else:
                    self.captain_resting = True
                    self._set_helm_operator(None)
                destination = self.ship.markers["rest_spot"]
            elif captain is not None and not self.captain_resting:
                self._set_helm_operator(captain)
            else:
                self._set_helm_operator(None)
        if sailor is self.radio_operator:
            self.pending_radio_calls.clear()
            self.radio_calls.clear()
            self.radio_transcript_queue.clear()
            self.radio_operator, self.radio_duty_active = None, False
            sailor.duty = ""
        if link is not None and sailor.pos.distance_to(link.pos(sailor.level)) <= self.ship.LINK_REACH:
            sailor._release()
            sailor.ordering, sailor.order_hold = False, 0.0
            sailor.start_climb(link)
            sailor.wheelhouse_exit_elapsed = sailor.wheelhouse_exit_attempts = 0.0
            return True
        goal = V(destination) if destination is not None else V(self.ship.markers["rest_spot"])
        sailor.order_to(goal, Level.MAIN)
        sailor.wheelhouse_exit_elapsed = 0.0
        sailor.wheelhouse_exit_attempts = 0
        return True

    def _generate_full_sheet_rows(self):
        if self.crew_sheet_tab == "crew":
            return [("crew", s) for s in self.sailors if s.mode == Sailor.ABOARD]
        if self.crew_sheet_tab == "shore":
            return [("shore", s) for s in self.sailors if s.mode == Sailor.SHORE]
        return [("hire", candidate) for candidate in self.hire_candidates]

    def _information_sheet_rows(self, tab):
        """On-demand detail data for the F1 sheet; the always-on HUD remains critical-only."""
        if tab == "controls":
            # Keep this list in sync with CONTROLS.md.  Values are deliberately
            # compact because the F1 sheet also needs to work on small windows.
            return [
                ("SELECT / MOVE CREW", "Left-click a sailor to select; TAB cycles living crew."),
                ("CREW MOVEMENT", "Right-click a deck or room spot to order the selected sailor."),
                ("CONTEXT MENU", "Right-click crew, hatches, roller, buoys or gear for actions."),
                ("MANUAL HELM", "With a helmsman on watch: LEFT/RIGHT steer; UP/DOWN telegraph."),
                ("STOP / BRAKE", "Hold SPACE to cancel travel orders and stop the vessel."),
                ("ANCHOR", "Press A or click ANCHOR beside the cash HUD to drop/weigh anchor; drift is greatly reduced."),
                ("QUICK STEER", "Right-click open water in deck view to steer toward that spot."),
                ("OCEAN PLOT", "SHIFT + right-drag A to B; needs daylight and clear visibility."),
                ("CHART", "C opens chart; click to add points; ENTER commits; ESC clears."),
                ("EDIT CHART", "Click a waypoint then its new spot; SHIFT-click a leg inserts one."),
                ("DELETE WAYPOINT", "Right-click a waypoint on the chart; ENTER commits the edit."),
                ("NAVIGATION FIX", "On chart: 1 landmark, 2 sextant, 3 RDF, 4 sounder."),
                ("AUTODOCK / NAV", "D toggles autodock; N switches to dead-reckoning navigation."),
                ("TIME / ZOOM", "T cycles time at 1x / 3x / 6x; mouse wheel zooms the world view."),
                ("LONGLINE", "L auto-fishing; P one manual set; J haul now; M operate roller."),
                ("LINE SLACK", "[ reduces slack; ] increases slack. Each press changes it by 0.05."),
                ("FISH FIGHT", "Hold X to tighten and Z to ease; SPACE works the manual gaff/brake."),
                ("DECK / HOLD GEAR", "K cycle bait; Y safety harness; U hatch; F hose wash; V trim ice."),
                ("CREW SAFETY", "H muster crew; R order recovery of a swimmer; Q/E climb or look levels."),
                ("CREW DUTIES A", "Select a sailor, then 1 set, 2 haul, 3 clean, 4 rest, 5 dress fish."),
                ("CREW DUTIES B", "6 engine watch; 7 helm watch; 0 clear the selected sailor's duty."),
                ("CREW REPORTS", "I bearing/range; O speed; click the same sailor again for second opinion."),
                ("CAPTAIN ORDERS", "Right-click the captain for Fish: 3-day trip or Return to port. Trips return early if fuel, bait, or ice runs low."),
                ("RADIO", "F2 weather; F3 market; F4 tow/escort position; click RADIO beside ANCHOR or press Ctrl+F11 for the ship-to-ship radio UI; G asks the Coast Guard captain questions while escorting."),
                ("TOW ESCORT", "Coast Guard launch has its own named captain/crew, regular 30-minute in-game radio check-ins, an amber chart marker and a towline. Stale reports show a question mark."),
                ("WEATHER", "W cycles weather. Comma / period lower / raise the sea-state setting."),
                ("HUD / DISPLAY", "F5 controls strip; F6 fishing meter; F7 HUD mode; F8 HUD visibility."),
                ("OTHER WINDOWS", "F1 info sheet; F9 notebook; F10 debug longline map; click RADIO or Ctrl+F11 ship radio; F11 fullscreen; F12 tow diagnostics."),
                ("AUCTION", "B at the quay opens settlement; 1-4 sell, K keep, A sell all."),
                ("MOUSE WHEEL", "Zoom the world view; scroll this information sheet while it is open."),
                ("COURSE BEHAVIOUR", "A plotted line is a desired track, not rails; wind/current add drift."),
                ("HELM REQUIREMENT", "Arrow-key ship control requires the captain or relief at the helm."),
                ("MODAL WINDOWS", "F1/ESC closes info; C toggles chart; F9/ESC closes the notebook."),
            ]
        w = self.world
        line_name = {Longline.IDLE: "Idle / stowed", Longline.SETTING: "Setting", Longline.SOAKING: "Soaking",
                     Longline.HAULING: "Hauling"}.get(self.line.phase, "Unknown")
        aboard = [s for s in self.sailors if s.mode == Sailor.ABOARD]
        shore = [s for s in self.sailors if s.mode == Sailor.SHORE]
        owed = sum(int(s.owed) for s in self.sailors if s.mode != Sailor.DEAD)
        hold_value = sum(c.sale_value() for c in self.hold)
        avg_quality = round(100 * sum(c.quality for c in self.hold) / max(1, len(self.hold)))
        if tab == "ship_catch":
            rows = [
                ("FINANCES", "%s yen cash | %s earned | market x%.2f" % (f"{self.cash:,}", f"{self.earned:,}", self.market)),
                ("WAGES", "%s yen owed | %d aboard | %d ashore" % (f"{owed:,}", len(aboard), len(shore))),
                ("FUEL", "%d / %d L" % (self.fuel, FUEL_CAP)),
                ("ENGINE", "%s | power %.0f%% | load %.0f%%" % (self.engine_status(), 100 * self.engine_power,
                    100 * clamp(w.throttle, 0.0, 1.0))),
                ("ENGINE CHECKS", "Oil %d%% | cooling %d%% | shaft seal %d%%" %
                    (round(self.engine_oil), round(self.cooling_intake), round(self.shaft_seal))),
                ("SUPPLIES", "%d gaffs | %d %s bait | %d buckets" %
                    (self.gaffs, int(self.bait.get(self.bait_sel, 0)), self.bait_sel, self.ship.bucket_count)),
                ("HOLD STORAGE", "%d ice | %.1f C | %s" % (round(self.ice), self.hold_temp,
                    "COLD" if self.ice > 0 and self.hold_temp <= 5.0 else "WARMING")),
                ("HOLD CATCH", "%d fish | average quality %d%% | est. %s yen" %
                    (len(self.hold), avg_quality, f"{hold_value:,}")),
                ("DECK CATCH", "%d fish on deck (%d alive) | %d on cutting table" %
                    (len(self.items), sum(1 for it in self.items if it.fish.alive), len(self.table.raw))),
                ("DECK WATER", "Wetness %.0f%% | standing water %.0f%%" % (100 * self.ship.wet, 100 * self.ship.flood)),
                ("ENGINE BILGE", "Flooding %.0f%% | room damage %.0f%%" % (100 * self.ship.engine_flood, self.engine_room_damage)),
                ("FLOODING", "%s | reserve %.0f%% | list %.0f deg %s | pump %s" % (
                    self.ship.flood_state.replace("_", " "), 100 * FloodingModel.reserve_buoyancy(self.ship),
                    abs(self.ship.list_trim) * FloodingModel.DEGREES_PER_LIST,
                    "stbd" if self.ship.list_trim > 0.01 else ("port" if self.ship.list_trim < -0.01 else ""),
                    ("%.1f%%/s" % (100 * self.ship.pump_flow)) if self.ship.pump_flow > 0 else ("idle" if self.engine_ok else "NO POWER"))),
                ("FISHING GEAR", "%s | slack x%.2f | %s" % (line_name, self.line.slack,
                    "auto" if self.line.auto else "manual")),
                ("AUCTION", "Available alongside; press B at the quay"),
            ]
            for fish in self.hold[:6]:
                rows.append(("STOWED FISH", "%s | %s | Q %d%% | %.1f C" %
                             (fish.name, fish.grade(), round(100 * fish.quality), fish.core)))
            return rows

        believed_distance = w.believed_pos.distance_to(HARBOUR) / w.scale
        believed_zone = 0 if believed_distance < 900 else (1 if believed_distance < 5000 else 2)
        heading = int(round(math.degrees(w.believed_heading) % 360))
        speed_kt = 10.0 * w.believed_speed / max(1.0, w.max_speed)
        helm_pos = self.ship.wheelhouse_stations["helm"]
        helm = next((s.name for s in self.sailors if s is self.helm_operator and s.mode == Sailor.ABOARD
                     and s.level == Level.WHEELHOUSE and s.task == "post" and s.at_post
                     and s.pos.distance_to(helm_pos) <= 55.0), "UNMANNED")
        radio_name = self.radio_operator.name if self.radio_operator is not None else "Unassigned"
        radio_status = "watch active" if self.radio_station_ok() else "unattended"
        if self.crew.alarm_target is not None:
            safety = "MOB %s / %s" % (self.crew.alarm_target.name, self.mob_rescue_mode.upper().replace("_", " "))
        elif self.muster_active:
            safety = "MUSTER %d/%d reported" % (len(self.muster_reports), len(self.muster_expected))
        else:
            safety = "No active rescue or muster"
        hurt = sum(1 for sailor in self.sailors if sailor.mode != Sailor.DEAD and sailor.health < 0.995)
        return [
            ("LOCAL TIME", "%s | believed %s waters" % (w.clock_text(), World.ZONES[believed_zone].lower())),
            ("SPEED / HEADING", "%.1f kt | %03d deg" % (speed_kt, heading)),
            ("ENGINE TELEGRAPH", "%s | brake %s" % (w.engine_order_text(), "ON" if w.brake else "off")),
            ("COURSE", "AUTODOCK %s" % w.dock_state if w.dock_state is not None else
             ("Destination %.0f units" % (w.believed_pos.distance_to(w.destination) / w.scale) if w.destination is not None else "No destination set")),
            ("NAVIGATION DOUBT", "+/- %d units | fix %s ago (%s)" %
             (round(w.dr_uncertainty), w.fix_age_text(), w.last_fix_method)),
            ("SEA STATE", "%.2f | wave energy %.2f" % (w.sea_state, w.waves.strength)),
            ("WEATHER", "%s | wind %s %d kt" % (self.weather.label(), self.weather.wind_from(), self.weather.wind_kt())),
            ("VISIBILITY", "%.1f km | air %d C" % (self.weather.visibility_km(), round(self.weather.air_temp()))),
            ("HELM WATCH", helm),
            ("RADIO WATCH", "%s | %d%% signal | %s" % (radio_name, round(100 * self.radio.signal_quality), radio_status)),
            ("LONGLINE", "%s | slack x%.2f" % (line_name, self.line.slack)),
            ("NAVIGATION", "Crew estimate / dead reckoning"),
            ("SAFETY", safety),
            ("CREW CONDITION", "%d aboard | %d ashore | %d injured" % (len(aboard), len(shore), hurt)),
            ("ENVIRONMENT", "Deck wet %.0f%% | bilge %.0f%%" % (100 * self.ship.wet, 100 * self.ship.engine_flood)),
        ]

    def _draw_information_page(self, x, y, width, height, tab):
        rows = self._information_sheet_rows(tab)
        body_top = y + 116
        body_bottom = y + height - 45
        row_gap = 8
        two_columns = width >= 760
        is_controls = tab == "controls"
        cell_h = (70 if two_columns else 62) if is_controls else (54 if two_columns else 44)
        cols = 2 if two_columns else 1
        cell_w = (width - 44 - row_gap * (cols - 1)) // cols
        visible_rows = max(1, (body_bottom - body_top + row_gap) // (cell_h + row_gap))
        indexed = [(rows[i], rows[i + 1] if i + 1 < len(rows) else None) for i in range(0, len(rows), cols)]
        self.info_sheet_scroll = int(clamp(self.info_sheet_scroll, 0, max(0, len(indexed) - visible_rows)))
        shown = indexed[self.info_sheet_scroll:self.info_sheet_scroll + visible_rows]
        for ri, pair in enumerate(shown):
            for ci, datum in enumerate(pair):
                if datum is None:
                    continue
                cx = x + 22 + ci * (cell_w + row_gap)
                cy = body_top + ri * (cell_h + row_gap)
                rect = pygame.Rect(cx, cy, cell_w, cell_h)
                pygame.draw.rect(self.screen, (27, 39, 43) if ri % 2 == 0 else (23, 34, 38), rect, border_radius=5)
                pygame.draw.rect(self.screen, (65, 88, 88), rect, 1, border_radius=5)
                label, value = datum
                label_surface = self.hud_compact_font.render(self._fit(label.upper(), cell_w - 18), True, (224, 194, 124))
                self.screen.blit(label_surface, (cx + 9, cy + 6))
                if is_controls:
                    lines = self._wrap_notebook_text(self.font, value, cell_w - 18)
                    max_lines = 3 if not two_columns else 2
                    for li, line in enumerate(lines[:max_lines]):
                        value_surface = self.font.render(line, True, (236, 240, 229))
                        self.screen.blit(value_surface, (cx + 9, cy + 27 + li * self.font.get_linesize()))
                else:
                    value_surface = self.font.render(self._fit(value, cell_w - 18), True, (236, 240, 229))
                    self.screen.blit(value_surface, (cx + 9, cy + 26 if two_columns else cy + 22))
        if len(indexed) > visible_rows:
            footer = "Rows %d-%d of %d | mouse wheel / UP-DOWN to scroll" % (
                self.info_sheet_scroll + 1, min(len(indexed), self.info_sheet_scroll + visible_rows), len(indexed))
        else:
            footer = "F1 / ESC close | TAB or LEFT/RIGHT changes section"
        self.screen.blit(self.hud_compact_font.render(self._fit(footer, width - 44), True, (200, 195, 175)),
                         (x + 22, y + height - 29))

    def draw_crew_sheet(self):
        """Unified F1 information sheet; Crew tab retains the existing dock roster actions."""
        if not self.crew_sheet_open:
            return
        shade = self._cached_panel_surface((W, H), (0, 0, 0, 205))
        self.screen.blit(shade, (0, 0))
        width, height = min(W - 32, 1120), min(H - 32, 760)
        x, y = (W - width) // 2, (H - height) // 2
        card = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (18, 27, 32), card, border_radius=12)
        pygame.draw.rect(self.screen, (202, 173, 104), card, width=2, border_radius=12)
        title_text = "VESSEL INFORMATION & CREW SHEET"
        title = self.font.render(self._fit(title_text, width - 166), True, (255, 232, 177))
        self.screen.blit(title, (x + 22, y + 13))
        status = "ALONGSIDE - crew changes enabled" if self.docked() else "UNDERWAY - information only; crew changes are dock-only"
        status_surf = self.hud_compact_font.render(self._fit(status, width - 44), True,
                         (180, 216, 192) if self.docked() else (240, 180, 150))
        self.screen.blit(status_surf, (x + 22, y + 39))
        self.crew_sheet_hitboxes = []

        def button(bx, by, bw, bh, label, action, value=None, enabled=True, active=False):
            rect = pygame.Rect(int(bx), int(by), int(bw), int(bh))
            fill = (71, 91, 81) if active else ((48, 77, 86) if enabled else (45, 48, 49))
            edge = (222, 197, 135) if active else (102, 129, 127)
            pygame.draw.rect(self.screen, fill, rect, border_radius=5)
            pygame.draw.rect(self.screen, edge, rect, width=1, border_radius=5)
            img = self.hud_compact_font.render(self._fit(label, rect.w - 10), True, (246, 241, 224) if enabled else (135, 140, 137))
            self.screen.blit(img, (rect.x + (rect.w - img.get_width()) // 2, rect.y + (rect.h - img.get_height()) // 2))
            self.crew_sheet_hitboxes.append((rect, action, value, enabled))

        button(x + width - 126, y + 10, 104, 28, "CLOSE [F1]", "close")

        # Main detail sections are always available; only the nested management buttons depend on docking.
        main_ty = y + 65
        tab_gap = 8
        main_tab_w = (width - 44 - tab_gap * 3) // 4
        for i, (key, label) in enumerate((("ship_catch", "SHIP & CATCH"), ("telemetry", "TELEMETRY"), ("crew", "CREW"), ("controls", "CONTROLS"))):
            button(x + 22 + i * (main_tab_w + tab_gap), main_ty, main_tab_w, 32,
                   label, "info_tab", key, True, self.info_sheet_tab == key)

        if self.info_sheet_tab != "crew":
            self._draw_information_page(x, y, width, height, self.info_sheet_tab)
            return

        # Existing Crew/Shore/Hire interface nested under the main CREW tab.
        ty = main_ty + 41
        compact_sheet = width < 582
        narrow_sheet = width < 900
        tab_w = min(140, max(82, int((width - 161) / 3)))
        for i, (key, label) in enumerate((("crew", "ABOARD"), ("shore", "SHORE"), ("hire", "HIRE"))):
            button(x + 20 + i * (tab_w + 8), ty, tab_w, 30, label, "tab", key, True, self.crew_sheet_tab == key)
        if self.crew_sheet_tab == "shore":
            shore_wait_label = "CANCEL WAIT" if self.shore_wait_active else "WAIT UNTIL RESTED"
            has_returning_shore_party = bool(self._shore_returning_crew())
            wait_y = ty + (38 if narrow_sheet else 0)
            wait_x = x + 20 if narrow_sheet else x + width - 215
            button(wait_x, wait_y, 190, 30, shore_wait_label, "wait_shore",
                   enabled=self.docked() and (has_returning_shore_party or self.shore_wait_active),
                   active=self.shore_wait_active)
        if self.crew_sheet_tab == "shore" and narrow_sheet:
            header_y = ty + 76
        else:
            header_y = ty + 39
        if compact_sheet and self.crew_sheet_tab == "shore":
            header_y = ty + 76
        if self.crew_sheet_tab == "crew":
            headings = "NAME / ROLE                  HEALTH  FATIGUE  SKILL  DUTY"
        elif self.crew_sheet_tab == "shore":
            headings = "NAME / ROLE                  HEALTH  FATIGUE  SKILL  SHORE STATUS"
        else:
            headings = "AVAILABLE RECRUITS          SKILL  CAUTION  HIRING FEE"
        self.screen.blit(self.hud_compact_font.render(headings, True, (206, 205, 184)), (x + 22, header_y))
        rows = self._generate_full_sheet_rows()
        list_top, list_bottom = header_y + 23, y + height - 47
        row_h = 49
        max_rows = max(1, (list_bottom - list_top) // row_h)
        self.crew_sheet_scroll = int(clamp(self.crew_sheet_scroll, 0, max(0, len(rows) - max_rows)))
        shown = rows[self.crew_sheet_scroll:self.crew_sheet_scroll + max_rows]
        if not rows:
            note = {"crew": "No sailors currently aboard.", "shore": "Nobody is currently ashore.",
                    "hire": "No recruits available; return to the dock later for another hiring board."}[self.crew_sheet_tab]
            self.screen.blit(self.font.render(note, True, (222, 210, 184)), (x + 28, list_top + 10))
        for i, (kind, item) in enumerate(shown):
            ry = list_top + i * row_h
            row_rect = pygame.Rect(x + 16, ry, width - 32, row_h - 3)
            pygame.draw.rect(self.screen, (27, 39, 43) if i % 2 == 0 else (23, 34, 38), row_rect, border_radius=4)
            if kind in ("crew", "shore"):
                sailor = item
                role = Sailor.ROLE_NAMES[sailor.role].upper()
                name = self.hud_compact_font.render("%-19s %-9s" % (sailor.name[:19], role), True, (245, 240, 222))
                self.screen.blit(name, (row_rect.x + 8, ry + 5))
                status_text = shore_status_label(sailor, Sailor.SHORE) if self.crew_sheet_tab == "shore" else (
                    "REST" if sailor.duty == "rest" else (sailor.duty.upper() or sailor.task.upper()))
                metrics = "%3d%%  FAT %3d%%  SK %.2f  %s" % (
                    round(100*sailor.health), round(100*sailor.fatigue), sailor.skill, status_text)
                bw, bh = (112 if narrow_sheet else 128), 28
                bx = row_rect.right - bw - 8
                metrics_max = max(40, bx - row_rect.x - 16)
                self.screen.blit(self.hud_compact_font.render(self._fit(metrics, metrics_max), True, (195, 211, 204)),
                                 (row_rect.x + 8, ry + 25 if narrow_sheet else ry + 7))
                if kind == "crew":
                    can_send = self.docked() and sailor.role == Sailor.DECKHAND
                    label = "SEND ASHORE" if can_send else ("COMMAND" if sailor.role != Sailor.DECKHAND else "DOCK ONLY")
                    button(bx, ry + 9 if narrow_sheet else ry + 5, bw, bh, label, "send_ashore", sailor, can_send)
                else:
                    shore_bw = 104 if narrow_sheet else 128
                    bx = row_rect.right - (112 if narrow_sheet else 128) - 8
                    button(bx - shore_bw - 6, ry + 9 if narrow_sheet else ry + 5, shore_bw, bh,
                           "AUTO-RETURN" if sailor.keep_ashore else "KEEP ASHORE", "toggle_shore", sailor,
                           self.docked() and sailor.role == Sailor.DECKHAND)
                    button(bx, ry + 9 if narrow_sheet else ry + 5, (112 if narrow_sheet else 128), bh,
                           "BRING ABOARD", "bring_aboard", sailor, self.docked())
            else:
                candidate = item
                label = "%-20s" % candidate["name"]
                skill_line = "SK %.2f   CAUTION %.2f   %d yen" % (candidate["skill"], candidate["caution"], candidate["fee"])
                bw, bh = (112 if narrow_sheet else 136), 28
                hire_x = row_rect.right - (2*bw + 18)
                self.screen.blit(self.hud_compact_font.render(label, True, (245, 240, 222)), (row_rect.x + 8, ry + 5))
                self.screen.blit(self.hud_compact_font.render(self._fit(skill_line, max(40, hire_x - row_rect.x - 16)),
                                 True, (195, 211, 204)), (row_rect.x + 8, ry + 25 if narrow_sheet else ry + 7))
                button(hire_x, ry + 9 if narrow_sheet else ry + 5, bw, bh, "HIRE ABOARD", "hire_aboard",
                       self.crew_sheet_scroll + i, self.docked())
                button(row_rect.right - bw - 8, ry + 9 if narrow_sheet else ry + 5, bw, bh, "HIRE ASHORE", "hire_shore",
                       self.crew_sheet_scroll + i, self.docked())
        footer = ("F1 close | 1 Aboard | 2 Shore | 3 Hire | Wait until rested returns eligible crew"
                  if self.crew_sheet_tab == "shore" else
                  "F1 close | 1 Aboard | 2 Shore | 3 Hire | Mouse wheel / Up-Down scroll")
        self.screen.blit(self.hud_compact_font.render(self._fit(footer, width - 44), True, (200, 195, 175)),
                         (x + 22, y + height - 27))

    def pick_hatch(self):
        """Alternate between open hatch covers when possible; if none are open, pick the next one and wait there."""
        order = (self.hatch_flip, 1 - self.hatch_flip)
        i = next((idx for idx in order if self.ship.hatch_is_open("hold_%d" % (idx + 1))), order[0])
        self.hatch_flip = 1 - i
        return i

    def stow(self, c, hatch_idx=None):
        """Stow catch only through an open hold hatch; direct system calls may omit hatch_idx."""
        if hatch_idx is not None and not self.ship.hatch_is_open("hold_%d" % (int(hatch_idx) + 1)):
            return False
        self.hold.append(c)
        if self.ice > 0:
            self.ice = max(0.0, self.ice - 0.8 * clamp((c.core - 1.0) / 16.0, 0.0, 1.5))
        return True

    def _ice(self, dt):
        self.ice_trimmed_time = max(0.0, self.ice_trimmed_time - dt)
        hold_water = clamp(self.ship.hold_flood, 0.0, 1.0)
        if self.ice > 0:
            melt_factor = 0.68 if self.ice_trimmed_time > 0.0 else 1.0
            melt_factor *= 1.0 + 0.9 * hold_water
            self.ice = max(0.0, self.ice - (0.04 + 0.005 * len(self.hold)) * melt_factor * dt)
            target_temp = 0.5 + 7.0 * hold_water
            cool_tau = 60.0 if hold_water < 0.2 else 28.0
            self.hold_temp += (target_temp - self.hold_temp) * (1.0 - math.exp(-dt / cool_tau))
            if self.ice <= 0 and self.ice_warn < 2:
                self.ice_warn = 2
                self.crew.say("The ice has run out! The catch is warming in the hold.")
            elif 0 < self.ice < 20 and self.ice_warn < 1:
                self.ice_warn = 1
                self.crew.say("Ice is running low. Better think about the harbour.")
        else:
            target_temp = 16.0 + 5.0 * hold_water
            self.hold_temp += (target_temp - self.hold_temp) * (1.0 - math.exp(-dt / 300.0))

    def catch_report_lines(self, limit=4):
        """Readable catch condition report for the hold: handling, quality grade, core temperature and storage."""
        if not self.hold:
            return ["Trip catch report: no fish in the hold."]
        avg = sum(c.quality for c in self.hold) / len(self.hold)
        grades = {}
        for fish in self.hold:
            grades[fish.grade()] = grades.get(fish.grade(), 0) + 1
        storage = "iced" if self.ice > 0 and self.hold_temp <= 5.0 else ("chilling" if self.ice > 0 else "warming")
        reports = ["Trip catch report: %d fish, average quality %d%% (%s grade); hold %.1f C, %s." %
                   (len(self.hold), round(avg * 100), grade_of(avg)[0], self.hold_temp, storage)]
        count = max(0, int(limit))
        for fish in self.hold[:count]:
            if fish.bled and fish.gutted:
                handling = "bled and dressed"
            elif fish.bled:
                handling = "bled, not dressed"
            elif fish.alive:
                handling = "alive / unprocessed"
            else:
                handling = "unbled"
            fish_storage = "iced" if self.ice > 0 and self.hold_temp <= 5.0 else ("cooling" if self.ice > 0 else "warming")
            reports.append("Catch report: %s — %s, quality %d%% (%s grade), core %.1f C, %s; deck exposure %.0f s." %
                           (fish.name, handling, round(fish.quality * 100), fish.grade(), fish.core,
                            fish_storage, fish.deck_exposure))
        if len(self.hold) > count:
            reports.append("Catch report: %d more fish; grade totals %s." %
                           (len(self.hold) - count, ", ".join("%d %s" % (grades[name], name)
                           for _, name, _ in GRADES if name in grades)))
        return reports

    def hold_text(self):
        n = len(self.hold)
        if not n:
            grade_text, quality = "no catch", 0
        else:
            avg = sum(c.quality for c in self.hold) / n
            grade_text, quality = grade_of(avg)[0], round(avg * 100)
        storage = "COLD" if self.ice > 0 and self.hold_temp <= 5.0 else ("CHILLING" if self.ice > 0 else "WARMING")
        return "Hold: %d fish, avg %d%% %s ~%d yen | ice %d/%d, %.1f C (%s)" % (
            n, quality, grade_text, sum(c.sale_value() for c in self.hold), self.ice, ICE_CAP, self.hold_temp, storage)

    # --- fuel, bait, sea state
    def take_bait(self):
        """One unit of bait for a hook: the chosen kind, or whatever there is most of. (None, 0) means a bare hook."""
        t = self.bait_sel
        if self.bait[t] < 1.0:
            t = max(self.bait, key=lambda k: self.bait[k])
        if self.bait[t] < 1.0:
            if not self.bait_warned:
                self.crew.say("Out of bait! The hooks go out bare.")
                self.bait_warned = True
            return None, 0.0
        self.bait[t] -= 1.0
        return t, self.bait_fresh[t]

    def auto_bait(self):
        self.bait_sel = max(self.bait, key=lambda k: self.bait[k])

    def bait_total(self):
        return sum(self.bait.values())

    def cycle_bait(self):
        keys = list(BAITS)
        self.bait_sel = keys[(keys.index(self.bait_sel) + 1) % len(keys)]
        self.crew.say("Bait: %s (%d in the boxes, %d yen a hook)." % (self.bait_sel, self.bait[self.bait_sel], BAITS[self.bait_sel]))

    def _say_station(self, text):
        self.crew.say(text)

    def can_enter_wheelhouse(self, sailor):
        """Only the current helm operator and the assigned radio operator can enter."""
        return sailor is not None and sailor.mode == Sailor.ABOARD and sailor in (self.helm_operator, self.radio_operator)

    def wheelhouse_goal_allowed(self, sailor, goal):
        """A station keeper can route only to their own station, never roam the cabin."""
        if not self.can_enter_wheelhouse(sailor):
            return False
        goal = V(goal)
        if sailor is self.helm_operator:
            target = self.ship.wheelhouse_stations["helm"]
            return goal.distance_to(target) <= 42.0
        if sailor is self.radio_operator:
            target = self.ship.wheelhouse_stations["radio"]
            return goal.distance_to(target) <= 42.0
        return False

    def _set_helm_operator(self, operator):
        if operator is self.radio_operator:
            return False
        if operator is not None and (operator.mode != Sailor.ABOARD or operator.role not in (Sailor.CAPTAIN, Sailor.VETERAN)):
            return False
        old = self.helm_operator
        if old is operator:
            return True
        if old is not None and old is not next((s for s in self.sailors if s.role == Sailor.CAPTAIN), None):
            old._release()
            old.duty = self._helm_previous_duty
            old.ordering, old.order_hold = False, 0.0
            old.task, old.think_t = "idle", 0.0
        if operator is not None and operator.role != Sailor.CAPTAIN:
            self._helm_previous_duty = operator.duty if operator.duty != "post" else ""
            operator._release()
            operator.duty = "post"
            operator.ordering, operator.order_hold = False, 0.0
            operator.task, operator.think_t = "idle", 0.0
        self.helm_operator = operator
        captain = next((s for s in self.sailors if s.role == Sailor.CAPTAIN), None)
        if captain is not None:
            captain.duty = "rest" if self.captain_resting else ""
            captain.ordering, captain.order_hold = False, 0.0
            captain.task, captain.think_t = "idle", 0.0
        if operator is not None:
            operator.think_t = 0.0

        # A relieved helmsman must physically vacate the wheelhouse. Merely
        # clearing his post duty left him idling upstairs, where he could block
        # the captain's return and look like a second man still claiming the helm.
        if (old is not None and old is not operator and old is not self.radio_operator
                and old.mode == Sailor.ABOARD and old.level == Level.WHEELHOUSE):
            old.order_to(self.ship.markers["rest_spot"], Level.MAIN)
        captain = next((s for s in self.sailors if s.role == Sailor.CAPTAIN), None)
        if old is not None and old.role == Sailor.CAPTAIN and operator is not None and operator is not old:
            self.crew.say("Captain: I'm taking a rest. %s has the helm." % operator.name)
        elif operator is not None and operator.role == Sailor.CAPTAIN and old is not None and old is not operator:
            self.crew.say("Captain: I'm back on watch. %s is relieved." % old.name)
        return True

    def _eligible_radio_candidates(self):
        excluded_tasks = {"set", "haul", "dress", "gaff", "rush", "rescue", "engine"}
        # Reserve the veteran for helm relief. Radio watch is a deckhand's permanent station.
        return [s for s in self.sailors
                if s.mode == Sailor.ABOARD and s.role == Sailor.DECKHAND
                and s is not self.helm_operator and s is not self.radio_operator
                and s.task not in excluded_tasks]

    def assign_radio_operator(self, sailor, announce=True):
        """Assign one persistent wireless operator; right-clicking RADIO also invokes this."""
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.role != Sailor.DECKHAND or sailor is self.helm_operator:
            if announce:
                self._say_station("Radio: Assign a deckhand to the wireless; the captain and veteran are reserved for the helm.")
            return False
        old = self.radio_operator
        if old is sailor:
            sailor.duty = "radio"
            sailor.think_t = 0.0
            return True
        if old is not None:
            old._release()
            old.duty = ""
            old.ordering, old.order_hold = False, 0.0
            old.task, old.think_t = "idle", 0.0
        self.radio_operator = sailor
        self.radio_duty_active = True
        # A relieved radio operator must physically leave the cabin; upstairs idle
        # sailors otherwise remain in place and can crowd the new operator out.
        if old is not None and old.mode == Sailor.ABOARD and old.level == Level.WHEELHOUSE:
            old.order_to(self.ship.markers["rest_spot"], Level.MAIN)
        sailor._release()
        sailor.duty = "radio"
        sailor.ordering, sailor.order_hold = False, 0.0
        sailor.task, sailor.think_t = "idle", 0.0
        if announce:
            self._say_station("Radio: %s assigned to keep watch on 2182 kHz." % sailor.name)
        return True

    def _ensure_radio_operator(self):
        if self.radio_operator is not None and self.radio_operator.mode == Sailor.ABOARD:
            return self.radio_operator
        self.radio_operator = None
        candidates = self._eligible_radio_candidates()
        if not candidates:
            # A radio watch may interrupt a non-critical deckhand task, but never takes the veteran from relief.
            candidates = [s for s in self.sailors if s.mode == Sailor.ABOARD
                          and s.role == Sailor.DECKHAND and s is not self.helm_operator]
        if not candidates:
            return None
        radio_pos = self.ship.wheelhouse_stations["radio"]
        def score(s):
            busy_penalty = 500.0 if s.working or s.task in ("set", "haul", "engine", "dress", "rescue", "rush") else 0.0
            level_penalty = 0.0 if s.level == Level.WHEELHOUSE else 350.0
            role_penalty = 0.0 if s.role == Sailor.DECKHAND else 90.0
            return busy_penalty + level_penalty + role_penalty + s.pos.distance_to(radio_pos)
        operator = min(candidates, key=score)
        self.assign_radio_operator(operator, announce=True)
        return operator

    def _update_station_roles(self, dt=0.0):
        """Keep helm/radio assignments exclusive and use the veteran as captain's relief."""
        # A muster is a mandatory ship-wide order: station automation must not
        # immediately send the captain/helm/radio watch back to their posts.
        if self.muster_active:
            self.helm_operator = None
            self.radio_duty_active = False
            self.radio_operator = None
            return
        captain = next((s for s in self.sailors if s.role == Sailor.CAPTAIN), None)
        if captain is not None and captain.mode == Sailor.ABOARD:
            if captain.duty == "rest" and not self.captain_resting:
                self.captain_resting, self.captain_rest_elapsed = True, 0.0
            if not self.captain_resting and captain.fatigue >= 0.78:
                self.captain_resting, self.captain_rest_elapsed = True, 0.0
            if self.captain_resting:
                if captain.duty != "rest":
                    captain.duty = "rest"
                    captain.ordering, captain.order_hold = False, 0.0
                    captain.think_t = 0.0
                rest_pos = self.ship.markers["rest_spot"]
                if captain.sleeping_in_bunk and captain.level == Level.BELOW:
                    self.captain_rest_elapsed += max(0.0, dt)
                elif captain.level == Level.MAIN and captain.pos.distance_to(rest_pos) < 85.0:
                    self.captain_rest_elapsed += max(0.0, dt)
                if self.captain_rest_elapsed >= 6.0 and captain.fatigue <= 0.20:
                    self.captain_resting, self.captain_rest_elapsed = False, 0.0
                    captain.duty = ""
            elif captain.duty == "rest":
                captain.duty = ""

        if self.captain_resting or captain is None or captain.mode != Sailor.ABOARD:
            # Only the designated veteran is qualified as relief. Never let several
            # deckhands converge on the wheelhouse when the relief position is vacant.
            relief = self.relief_helmsman
            if relief is not None and relief.mode == Sailor.ABOARD and relief is not self.radio_operator:
                self._set_helm_operator(relief)
            elif self.helm_operator is not None and self.helm_operator.mode != Sailor.ABOARD:
                self._set_helm_operator(None)
        elif captain is not None and captain.mode == Sailor.ABOARD:
            self._set_helm_operator(captain)

        if self.radio_duty_active and (self.radio_operator is None or self.radio_operator.mode != Sailor.ABOARD
                                       or self.radio_operator is self.helm_operator):
            lost_operator = self.radio_operator
            self.radio_operator = None
            if lost_operator is not None:
                lost_operator.duty = ""
                lost_operator.ordering, lost_operator.order_hold = False, 0.0
                if lost_operator.mode == Sailor.ABOARD:
                    lost_operator._release()
                    lost_operator.task, lost_operator.think_t = "idle", 0.0
            self._ensure_radio_operator()
        elif self.pending_radio_calls and (self.radio_operator is None or self.radio_operator.mode != Sailor.ABOARD):
            self._ensure_radio_operator()

    def _log_stamp(self):
        w = getattr(self, "world", None)
        if w is None:
            return {"date": "01 APR 1962", "clock": "06:30", "elapsed": 0.0}
        h = w.hour()
        return {"date": w.calendar_date_text(),
                "clock": "%02d:%02d" % (int(h), int((h % 1.0) * 60)),
                "elapsed": float(w.time)}

    def record_log_entry(self, text):
        """Record a dated crew event or radio turn for the Ship's Notebook."""
        raw = str(text).strip()
        if not raw:
            return
        stamp = self._log_stamp()
        if raw.lower().startswith("radio:"):
            body = raw.split(":", 1)[1].strip()
            match = re.match(r"\[([^\]]+)\]\s*:\s*(.*)", body)
            if match:
                speaker, body = match.group(1).strip().upper(), match.group(2).strip()
            else:
                low = body.lower()
                if any(word in low for word in ("coast station", "harbour control", "harbour market", "weather bulletin")):
                    speaker = "COAST / HARBOUR STATION"
                elif any(word in low for word in ("maru", "to fleet traffic", "any vessel", "calling any vessel")):
                    speaker = "FLEET VESSEL"
                else:
                    speaker = "RADIO TRAFFIC"
            entry = dict(stamp, speaker=speaker, text=body, kind="TX" if speaker == "VESSEL" else "RX")
            self.radio_log_entries.append(entry)
            limit = getattr(self, "log_entry_limit", 600)
            del self.radio_log_entries[:-limit]
            return

        speaker, body = "SHIP", raw
        if ":" in raw[:36]:
            candidate, remain = raw.split(":", 1)
            if candidate and len(candidate) <= 28:
                speaker, body = candidate.strip().upper(), remain.strip()
        low = raw.lower()
        kind = "ORDER" if any(t in low for t in ("order", "ordered", "going to", "heading for", "take the helm", "stand by", "muster", "rescue")) else "LOG"
        entry = dict(stamp, speaker=speaker, text=body, kind=kind)
        self.crew_log_entries.append(entry)
        limit = getattr(self, "log_entry_limit", 600)
        del self.crew_log_entries[:-limit]

    def _refresh_market_index(self):
        self.market = storm_price_index(self.market_base, self.market_storm_surge)
        return self.market

    def on_weather_transition(self, old_kind, new_kind):
        """Storm damage to supply and fishing effort raises the auction index temporarily."""
        if new_kind == "storm" and old_kind != "storm":
            # A stronger/longer storm disrupts landings; the surge then slowly recedes.
            self.market_storm_surge = add_storm_surge(
                self.market_storm_surge, float(getattr(self.weather, "wind", 0.7)))
            self._refresh_market_index()
            self.record_log_entry("Market watch: storm disruption has reduced landings; fish prices spike to x%.2f." % self.market)
            self.queue_broadcast_conversation([
                (0.0, "COAST STATION", "Weather warning. A storm is crossing the outer grounds. Secure loose gear and keep clear of the rails. Over.", "radio"),
                (3.5, "TENYO MARU", "Coast station, Tenyo Maru. We have heavy motion at the stern and are suspending work. Over.", "radio"),
                (4.0, "COAST STATION", "Tenyo Maru, roger. All vessels are advised to reduce speed and report any vessel in distress. Out.", "radio"),
            ], priority=PRIORITY_HIGH, source="weather_transition")

    def _update_market_surge(self, dt):
        dt = max(0.0, float(dt))
        if self.market_storm_surge > 0.0 and dt > 0.0:
            self.market_storm_surge = decay_storm_surge(self.market_storm_surge, dt, DAY_LEN)
            self._refresh_market_index()

    def _notebook_entries(self, section):
        if section == 0:
            # Crew activity is a running log: newest decisions are easiest to inspect first.
            return list(reversed(self.crew_log_entries))
        if section == 1:
            # Keep radio traffic in transmission order. The renderer pages backward
            # from the newest block, but turns within each displayed page stay chronological.
            return list(self.radio_log_entries)
        if section == 4:
            # Gut-book records are historical snapshots, newest discovery first.
            return list(reversed(self.gut_book_entries))
        return []

    def show_radio_dialogue(self, text):
        """Display radio traffic in a persistent screen-space bubble, independent of deck view."""
        body = text.strip()
        if body.lower().startswith("radio:"):
            body = body.split(":", 1)[1].strip()
        match = re.match(r"\[([^\]]+)\]\s*:\s*(.*)", body)
        if match:
            self.radio_bubble_speaker = match.group(1).strip().upper()
            body = match.group(2).strip()
        else:
            self.radio_bubble_speaker = "COAST / FLEET RADIO"
        self.radio_bubble_text = body or text.strip()
        # A radio turn must remain readable, but a long reply should not freeze the
        # exchange for twelve seconds. The conversation director adds its own pacing.
        self.radio_bubble_t = clamp(2.35 + len(self.radio_bubble_text) * 0.018, 2.6, 5.2)

    def radio_station_ok(self):
        """Only the named radio operator counts, not a sailor merely passing the set."""
        op = self.radio_operator
        if op is None or op.mode != Sailor.ABOARD or op.level != Level.WHEELHOUSE:
            return False
        if op.duty != "radio":
            return False
        radio = self.ship.wheelhouse_stations["radio"]
        return op.pos.distance_to(radio) < 58.0

    def radio_call(self, kind):
        """Request a coast-station call. Tow requests remain active until delivered."""
        if kind not in ("weather", "auction", "tow"):
            return False
        if kind == "tow":
            if self.tow_transit_active:
                self.crew.say("Radio: The tug already has the towline fast. Stand by for the berth.")
                return False
            if self.docked():
                self.tow_request_active = False
                self.tow_retry_elapsed = 0.0
                self.tow_failed_call_count = 0
                self.crew.say("Radio: We are alongside; no tow is needed.")
                return False
            # Keep the request latched even if the operator cannot answer now or
            # this transmission is lost in static. _update_radio retries it.
            if not self.tow_request_active:
                self.tow_failed_call_count = 0
            self.tow_request_active = True
        self._prepare_broadcast_priority(PRIORITY_HIGH if kind == "tow" else PRIORITY_MEDIUM)
        operator = self.radio_operator if self.radio_operator and self.radio_operator.mode == Sailor.ABOARD else None
        if operator is None:
            operator = self._ensure_radio_operator()
        if operator is None:
            self.crew.say("Radio: No available hand can take the wireless watch.")
            self.radio_message, self.radio_message_t = "NO RADIO OPERATOR", 5.0
            if kind == "tow":
                self.tow_retry_elapsed = max(self.tow_retry_elapsed, 8.0)
            return False
        # One wireless exchange at a time. Calls pressed during a conversation wait
        # their turn instead of replacing the station's current spoken line.
        if self.radio_calls or self.radio_transcript_queue or self.pending_radio_calls or self.radio_bubble_t > 0.25:
            if kind not in self.pending_radio_calls and not any(c.get("kind") == kind for c in self.radio_calls):
                self.pending_radio_calls.append(kind)
            self.radio_message, self.radio_message_t = "WIRELESS OCCUPIED — CALL QUEUED", 4.0
            return True
        if not self.radio_station_ok():
            if kind not in self.pending_radio_calls:
                self.pending_radio_calls.append(kind)
            self.radio_message, self.radio_message_t = "RADIO OPERATOR PROCEEDING TO SET", 5.0
            self.crew.say("Radio: %s is taking the wireless. Call queued." % operator.name)
            return True
        return self._start_radio_call(kind)

    def _start_radio_call(self, kind):
        """Queue an actual transmission after the assigned operator reaches the set."""
        w, wx = self.world, self.weather
        if kind == "tow" and self.docked():
            self.tow_request_active = False
            self.tow_retry_elapsed = 0.0
            self.tow_failed_call_count = 0
            self.crew.say("Radio: We're alongside; no tow needed.")
            return False
        if kind == "tow" and (self.tow_arrival_t > 0 or any(c["kind"] == "tow" for c in self.radio_calls)
                              or (self.tow_escort is not None and self.tow_escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW"))
                              or self.tow_transit_active):
            self.crew.say("Radio: A tow has already been requested.")
            return False

        priority = PRIORITY_HIGH if kind == "tow" else PRIORITY_MEDIUM
        self._prepare_broadcast_priority(priority)
        self.radio_transcript_priority = priority
        ranges = {"weather": 5200.0, "auction": 2800.0, "tow": 9000.0}
        max_range = ranges[kind]
        distance = w.dist()
        in_range = distance <= max_range
        strength = clamp(1.0 - distance / max_range, 0.0, 1.0)
        interference = 0.24 * wx.wind + 0.22 * wx.rain + 0.18 * wx.fog
        # Tow replies depend on the actual wireless clarity estimate as well as distance.
        clarity = clamp(float(getattr(self.radio, "signal_quality", 0.65)), 0.05, 1.0)
        if in_range:
            chance = clamp((0.40 + 0.52 * strength) * (0.45 + 0.55 * clarity) - interference * 0.55,
                           0.04, 0.90)
            if kind == "tow":
                # The coast station may hear us poorly in a storm, but repeated
                # calls must still become more effective instead of rolling the
                # minimum in-range chance indefinitely.
                chance = clamp(chance + min(0.25, 0.02 * self.tow_failed_call_count), 0.04, 0.95)
        elif kind == "tow":
            # Long-range contact stays harder than a close call, but repeated
            # unanswered requests become more likely to reach a listener. This
            # avoids an offshore request effectively rolling a 0.4% chance forever.
            chance = tow_long_range_response_probability(
                distance=distance, max_range=max_range, clarity=clarity,
                interference=interference, failed_calls=self.tow_failed_call_count,
            )
        else:
            chance = 0.0
        success = random.random() < chance
        delay = 1.8 + 10.0 * (1.0 - strength) + 5.0 * interference
        failures = {
            "weather": "Radio: Static and fading signal; the coast station could not copy us.",
            "auction": "Radio: Market office unreadable through the static; no price report.",
            "tow": "Radio: No reply to the tow call. Keep transmitting; signal is weak.",
        }
        if kind == "weather":
            forecast = self.weather.forecast(4)[1:4]  # tomorrow plus the following two days
            reply_lines = ["Roger, vessel. Three-day coastal marine outlook follows."]
            reply_lines.extend(item.radio_line() for item in forecast)
            reply_lines.append("That concludes the forecast. Keep listening for changes; coast station standing by. Over.")
            payload = " ".join(reply_lines)
            request = "Coast station, this is the fishing vessel calling for the next three days' marine forecast. Over."
        elif kind == "auction":
            payload = ("Harbour market report — buyer index x%.2f. Storm disruption premium is %.0f%%. "
                       "Sashimi grade commands the best price; handle and chill the catch promptly. Over." %
                       (self.market, 100.0 * self.market_storm_surge))
            reply_lines = [payload]
            request = "Harbour market office, report today's buyer index and any storm disruption premium. Over."
        else:
            payload = "Tow request copied. Coast Guard launch is being dispatched; maintain a safe heading and stand by."
            reply_lines = ["We copy your tow request. Stand by for the launch.",
                           "Coast Guard launch is being dispatched; maintain a safe heading and stand by. Over."]
            request = "Mayday relay to coast station: request tow assistance. We are unable to make harbour under our own power. Over."
        self.radio_calls.append({"timer": delay, "kind": kind, "success": success, "payload": payload,
                                 "reply_lines": reply_lines, "request": request,
                                 "failure": failures[kind], "distance": distance})
        self.radio_message, self.radio_message_t = "TUNING 2182 kHz AM/SSB…", 4.0
        # The outgoing call is the first visible/logged turn. The coast station's
        # acknowledgement and report are staged later as separate turns.
        self.broadcast_visible_priority = priority
        self.broadcast_visible_channel = "radio"
        self.broadcast_visible_source = "requested_radio_call"
        self.crew.say("Radio: [VESSEL]: %s" % request)
        return True

    def queue_broadcast_conversation(self, lines, priority=PRIORITY_LOW, channel="radio", source="broadcast"):
        """Queue timed speech. Urgent traffic interrupts lower-priority visible speech."""
        priority = int(priority)
        # The selectable radio panel stages ordinary replies locally. A critical
        # MAYDAY must also pre-empt that modal exchange, otherwise its UI would
        # hide the incoming emergency even though the broadcast director is ready.
        if priority >= PRIORITY_CRITICAL and getattr(self, "radio_ui_open", False):
            selected_id = getattr(self, "radio_ui_selected_ship_id", None)
            history = getattr(self, "radio_ui_histories", {}).get(selected_id) if selected_id else None
            if history is not None:
                visible_count = max(0, min(len(history.get("lines", [])), int(history.get("visible_count", 0))))
                del history["lines"][visible_count:]
                history["visible_count"] = visible_count
                self.radio_ui_active_end[selected_id] = visible_count
            self.radio_ui_open = False
            self.radio_ui_status = "DISTRESS TRAFFIC — current exchange interrupted."
        visible_priority = int(getattr(self, "broadcast_visible_priority", 0))
        radio_priority = int(getattr(self, "radio_transcript_priority", 0))
        interrupted = self.broadcast_director.enqueue(lines, priority=priority, channel=channel, source=source)
        has_broadcast_visible = bool(self.broadcast_visible_source)
        should_interrupt_visible = has_broadcast_visible and priority > visible_priority and (
            (self.broadcast_visible_channel == "radio" and self.radio_bubble_t > 0.0) or
            (self.broadcast_visible_channel in ("crew", "intercom", "harbour") and
             any(getattr(s, "speech_t", 0.0) > 0.0 for s in self.sailors))
        )
        should_interrupt_transcript = priority > radio_priority and bool(self.radio_transcript_queue)
        if interrupted or should_interrupt_visible or should_interrupt_transcript:
            self._clear_lower_priority_broadcast(priority)
        return True

    def _clear_lower_priority_broadcast(self, priority):
        """Remove lower-priority broadcast speech, but never cancel an unrelated crew line."""
        priority = int(priority)
        visible_is_lower = bool(self.broadcast_visible_source) and self.broadcast_visible_priority < priority
        if visible_is_lower:
            if self.broadcast_visible_channel == "radio":
                self.radio_bubble_t = 0.0
                self.radio_bubble_text = ""
            elif self.broadcast_visible_channel in ("crew", "intercom", "harbour"):
                for sailor in getattr(self, "sailors", []):
                    sailor.speech_t = 0.0
        if self.radio_transcript_priority < priority and self.radio_transcript_queue:
            self.radio_transcript_queue.clear()
            self.radio_transcript_priority = 0
            if self.broadcast_visible_source == "requested_radio_call" and self.broadcast_visible_priority < priority:
                self.radio_bubble_t = 0.0
                self.radio_bubble_text = ""
                visible_is_lower = True
        if visible_is_lower:
            self.broadcast_visible_priority = 0
            self.broadcast_visible_channel = ""
            self.broadcast_visible_source = ""

    def _prepare_broadcast_priority(self, priority):
        """Let a player-requested call take the wireless from non-urgent ambient chatter."""
        priority = int(priority)
        self.broadcast_director.interrupt_below(priority)
        self.broadcast_director.discard_pending_below(priority)
        self._clear_lower_priority_broadcast(priority)

    def _broadcast_can_emit(self, channel, priority):
        """Prevent speech bubbles and radio replies from overwriting one another."""
        priority = int(priority)
        if self.radio_transcript_queue and priority <= self.radio_transcript_priority:
            return False
        if channel == "radio":
            active_call_priority = max((PRIORITY_HIGH if call.get("kind") == "tow" else PRIORITY_MEDIUM
                                        for call in self.radio_calls), default=0)
            if self.radio_calls and priority <= active_call_priority:
                return False
            return self.radio_bubble_t <= 0.05 and not self.radio_transcript_queue
        # Critical distress traffic may cut in over deck chatter; ordinary lines wait.
        if priority >= PRIORITY_CRITICAL:
            return True
        if self.radio_bubble_t > 0.05:
            return False
        return not any(getattr(s, "speech_t", 0.0) > 0.05 for s in self.sailors
                       if getattr(s, "mode", None) == Sailor.ABOARD)

    def _present_broadcast_turn(self, conversation, turn):
        self.broadcast_visible_priority = conversation.priority
        self.broadcast_visible_channel = turn.channel
        self.broadcast_visible_source = conversation.source
        if turn.channel == "radio":
            self.crew.say("Radio: [%s]: %s" % (turn.speaker, turn.text))
            if str(conversation.source).startswith("ambient_ship_radio:"):
                # Log on emission, not enqueue, so interrupted/unheard lines are not
                # falsely represented as part of the player's received transcript.
                self.record_log_entry("Radio: [%s]: %s" % (turn.speaker, turn.text))
        else:
            self.crew.say("%s: %s" % (turn.speaker, turn.text))

    def _queue_ambient_crew_conversation(self, dt):
        """Sparse crew/intercom chatter: the ordinary state of the watch is quiet."""
        dt = max(0.0, float(dt))
        docked_now = self.docked()
        if self._broadcast_was_docked is None:
            self._broadcast_was_docked = docked_now
        elif docked_now and not self._broadcast_was_docked:
            self.broadcast_harbour_gossip_count = 0
            self.broadcast_harbour_extra_timer = random.uniform(100.0, 160.0)
            self.queue_broadcast_conversation([
                (0.0, "Quay hand", "Ahoy, Kōei Maru! Catch looking good?", "harbour"),
                (3.0, "Deck", "Good enough. Is the ice house still open?", "harbour"),
                (3.5, "Quay hand", "Till six. The Ginza buyer is asking after good yellowfin today.", "harbour"),
            ], priority=PRIORITY_LOW, source="arrival_gossip")
            self.broadcast_harbour_gossip_count = 1
        elif not docked_now and self._broadcast_was_docked:
            self.broadcast_harbour_gossip_count = 0
        self._broadcast_was_docked = docked_now

        self.broadcast_crew_chatter_timer -= dt
        if self.broadcast_crew_chatter_timer <= 0.0:
            self.broadcast_crew_chatter_timer = random.uniform(80.0, 130.0)
            busy = (self.broadcast_director.is_busy() or self.radio_bubble_t > 0.05 or
                    bool(self.radio_transcript_queue or self.radio_calls))
            aboard = [s for s in self.sailors if s.mode == Sailor.ABOARD and s.level == Level.MAIN]
            if not busy and not docked_now and len(aboard) >= 2:
                veteran = next((s for s in aboard if s.role == Sailor.VETERAN), None)
                hand = random.choice([s for s in aboard if s is not veteran])
                wx = self.weather
                if wx.storm > 0.55 or wx.wind > 0.8:
                    first = (hand.name, "I can't feel my fingers in this wind.")
                    second = (veteran.name if veteran else "Captain Ishida", "Then keep them clear of the rail and finish the work safely.")
                else:
                    pair = random.choice((
                        ((veteran.name if veteran else "Captain Ishida"), "The sea tells you where the fish are. You just have to look.", hand.name, "And if the sea tells you nothing?"),
                        (hand.name, "My daughter starts school next month. I ought to be home.", (veteran.name if veteran else "Captain Ishida"), "Then make a good trip of it and get home safely."),
                        (hand.name, "Six hours in a swell and my hands won't close. Where's the cook?", (veteran.name if veteran else "Captain Ishida"), "Ask him after the line is secured."),
                    ))
                    first, second = (pair[0], pair[1]), (pair[2], pair[3])
                self.queue_broadcast_conversation([
                    (0.0, first[0], first[1], "crew"),
                    (3.2, second[0], second[1], "crew"),
                ], priority=PRIORITY_LOW, source="deck_chatter")

        self.broadcast_intercom_timer -= dt
        if self.broadcast_intercom_timer <= 0.0:
            self.broadcast_intercom_timer = random.uniform(130.0, 210.0)
            working = self.line.phase in (Longline.SETTING, Longline.HAULING) or self.engine_hold > 0.0
            busy = (self.broadcast_director.is_busy() or self.radio_bubble_t > 0.05 or
                    bool(self.radio_transcript_queue or self.radio_calls))
            if working and not busy:
                if self.line.phase == Longline.HAULING:
                    lines = [
                        (0.0, "Takeda", "Bridge, deck. Fish alongside. Do you want the boat held?", "intercom"),
                        (3.0, "Captain Ishida", "Hold her head to the swell. Two minutes.", "intercom"),
                        (3.0, "Takeda", "Aye. Holding.", "intercom"),
                    ]
                    source = "deck_intercom"
                else:
                    lines = [
                        (0.0, "Engine Room", "Bridge, engine room. Oil pressure steady. Temperature holding at the mark.", "intercom"),
                        (3.0, "Captain Ishida", "Acknowledged. Keep an eye on the cooling water.", "intercom"),
                    ]
                    source = "engine_intercom"
                self.queue_broadcast_conversation(lines, priority=PRIORITY_LOW, source=source)

    def _update_radio(self, dt):
        self.radio.update(dt)
        self.radio_bubble_t = max(0.0, self.radio_bubble_t - dt)
        if self.radio_bubble_t <= 0.0:
            self.radio_bubble_text = ""
            if self.broadcast_director.active is None and not self.radio_transcript_queue:
                self.broadcast_visible_priority = 0
                self.broadcast_visible_channel = ""
                self.broadcast_visible_source = ""
        if (self.pending_radio_calls and self.radio_station_ok() and not self.radio_calls
                and not self.radio_transcript_queue and self.radio_bubble_t <= 0.0
                and not self.broadcast_director.is_busy()):
            kind = self.pending_radio_calls.pop(0)
            self._start_radio_call(kind)
        self.radio_message_t = max(0.0, self.radio_message_t - dt)
        if self.radio_message_t <= 0:
            self.radio_message = ""
        for call in self.radio_calls[:]:
            call["timer"] -= dt
            if call["timer"] > 0:
                continue
            self.radio_calls.remove(call)
            if not call["success"]:
                message = call["failure"]
                self.radio_message = "NO REPLY — STATIC"
                if call.get("kind") == "tow":
                    # Keep the distress call alive as repeated transmissions, not a one-shot event.
                    # Each unanswered call raises the next offshore response chance, preventing
                    # the 0.4% long-range floor from leaving a vessel waiting for many game days.
                    self.tow_failed_call_count = min(20, self.tow_failed_call_count + 1)
                    self.tow_retry_elapsed = 14.0 + 18.0 * (1.0 - clamp(self.radio.signal_quality, 0.0, 1.0))
            else:
                message = call["payload"]
                if call["kind"] == "tow":
                    self.tow_retry_elapsed = 0.0
                    self.tow_failed_call_count = 0
                    # Acknowledgement arrives first; the tow itself takes longer, especially offshore.
                    w = self.world
                    tow_distance_to_berth = w.ship_pos.distance_to(w.berth) / max(0.001, w.scale)
                    self.tow_arrival_t = 8.0 + min(24.0, tow_distance_to_berth / 300.0)
                    harbor_chart = (float(w.berth.x / w.scale), float(w.berth.y / w.scale))
                    self.tow_escort = TowEscort.coast_guard(
                        harbor_chart, enroute_duration=self.tow_arrival_t
                    )
                    self.tow_escort_status_message = "COAST GUARD LAUNCH EN ROUTE"
                    self.tow_escort_status_t = 8.0
                    self.record_log_entry("Radio: Coast Guard launch %s has acknowledged the tow and is coming to our position." % self.tow_escort.callsign)
                    self.radio_message = "TOW ACKNOWLEDGED — COAST GUARD EN ROUTE"
                else:
                    self.radio_message = "COAST STATION REPLY RECEIVED"
            self.radio_message_t = 7.0
            if call["success"]:
                if call.get("kind") == "tow" and self.tow_escort is not None:
                    turns = [
                        ("HAKODATE COAST RADIO", "Fishing vessel, your tow request is acknowledged. Coast Guard launch %s is responding. Over." % self.tow_escort.callsign),
                        (self.tow_escort.callsign, "Fishing vessel, this is %s. We have your call and are coming to your position. Keep the wireless open. Over." % self.tow_escort.callsign),
                        ("VESSEL", "%s, received. We will stand by. Out." % self.tow_escort.callsign),
                    ]
                else:
                    turns = [("COAST STATION", "Roger, fishing vessel. This is the coast station. Over.")]
                    turns.extend(("COAST STATION", str(reply)) for reply in call.get("reply_lines", [message]))
                    turns.append(("VESSEL", "Received, coast station. We will act on the report. Out."))
            else:
                turns = [
                    ("VESSEL", "Coast station, say again? We are receiving static. Over."),
                    ("COAST STATION", str(message).replace("Radio:", "", 1).strip()),
                ]
            self.radio_transcript_queue.extend(turns)
        # Sparse crew/intercom/habour exchanges use the same priority director.
        self._queue_ambient_crew_conversation(dt)
        # Incoming coast/fleet traffic is a timed conversation, not a single disposable line.
        staffed = self.radio_station_ok()
        radio_busy = bool(self.radio_calls or self.pending_radio_calls or self.radio_transcript_queue
                          or self.radio_bubble_t > 0.25 or self.broadcast_director.is_busy())
        broadcast = self.radio.poll_random_conversation(
            dt, staffed=staffed, busy=radio_busy, docked=self.docked(), line_phase=self.line.phase)
        if broadcast:
            self.queue_broadcast_conversation(
                broadcast["lines"], priority=broadcast["priority"], source=broadcast["source"])

        # The director emits at most one timed line. Legacy player-call turns remain
        # compatible, but wait behind active conversations and retain their priority.
        self.broadcast_director.update(dt, self._broadcast_can_emit, self._present_broadcast_turn)
        director_blocks_call = (self.broadcast_director.active is not None and
                                 self.broadcast_director.active.priority >= self.radio_transcript_priority)
        if (self.radio_transcript_queue and self.radio_bubble_t <= 0.0
                and not director_blocks_call):
            speaker, line = self.radio_transcript_queue.pop(0)
            self.broadcast_visible_priority = self.radio_transcript_priority
            self.broadcast_visible_channel = "radio"
            self.broadcast_visible_source = "requested_radio_call"
            self.crew.say("Radio: [%s]: %s" % (speaker, line))
        if not self.radio_transcript_queue and not self.radio_calls and self.radio_bubble_t <= 0.0:
            if not self.broadcast_director.is_busy():
                self.radio_transcript_priority = 0

        tow_in_flight = (self.tow_arrival_t > 0
                        or any(c.get("kind") == "tow" for c in self.radio_calls)
                        or ("tow" in self.pending_radio_calls)
                        or (self.tow_escort is not None and self.tow_escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW")))
        if self.docked() and not self.tow_transit_active:
            # Reaching the harbour under own power cancels an outstanding distress loop.
            self.tow_request_active = False
            self.tow_retry_elapsed = 0.0
            self.tow_failed_call_count = 0
            self.adrift_elapsed = 0.0
        if self.tow_request_active and not tow_in_flight and not self.tow_transit_active:
            if self.tow_retry_elapsed > 0.0:
                self.tow_retry_elapsed = max(0.0, self.tow_retry_elapsed - dt)
            if self.tow_retry_elapsed <= 0.0 and not self.docked():
                accepted = self.radio_call("tow")
                still_in_flight = (self.tow_arrival_t > 0
                                   or any(c.get("kind") == "tow" for c in self.radio_calls)
                                   or ("tow" in self.pending_radio_calls)
                                   or (self.tow_escort is not None and self.tow_escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW")))
                if not accepted or not still_in_flight:
                    # A missing operator or an occupied set must not turn a request
                    # into a frame-by-frame spam loop.
                    self.tow_retry_elapsed = 8.0
        if self.tow_arrival_t > 0:
            # The timer is an ETA for the launch, not a teleport trigger. Actual
            # handover occurs only after its visible harbour-to-vessel approach.
            self.tow_arrival_t = max(0.0, self.tow_arrival_t - dt)

    def toggle_harness(self):
        self.harness = not self.harness
        self.crew.say("Captain: Harnesses on at the rail. Slower, but you stay aboard." if self.harness
                      else "Captain: Harnesses off.")

    def fuel_ok_for_trip(self):
        w = self.world
        out = w.ship_pos.distance_to(w.fishing_ground()) / w.scale
        home = w.fishing_ground().distance_to(HARBOUR) / w.scale
        return self.fuel >= (out + home) * 0.024 * 1.3 + 60

    def eff_tilt(self):
        """How far the deck is heeled, from the roll and the pitch: what the crew at the rail have to fight."""
        return math.hypot(self.roll, self.ship.slope.x * 0.6)

    # --- man-overboard rescue: stop, assess the sea, then use the safest recovery method
    ROUGH_SEA_NO_BOAT = 0.75
    DAVIT_LIFELINE_EDGE_RANGE = 190.0

    def _rescue_boat_launch_spot(self):
        """Clear water just outboard of the port-side lifeboat/davit."""
        x, y, ww, hh = self.ship.lifeboat
        # The prior point sat inside the hull. Place the launch centre outside the rail
        # so its first movement frame does not begin in an impossible collision.
        return V(x + ww * 0.5, y - hh - 42.0)

    def _rescue_boat_safe_target(self, target_world):
        """Keep the dinghy outside the hull and gunwale when approaching a swimmer."""
        local = self.world.deck_of(V(target_world))
        half_l, half_b = self.ship.length * 0.5, self.ship.beam * 0.5
        if abs(local.x) <= half_l + 55.0 and abs(local.y) <= half_b + 55.0:
            side = 1.0 if local.y >= 0.0 else -1.0
            local.y = side * (half_b + 63.0)
        return self.world.world_of(local)

    def _rescue_boat_waypoint(self, boat, target_world):
        """Plan/update a water-space route that passes around the bow or stern."""
        w = self.world
        target = self._rescue_boat_safe_target(target_world)
        old_target = boat.get("route_target")
        needs_route = (old_target is None or V(old_target).distance_to(target) > 110.0
                       or not boat.get("route"))
        if needs_route:
            start_local = w.deck_of(V(boat["pos"]))
            target_local = w.deck_of(target)
            margin_x, margin_y = 55.0, 48.0
            rect = (-self.ship.length * 0.5 - margin_x,
                    self.ship.length * 0.5 + margin_x,
                    -self.ship.beam * 0.5 - margin_y,
                    self.ship.beam * 0.5 + margin_y)
            local_route = route_around_rect(
                (start_local.x, start_local.y), (target_local.x, target_local.y), rect)
            boat["route"] = [w.world_of(V(point)) for point in local_route]
            boat["route_index"] = 0
            boat["route_target"] = V(target)
        route = boat.get("route", [])
        index = int(boat.get("route_index", 0))
        while index < len(route) and V(boat["pos"]).distance_to(route[index]) <= 45.0:
            index += 1
        boat["route_index"] = index
        return V(route[index]) if index < len(route) else V(target)

    def _move_rescue_boat(self, boat, target_world, speed, drift_speed, dt):
        """Navigate a rescue-boat step and physically resolve contacts instead of ghosting through them."""
        w = self.world
        current = V(boat["pos"])
        waypoint = self._rescue_boat_waypoint(boat, target_world)
        delta = waypoint - current
        if delta.length() <= 1e-6:
            return
        direction = delta.normalize()
        boat["heading"] = math.atan2(direction.y, direction.x)
        drift = V(1, 0).rotate_rad(w.wave_direction) * drift_speed
        proposed = current + (direction * speed + drift) * max(0.0, dt)
        corrected, contact = w.collide_rescue_boat_position(proposed)
        if contact:
            # Slide along the contact surface when there is room rather than
            # repeatedly pushing into the same obstacle on every frame.
            tangent = V(-direction.y, direction.x)
            alternatives = []
            for sign in (-1.0, 1.0):
                trial = current + (tangent * sign * speed * 0.72 + drift) * max(0.0, dt)
                trial_fixed, trial_contact = w.collide_rescue_boat_position(trial)
                if not trial_contact and trial_fixed.distance_to(current) > 0.1:
                    alternatives.append((trial_fixed.distance_to(waypoint), trial_fixed, sign))
            if alternatives:
                _, corrected, sign = min(alternatives, key=lambda item: item[0])
                boat["heading"] = math.atan2((corrected - current).y, (corrected - current).x)
            # Rebuild the route after every contact. Ship heading changes during a
            # man-overboard event, so yesterday's hull-relative route may no longer
            # pass around the now-rotated bow or stern.
            boat["route_target"] = None
        boat["pos"] = V(corrected)

    def _eligible_rescue_boat_hands(self):
        excluded_tasks = {"set", "haul", "engine", "rescue", "rush", "muster", "gaff", "dress", "bucket", "boat_launch"}
        target = self._rescue_boat_launch_spot()
        candidates = []
        for sailor in self.sailors:
            if (sailor.mode != Sailor.ABOARD or sailor.role == Sailor.CAPTAIN
                    or sailor in (self.helm_operator, self.radio_operator)
                    or sailor.ladder is not None or sailor.health < 0.35):
                continue
            # Safety-critical work is not abandoned unless no other two hands exist.
            penalty = 500.0 if sailor.task in excluded_tasks or sailor.at_engine else 0.0
            candidates.append((penalty + sailor.pos.distance_to(target)
                               + (160.0 if sailor.level == Level.BELOW else 0.0), sailor))
        candidates.sort(key=lambda pair: pair[0])
        available = [s for score, s in candidates if score < 500.0]
        if len(available) < 2:
            available = [s for _, s in candidates]
        return available[:2]

    def _return_rescue_assembly_hands(self):
        """Cancel a not-yet-launched crew order without leaving sailors stuck in a boat task."""
        for sailor in list(self.rescue_boat_hands):
            if sailor.mode == Sailor.ABOARD and sailor.task == "boat_launch":
                sailor._enter("idle")
                sailor.order_hold = 0.0
                sailor.think_t = 0.0
                sailor.alert_target = sailor.rescue_target = None
        self.rescue_boat_hands.clear()
        self.rescue_boat_assembly_elapsed = 0.0

    def _switch_rescue_to_ship_turn(self, message):
        if self.rescue_boat_state is not None and self.rescue_boat_state.get("phase") == "launching":
            # The boat has not been lowered into the water yet; leave it secured at the davit.
            self.rescue_boat_state = None
        self._return_rescue_assembly_hands()
        self.mob_rescue_mode = "ship_turn"
        self.world.rescue_to = None
        self.rescue_engineer = None
        self.crew.say(message)

    def begin_mob_rescue(self, swimmer):
        """Called only after a real visual sighting. All-stop precedes any recovery attempt."""
        if swimmer is None or swimmer.mode != Sailor.SWIMMING:
            return
        self._prepare_broadcast_priority(PRIORITY_CRITICAL)
        w = self.world
        was_docking = w.dock_state is not None
        w.brake = True
        w.throttle = 0.0
        w.destination = None
        w.route_waypoints.clear()
        w.route_origin = None
        w.route_arrival_hold = False
        w.ocean_quick_target = None
        w.rescue_to = None
        w.manual_helm = False
        w.requested_prop_direction = 1
        w.cancel_dock()
        if was_docking:
            w.dock_result = "cancelled by man overboard"
        self.rescue_engineer = None
        self.rescue_boat_state = None
        self.rescue_boat_passenger = None
        self.rescue_boat_assembly_elapsed = 0.0
        self._return_rescue_assembly_hands()

        captain_aboard = any(s.role == Sailor.CAPTAIN and s.mode == Sailor.ABOARD for s in self.sailors)
        if captain_aboard:
            self.crew.say("Captain: ALL STOP! Man overboard! Hold position and prepare to recover %s!" % swimmer.name)
        else:
            self.crew.say("Mate: ALL STOP! Captain overboard! Hold position and prepare to recover %s!" % swimmer.name)
        # If the captain was the casualty, appoint the available relief before anyone is tasked.
        self._update_station_roles(0.0)

        local = w.deck_of(swimmer.wpos)
        edge_distance = local.distance_to(self.ship.nearest_hull_point(local))
        if edge_distance <= self.DAVIT_LIFELINE_EDGE_RANGE:
            self.mob_rescue_mode = "lifeline"
            self.crew.say("The swimmer is within davit-lifeline range. Keep her stopped and throw a line.")
            return

        if w.sea_state >= self.ROUGH_SEA_NO_BOAT:
            self._switch_rescue_to_ship_turn(
                "Sea state %.2f is too rough to launch. Captain is coming about now; the ship will turn back slowly and bring the starboard rail to the swimmer." % w.sea_state)
            return

        hands = self._eligible_rescue_boat_hands()
        if len(hands) < 2:
            self._switch_rescue_to_ship_turn(
                "Not enough safe hands to crew the launch. All stop; turn back for a davit-lifeline recovery.")
            return
        self.rescue_boat_hands = set(hands)
        self.mob_rescue_mode = "boat_assembly"
        launch = self._rescue_boat_launch_spot()
        for sailor in hands:
            sailor._release()
            sailor.alert_target = sailor.rescue_target = None
            sailor.ordering = False
            sailor.order_hold = 0.0
            sailor.muster_target = None
            sailor._enter("boat_launch")
            sailor.think_t = 0.0
        self.crew.say("Sea state %.2f is manageable. Two deckhands are proceeding to the davit to lower the rescue boat." % w.sea_state)

    def finish_mob_rescue(self, swimmer, survivor=True):
        """Clear the all-stop after recovery or casualty loss without teleporting a deployed boat crew."""
        boat = self.rescue_boat_state
        if boat is not None and boat.get("phase") in ("out", "pickup", "return"):
            # If the swimmer got home or drowned before the boat arrived, the launch must still return.
            boat["target"] = None if not survivor or swimmer is not boat.get("passenger") else boat.get("target")
            if boat.get("passenger") is None:
                boat["phase"] = "return"
                boat["abort_to_ship_turn"] = False
                self.mob_rescue_mode = "boat_return"
                self.rescue_engineer = None
                self.world.rescue_to = None
                self.world.destination = None
                self.world.throttle = 0.0
                self.world.manual_helm = False
                self.crew.say("The rescue launch is returning to the davit before the ship gets under way.")
                return
        if self.rescue_boat_state is not None and self.rescue_boat_state.get("phase") == "launching":
            self.rescue_boat_state = None
        self._return_rescue_assembly_hands()
        self.rescue_boat_state = None
        self.rescue_boat_hands.clear()
        self.rescue_boat_passenger = None
        self.rescue_engineer = None
        self.rescue_boat_assembly_elapsed = 0.0
        self.mob_rescue_mode = "idle"
        self.world.rescue_to = None
        self.world.destination = None
        self.world.throttle = 0.0
        self.world.manual_helm = False
        self.world.brake = False
        if survivor:
            self.crew.say("Captain: Survivor recovered. Hold position; confirm the next course before making way.")
        else:
            self.crew.say("Captain: Casualty lost. The launch is secured and the vessel remains stopped.")

    def _recover_boat_hands(self, boat):
        launch = self._rescue_boat_launch_spot()
        for i, sailor in enumerate(list(boat.get("crew", []))):
            if sailor.mode == Sailor.RESCUE_BOAT:
                sailor.mode = Sailor.ABOARD
                sailor.level = Level.MAIN
                sailor.pos = launch + V((-1 if i == 0 else 1) * 34.0, 28.0)
                sailor.vel = V(0, 0)
                sailor.task = "idle"
                sailor.think_t = 0.0
                sailor.alert_target = sailor.rescue_target = None
                sailor.has_target = False
                sailor.path, sailor.path_goal = [], None
                sailor.at_post = sailor.at_engine = sailor.at_radio = False
                sailor.order_hold = 0.0
        self.rescue_boat_hands.clear()

    def _update_rescue_operation(self, dt):
        """Progress launch, paddle-out, pickup, and boat recovery using explicit timers and distances."""
        w = self.world
        target = self.crew.alarm_target
        mode = self.mob_rescue_mode

        if mode == "boat_assembly":
            self.rescue_boat_assembly_elapsed += max(0.0, dt)
            if target is None or target.mode != Sailor.SWIMMING:
                self._return_rescue_assembly_hands()
                self.mob_rescue_mode = "idle"
                return
            if w.sea_state >= self.ROUGH_SEA_NO_BOAT:
                self._switch_rescue_to_ship_turn(
                    "A squall has lifted the sea above %.2f. No launch is coming; the captain is turning the ship back for a lifeline recovery." % self.ROUGH_SEA_NO_BOAT)
                return
            launch = self._rescue_boat_launch_spot()
            at_station = [s for s in self.rescue_boat_hands
                          if s.mode == Sailor.ABOARD and s.task == "boat_launch"
                          and s.level == Level.MAIN and s.ladder is None
                          and s.pos.distance_to(launch + s.spot_off * 0.12) <= 42.0]
            if len(at_station) >= 2 and w.speed <= 28.0:
                self.rescue_boat_state = {
                    "phase": "launching", "pos": w.world_of(launch), "heading": w.heading,
                    "target": target, "crew": list(self.rescue_boat_hands), "passenger": None,
                    "timer": 0.0, "abort_to_ship_turn": False,
                    "route": [], "route_index": 0, "route_target": None,
                }
                self.mob_rescue_mode = "boat_launching"
                self.crew.say("The ship is stopped. The deckhands are lowering the rescue boat from the davit.")
            elif self.rescue_boat_assembly_elapsed > 18.0:
                self._switch_rescue_to_ship_turn(
                    "The launch crew cannot safely reach the davit. Turn back for a lifeline recovery instead.")
            return

        boat = self.rescue_boat_state
        if boat is None:
            return
        phase = boat.get("phase")
        boat["timer"] = float(boat.get("timer", 0.0)) + max(0.0, dt)

        if phase == "launching":
            if w.sea_state >= self.ROUGH_SEA_NO_BOAT:
                self._switch_rescue_to_ship_turn(
                    "A squall has made the sea too rough to launch. Secure the boat and turn back for the davit lifeline.")
                return
            if boat["timer"] >= 1.45:
                boat["phase"] = "out"
                boat["timer"] = 0.0
                boat["route_target"] = None
                self.mob_rescue_mode = "boat_out"
                for sailor in boat["crew"]:
                    if sailor.mode == Sailor.ABOARD:
                        sailor.mode = Sailor.RESCUE_BOAT
                        sailor.task = "boat_crew"
                        sailor.vel = V(0, 0)
                        sailor.has_target = False
                        sailor.path, sailor.path_goal = [], None
                self.crew.say("The rescue boat is away from the davit. The crew are paddling toward %s." % target.name)
            return

        if phase in ("out", "pickup"):
            if target is None or target.mode != Sailor.SWIMMING:
                boat["target"] = None
                boat["phase"] = "return"
                boat["timer"] = 0.0
                self.mob_rescue_mode = "boat_return"
                return
            if w.sea_state >= self.ROUGH_SEA_NO_BOAT and boat.get("passenger") is None:
                boat["phase"] = "return"
                boat["timer"] = 0.0
                boat["abort_to_ship_turn"] = True
                self.mob_rescue_mode = "boat_return"
                self.crew.say("A squall is building. The launch is returning; the ship will turn for a lifeline recovery.")
                return
            if phase == "out":
                distance = V(target.wpos).distance_to(V(boat["pos"]))
                if distance <= 82.0:
                    boat["phase"] = "pickup"
                    boat["timer"] = 0.0
                    self.mob_rescue_mode = "boat_pickup"
                    self.crew.say("The launch is alongside %s. The crew are pulling him over the gunwale." % target.name)
                else:
                    paddle_speed = 142.0 * (1.0 - 0.30 * clamp(w.sea_state, 0.0, 1.0))
                    self._move_rescue_boat(boat, V(target.wpos), paddle_speed,
                                            3.0 + 16.0 * w.sea_state, dt)
                return
            if boat["timer"] >= 1.65:
                if target.mode == Sailor.SWIMMING:
                    target.mode = Sailor.RESCUE_BOAT
                    target.task = "boat_passenger"
                    target.selected = False
                    target.lifeline = None
                    target.swim_goal = None
                    target.vel = V(0, 0)
                    self.rescue_boat_passenger = target
                    boat["passenger"] = target
                    boat["phase"] = "return"
                    boat["timer"] = 0.0
                    self.mob_rescue_mode = "boat_return"
                    self.crew.say("%s is aboard the rescue boat. The launch is turning back to the ship." % target.name)
                else:
                    boat["target"] = None
                    boat["phase"] = "return"
                    boat["timer"] = 0.0
                    self.mob_rescue_mode = "boat_return"
            return

        if phase == "return":
            launch_world = w.world_of(self._rescue_boat_launch_spot())
            delta = launch_world - V(boat["pos"])
            distance = delta.length()
            if distance > 115.0:
                paddle_speed = 128.0 * (1.0 - 0.27 * clamp(w.sea_state, 0.0, 1.0))
                self._move_rescue_boat(boat, launch_world, paddle_speed,
                                        3.0 + 12.0 * w.sea_state, dt)
                return

            passenger = boat.get("passenger")
            if passenger is not None and passenger.mode == Sailor.RESCUE_BOAT:
                local = w.deck_of(boat["pos"])
                hull_pt, tangent, inward = self.ship.hull_frame(local)
                passenger.pos = V(local)
                passenger.climb_to = V(hull_pt + inward * 42.0)
                passenger.mode = Sailor.CLIMBING
                passenger.lifeline = None
                passenger.vel = V(0, 0)
            self._recover_boat_hands(boat)
            abort_to_turn = bool(boat.get("abort_to_ship_turn"))
            self.rescue_boat_state = None
            self.rescue_boat_passenger = passenger if passenger is not None and passenger.mode == Sailor.CLIMBING else None
            self.rescue_boat_assembly_elapsed = 0.0
            self.rescue_engineer = None
            if abort_to_turn and target is not None and target.mode == Sailor.SWIMMING:
                self.mob_rescue_mode = "ship_turn"
                self.crew.say("The launch is secured. The ship is turning back for the swimmer with a davit lifeline.")
            elif passenger is not None and passenger.mode == Sailor.CLIMBING:
                self.mob_rescue_mode = "recovering"
                self.crew.say("The rescue boat is alongside; the survivor is climbing aboard.")
            else:
                self.mob_rescue_mode = "idle"
                if target is not None and target.mode == Sailor.SWIMMING:
                    self.mob_rescue_mode = "ship_turn"
                    self.crew.say("The launch returned without the swimmer. Turn back for a davit-lifeline recovery.")
                else:
                    self.world.brake = False
                    self.world.throttle = 0.0

    def _player_position_nm_for_phase(self, phase="A", *, believed=False):
        """Project the legacy hull position into the selected traffic-world plane."""
        w = self.world
        pos = w.believed_pos if believed else w.ship_pos
        scale = max(0.001, float(w.scale) * 185.2)
        local_nm = (float(pos.x) / scale, -float(pos.y) / scale)
        return legacy_nm_to_phase_b_nm(local_nm) if str(phase).upper() == "B" else local_nm

    def _traffic_player_position_nm(self):
        """Return physical player position in the active campaign's coordinate plane."""
        return self._player_position_nm_for_phase(getattr(self, "campaign_phase", "A"))

    def _traffic_player_believed_position_nm(self):
        """Return the crew-estimated position in the active campaign's coordinate plane."""
        return self._player_position_nm_for_phase(getattr(self, "campaign_phase", "A"), believed=True)

    def _active_nm_to_legacy_nm(self, position_nm):
        """Convert a traffic-world coordinate into the legacy hull/world local plane."""
        if getattr(self, "campaign_phase", "A") == "B":
            return phase_b_nm_to_legacy_nm((float(position_nm[0]), float(position_nm[1])))
        return (float(position_nm[0]), float(position_nm[1]))

    def _legacy_nm_to_active_nm(self, position_nm):
        """Convert a legacy local coordinate into the active traffic-world plane."""
        if getattr(self, "campaign_phase", "A") == "B":
            return legacy_nm_to_phase_b_nm((float(position_nm[0]), float(position_nm[1])))
        return (float(position_nm[0]), float(position_nm[1]))

    def _set_campaign_phase(self, phase):
        """Switch the playable traffic/radio/weather context without moving the hull.

        Hull physics stays local to Hakodate for backwards compatibility. Coordinate
        adapters map that position to Phase B for traffic, radio, weather, and chart
        routing, making the high-seas map navigable rather than a separate preview.
        """
        phase = str(phase).upper()
        if phase not in ("A", "B"):
            return False
        current = getattr(self, "campaign_phase", "A")
        if phase == current:
            return True
        if getattr(self, "player_rescue_manager", None) is not None and self.player_rescue_manager.has_active_mission:
            self.chart_status = "RESCUE ACTIVE — finish or break off the assistance before changing campaign phase."
            return False
        if getattr(self, "ai_rescue_manager", None) is not None and self.ai_rescue_manager.has_active_mission:
            self.chart_status = "FLEET RESCUE ACTIVE — wait for the responding vessel to clear the incident before changing campaign phase."
            return False
        self._phase_traffic_worlds[current] = self.traffic_world
        self._phase_weather_grids[current] = self.world_weather_grid
        self._phase_relationship_dynamics[current] = self.relationship_dynamics
        if phase not in self._phase_traffic_worlds:
            tw = TrafficWorld(world_seed=1962, active_cap=30, phase=phase)
            self._phase_traffic_worlds[phase] = tw
            dynamics = RelationshipDynamics(world_seed=1962)
            dynamics.seed_baseline(tw, self.world.time)
            self._phase_relationship_dynamics[phase] = dynamics
        if phase not in self._phase_weather_grids:
            new_grid = WeatherGrid(world_seed=1962, phase=phase)
            # This phase has never been visited in this career. Start its live
            # weather epoch now rather than replaying thousands of unseen ticks.
            new_grid.rebase_time(self.world.time)
            self._phase_weather_grids[phase] = new_grid
        self.campaign_phase = phase
        self.traffic_world = self._phase_traffic_worlds[phase]
        self.world_weather_grid = self._phase_weather_grids[phase]
        date = self.world.calendar_date()
        player_nm = self._traffic_player_position_nm()
        self.traffic_world.advance(self.world.time, focus_nm=player_nm, month=date.month,
                                   day=date.day, hour=self.world.hour(), force=True)
        self.world_weather_grid.advance(self.world.time)
        self.world_weather_grid.observe_local(
            player_nm, cloud=self.weather.cloud, precipitation=self.weather.rain,
            fog=self.weather.fog, wind_speed_kt=self.weather.wind_kt(),
            wind_direction_rad=self.weather.wind_dir, sea_state=float(self.world.sea_state))
        self.relationship_dynamics = self._phase_relationship_dynamics[phase]
        if getattr(self, "tow_escort", None) is not None:
            self._tow_escort_synced_id = None
            self._sync_tow_escort_world_entity()
        self._chart_base_surface = None
        self._chart_cache_size = None
        self._chart_transform = None
        self._phase_b_contact_hitboxes = []
        self.chart_status = ("REGIONAL WATERS / PHASE A ACTIVE" if phase == "A"
                             else "HIGH SEAS / PHASE B ACTIVE — ROUTES NOW USE THE WIDE MAP")
        self.record_log_entry("Navigation: campaign chart switched to Phase %s (%s)." % (
            phase, "Hakodate regional waters" if phase == "A" else "North Pacific high seas"))
        return True

    def _rescue_navigation_backup(self):
        """Capture the player's current plotted navigation intent before a rescue diversion."""
        world = self.world
        def pair(value):
            if value is None:
                return None
            return [float(value.x), float(value.y)]
        return {
            "destination": pair(world.destination),
            "route_waypoints": [pair(point) for point in world.route_waypoints],
            "route_origin": pair(world.route_origin),
            "ocean_quick_target": pair(world.ocean_quick_target),
            "route_arrival_hold": bool(world.route_arrival_hold),
            "manual_helm": bool(world.manual_helm),
            "throttle": float(world.throttle),
            "cruise": float(world.cruise),
        }

    def _rescue_world_target(self, reported_position_nm):
        """Convert an active-phase radio plot to the legacy hull simulation plane."""
        legacy_x, legacy_y = self._active_nm_to_legacy_nm(reported_position_nm)
        scale = max(0.001, float(self.world.scale) * 185.2)
        return (float(legacy_x) * scale, -float(legacy_y) * scale)

    def _start_player_rescue_mission(self, ship):
        """Commit the single rescue mission and make the player actually sail to its plot."""
        if ship is None or self.player_rescue_manager.has_active_mission:
            return False
        report = getattr(ship, "last_reported_position_nm", None)
        if not isinstance(report, (tuple, list)) or len(report) != 2:
            return False
        if not all(math.isfinite(float(value)) for value in report):
            return False
        target_world = self._rescue_world_target(report)
        backup = self._rescue_navigation_backup()
        mission = self.player_rescue_manager.dispatch(
            ship, self.world.time, reported_position_nm=report,
            navigation_backup=backup, route_target_world=target_world)
        world = self.world
        self.anchor_deployed = False
        world.hold = False
        world.brake = False
        world.set_destination(V(target_world[0], target_world[1]), keep_dock=False)
        world.cruise = max(float(world.cruise), 0.82)
        # Let the navigation/autothrottle model build way gradually. No instant player
        # position change is allowed here: the helm must actually sail to the plot.
        world.ap_t = 0.0
        self.radio_ui_open = False
        self.radio_ui_status = "RESCUE DISPATCHED — sailing for %s's reported position." % ship.callsign
        self.traffic_hail_status = "MAYDAY ASSIST — EN ROUTE TO %s" % ship.callsign
        self.traffic_hail_status_t = 12.0
        self.record_log_entry(
            "Rescue mission %s dispatched to %s's reported plot (%.2f, %.2f) NM. Course diverted; no teleport." %
            (mission["mission_id"], ship.callsign, float(report[0]), float(report[1])))
        self.crew.say("Helm: Diverting to the reported MAYDAY position of %s." % ship.callsign)
        if self.radio_station_ok():
            self.queue_broadcast_conversation((
                (0.0, "KŌEI MARU", "%s, this is Kōei Maru. We are proceeding to your reported position. Keep this frequency clear. Over." % ship.callsign, "radio"),
                (2.0, ship.callsign, "Kōei Maru, roger. We are holding at our reported plot. Advise when on scene. Over.", "radio"),
            ), priority=PRIORITY_HIGH, channel="radio", source="rescue:%s:dispatch" % mission["mission_id"])
        return True

    def _restore_rescue_navigation(self, mission):
        """Restore the pre-rescue plot only when the player has not chosen another course."""
        if not isinstance(mission, dict) or bool(mission.get("course_overridden", False)):
            return False
        backup = mission.get("navigation_backup", {})
        if not isinstance(backup, dict):
            return False
        world = self.world
        def vector(name):
            value = backup.get(name)
            if value is None:
                return None
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                return None
            return V(float(value[0]), float(value[1]))
        world.destination = vector("destination")
        world.route_waypoints = [V(float(p[0]), float(p[1])) for p in backup.get("route_waypoints", [])
                                 if isinstance(p, (tuple, list)) and len(p) == 2]
        world.route_origin = vector("route_origin")
        world.ocean_quick_target = vector("ocean_quick_target")
        world.route_arrival_hold = bool(backup.get("route_arrival_hold", False))
        world.manual_helm = bool(backup.get("manual_helm", False))
        world.throttle = clamp(float(backup.get("throttle", world.throttle)), 0.0, 1.0)
        world.cruise = clamp(float(backup.get("cruise", world.cruise)), 0.0, 1.0)
        world.ap_t = 0.0
        return True

    def _handle_ai_rescue_transition(self, event):
        """Record autonomous fleet rescue transitions without inventing radio range."""
        if not event:
            return
        event_type = str(event.get("type", ""))
        target = str(event.get("target_callsign", "distressed vessel"))
        responder = str(event.get("responder_callsign", "responder"))
        distance = max(0.0, float(event.get("distance_nm", 0.0) or 0.0))
        if event_type == "dispatched":
            storm_note = " Heavy weather shortened the unanswered distress window." if float(self.world.sea_state) >= 0.75 else ""
            self.record_log_entry(
                "Fleet rescue: %s is turning to assist %s (%.1f NM away); Kōei Maru has not been diverted.%s" %
                (responder, target, distance, storm_note))
            self.traffic_hail_status = "FLEET RESCUE — %s RESPONDING" % target.upper()
            self.traffic_hail_status_t = 12.0
        elif event_type == "on_scene":
            self.record_log_entry("Fleet rescue: %s reached %s and began assistance (working range %.1f NM)." %
                                  (responder, target, distance))
            self.traffic_hail_status = "FLEET RESCUE — %s ON SCENE" % responder.upper()
            self.traffic_hail_status_t = 10.0
        elif event_type == "rendezvous_lost":
            self.record_log_entry("Fleet rescue: %s lost working range to %s at %.1f NM and is re-approaching." %
                                  (responder, target, distance))
        elif event_type == "completed":
            outcome = str(event.get("outcome", "assistance completed"))
            self.record_log_entry("Fleet rescue: %s assisted %s — %s." % (responder, target, outcome))
            self.traffic_hail_status = "FLEET RESCUE COMPLETE — %s" % target.upper()
            self.traffic_hail_status_t = 12.0
        elif event_type == "returned":
            self.record_log_entry("Fleet rescue: %s has cleared the incident with %s and is returning to patrol." %
                                  (responder, target))
        elif event_type == "failed":
            reason = str(event.get("reason", "response failed"))
            self.record_log_entry("Fleet rescue failed: %s could not complete the response to %s (%s)." %
                                  (responder, target, reason))
            self.traffic_hail_status = "FLEET RESCUE FAILED — %s" % target.upper()
            self.traffic_hail_status_t = 12.0

    def _handle_player_rescue_transition(self, event):
        """Record and speak each physical assistance transition exactly once."""
        if not event:
            return
        event_type = str(event.get("type", ""))
        callsign = str(event.get("callsign", "distressed vessel"))
        target_id = str(event.get("target_vessel_id", ""))
        if event_type == "on_scene":
            # Arrival is a real navigation state transition, not an immediate rescue.
            # Never override a course the player deliberately took over from us.
            mission = self.player_rescue_manager.mission or {}
            if not mission.get("course_overridden", False):
                self.world.destination = None
                self.world.route_waypoints.clear()
                self.world.route_origin = None
                self.world.ocean_quick_target = None
                self.world.route_arrival_hold = False
                self.world.throttle = 0.0
                self.world.brake = False
            self.record_log_entry("Rescue: Kōei Maru is on scene with %s (about %.1f NM by physical range); assistance work begins." %
                                  (callsign, float(event.get("distance_nm", 0.0))))
            self.crew.say("On scene with %s. Stand by while we render assistance." % callsign)
            self.traffic_hail_status = "ON SCENE — ASSISTING %s" % callsign.upper()
            self.traffic_hail_status_t = 12.0
            self._append_rescue_radio_history(target_id, callsign,
                "Kōei Maru is on scene. We are standing by to assist. Over.", "TX")
            if self.radio_station_ok():
                self.queue_broadcast_conversation((
                    (0.0, "KŌEI MARU", "%s, Kōei Maru. We are on scene and commencing assistance. Stand by. Over." % callsign, "radio"),
                    (1.8, callsign, "Kōei Maru, roger. We have you in sight. Thank you. Over.", "radio"),
                ), priority=PRIORITY_HIGH, channel="radio", source="rescue:%s:on-scene" % event.get("mission_id", target_id))
        elif event_type == "rendezvous_lost":
            self.record_log_entry("Rescue: %s moved out of working range; rendezvous lost at %.1f NM." %
                                  (callsign, float(event.get("distance_nm", 0.0))))
            self.traffic_hail_status = "RENDEZVOUS LOST — REAPPROACH %s" % callsign.upper()
            self.traffic_hail_status_t = 10.0
            mission = self.player_rescue_manager.mission or {}
            if not mission.get("course_overridden"):
                route = mission.get("route_target_world")
                if isinstance(route, (list, tuple)) and len(route) == 2:
                    self.world.set_destination(V(float(route[0]), float(route[1])))
                    self.world.cruise = max(float(self.world.cruise), 0.82)
        elif event_type in ("completed", "failed", "cancelled"):
            mission = self.player_rescue_manager.mission or {}
            restored = self._restore_rescue_navigation(mission) if event_type == "completed" else False
            if event_type == "completed":
                outcome = str(event.get("outcome", "assistance completed"))
                self.record_log_entry("Rescue complete: %s — %s." % (callsign, outcome))
                self.crew.say("%s: Assistance completed. %s." % (callsign, outcome))
                self.traffic_hail_status = "RESCUE COMPLETE — %s" % callsign.upper()
                self.traffic_hail_status_t = 12.0
                self._append_rescue_radio_history(target_id, callsign, outcome + ". Assistance complete. Over.", "RX")
                if restored:
                    self.crew.say("Helm: Returning to the course plotted before the rescue.")
            else:
                reason = str(event.get("reason", event_type))
                self.record_log_entry("Rescue %s: %s (%s)." % (event_type, callsign, reason))
                self.crew.say("Rescue: The assistance mission for %s has ended (%s)." % (callsign, reason))
                self.traffic_hail_status = "RESCUE %s — %s" % (event_type.upper(), callsign.upper())
                self.traffic_hail_status_t = 12.0
                if not mission.get("course_overridden"):
                    self._restore_rescue_navigation(mission)
            if self.radio_station_ok():
                self.queue_broadcast_conversation((
                    (0.0, "KŌEI MARU", "%s, Kōei Maru. Assistance update: %s. Over." %
                     (callsign, str(event.get("outcome", event_type.replace("_", " ")))), "radio"),
                ), priority=PRIORITY_HIGH, channel="radio", source="rescue:%s:%s" % (event.get("mission_id", target_id), event_type))

    def _append_rescue_radio_history(self, vessel_id, callsign, text, kind):
        if not vessel_id:
            return
        history = self.radio_ui_histories.setdefault(str(vessel_id), {"lines": [], "visible_count": 0})
        lines = history.setdefault("lines", [])
        # Radio updates occur while the UI may be closed. Preserve the user's read
        # cursor so a later visit to this contact can advance the new transcript lines.
        visible_before = max(0, min(len(lines), int(history.get("visible_count", 0))))
        lines.append({"speaker": str(callsign if kind == "RX" else "KŌEI MARU · TX"), "text": str(text), "kind": str(kind)})
        trim = max(0, len(lines) - 100)
        if trim:
            del lines[:trim]
            visible_before = max(0, visible_before - trim)
        history["visible_count"] = visible_before
        self.radio_ui_active_end[str(vessel_id)] = len(lines)

    def _update_player_rescue_mission(self):
        """Monitor whether navigation is still following the rescue course and advance assistance."""
        manager = getattr(self, "player_rescue_manager", None)
        if manager is None or not manager.has_active_mission:
            return
        mission = manager.mission
        target = self.traffic_world.by_id(mission["target_vessel_id"])
        if target is None:
            event = manager.update(self.world.time, self._traffic_player_position_nm(), self.traffic_world)
            self._handle_player_rescue_transition(event)
            return
        player_nm = self._traffic_player_position_nm()
        true_distance = math.hypot(float(player_nm[0]) - float(target.position_nm[0]),
                                   float(player_nm[1]) - float(target.position_nm[1]))
        state = mission.get("state")
        if state == "en_route" and not mission.get("course_overridden"):
            expected = mission.get("route_target_world")
            destination = self.world.destination
            if self.world.manual_helm or self.world.dock_state is not None:
                manager.mark_course_overridden()
            elif destination is not None and isinstance(expected, (tuple, list)) and len(expected) == 2:
                if math.hypot(float(destination.x) - float(expected[0]),
                              float(destination.y) - float(expected[1])) > 90.0:
                    manager.mark_course_overridden()
            elif destination is None and true_distance > RESCUE_ON_SCENE_RADIUS_NM:
                # An auto-arrival can clear destination only at the end of the rescue
                # approach; a distant empty destination means the player changed course.
                manager.mark_course_overridden()
        elif state == "on_scene":
            if self.world.manual_helm or self.world.destination is not None or self.world.dock_state is not None:
                manager.mark_course_overridden()
        event = manager.update(self.world.time, player_nm, self.traffic_world)
        self._handle_player_rescue_transition(event)

    def _traffic_visual_range_nm(self):
        """Approximate a weather-limited visual sighting radius from reported visibility."""
        try:
            visibility_km = float(self.weather.visibility_km())
        except (AttributeError, TypeError, ValueError):
            visibility_km = 4.0
        return clamp(visibility_km / 1.852, 0.25, 5.5)

    def _update_v13_2_traffic(self, dt):
        """Advance coarse traffic on scheduled ticks, never as per-frame AI."""
        if not hasattr(self, "traffic_world"):
            return
        w = self.world
        player_nm = self._traffic_player_position_nm()
        # Weather evolves on its own fixed cadence, not per rendered frame. At every
        # completed grid tick, assimilate the shipboard weather into the local cell.
        weather_tick_before = self.world_weather_grid.tick_index
        self.world_weather_grid.advance(w.time)
        if self.world_weather_grid.tick_index != weather_tick_before:
            self.world_weather_grid.observe_local(
                player_nm, cloud=self.weather.cloud, precipitation=self.weather.rain,
                fog=self.weather.fog, wind_speed_kt=self.weather.wind_kt(),
                wind_direction_rad=self.weather.wind_dir, sea_state=float(w.sea_state))
        date = w.calendar_date()
        changed = self.traffic_world.advance(w.time, focus_nm=player_nm,
                                             month=date.month, day=date.day, hour=w.hour())
        # A vessel gets a chart plot when it is close enough to be seen from the deck.
        if changed:
            self.traffic_world.observe_nearby(
                player_nm, w.time, radius_nm=self._traffic_visual_range_nm())
            for social_event in self.relationship_dynamics.advance(self.traffic_world, w.time):
                self.record_log_entry("Fleet gossip: dealings with %s reached %s (%s report)." % (
                    social_event["source_callsign"], social_event["target_callsign"],
                    social_event["direction"]))
        # M9: coarse distress dispatcher uses spatial/radio contacts, not the active
        # render list. A MAYDAY can therefore arrive from a vessel that was never drawn.
        events = self.distress_dispatcher.update(
            self.traffic_world, w.time, player_nm, sea_state=float(w.sea_state),
            radio_staffed=self.radio_station_ok(), sea_state_at=self._traffic_remote_sea_state)
        for event in events:
            if not event.heard_by_player:
                continue
            self.last_mayday_source_id = event.vessel_id
            self.traffic_world.mark_known(event.vessel_id)
            self.traffic_world.promote_rescue_contact(event.vessel_id)
            self.record_log_entry("MAYDAY received from %s: %s. Reported position kept separate from true position." %
                                   (event.callsign, event.issue_text))
            self.queue_broadcast_conversation(
                event.radio_turns(), priority=PRIORITY_CRITICAL, channel="radio", source=event.source)
        # M9: an accepted MAYDAY commits real navigation to the reported plot. The
        # controller runs per simulation update while the world/traffic itself remains throttled.
        self._update_player_rescue_mission()
        # M9 extension: the AI fleet takes over overdue unattended distress calls
        # and moves an existing scheduled vessel along a physically steered response.
        ai_events = self.ai_rescue_manager.update(
            w.time, self.traffic_world, sea_state=float(w.sea_state),
            player_rescue_target_id=(self.player_rescue_manager.mission.get("target_vessel_id")
                                     if self.player_rescue_manager.has_active_mission
                                     and self.player_rescue_manager.mission else None),
            sea_state_at=self._traffic_remote_sea_state)
        for ai_event in ai_events:
            self._handle_ai_rescue_transition(ai_event)
        # M11: overheard band traffic runs only on its own coarse cadence. It is
        # discarded for this slot if the channel is busy; it never builds a backlog.
        radio_busy = bool(self.radio_calls or self.pending_radio_calls or self.radio_transcript_queue
                          or self.radio_bubble_t > 0.25 or self.broadcast_director.is_busy())
        ambient = self.ambient_ship_radio.update(
            self.traffic_world, w.time, player_nm,
            radio_staffed=self.radio_station_ok(), channel_busy=radio_busy,
            radio_clarity=float(getattr(self.radio, "signal_quality", 0.75)),
            sea_state=float(w.sea_state), hour=w.hour(), month=date.month, day=date.day,
            docked=self.docked())
        if ambient is not None:
            self.queue_broadcast_conversation(
                ambient.turns, priority=PRIORITY_LOW, channel="radio", source=ambient.source)
        self.traffic_hail_status_t = max(0.0, self.traffic_hail_status_t - max(0.0, float(dt)))

    def _weather_sample_for_traffic(self, ship):
        """Sample weather at a remote ship; local player's current weather remains authoritative."""
        if not hasattr(self, "world_weather_grid") or ship is None:
            return None
        self.world_weather_grid.advance(self.world.time)
        return self.world_weather_grid.sample(ship.position_nm, sim_time_s=self.world.time)

    def _traffic_remote_sea_state(self, ship):
        """Return one spatial sea-state sample for an occasional coarse distress check."""
        sample = self._weather_sample_for_traffic(ship)
        return float(sample.sea_state) if sample is not None else float(self.world.sea_state)

    def _hail_fleet_traffic(self):
        """Transmit one routine hail; responder selection is local and range-gated."""
        if not hasattr(self, "traffic_world"):
            return False
        if not self.radio_station_ok():
            operator = self._ensure_radio_operator()
            if operator is None:
                self.crew.say("Radio: No available hand can take the wireless watch.")
            else:
                self.crew.say("Radio: %s must reach the wireless before we can call the fleet. Acknowledge from the set, then try Ctrl+F11 again." % operator.name)
            return False
        if (self.radio_calls or self.pending_radio_calls or self.radio_transcript_queue
                or self.radio_bubble_t > 0.25 or self.broadcast_director.is_busy()):
            self.crew.say("Radio: Frequency occupied. Wait for the current exchange to clear before hailing fleet traffic.")
            return False
        player_nm = self._traffic_player_position_nm()
        date = self.world.calendar_date()
        self.traffic_world.advance(self.world.time, focus_nm=player_nm,
                                   month=date.month, day=date.day, hour=self.world.hour(), force=True)
        candidates = self.traffic_world.radio_candidates(player_nm)
        if not candidates:
            tx = ("All stations, all stations. This is Kōei Maru, independent longline out of Hakodate. "
                  "Any traffic in the vicinity, report general conditions and fishing activity. Over.")
            self._prepare_broadcast_priority(PRIORITY_MEDIUM)
            self.crew.say("Radio: [VESSEL]: %s" % tx)
            self.crew.say("Radio: [RADIO TRAFFIC]: Only static and carrier noise. No vessel answers within our set's range.")
            self.traffic_hail_status = "NO FLEET REPLY"
            self.traffic_hail_status_t = 6.0
            return True
        # The call goes to every listener in range. A silent nearer vessel must not
        # block a farther one from answering; the first successful reply wins the channel.
        responder, exchange = self.ship_radio_service.hail_any(
            candidates, player_name="Kōei Maru", player_port="Hakodate",
            player_position_nm=player_nm, sim_time_s=self.world.time,
            sea_state=float(self.world.sea_state),
            weather_phrase=self.weather.label(),
            radio_clarity=float(getattr(self.radio, "signal_quality", 0.75)),
            month=date.month, day=date.day,
        )
        self._prepare_broadcast_priority(PRIORITY_MEDIUM)
        self.crew.say("Radio: [VESSEL]: %s" % exchange.transmit_text)
        if not exchange.delivered or responder is None:
            self.crew.say("Radio: [RADIO TRAFFIC]: %s" % exchange.reason)
            self.traffic_hail_status = "NO REPLY — %s" % exchange.intent.replace("_", " ").upper()
            self.traffic_hail_status_t = 6.0
            return True
        self.traffic_world.mark_known(responder.id)
        self.traffic_hail_status = "FLEET CONTACT — %s" % responder.callsign
        self.traffic_hail_status_t = 8.0
        self.crew.say("Radio: [VESSEL]: Contact made with %s. Plot reported; range remains approximate." % responder.callsign)
        self.queue_broadcast_conversation(
            exchange.turns, priority=PRIORITY_MEDIUM, channel="radio",
            source="ship_radio:%s:%s" % (responder.id, exchange.intent),
        )
        self.record_log_entry("Ship-radio contact: %s (%s), intent %s, range %.1f nm; reported position stored separately from live position." % (
            responder.callsign, responder.archetype.value, exchange.intent,
            math.hypot(responder.position_nm[0] - player_nm[0], responder.position_nm[1] - player_nm[1])))
        return True

    def open_radio_ui(self):
        """Open the selectable fleet radio panel from HUD or Ctrl+F11."""
        if self.auction_active:
            return False
        self.radio_ui_open = True
        self.notebook_open = False
        self.chart_open = False
        self.crew_sheet_open = False
        self.context_menu = None
        self._refresh_radio_ui_contacts()
        self.radio_ui_status = ("WIRELESS READY — select a vessel and choose a topic."
                                if self.radio_station_ok() else
                                "WIRELESS UNMANNED — assign a radio operator at the set before transmitting.")
        return True

    def _refresh_radio_ui_contacts(self):
        """Refresh the list from spatially nearby vessels, not the full fleet each frame."""
        if not hasattr(self, "traffic_world"):
            self.radio_ui_contacts = []
            return []
        player_nm = self._traffic_player_position_nm()
        date = self.world.calendar_date()
        self.traffic_world.advance(self.world.time, focus_nm=player_nm,
                                   month=date.month, day=date.day, hour=self.world.hour(), force=True)
        contacts = self.traffic_world.nearby(player_nm, 55.0)
        contacts.sort(key=lambda ship: math.hypot(ship.position_nm[0] - player_nm[0],
                                                 ship.position_nm[1] - player_nm[1]))
        self.radio_ui_contacts = contacts
        if self.radio_ui_selected_ship_id not in {ship.id for ship in contacts}:
            self.radio_ui_selected_ship_id = contacts[0].id if contacts else None
        return contacts

    def _radio_ui_selected_ship(self):
        if not self.radio_ui_selected_ship_id:
            return None
        return self.traffic_world.by_id(self.radio_ui_selected_ship_id)

    def _radio_ui_distance(self, ship):
        if ship is None:
            return math.inf
        px, py = self._traffic_player_position_nm()
        return math.hypot(ship.position_nm[0] - px, ship.position_nm[1] - py)

    def _radio_ui_select_next_ship(self, step=1):
        contacts = self.radio_ui_contacts
        if not contacts:
            self.radio_ui_selected_ship_id = None
            return
        ids = [ship.id for ship in contacts]
        try:
            index = ids.index(self.radio_ui_selected_ship_id)
        except ValueError:
            index = -1 if step > 0 else 0
        self.radio_ui_selected_ship_id = ids[(index + int(step)) % len(ids)]
        self.radio_ui_scroll = max(0, min(self.radio_ui_scroll, max(0, len(ids) - 1)))
        ship = self._radio_ui_selected_ship()
        self.radio_ui_status = "Selected %s — choose a radio topic." % ship.callsign if ship else "No vessels in the contact list."

    def _radio_ui_start_topic(self, topic):
        """Transmit one question to the selected vessel and stage the reply line-by-line."""
        ship = self._radio_ui_selected_ship()
        if ship is None:
            self.radio_ui_status = "No vessel selected."
            return False
        if ship.mayday_player_heard and not ship.mayday_resolved and topic not in ("assist", "ignore"):
            self.radio_ui_status = "MAYDAY ACTIVE — choose ASSIST or IGNORE before routine conversation."
            return False
        if not self.radio_station_ok():
            op = self._ensure_radio_operator()
            self.radio_ui_status = ("%s is not at the wireless set yet. Wait for the operator to reach the wheelhouse station." % op.name
                                    if op is not None else
                                    "NO RADIO OPERATOR — no one aboard can take the wireless watch.")
            return False
        if (self.radio_calls or self.pending_radio_calls or self.radio_transcript_queue
                or self.radio_bubble_t > 0.25 or self.broadcast_director.is_busy()):
            self.radio_ui_status = "CHANNEL BUSY — finish the current broadcast before transmitting."
            return False
        history = self.radio_ui_histories.setdefault(ship.id, {"lines": [], "visible_count": 0})
        if history["visible_count"] < len(history["lines"]):
            self.radio_ui_status = "ADVANCE THE CURRENT EXCHANGE BEFORE STARTING ANOTHER."
            return False
        # M8: the Coast Guard launch is the same stable contact in the chart,
        # traffic index, radio list and captain/crew controller. Route its topics
        # through TowEscort while keeping the radio UI's staged NEXT LINE flow.
        prior_contact_count = int(ship.contact_count)
        distance = self._radio_ui_distance(ship)
        escort = getattr(self, "tow_escort", None)
        if (escort is not None and distance <= ship.radio_range_nm
                and getattr(ship, "runtime_kind", "scheduled") == "tow_escort"
                and ship.id == getattr(escort, "vessel_id", None)):
            topic_map = {"hail": "position", "position": "position", "weather": "weather",
                         "activity": "traffic", "grounds": "fishing", "crew": "crew", "name": "name"}
            return self.tow_escort_talk(topic_map.get(topic, "position"), via_radio_ui=True)
        if distance > ship.radio_range_nm:
            tx = "%s, %s. This is Kōei Maru. Request %s. Over." % (
                ship.callsign, ship.callsign,
                {"hail": "radio check", "position": "your position", "weather": "weather report",
                 "activity": "activity report", "grounds": "fishing information", "crew": "crew report",
                 "name": "vessel identification"}.get(topic, str(topic)))
            exchange = RadioExchange(False, "out_of_range", tx,
                                     reason="No reply; vessel is beyond its set's stated range.")
        else:
            remote_weather = self._weather_sample_for_traffic(ship)
            exchange = self.ship_radio_service.interact(
                ship, topic, player_name="Kōei Maru", player_port="Hakodate",
                player_position_nm=self._traffic_player_position_nm(), sim_time_s=self.world.time,
                sea_state=float(self.world.sea_state), weather_phrase=self.weather.label(),
                responder_sea_state=(remote_weather.sea_state if remote_weather is not None else None),
                responder_weather_phrase=(remote_weather.phrase if remote_weather is not None else None),
                radio_clarity=float(getattr(self.radio, "signal_quality", 0.75)),
                month=self.world.calendar_date().month, day=self.world.calendar_date().day)
        # The selected-contact UI addresses a vessel directly, unlike the legacy
        # one-key all-stations broadcast. Preserve the service's response simulation.
        if topic == "hail":
            exchange = exchange.__class__(exchange.delivered, exchange.intent,
                "%s, %s. This is Kōei Maru, independent longline out of Hakodate. Do you copy? Over." %
                (ship.callsign, ship.callsign), exchange.turns, exchange.reason, exchange.reported_position_nm)
        if exchange.delivered:
            self.traffic_world.mark_known(ship.id)
            self.radio_ui_status = "%s answered — advance the transcript line by line." % ship.callsign
            if prior_contact_count == 0:
                # These hints describe observable conventions only; they do not reveal
                # hidden trust, honesty rolls, or the truth of any fishing-ground claim.
                if ship.archetype in (TrafficArchetype.CORPORATE_CATCHER, TrafficArchetype.CORPORATE_LONGLINER):
                    hint = "Notebook hint: numbered company callsigns often indicate contracted fleet traffic. Weather reports may be useful even when grounds information is withheld."
                elif ship.archetype == TrafficArchetype.COAST_GUARD:
                    hint = "Notebook hint: official traffic is usually strongest on safety and weather. Acknowledgement is not the same as a rescue commitment."
                elif ship.archetype == TrafficArchetype.SOVIET_TRAWLER:
                    hint = "Notebook hint: foreign traffic may be terse near working boundaries. Treat navigation claims as reports, not surveyed fixes."
                else:
                    hint = "Notebook hint: a peer's fishing report is a lead, not a guarantee. Compare separate reports and your own observations before making a long run."
                self.record_log_entry(hint)
        else:
            self.radio_ui_status = "%s — %s" % (exchange.intent.replace("_", " ").upper(), exchange.reason)

        lines = history["lines"]
        tx_line = {"speaker": "KŌEI MARU · TX", "text": exchange.transmit_text, "kind": "TX"}
        lines.append(tx_line)
        self.record_log_entry("Radio: [VESSEL]: %s" % exchange.transmit_text)
        if exchange.delivered:
            for _delay, speaker, text, _channel in exchange.turns:
                lines.append({"speaker": str(speaker), "text": str(text), "kind": "RX" if str(speaker).upper() != "KŌEI MARU" else "TX"})
        else:
            lines.append({"speaker": "RADIO SET", "text": exchange.reason or "Only static answers.", "kind": "STATIC"})
        self.radio_ui_active_end[ship.id] = len(lines)
        history["visible_count"] = len(lines) - (len(exchange.turns) if exchange.delivered else 1)
        # Clamp histories without discarding a currently staged conversation.
        if len(lines) > 100:
            trim = len(lines) - 100
            del lines[:trim]
            history["visible_count"] = max(0, history["visible_count"] - trim)
            self.radio_ui_active_end[ship.id] = max(history["visible_count"], self.radio_ui_active_end[ship.id] - trim)
        return True

    def _radio_ui_decide_distress(self, decision):
        """Record a single player response to a received MAYDAY, with paced radio text."""
        ship = self._radio_ui_selected_ship()
        if ship is None:
            self.radio_ui_status = "No vessel selected."
            return False
        if not self.radio_station_ok():
            self.radio_ui_status = "WIRELESS UNMANNED — the MAYDAY decision cannot be transmitted."
            return False
        if (self.radio_calls or self.pending_radio_calls or self.radio_transcript_queue
                or self.radio_bubble_t > 0.25 or self.broadcast_director.is_busy()):
            self.radio_ui_status = "CHANNEL BUSY — wait until urgent radio traffic clears."
            return False
        if self.ai_rescue_manager.is_responding_to(ship.id):
            self.radio_ui_status = "ANOTHER VESSEL IS ALREADY RESPONDING — stand by for its report."
            return False
        if decision == "assist":
            if self.player_rescue_manager.has_active_mission:
                self.radio_ui_status = "RESCUE ALREADY ACTIVE — finish or break off the current assistance first."
                return False
            report = getattr(ship, "last_reported_position_nm", None)
            if not isinstance(report, (tuple, list)) or len(report) != 2 or not all(math.isfinite(float(v)) for v in report):
                self.radio_ui_status = "NO USABLE POSITION PLOT — unable to commit a rescue course yet."
                return False
        trust_before = float(ship.trust)
        last_contact_before = float(ship.last_contact_sim_time)
        decisions_before = int(self.distress_dispatcher.decisions_applied)
        applied, status = self.distress_dispatcher.decide(ship, decision, self.world.time)
        if not applied:
            self.radio_ui_status = status
            return False
        self._prepare_broadcast_priority(PRIORITY_HIGH)
        history = self.radio_ui_histories.setdefault(ship.id, {"lines": [], "visible_count": 0})
        lines = history["lines"]
        if decision == "assist":
            tx = ("Mayday vessel, this is Kōei Maru. We copy your distress and will render assistance. "
                  "State your condition and keep this frequency clear. Over.")
            rx = ("Kōei Maru, this is %s. Roger, assistance acknowledged. We will hold to our reported plot "
                  "and await your next transmission. Over." % ship.callsign)
            lines.append({"speaker": "KŌEI MARU · TX", "text": tx, "kind": "TX"})
            lines.append({"speaker": ship.callsign, "text": rx, "kind": "RX"})
            history["visible_count"] = len(lines) - 1
            self.radio_ui_active_end[ship.id] = len(lines)
            self.radio_ui_status = status
            self.record_log_entry("MAYDAY response: Kōei Maru acknowledged %s and committed to assist; trust changed once." % ship.callsign)
            try:
                started = self._start_player_rescue_mission(ship)
                if not started:
                    raise ValueError("rescue mission could not be dispatched")
            except Exception:
                # The player decision and its trust effect are atomic with the mission
                # handover. A routing/setup error must not consume the one-shot MAYDAY.
                failed_mission = self.player_rescue_manager.mission
                if failed_mission is not None:
                    self._restore_rescue_navigation(failed_mission)
                self.player_rescue_manager.mission = None
                ship.trust = trust_before
                ship.distress_decision = None
                ship.mayday_resolved = False
                ship.distress_assistance_status = "none"
                ship.last_contact_sim_time = last_contact_before
                self.distress_dispatcher.decisions_applied = decisions_before
                self.radio_ui_status = "RESCUE DISPATCH FAILED — MAYDAY decision was not consumed; retry after checking navigation."
                return False
        else:
            lines.append({"speaker": "RADIO SET", "text": "No transmission sent. Kōei Maru clears the frequency without answering the MAYDAY.", "kind": "STATIC"})
            history["visible_count"] = len(lines)
            self.radio_ui_active_end[ship.id] = len(lines)
            self.radio_ui_status = status
            self.traffic_world.release_rescue_contact(ship.id)
            self.record_log_entry("MAYDAY ignored: Kōei Maru made no reply to %s. Trust consequence applied once." % ship.callsign)
        return True

    def _radio_ui_next(self):
        ship = self._radio_ui_selected_ship()
        if ship is None:
            return
        history = self.radio_ui_histories.setdefault(ship.id, {"lines": [], "visible_count": 0})
        end = self.radio_ui_active_end.get(ship.id, len(history["lines"]))
        if history["visible_count"] < end:
            line = history["lines"][history["visible_count"]]
            history["visible_count"] += 1
            self.record_log_entry("Radio: [%s]: %s" % (line["speaker"], line["text"]))
            self.radio_ui_status = "%s transmitted." % line["speaker"]
        else:
            self._radio_ui_select_next_ship(1)

    def _handle_radio_ui(self, ev):
        """Modal input for ship selection, topic transmission, and paced dialogue."""
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                self.radio_ui_open = False
                return True
            if ev.key == pygame.K_TAB:
                self._radio_ui_select_next_ship(1)
                return True
            if ev.key in (pygame.K_UP, pygame.K_DOWN):
                self._radio_ui_select_next_ship(-1 if ev.key == pygame.K_UP else 1)
                return True
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                ship = self._radio_ui_selected_ship()
                history = self.radio_ui_histories.get(ship.id, {}) if ship else {}
                end = self.radio_ui_active_end.get(ship.id, len(history.get("lines", []))) if ship else 0
                if ship is not None and history.get("visible_count", 0) < end:
                    self._radio_ui_next()
                else:
                    self._radio_ui_start_topic("hail")
                return True
            ship = self._radio_ui_selected_ship()
            distress_action = bool(ship and ship.mayday_player_heard and not ship.mayday_resolved)
            if distress_action and ev.key == pygame.K_a:
                self._radio_ui_decide_distress("assist")
                return True
            if distress_action and ev.key == pygame.K_i:
                self._radio_ui_decide_distress("ignore")
                return True
            topic_keys = {pygame.K_1: "hail", pygame.K_2: "position", pygame.K_3: "weather",
                          pygame.K_4: "activity", pygame.K_5: "grounds", pygame.K_6: "crew", pygame.K_7: "name"}
            if ev.key in topic_keys:
                self._radio_ui_start_topic(topic_keys[ev.key])
                return True
            if ev.key == pygame.K_F11 and (getattr(ev, "mod", pygame.key.get_mods()) & pygame.KMOD_CTRL):
                self.radio_ui_open = False
                return True
            return True
        if ev.type == pygame.MOUSEWHEEL:
            if self.radio_ui_contacts:
                visible = int(getattr(self, "radio_ui_visible_rows", 3))
                self.radio_ui_scroll = int(clamp(self.radio_ui_scroll - ev.y, 0,
                                                 max(0, len(self.radio_ui_contacts) - visible)))
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            if ev.button == 3:
                self.radio_ui_open = False
                return True
            for name, rect in self.radio_ui_hitboxes.items():
                if not rect.collidepoint(ev.pos):
                    continue
                if name == "close":
                    self.radio_ui_open = False
                elif name == "next":
                    self._radio_ui_next()
                elif name == "prev_contact":
                    self._radio_ui_select_next_ship(-1)
                elif name == "next_contact":
                    self._radio_ui_select_next_ship(1)
                elif name.startswith("ship:"):
                    self.radio_ui_selected_ship_id = name.split(":", 1)[1]
                    ship = self._radio_ui_selected_ship()
                    self.radio_ui_status = "Selected %s — choose a radio topic." % ship.callsign if ship else "Contact unavailable."
                elif name == "distress:assist":
                    self._radio_ui_decide_distress("assist")
                elif name == "distress:ignore":
                    self._radio_ui_decide_distress("ignore")
                elif name.startswith("topic:"):
                    self._radio_ui_start_topic(name.split(":", 1)[1])
                break
            return True
        return True

    def draw_radio_ui(self):
        """Dark, wheelhouse-style radio panel with clickable contacts and paced conversation."""
        if not self.radio_ui_open:
            return
        dim = self._cached_panel_surface((W, H), (3, 9, 13, 218))
        self.screen.blit(dim, (0, 0))
        outer = pygame.Rect(max(18, int(W * 0.055)), max(16, int(H * 0.045)),
                            min(W - 36, 1010), min(H - 32, 680))
        outer.center = (W // 2, H // 2)
        bg, panel, border = (13, 25, 31), (20, 38, 44), (115, 148, 145)
        pygame.draw.rect(self.screen, bg, outer, border_radius=10)
        pygame.draw.rect(self.screen, border, outer, 2, border_radius=10)
        header = pygame.Rect(outer.x + 2, outer.y + 2, outer.w - 4, 62)
        pygame.draw.rect(self.screen, (27, 52, 59), header, border_radius=8)
        self.screen.blit(self.chart_title_font.render("WIRELESS  /  FLEET CONTACTS", True, (237, 225, 187)),
                         (outer.x + 18, outer.y + 9))
        status_text = "2182 kHz  ·  %s" % ("WATCH ACTIVE" if self.radio_station_ok() else "NO OPERATOR AT SET")
        self.screen.blit(self.chart_small_font.render(status_text, True,
                         (140, 216, 171) if self.radio_station_ok() else (236, 166, 116)),
                         (outer.x + 20, outer.y + 39))
        close_rect = pygame.Rect(outer.right - 88, outer.y + 15, 70, 30)
        pygame.draw.rect(self.screen, (59, 74, 77), close_rect, border_radius=4)
        pygame.draw.rect(self.screen, border, close_rect, 1, border_radius=4)
        self.screen.blit(self.chart_small_font.render("CLOSE  Esc", True, (239, 236, 216)), (close_rect.x + 6, close_rect.y + 8))
        self.radio_ui_hitboxes = {"close": close_rect}

        body_top = outer.y + 78
        body_bottom = outer.bottom - 68
        left_w = int((outer.w - 44) * 0.32)
        left = pygame.Rect(outer.x + 14, body_top, left_w, body_bottom - body_top)
        right = pygame.Rect(left.right + 12, body_top, outer.right - left.right - 26, body_bottom - body_top)
        for rect in (left, right):
            pygame.draw.rect(self.screen, panel, rect, border_radius=5)
            pygame.draw.rect(self.screen, (70, 101, 101), rect, 1, border_radius=5)
        self.screen.blit(self.chart_header_font.render("VESSELS IN THE NEIGHBOURHOOD", True, (221, 210, 170)),
                         (left.x + 10, left.y + 9))
        list_top = left.y + 36
        list_bottom = left.bottom - 42  # reserve the bottom row for Prev/Next contact buttons
        row_h = 38
        visible = max(2, (list_bottom - list_top) // row_h)
        self.radio_ui_visible_rows = visible
        self.radio_ui_scroll = int(clamp(self.radio_ui_scroll, 0, max(0, len(self.radio_ui_contacts) - visible)))
        for row_idx, ship in enumerate(self.radio_ui_contacts[self.radio_ui_scroll:self.radio_ui_scroll + visible]):
            y = list_top + row_idx * row_h
            rect = pygame.Rect(left.x + 6, y, left.w - 12, row_h - 3)
            selected = ship.id == self.radio_ui_selected_ship_id
            distance = self._radio_ui_distance(ship)
            reachable = distance <= ship.radio_range_nm
            fill = (57, 75, 66) if selected else ((23, 51, 52) if reachable else (38, 40, 39))
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            pygame.draw.rect(self.screen, (208, 176, 100) if selected else (63, 93, 92), rect,
                             2 if selected else 1, border_radius=3)
            name = self.chart_small_font.render(ship.callsign[:24], True, (244, 229, 190) if reachable else (155, 156, 145))
            distress_tag = "  / MAYDAY" if ship.mayday_player_heard and not ship.mayday_resolved else ""
            sub = "%0.1f nm  ·  %s%s%s" % (distance, ship.activity.value.replace("_", " ").upper(),
                                          "  / OUT OF RANGE" if not reachable else "", distress_tag)
            self.screen.blit(name, (rect.x + 6, rect.y + 4))
            self.screen.blit(self.chart_small_font.render(sub[:38], True, (183, 204, 189) if reachable else (151, 147, 130)),
                             (rect.x + 6, rect.y + 20))
            self.radio_ui_hitboxes["ship:" + ship.id] = rect
        if not self.radio_ui_contacts:
            self.screen.blit(self.chart_font.render("No scheduled vessels nearby.", True, (194, 205, 190)),
                             (left.x + 12, list_top + 12))
        # Contact paging is separate from the contact-list scroll.
        for name, label in (("prev_contact", "‹ PREV"), ("next_contact", "NEXT ›")):
            width = 76
            rect = pygame.Rect(left.x + 8 if name == "prev_contact" else left.right - width - 8,
                               left.bottom - 32, width, 24)
            pygame.draw.rect(self.screen, (44, 65, 68), rect, border_radius=3)
            pygame.draw.rect(self.screen, (94, 124, 121), rect, 1, border_radius=3)
            self.screen.blit(self.chart_small_font.render(label, True, (238, 231, 205)), (rect.x + 7, rect.y + 5))
            self.radio_ui_hitboxes[name] = rect

        ship = self._radio_ui_selected_ship()
        if ship is None:
            self.screen.blit(self.chart_header_font.render("NO CONTACT SELECTED", True, (221, 210, 170)), (right.x + 12, right.y + 10))
        else:
            dist = self._radio_ui_distance(ship)
            reach = "IN RANGE" if dist <= ship.radio_range_nm else "OUT OF RANGE — %.0f nm SET" % ship.radio_range_nm
            self.screen.blit(self.chart_header_font.render("%s  /  %s" % (ship.name.upper(), ship.callsign), True, (241, 225, 187)),
                             (right.x + 12, right.y + 9))
            distress_detail = ("  ·  MAYDAY — DECISION REQUIRED" if ship.mayday_player_heard and not ship.mayday_resolved
                               else ("  ·  RESPONSE: %s" % ship.distress_decision.upper() if ship.distress_decision else ""))
            detail = "%s  ·  %s  ·  %.1f nm  ·  %s%s" % (
                ship.archetype.value.replace("_", " ").upper(), ship.activity.value.replace("_", " ").upper(), dist, reach, distress_detail)
            self.screen.blit(self.chart_small_font.render(detail[:100], True,
                             (153, 218, 174) if dist <= ship.radio_range_nm else (229, 160, 123)),
                             (right.x + 14, right.y + 32))
        topic_specs = (("hail", "1  HAIL"), ("position", "2  POSITION"), ("weather", "3  WEATHER"),
                       ("activity", "4  ACTIVITY"), ("grounds", "5  GROUNDS"),
                       ("crew", "6  CREW"), ("name", "7  IDENTIFY"))
        topic_top = right.y + 57
        gap = 6
        bw = max(68, (right.w - 24 - gap * 3) // 4)
        for index, (topic, label) in enumerate(topic_specs):
            row, col = divmod(index, 4)
            rect = pygame.Rect(right.x + 10 + col * (bw + gap), topic_top + row * 34, bw, 28)
            active = ship is not None and self._radio_ui_distance(ship) <= ship.radio_range_nm and self.radio_station_ok()
            pygame.draw.rect(self.screen, (44, 74, 69) if active else (43, 48, 47), rect, border_radius=4)
            pygame.draw.rect(self.screen, (104, 147, 126) if active else (75, 92, 88), rect, 1, border_radius=4)
            tx = self.chart_small_font.render(label, True, (232, 236, 213) if active else (155, 165, 156))
            if tx.get_width() > rect.w - 8:
                tx = self.chart_small_font.render(label.split("  ")[-1], True, (232, 236, 213) if active else (155, 165, 156))
            self.screen.blit(tx, (rect.x + 4, rect.y + 8))
            self.radio_ui_hitboxes["topic:" + topic] = rect

        distress_active = bool(ship and ship.mayday_player_heard and not ship.mayday_resolved)
        transcript_offset = 76
        if distress_active:
            action_y = topic_top + 68
            assist_rect = pygame.Rect(right.x + 10, action_y, 142, 28)
            ignore_rect = pygame.Rect(assist_rect.right + 8, action_y, 142, 28)
            for rect, fill, label in ((assist_rect, (116, 75, 44), "A  ASSIST MAYDAY"),
                                      (ignore_rect, (70, 56, 51), "I  IGNORE")):
                pygame.draw.rect(self.screen, fill, rect, border_radius=4)
                pygame.draw.rect(self.screen, (225, 166, 91), rect, 1, border_radius=4)
                self.screen.blit(self.chart_small_font.render(label, True, (250, 235, 204)),
                                 (rect.x + 7, rect.y + 8))
            self.radio_ui_hitboxes["distress:assist"] = assist_rect
            self.radio_ui_hitboxes["distress:ignore"] = ignore_rect
            transcript_offset = 104
        transcript_rect = pygame.Rect(right.x + 10, topic_top + transcript_offset, right.w - 20,
                                      right.bottom - (topic_top + transcript_offset) - 12)
        pygame.draw.rect(self.screen, (7, 17, 21), transcript_rect, border_radius=4)
        pygame.draw.rect(self.screen, (51, 86, 85), transcript_rect, 1, border_radius=4)
        self.screen.blit(self.chart_small_font.render("EXCHANGE / TRANSMISSION LOG", True, (212, 190, 131)),
                         (transcript_rect.x + 8, transcript_rect.y + 7))
        history = self.radio_ui_histories.get(ship.id, {"lines": [], "visible_count": 0}) if ship else {"lines": [], "visible_count": 0}
        revealed = history.get("lines", [])[:history.get("visible_count", 0)]
        transcript_clip = self.screen.get_clip()
        self.screen.set_clip(transcript_rect.inflate(-4, -4))
        y = transcript_rect.y + 27
        available_h = transcript_rect.h - 38
        for line in revealed[-max(1, available_h // 33):]:
            speaker = str(line.get("speaker", "RADIO"))
            col = (241, 201, 122) if line.get("kind") == "TX" else ((143, 210, 174) if line.get("kind") == "RX" else (204, 168, 133))
            head = self.chart_small_font.render(speaker[:48], True, col)
            self.screen.blit(head, (transcript_rect.x + 8, y))
            y += 15
            wrap = self._wrap_notebook_text(self.chart_small_font, str(line.get("text", "")), transcript_rect.w - 18)
            for text_line in wrap[:2]:
                if y + 14 > transcript_rect.bottom - 4:
                    break
                self.screen.blit(self.chart_small_font.render(text_line, True, (222, 229, 217)),
                                 (transcript_rect.x + 10, y))
                y += 14
            y += 2
            if y > transcript_rect.bottom - 15:
                break
        if not revealed:
            prompt = ["Select a vessel on the left.", "Pick a topic to transmit.", "Use NEXT to step through each reply."]
            for i, line in enumerate(prompt):
                self.screen.blit(self.chart_font.render(line, True, (150, 175, 165)),
                                 (transcript_rect.x + 12, transcript_rect.y + 46 + i * 22))
        self.screen.set_clip(transcript_clip)

        footer_y = outer.bottom - 52
        status_lines = self._wrap_notebook_text(self.chart_small_font, self.radio_ui_status, outer.w - 220)
        for i, line in enumerate(status_lines[:2]):
            self.screen.blit(self.chart_small_font.render(line, True, (226, 211, 168)), (outer.x + 16, footer_y + i * 15))
        next_rect = pygame.Rect(outer.right - 184, footer_y - 3, 166, 38)
        pygame.draw.rect(self.screen, (55, 86, 75), next_rect, border_radius=5)
        pygame.draw.rect(self.screen, (164, 191, 143), next_rect, 2, border_radius=5)
        pending = bool(ship and self.radio_ui_histories.get(ship.id, {}).get("visible_count", 0)
                       < self.radio_ui_active_end.get(ship.id, 0))
        next_label = "NEXT LINE  →" if pending else "NEXT SHIP  →"
        self.screen.blit(self.chart_header_font.render(next_label, True, (242, 237, 212)),
                         (next_rect.x + 10, next_rect.y + 9))
        self.radio_ui_hitboxes["next"] = next_rect
        footer_help = "Click a ship or topic · Enter / Space = next · Tab = next ship · 1–7 = topic"
        if distress_active:
            footer_help += " · A = assist / I = ignore"
        self.screen.blit(self.chart_small_font.render(footer_help,
                         True, (146, 164, 157)), (outer.x + 16, outer.bottom - 17))

    def draw_ai_traffic(self):
        """Draw nearby active vessels as small hull silhouettes in the sea view."""
        if (not hasattr(self, "traffic_world") or self.chart_open
                or self.view_level() != Level.MAIN):
            return
        w = self.world
        player_nm = self._traffic_player_position_nm()
        tow_id = getattr(getattr(self, "tow_escort", None), "vessel_id", None)
        for ship in self.traffic_world.nearby(player_nm, self._traffic_visual_range_nm()):
            if ship.id == tow_id or ship.lod != "active":
                continue
            # Keep deck clutter down: the hull is drawn only when its centre can appear
            # inside the camera; radio range never activates a rendered ship by itself.
            legacy_nm = self._active_nm_to_legacy_nm(ship.position_nm)
            world_position = V(legacy_nm[0] * 185.2 * w.scale,
                               -legacy_nm[1] * 185.2 * w.scale)
            centre_local = w.deck_of(world_position)
            if (abs(centre_local.x) > W / max(0.10, self.zoom) * 0.58 + self.ship.length
                    or abs(centre_local.y) > H / max(0.10, self.zoom) * 0.58 + self.ship.length):
                continue
            relative_heading = ship.heading_rad - float(w.heading)
            hull_scale, beam_scale = 0.42, 0.48
            def pnt(x, y, inset=1.0):
                local = V(x * hull_scale * inset, y * beam_scale * inset).rotate_rad(relative_heading)
                return self.S(centre_local + local)
            hull = [pnt(p.x, p.y) for p in self.ship.hull]
            deck = [pnt(p.x, p.y, 0.90) for p in self.ship.hull]
            if ship.archetype == TrafficArchetype.SOVIET_TRAWLER:
                hull_color, deck_color, stripe = (61, 68, 54), (184, 183, 154), (194, 132, 57)
            elif ship.archetype == TrafficArchetype.COAST_GUARD:
                hull_color, deck_color, stripe = (28, 49, 67), (218, 224, 213), (232, 104, 41)
            elif ship.archetype in (TrafficArchetype.CORPORATE_CATCHER, TrafficArchetype.CORPORATE_LONGLINER,
                                    TrafficArchetype.MOTHERSHIP):
                hull_color, deck_color, stripe = (35, 48, 57), (199, 206, 195), (201, 162, 39)
            else:
                hull_color, deck_color, stripe = (71, 83, 83), (214, 209, 188), (120, 151, 150)
            pygame.draw.polygon(self.screen, hull_color, hull)
            pygame.draw.lines(self.screen, (30, 38, 39), True, hull, max(1, int(2 * self.zoom)))
            pygame.draw.polygon(self.screen, deck_color, deck)
            pygame.draw.lines(self.screen, (71, 79, 74), True, deck, max(1, int(self.zoom)))
            stripe_points = [pnt(-self.ship.length * 0.26, -self.ship.beam * 0.24),
                             pnt(self.ship.length * 0.25, -self.ship.beam * 0.24)]
            pygame.draw.line(self.screen, stripe, stripe_points[0], stripe_points[1], max(1, int(3 * self.zoom)))
            # Reported/known contact name only appears when close enough for a lookout or radio plot.
            if ship.known_to_player and self.zoom >= 0.24:
                label = self.chart_small_font.render(ship.name, True, (231, 225, 196))
                label_pos = self.S(centre_local + V(0, -self.ship.beam * 0.35))
                self.screen.blit(label, (label_pos[0] - label.get_width() // 2, label_pos[1] - label.get_height()))

    def draw_traffic_chart_contacts(self, chart_surface, point, map_w, map_h, pal):
        """Draw only known reported plots; exact physical positions never reach the chart."""
        if not hasattr(self, "traffic_world"):
            return
        now = float(self.world.time)
        color_for = {
            TrafficArchetype.INDEPENDENT_LONGLINE: (66, 108, 105),
            TrafficArchetype.INDEPENDENT_GILLNET: (71, 116, 134),
            TrafficArchetype.CORPORATE_CATCHER: (100, 91, 65),
            TrafficArchetype.CORPORATE_LONGLINER: (126, 91, 52),
            TrafficArchetype.MOTHERSHIP: (81, 67, 119),
            TrafficArchetype.COAST_GUARD: pal.get("tow", (211, 105, 51)),
            TrafficArchetype.SOVIET_TRAWLER: (93, 105, 70),
        }
        for ship in self.traffic_world.known_contacts():
            report = ship.last_reported_position_nm
            if not ship.known_to_player or report is None:
                continue
            x, y = float(report[0]) * 185.2, -float(report[1]) * 185.2
            if not within_chart_bounds(x, y):
                continue
            sx, sy = point(x, y)
            stale = ship.report_stale_at(now)
            color = (128, 125, 108) if stale else color_for.get(ship.archetype, pal["ink"])
            angle = float(ship.last_reported_heading_rad)
            tip = (sx + int(9 * math.cos(angle)), sy + int(9 * math.sin(angle)))
            left = (sx + int(-6 * math.cos(angle) - 4 * math.sin(angle)),
                    sy + int(-6 * math.sin(angle) + 4 * math.cos(angle)))
            right = (sx + int(-6 * math.cos(angle) + 4 * math.sin(angle)),
                     sy + int(-6 * math.sin(angle) - 4 * math.cos(angle)))
            poly = [tip, left, right]
            pygame.draw.polygon(chart_surface, color, poly)
            pygame.draw.polygon(chart_surface, pal["paper"], poly, 1)
            age_s = ship.report_age_s(now)
            suffix = "?" if stale else ""
            prefix = "CG " if getattr(ship, "runtime_kind", "scheduled") == "tow_escort" else ""
            if math.isfinite(age_s):
                label_text = "%s%s%s (%dm ago)" % (prefix, ship.callsign, suffix, int(age_s * 2.4))
            else:
                label_text = "%s%s? (age unknown)" % (prefix, ship.callsign)
            label = self.chart_small_font.render(label_text, True, color)
            lx = int(clamp(sx + 9, 2, map_w - label.get_width() - 2))
            ly = int(clamp(sy - label.get_height() - 3, 2, map_h - label.get_height() - 2))
            chart_surface.blit(label, (lx, ly))

    def draw_tow_escort(self):
        """Draw the Coast Guard launch as a separate hull moving through the water."""
        escort = getattr(self, "tow_escort", None)
        if (escort is None or escort.state not in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW")
                or self.chart_open or self.view_level() != Level.MAIN):
            return
        w = self.world
        # Escort positions are stored in chart units; convert to world coordinates,
        # then into the player hull's camera-relative frame.
        tow_world = V(escort.true_position) * w.scale
        centre_local = w.deck_of(tow_world)
        relative_heading = float(escort.heading) - float(w.heading)
        if (abs(centre_local.x) > W / max(0.10, self.zoom) + self.ship.length
                or abs(centre_local.y) > H / max(0.10, self.zoom) + self.ship.length):
            return

        # PLACE HOLDER SHIP: reuse the player's hull outline as the visual reference
        # for now. A dedicated Coast Guard sprite/model can replace this drawing later.
        hull_length_scale, hull_beam_scale = 0.76, 0.82

        def point(x, y, inset=1.0):
            local = V(x * hull_length_scale * inset,
                      y * hull_beam_scale * inset).rotate_rad(relative_heading)
            return self.S(centre_local + local)

        screen = self.screen
        hull = [point(p.x, p.y) for p in self.ship.hull]
        deck = [point(p.x, p.y, 0.91) for p in self.ship.hull]
        # Deep navy hull, light weather deck and international orange safety stripe.
        pygame.draw.polygon(screen, (28, 49, 67), hull)
        pygame.draw.lines(screen, (220, 226, 218), True, hull, max(2, int(3 * self.zoom)))
        pygame.draw.polygon(screen, (218, 224, 213), deck)
        pygame.draw.lines(screen, (77, 95, 103), True, deck, max(1, int(1.5 * self.zoom)))

        def local_point(x, y):
            return point(x, y)

        stripe_y = self.ship.beam * 0.36
        for side in (-1, 1):
            stripe = [local_point(-self.ship.length * 0.35, side * stripe_y),
                      local_point(-self.ship.length * 0.12, side * stripe_y),
                      local_point(self.ship.length * 0.16, side * stripe_y),
                      local_point(self.ship.length * 0.31, side * stripe_y * 0.72)]
            pygame.draw.lines(screen, (232, 104, 41), False, stripe, max(2, int(5 * self.zoom)))

        # A compact bridge and two dark windows make it read as a working launch,
        # while the hull remains the same recognizable shape as the fishing vessel.
        bridge = [local_point(-85, -48), local_point(145, -48),
                  local_point(190, -24), local_point(190, 24),
                  local_point(145, 48), local_point(-85, 48)]
        pygame.draw.polygon(screen, (197, 210, 211), bridge)
        pygame.draw.lines(screen, (39, 57, 68), True, bridge, max(1, int(2 * self.zoom)))
        for wx in (8, 82, 145):
            window = [local_point(wx, -37), local_point(wx + 30, -37),
                      local_point(wx + 30, 37), local_point(wx, 37)]
            pygame.draw.polygon(screen, (40, 72, 88), window)
            pygame.draw.polygon(screen, (232, 237, 220), window, max(1, int(self.zoom)))
        # Wake marks trail the stern, reinforcing that this hull is under way.
        wake_a = point(-self.ship.length * 0.43, -self.ship.beam * 0.18)
        wake_b = point(-self.ship.length * 0.60, -self.ship.beam * 0.29)
        wake_c = point(-self.ship.length * 0.43, self.ship.beam * 0.18)
        wake_d = point(-self.ship.length * 0.60, self.ship.beam * 0.29)
        pygame.draw.line(screen, (153, 199, 205), wake_a, wake_b, max(1, int(2 * self.zoom)))
        pygame.draw.line(screen, (153, 199, 205), wake_c, wake_d, max(1, int(2 * self.zoom)))

    def draw_tow_escort_towline(self):
        """Render the working towline between our bow and the launch's stern."""
        escort = getattr(self, "tow_escort", None)
        if (escort is None or escort.state != "UNDER_TOW" or self.chart_open
                or self.view_level() != Level.MAIN):
            return
        w = self.world
        tow_world = V(escort.true_position) * w.scale
        centre_local = w.deck_of(tow_world)
        relative_heading = float(escort.heading) - float(w.heading)
        player_bow = self.SS(V(self.ship.length * 0.49, 0.0))
        tug_stern = self.S(centre_local + V(-self.ship.length * 0.49 * 0.76, 0.0).rotate_rad(relative_heading))
        color = (232, 133, 66) if escort.line_at_risk else (220, 211, 174)
        width = max(2, int(3 * self.zoom))
        if escort.line_at_risk:
            self._draw_dashed_screen_line(self.screen, player_bow, tug_stern, color, width=width, dash=8, gap=6)
        else:
            pygame.draw.line(self.screen, color, player_bow, tug_stern, width)

    def draw_rescue_boat(self):
        """Render a person-sized rescue dinghy, including seats, two rescuers and a casualty."""
        boat = self.rescue_boat_state
        if not boat or boat.get("phase") not in ("out", "pickup", "return"):
            return
        pos = V(boat["pos"])
        local = self.world.deck_of(pos)
        angle = float(boat.get("heading", 0.0)) - self.world.heading

        def point(x, y):
            return self.S(local + V(x, y).rotate_rad(angle))

        # 176 x 66 world units: large enough for two paddlers and one recovered adult.
        hull = [point(90, 0), point(75, -22), point(48, -32), point(-58, -32),
                point(-82, -22), point(-88, -10), point(-88, 10), point(-82, 22),
                point(-58, 32), point(48, 32), point(75, 22)]
        deck = [point(78, 0), point(65, -17), point(43, -25), point(-55, -25),
                point(-73, -17), point(-79, -8), point(-79, 8), point(-73, 17),
                point(-55, 25), point(43, 25), point(65, 17)]
        hull_edge = max(1, int(2.5 * self.zoom))
        pygame.draw.polygon(self.screen, hexc("#c5a16a"), hull)
        pygame.draw.lines(self.screen, hexc("#543b27"), True, hull, hull_edge + 1)
        pygame.draw.polygon(self.screen, hexc("#e0c38d"), deck)
        pygame.draw.lines(self.screen, hexc("#9c7546"), True, deck, max(1, int(self.zoom)))
        # Rubbing strake / gunwales and three rowing thwarts make the craft visually legible.
        for side in (-1, 1):
            gunwale = [point(70, side * 18), point(44, side * 28),
                       point(-55, side * 28), point(-77, side * 16)]
            pygame.draw.lines(self.screen, hexc("#6c4c31"), False, gunwale, hull_edge)
            pygame.draw.line(self.screen, hexc("#e8d8b1"), point(-5, side * 24), point(4, side * 53), hull_edge)
        for x in (-38, 2, 43):
            pygame.draw.line(self.screen, hexc("#8b633c"), point(x, -22), point(x, 22), max(2, int(3 * self.zoom)))
        pygame.draw.line(self.screen, hexc("#8b633c"), point(-63, 0), point(65, 0), max(1, int(2 * self.zoom)))

        def seated_sailor(sailor, x, fallback_color):
            color = sailor.jacket if sailor is not None else fallback_color
            # Torso is aligned with the boat; the circular head remains easily visible at normal zoom.
            body_w = max(4, int(10 * self.zoom))
            pygame.draw.line(self.screen, tuple(max(0, int(c * 0.66)) for c in color),
                             point(x - 8, 0), point(x + 8, 0), body_w)
            pygame.draw.circle(self.screen, color, point(x, 0), max(4, int(7.5 * self.zoom)))
            # Faces are deliberately turned to the boat's starboard gunwale (+y)
            # instead of inheriting a drifting camera/ship-relative direction.
            pygame.draw.circle(self.screen, hexc("#f0c9a2"), point(x, 4), max(3, int(4.5 * self.zoom)))
            # A small nose wedge makes the facing direction readable even when the
            # dinghy is rendered at ordinary gameplay zoom. Local +y is starboard.
            pygame.draw.polygon(self.screen, hexc("#f0c9a2"),
                                [point(x, 9), point(x - 2.5, 5), point(x + 2.5, 5)])
            # Life vest band gives each occupant a distinct, high-contrast silhouette.
            pygame.draw.line(self.screen, hexc("#f2bd39"), point(x - 4, -2), point(x + 4, -2), max(2, int(3 * self.zoom)))

        crew = list(boat.get("crew", []))
        if crew:
            seated_sailor(crew[0], -30, hexc("#d34e3f"))
        if len(crew) > 1:
            seated_sailor(crew[1], 8, hexc("#d34e3f"))
        passenger = boat.get("passenger")
        if passenger is not None:
            seated_sailor(passenger, 48, hexc("#e3d5ba"))
        # Oar blades extend outboard of the gunwale, not through the hull.
        for x, side in ((-28, -1), (6, 1)):
            a, b = point(x - 5, side * 17), point(x + 14, side * 52)
            pygame.draw.line(self.screen, hexc("#4c3525"), a, b, max(2, int(3 * self.zoom)))
            pygame.draw.line(self.screen, hexc("#dbc69b"), point(x + 11, side * 45), b, max(3, int(5 * self.zoom)))
        if boat.get("phase") == "pickup":
            center = point(75, 0)
            pygame.draw.circle(self.screen, hexc("#f3d45c"), center, max(5, int(11 * self.zoom)), max(2, int(2 * self.zoom)))

    def _apply_hull_strikes(self, dt):
        """What a wave does to the hull itself: bows slam and lose way, beam seas kick the roll."""
        w = self.world
        for st in w.hull_strikes:
            e = st.energy
            side = {"stbd": 1.0, "port": -1.0}.get(st.zone, 0.0)
            if st.kind == "overtop":
                if st.zone == "bow":
                    w.speed *= 1.0 - 0.10 * e
                self.roll_v += side * 0.9 * e              # green water on one side weighs that side down
            else:
                if st.zone == "bow":
                    w.speed *= 1.0 - 0.03 * e
                self.roll_v += -side * 1.4 * e             # a crest slapping the side lifts it
            self.slam_t = max(getattr(self, "slam_t", 0.0), 0.6 * e)
        self.slam_t = max(0.0, getattr(self, "slam_t", 0.0) - dt)

    def _update_flood_alerts(self, dt):
        """Crew calls for the flooding state machine, the list, and the bilge pump."""
        ship = self.ship
        rep = ship.last_flood_report
        self.flood_msg_t = max(0.0, getattr(self, "flood_msg_t", 0.0) - dt)
        if rep is not None and rep.changed:
            line = {"TAKING_ON_WATER": "Captain: We're taking on water. Shut every hatch and keep the bilge pump running.",
                    "FLOODED": "Captain: She's flooding! Buckets to the water, hatches dogged, and get her head into it!",
                    "CRITICAL": "Captain: She's going down by the weight of the water! Clear the lifeboat and stand by to abandon ship!"
                    }.get(rep.state)
            if line:
                self.crew.say(line)
                self.flood_msg_t = 12.0
        if abs(ship.list_trim) > 0.22 and ship.flood > 0.30 and self.flood_msg_t <= 0.0:
            self.crew.say("Captain: She's lolling %s with water on deck! Clear the scuppers and bail!" %
                          ("to starboard" if ship.list_trim > 0 else "to port"))
            self.flood_msg_t = 25.0
        if ship.engine_flood > 0.20 and not getattr(self, "_pump_warn_pump", False) and ship.pump_flow > 0.0:
            self._pump_warn_pump = True
            self.crew.say("Engine room: Bilge pump is running and pulling on the bilge.")
        elif ship.engine_flood > 0.30 and ship.pump_flow <= 0.0 and self.flood_msg_t <= 0.0:
            self.crew.say("Engine room: No power to the bilge pump! Get the diesel back, or bucket her out!")
            self.flood_msg_t = 30.0
        if ship.engine_flood < 0.05:
            self._pump_warn_pump = False

    def _bucket_water_needed(self):
        """Use hysteresis so the bucket team doesn't repeatedly start/stop in rough weather."""
        if self.ship.bucket_count < 2:
            return False
        if self.bucket_chain_active:
            return self.ship.wet > 0.48 or self.ship.flood > 0.12
        return self.ship.wet > 0.66 or self.ship.flood > 0.28

    def _update_bucket_chain(self, dt):
        """Assign deckhands, send them to the stern, and remove water only while the line works."""
        self.bucket_work_t = max(0.0, self.bucket_work_t - dt)
        self.bucket_log_t = max(0.0, self.bucket_log_t - dt)
        need_line = self._bucket_water_needed()
        excluded = {"set", "haul", "engine", "rescue", "rush", "muster", "gaff", "dress", "bucket"}
        candidates = []
        if need_line:
            for sailor in self.sailors:
                if (sailor.mode != Sailor.ABOARD or sailor.level != Level.MAIN
                        or sailor.ladder is not None or sailor.health <= 0.35
                        or sailor.role == Sailor.CAPTAIN
                        or sailor in (self.helm_operator, self.radio_operator)
                        or sailor.task in excluded - {"bucket"}
                        or sailor.duty in ("engine", "haul", "set", "radio")):
                    continue
                candidates.append(sailor)
        # Keep hands already at the line in their slots; recruit idle/optional-duty sailors next.
        task_priority = {"bucket": 0, "idle": 1, "clean": 2, "rest": 3,
                         "social": 4, "order": 5, "post": 6}
        candidates.sort(key=lambda s: (task_priority.get(s.task, 7),
                                       0 if s.bucket_slot is not None else 1, s.name))
        team_size = min(3, self.ship.bucket_count, len(candidates)) if need_line else 0
        team = candidates[:team_size] if team_size >= 2 else []
        old_team = set(self.bucket_chain_hands)
        new_team = set(team)
        for sailor in old_team - new_team:
            sailor.bucket_slot = None
            if sailor.task == "bucket":
                sailor._enter("idle")
                sailor.think_t = 0.0
        was_active = self.bucket_chain_active
        self.bucket_chain_hands = new_team
        self.bucket_chain_active = len(team) >= 2
        for slot, sailor in enumerate(team):
            sailor.bucket_slot = slot
            if sailor.task != "bucket":
                sailor._enter("bucket")
                sailor.think_t = 0.0
        if self.bucket_chain_active and not was_active:
            self.crew.say("Deckhands grab buckets and move into position to form a line at the stern.")
        elif was_active and not self.bucket_chain_active:
            self.crew.say("The deck bucket line breaks off; the standing water is under control or too few hands remain.")

        working = [s for s in team if s.task == "bucket" and s.working
                   and s.mode == Sailor.ABOARD and s.level == Level.MAIN
                   and s.pos.distance_to(V(-self.ship.length * 0.5 + 100.0,
                                           ((s.bucket_slot or 0) - 1) * 52.0)) < 45.0]
        if self.bucket_chain_active and len(working) >= 2 and self.bucket_work_t <= 0.0:
            self.bucket_work_t = 1.8
            hands = min(3, len(working))
            old_wet, old_flood = self.ship.wet, self.ship.flood
            # Water is only removed when at least two sailors have physically reached the line.
            self.ship.wet = max(0.20, self.ship.wet - 0.055 * hands)
            self.ship.flood = max(0.0, self.ship.flood - 0.018 * hands)
            if self.bucket_log_t <= 0.0 and (self.ship.wet < old_wet or self.ship.flood < old_flood):
                self.crew.say("The bucket line passes water hand-to-hand and throws it over the stern.")
                self.bucket_log_t = 8.0

        # The engine-room bilge and ice hold are distinct compartments. Buckets lower
        # the water only when hands are actually in the affected room, and closed covers
        # are what stop the water returning at the same rate.
        self.engine_bail_t = max(0.0, self.engine_bail_t - dt)
        if self.ship.engine_flood > 0.20 and self.engine_bail_t <= 0.0:
            self.engine_bail_t = 5.0
            engine_rect = self.ship.below_rooms[0]
            engine_hands = [s for s in self.sailors if s.mode == Sailor.ABOARD and s.level == Level.BELOW
                            and rect_has(engine_rect, s.pos) and s.health > 0.35
                            and s.task not in ("rescue", "rush", "muster")]
            if engine_hands and self.ship.bucket_count > 0:
                before = self.ship.engine_flood
                self.ship.engine_flood = max(0.0, self.ship.engine_flood - 0.035 * min(2, len(engine_hands)))
                if self.ship.engine_flood < before:
                    self.crew.say("A hand below bails water from the engine-room bilge with a bucket.")
        self.hold_bail_t = max(0.0, self.hold_bail_t - dt)
        if self.ship.hold_flood > 0.12 and self.hold_bail_t <= 0.0:
            self.hold_bail_t = 5.0
            hold_rect = self.ship.below_rooms[1]
            hold_hands = [s for s in self.sailors if s.mode == Sailor.ABOARD and s.level == Level.BELOW
                          and rect_has(hold_rect, s.pos) and s.health > 0.35
                          and s.task not in ("rescue", "rush", "muster")]
            if hold_hands and self.ship.bucket_count > 0:
                before = self.ship.hold_flood
                self.ship.hold_flood = max(0.0, self.ship.hold_flood - 0.03 * min(2, len(hold_hands)))
                if self.ship.hold_flood < before:
                    self.crew.say("A hand bails wash water from the ice hold; dog the hold hatches to keep it dry.")
        if self.ship.engine_flood > 0.65:
            self.engine_room_damage = min(1.0, self.engine_room_damage + 0.0008 * dt)
            if random.random() < 0.025 * dt:
                self.crew.say("Engine-room bilge is high! Bucket-bail the water before machinery suffers.")

    def _update_tow_diagnostics(self, dt):
        """F12 console diagnostics for tow triggers; disabled during normal play."""
        if not self.tow_debug_enabled:
            self.tow_debug_last_ship_pos = V(self.world.ship_pos)
            self.tow_debug_sample_elapsed = 0.0
            self.tow_debug_elapsed = 0.0
            return
        step_dt = max(0.0, float(dt))
        self.tow_debug_elapsed += step_dt
        self.tow_debug_sample_elapsed += step_dt
        if self.tow_debug_elapsed < 1.0:
            return
        w = self.world
        now_pos = V(w.ship_pos)
        sample_dt = max(1e-6, self.tow_debug_sample_elapsed)
        sog = (now_pos.distance_to(self.tow_debug_last_ship_pos) / sample_dt
               if self.tow_debug_last_ship_pos is not None else 0.0)
        hour = w.hour()
        clock = "%02d:%02d" % (int(hour) % 24, int((hour % 1.0) * 60.0))
        if self.tow_transit_active:
            tow_state = "UNDER_TOW"
        elif self.tow_request_active:
            tow_state = "REQUESTED"
        else:
            tow_state = "NORMAL"
        print(
            "[TOW DEBUG] date=%s clock=%s fuel=%.1f/%.1f stw=%.3f sog=%.3f "
            "adrift=%s drift_t=%.1f/%.1f anchor=%s tow=%s failed_calls=%d" %
            (w.calendar_date_text(), clock, self.fuel, FUEL_CAP,
             w.speed_through_water, sog,
             is_unpowered_adrift(
                 speed_through_water=w.speed_through_water,
                 engine_on=self._engine_on, engine_ok=self.engine_ok,
                 engine_power=self.engine_power, fuel=self.fuel,
                 anchor_deployed=self.anchor_deployed, docked=self.docked(),
                 tow_in_transit=self.tow_transit_active,
                 speed_threshold=TOW_ADRIFT_SPEED,
             ), self.adrift_elapsed, TOW_TRIGGER_DRIFT_SECONDS,
             self.anchor_deployed, tow_state, self.tow_failed_call_count)
        )
        self.tow_debug_last_ship_pos = now_pos
        self.tow_debug_sample_elapsed = 0.0
        self.tow_debug_elapsed = 0.0

    def _logistics(self, dt):
        w = self.world
        # A tow can be requested by low fuel or by genuinely being adrift with no
        # propulsion. Use speed through water, not chart/ground displacement: current
        # and wind can move the hull while it has no way on. Engine faults also count
        # as unavailable propulsion even if the ignition flag or tank still has fuel.
        adrift = is_unpowered_adrift(
            speed_through_water=w.speed_through_water,
            engine_on=self._engine_on,
            engine_ok=self.engine_ok,
            engine_power=self.engine_power,
            fuel=self.fuel,
            anchor_deployed=self.anchor_deployed,
            docked=self.docked(),
            tow_in_transit=self.tow_transit_active,
            speed_threshold=TOW_ADRIFT_SPEED,
        )
        if adrift:
            self.adrift_elapsed += max(0.0, float(dt))
        else:
            self.adrift_elapsed = 0.0
        fuel_trigger = self.fuel <= FUEL_CAP * TOW_TRIGGER_FUEL_FRACTION
        drift_trigger = self.adrift_elapsed >= TOW_TRIGGER_DRIFT_SECONDS
        if (not self.docked() and not self.tow_transit_active
                and (fuel_trigger or drift_trigger) and not self.tow_request_active):
            self.tow_request_active = True
            self.tow_retry_elapsed = 0.0
            self.tow_failed_call_count = 0
            if fuel_trigger:
                self.crew.say("Fuel is critically low. Repeatedly calling for a tow; we will not jump to harbour.")
            else:
                self.crew.say("We have been adrift without power for six in-game hours. Repeatedly calling for a tow.")
        # Progressive foundering: combined engine/hold flooding and deck water can overwhelm
        # the hull. This is not an instant position jump; abandon-ship uses the existing
        # swimming, man-overboard and rescue states.
        foundering = ((self.ship.engine_flood >= 0.97 and self.ship.hold_flood >= 0.90) or self.ship.flood >= 0.995
                      or FloodingModel.reserve_buoyancy(self.ship) <= FloodingModel.FOUNDER_RESERVE)
        if foundering and not self.abandon_ship_started:
            self.sinking_elapsed += dt
            if self.sinking_elapsed >= 18.0:
                self.abandon_ship_started = True
                self.world.brake = True
                self.world.throttle = 0.0
                self.crew.say("Captain: Abandon ship! Take to the emergency boat and stay together!")
                # Existing rescue-boat launch logic is used where available; sailors not
                # assigned to a boat enter the existing swimmer recovery system.
                launched = False
                for sailor in self.sailors:
                    if sailor.mode == Sailor.ABOARD and sailor.level != Level.BELOW:
                        if hasattr(self, "_begin_rescue_boat") and not launched:
                            try:
                                self._begin_rescue_boat(sailor)
                                launched = True
                                continue
                            except Exception:
                                pass
                        sailor.mode, sailor.task = Sailor.SWIMMING, "swim"
                        sailor.has_target = False
                        sailor.vel = V(0, 0)
                        sailor.breath = min(sailor.breath, 0.65)
        else:
            self.sinking_elapsed = max(0.0, self.sinking_elapsed - 0.2 * dt) if not self.abandon_ship_started else self.sinking_elapsed
        if self._engine_on:
            self.fuel = max(0.0, self.fuel - (0.12 + 4.5 * (w.speed / w.max_speed) ** 2 * (1.0 + 0.5 * w.waves.strength)) * dt)
        if self.fuel <= 0:
            if self.fuel_warn < 2:
                self.fuel_warn = 2
                self.crew.say("The tank is dry! The engine has stopped. The tow request stays on the radio; no position jump will occur.")
            if not self.docked() and not self.tow_transit_active:
                self.tow_t += dt
            else:
                self.tow_t = 0.0
        else:
            self.tow_t = 0.0
            if self.fuel < 120 and self.fuel_warn < 1:
                self.fuel_warn = 1
                self.crew.say("Fuel is low. Think about the quay; an automatic tow request starts at 5% tank capacity.")
        for k in self.bait_fresh:               # bait goes off, faster once the ice is gone
            self.bait_fresh[k] = max(0.0, self.bait_fresh[k] - (0.0004 + (0.0010 if self.ice <= 0 else 0.0)) * dt)

    def start_muster(self):
        """Call a headcount and have eligible crew physically report to a deck muster point."""
        if self.muster_active:
            self.crew.say("Captain: The muster is already under way.")
            return False
        self.muster_active = True
        self.muster_elapsed = 0.0
        self.muster_expected = set()
        self.muster_reports = set()
        self.muster_unavailable = {}
        assembly = self.ship.markers["rest_spot"]
        slot = 0
        for sailor in self.sailors:
            reason = None
            if sailor.mode == Sailor.SHORE:
                reason = "ashore"
            elif sailor.mode == Sailor.DEAD:
                reason = "dead"
            elif sailor.mode == Sailor.SWIMMING:
                reason = "overboard / in the water"
            elif sailor.mode == Sailor.RESCUE_BOAT:
                reason = "on rescue boat"
            elif sailor.mode == Sailor.CLIMBING or sailor.ladder is not None:
                reason = "on a ladder"
            elif sailor.health < 0.25:
                reason = "too badly injured"
            elif sailor.task == "rest" and sailor.fatigue >= 0.92:
                reason = "exhausted / resting"
            # Muster is a ship-wide order: even the captain and station keepers
            # leave their posts. Safety-critical rescue work remains represented
            # as unavailable only when the sailor is actually overboard/injured.
            if reason is not None:
                self.muster_unavailable[sailor.name] = reason
                continue
            if sailor.mode != Sailor.ABOARD:
                self.muster_unavailable[sailor.name] = "not aboard"
                continue
            self.muster_expected.add(sailor)
            # Grid slots avoid a single crowding target while keeping everyone near one deck station.
            offset = V((slot % 3 - 1) * 58.0, (slot // 3 - 0.5) * 46.0)
            sailor.muster_target = assembly + offset
            slot += 1
            sailor._enter("muster")
            sailor.think_t = 999.0             # the muster order holds until arrival/completion
        self.crew.say("Captain: HEADCOUNT! All available hands to the main-deck muster point. Report in!")
        if not self.muster_expected:
            self._finish_muster()
        return True

    def _muster_arrive(self, sailor):
        if self.muster_active and sailor in self.muster_expected and sailor not in self.muster_reports:
            self.muster_reports.add(sailor)
            self.crew.say("%s reports for headcount." % sailor.name)

    def _update_muster(self, dt):
        if not self.muster_active:
            return
        self.muster_elapsed += dt
        # Crew who become unavailable during the walk are counted by reason, not as silently present.
        for sailor in list(self.muster_expected):
            if sailor.mode != Sailor.ABOARD:
                self.muster_unavailable[sailor.name] = ("overboard / in the water" if sailor.mode == Sailor.SWIMMING
                                                        else "dead" if sailor.mode == Sailor.DEAD else "no longer aboard")
                self.muster_expected.discard(sailor)
                self.muster_reports.discard(sailor)
            elif sailor.health < 0.25 and sailor not in self.muster_reports:
                self.muster_unavailable[sailor.name] = "too badly injured"
                self.muster_expected.discard(sailor)
        if not (self.muster_expected - self.muster_reports):
            self._finish_muster()
        elif self.muster_elapsed >= 60.0:
            for sailor in self.muster_expected - self.muster_reports:
                self.muster_unavailable[sailor.name] = "unable to reach muster point"
            self._finish_muster()

    def _finish_muster(self):
        if not self.muster_active:
            return
        reports = len(self.muster_reports)
        groups = {}
        for name, reason in self.muster_unavailable.items():
            groups.setdefault(reason, []).append(name)
        parts = []
        priority = ("ashore", "on helm watch", "on radio watch", "on engine watch",
                    "responding to man overboard", "too badly injured", "exhausted / resting",
                    "on a ladder", "overboard / in the water", "dead", "unable to reach muster point", "not aboard", "no longer aboard")
        for reason in priority:
            names = groups.get(reason, [])
            if names:
                parts.append("%s: %s" % (reason, ", ".join(names)))
        for reason, names in groups.items():
            if reason not in priority and names:
                parts.append("%s: %s" % (reason, ", ".join(names)))
        detail = "; ".join(parts) if parts else "everyone available reported"
        self.crew.say("Headcount complete: %d reported in, %d accounted separately (%s)." %
                      (reports, len(self.muster_unavailable), detail))
        for name, status in self.crew.status.items():
            if status not in ("aboard", "shore"):
                self.crew._mark(name, True)
        for sailor in self.sailors:
            sailor.muster_target = None
            if sailor.task == "muster":
                sailor._enter("idle")
                sailor.think_t = 0.0
        self.muster_active = False
        self.muster_elapsed = 0.0

    def toggle_anchor(self):
        """Drop or weigh anchor. Deploying cancels travel orders and arrests drift."""
        if self.tow_transit_active:
            self.crew.say("Captain: We are under tow; the anchor cannot be worked until the tug releases us.")
            return False
        self.anchor_deployed = not self.anchor_deployed
        if self.anchor_deployed:
            w = self.world
            w.destination = None
            w.route_waypoints.clear()
            w.route_origin = None
            w.route_arrival_hold = False
            w.ocean_quick_target = None
            w.cancel_dock()
            w.throttle = 0.0
            w.speed = min(w.speed, 8.0)
            w.manual_helm = False
            w.brake = True
            self.crew.say("Captain: Let go the anchor. Cancel the course and hold position.")
            self.radio_message = "ANCHOR DOWN — DRIFT REDUCED"
        else:
            self.world.brake = False
            self.crew.say("Captain: Weigh anchor. Ready to manoeuvre.")
            self.radio_message = "ANCHOR UP"
        self.radio_message_t = 5.0
        return True

    def _tow_escort_log_and_broadcast(self, turns, source="tow_escort_checkin", priority=None):
        """Stage a tow exchange with its stable world entity ID in transcript metadata."""
        if priority is None:
            priority = PRIORITY_MEDIUM
        if not turns:
            return False
        escort = getattr(self, "tow_escort", None)
        if escort is not None and escort.vessel_id:
            source = "%s:%s" % (source, escort.vessel_id)
        return self.queue_broadcast_conversation(turns, priority=priority, channel="radio", source=source)

    def tow_escort_talk(self, topic=None, *, via_radio_ui=False):
        """Ask the persistent Coast Guard captain a question over the wireless."""
        escort = self.tow_escort
        if escort is None or escort.state not in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW", "ARRIVED"):
            self.crew.say("Radio: No Coast Guard escort is currently on our frequency.")
            return False
        topics = ("position", "eta", "weather", "traffic", "fishing", "fuel", "crew", "name", "fee", "stay")
        if topic is None:
            topic = topics[escort.question_index % len(topics)]
            escort.question_index += 1
        elif topic not in topics:
            topic = "position"
        w = self.world
        player_pos = (float(w.believed_pos.x / w.scale), float(w.believed_pos.y / w.scale))
        harbor_pos = (float(w.berth.x / w.scale), float(w.berth.y / w.scale))
        tow_report = format_chart_position(escort.reported_position, origin=harbor_pos)
        player_report = format_chart_position(player_pos, origin=harbor_pos)
        distance = math.dist(player_pos, harbor_pos)
        eta_hours = distance / max(1.0, 85.0 * 25.0)
        questions = {
            "position": ("Request position check.", "Our last plot puts us at %s. We have you at %s. Your fix may be the better one; report any discrepancy. Over." % (tow_report, player_report)),
            "eta": ("What's your estimate to harbour?", "At this speed, about %.1f in-game hours if the weather holds. I'll revise that if the sea turns. Over." % eta_hours),
            "weather": ("What's the weather ahead?", ("North-east is dark and the sea is building. We'll ease her back if the line starts to snatch." if self.world.sea_state > 0.65 else "Visibility is fair from here. There's a little weather to the north-east, but nothing severe yet.")),
            "traffic": ("What have you heard on the wireless?", "Mostly routine traffic and one vessel reporting poor visibility east of the line. Nothing that should affect our course at present. Over."),
            "fishing": ("Any fish where you've been working?", "We're Coast Guard, not fishing that ground. I can tell you the sea state; the grounds are your business. Over."),
            "fuel": ("How is your fuel holding?", "Fuel state is good enough for this escort. The engineer is monitoring consumption and I'll call it if that changes. Over."),
            "crew": ("How's your crew doing?", "All four hands accounted for. Nakamura has the wireless, Fujita is in the engine room, and Arai and Kobayashi are tending the line. Over."),
            "name": ("Who am I speaking to?", "%s, master of %s, Coast Guard launch. We're bringing you home. Over." % (escort.captain_name, escort.callsign)),
            "fee": ("What's the charge for the tow?", "The harbour handling fee is already on your account. Keep your attention on the line and we'll settle the paperwork alongside. Over."),
            "stay": ("Will you stay with us all the way in?", "We'll stay with you to the berth. If conditions force us to break off, I'll tell you before we cast off. Over."),
        }
        question, answer = questions[topic]
        if escort.personality == "chatty" and topic in ("weather", "crew", "traffic"):
            answer = answer.replace(" Over.", " The hands are steady, and we'll keep listening. Over.")
        elif escort.personality == "terse":
            answer = answer.split(" Over.")[0] + ". Over."
        tx_text = "%s, %s. This is Kōei Maru. %s Over." % (escort.callsign, escort.callsign, question)
        rx_text = "%s, %s. %s" % ("Fishing vessel", escort.callsign, answer)
        self.record_log_entry("Radio: Tow escort hail to %s (%s)." % (escort.callsign, topic))
        if via_radio_ui:
            history = self.radio_ui_histories.setdefault(escort.vessel_id, {"lines": [], "visible_count": 0})
            if history["visible_count"] < self.radio_ui_active_end.get(escort.vessel_id, len(history["lines"])):
                self.radio_ui_status = "ADVANCE THE CURRENT EXCHANGE BEFORE STARTING ANOTHER."
                return False
            lines = history["lines"]
            lines.append({"speaker": "KŌEI MARU · TX", "text": tx_text, "kind": "TX"})
            lines.append({"speaker": escort.callsign, "text": rx_text, "kind": "RX"})
            self.radio_ui_active_end[escort.vessel_id] = len(lines)
            history["visible_count"] = len(lines) - 1  # show our transmission, stage the reply
            self.record_log_entry("Radio: [VESSEL]: %s" % tx_text)
            self.radio_ui_status = "%s answered — advance the transcript line by line." % escort.callsign
            if len(lines) > 100:
                trim = len(lines) - 100
                del lines[:trim]
                history["visible_count"] = max(0, history["visible_count"] - trim)
                self.radio_ui_active_end[escort.vessel_id] = max(history["visible_count"], self.radio_ui_active_end[escort.vessel_id] - trim)
            return True
        turns = [
            (0.0, "VESSEL", tx_text, "radio"),
            (2.2, escort.callsign, rx_text, "radio"),
        ]
        return self._tow_escort_log_and_broadcast(turns, source="tow_escort_player_hail")

    def _sync_tow_escort_world_entity(self):
        """Expose the active tow launch through the shared AIShip/contact identity."""
        world = getattr(self, "traffic_world", None)
        if world is None:
            return
        escort = getattr(self, "tow_escort", None)
        previous_id = getattr(self, "_tow_escort_synced_id", None)
        if escort is None:
            if previous_id:
                world.unregister_runtime_ship(previous_id)
            self._tow_escort_synced_id = None
            return

        vessel_id = escort.vessel_id or ("coast_guard_launch:" + escort.callsign.lower().replace(" ", "_"))
        escort.vessel_id = vessel_id
        if previous_id and previous_id != vessel_id:
            world.unregister_runtime_ship(previous_id)
        # TowEscort uses chart design units (y increases down); traffic uses nautical
        # miles (y increases north). Keep that conversion in one adapter only.
        true_nm = self._legacy_nm_to_active_nm(escort.world_position_nm)
        report_nm = self._legacy_nm_to_active_nm(escort.world_reported_position_nm)
        report_age_s = max(0.0, float(escort.elapsed) - float(escort.last_report_elapsed))
        report_time = float(self.world.time) - report_age_s
        heading_nm = escort.world_heading_rad
        activity = TrafficActivity.RETURNING if escort.state == "ARRIVED" else TrafficActivity.TRANSIT
        ship = world.by_id(vessel_id)
        if ship is None:
            ship = AIShip(
                id=vessel_id, name=escort.callsign, callsign=escort.callsign,
                archetype=TrafficArchetype.COAST_GUARD, home_port="Hakodate Coast Guard",
                personality="official", schedule=(), period_s=0.0, speed_kn=0.0,
                radio_fit="SSB", radio_range_nm=49.0,
                trust=0.0, position_nm=true_nm, heading_rad=heading_nm,
                activity=activity, lod="active", known_to_player=True,
                last_reported_position_nm=report_nm,
                last_reported_heading_rad=heading_nm, last_report_time_s=report_time,
                runtime_kind="tow_escort")
            world.register_runtime_ship(ship)
        else:
            world.sync_runtime_ship(vessel_id, position_nm=true_nm, heading_rad=heading_nm,
                                    activity=activity, reported_position_nm=report_nm,
                                    reported_heading_rad=heading_nm, report_time_s=report_time,
                                    known_to_player=True)
            ship.runtime_kind = "tow_escort"
            ship.name = escort.callsign
            ship.callsign = escort.callsign
            ship.personality = "official"
            ship.radio_fit = "SSB"
            ship.radio_range_nm = 49.0
        self._tow_escort_synced_id = vessel_id

    def _update_tow_escort(self, dt):
        """Maintain Coast Guard position reports and regular two-way radio contact."""
        escort = self.tow_escort
        if escort is None:
            self.tow_escort_status_t = max(0.0, self.tow_escort_status_t - max(0.0, dt))
            return
        dt = max(0.0, float(dt))
        if escort.state == "EN_ROUTE" and self.docked() and not self.tow_transit_active:
            self.record_log_entry("Radio: We reached harbour under our own power; Coast Guard launch %s has been stood down." % escort.callsign)
            self.tow_escort = None
            self.tow_escort_status_message = "COAST GUARD LAUNCH STOOD DOWN"
            self.tow_escort_status_t = 8.0
            return
        escort.elapsed += dt
        self.tow_escort_status_t = max(0.0, self.tow_escort_status_t - dt)
        w = self.world
        scale = max(0.001, float(w.scale))
        ship_chart = (float(w.ship_pos.x / scale), float(w.ship_pos.y / scale))
        harbor_chart = (float(w.berth.x / scale), float(w.berth.y / scale))
        if escort.state == "EN_ROUTE":
            # PLACE HOLDER SHIP movement: advance the same visible hull used by
            # draw_tow_escort() from the harbour toward an intercept point just
            # ahead of our ship. The reported chart position remains radio-based.
            escort.enroute_elapsed += dt
            progress = clamp(escort.enroute_elapsed / max(0.1, escort.enroute_duration), 0.0, 1.0)
            dx, dy = ship_chart[0] - harbor_chart[0], ship_chart[1] - harbor_chart[1]
            intercept = tow_intercept_position(harbor_chart, ship_chart)
            escort.true_position = lerp_chart_position(harbor_chart, intercept, progress)
            escort.heading = math.atan2(intercept[1] - harbor_chart[1], intercept[0] - harbor_chart[0])
            if progress >= 1.0:
                # The launch has physically reached its intercept point; hold there,
                # report the approach complete, and take a few seconds to turn.
                escort.true_position = intercept
                escort.handover_elapsed = 0.0
                escort.heading = math.atan2(ship_chart[1] - harbor_chart[1], ship_chart[0] - harbor_chart[0])
                escort.refresh_report(escort.true_position)
                escort.state = "ALONGSIDE"
                self.tow_arrival_t = 0.0
                self.tow_escort_status_message = "%s ALONGSIDE — MAKING THE TOW FAST" % escort.callsign
                self.tow_escort_status_t = 8.0
                self.record_log_entry("Radio: Coast Guard launch %s reached our position from the harbour and is making the tow fast." % escort.callsign)
                self._tow_escort_log_and_broadcast([
                    (0.0, escort.callsign, "Fishing vessel, this is %s. We're alongside. Stand by while my hands pass the line and we turn her for the harbour. Over." % escort.callsign, "radio"),
                    (2.0, "VESSEL", "%s, received. We'll keep clear and stand by. Over." % escort.callsign, "radio"),
                ], source="tow_escort_handover", priority=PRIORITY_HIGH)
                self.crew.say("Coast Guard launch has arrived from the harbour and is coming alongside to make fast the towline.")
                return
        elif escort.state == "ALONGSIDE":
            # Keep the launch beside its intercept point while it turns around.
            dx, dy = harbor_chart[0] - ship_chart[0], harbor_chart[1] - ship_chart[1]
            distance = math.hypot(dx, dy)
            if distance > 1e-6:
                separation = min(TOW_ESCORT_SEPARATION_NM * 185.2, distance * 0.82)
                escort.true_position = (ship_chart[0] + dx / distance * separation,
                                        ship_chart[1] + dy / distance * separation)
                target_heading = math.atan2(dy, dx)
                delta = (target_heading - escort.heading + math.pi) % math.tau - math.pi
                escort.heading += clamp(delta, -1.15 * dt, 1.15 * dt)
            escort.handover_elapsed += dt
            if escort.handover_elapsed >= TOW_ESCORT_HANDOVER_SECONDS:
                if distance > 1e-6:
                    escort.heading = math.atan2(harbor_chart[1] - ship_chart[1], harbor_chart[0] - ship_chart[0])
                self.tow_in()
                return
        elif escort.state == "UNDER_TOW":
            dx, dy = harbor_chart[0] - ship_chart[0], harbor_chart[1] - ship_chart[1]
            distance = math.hypot(dx, dy)
            if distance > 1e-6:
                escort.heading = math.atan2(dy, dx)
                # Chart coordinates: the launch leads from the front and moves
                # with the fishing vessel, keeping a visible, consistent towline.
                separation = min(TOW_ESCORT_SEPARATION_NM * 185.2, distance)
                escort.true_position = (ship_chart[0] + dx / distance * separation,
                                        ship_chart[1] + dy / distance * separation)
            else:
                escort.true_position = harbor_chart
            escort.fuel = max(0.0, escort.fuel - dt / 1800.0)
            # The same physical storm state marks the line as strained on the chart.
            risk = float(w.sea_state) >= LINE_RISK_SEA_STATE
            if risk and not escort.warned_line_risk:
                self._tow_escort_log_and_broadcast([
                    (0.0, escort.callsign, "%s, %s. Sea state is rising; the towline is taking a strain. I'm reducing speed and watching the fairlead. Over." % ("Fishing vessel", escort.callsign), "radio")
                ], source="tow_escort_line_warning", priority=PRIORITY_HIGH)
                self.tow_escort_status_message = "TOWLINE UNDER STRAIN — COAST GUARD REDUCING SPEED"
                self.tow_escort_status_t = 10.0
                escort.warned_line_risk = True
            elif not risk and escort.warned_line_risk:
                self._tow_escort_log_and_broadcast([
                    (0.0, escort.callsign, "Sea state has eased. Line strain is back within limits; resuming the planned tow speed. Over.", "radio")
                ], source="tow_escort_line_safe")
                escort.warned_line_risk = False
            escort.line_at_risk = risk
        elif escort.state == "ARRIVED":
            escort.depart_elapsed += dt
            if escort.depart_elapsed >= DEPART_DELAY:
                self.record_log_entry("Radio: Coast Guard launch %s signed off after the tow." % escort.callsign)
                self.tow_escort = None
                self.tow_escort_status_message = ""
                self.tow_escort_status_t = 0.0
                return
        else:
            return

        escort.unscheduled_elapsed += dt
        if (escort.state == "UNDER_TOW" and escort.unscheduled_elapsed >= escort.unscheduled_next
                and not self.radio_calls and not self.radio_transcript_queue
                and self.radio_bubble_t <= 0.25 and not self.broadcast_director.is_busy()):
            escort.unscheduled_elapsed = 0.0
            escort.unscheduled_next = random.uniform(55.0, 105.0)
            lines = {
                "professional": ("Weather remains manageable. Keep your hands clear of the bight and report any flooding. Over.",
                                 "The watch is steady here. We will keep you informed if anything changes. Over."),
                "terse": ("Line holding. Keep clear of the bight. Over.",
                          "No change on our end. Stay ready to report trouble. Over."),
                "chatty": ("Kobayashi says the swell always feels longer on the way home. He's been on this coast fifteen years. Over.",
                           "We passed a small light to the east earlier. Could have been another catcher-boat, but no call sign. Over."),
                "worried": ("Tell me plainly if you're taking water. I don't want to discover it from a change in the towline. Over.",
                            "Your crew should keep warm and stay low. The next swell looks uneven. Over."),
            }.get(escort.personality, ("Line holding. Over.", "No change. Over."))
            line = random.choice(lines)
            self._tow_escort_log_and_broadcast([
                (0.0, escort.callsign, "%s, %s. %s" % ("Fishing vessel", escort.callsign, line), "radio")
            ], source="tow_escort_unscheduled")

        escort.since_checkin += dt
        if escort.since_checkin >= CHECKIN_INTERVAL and escort.state in ("EN_ROUTE", "UNDER_TOW"):
            escort.since_checkin %= CHECKIN_INTERVAL
            op = self.radio_operator
            receiver_ready = self.radio_station_ok()
            signal_quality = clamp(float(getattr(self.radio, "signal_quality", 0.5)), 0.0, 1.0)
            hearing_chance = clamp(0.65 + 0.30 * signal_quality + 0.10 * (float(op.skill) if op else 0.0), 0.20, 0.98)
            if not receiver_ready or random.random() > hearing_chance:
                escort.missed_checkins += 1
                if escort.missed_checkins >= 2 and receiver_ready and op is not None and op.skill >= 0.55:
                    self.crew.say('Radio Op %s: "%s has been off the air. Should we try to raise them?"' % (op.name, escort.callsign))
                    self.record_log_entry("Tow escort: two scheduled Coast Guard check-ins missed; radio operator recommends raising them.")
                return
            escort.refresh_report(escort.true_position)
            tow_report = format_chart_position(escort.reported_position, origin=harbor_chart)
            player_report = format_chart_position((float(w.believed_pos.x / scale), float(w.believed_pos.y / scale)), origin=harbor_chart)
            remaining_nm = math.dist(ship_chart, harbor_chart) / 185.2
            eta_hours = remaining_nm / 11.5
            personality_line = {
                "professional": "Line is holding. Report any change in your vessel's condition. Over.",
                "terse": "Line holding. Report trouble immediately. Over.",
                "chatty": "We're making fair progress. How are the hands aboard? Keep them warm and clear of the line. Over.",
                "worried": "The sea has a nasty look to it. Are you all secure aboard? We're staying with you. Over.",
            }.get(escort.personality, "Line holding. Over.")
            turns = [
                (0.0, escort.callsign, "%s, %s. Position report: our plot %s. We have you at %s. Estimated time to harbour %.1f hours. Over." % ("Fishing vessel", escort.callsign, tow_report, player_report, eta_hours), "radio"),
                (2.3, "VESSEL", "%s, received. Towline holding; we'll report if the situation changes. Over." % escort.callsign, "radio"),
                (4.2, escort.callsign, personality_line, "radio"),
            ]
            self._tow_escort_log_and_broadcast(turns, source="tow_escort_checkin")
            self.tow_escort_status_message = "COAST GUARD CHECK-IN RECEIVED — %s" % escort.callsign
            self.tow_escort_status_t = 5.0

    def tow_in(self):
        """Begin towing only after the Coast Guard has visibly reached the vessel."""
        if self.tow_transit_active or self.docked():
            return False
        w, ln = self.world, self.line
        if self.tow_escort is None:
            # Direct callers still get a proper harbour departure, not a tug spawned
            # beside the fishing vessel. The normal radio path creates this earlier.
            scale = max(0.001, float(w.scale))
            harbor_chart = (float(w.berth.x / scale), float(w.berth.y / scale))
            distance = w.ship_pos.distance_to(w.berth) / scale
            duration = 8.0 + min(24.0, distance / 300.0)
            self.tow_escort = TowEscort.coast_guard(harbor_chart, enroute_duration=duration)
            self.tow_escort_status_message = "COAST GUARD LAUNCH EN ROUTE FROM HARBOUR"
            self.tow_escort_status_t = 8.0
            self.tow_arrival_t = duration
            return False
        if self.tow_escort.state == "EN_ROUTE":
            return False
        if self.tow_escort.state not in ("ALONGSIDE", "UNDER_TOW"):
            return False
        self.cash -= TOW_FEE
        if ln.phase != Longline.IDLE:
            ln.pts, ln.phase, ln.fight, ln.gaff = [], Longline.IDLE, None, None
            self.crew.say("The coast guard cuts the longline clear to make the tow safe.")
        ln.auto, ln.stage, ln.dock_started = False, "off", False
        self.anchor_deployed = False
        w.brake = False
        w.throttle = 0.0
        w.speed = 0.0
        w.destination = None
        w.route_waypoints.clear()
        w.route_origin = None
        w.ocean_quick_target = None
        w.route_arrival_hold = False
        w.cancel_dock()
        self.tow_transit_active = True
        self.tow_transit_elapsed = 0.0
        self.tow_transit_target = V(w.berth)
        # The launch has already travelled from the berth to the intercept point.
        # Preserve its physical position; only turn its heading for the homeward leg.
        self.tow_escort.state = "UNDER_TOW"
        self.tow_escort.since_checkin = 0.0
        self.tow_arrival_t = 0.0
        ship_chart = (float(w.ship_pos.x / w.scale), float(w.ship_pos.y / w.scale))
        harbor_chart = (float(w.berth.x / w.scale), float(w.berth.y / w.scale))
        dx, dy = harbor_chart[0] - ship_chart[0], harbor_chart[1] - ship_chart[1]
        distance = math.hypot(dx, dy)
        if distance > 1e-6:
            self.tow_escort.heading = math.atan2(dy, dx)
        self.tow_escort_status_message = "%s HAS THE TOWLINE FAST" % self.tow_escort.callsign
        self.tow_escort_status_t = 8.0
        self.tow_transit_distance_start = w.ship_pos.distance_to(self.tow_transit_target)
        self.arrival_done = False
        self.crew.say("Coast Guard has the towline fast. We are being towed toward the berth; hold position and stand by.")
        self.radio_message = "TOW UNDER WAY — RETURNING TO BERTH"
        self.radio_message_t = 8.0
        return True

    def _update_tow_transit(self, dt):
        """Advance the vessel at a controlled tow speed; position changes continuously."""
        if not self.tow_transit_active or self.tow_transit_target is None:
            return
        w = self.world
        to = self.tow_transit_target - w.ship_pos
        remaining = to.length()
        self.tow_transit_elapsed += max(0.0, dt)
        if remaining <= 18.0:
            w.ship_pos = V(self.tow_transit_target)
            w.speed = w.throttle = 0.0
            w.destination = None
            w.dock_state = None
            w.cancel_dock()
            w.zone = 0
            w.reset_position_fix("TOW ARRIVAL")
            self.fuel = min(FUEL_CAP, max(30.0, self.fuel))
            self.fuel_warn = 0
            self.tow_t = 0.0
            self.tow_transit_active = False
            self.tow_transit_target = None
            self.tow_retry_elapsed = 0.0
            self.tow_request_active = False
            self.tow_failed_call_count = 0
            self.adrift_elapsed = 0.0
            self.arrival_done = True
            if self.tow_escort is not None:
                self.tow_escort.state = "ARRIVED"
                self.tow_escort.depart_elapsed = 0.0
                escort_pos = (float(w.berth.x / w.scale) + 0.8,
                              float(w.berth.y / w.scale) - 0.8)
                self.tow_escort.true_position = escort_pos
                self.tow_escort.refresh_report(escort_pos, initial=True)
                self.queue_broadcast_conversation([
                    (0.0, self.tow_escort.callsign, "We've got you alongside, vessel. Towline is coming off now. Let the harbour hands take you from here. Over.", "radio"),
                    (3.0, "VESSEL", "%s, received. Thanks to you and your crew. Out." % self.tow_escort.callsign, "radio"),
                ], priority=PRIORITY_MEDIUM, source="tow_escort_arrival")
                self.tow_escort_status_message = "COAST GUARD ALONGSIDE — CASTING OFF"
                self.tow_escort_status_t = 8.0
            self.crew.say("The tow is alongside the berth. Emergency fuel supplied; the vessel is safe to dock and refuel.")
            self.radio_message = "TOW COMPLETE — BERTH REACHED"
            self.radio_message_t = 8.0
            return
        direction = to / max(remaining, 1e-6)
        escort = getattr(self, "tow_escort", None)
        tow_speed = 48.0 if escort is not None and escort.line_at_risk else 85.0
        step = min(remaining, tow_speed * max(0.0, dt))
        w.ship_pos += direction * step
        w.believed_pos += direction * step
        w.heading = math.atan2(direction.y, direction.x) % TAU
        w.believed_heading = w.heading
        w.speed = tow_speed
        w.throttle = 0.0
        w.destination = None
        w.dock_state = None
        w.zone = 0 if w.dist() < 900 else (1 if w.dist() < 5000 else 2)

    def _sea_hazards(self, dt):
        """A heeling deck slides loose fish about, and a heavy roll can sweep an unclipped man off the open stern or the hauler rail."""
        ship = self.ship
        tilt = self.eff_tilt()
        if tilt > 0.18:
            for it in self.items:
                it.pos += ship.slope * ((tilt - 0.18) * 320.0 * dt)
        if self.harness or tilt < 0.36:
            return
        for sl in self.sailors:
            if sl.mode != Sailor.ABOARD or sl.level != Level.MAIN:
                continue
            best, bd = None, 1e9
            for a, b in ship.open_edges:
                c = closest_on_seg(sl.pos, a, b)
                d = sl.pos.distance_to(c)
                if d < bd:
                    best, bd = c, d
            if best is None or bd > 70:
                continue
            p = 0.10 * (tilt - 0.36) + 0.03 * clamp(ship.wash_push(sl.pos).length(), 0.0, 1.0)
            if random.random() < p * dt:
                out = best.normalize() if best.length() > 1e-6 else V(0, 1)
                sl.pos = V(best) + out * 40
                sl.vel = out * 120
                self.crew.say("A sea sweeps %s over the rail!" % sl.name)

    def find_loose_fish(self, s):
        best, best_d = None, 1e18
        for it in self.items:
            if it.free_for(s):
                d = s.pos.distance_to(it.pos)
                if d < best_d:
                    best, best_d = it, d
        return best

    def _update_deck_fish(self, dt):
        """Advance deck catch deterioration and the physical thrash/slime hazard for live, unsecured fish."""
        for item in list(self.items):
            item.thrash_anim = max(0.0, item.thrash_anim - dt * 1.8)
            if not item.fish.alive:
                continue
            item.thrash_timer -= dt
            if item.thrash_timer > 0.0:
                continue
            item.thrash_timer = random.uniform(5.5, 9.0)
            item.thrash_count += 1
            item.thrash_anim = 1.0
            fish = item.fish
            self.crew.say("The live %s thrashes on deck!" % fish.name)

            # Reinforce an existing slime patch rather than adding a second hazard system.
            patch = next((p for p in self.patches
                          if p.kind == "slime" and p.pos.distance_to(item.pos) < p.radius + 35.0), None)
            if patch is None:
                self.patches.append(Patch(item.pos, "slime", radius=55.0))
            else:
                patch.radius = min(120.0, patch.radius + 6.0)
                patch.life = min(360.0, patch.life + 25.0)
                patch.age = max(0.0, patch.age - 8.0)
                patch.grip = min(patch.grip, 0.12)

            nearby = []
            for sailor in self.sailors:
                if (sailor.mode != Sailor.ABOARD or sailor.level != Level.MAIN
                        or sailor.ladder is not None):
                    continue
                distance = sailor.pos.distance_to(item.pos)
                if distance < 112.0:
                    nearby.append((distance, sailor))
            nearby.sort(key=lambda pair: pair[0])
            damaged = 0.0
            damage_budget = 0.025  # cap total bruising from one thrash event, even if two sailors are close
            for distance, sailor in nearby[:2]:
                severity = clamp((112.0 - distance) / 112.0, 0.0, 1.0)
                direction = sailor.pos - item.pos
                if direction.length() < 1e-5:
                    direction = V(1, 0).rotate_rad(random.uniform(0.0, TAU))
                else:
                    direction = direction.normalize()
                sailor.vel += direction * (55.0 + 100.0 * severity)
                # A shove delays optional work; safety-critical station and rescue tasks retain control.
                if sailor.task in ("clean", "social", "rest", "idle", "order"):
                    sailor._enter("idle")
                    sailor.think_t = min(sailor.think_t, 0.1)
                handling_hit = fish.damage_from_handling(min(damage_budget, 0.004 + 0.010 * severity))
                damage_budget = max(0.0, damage_budget - handling_hit)
                damaged += handling_hit
                if sailor.hit_cd <= 0.0:
                    sailor.hurt(0.008 + 0.025 * severity, "struck by a thrashing %s" % fish.name)
                    sailor.hit_cd = 1.0
                    if sailor.grip_mult < 0.5 or any(p.kind == "slime" and p.pos.distance_to(sailor.pos) < p.radius for p in self.patches):
                        self.crew.say("%s slips on fish slime and is shoved aside!" % sailor.name)
                    else:
                        self.crew.say("%s is shoved by the thrashing %s!" % (sailor.name, fish.name))
            if damaged > 0.0:
                self.crew.say("Rough handling bruises the %s; quality falls to %d%%." %
                              (fish.name, round(fish.quality * 100)))

    # --- blood: cutting splashes the table and the deck round it; wash it away or the crew scrub it
    def splash_blood(self, pos, n, spread=60.0):
        for _ in range(n):
            if len(self.splats) < 160:
                v = V(random.uniform(-1, 1), random.uniform(-1, 1)) * random.uniform(40, 140)
                self.splats.append([V(pos) + V(random.uniform(-8, 8), random.uniform(-8, 8)), v, 0.0, random.uniform(14, 28), random.uniform(2.0, 5.0)])

    def add_blood(self, pos, amount):
        for p in self.patches:
            if p.kind == "blood" and p.pos.distance_to(pos) < 45:    # more blood on a puddle that is already there
                p.radius = min(p.radius + 7 * amount, 80.0)
                p.age, p.cleaning = min(p.age, 20.0), max(p.cleaning - 0.2, 0.0)
                return
        if sum(1 for p in self.patches if p.kind == "blood") < 12:
            self.patches.append(Patch(pos, "blood", random.uniform(20, 32) * (0.7 + 0.5 * amount)))

    def cut_blood(self, stand, amount):
        self.table_blood = min(1.0, self.table_blood + 0.3 * amount)
        self.splash_blood(stand + V(random.uniform(-15, 15), 26), int(5 + 4 * amount))
        self.add_blood(stand + V(random.uniform(-40, 40), random.uniform(-4, 14)), amount)

    # --- autodock: sail to the berth, then the harbour does the rest (heal, auction, ice, wages)
    def begin_autodock(self):
        w, say = self.world, self.crew.say
        if w.ship_pos.distance_to(w.berth) < 90 and w.speed < 80:
            say("Captain: We're already alongside.")
            self.arrival_done = False
            return False
        w.start_dock()
        say("Captain: Autodock. Making for the quay.")
        return True

    TRIP_DAYS = 3

    def start_fishing_trip(self, days=None):
        """The captain's order to fish: stay out `days` game days, setting and hauling as often as time, fuel, bait and ice allow."""
        days = self.TRIP_DAYS if days is None else int(days)
        w, ln, say = self.world, self.line, self.crew.say
        if w.dock_state is not None:
            say("Captain: We're still coming alongside. Ask again once she's tied up.")
            return False
        if ln.phase != Longline.IDLE and not ln.auto:
            say("Captain: Finish with this line first.")
            return False
        if w.route_waypoints:                                   # fishing has priority over a plotted course
            w.route_waypoints.clear()
            w.destination = None
            self.record_log_entry("Manual chart route cancelled because the fishing trip took priority.")
        if self.docked():
            self._recall_shore_leave(departure=True)            # the shore party comes back aboard before we sail
        ln.trip_days, ln.trip_start = days, w.time
        ln.trip_end = w.time + days * DAY_LEN
        if not ln.auto:
            ln.auto = True
            if ln.phase == Longline.IDLE:
                ln.stage, ln.dock_started = "off", False
        say("Captain: Right, we fish. %d days out, then we come home. Crew, get to it." % days)
        self.record_log_entry("Captain's order: fishing trip of %d days." % days)
        return True

    def order_return_to_port(self):
        """The captain's order to stop fishing and take her home. A line that is still out is hauled first."""
        w, ln, say = self.world, self.line, self.crew.say
        if w.dock_state is not None:
            say("Captain: We're already making for the quay.")
            return False
        if w.ship_pos.distance_to(w.berth) < 90 and w.speed < 80:      # the same test begin_autodock uses for "alongside"
            say("Captain: We're already alongside.")
            return False
        if ln.phase != Longline.IDLE:
            if not ln.auto:
                say("Captain: The line is still out. Haul it first.")
                return False
            if ln.trip_end is None:
                ln.trip_days, ln.trip_start = 1, w.time
            ln.trip_end = w.time                                # the clock has run out: after this haul, home
            say("Captain: The line's still out. We haul it in, then head for port.")
            self.record_log_entry("Captain's order: return to port after hauling the line.")
            return True
        w.route_waypoints.clear()
        ln.auto, ln.stage, ln.dock_started, ln.trip_end = False, "off", False, None
        w.destination = None
        self.record_log_entry("Captain's order: return to port.")
        return self.begin_autodock()

    def toggle_autodock(self):
        w, say, ln = self.world, self.crew.say, self.line
        if w.dock_state is not None:
            w.cancel_dock()
            say("Captain: Cancelling the approach.")
            return
        if ln.phase != Longline.IDLE:
            say("Captain: The line is still out. Haul it first.")
            return
        if ln.auto:                                 # the player takes over from the crew's own fishing
            ln.auto, ln.stage, ln.dock_started = False, "off", False
        self.begin_autodock()

    # --- selection / input
    def selected(self):
        return next((s for s in self.sailors if s.selected), None)

    def _show_context_menu(self, screen_point, title, options, target=None):
        """Open a compact in-world context menu; options are action dictionaries."""
        self.context_menu = {"pos": (int(screen_point[0]), int(screen_point[1])),
                             "title": str(title), "options": list(options),
                             "target": target, "rects": []}

    def _open_context_menu_at(self, screen_point, deck_pos):
        """Find an actual visible object under the pointer, not empty water/deck."""
        vl = self.view_level()
        mouse = V(screen_point)
        # Floating buoys and exposed sections of longline are world objects. Their
        # menu takes priority over an ocean steer-to order if the pointer hits one.
        if vl == Level.MAIN and self.line.pts:
            for i, point in enumerate(self.line.pts):
                if not (point.get("float") or i in (0, len(self.line.pts) - 1)):
                    continue
                local = self.world.deck_of(point["pos"])
                center = V(self.SS(local))
                if mouse.distance_to(center) <= max(16.0, 23.0 * self.zoom):
                    options = [{"label": "Inspect buoy / line", "action": "inspect_gear"}]
                    if self.line.phase == Longline.SOAKING:
                        options.append({"label": "Start hauling", "action": "haul_now"})
                    if self.line.roller_snag_timer > 0.0 or self.line.roller_jammed:
                        options.append({"label": "Clear stern-gear snag", "action": "clear_snag"})
                    options.append({"label": "Cancel", "action": "close"})
                    self._show_context_menu(screen_point, "FISHING GEAR", options,
                                            {"kind": "gear", "index": i})
                    return True

        # Workable hatch covers.
        hatch_sets = [("engine", self.ship.engine_hatch, "engine-room hatch")]
        hatch_sets += [("hold_%d" % (i + 1), r, "ice-hold hatch %d" % (i + 1))
                       for i, r in enumerate(self.ship.hatches)]
        if vl in (Level.MAIN, Level.BELOW):
            for key, rect, label in hatch_sets:
                x, y, ww, hh = rect
                center = V(self.SS(V(x + ww / 2, y + hh / 2)))
                if rect_has(rect, deck_pos) or mouse.distance_to(center) <= max(20.0, 27.0 * self.zoom):
                    opened = self.ship.hatch_is_open(key)
                    options = [{"label": "Dog hatch shut" if opened else "Open hatch",
                                "action": "hatch_order", "value": {"key": key, "open": not opened}},
                               {"label": "Cancel", "action": "close"}]
                    self._show_context_menu(screen_point, label.upper(), options,
                                            {"kind": "hatch", "key": key, "label": label})
                    return True


        # Crew context: selecting a sailor under the pointer is distinct from moving
        # the currently selected sailor to an empty deck position.
        for sailor in reversed(self.sailors):
            if sailor.mode in (Sailor.DEAD, Sailor.SHORE):
                continue
            if sailor.mode == Sailor.ABOARD and sailor.level != vl and not (vl == Level.WHEELHOUSE and sailor.level == Level.MAIN):
                continue
            center = V(self.SS(sailor.pos))
            if mouse.distance_to(center) <= max(19.0, 27.0 * self.zoom):
                options = [
                    {"label": "Select sailor", "action": "select_sailor"},
                    {"label": "Assign: haul line", "action": "set_duty", "value": "haul"},
                    {"label": "Assign: set longline", "action": "set_duty", "value": "set"},
                    {"label": "Assign: engine watch", "action": "set_duty", "value": "engine"},
                    {"label": "Assign: rest", "action": "set_duty", "value": "rest"},
                    {"label": "Cancel", "action": "close"},
                ]
                if sailor.role == Sailor.CAPTAIN:
                    # The captain's own orders replace the crew duties (he is not a deckhand): the ship's business.
                    status = self.line.trip_hud() or ("Fishing" if self.line.auto else "No trip")
                    options = [
                        {"label": "Select captain", "action": "select_sailor"},
                        {"label": "Fish: %d-day trip" % self.TRIP_DAYS, "action": "captain_fish"},
                        {"label": "Return to port", "action": "captain_port"},
                        {"label": "Assign: rest", "action": "set_duty", "value": "rest"},
                        {"label": "Cancel", "action": "close"},
                    ]
                    self._show_context_menu(screen_point, "%s  [%s]" % (sailor.name.upper(), status), options,
                                            {"kind": "sailor", "sailor": sailor})
                    return True
                self._show_context_menu(screen_point, sailor.name, options,
                                        {"kind": "sailor", "sailor": sailor})
                return True

        # Stern hauler and roller controls are accessible without memorising M.
        if vl == Level.MAIN:
            for key, rect, title in (("hauler", self.ship.hauler, "STARBOARD HAULER"),
                                     ("roller", self.ship.roller, "STERN ROLLER")):
                x, y, ww, hh = rect
                center = V(self.SS(V(x + ww / 2, y + hh / 2)))
                if rect_has(rect, deck_pos) or mouse.distance_to(center) <= max(22.0, 28.0 * self.zoom):
                    options = []
                    if key == "hauler":
                        options.append({"label": "Assign selected sailor to haul", "action": "set_selected_duty", "value": "haul"})
                    if self.line.roller_jammed or self.line.roller_snag_timer > 0.0:
                        options.append({"label": "Clear stern-gear snag", "action": "clear_snag"})
                    options.append({"label": "Engage / bypass roller", "action": "operate_roller"})
                    options.append({"label": "Cancel", "action": "close"})
                    self._show_context_menu(screen_point, title, options, {"kind": key})
                    return True

        # An empty patch of walkable deck gets an ordinary move/work menu too; this
        # keeps the right-click interaction consistent instead of silently switching
        # between menus and direct orders depending on what is under the pointer.
        walkable_click = (self.ship.on_deck(deck_pos) if vl == Level.MAIN else
                          (vl == Level.BELOW and self.ship.maps[Level.BELOW].point_safe(deck_pos)))
        if walkable_click:
            options = [
                {"label": "Move selected sailor here", "action": "move_here"},
                {"label": "Assign selected: haul line", "action": "set_selected_duty", "value": "haul"},
                {"label": "Assign selected: set longline", "action": "set_selected_duty", "value": "set"},
                {"label": "Assign selected: engine watch", "action": "set_selected_duty", "value": "engine"},
                {"label": "Cancel", "action": "close"},
            ]
            self._show_context_menu(screen_point, "DECK ORDER", options,
                                    {"kind": "deck", "pos": V(deck_pos), "level": vl})
            return True
        return False

    def _queue_hatch_context_order(self, sailor, key, should_open):
        """Route a suitable sailor to a hatch and have them physically work the cover."""
        def hatch_point(person):
            choices = [(label, V(pos)) for k, label, pos in self.ship.hatch_interaction_points(person.level)
                       if k == key]
            if not choices:
                return None
            return min(choices, key=lambda row: person.pos.distance_to(row[1]))[1]

        suitable = (sailor is not None and sailor.mode == Sailor.ABOARD
                    and sailor.level in (Level.MAIN, Level.BELOW) and sailor.ladder is None
                    and sailor.deck_action is None and sailor not in (self.helm_operator, self.radio_operator)
                    and hatch_point(sailor) is not None)
        if not suitable:
            candidates = [person for person in self.sailors
                          if person.mode == Sailor.ABOARD and person.level in (Level.MAIN, Level.BELOW)
                          and person.ladder is None and person.deck_action is None
                          and person not in (self.helm_operator, self.radio_operator)
                          and hatch_point(person) is not None]
            if candidates:
                sailor = min(candidates, key=lambda person: person.pos.distance_to(hatch_point(person)))
            else:
                self.crew.say("Captain: No available deckhand can reach that hatch right now.")
                return False

        pos = hatch_point(sailor)
        if pos is None:
            self.crew.say("That hatch is not reachable from this deck landing.")
            return False
        if sailor.pos.distance_to(pos) <= 56.0:
            if self.ship.hatch_is_open(key) == bool(should_open):
                self.crew.say("That hatch is already %s." % ("open" if should_open else "dogged shut"))
                return True
            return self._start_hatch_action(sailor, key, automatic=False)
        sailor.order_to(pos, sailor.level)
        sailor.hatch_order = {"key": key, "open": bool(should_open), "level": sailor.level, "pos": V(pos)}
        self.record_log_entry("Captain's order: %s ordered to %s the %s." %
                              (sailor.name, "open" if should_open else "dog shut", key.replace("_", " ")))
        return True

    def _queue_stern_snag_clear(self, sailor):
        """Send an actual deckhand to the roller and clear it on arrival."""
        if (sailor is None or sailor.mode != Sailor.ABOARD or sailor.ladder is not None
                or sailor.deck_action is not None or sailor in (self.helm_operator, self.radio_operator)):
            available = [s for s in self.sailors if s.mode == Sailor.ABOARD and s.level in (Level.MAIN, Level.BELOW)
                         and s.ladder is None and s.deck_action is None and s.health > 0.0
                         and s not in (self.helm_operator, self.radio_operator)]
            sailor = min(available, key=lambda s: s.pos.distance_to(V(-self.ship.length * 0.45, 0.0)), default=None)
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.ladder is not None:
            self.crew.say("Captain: No available deckhand can clear the stern gear right now.")
            return False
        target = V(-self.ship.length * 0.45, 0.0)
        if sailor.level == Level.MAIN and sailor.pos.distance_to(target) <= 245.0:
            return self.line.operate_roller(sailor)
        sailor.gear_order = "clear_snag"
        sailor.order_to(target, Level.MAIN)
        self.record_log_entry("Captain's order: %s sent aft to clear the stern-gear snag." % sailor.name)
        self.crew.say("%s: Going aft to clear the buoy/mainline at the roller." % sailor.name)
        return True

    def _perform_context_action(self, option):
        menu = self.context_menu
        if menu is None:
            return
        target = menu.get("target") or {}
        action, value = option.get("action"), option.get("value")
        sailor = target.get("sailor") if target.get("kind") == "sailor" else self.selected()
        self.context_menu = None
        if action == "close":
            return
        if action == "move_here":
            selected = self.selected()
            if selected is None:
                self.crew.say("Captain: Select a sailor first.")
                return
            deck_target = target.get("pos")
            deck_level = target.get("level", self.view_level())
            selected.order_to(deck_target, deck_level)
            self.record_log_entry("Captain's order: %s ordered to a point on %s." %
                                  (selected.name, "the main deck" if deck_level == Level.MAIN else "the lower deck"))
        elif action == "select_sailor":
            self.select(target.get("sailor"))
        elif action == "set_duty":
            crew_target = target.get("sailor")
            if crew_target is not None:
                crew_target.set_duty(value)
                self.record_log_entry("Captain's order: %s assigned to %s." % (crew_target.name, value or "no duty"))
        elif action == "captain_fish":
            self.start_fishing_trip()
        elif action == "captain_port":
            self.order_return_to_port()
        elif action == "set_selected_duty":
            selected = self.selected()
            if selected is not None:
                selected.set_duty(value)
                self.record_log_entry("Captain's order: %s assigned to %s." % (selected.name, value))
            else:
                self.crew.say("Captain: Select a sailor first.")
        elif action == "hatch_order":
            self._queue_hatch_context_order(sailor, value["key"], value["open"])
        elif action == "inspect_gear":
            self.crew.say(self.line.status_text())
            self.record_log_entry("Fishing gear inspected from the right-click context menu.")
        elif action == "haul_now":
            self.line.haul_now()
        elif action == "clear_snag":
            self._queue_stern_snag_clear(sailor)
        elif action == "operate_roller":
            self.line.operate_roller(sailor)

    def draw_context_menu(self):
        """Paint a small, non-modal right-click menu and cache its option hitboxes."""
        menu = self.context_menu
        if menu is None:
            return
        if self.chart_open or self.notebook_open or self.auction_active:
            self.context_menu = None
            return
        font = self.hud_compact_font
        labels = [str(item.get("label", "")) for item in menu["options"]]
        width = max([font.size(menu["title"])[0] + 24] + [font.size(label)[0] + 24 for label in labels])
        row_h, title_h, pad = 25, 27, 4
        height = title_h + row_h * len(labels) + pad * 2
        x = int(clamp(menu["pos"][0], 5, max(5, W - width - 5)))
        y = int(clamp(menu["pos"][1], 5, max(5, H - height - 5)))
        outer = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (22, 29, 34), outer)
        pygame.draw.rect(self.screen, (181, 164, 125), outer, 1)
        title_surf = self.hud_compact_font.render(menu["title"], True, (240, 220, 173))
        self.screen.blit(title_surf, (x + 10, y + 5))
        rects = []
        yy = y + title_h
        for label in labels:
            rect = pygame.Rect(x + 3, yy, width - 6, row_h)
            pygame.draw.rect(self.screen, (43, 53, 58), rect)
            surf = font.render(label, True, (231, 236, 231))
            self.screen.blit(surf, (rect.x + 8, rect.y + (row_h - surf.get_height()) // 2))
            rects.append(rect)
            yy += row_h
        menu["rects"] = rects

    def _ocean_helm_ready(self):
        helm_pos = self.ship.wheelhouse_stations["helm"]
        return any(
            s is self.helm_operator and s.mode == Sailor.ABOARD
            and s.level == Level.WHEELHOUSE and s.task == "post"
            and s.at_post and s.pos.distance_to(helm_pos) <= 55.0
            for s in self.sailors
        )

    def _ocean_visibility_ready(self):
        w, wx = self.world, self.weather
        return visibility_allows_ocean_plot(
            w.daylight(), wx.fog, wx.rain, wx.visibility_km()
        )

    def _ocean_plot_order_allowed(self, persistent=False):
        if self.view_level() != Level.MAIN:
            self.crew.say("Ocean steering is for the working deck only. Use C at the chart table from below.")
            return False
        if not self._ocean_visibility_ready():
            # A skipper may still make a short visual manoeuvre in bad weather.
            # The target conversion below sharply reduces the range and uncertainty
            # grows with rain, fog and darkness; the chart remains the long-leg tool.
            self.crew.say("Captain: Poor visibility. Keep that ocean mark close; use the chart for any longer leg.")
        if self.line.auto:
            self.crew.say("Captain: Auto-fishing has navigation priority. Stand it down before steering the ship.")
            return False
        if self.line.stage != "off":
            if persistent:
                self.crew.say("Captain: The fishing gear is still out. Only a short steer-to order is safe until the line is secured.")
                return False
            if self.line.phase not in (Longline.SOAKING, Longline.HAULING):
                self.crew.say("Captain: Keep the ship steady while setting the longline. Wait until the soak or haul before manoeuvring.")
                return False
            self.crew.say("Captain: Short steer-to order only while the line is out. Watch tension and the starboard-quarter roller.")
        if self.world.dock_state is not None or self.mob_rescue_mode != "idle" or self.crew.alarm_target is not None:
            self.crew.say("Captain: Docking or man-overboard work has the helm. Ocean order held.")
            return False
        return True

    def _ocean_world_at_screen(self, screen_point):
        """Convert a visible water mark to a relative visual target, not an exact chart fix."""
        w = self.world
        rel = screen_to_relative(screen_point, (CENTER.x, CENTER.y), self.zoom)
        # Ocean clicks represent nearby water a lookout can distinguish, not a
        # supernatural long-range waypoint. Bad weather never disables steering
        # outright, but it collapses the visual range; longer legs belong on the estimated-position chart.
        daylight = w.daylight()
        visibility = max(0.0, float(self.weather.visibility_km()))
        quality = clamp(0.22 + 0.72 * daylight - 0.58 * float(self.weather.fog)
                        - 0.28 * float(self.weather.rain), 0.14, 1.0)
        range_from_visibility = max(190.0, visibility * 300.0) * quality
        max_visible = min(1100.0 * w.scale, max(190.0 * w.scale, range_from_visibility * w.scale))
        limited = extend_edge_target(
            rel, screen_point, (W, H), self.zoom, max_visible,
            edge_margin=28.0, extension_pixels=160.0,
        )
        self.ocean_plot_edge_extended = (math.hypot(limited[0] - rel[0], limited[1] - rel[1]) > 1.0)
        # The ocean view is in the ship-centred heading-up frame; rotate the observed
        # offset back into world space. The crew's estimated position remains the track origin.
        return w.ship_pos + V(limited).rotate_rad(w.heading)


    def _clear_ocean_course(self, say=True):
        w = self.world
        existed = bool(w.route_waypoints) or w.ocean_quick_target is not None
        w.route_waypoints.clear()
        w.route_origin = None
        w.route_arrival_hold = False
        w.ocean_quick_target = None
        if w.dock_state is None and w.rescue_to is None and self.mob_rescue_mode == "idle":
            w.destination = None
            w.ap_t = 0.0
            w.throttle = min(w.throttle, 0.12)
        if existed:
            self.record_log_entry("Ocean/chart course cleared by the captain.")
            if say:
                self.crew.say("Captain: Plot cleared. Hold present heading and await orders.")

    def _handle_ocean_right_click(self, screen_point, shift=False):
        w = self.world
        # Ocean orders never test for invisible waypoint markers. Edit/delete plotted
        # legs on the chart table (C), where their lines and handles are actually seen.
        if not self._ocean_plot_order_allowed(persistent=shift):
            return
        target = self._ocean_world_at_screen(screen_point)
        if shift:
            self.ocean_plot_drag_start = V(target)
            self.ocean_plot_drag_start_screen = V(screen_point)
            self.ocean_plot_preview_world = V(target)
            self.ocean_plot_edit_index = None
            return

        # A plain right-click is intentionally only a short, disposable bearing order.
        self._clear_ocean_course(say=False)
        w.route_origin = V(w.believed_pos)
        w.route_arrival_hold = False
        w.ocean_quick_target = V(target)
        w.set_destination(target, preserve_route=True)
        w.ocean_quick_target = V(target)
        metrics = leg_metrics(w.ship_pos, target, position=w.ship_pos,
                              speed_knots=max(0.7, 10.0 * w.speed / max(1.0, w.max_speed)),
                              units_per_nautical_mile=world_units_per_nautical_mile(w.scale))
        self.record_log_entry("Steer-to order: bearing %03.0f / %.2f nm; helm: %s. Visual mark, not a plotted leg." % (
            metrics["bearing"], metrics["distance"] / (world_units_per_nautical_mile(w.scale)),
            self.helm_operator.name if self.helm_operator is not None else "unassigned"))
        if self._ocean_helm_ready():
            self.crew.say("Helm: Come to %03.0f, make for that water mark. Quick order, not a plotted leg." % metrics["bearing"])
        else:
            self.crew.say("Captain: Bearing noted in the notebook, but nobody is properly at the helm; the ship will not execute it.")

    def _finish_ocean_plot_drag(self, screen_point):
        start = self.ocean_plot_drag_start
        start_screen = self.ocean_plot_drag_start_screen
        edit_index = self.ocean_plot_edit_index
        end = self._ocean_world_at_screen(screen_point)
        self.ocean_plot_drag_start = None
        self.ocean_plot_drag_start_screen = None
        self.ocean_plot_preview_world = None
        self.ocean_plot_edit_index = None
        if start is None or start_screen is None:
            return
        if V(screen_point).distance_to(start_screen) < 14.0:
            self.crew.say("Plot not committed. Hold Shift and drag from A to B; a plain right-click is steer-to.")
            return
        if not self._ocean_plot_order_allowed(persistent=True):
            return
        w = self.world
        if edit_index is not None:
            if edit_index == -1:
                w.ocean_quick_target = V(end)
                w.set_destination(end, preserve_route=True)
                w.ocean_quick_target = V(end)
                self.record_log_entry("Quick steering mark repositioned by ocean plot.")
                self.crew.say("Helm: Quick mark moved. Bearing order updated.")
                return
            w.route_waypoints[edit_index] = V(end)
            if edit_index == 0:
                w.set_destination(end, preserve_route=True)
            self.record_log_entry("Ocean waypoint %d repositioned." % (edit_index + 1))
            self.crew.say("Helm: Waypoint repositioned. Track updated; current and leeway will still set the boat off line.")
            return

        near_ship = start.distance_to(w.ship_pos) <= self.ship.length * 0.58 + 110.0
        w.route_origin = V(w.believed_pos)
        w.route_waypoints = [V(end)] if near_ship else [V(start), V(end)]
        w.ocean_quick_target = None
        w.route_arrival_hold = False
        w.set_destination(w.route_waypoints[0], preserve_route=True)
        w.route_origin = V(w.believed_pos)
        if len(w.route_waypoints) == 2:
            point_a, point_b = V(w.route_waypoints[0]), V(w.route_waypoints[1])
            nm = point_a.distance_to(point_b) / (world_units_per_nautical_mile(w.scale))
            bearing = bearing_degrees(point_a, point_b)
            self.record_log_entry("Plotted ocean leg %03.0f / %.2f nm (A to B); helm: %s." % (
                bearing, nm, self.helm_operator.name if self.helm_operator is not None else "unassigned"))
        else:
            metrics = leg_metrics(w.route_origin, w.route_waypoints[0], position=w.route_origin,
                                  speed_knots=max(0.7, 10.0 * w.speed / max(1.0, w.max_speed)),
                                  units_per_nautical_mile=world_units_per_nautical_mile(w.scale))
            self.record_log_entry("Plotted ocean leg %03.0f / %.2f nm — helm: %s." % (
                metrics["bearing"], metrics["distance"] / (world_units_per_nautical_mile(w.scale)),
                self.helm_operator.name if self.helm_operator is not None else "unassigned"))
        if self._ocean_helm_ready():
            self.crew.say("Helm: Ocean leg committed. I'll steer the track; current, wind and turning room will set the actual path.")
        else:
            self.crew.say("Captain: Ocean leg logged, but no helmsman is properly at the wheel. It will wait until the helm is manned.")

    def view_level(self):
        """The level on screen: the selected sailor's, or the one being peeked at."""
        if self.peek is not None:
            return self.peek
        sel = self.selected()
        return sel.level if sel is not None and sel.mode == Sailor.ABOARD else Level.MAIN

    def _hatch_in_use(self, key, except_sailor=None):
        """A hatch cannot be dogged while anyone is physically in its ladder animation."""
        for person in self.sailors:
            if person is except_sailor or person.ladder is None:
                continue
            link = person.ladder.get("link")
            if link is not None and self.ship.hatch_key_for_link(link) == key:
                return True
        return False

    def _nearest_hatch_action(self, sailor):
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.ladder is not None:
            return None
        candidates = []
        for key, label, pos in self.ship.hatch_interaction_points(sailor.level):
            if sailor.level == Level.BELOW:
                # The engine room and ice hold are bulkheaded off from one another.
                nav = self.ship.maps[Level.BELOW]
                if not nav.connected(sailor.pos, pos):
                    continue
            distance = sailor.pos.distance_to(pos)
            if distance <= 56.0:
                candidates.append((distance, key, label, pos))
        return min(candidates, default=None, key=lambda row: row[0])

    def _start_hatch_action(self, sailor, key, automatic=False):
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.ladder is not None or sailor.deck_action is not None:
            return False
        opening = not self.ship.hatch_is_open(key)
        if not opening and self._hatch_in_use(key, sailor):
            if not automatic:
                self.crew.say("Someone is still on that ladder. Wait before dogging the hatch.")
            return False
        if automatic:
            # AI opens a cover only after reaching its landing; it is dogged again after crossing.
            if key == "engine":
                links = [lk for lk in self.ship.links if self.ship.hatch_key_for_link(lk) == key and sailor.level in lk.ends]
                if links and min(sailor.pos.distance_to(lk.pos(sailor.level)) for lk in links) > 62.0:
                    return False
            else:
                links = [lk for lk in self.ship.links if self.ship.hatch_key_for_link(lk) == key and sailor.level in lk.ends]
                if links and min(sailor.pos.distance_to(lk.pos(sailor.level)) for lk in links) > 62.0:
                    return False
        sailor.deck_action = {"kind": "hatch", "key": key, "opening": opening,
                              "automatic": bool(automatic), "elapsed": 0.0, "duration": 1.35}
        sailor.vel = V(0, 0)
        if not automatic:
            sailor.has_target = False
        if automatic and opening:
            sailor.auto_close_hatch = key
        return True

    def toggle_nearby_hatch(self, sailor):
        nearest = self._nearest_hatch_action(sailor)
        if nearest is None:
            self.crew.say("Captain: Stand within arm's reach of an engine or hold hatch to work its dogs. (U)")
            return False
        _distance, key, label, _pos = nearest
        if sailor.deck_action is not None:
            self.crew.say("Finish the current job before working another hatch.")
            return False
        if not self._start_hatch_action(sailor, key, automatic=False):
            return False
        action = "open" if not self.ship.hatch_is_open(key) else "dog shut"
        self.crew.say("%s: %s %s." % (sailor.name, "Opening" if action == "open" else "Dogging", label))
        return True

    def _finish_deck_action(self, sailor):
        action = sailor.deck_action
        if action is None:
            return
        kind = action["kind"]
        if kind == "hatch":
            key = action["key"]
            opening = bool(action["opening"])
            if not opening and self._hatch_in_use(key, sailor):
                self.crew.say("Someone is still on the ladder; the hatch stays open.")
                sailor.deck_action = None
                return
            self.ship.hatch_states[key] = opening
            label = {"engine": "engine-room hatch", "hold_1": "aft ice-hold hatch", "hold_2": "forward ice-hold hatch"}.get(key, key)
            if action.get("automatic"):
                if opening:
                    sailor.auto_close_hatch = key
                elif sailor.auto_close_hatch == key:
                    sailor.auto_close_hatch = None
                self.record_log_entry("%s %s the %s automatically." %
                                      (sailor.name, "opened" if opening else "closed", label))
            else:
                self.crew.say("%s: %s the %s." % (sailor.name, "Hatch open" if opening else "Hatch dogged shut", label))
                self.record_log_entry("%s %s the %s." % (sailor.name, "opened" if opening else "dogged shut", label))
        elif kind == "hose":
            self.table_blood = max(0.0, self.table_blood - 0.85)
            rinsed = 0
            for patch in self.patches:
                if patch.kind == "blood" and patch.pos.distance_to(self.ship.hose_station) < 190.0:
                    patch.cleaning = min(1.0, patch.cleaning + 0.8)
                    rinsed += 1
                elif patch.kind == "slime" and patch.pos.distance_to(self.ship.hose_station) < 130.0:
                    patch.cleaning = min(1.0, patch.cleaning + 0.55)
            self.ship.wet = min(1.0, self.ship.wet + 0.14)
            self.crew.say("%s sluices the cutting table and deck with the seawater hose; %d patches loosen." % (sailor.name, rinsed))
            self.record_log_entry("Seawater hose used at the cutting table; blood and slime are rinsed toward the scuppers.")
        elif kind == "ice_trim":
            if self.ice <= 0:
                self.crew.say("There is no ice left to trim. The hold is warming.")
            elif self.ship.hold_flood > 0.45:
                self.crew.say("Too much water is in the ice hold to trim safely. Dog the hatch and bail it first.")
            else:
                self.ice_trimmed_time = 180.0
                self.hold_temp = min(self.hold_temp, 0.25)
                self.crew.say("%s levels the flake ice around the catch. The hold should stay colder and use less ice for a while." % sailor.name)
                self.record_log_entry("Ice hold flake ice trimmed and packed around the catch; cooling efficiency improved for three minutes.")
        sailor.deck_action = None

    def start_hose_wash(self, sailor):
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.level != Level.MAIN or sailor.ladder is not None:
            self.crew.say("Captain: The seawater hose is on the main deck beside the cutting table.")
            return False
        if sailor.pos.distance_to(self.ship.hose_station) > 78.0:
            self.crew.say("%s: Move beside the cutting-table hose first." % sailor.name)
            return False
        if sailor.deck_action is not None:
            return False
        sailor.deck_action = {"kind": "hose", "elapsed": 0.0, "duration": 2.8}
        sailor.vel = V(0, 0)
        self.crew.say("%s: Taking the seawater hose to sluice the table." % sailor.name)
        return True

    def start_ice_trim(self, sailor):
        if sailor is None or sailor.mode != Sailor.ABOARD or sailor.level != Level.BELOW or sailor.ladder is not None:
            self.crew.say("Captain: Ice trimming is done inside the below-deck ice hold. (V)")
            return False
        if not rect_has(self.ship.below_rooms[1], sailor.pos):
            self.crew.say("%s: I need to be inside the ice hold to trim the flake ice." % sailor.name)
            return False
        if sailor.deck_action is not None:
            return False
        sailor.deck_action = {"kind": "ice_trim", "elapsed": 0.0, "duration": 3.2}
        sailor.vel = V(0, 0)
        self.crew.say("%s starts trimming and leveling the flake ice around the catch." % sailor.name)
        return True

    def _close_hatch_after_crossing(self, sailor, key):
        if key not in self.ship.hatch_states or not self.ship.hatch_is_open(key):
            return
        if self._hatch_in_use(key, sailor):
            return
        self.ship.hatch_states[key] = False
        self.record_log_entry("%s dogged the %s after crossing." %
                              (sailor.name, "engine-room hatch" if key == "engine" else "ice-hold hatch"))

    def press_climb(self, sel, direction):
        """Q / E: the selected sailor climbs if he is at a ladder or hatch; otherwise the key peeks at another level."""
        if sel is None or sel.mode != Sailor.ABOARD or sel.ladder is not None:
            return
        lk = self.ship.link_near(sel.level, sel.pos, direction)
        if lk is None:
            return
        self.climb_used = True
        hatch_key = self.ship.hatch_key_for_link(lk)
        if hatch_key and not self.ship.hatch_is_open(hatch_key):
            name = "engine-room hatch" if hatch_key == "engine" else "ice-hold hatch"
            self.crew.say("The %s is dogged shut. Press U to open it before climbing." % name)
            return
        to = lk.other(sel.level)
        if to == Level.WHEELHOUSE and not self.can_enter_wheelhouse(sel):
            self.crew.say("Wheelhouse access is controlled: helm watch or assigned radio operator only.")
            return
        if sel.level == Level.WHEELHOUSE and to != Level.WHEELHOUSE and (sel is self.helm_operator or sel is self.radio_operator):
            self.request_wheelhouse_exit(sel, link=lk)
            return
        if to == Level.WHEELHOUSE and not self.ship.wheelhouse_entry_space(lk.pos(to), sel):
            self.crew.say("Wheelhouse landing is occupied. Wait on deck until there is room.")
            return
        self.climb_used = True
        sel.order_to(lk.pos(to), to)           # he stays where he climbs to, like any other order
        sel.start_climb(lk)

    def select(self, s):
        if s is not None and s.mode == Sailor.SHORE:
            s = None
        for o in self.sailors:
            o.selected = o is s

    def handle(self, ev):
        # Career I/O is global and deliberately precedes modal panels. Ctrl+O is
        # intercepted here, so plain O still requests a speed report on deck.
        if ev.type == pygame.KEYDOWN and (getattr(ev, "mod", pygame.key.get_mods()) & pygame.KMOD_CTRL):
            if ev.key == pygame.K_s:
                self.save_career()
                return True
            if ev.key == pygame.K_o:
                self.load_career()
                return True
        if self.auction_active:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_k):
                    self._auction_keep_current()
                elif ev.key == pygame.K_a:
                    self._auction_accept_all()
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    self._auction_sell_current(ev.key - pygame.K_1)
                elif ev.key in (pygame.K_LEFT, pygame.K_UP):
                    self.auction_index = max(0, self.auction_index - 1)
                    self._auction_advance()
                elif ev.key in (pygame.K_RIGHT, pygame.K_DOWN):
                    self.auction_index = min(max(0, len(self.hold) - 1), self.auction_index + 1)
                    self._auction_advance()
                return True
            return True
        # The radio is a modal interaction panel; its clicks/keys never leak into helm controls.
        if self.radio_ui_open:
            return self._handle_radio_ui(ev)
        # The Ship's Notebook is a modal paper UI. Page/tab interactions must
        # never fall through as helm, duty, or crew movement commands.
        if self.notebook_open:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_F9):
                    self.notebook_open = False
                elif ev.key in (pygame.K_LEFT, pygame.K_COMMA, pygame.K_LESS):
                    self._notebook_turn_page(-1)
                elif ev.key in (pygame.K_RIGHT, pygame.K_PERIOD, pygame.K_GREATER):
                    self._notebook_turn_page(1)
                elif ev.key == pygame.K_TAB:
                    self._notebook_set_section((self.notebook_section + 1) % 5)
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                    self._notebook_set_section(ev.key - pygame.K_1)
                elif ev.key == pygame.K_HOME:
                    self.notebook_page = 0
                return True
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 3:
                    self.notebook_open = False
                else:
                    for name, rect in self.notebook_hitboxes.items():
                        if rect.collidepoint(ev.pos):
                            if name.startswith("section_"):
                                self._notebook_set_section(int(name.split("_", 1)[1]))
                            elif name == "prev":
                                self._notebook_turn_page(-1)
                            elif name == "next":
                                self._notebook_turn_page(1)
                            elif name == "close":
                                self.notebook_open = False
                            break
                return True
            if ev.type == pygame.MOUSEWHEEL:
                self._notebook_turn_page(-1 if ev.y > 0 else 1)
                return True
            return True
        # The navigation chart owns input while open: chart clicks edit a staged
        # course and never issue crew/deck orders. Enter commits, Escape clears the
        # course, and closing without Enter discards uncommitted edits.
        if self.chart_open:
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_b:
                    self._set_campaign_phase("B")
                    return True
                if ev.key == pygame.K_a:
                    self._set_campaign_phase("A")
                    return True
                if ev.key == pygame.K_r and self.campaign_phase == "B":
                    self._open_phase_b_selected_radio_contact()
                    return True
                if ev.key == pygame.K_RETURN or ev.key == pygame.K_KP_ENTER:
                    self._commit_chart_route()
                    return True
                if ev.key == pygame.K_ESCAPE:
                    self._clear_chart_route()
                    return True
                if ev.key == pygame.K_c:
                    self._close_navigation_chart()
                    return True
                if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    fix_kind = {pygame.K_1: "landmark", pygame.K_2: "sextant",
                                pygame.K_3: "rdf", pygame.K_4: "sounder"}[ev.key]
                    self._attempt_navigation_fix(fix_kind)
                    return True
                if ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    # Convenient route editing on compact devices; points are still
                    # persisted in chart units and not screen pixels.
                    if self.chart_route_editor and self.chart_route_editor.points:
                        delta = -1 if ev.key == pygame.K_LEFT else 1
                        if self.chart_move_index is None:
                            self.chart_move_index = 0 if delta > 0 else len(self.chart_route_editor.points) - 1
                        else:
                            self.chart_move_index = int(clamp(self.chart_move_index + delta, 0, len(self.chart_route_editor.points) - 1))
                        self.chart_status = "WAYPOINT %d SELECTED — CLICK ITS NEW POSITION" % (self.chart_move_index + 1)
                    return True
            if ev.type == pygame.MOUSEMOTION:
                self.chart_mouse_pos = ev.pos
                return True
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    phase_hit = next((phase for phase, rect in self._chart_phase_button_rects.items()
                                      if rect.collidepoint(ev.pos)), None)
                    if phase_hit is not None:
                        self._set_campaign_phase(phase_hit)
                    elif self.campaign_phase == "B" and self._select_phase_b_contact_at(ev.pos):
                        pass
                    else:
                        self._handle_chart_left_click(ev.pos, bool(getattr(ev, "mod", 0) & pygame.KMOD_SHIFT))
                elif ev.button == 3:
                    self._handle_chart_right_click(ev.pos)
                return True
            return True
        # Context menus take the next left click, but do not become modal: clicking
        # outside closes the menu and proceeds with the world action under that click.
        if self.context_menu is not None:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.context_menu = None
                return True
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                self.context_menu = None
                return True
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                menu = self.context_menu
                hit_index = next((i for i, rect in enumerate(menu.get("rects", [])) if rect.collidepoint(ev.pos)), None)
                if hit_index is not None:
                    option = menu["options"][hit_index]
                    self._perform_context_action(option)
                    return True
                self.context_menu = None
        # Ocean navigation shares the chart's route model. Escape cancels a drag or active course; a course never disappears as an accidental side effect of a
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.ocean_plot_drag_start is not None:
                self.ocean_plot_drag_start = self.ocean_plot_drag_start_screen = None
                self.ocean_plot_preview_world = None
                self.ocean_plot_edit_index = None
                self.crew.say("Plot edit cancelled.")
                return True
            if self.world.route_waypoints or self.world.ocean_quick_target is not None:
                self._clear_ocean_course()
                return True
        if ev.type == pygame.MOUSEMOTION and self.ocean_plot_drag_start is not None:
            self.ocean_plot_preview_world = self._ocean_world_at_screen(ev.pos)
            return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 3 and self.ocean_plot_drag_start is not None:
            self._finish_ocean_plot_drag(ev.pos)
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F5:
            self.show_controls = not self.show_controls
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F6:
            self.show_fishing_minigame = not self.show_fishing_minigame
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F7:
            self.hud_mode = "operations" if self.hud_mode == "navigation" else "navigation"
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F8:
            self.telemetry_visible = not self.telemetry_visible
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F10:
            self.longline_minimap_debug = not self.longline_minimap_debug
            self.crew.say("Debug longline map %s." % ("enabled" if self.longline_minimap_debug else "hidden"))
            return True
        # F11 remains fullscreen; Ctrl+F11 opens the selectable radio UI.
        if (ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11
                and (getattr(ev, "mod", pygame.key.get_mods()) & pygame.KMOD_CTRL)):
            self.open_radio_ui()
            return True
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F12:
            self.tow_debug_enabled = not self.tow_debug_enabled
            self.tow_debug_elapsed = 0.0
            self.tow_debug_sample_elapsed = 0.0
            self.tow_debug_last_ship_pos = V(self.world.ship_pos)
            print("[TOW DEBUG] %s" % ("enabled — printing one line per simulation second" if self.tow_debug_enabled else "disabled"))
            self.crew.say("Tow diagnostics %s; see the console." % ("enabled" if self.tow_debug_enabled else "disabled"))
            return True
        if self.crew_sheet_open:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_F1):
                    self.crew_sheet_open = False
                elif ev.key == pygame.K_TAB or ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    tabs = ("ship_catch", "telemetry", "crew", "controls")
                    i = tabs.index(self.info_sheet_tab) if self.info_sheet_tab in tabs else 0
                    step = -1 if ev.key == pygame.K_LEFT else 1
                    self._sheet_action("info_tab", tabs[(i + step) % len(tabs)])
                elif self.info_sheet_tab == "crew" and ev.key == pygame.K_1:
                    self._sheet_action("tab", "crew")
                elif self.info_sheet_tab == "crew" and ev.key == pygame.K_2:
                    self._sheet_action("tab", "shore")
                elif self.info_sheet_tab == "crew" and ev.key == pygame.K_3:
                    self._sheet_action("tab", "hire")
                elif ev.key == pygame.K_UP:
                    if self.info_sheet_tab == "crew":
                        self.crew_sheet_scroll = max(0, self.crew_sheet_scroll - 1)
                    else:
                        self.info_sheet_scroll = max(0, self.info_sheet_scroll - 1)
                elif ev.key == pygame.K_DOWN:
                    if self.info_sheet_tab == "crew":
                        self.crew_sheet_scroll += 1
                    else:
                        self.info_sheet_scroll += 1
                return True
            if ev.type == pygame.MOUSEBUTTONDOWN:
                self._handle_crew_sheet_click(ev.pos)
                return True
            if ev.type == pygame.MOUSEWHEEL:
                if self.info_sheet_tab == "crew":
                    self.crew_sheet_scroll = max(0, self.crew_sheet_scroll - ev.y)
                else:
                    self.info_sheet_scroll = max(0, self.info_sheet_scroll - ev.y)
                return True
        if ev.type == pygame.KEYDOWN:
            sel = self.selected()
            k = ev.key
            if k == pygame.K_ESCAPE:
                return False
            elif k == pygame.K_c:
                self._open_navigation_chart()
            elif k == pygame.K_F9:
                self.notebook_open = True
                self.notebook_page = 0
            elif k == pygame.K_l:
                cancelled_route = bool(not self.line.auto and
                                       (self.world.route_waypoints or self.world.ocean_quick_target is not None))
                if cancelled_route:
                    # The supplied design gives auto-fishing priority over a manual
                    # chart course. Clear the route before the fishing AI picks a
                    # destination, but deliver the override message after its generic
                    # toggle response so the important message remains visible.
                    self.world.route_waypoints.clear()
                    self.world.route_origin = None
                    self.world.route_arrival_hold = False
                    self.world.ocean_quick_target = None
                    self.world.destination = None
                    self.world.ap_t = 0.0
                    self.record_log_entry("Manual chart route cancelled because auto-fishing took priority. Any active ocean leg or steer-to mark was also cleared.")
                self.line.toggle_auto()
                if cancelled_route:
                    self.crew.say("Captain: Auto-fishing takes priority. Manual waypoint route cancelled.")
            elif k == pygame.K_p:
                self.line.begin_manual_set()
            elif k == pygame.K_m:
                self.line.operate_roller(sel)
            elif k == pygame.K_u:
                self.toggle_nearby_hatch(sel)
            elif k == pygame.K_f:
                self.start_hose_wash(sel)
            elif k == pygame.K_v:
                self.start_ice_trim(sel)
            elif k == pygame.K_j:
                self.line.haul_now()
            elif k == pygame.K_h:
                self.start_muster()
            elif k == pygame.K_r:
                swimmers = [s for s in self.sailors if s.mode == Sailor.SWIMMING]
                if swimmers:
                    swimmer = min(swimmers, key=lambda s: s.wpos.distance_to(self.world.ship_pos))
                    self.crew.alarm_target = swimmer
                    self.begin_mob_rescue(swimmer)
                    self.crew.say("Captain: Rescue order confirmed for %s. All available hands respond." % swimmer.name)
                else:
                    self.crew.say("Captain: No fallen crew in the water to rescue.")
            elif k == pygame.K_b:
                self.settle(manual=True)
            elif k == pygame.K_a:
                self.toggle_anchor()
            elif k == pygame.K_d:
                self.toggle_autodock()
            elif k == pygame.K_n:
                self.navigation_mode = "dead_reckoning"
                self.crew.say("Navigation: dead reckoning. Compass and estimated speed only; no GPS, radar or echo sounder.")
            elif k == pygame.K_i:
                self._request_crew_report("bearing_distance")
            elif k == pygame.K_o:
                self._request_crew_report("speed")
            elif k == pygame.K_k:
                self.cycle_bait()
            elif k == pygame.K_y:
                self.toggle_harness()
            elif k == pygame.K_w:
                self.weather.cycle()
            elif k == pygame.K_F1:
                self.crew_sheet_open = not self.crew_sheet_open
                self.info_sheet_tab = "ship_catch"
                self.crew_sheet_tab = "crew"
                self.crew_sheet_scroll = 0
                self.info_sheet_scroll = 0
            elif k == pygame.K_F2:
                self.radio_call("weather")
            elif k == pygame.K_F3:
                self.radio_call("auction")
            elif k == pygame.K_F4:
                if self.tow_escort is not None and self.tow_escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW", "ARRIVED"):
                    self.tow_escort_talk("position")
                else:
                    self.radio_call("tow")
            elif k == pygame.K_g:
                if self.tow_escort is not None and self.tow_escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW"):
                    self.tow_escort_talk()
            elif k == pygame.K_LEFTBRACKET:
                self.line.adjust_slack(-0.05)
            elif k == pygame.K_RIGHTBRACKET:
                self.line.adjust_slack(0.05)
            elif k == pygame.K_F11:
                try:
                    pygame.display.toggle_fullscreen()
                except pygame.error:
                    pass
            elif k == pygame.K_t:
                self.timescale = {1: 3, 3: 6, 6: 1}[self.timescale]
            elif k == pygame.K_q:
                self.press_climb(sel, 1)
            elif k == pygame.K_e:
                self.press_climb(sel, -1)
            elif k == pygame.K_TAB:
                alive = [s for s in self.sailors if s.mode not in (Sailor.DEAD, Sailor.SHORE)]
                if alive:
                    i = alive.index(sel) if sel in alive else -1
                    self.select(alive[(i + 1) % len(alive)])
            elif sel is not None and sel.mode == Sailor.ABOARD:
                duties = {pygame.K_1: "set", pygame.K_2: "haul", pygame.K_3: "clean", pygame.K_4: "rest",
                          pygame.K_5: "dress", pygame.K_6: "engine", pygame.K_7: "post", pygame.K_0: ""}
                if k in duties:
                    sel.set_duty(duties[k])
                    duty_name = {"set": "line setting", "haul": "hauling", "clean": "fish cleaning",
                                 "rest": "rest", "dress": "dressing fish", "engine": "engine watch",
                                 "post": "helm watch", "": "no assigned duty"}.get(duties[k], duties[k])
                    self.record_log_entry("Captain's order: %s assigned to %s." % (sel.name, duty_name))
                    if k == pygame.K_7:
                        self.crew.say("%s: Going up to the wheelhouse." % sel.name)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            if self.telemetry_panel_rect.collidepoint(ev.pos):
                if not self.telemetry_visible:
                    self.telemetry_visible = True
                return True  # Never let a HUD click become a crew/world order.
            if getattr(self, "radio_hud_rect", pygame.Rect(0, 0, 0, 0)).collidepoint(ev.pos):
                self.open_radio_ui()
                return True
            if getattr(self, "anchor_hud_rect", pygame.Rect(0, 0, 0, 0)).collidepoint(ev.pos):
                self.toggle_anchor()
                return True
            if getattr(self, "money_hud_rect", pygame.Rect(0, 0, 0, 0)).collidepoint(ev.pos):
                return True
            if getattr(self, "profile_rect", pygame.Rect(0, 0, 0, 0)).collidepoint(ev.pos):
                return True
            d = self.unSS(V(ev.pos))
            if ev.button == 3 and self.view_level() == Level.MAIN:
                shift = bool(getattr(ev, "mod", pygame.key.get_mods()) & pygame.KMOD_SHIFT)
                # Persistent course editing belongs on the chart table; the ocean view
                # reserves a plain right-click for a quick steer-to order. Right-click
                # visible sailors, hatches, hauler, roller, or buoys for object actions,
                # while empty walkable deck opens the movement/work context menu.
                if self._open_context_menu_at(ev.pos, d):
                    return True
                if not self.ship.on_deck(d):
                    self._handle_ocean_right_click(ev.pos, shift)
                    return True
            elif ev.button == 3 and self._open_context_menu_at(ev.pos, d):
                return True
            if ev.button == 1:
                hit = None
                vl = self.view_level()
                for s in self.sailors:
                    visible_levels = (vl, Level.MAIN) if vl == Level.WHEELHOUSE else (vl,)
                    if (s.mode not in (Sailor.DEAD, Sailor.SHORE)
                            and s.pos.distance_to(d) < 24 * s.scale
                            and (s.level in visible_levels or s.mode != Sailor.ABOARD)):
                        hit = s
                if hit is not None:
                    self._try_second_opinion(hit)
                self.select(hit)
            elif ev.button == 3:
                sel = self.selected()
                if sel:
                    target_level = self.view_level()
                    if target_level == Level.WHEELHOUSE:
                        if rect_has(self.ship.wheelhouse_floor, d):
                            # Right-click on an instrument sends him to it; elsewhere on the floor, just to that spot.
                            hit = self.ship.station_at(d)
                            if hit is not None:
                                sel.order_to(hit[1], Level.WHEELHOUSE)
                                self.record_log_entry("Captain's order: %s assigned to the %s station." % (sel.name, hit[0]))
                                self.crew.say("%s: Heading for the %s." % (sel.name, hit[0]))
                            else:
                                if not self.can_enter_wheelhouse(sel):
                                    self.crew.say("Wheelhouse access is controlled: helm watch or assigned radio operator only.")
                                else:
                                    sel.order_to(self.ship.wheelhouse_floor_point(d), Level.WHEELHOUSE)
                                    self.record_log_entry("Captain's order: %s ordered to a position in the wheelhouse." % sel.name)
                        else:
                            # An explicit exit order hands off helm/radio ownership first,
                            # then routes through the wheelhouse ladder instead of rejecting it.
                            if sel.level == Level.WHEELHOUSE and (sel is self.helm_operator or sel is self.radio_operator):
                                self.request_wheelhouse_exit(sel, d)
                                self.record_log_entry("Captain's order: %s ordered to leave the wheelhouse." % sel.name)
                            else:
                                sel.order_to(d, Level.MAIN)
                                self.record_log_entry("Captain's order: %s ordered to the main deck." % sel.name)
                    elif target_level == Level.MAIN and rect_has(self.ship.wheelhouse, d):
                        # From deck view, click the cabin to use its ladder and enter it.
                        hit = self.ship.station_at(d)
                        if hit is not None:
                            sel.order_to(hit[1], Level.WHEELHOUSE)
                            self.record_log_entry("Captain's order: %s sent to the %s station." % (sel.name, hit[0]))
                        else:
                            if not self.can_enter_wheelhouse(sel):
                                self.crew.say("Wheelhouse access is controlled: helm watch or assigned radio operator only.")
                            else:
                                sel.order_to(self.ship.wheelhouse_floor_point(d), Level.WHEELHOUSE)
                                self.record_log_entry("Captain's order: %s ordered into the wheelhouse." % sel.name)
                                self.crew.say("%s: Going into the wheelhouse." % sel.name)
                    else:
                        sel.order_to(d, target_level)
                        self.record_log_entry("Captain's order: %s ordered to move on %s." %
                                               (sel.name, "the main deck" if target_level == Level.MAIN else "the lower deck"))
        elif ev.type == pygame.MOUSEWHEEL:
            self.zoom = clamp(self.zoom * (1.1 ** ev.y), 0.08, 2.5)
        return True

    # --- simulation
    def update(self, dt, keys):
        w = self.world
        # Expire unanswered second-opinion requests as simulation time advances.
        if self.crew_report_pending is not None and w.time >= self.crew_report_pending["deadline"]:
            self.crew_report_pending = None
            if self.crew_report_display and self.crew_report_display.get("mode") == "pending":
                self.crew_report_display = None
        if self.auction_active:
            self.chart_open = False
            # Modal auction pauses the world; UI input is handled in handle().
            return
        if self.chart_open or self.notebook_open or self.radio_ui_open:
            # Do not let held steering/brake/duty keys leak through modal overlays.
            keys = _NO_GAMEPLAY_KEYS
        if self.crew_sheet_open and not self.shore_wait_active:
            # The F1 information sheet is modal too; shore recovery can keep running when explicitly requested.
            return
        if self.shore_wait_active:
            returning = self._shore_returning_crew()
            if not self.docked() or not returning:
                if not self.docked():
                    self._stop_shore_wait("Dockmaster: Waiting stopped because the vessel is no longer alongside.")
                else:
                    self._stop_shore_wait("Dockmaster: Waiting stopped; no automatic shore party remains.")
            elif all(shore_recovery_ready(s) for s in returning):
                self._stop_shore_wait()
                self._recall_shore_leave()
                # Waiting is not a new docking event: keep the shore-leave trigger
                # latched so a later settlement check does not immediately send
                # the recovered crew back into town.
                self.dock_shore_leave_started = True
                self.crew.say("Dockmaster: Shore party recovered. All returning hands are aboard.")
        # Manual departure from the quay also recalls the automatic shore party;
        # otherwise there would be nobody available to reach the helm in time.
        steer_keys = (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN)
        if self.docked() and any(keys[k] for k in steer_keys):
            self._recall_shore_leave(departure=True)
        self._update_station_roles(dt)
        sel = self.selected()                                     # Q / E held with no ladder to climb: peek up or down
        q, e = bool(keys[pygame.K_q]), bool(keys[pygame.K_e])
        if not (q or e):
            self.climb_used = False
        self.peek = None
        if q != e and not self.climb_used and sel is not None and sel.mode == Sailor.ABOARD and sel.ladder is None:
            lv = int(clamp(sel.level + (1 if q else -1), -1, 1))
            if lv != sel.level:
                self.peek = Level(lv)
        # In rough weather the launch is forbidden: stop first, then creep back until the davit line reaches.
        tgt = self.crew.alarm_target
        w.rescue_to = None
        if (self.mob_rescue_mode == "ship_turn" and tgt is not None
                and tgt.mode == Sailor.SWIMMING and tgt.lifeline is None):
            swimmer_local = w.deck_of(tgt.wpos)
            # Keep manoeuvring until the swimmer is genuinely close to the rail.
            # The approach controller then pivots to present starboard for the throw.
            if self.ship.nearest_hull_point(swimmer_local).distance_to(swimmer_local) > 80.0:
                w.rescue_to = V(tgt.wpos)
        if w.rescue_to is not None:
            e = self.rescue_engineer
            if e is None or e.mode != Sailor.ABOARD or e.rescue_target is not None:
                cands = [o for o in self.sailors if o.mode == Sailor.ABOARD and o.role != Sailor.CAPTAIN and o not in (self.helm_operator, self.radio_operator) and o.rescue_target is None]
                em = self.ship.markers["engine"]
                self.rescue_engineer = min(cands, key=lambda o: o.pos.distance_to(em) + (0 if o.level == Level.BELOW else 400)) if cands else None
        else:
            self.rescue_engineer = None
        helm_pos = self.ship.wheelhouse_stations["helm"]
        helm_ok = any(
            s is self.helm_operator
            and s.mode == Sailor.ABOARD
            and s.level == Level.WHEELHOUSE
            and s.task == "post"
            and s.at_post
            and s.pos.distance_to(helm_pos) <= 55.0
            for s in self.sailors
        )
        eng = next((s for s in self.sailors if s.mode == Sailor.ABOARD and s.at_engine), None)
        engine_demand = (w.destination is not None or w.rescue_to is not None or w.dock_state is not None
                         or w.throttle > 0.025 or w.speed > 25.0
                         or self.line.phase in (Longline.SETTING, Longline.HAULING))
        if engine_demand:
            self.engine_hold = 8.0
        else:
            self.engine_hold = max(self.engine_hold - dt, 0.0)
        if self.engine_hold > 0 and eng is None:
            self.engine_wait += dt
            if self.engine_wait > 6.0 and not self.engine_warned:
                self.crew.say("No engineer below. The engine checks are going unattended.")
                self.engine_warned = True
        else:
            self.engine_wait, self.engine_warned = 0.0, False
        self.update_engine_room(dt, eng)
        if (w.destination is not None or w.dock_state is not None) and not helm_ok:
            self.no_helm_t += dt
            if self.no_helm_t > 4.0 and not self.helm_warned:
                self.crew.say("Nobody at the helm. We're losing way.")
                self.helm_warned = True
        elif helm_ok:
            self.no_helm_t, self.helm_warned = 0.0, False
        self.time_since_wave_msg += dt
        w.brake = self.crew.alarm_target is not None
        self.weather.update(dt)
        self._update_market_surge(dt)
        self._update_radio(dt)
        engine_ok = bool(self.engine_ok and self.fuel > 0)
        watch_skill = (0.75 + 0.25 * eng.skill) if eng is not None else 1.0
        if self.tow_transit_active:
            # Suppress ordinary propulsion/drift while the external tug controls the tow.
            w.speed = 0.0
            w.throttle = 0.0
            w.destination = None
            w.dock_state = None
        w.update(dt, keys, helm_ok, engine_ok,
                 self.engine_power * watch_skill if engine_ok else 0.0)
        self._update_tow_transit(dt)
        self._update_tow_escort(dt)
        self._update_v13_2_traffic(dt)
        self._sync_tow_escort_world_entity()
        # Arrow keys pressed with an empty wheelhouse: tell the player why nothing happens.
        self.arrow_helm_warn_t = max(0.0, self.arrow_helm_warn_t - dt)
        manual_keys = any(keys[k] for k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN))
        if manual_keys and not helm_ok and self.arrow_helm_warn_t <= 0.0:
            self.crew.say("Helm: Wheelhouse is unmanned — the captain or relief helmsman must take the wheel.")
            self.arrow_helm_warn_t = 6.0
        self.ship.slope = self.ship.slope.lerp(w.deck_slope(), 1 - math.exp(-5 * dt))
        self._apply_hull_strikes(dt)
        self.ship.update_water(dt, self)
        self._update_flood_alerts(dt)
        # Bucket work is assigned to real crew tasks; water is only thrown once hands reach the stern.
        self._update_bucket_chain(dt)
        wet_goal = 0.85 * self.weather.rain ** 0.7                    # rain soaks the planking (drizzle: damp, downpour: wet)
        if self.ship.wet < wet_goal:
            self.ship.wet = min(wet_goal, self.ship.wet + (0.02 + 0.04 * self.weather.rain) * dt)
        sl = self.ship.slope
        tgt_roll = sl.y * (1.0 + 0.8 * self.ship.flood) + self.ship.list_trim   # deck water: worse roll, plus a static list
        stiffness = 9.0 * FloodingModel.stability(self.ship)  # free-surface water softens her righting
        self.roll_v += (stiffness * (tgt_roll - self.roll) - 1.6 * self.roll_v) * dt
        self.roll += self.roll_v * dt
        self.rock_ang = 0.045 * self.roll + 0.012 * sl.x      # roll + a bit of pitch, as sway
        self.rock_shift = V(sl.x, sl.y) * 5.0
        self.line.update(dt, keys)
        self._update_follow_birds(dt)
        self._update_seabird_flocks(dt)
        self._logistics(dt)
        self._update_tow_diagnostics(dt)
        self._sea_hazards(dt)
        for sp in self.splats:                                  # blood spots fly, settle and fade
            sp[0] += sp[1] * dt
            sp[1] *= math.exp(-6.0 * dt)
            sp[2] += dt
            if self.ship.wash_push(sp[0]).length() > 0.05:      # a wave sweeps them away
                sp[2] += 6.0 * dt
        self.splats = [sp for sp in self.splats if sp[2] < sp[3] and self.ship.on_deck(sp[0])]
        self.table_blood = max(0.0, self.table_blood - 0.012 * dt)
        # the catch warms up on deck, cools in the hold, and loses quality as it goes
        self._update_deck_fish(dt)
        for it in self.items:
            it.fish.tick(dt, self.weather.air_temp(), False, on_deck=True)
        for c in self.table.raw:
            c.tick(dt, self.weather.air_temp(), False)
        for sl in self.sailors:
            for c in sl.carry:
                c.tick(dt, self.weather.air_temp(), False)
        iced = self.ice > 0
        for c in self.hold:
            c.tick(dt, self.hold_temp, iced, True)
        self._ice(dt)
        # wages accrue while a hand is alive; the harbour heals and pays
        for s in self.sailors:
            if s.mode in (Sailor.ABOARD, Sailor.SWIMMING, Sailor.CLIMBING, Sailor.RESCUE_BOAT):
                s.owed += s.wage / 1200.0 * dt
        at_quay = self.docked()
        if w.dist() > 1100:
            self.arrival_done = False
        self.dock_t = self.dock_t + dt if at_quay else 0.0
        if at_quay:
            for s in self.sailors:
                if s.mode == Sailor.ABOARD:
                    s.health = min(1.0, s.health + 0.03 * dt)
                    s.fatigue = max(s.fatigue - 0.004 * dt, 0.0)
            if not self.arrival_done and self.dock_t > 3.0:
                self.settle()
        for p in self.patches:
            p.update(dt)
            push = self.ship.wash_push(p.pos)               # a wave sluices the slime away
            if push.length() > 0.05:
                p.cleaning += 0.6 * push.length() * dt
        self.patches = [p for p in self.patches if p.age < p.life and p.cleaning < 1.0]
        for it in self.items:                               # ... and can carry loose fish with it
            push = self.ship.wash_push(it.pos)
            if push.length() > 0.05:
                it.pos += push * 160 * dt
        lost = [it for it in self.items if not self.ship.on_deck(it.pos)]
        for it in lost:
            self.crew.say("A %s slid over the side!" % it.fish.name)
        self.items = [it for it in self.items if it not in lost]
        for s in self.sailors:
            s.update(dt)
        self._update_hotspot_lookouts(dt)
        self._update_rescue_operation(dt)
        # Falls are not a shared omniscient event: rescue begins only after a real sighting.
        self.crew.update_sightings(dt)
        self.separate_crew()
        self._update_muster(dt)
        self.sailors = [s for s in self.sailors if not (s.mode == Sailor.DEAD and s.dead_t > 30)]
        # exhaust from the funnel while the engine is turning over
        self.smoke_t -= dt
        if self._engine_on and self.smoke_t <= 0:
            self.smoke_t = 0.12
            wx, wy, ww, wh = self.ship.wheelhouse
            self.smoke.append([V(wx + ww * 0.28, 0), V(-40 - 0.25 * w.speed, random.uniform(-15, 15)), 0.0])
        for p in self.smoke:
            p[0] += p[1] * dt
            p[2] += dt
        self.smoke = [p for p in self.smoke if p[2] < 2.5]

    # --- drawing
    def draw_speech_bubbles(self):
        """Draw active sailor speech above the characters, not in the old corner log."""
        font = self.font
        max_text_width = min(238, max(120, W - 32))
        pad_x, pad_y = 9, 6
        line_h = font.get_linesize()

        for sailor in self.sailors:
            if (not sailor.speech_bubble or sailor.speech_t <= 0
                    or sailor.mode in (Sailor.DEAD, Sailor.RESCUE_BOAT)):
                continue

            # Swimmers live in the water/world frame; crew aboard the ship use the rocking ship frame.
            anchor = self.S(sailor.pos) if sailor.mode == Sailor.SWIMMING else self.SS(sailor.pos)
            words = sailor.speech_bubble.split()
            lines, current = [], ""
            for word in words:
                candidate = word if not current else current + " " + word
                if current and font.size(candidate)[0] > max_text_width - 2 * pad_x:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                lines.append(current)
            if not lines:
                continue

            content_w = max(font.size(line)[0] for line in lines)
            bw = min(max_text_width, content_w + 2 * pad_x)
            bh = len(lines) * line_h + 2 * pad_y
            bx = int(clamp(anchor.x - bw / 2, 5, W - bw - 5))
            # Leave a little gap above the sailor's head and point the tail back to them.
            tail_base_y = int(anchor.y - max(28, 31 * sailor.scale * self.zoom))
            by = max(5, tail_base_y - bh - 8)
            tail_x = int(clamp(anchor.x, bx + 12, bx + bw - 12))
            tail_bottom = by + bh

            if "???" in sailor.speech_bubble:
                edge = (52, 116, 160)
            elif "!!!" in sailor.speech_bubble:
                edge = (177, 64, 43)
            else:
                edge = (73, 67, 53)

            # Draw the tail first, so the bubble body neatly covers its base.
            pygame.draw.polygon(self.screen, edge, [
                (tail_x - 7, tail_bottom - 1), (tail_x + 7, tail_bottom - 1),
                (int(anchor.x), tail_base_y + 7)
            ])
            pygame.draw.polygon(self.screen, (248, 244, 226), [
                (tail_x - 5, tail_bottom - 2), (tail_x + 5, tail_bottom - 2),
                (int(anchor.x), tail_base_y + 5)
            ])
            pygame.draw.rect(self.screen, (25, 24, 22), (bx + 2, by + 2, bw, bh), border_radius=7)
            pygame.draw.rect(self.screen, (248, 244, 226), (bx, by, bw, bh), border_radius=7)
            pygame.draw.rect(self.screen, edge, (bx, by, bw, bh), width=2, border_radius=7)
            for i, line in enumerate(lines):
                image = font.render(line, True, (35, 32, 27))
                self.screen.blit(image, (bx + pad_x, by + pad_y + i * line_h))

    def draw_visibility_cones(self, level):
        """Draw weather-limited forward view cones for sailors on the viewed level."""
        if level == Level.BELOW:
            return
        overlay = self.ov_d
        for sailor in self.sailors:
            if (sailor.mode != Sailor.ABOARD or sailor.level != level
                    or sailor.ladder is not None):
                continue
            origin = V(sailor.pos)
            radius = sailor.vision_range()
            start = sailor.facing - Sailor.VIEW_HALF_ANGLE
            end = sailor.facing + Sailor.VIEW_HALF_ANGLE
            segments = 18
            local_points = [origin]
            for i in range(segments + 1):
                a = start + (end - start) * i / segments
                local_points.append(origin + V(math.cos(a), math.sin(a)) * radius)
            points = [self.SS(p) for p in local_points]
            if len(points) < 3:
                continue
            if sailor.selected:
                fill, edge = (68, 190, 238, 31), (75, 205, 255, 95)
            else:
                fill, edge = (68, 165, 210, 13), (75, 185, 225, 38)
            pygame.draw.polygon(overlay, fill, points)
            pygame.draw.lines(overlay, edge, False, points[1:], max(1, int(self.zoom)))
            pygame.draw.line(overlay, edge, points[0], points[1], max(1, int(self.zoom)))
            pygame.draw.line(overlay, edge, points[0], points[-1], max(1, int(self.zoom)))
        self.screen.blit(overlay, (0, 0))
        overlay.fill((0, 0, 0, 0))

    def draw_radio_bubble(self):
        """Draw a readable coast-station speech bubble even when the operator is off-screen."""
        if not self.radio_bubble_text or self.radio_bubble_t <= 0:
            return
        font = self.font
        max_w = min(560, max(260, W - 36))
        pad_x, pad_y = 14, 9
        line_h = font.get_linesize()
        words, lines, current = self.radio_bubble_text.split(), [], ""
        for word in words:
            candidate = word if not current else current + " " + word
            if current and font.size(candidate)[0] > max_w - 2 * pad_x:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        lines = lines[:5]
        if not lines:
            return
        content_w = max(font.size(line)[0] for line in lines)
        width = min(max_w, content_w + 2 * pad_x)
        header_h = line_h + 8
        height = header_h + len(lines) * line_h + 2 * pad_y + 3
        x = (W - width) // 2
        y = 14
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (12, 23, 30), rect, border_radius=10)
        pygame.draw.rect(self.screen, (218, 185, 105), rect, width=2, border_radius=10)
        head = pygame.Rect(x + 2, y + 2, width - 4, header_h + 2)
        pygame.draw.rect(self.screen, (36, 61, 70), head, border_radius=8)
        label = font.render("RADIO  •  %s  •  2182 kHz" % self.radio_bubble_speaker, True, (247, 222, 160))
        self.screen.blit(label, (x + pad_x, y + 5))
        for i, line in enumerate(lines):
            rendered = font.render(line, True, (246, 244, 229))
            self.screen.blit(rendered, (x + pad_x, y + header_h + pad_y + i * line_h))
        # Small tail to make this read as dialogue, not a status card.
        mid = W // 2
        pygame.draw.polygon(self.screen, (12, 23, 30), [(mid - 8, y + height - 1),
                                                        (mid + 8, y + height - 1),
                                                        (mid, y + height + 9)])

    def _hotspot_lookout_comment(self, sailor, spot):
        """Give a single useful spoken report when a crew lookout becomes confident."""
        species = str(spot.species).replace("_", " ")
        if sailor.skill < 0.35:
            line = "%s: Birds working over there." % sailor.name
        elif sailor.skill < 0.65:
            line = "%s: Looks like %s under those birds." % (sailor.name, species)
        elif spot.species == "mixed":
            line = "%s: Mixed feed under the flock. Could be worth a set." % sailor.name
        else:
            line = "%s: %s on the birds. Line's going in here." % (sailor.name, species.title())
        self.crew.say(line)

    def _record_gut_book_detection(self, sailor, spot):
        """Record the first confident crew plot of a school as a durable session memory."""
        if getattr(spot, "gut_book_entry_id", None) is not None:
            return next((entry for entry in self.gut_book_entries
                         if entry.entry_id == spot.gut_book_entry_id), None)
        stamp = self._log_stamp()
        x, y = believed_chart_position(spot.pos, self.world.position_error, self.world.scale)
        entry = GutBookEntry(
            entry_id=self.next_gut_book_id,
            date=stamp["date"], clock=stamp["clock"], elapsed=float(self.world.time),
            sailor=str(sailor.name), skill=float(sailor.skill),
            species_guess=str(spot.species), x=x, y=y,
            confidence=float(clamp(sailor.gut_confidence, 0.0, 1.0)),
            strength=float(clamp(spot.strength_now, 0.0, 1.0)), hotspot_ref=spot,
        )
        self.next_gut_book_id += 1
        spot.gut_book_entry_id = entry.entry_id
        self.gut_book_entries.append(entry)
        limit = max(1, int(getattr(self, "gut_book_entry_limit", MAX_GUT_BOOK_ENTRIES)))
        del self.gut_book_entries[:-limit]
        self.record_log_entry(
            "Gut book: %s logged a %s lead at chart position X%+.0f Y%+.0f." %
            (sailor.name, str(spot.species).replace("_", " "), x, y)
        )
        return entry

    def _update_hotspot_lookouts(self, dt):
        """Crew-dependent tier-two discovery. Physical cues themselves need no lookout."""
        w = self.world
        visibility_km = self.weather.visibility_km()
        daylight = w.daylight()
        live_spots = set(id(spot) for spot in w.hotspots)
        for sailor in self.sailors:
            best = None
            best_score = -1.0
            if (sailor.mode == Sailor.ABOARD and sailor.level == Level.MAIN
                    and sailor.ladder is None and sailor.health > 0.0):
                detect_range = lookout_detection_range(sailor.skill, visibility_km, daylight)
                for spot in w.hotspots:
                    strength = clamp(spot.strength_now, 0.0, 1.0)
                    if strength < 0.15 or detect_range <= 0.0:
                        continue
                    target = w.deck_of(V(spot.x, spot.y))
                    to = target - sailor.pos
                    distance = to.length()
                    if distance > detect_range or distance < 1.0:
                        continue
                    bearing = math.atan2(to.y, to.x)
                    difference = abs((bearing - sailor.facing + math.pi) % TAU - math.pi)
                    if difference > math.pi * 0.5:
                        continue
                    score = strength * (1.0 - distance / max(1.0, detect_range))
                    if score > best_score:
                        best, best_score = spot, score
            if best is None:
                if sailor.gut_spot is not None and id(sailor.gut_spot) not in live_spots:
                    sailor.gut_spot, sailor.gut_confidence = None, 0.0
                else:
                    sailor.gut_confidence = max(0.0, sailor.gut_confidence - max(0.0, dt) * 0.10)
                    if sailor.gut_confidence <= 0.0:
                        sailor.gut_spot = None
                continue
            if best is not sailor.gut_spot:
                sailor.gut_spot = best
                sailor.gut_confidence = 0.0
                continue
            old_confidence = sailor.gut_confidence
            sailor.gut_confidence = min(1.0, old_confidence + max(0.0, dt) * lookout_confidence_rate(sailor.skill))
            if old_confidence < GUT_BOOK_CONFIDENCE_THRESHOLD <= sailor.gut_confidence and best.detected_by is None:
                best.detected_by = sailor
                best.detected_at = w.time
                self._record_gut_book_detection(sailor, best)
                self._hotspot_lookout_comment(sailor, best)

    def _update_follow_birds(self, dt):
        """Move a small, persistent flock behind the stern during active fishing only."""
        target_count = follow_bird_count(self.line.phase, self.world.daylight(), self.weather.storm)
        w = self.world
        while len(self.follow_birds) < target_count:
            i = len(self.follow_birds)
            local = V(-self.ship.length * 0.70 - random.uniform(20.0, 100.0),
                      random.uniform(-95.0, 95.0))
            self.follow_birds.append(FollowBird(w.world_of(local)))
        while len(self.follow_birds) > target_count:
            self.follow_birds.pop()
        if not self.follow_birds:
            return
        ship_velocity = V(1, 0).rotate_rad(w.heading) * w.speed
        for i, bird in enumerate(self.follow_birds):
            side = ((i % 7) - 3) * 25.0
            stern_offset = V(-self.ship.length * (0.66 + 0.04 * (i % 3)), side + 12.0 * math.sin(bird.flutter))
            anchor = w.world_of(stern_offset)
            correction = anchor - bird.pos
            if correction.length() > 180.0:
                correction.scale_to_length(180.0)
            desired_velocity = ship_velocity + correction * 0.85
            bird.vel = bird.vel.lerp(desired_velocity, 1.0 - math.exp(-1.8 * max(0.0, dt)))
            bird.pos += bird.vel * max(0.0, dt)
            bird.flutter += max(0.0, dt) * (7.0 + 0.35 * (i % 5))
            bird.dive_t = max(0.0, bird.dive_t - max(0.0, dt))
            if bird.dive_t <= 0.0 and self.line.phase == Longline.HAULING:
                bird.dive_t = random.uniform(3.0, 8.0)

    def _update_seabird_flocks(self, dt):
        """Keep one flight-modelled flock per live school; a school's end releases its flock."""
        w, wx = self.world, self.weather
        wind = (math.cos(wx.wind_dir) * wx.wind * 14.0, math.sin(wx.wind_dir) * wx.wind * 14.0)
        live = {}
        for spot in w.hotspots:
            flock = self.seabird_flocks.get(id(spot))
            if flock is None or flock.spot is not spot:
                flock = SeabirdFlock(seed=int(abs(spot.phase) * 1000.0) & 0xFFFFFF)
                flock.spot = spot
            strength = clamp(spot.strength_now, 0.0, 1.0)
            flock.update(dt, spot.x, spot.y, spot.radius * 0.30, strength,
                         working_bird_count(strength), wind)
            live[id(spot)] = flock
        self.seabird_flocks = live

    def draw_follow_birds(self):
        """Dark stern-following shearwaters, drawn top-down: distinct from the pale gulls working a school."""
        if not self.follow_birds:
            return
        zoom_factor = math.sqrt(max(0.01, self.zoom) / 0.6)
        half_span = max(7.0, min(17.0, 10.0 * zoom_factor))
        for i, bird in enumerate(self.follow_birds):
            p = V(self.S(self.world.deck_of(bird.pos)))
            if not (-half_span - 4 <= p.x <= W + half_span + 4
                    and -half_span - 4 <= p.y <= H + half_span + 4):
                continue
            heading = (math.atan2(bird.vel.y, bird.vel.x) if bird.vel.length() > 6.0 else self.world.heading)
            cycle = bird.flutter / TAU
            soaring = (int(cycle) + i) % 3 == 0                     # every third wing-beat cycle is a glide
            frame = FRAME_GLIDE if soaring else int((cycle % 1.0) * FLAP_FRAMES) % FLAP_FRAMES
            draw_seabird(self.screen, "shearwater", (p.x, p.y), heading - self.world.heading,
                         half_span, frame)

    def draw_hotspot_cues(self):
        """Tier-one physical signs are always discoverable without a crew marker."""
        overlay = self.hotspot_overlay
        overlay.fill((0, 0, 0, 0))
        if not self.world.hotspots:
            return

        daylight = self.world.daylight()
        weather_visibility = clamp(1.0 - 0.48 * self.weather.fog - 0.16 * self.weather.rain, 0.28, 1.0)
        bird_visibility = clamp(0.25 + 0.80 * daylight, 0.25, 1.0) * weather_visibility
        for spot in self.world.hotspots:
            strength = clamp(spot.strength_now, 0.0, 1.0)
            if strength < 0.08:
                continue
            center = V(self.S(self.world.deck_of(V(spot.x, spot.y))))
            # Cue radius extends beyond the tint so the outermost rings/debris remain visible at screen edges.
            render_extent = min(max(4, int(spot.radius * self.zoom * 0.82)), int(math.hypot(W, H) * 0.72))
            radius = min(max(4, int(spot.radius * self.zoom * 0.30)), int(min(W, H) * 0.30))
            margin = 24
            if (center.x < -render_extent - margin or center.x > W + render_extent + margin
                    or center.y < -render_extent - margin or center.y > H + render_extent + margin):
                continue
            cx, cy = round(center.x), round(center.y)

            # 1) Three low-alpha concentric green -> teal -> blue discs.
            strength_vis = strength * weather_visibility
            tint_radii = (radius, int(radius * 0.64), int(radius * 0.32))
            tint_cols = ((42, 127, 86), (39, 137, 123), (39, 103, 160))
            tint_alphas = (int(7 + 8 * strength_vis), int(8 + 10 * strength_vis), int(9 + 12 * strength_vis))
            for tint_radius, tint_col, tint_alpha in zip(tint_radii, tint_cols, tint_alphas):
                pygame.draw.circle(overlay, tint_col + (tint_alpha,), (cx, cy), max(2, tint_radius))

            # 1b) A smooth, pale slick drifts downwind of the feeding fish (oil from the baitfish).
            if slick_visible(strength):
                wind_a = float(self.weather.wind_dir) - self.world.heading
                wu, wv = V(math.cos(wind_a), math.sin(wind_a)), V(-math.sin(wind_a), math.cos(wind_a))
                slick_c = center + wu * radius * 0.55
                for scale_l, scale_w, a_base in ((1.0, 1.0, 12), (0.72, 0.62, 14)):
                    pts = []
                    for k in range(18):
                        t = k / 18.0 * TAU
                        pts.append((round(slick_c.x + wu.x * math.cos(t) * radius * 0.95 * scale_l + wv.x * math.sin(t) * radius * 0.34 * scale_w),
                                    round(slick_c.y + wu.y * math.cos(t) * radius * 0.95 * scale_l + wv.y * math.sin(t) * radius * 0.34 * scale_w)))
                    pygame.draw.polygon(overlay, (206, 230, 232, int(a_base * (0.4 + 0.6 * strength_vis))), pts)
                for off in (-0.16, 0.0, 0.17):
                    s0 = slick_c + wv * radius * off - wu * radius * 0.8
                    s1 = slick_c + wv * radius * off + wu * radius * 0.8
                    pygame.draw.line(overlay, (226, 242, 244, int(34 * strength_vis)), (round(s0.x), round(s0.y)),
                                     (round(s1.x), round(s1.y)), max(1, int(1.6 * self.zoom)))

            # 2) Flotsam clusters near the centre, and vanishes below strength 0.3.
            if flotsam_visible(strength):
                debris_count = 4 + int(7 * strength)
                for i in range(debris_count):
                    angle = spot.phase * 0.7 + i * 2.399963229728653
                    frac = 0.06 + 0.22 * (0.5 + 0.5 * math.sin(spot.phase + i * 4.17))
                    world_pos = V(spot.x, spot.y) + V(math.cos(angle), math.sin(angle)) * spot.radius * frac
                    px = V(self.S(self.world.deck_of(world_pos)))
                    size = max(2, int((2.0 + 2.2 * strength) * self.zoom))
                    if -size <= px.x <= W + size and -size <= px.y <= H + size:
                        col = mix((83, 73, 50), (147, 119, 72), strength)
                        col = mix((35, 40, 42), col, weather_visibility)
                        points = [(round(px.x), round(px.y - size)),
                                  (round(px.x + size * 1.3), round(px.y - size * 0.15)),
                                  (round(px.x + size * 0.2), round(px.y + size)),
                                  (round(px.x - size), round(px.y + size * 0.2))]
                        pygame.draw.polygon(overlay, col + (int(115 + 85 * strength),), points)

            # 3) Expanding white rings stop when strength falls below 0.2.
            if ripples_visible(strength):
                ripple_count = 3 + int(7 * strength)
                for i in range(ripple_count):
                    angle = spot.phase + i * 2.399963229728653
                    frac = 0.12 + 0.68 * ((i * 0.38196601125 + 0.13) % 1.0)
                    world_pos = V(spot.x, spot.y) + V(math.cos(angle), math.sin(angle)) * spot.radius * frac
                    px = V(self.S(self.world.deck_of(world_pos)))
                    progress = (self.world.time * (0.34 + 0.03 * (i % 3)) + spot.phase + i * 0.23) % 1.0
                    rr = max(3, int((5.0 + 15.0 * progress) * self.zoom))
                    alpha = int(125 * (1.0 - progress) * strength * weather_visibility)
                    if alpha > 4 and -rr <= px.x <= W + rr and -rr <= px.y <= H + rr:
                        pygame.draw.circle(overlay, (226, 240, 237, alpha), (round(px.x), round(px.y)), rr,
                                           max(1, int(1.8 * self.zoom)))

            # 3b) Nervous water: baitfish flicker at the surface as tiny silver flecks that come and go.
            fleck_world = spot.radius * 0.30
            for i in range(baitfish_fleck_count(strength)):
                period = 0.7 + 1.1 * hash01(i, 11, 1)
                phase_t = self.world.time / period + hash01(i, 12, 2) * 7.0
                cycle, prog = int(phase_t // 1), phase_t % 1.0
                if prog > 0.34:
                    continue
                a_f = TAU * hash01(i, cycle, 3)
                d_f = math.sqrt(hash01(i, cycle, 4)) * fleck_world
                fp = V(self.S(self.world.deck_of(V(spot.x, spot.y) + V(math.cos(a_f), math.sin(a_f)) * d_f)))
                if not (-12 <= fp.x <= W + 12 and -12 <= fp.y <= H + 12):
                    continue
                v = V(math.cos(TAU * hash01(i, cycle, 6)), math.sin(TAU * hash01(i, cycle, 6))) \
                    * (5.0 + 7.0 * hash01(i, cycle, 5)) * self.zoom * 0.5
                pygame.draw.line(overlay, (232, 244, 246, int(190 * (1.0 - prog / 0.34) * strength_vis)),
                                 (round(fp.x - v.x), round(fp.y - v.y)), (round(fp.x + v.x), round(fp.y + v.y)),
                                 max(1, int(1.6 * self.zoom)))

            # 3c) Fish breaking the surface: a short-lived white boil with an expanding ring.
            for i in range(boil_count(strength)):
                period = 2.4 + 2.2 * hash01(i, 21, 1)
                phase_t = self.world.time / period + hash01(i, 22, 2) * 9.0
                cycle, prog = int(phase_t // 1), phase_t % 1.0
                if prog > 0.55:
                    continue
                t_b = prog / 0.55
                a_b = TAU * hash01(i, cycle, 7)
                d_b = math.sqrt(hash01(i, cycle, 8)) * fleck_world * 0.9
                bp = V(self.S(self.world.deck_of(V(spot.x, spot.y) + V(math.cos(a_b), math.sin(a_b)) * d_b)))
                alpha_b = int(150 * (1.0 - t_b) * strength_vis)
                rr_b = max(3, int((7.0 + 30.0 * t_b) * self.zoom))
                if alpha_b > 4 and -rr_b <= bp.x <= W + rr_b and -rr_b <= bp.y <= H + rr_b:
                    pygame.draw.circle(overlay, (236, 246, 244, alpha_b), (round(bp.x), round(bp.y)), rr_b,
                                       max(1, int(2.2 * self.zoom)))
                    if t_b < 0.4:
                        pygame.draw.circle(overlay, (250, 253, 252, int(alpha_b * 0.8 * (1.0 - t_b / 0.4))),
                                           (round(bp.x), round(bp.y)), max(2, int((5.0 + 6.0 * t_b) * self.zoom)))

            # 3d) Splashes left by diving birds: white water and flung spray over the boil.
            flock = self.seabird_flocks.get(id(spot))
            if flock is not None and flock.spot is spot:
                for sp in flock.splashes:
                    sx = V(self.S(self.world.deck_of(V(sp.x, sp.y))))
                    t_s = sp.progress
                    rr_s = max(3, int((8.0 + 46.0 * t_s) * sp.size * self.zoom))
                    if not (-rr_s <= sx.x <= W + rr_s and -rr_s <= sx.y <= H + rr_s):
                        continue
                    alpha_s = int(170 * (1.0 - t_s) ** 1.3 * weather_visibility)
                    pygame.draw.circle(overlay, (240, 250, 248, alpha_s), (round(sx.x), round(sx.y)), rr_s,
                                       max(1, int(2.2 * self.zoom)))
                    if t_s < 0.35:
                        pygame.draw.circle(overlay, (252, 255, 255, int(alpha_s * (1.0 - t_s / 0.35))),
                                           (round(sx.x), round(sx.y)), max(2, int((6.0 + 8.0 * t_s) * sp.size * self.zoom)))
                        for j in range(6):
                            a_j = TAU * hash01(sp.seed % 997, j, 9)
                            d_j = (6.0 + 38.0 * t_s) * sp.size * self.zoom * (0.6 + 0.8 * hash01(sp.seed % 991, j, 10))
                            pygame.draw.circle(overlay, (250, 254, 254, int(alpha_s * 0.8)),
                                               (round(sx.x + math.cos(a_j) * d_j), round(sx.y + math.sin(a_j) * d_j)),
                                               max(1, int(1.8 * self.zoom)))

        self.screen.blit(overlay, (0, 0))

        # 4) Working seabirds. Each bird flies (SeabirdFlock): wheeling above the school, banking, gliding,
        # then folding its wings and plunging onto the boil. Strong schools hold dense, tight flocks;
        # fading ones fewer, wider-ranging and fainter birds that peel away and leave.
        flying = []
        for spot in self.world.hotspots:
            strength = clamp(spot.strength_now, 0.0, 1.0)
            bird_count = working_bird_count(strength)
            flock = self.seabird_flocks.get(id(spot))
            if flock is None or flock.spot is not spot or (not bird_count and not flock.birds):
                continue
            half_span = working_bird_half_span(strength, self.zoom)
            alpha = int(255 * clamp(0.30 + 0.70 * bird_visibility, 0.30, 1.0) * (0.60 + 0.40 * strength))
            for bird in flock.birds:
                hs = half_span * (0.90 + 0.15 * bird.alt)
                p = V(self.S(self.world.deck_of(V(bird.x, bird.y))))
                if not (-hs - 8 <= p.x <= W + hs + 8 and -hs - 8 <= p.y <= H + hs + 8):
                    continue
                flying.append((p, bird, hs, alpha))
        if flying:
            overlay.fill((0, 0, 0, 0))
            for p, bird, hs, _alpha in flying:      # soft shadows on the water, further off when higher
                off = (3.0 + 14.0 * bird.alt) * math.sqrt(max(0.01, self.zoom) / 0.6)
                sw, sh = max(4, int(hs * 1.2)), max(3, int(hs * 0.45))
                pygame.draw.ellipse(overlay, (8, 22, 32, int(52 * (1.0 - 0.5 * bird.alt))),
                                    pygame.Rect(round(p.x + off * 0.7 - sw / 2), round(p.y + off - sh / 2), sw, sh))
            self.screen.blit(overlay, (0, 0))
            overlay.fill((0, 0, 0, 0))
            for p, bird, hs, alpha in flying:
                draw_seabird(self.screen, "gull", (p.x, p.y), bird.heading - self.world.heading,
                             hs, sprite_frame(bird), bird.bank, alpha)

    def draw_hotspot_lookout_markers(self):
        """Draw one confidence-gated diamond per detected school, or a directional edge arrow."""
        overlay = self.ov_d
        overlay.fill((0, 0, 0, 0))
        margin = 46
        for spot in self.world.hotspots:
            confidence = max((s.gut_confidence for s in self.sailors
                              if s.gut_spot is spot and s.mode == Sailor.ABOARD and s.level == Level.MAIN
                              and s.ladder is None), default=0.0)
            if confidence < 0.5:
                continue
            center = V(self.S(self.world.deck_of(V(spot.x, spot.y))))
            pulse = 0.76 + 0.24 * math.sin(self.world.time * 2.5 + spot.phase)
            alpha = int(clamp((100 + 150 * confidence) * pulse, 60, 245))
            fill = (255, 239, 151, alpha)
            edge = (111, 86, 33, min(255, alpha + 10))
            if margin <= center.x <= W - margin and margin <= center.y <= H - margin:
                size = 10.0 + 4.0 * pulse
                pts = [(round(center.x), round(center.y - size)),
                       (round(center.x + size), round(center.y)),
                       (round(center.x), round(center.y + size)),
                       (round(center.x - size), round(center.y))]
                pygame.draw.polygon(overlay, fill, pts)
                pygame.draw.polygon(overlay, edge, pts, max(2, int(2.0 * self.zoom)))
                pygame.draw.circle(overlay, (255, 248, 208, alpha), (round(center.x), round(center.y)),
                                   max(2, int(size * 0.22)), 1)
            else:
                ex, ey = screen_edge_intersection(W, H, (center.x, center.y), margin)
                angle = math.atan2(center.y - CENTER.y, center.x - CENTER.x)
                origin = V(ex, ey)
                size = 15.0
                tip = origin + V(size, 0).rotate_rad(angle)
                rear = origin + V(-size * 0.72, 0).rotate_rad(angle)
                left = rear + V(0, -size * 0.66).rotate_rad(angle)
                right = rear + V(0, size * 0.66).rotate_rad(angle)
                pts = [(round(tip.x), round(tip.y)), (round(left.x), round(left.y)), (round(right.x), round(right.y))]
                pygame.draw.polygon(overlay, fill, pts)
                pygame.draw.polygon(overlay, edge, pts, 2)
                pygame.draw.circle(overlay, fill, (round(ex), round(ey)), 3)
        self.screen.blit(overlay, (0, 0))
        overlay.fill((0, 0, 0, 0))

    def _draw_ship_cached(self):
        """Rasterize the mostly-static deck artwork at 30 Hz and blit only its bounds."""
        elapsed = min(0.10, max(0.0, self.clock.get_time() / 1000.0))
        age = float(getattr(self, "_ship_static_cache_age", 1.0)) + elapsed
        size = self.screen.get_size()
        table_state = tuple((c.name, round(c.quality, 1), bool(c.bled), bool(c.gutted))
                            for c in self.table.raw)
        boat = self.rescue_boat_state
        lifeboat_visible = boat is None or boat.get("phase") == "launching"
        state = (size, round(self.zoom, 4), bool(self.engine_ok), bool(self.engine_running()),
                 int(self.ice), len(self.hold), round(self.table_blood, 1), table_state,
                 lifeboat_visible)
        cache = getattr(self, "_ship_static_cache", None)
        if (cache is None or self._ship_static_cache_rect is None
                or state != getattr(self, "_ship_static_cache_state", None)
                or age >= self._ship_static_cache_interval):
            original_screen = self.screen
            target = getattr(self, "_ship_static_target_surface", None)
            if target is None or target.get_size() != size:
                target = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
                self._ship_static_target_surface = target
            target.fill((0, 0, 0, 0))
            self.screen = target
            try:
                self.ship.draw(self)
            finally:
                self.screen = original_screen
            # Ship artwork occupies only a part of the display. Crop the full
            # off-screen render before caching so each frame blends a small
            # transparent rectangle rather than a transparent full-screen image.
            hull_screen = [self.SS(point) for point in self.ship.hull]
            pad = max(20, int(38 * self.zoom + 12))
            left = max(0, int(math.floor(min(p.x for p in hull_screen))) - pad)
            top = max(0, int(math.floor(min(p.y for p in hull_screen))) - pad)
            right = min(size[0], int(math.ceil(max(p.x for p in hull_screen))) + pad)
            bottom = min(size[1], int(math.ceil(max(p.y for p in hull_screen))) + pad)
            rect = pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))
            cache = target.subsurface(rect).copy().convert_alpha()
            self._ship_static_cache = cache
            self._ship_static_cache_rect = rect
            self._ship_static_cache_state = state
            self._ship_static_cache_age = 0.0
        else:
            self._ship_static_cache_age = age
        self.screen.blit(self._ship_static_cache, self._ship_static_cache_rect.topleft)

    @staticmethod
    def _draw_dashed_screen_line(surface, start, end, color, width=2, dash=10, gap=6):
        a, b = V(start), V(end)
        delta = b - a
        length = delta.length()
        if length < 1.0:
            return
        direction = delta / length
        step = max(2.0, float(dash) + float(gap))
        offset = 0.0
        while offset < length:
            finish = min(length, offset + dash)
            pygame.draw.line(surface, color,
                             (int(a.x + direction.x * offset), int(a.y + direction.y * offset)),
                             (int(a.x + direction.x * finish), int(a.y + direction.y * finish)),
                             max(1, int(width)))
            offset += step

    def _draw_ocean_edge_marker(self, point, label, color):
        """Clamp an off-screen course point to the nearest visible edge with a direction arrow."""
        p = V(point)
        if 14 <= p.x <= W - 14 and 14 <= p.y <= H - 14:
            return False
        centre = V(CENTER)
        delta = p - centre
        if delta.length() < 1e-6:
            return False
        sx = (W * 0.5 - 24.0) / abs(delta.x) if abs(delta.x) > 1e-6 else float("inf")
        sy = (H * 0.5 - 24.0) / abs(delta.y) if abs(delta.y) > 1e-6 else float("inf")
        marker = centre + delta * max(0.0, min(sx, sy))
        direction = delta.normalize()
        side = V(-direction.y, direction.x)
        tip = marker + direction * 11.0
        base_a = marker - direction * 7.0 + side * 6.0
        base_b = marker - direction * 7.0 - side * 6.0
        pygame.draw.polygon(self.screen, color, [tip, base_a, base_b])
        pygame.draw.circle(self.screen, color, (int(marker.x), int(marker.y)), 11, 1)
        label_surf = self.chart_small_font.render(str(label), True, color)
        lx = int(clamp(marker.x + (10 if direction.x >= 0 else -label_surf.get_width() - 10), 2, W - label_surf.get_width() - 2))
        ly = int(clamp(marker.y + (8 if direction.y >= 0 else -label_surf.get_height() - 8), 2, H - label_surf.get_height() - 2))
        self.screen.blit(label_surf, (lx, ly))
        return True

    def draw_ocean_plot(self):
        """Show helm orders as a discreet instrument card, never as a line on the sea.

        The persistent route is still drawn on the chart table. In the ocean view,
        the skipper gets bearing/range/ETA/cross-track feedback and speech/log orders,
        but no supernatural glowing track, target rings, or predicted path painted on
        the actual water. Shift-drag preview is textual for the same immersion reason.
        """
        if self.view_level() != Level.MAIN or self.chart_open or self.notebook_open:
            return
        w = self.world
        if not (w.route_waypoints or w.ocean_quick_target is not None
                or (self.ocean_plot_drag_start is not None and self.ocean_plot_preview_world is not None)):
            return

        units_per_nm = world_units_per_nautical_mile(w.scale)
        speed_knots = max(0.7, 10.0 * max(w.speed, 175.0) / max(1.0, w.max_speed))
        title = "HELM ORDER"
        detail = ""
        foot = "COURSE MARKS ARE ON THE CHART (C)"
        if self.ocean_plot_drag_start is not None and self.ocean_plot_preview_world is not None:
            start, end = V(self.ocean_plot_drag_start), V(self.ocean_plot_preview_world)
            metrics = leg_metrics(start, end, position=start, speed_knots=speed_knots,
                                  units_per_nautical_mile=units_per_nm)
            nm = metrics["distance"] / units_per_nm
            eta = eta_minutes(metrics["distance"], speed_knots, units_per_nm)
            title = "PLOTTING LEG — RELEASE RIGHT BUTTON TO COMMIT"
            detail = "A→B  BRG %03.0f°  RANGE %.1f NM  ETA %s" % (
                metrics["bearing"], nm, "—" if eta is None else "%d MIN" % max(1, round(eta)))
            desired = heading_radians(w.ship_pos, end)
            if abs(shortest_angle(desired, w.heading)) > 1.25 and w.speed > 135.0:
                foot = "WIDE TURN AT THIS SPEED — EXPECT OVERSHOOT"
            else:
                foot = "NO LINE IS DRAWN ON THE WATER"
        elif w.ocean_quick_target is not None:
            target = V(w.ocean_quick_target)
            metrics = leg_metrics(w.ship_pos, target, position=w.ship_pos,
                                  speed_knots=speed_knots, units_per_nautical_mile=units_per_nm)
            nm = metrics["distance"] / units_per_nm
            eta = eta_minutes(metrics["distance"], speed_knots, units_per_nm)
            title = "QUICK STEER-TO"
            detail = "COME TO %03.0f°  RANGE %.1f NM  ETA %s" % (
                metrics["bearing"], nm, "—" if eta is None else "%d MIN" % max(1, round(eta)))
            foot = "ESC CANCELS COURSE  •  C OPENS THE CHART"
        elif w.route_waypoints:
            origin = V(w.route_origin) if w.route_origin is not None else V(w.believed_pos)
            target = V(w.route_waypoints[0])
            metrics = leg_metrics(origin, target, position=w.believed_pos,
                                  speed_knots=speed_knots, units_per_nautical_mile=units_per_nm)
            nm = metrics["distance"] / units_per_nm
            eta = eta_minutes(metrics["distance"], speed_knots, units_per_nm)
            xte = cross_track_error(w.believed_pos, origin, target) / max(1.0, w.scale)
            title = "PLOTTED COURSE  •  %d WAYPOINT(S) REMAIN" % len(w.route_waypoints)
            detail = "NEXT LEG %03.0f°  %.1f NM  ETA %s  XTE %+.0f" % (
                metrics["bearing"], nm, "—" if eta is None else "%d MIN" % max(1, round(eta)), xte)
            desired = heading_radians(w.ship_pos, target)
            if abs(shortest_angle(desired, w.heading)) > 1.25 and w.speed > 135.0:
                foot = "WIDE TURN / EXPECT OVERSHOOT  •  ESC CANCELS"
            else:
                foot = "TRACK IS A REFERENCE, NOT A RAIL  •  ESC CANCELS"

        lines = [title, detail, foot]
        rendered = [self.chart_small_font.render(line, True, color) for line, color in zip(
            lines, ((245, 223, 172), (239, 241, 226), (178, 196, 185)))]
        card_w = min(max(surf.get_width() for surf in rendered) + 22, max(220, W - 24))
        card_h = sum(surf.get_height() for surf in rendered) + 16
        card_x = int(clamp(CENTER.x - card_w / 2, 8, W - card_w - 8))
        card_y = 70
        panel = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        panel.fill((18, 29, 31, 218))
        pygame.draw.rect(panel, (163, 143, 102, 230), panel.get_rect(), 1)
        yy = 5
        for surf in rendered:
            panel.blit(surf, (11, yy))
            yy += surf.get_height()
        self.screen.blit(panel, (card_x, int(clamp(card_y, 8, H - card_h - 8))))

    def draw(self):
        self.world.draw(self)
        self.draw_hotspot_cues()
        self.draw_follow_birds()
        self.line.draw(self)
        self.draw_hotspot_lookout_markers()
        self.ov_d.fill((0, 0, 0, 0))
        for s in self.sailors:       # people in the water are under the hull
            if s.mode in (Sailor.SWIMMING, Sailor.DEAD):
                s.draw(self)
        self.screen.blit(self.ov_d, (0, 0))
        self.ov_d.fill((0, 0, 0, 0))
        self.draw_rescue_boat()       # water-side craft is drawn over the sea but underneath the ship
        self.draw_ai_traffic()        # v13.2.01: nearby scheduled traffic; not all fleet ships are full-AI/rendered
        self.draw_tow_escort()        # PLACE HOLDER SHIP — physical Coast Guard hull on the water
        self._draw_ship_cached()
        for p in self.patches:
            p.draw(self)
        for pos, vel, age, life, size in self.splats:
            a = clamp((life - age) / 6.0, 0.0, 1.0) * (0.95 if age > 0.4 else 0.8)
            pygame.draw.circle(self.ov_d, mix((200, 30, 30), (110, 22, 20), clamp(age / 40.0, 0.0, 1.0)) + (int(255 * a),),
                               self.SS(pos), max(1, int(size * self.zoom)))
        self.ship.draw_water(self)
        self.draw_tow_escort_towline()  # draw after sea wash so the working line stays legible
        for s in self.sailors:
            if s.mode == Sailor.ABOARD and s.level == Level.MAIN:
                s.shadow(self)
        self.screen.blit(self.ov_d, (0, 0))
        self.ov_d.fill((0, 0, 0, 0))
        vl = self.view_level()
        if vl != Level.MAIN:
            self.ship.draw_level_view(self, vl)
        # Field-of-view checks remain active for spotting events, but cones are hidden.
        self.draw_lifelines()
        if vl == Level.MAIN:
            for it in self.items:
                it.draw(self)
        for s in self.sailors:
            visible_on_cutaway = (vl == Level.WHEELHOUSE and s.level == Level.MAIN)
            if s.mode == Sailor.CLIMBING or (s.mode == Sailor.ABOARD and (s.level == vl or visible_on_cutaway)):
                s.draw(self)
            elif s.mode == Sailor.ABOARD:
                s.draw_faint(self)
        for pos, vel, age in self.smoke:
            a = 1 - age / 2.5
            pygame.draw.circle(self.ov_d, (170, 170, 170, int(110 * a)), self.SS(pos), max(2, int((10 + 28 * age / 2.5) * self.zoom)))
        self.screen.blit(self.ov_d, (0, 0))
        self.draw_weather()
        self.draw_night()
        self.draw_lightning()
        self.draw_ocean_plot()
        self.draw_speech_bubbles()
        self.draw_radio_bubble()
        self.draw_hud()
        self.draw_crew_report_panel()
        self.draw_tension()
        self.draw_gaff()
        if self.longline_minimap_debug:
            self.draw_longline_debug_minimap()
        # The old top-right line/depth graph is a debug view only (F10).
        if self.longline_minimap_debug:
            self.draw_profile()
        self.draw_crew_sheet()
        self.draw_auction_modal()
        if self.chart_open and not self.auction_active:
            self.draw_navigation_chart()
        if self.notebook_open and not self.auction_active:
            self.draw_notebook()
        self.draw_context_menu()
        self.draw_radio_ui()  # v13.2.02: draw modal radio above all other UI.

    def _notebook_set_section(self, section):
        self.notebook_section = int(clamp(section, 0, 4))
        self.notebook_page = 0

    def _notebook_page_capacity(self):
        return max(3, min(8, (H - 205) // 48))

    def _notebook_page_count(self):
        section = self.notebook_section
        if section in (0, 1, 4):
            entries = (self.crew_log_entries if section == 0 else
                       self.radio_log_entries if section == 1 else self.gut_book_entries)
            return max(1, int(math.ceil(len(entries) / float(self._notebook_page_capacity()))))
        if section == 3:
            return 20  # five-day forecast sheets, covering the next hundred game days
        # Calendar paging moves through months; there is no arbitrary real-world end date.
        return 240

    def _notebook_turn_page(self, step):
        count = self._notebook_page_count()
        self.notebook_page = int(clamp(self.notebook_page + int(step), 0, count - 1))

    @staticmethod
    def _month_offset(day, offset):
        month_index = (day.year * 12 + day.month - 1) + int(offset)
        year, month0 = divmod(month_index, 12)
        month = month0 + 1
        import calendar as _calendar
        from datetime import date as _date
        return _date(year, month, min(day.day, _calendar.monthrange(year, month)[1]))

    @staticmethod
    def _wrap_notebook_text(font, text, max_width):
        words, rows, current = str(text).split(), [], ""
        for word in words:
            candidate = word if not current else current + " " + word
            if current and font.size(candidate)[0] > max_width:
                rows.append(current)
                current = word
            else:
                current = candidate
        if current:
            rows.append(current)
        return rows or [""]

    def draw_notebook(self):
        """A chart-matching paper notebook with crew, radio, calendar, and forecast pages."""
        if not self.notebook_open:
            return
        dim = self._cached_panel_surface((W, H), (4, 11, 14, 220))
        self.screen.blit(dim, (0, 0))
        outer = pygame.Rect(18, 14, W - 36, H - 28)
        paper, ink, faded, rule, gold = (226, 215, 187), (65, 49, 33), (117, 93, 62), (177, 153, 118), (151, 109, 43)
        pygame.draw.rect(self.screen, paper, outer)
        pygame.draw.rect(self.screen, ink, outer, 2)
        pygame.draw.line(self.screen, faded, (outer.x + 8, outer.y + 65), (outer.right - 8, outer.y + 65), 1)
        title = self.chart_title_font.render("SHIP'S NOTEBOOK", True, ink)
        self.screen.blit(title, (outer.x + 16, outer.y + 8))
        subtitle = self.chart_small_font.render("NORTH PACIFIC FISHING VESSEL  •  1962  •  HAND-KEPT RECORD", True, faded)
        self.screen.blit(subtitle, (outer.x + 18, outer.y + 38))
        close_rect = pygame.Rect(outer.right - 104, outer.y + 10, 86, 26)
        pygame.draw.rect(self.screen, (211, 198, 168), close_rect)
        pygame.draw.rect(self.screen, ink, close_rect, 1)
        self.screen.blit(self.chart_small_font.render("CLOSE  F9", True, ink), (close_rect.x + 8, close_rect.y + 7))
        self.notebook_hitboxes = {"close": close_rect}

        rail = pygame.Rect(outer.x + 10, outer.y + 76, 145, outer.h - 128)
        pygame.draw.rect(self.screen, (215, 202, 171), rail)
        pygame.draw.rect(self.screen, faded, rail, 1)
        labels = ("CREW LOG", "RADIO LOG", "CALENDAR", "FORECAST", "GUT BOOK")
        for i, label in enumerate(labels):
            rect = pygame.Rect(rail.x + 6, rail.y + 8 + i * 36, rail.w - 12, 30)
            active = i == self.notebook_section
            pygame.draw.rect(self.screen, (238, 226, 195) if active else (205, 190, 159), rect)
            pygame.draw.rect(self.screen, gold if active else rule, rect, 2 if active else 1)
            self.screen.blit(self.chart_header_font.render(label, True, ink), (rect.x + 7, rect.y + 8))
            self.notebook_hitboxes["section_%d" % i] = rect
        rail_note_y = rail.y + 8 + len(labels) * 36 + 4
        notes = ("1–5  select", "TAB  next section", "← →  turn page", "ESC / F9 close")
        for i, line in enumerate(notes):
            self.screen.blit(self.chart_small_font.render(line, True, faded), (rail.x + 8, rail_note_y + i * 18))

        page_rect = pygame.Rect(rail.right + 12, outer.y + 76, outer.right - rail.right - 22, outer.h - 128)
        pygame.draw.rect(self.screen, (235, 226, 204), page_rect)
        pygame.draw.rect(self.screen, rule, page_rect, 1)
        pad_x, top = page_rect.x + 17, page_rect.y + 15
        section = self.notebook_section
        if section in (0, 1):
            title_text = "CREW ACTIVITY / ORDERS" if section == 0 else "WIRELESS TRANSCRIPT / 2182 kHz"
            self.screen.blit(self.chart_header_font.render(title_text, True, ink), (pad_x, top))
            self.screen.blit(self.chart_small_font.render("DATE             TIME        SPEAKER / STATION", True, faded), (pad_x, top + 24))
            pygame.draw.line(self.screen, rule, (pad_x, top + 42), (page_rect.right - 14, top + 42), 1)
            entries = self._notebook_entries(section)
            page_size = self._notebook_page_capacity()
            pages = max(1, int(math.ceil(len(entries) / float(page_size))))
            self.notebook_page = int(clamp(self.notebook_page, 0, pages - 1))
            if section == 1:
                # Page 1 shows the latest block, in the order it was spoken; later
                # pages walk backward to earlier exchanges without reversing dialogue.
                end = max(0, len(entries) - self.notebook_page * page_size)
                begin = max(0, end - page_size)
                selected = entries[begin:end]
            else:
                selected = entries[self.notebook_page * page_size:(self.notebook_page + 1) * page_size]
            yy = top + 54
            for entry in selected:
                if yy + 36 > page_rect.bottom - 46:
                    break
                date_clock = "%s  %s" % (entry.get("date", "--"), entry.get("clock", "--:--"))
                stamp = self.chart_small_font.render(date_clock, True, faded)
                speaker = str(entry.get("speaker", "SHIP"))
                kind = str(entry.get("kind", "LOG"))
                tag = self.chart_small_font.render("%s  / %s" % (speaker, kind), True, gold if kind in ("ORDER", "TX") else faded)
                self.screen.blit(stamp, (pad_x, yy))
                self.screen.blit(tag, (pad_x + 124, yy))
                yy += 14
                wrapped = self._wrap_notebook_text(self.chart_font, entry.get("text", ""), page_rect.w - 43)
                for line in wrapped[:2]:
                    self.screen.blit(self.chart_font.render(line, True, ink), (pad_x + 8, yy))
                    yy += 14
                pygame.draw.line(self.screen, (211, 199, 173), (pad_x, yy + 2), (page_rect.right - 14, yy + 2), 1)
                yy += 9
            if not selected:
                empty = "No crew activity recorded yet." if section == 0 else "No radio traffic copied yet. Calls and broadcasts appear here."
                self.screen.blit(self.chart_font.render(empty, True, faded), (pad_x, top + 62))
            page_label = "PAGE %d / %d" % (self.notebook_page + 1, pages)
        elif section == 4:
            title_text = "GUT BOOK / LOOKOUT MEMORIES"
            self.screen.blit(self.chart_header_font.render(title_text, True, ink), (pad_x, top))
            self.screen.blit(self.chart_small_font.render(
                "FIRST CONFIDENT SIGHTING  •  PLOTTED FROM CREW POSITION ESTIMATE", True, faded), (pad_x, top + 24))
            pygame.draw.line(self.screen, rule, (pad_x, top + 42), (page_rect.right - 14, top + 42), 1)
            entries = self._notebook_entries(4)
            page_size = self._notebook_page_capacity()
            pages = max(1, int(math.ceil(len(entries) / float(page_size))))
            self.notebook_page = int(clamp(self.notebook_page, 0, pages - 1))
            selected = entries[self.notebook_page * page_size:(self.notebook_page + 1) * page_size]
            yy = top + 54
            for entry in selected:
                if yy + 55 > page_rect.bottom - 48:
                    break
                status = "ACTIVE" if entry_is_active(entry, self.world.hotspots) else "HISTORICAL"
                stamp = self.chart_small_font.render(
                    "%s  %s  #%02d" % (entry.date, entry.clock, entry.entry_id % 100), True, faded)
                status_color = (57, 104, 75) if status == "ACTIVE" else faded
                tag = self.chart_small_font.render("%s  /  %s" % (entry.sailor, status), True, status_color)
                self.screen.blit(stamp, (pad_x, yy))
                self.screen.blit(tag, (pad_x + 160, yy))
                yy += 16
                detail = "%s?  SKILL %.2f  SURETY %d%%" % (
                    str(entry.species_guess).replace("_", " ").upper(), entry.skill,
                    round(entry.confidence * 100))
                for line in self._wrap_notebook_text(self.chart_font, detail, page_rect.w - 42)[:1]:
                    self.screen.blit(self.chart_font.render(line, True, ink), (pad_x + 7, yy))
                    yy += 15
                pos_line = "PLOTTED X%+.0f  Y%+.0f" % (entry.x, entry.y)
                self.screen.blit(self.chart_font.render(pos_line, True, ink), (pad_x + 7, yy))
                yy += 16
                pygame.draw.line(self.screen, (211, 199, 173), (pad_x, yy + 2), (page_rect.right - 14, yy + 2), 1)
                yy += 9
            if not selected:
                self.screen.blit(self.chart_font.render(
                    "No confident fishing spots recorded yet. Lookouts add entries when their certainty reaches 50%.",
                    True, faded), (pad_x, top + 62))
            note_y = max(top + 65, yy + 2)
            note_lines = [
                "Historical positions are the crew's plot at detection time.",
                "A later navigation fix can move the live G# chart marker.",
                "The gut book records memories; it does not confirm fish are still there.",
            ]
            for line_text in note_lines:
                if note_y + 15 > page_rect.bottom - 40:
                    break
                for wrapped_line in self._wrap_notebook_text(self.chart_small_font, line_text, page_rect.w - 36)[:2]:
                    self.screen.blit(self.chart_small_font.render(wrapped_line, True, faded), (pad_x, note_y))
                    note_y += 13
            page_label = "PAGE %d / %d" % (self.notebook_page + 1, pages)
        elif section == 2:
            day = self._month_offset(self.world.calendar_date(), self.notebook_page)
            import calendar as _calendar
            weeks = _calendar.Calendar(firstweekday=6).monthdayscalendar(day.year, day.month)
            title_text = day.strftime("%B %Y").upper()
            self.screen.blit(self.chart_header_font.render("ALMANAC  /  " + title_text, True, ink), (pad_x, top))
            self.screen.blit(self.chart_small_font.render("CAMPAIGN BEGAN 01 APR 1962  •  " + season_name(day.month).upper(), True, faded), (pad_x, top + 24))
            grid_x, grid_y = pad_x, top + 51
            grid_w = page_rect.w - 34
            cell_w = max(24, grid_w // 7)
            cell_h = min(39, max(25, (page_rect.h - 165) // (len(weeks) + 1)))
            for i, name in enumerate(("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")):
                self.screen.blit(self.chart_small_font.render(name, True, faded), (grid_x + i * cell_w + 2, grid_y))
            for row_i, week in enumerate(weeks):
                for col_i, num in enumerate(week):
                    if not num:
                        continue
                    rect = pygame.Rect(grid_x + col_i * cell_w, grid_y + 17 + row_i * cell_h, cell_w - 3, cell_h - 2)
                    current = day.year == self.world.calendar_date().year and day.month == self.world.calendar_date().month and num == self.world.calendar_date().day
                    pygame.draw.rect(self.screen, (247, 237, 207) if current else (225, 214, 190), rect)
                    pygame.draw.rect(self.screen, gold if current else rule, rect, 2 if current else 1)
                    self.screen.blit(self.chart_font.render(str(num), True, ink), (rect.x + 5, rect.y + 4))
            note_y = grid_y + 17 + len(weeks) * cell_h + 5
            current_outlook = forecast_for_date(self.world.calendar_date())
            note_lines = ["TODAY: " + current_outlook.label,
                          "OUTLOOK: %d–%d C / WIND %d–%d kt" % (current_outlook.temp_low_c, current_outlook.temp_high_c,
                                                               current_outlook.wind_min_kt, current_outlook.wind_max_kt),
                          season_note(day)]
            for line_i, line_text in enumerate(note_lines):
                rows = self._wrap_notebook_text(self.chart_font, line_text, page_rect.w - 36)
                for wrapped_line in rows[:2]:
                    self.screen.blit(self.chart_font.render(wrapped_line, True, ink if line_i < 2 else faded), (pad_x, note_y))
                    note_y += 15
            page_label = day.strftime("%B %Y").upper()
        else:
            start_date = self.world.calendar_date() + __import__("datetime").timedelta(days=self.notebook_page * 5)
            forecasts = forecast_range(start_date, 5)
            self.screen.blit(self.chart_header_font.render("COAST STATION  /  FIVE-DAY MARINE OUTLOOK", True, ink), (pad_x, top))
            self.screen.blit(self.chart_small_font.render("SEASONAL SIMULATION • NOT A LIVE WEATHER FEED", True, faded), (pad_x, top + 24))
            yy = top + 48
            for index, outlook in enumerate(forecasts):
                if yy + 60 > page_rect.bottom - 42:
                    break
                head = outlook.day.strftime("%A, %d %B %Y").upper()
                self.screen.blit(self.chart_header_font.render(head, True, gold if outlook.condition == "storm" else ink), (pad_x, yy))
                yy += 19
                main = outlook.notebook_line()
                for line in self._wrap_notebook_text(self.chart_font, main, page_rect.w - 42)[:2]:
                    self.screen.blit(self.chart_font.render(line, True, ink), (pad_x + 5, yy))
                    yy += 15
                confidence = "Forecast confidence: %d%%" % outlook.confidence_pct
                self.screen.blit(self.chart_small_font.render(confidence, True, faded), (pad_x + 5, yy))
                yy += 18
                pygame.draw.line(self.screen, (211, 199, 173), (pad_x, yy), (page_rect.right - 14, yy), 1)
                yy += 10
            page_label = "DAYS %d–%d AHEAD" % (self.notebook_page * 5 + 1, self.notebook_page * 5 + 5)

        # Explicit paper page controls. They are real mouse targets as well as keyboard pages.
        footer_y = outer.bottom - 39
        pygame.draw.line(self.screen, rule, (outer.x + 10, footer_y - 8), (outer.right - 10, footer_y - 8), 1)
        prev_rect = pygame.Rect(page_rect.x + 10, footer_y - 1, 64, 24)
        next_rect = pygame.Rect(page_rect.right - 74, footer_y - 1, 64, 24)
        for rect, label in ((prev_rect, "< PREV"), (next_rect, "NEXT >")):
            pygame.draw.rect(self.screen, (216, 203, 172), rect)
            pygame.draw.rect(self.screen, ink, rect, 1)
            txt = self.chart_small_font.render(label, True, ink)
            self.screen.blit(txt, (rect.centerx - txt.get_width() // 2, rect.y + 6))
        page_txt = self.chart_small_font.render(page_label, True, ink)
        self.screen.blit(page_txt, (page_rect.centerx - page_txt.get_width() // 2, footer_y + 5))
        self.notebook_hitboxes["prev"] = prev_rect
        self.notebook_hitboxes["next"] = next_rect

    def _chart_landmarks(self):
        """Named fixed landmarks drawn at their charted world positions."""
        w = self.world
        temple_y = w.coast_y(1030.0) - 560.0 - 40.0
        reef_mid = (w.bw_a + w.bw_b) / (2.0 * w.scale)
        return [
            ("HARBOUR MOUTH", V(0.0, -350.0), "mouth"),
            ("LIGHTHOUSE", V(w.bw_b) / w.scale, "light"),
            ("TEMPLE PEAK", V(1030.0, temple_y), "temple"),
            ("REEF", V(reef_mid), "reef"),
        ]

    def _build_navigation_chart_base(self, size):
        """Build static chart cartography once per viewport size."""
        w = self.world
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        surface = pygame.Surface((width, height))
        pal = CHART_PALETTE
        surface.fill(pal["water"])
        transform = chart_transform(width, height)
        self._chart_transform = transform
        k = transform[0]

        def point(x, y):
            return chart_to_pixel(float(x), float(y), transform)

        def is_land(x, y):
            return in_poly(V(float(x), float(y)) * w.scale, w.land_w)

        # Subtle grid and two shoal-water bands; the land polygon is painted over these.
        xmin, ymin, xmax, ymax = CHART_BOUNDS
        for gx in range(math.floor(xmin / 1000.0) * 1000, math.ceil(xmax / 1000.0) * 1000 + 1, 1000):
            if xmin <= gx <= xmax:
                pygame.draw.line(surface, pal["grid"], point(gx, ymin), point(gx, ymax), 1)
        for gy in range(math.floor(ymin / 1000.0) * 1000, math.ceil(ymax / 1000.0) * 1000 + 1, 1000):
            if ymin <= gy <= ymax:
                pygame.draw.line(surface, pal["grid"], point(xmin, gy), point(xmax, gy), 1)
        harbour_px = point(0.0, 0.0)
        pygame.draw.circle(surface, pal["water_inner"], harbour_px, max(1, int(5200 * k)))
        pygame.draw.circle(surface, pal["water_harbour"], harbour_px, max(1, int(950 * k)))

        # Stable hatching marks unsurveyed sea beyond the known radius.
        for gy in range(math.floor(ymin / 500.0) * 500, math.ceil(ymax / 500.0) * 500 + 1, 500):
            for gx in range(math.floor(xmin / 500.0) * 500, math.ceil(xmax / 500.0) * 500 + 1, 500):
                if math.hypot(gx, gy) <= KNOWN_AREA_RADIUS or is_land(gx, gy):
                    continue
                px, py = point(gx, gy)
                if -3 <= px < width + 3 and -3 <= py < height + 3:
                    pygame.draw.line(surface, pal["uncharted"], (px - 2, py + 2), (px + 3, py - 2), 1)

        land_points = [point(p.x, p.y) for p in w.land]
        if len(land_points) >= 3:
            pygame.draw.polygon(surface, pal["land"], land_points)
        coast_points = [point(p.x / w.scale, p.y / w.scale) for p in w.coast_w]
        if len(coast_points) >= 2:
            pygame.draw.lines(surface, pal["coast"], False, coast_points, 2)

        # Danger marks: current reef geometry plus the harbour-mouth sandbar from the plan.
        reef_a, reef_b = V(w.bw_a) / w.scale, V(w.bw_b) / w.scale
        delta = reef_b - reef_a
        length = max(delta.length(), 1.0)
        dash_len = 65.0
        t = 0.0
        while t < length:
            a = reef_a + delta * (t / length)
            b = reef_a + delta * (min(length, t + dash_len * 0.58) / length)
            pygame.draw.line(surface, pal["danger"], point(a.x, a.y), point(b.x, b.y), 2)
            t += dash_len
        pygame.draw.circle(surface, pal["danger"], point(reef_a.x, reef_a.y), max(2, int(3 * k)))
        pygame.draw.circle(surface, pal["danger"], point(reef_b.x, reef_b.y), max(2, int(3 * k)))
        sandbar_a, sandbar_b = V(-260.0, -245.0), V(260.0, -245.0)
        sand_delta = sandbar_b - sandbar_a
        sand_len = sand_delta.length()
        t = 0.0
        while t < sand_len:
            a = sandbar_a + sand_delta * (t / sand_len)
            b = sandbar_a + sand_delta * (min(sand_len, t + 65.0) / sand_len)
            pygame.draw.line(surface, pal["danger"], point(a.x, a.y), point(b.x, b.y), 2)
            t += 100.0

        # One-time deterministic charted depths in fathoms; redraws reuse this rasterized surface.
        for sx, sy, depth in generate_soundings(is_land, w.bottom_m):
            px, py = point(sx, sy)
            label = self.chart_small_font.render(str(depth), True, pal["sounding"])
            surface.blit(label, (px - label.get_width() // 2, py - label.get_height() // 2))

        # Dashes rather than a perfect quest-ring: the edge indicates survey limits, not a fish spot.
        boundary_r = max(1, int(KNOWN_AREA_RADIUS * k))
        for i in range(100):
            if (i // 2) % 2:
                continue
            a0, a1 = math.tau * i / 100, math.tau * (i + 1) / 100
            pa = point(math.cos(a0) * KNOWN_AREA_RADIUS, math.sin(a0) * KNOWN_AREA_RADIUS)
            pb = point(math.cos(a1) * KNOWN_AREA_RADIUS, math.sin(a1) * KNOWN_AREA_RADIUS)
            pygame.draw.line(surface, (113, 112, 91), pa, pb, 1)

        for label, pos, kind in self._chart_landmarks():
            px, py = point(pos.x, pos.y)
            if kind == "light":
                pygame.draw.polygon(surface, pal["landmark"], [(px, py - 5), (px - 4, py + 4), (px + 4, py + 4)])
                pygame.draw.circle(surface, (244, 224, 153), (px, py - 1), 2)
            elif kind == "temple":
                pygame.draw.polygon(surface, pal["ink"], [(px - 5, py - 1), (px, py - 6), (px + 5, py - 1)])
                pygame.draw.line(surface, pal["ink"], (px - 4, py + 2), (px + 4, py + 2), 2)
            elif kind == "reef":
                pygame.draw.polygon(surface, pal["danger"], [(px, py - 5), (px + 5, py + 4), (px - 5, py + 4)], 1)
            else:
                pygame.draw.line(surface, pal["landmark"], (px - 4, py), (px + 4, py), 2)
                pygame.draw.line(surface, pal["landmark"], (px, py - 4), (px, py + 4), 2)
            label_surface = self.chart_small_font.render(label, True, pal["ink"])
            lx = int(clamp(px + 7, 2, width - label_surface.get_width() - 2))
            ly = int(clamp(py - label_surface.get_height() - 2, 2, height - label_surface.get_height() - 2))
            label_rect = pygame.Rect(lx - 2, ly - 1, label_surface.get_width() + 4, label_surface.get_height() + 2)
            pygame.draw.rect(surface, pal["paper"], label_rect)
            pygame.draw.rect(surface, (157, 137, 99), label_rect, 1)
            surface.blit(label_surface, (lx, ly))

        for x, y in ((-4300.0, 2100.0), (4300.0, 2600.0), (1000.0, 4700.0)):
            if not is_land(x, y):
                px, py = point(x, y)
                txt = self.chart_italic_font.render("UNCHARTED", True, pal["uncharted"])
                surface.blit(txt, (px - txt.get_width() // 2, py - txt.get_height() // 2))
        note = self.chart_small_font.render("SURVEYED LIMIT / 6,000 UNITS", True, pal["ink"])
        surface.blit(note, (max(4, harbour_px[0] - note.get_width() // 2),
                            min(height - note.get_height() - 4, harbour_px[1] + boundary_r + 4)))

        # Period-appropriate scale bar and magnetic-variation note.
        scale_len = int(185.2 * 10.0 * k)  # 185.2 design units represent one nautical mile.
        scale_x, scale_y = 16, height - 24
        pygame.draw.line(surface, pal["ink"], (scale_x, scale_y), (scale_x + scale_len, scale_y), 2)
        for mark in (0.0, 0.5, 1.0):
            xx = scale_x + int(scale_len * mark)
            pygame.draw.line(surface, pal["ink"], (xx, scale_y - 5), (xx, scale_y + 4), 2)
        for value, fraction in (("0", 0.0), ("5", 0.5), ("10 nm", 1.0)):
            label = self.chart_small_font.render(value, True, pal["ink"])
            xx = scale_x + int(scale_len * fraction) - label.get_width() // 2
            surface.blit(label, (int(clamp(xx, 0, width - label.get_width())), scale_y - 16))

        rose = (width - 48, 48)
        pygame.draw.circle(surface, pal["paper"], rose, 25)
        pygame.draw.circle(surface, pal["ink"], rose, 25, 1)
        pygame.draw.line(surface, pal["ink"], (rose[0], rose[1] - 18), (rose[0], rose[1] + 17), 1)
        pygame.draw.line(surface, pal["ink"], (rose[0] - 17, rose[1]), (rose[0] + 17, rose[1]), 1)
        pygame.draw.polygon(surface, pal["landmark"], [(rose[0], rose[1] - 18), (rose[0] - 4, rose[1] + 1), (rose[0] + 4, rose[1] + 1)])
        pygame.draw.circle(surface, pal["gold"], rose, 2)
        n_label = self.chart_header_font.render("N", True, pal["ink"])
        surface.blit(n_label, (rose[0] - n_label.get_width() // 2, rose[1] - 40))

        title_w, title_h = min(225, width - 10), 43
        title_rect = pygame.Rect(width - title_w - 7, height - title_h - 7, title_w, title_h)
        pygame.draw.rect(surface, pal["paper"], title_rect)
        pygame.draw.rect(surface, pal["ink"], title_rect, 1)
        yy = title_rect.y + 3
        for line in ("NORTH PACIFIC — 1962", "APPROACHES TO THE HARBOUR", "SOUNDINGS: FATHOMS / HAND CORRECTED"):
            txt = self.chart_small_font.render(line, True, pal["ink"])
            surface.blit(txt, (title_rect.x + 4, yy))
            yy += 12
        return surface

    def _open_navigation_chart(self):
        """Open the chart with a staged copy of the current manual route."""
        self.chart_open = True
        self.chart_move_index = None
        self.chart_status = "LEFT-CLICK TO ADD / SELECT • ENTER TO COMMIT"
        w = self.world
        points = []
        if w.route_waypoints:
            points = [(float(p.x / w.scale), float(p.y / w.scale)) for p in w.route_waypoints]
        elif (w.destination is not None and not self.line.auto and self.line.stage == "off"
              and w.dock_state is None and w.rescue_to is None):
            points = [(float(w.destination.x / w.scale), float(w.destination.y / w.scale))]
        phase_bounds = phase_b_legacy_design_bounds()
        chart_bounds = CHART_BOUNDS
        route_bounds = (min(chart_bounds[0], phase_bounds[0]), min(chart_bounds[1], phase_bounds[1]),
                        max(chart_bounds[2], phase_bounds[2]), max(chart_bounds[3], phase_bounds[3]))
        self.chart_route_editor = WaypointRoute(points, bounds=route_bounds)

    def _close_navigation_chart(self):
        """Close the chart and discard only the uncommitted edit buffer."""
        self.chart_open = False
        self.chart_route_editor = None
        self.chart_move_index = None

    def _best_navigation_observer(self):
        """Best skilled sailor physically on the working deck for visual fixes."""
        candidates = [s for s in self.sailors
                      if s.mode == Sailor.ABOARD and s.level == Level.MAIN]
        return max(candidates, key=lambda sailor: float(getattr(sailor, "skill", 0.0)), default=None)

    def _visible_navigation_landmarks(self):
        """Return named landmarks genuinely within current visibility, without displaying true ship coordinates."""
        w = self.world
        true_design = V(w.ship_pos) / w.scale
        visibility_range = max(0.0, self.weather.visibility_km()) * 300.0
        landmarks = []
        for name, pos, _kind in self._chart_landmarks():
            distance = true_design.distance_to(pos)
            if distance <= visibility_range:
                landmarks.append((distance, name, V(pos)))
        return sorted(landmarks, key=lambda item: item[0])

    def _crew_report_eligible(self, sailor):
        """Reports require a living sailor physically aboard on the working deck."""
        return bool(sailor is not None and sailor.mode == Sailor.ABOARD
                    and sailor.level == Level.MAIN and sailor.ladder is None
                    and sailor.health > 0.0)

    def _make_crew_report(self, sailor, kind, target_name=None, target_design=None):
        """Sample one sailor's observation without changing physical or believed state."""
        w = self.world
        observer_world = w.world_of(sailor.pos)
        report = {
            "kind": kind,
            "sailor_name": sailor.name,
            "skill": clamp(float(sailor.skill), 0.0, 1.0),
            "target_name": target_name,
        }
        if kind == "bearing_distance":
            target_world = V(target_design) * w.scale
            bearing_rad = report_bearing(observer_world, target_world, sailor.skill)
            report["bearing_degrees"] = math.degrees(bearing_rad) % 360.0
            report["distance_nm"] = report_distance(observer_world, target_world, w.scale, sailor.skill)
            # A chart reference is calculated from the crew's believed position,
            # never from the hidden physical position. It helps expose contradictions.
            chart_origin = V(w.believed_pos) / w.scale
            chart_delta = V(target_design) - chart_origin
            report["chart_bearing_degrees"] = math.degrees(math.atan2(chart_delta.x, -chart_delta.y)) % 360.0
        elif kind == "speed":
            report["speed_knots"] = report_speed(w.speed, sailor.skill)
        else:
            raise ValueError("Unknown crew report kind: %s" % kind)
        return report

    def _speak_crew_report(self, report):
        """Deliver the measurement as a named speech bubble and normal crew-log entry."""
        name = report["sailor_name"]
        if report["kind"] == "bearing_distance":
            bearing = int(round(report["bearing_degrees"])) % 360
            target = str(report["target_name"]).title()
            line = "%s: %s bears %03d degrees; range about %.1f nautical miles." % (
                name, target, bearing, report["distance_nm"])
        else:
            line = "%s: The speed log reads about %.1f knots." % (name, report["speed_knots"])
        self.crew.say(line)

    @staticmethod
    def _crew_report_line(report):
        if report["kind"] == "bearing_distance":
            bearing = int(round(report["bearing_degrees"])) % 360
            return "%s (skill %.2f) — %s: %03d° / %.1f nm" % (
                report["sailor_name"], report["skill"],
                str(report["target_name"]).title(), bearing, report["distance_nm"])
        return "%s (skill %.2f) — speed %.1f kt" % (
            report["sailor_name"], report["skill"], report["speed_knots"])

    def _crew_report_comparison(self, first, second):
        """Summarize disagreement without identifying either sailor as correct."""
        if first["kind"] == "bearing_distance":
            b1 = int(round(first["bearing_degrees"])) % 360
            b2 = int(round(second["bearing_degrees"])) % 360
            bearing_spread = bearing_difference_degrees(b1, b2)
            range_spread = abs(first["distance_nm"] - second["distance_nm"])
            mean_range = (first["distance_nm"] + second["distance_nm"]) / 2.0
            chart_bearing = int(round(first.get("chart_bearing_degrees", b1))) % 360
            chart_diff_1 = bearing_difference_degrees(b1, chart_bearing)
            chart_diff_2 = bearing_difference_degrees(b2, chart_bearing)
            chart_contradiction = min(chart_diff_1, chart_diff_2) >= 8.0
            disagreement = bearing_spread >= 4.0 or range_spread > max(0.35, 0.15 * mean_range)
            if chart_contradiction:
                label = "CHART CONFLICT — consider a position fix"
            elif disagreement:
                label = "READINGS DISAGREE — cross-check chart/observer"
            else:
                label = "BROADLY CONSISTENT — neither guaranteed correct"
            return "Spread: bearing %.0f° / range %.1f nm — %s" % (
                bearing_spread, range_spread, label)
        speed_spread = abs(first["speed_knots"] - second["speed_knots"])
        mean_speed = (first["speed_knots"] + second["speed_knots"]) / 2.0
        disagreement = speed_spread > max(0.6, 0.15 * mean_speed)
        label = "READINGS DISAGREE — take another reading" if disagreement else "BROADLY CONSISTENT — neither report is guaranteed correct"
        return "Spread: speed %.1f kt. %s" % (speed_spread, label)

    def _request_crew_report(self, kind):
        """Ask the selected deckhand for bearing/range or speed observations."""
        sailor = self.selected()
        if not self._crew_report_eligible(sailor):
            self.crew.say("Navigator: Select an able sailor on the main deck to take a report.")
            self.crew_report_pending = None
            self.crew_report_display = None
            return False

        target_name, target_design = None, None
        if kind == "bearing_distance":
            visible = self._visible_navigation_landmarks()
            if not visible:
                self.crew.say("Navigator: No named landmark is visible. Wait for clearer water before taking a bearing.")
                self.crew_report_pending = None
                self.crew_report_display = None
                return False
            _distance, target_name, target_design = visible[0]

        report = self._make_crew_report(sailor, kind, target_name, target_design)
        deadline = self.world.time + SECOND_OPINION_WINDOW_SECONDS
        self.crew_report_pending = {
            "kind": kind,
            "first": report,
            "target_name": target_name,
            "target_design": V(target_design) if target_design is not None else None,
            "deadline": deadline,
        }
        self.crew_report_display = {
            "mode": "pending", "reports": [report], "expires_at": deadline,
            "message": "Click another able deckhand within %.0f seconds for an independent second opinion." % SECOND_OPINION_WINDOW_SECONDS,
        }
        self._speak_crew_report(report)
        return True

    def _try_second_opinion(self, sailor):
        """A click on another deckhand during the window repeats the same observation."""
        pending = self.crew_report_pending
        if pending is None:
            return False
        now = self.world.time
        if now >= pending["deadline"]:
            self.crew_report_pending = None
            if self.crew_report_display and self.crew_report_display.get("mode") == "pending":
                self.crew_report_display = None
            return False
        first = pending["first"]
        if sailor is None or sailor.name == first["sailor_name"] or not self._crew_report_eligible(sailor):
            return False

        second = self._make_crew_report(sailor, pending["kind"],
                                        pending["target_name"], pending["target_design"])
        self.crew_report_pending = None
        comparison = self._crew_report_comparison(first, second)
        self.crew_report_display = {
            "mode": "comparison", "reports": [first, second],
            "comparison": comparison, "expires_at": now + 12.0,
        }
        self._speak_crew_report(second)
        self.record_log_entry("Crew report comparison: %s / %s. %s" % (
            first["sailor_name"], second["sailor_name"], comparison))
        return True

    def draw_crew_report_panel(self):
        """Show pending and paired observations without revealing hidden ship truth."""
        display = self.crew_report_display
        if not display or self.world.time >= float(display.get("expires_at", -1.0)):
            return
        if display.get("mode") == "pending":
            pending = self.crew_report_pending
            if pending is None or self.world.time >= pending["deadline"]:
                return
            reports = display["reports"]
            body = [self._crew_report_line(reports[0])]
            if reports[0]["kind"] == "bearing_distance":
                chart_bearing = int(round(reports[0].get("chart_bearing_degrees", 0.0))) % 360
                chart_diff_1 = bearing_difference_degrees(reports[0]["bearing_degrees"], chart_bearing)
                body.append("Chart estimate %03d°; first report offset %.0f°" % (chart_bearing, chart_diff_1))
            body.append(display["message"])
            heading = "CREW REPORT — SECOND OPINION WINDOW"
        else:
            reports = display["reports"]
            body = [self._crew_report_line(reports[0]), self._crew_report_line(reports[1])]
            if reports[0]["kind"] == "bearing_distance":
                chart_bearing = int(round(reports[0].get("chart_bearing_degrees", 0.0))) % 360
                chart_diff_1 = bearing_difference_degrees(reports[0]["bearing_degrees"], chart_bearing)
                chart_diff_2 = bearing_difference_degrees(reports[1]["bearing_degrees"], chart_bearing)
                body.append("Chart %03d°; report offsets %.0f° / %.0f°" % (chart_bearing, chart_diff_1, chart_diff_2))
            body.append(display["comparison"])
            heading = "INDEPENDENT CREW REPORTS — COMPARE THE READINGS"

        width = min(620, max(300, W - 24))
        line_h = 18
        height = 17 + 20 + len(body) * line_h + 11
        x, y = (W - width) // 2, 12
        card = self._cached_panel_surface((width, height), (10, 18, 22, 226), radius=6)
        self.screen.blit(card, (x, y))
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (202, 173, 104), rect, 1, border_radius=6)
        title = self.hud_compact_font.render(heading, True, (255, 226, 157))
        self.screen.blit(title, (x + 9, y + 5))
        for index, line in enumerate(body):
            colour = (255, 225, 154) if "DISAGREE" in line else (235, 239, 226)
            text_surface = self.hud_compact_font.render(self._fit(line, width - 18), True, colour)
            self.screen.blit(text_surface, (x + 9, y + 25 + index * line_h))

    def _navigation_fix_status_lines(self):
        """Current availability hints displayed on the chart, one line per fix."""
        w = self.world
        now = w.time
        labels = []
        observer = self._best_navigation_observer()
        visible = self._visible_navigation_landmarks()
        for key, label in (("landmark", "1 LANDMARK"), ("sextant", "2 SEXTANT"),
                           ("rdf", "3 RDF"), ("sounder", "4 SOUNDER")):
            remaining = self.navigation_fix_cooldowns[key] - (now - self.navigation_fix_last_attempt[key])
            if remaining > 0:
                labels.append("%s: COOLING %.0fs" % (label, remaining))
                continue
            if key == "landmark":
                if observer is None:
                    reason = "NEED DECK OBSERVER"
                elif not visible:
                    reason = "NO LANDMARK IN SIGHT"
                else:
                    reason = "%s VISIBLE" % visible[0][1]
            elif key == "sextant":
                check = assess_sextant(w.hour(), self.weather.cloud,
                                       float(observer.skill) if observer else 0.0, observer is not None)
                reason = "READY" if check.available else check.reason
            elif key == "rdf":
                op = self.radio_operator
                distance = w.ship_pos.distance_to(HARBOUR) / w.scale
                check = assess_rdf(distance, self.radio_station_ok(),
                                   float(op.skill) if op is not None else 0.0)
                reason = "READY" if check.available else check.reason
            else:
                charted_area = math.hypot(w.believed_pos.x / w.scale, w.believed_pos.y / w.scale) <= KNOWN_AREA_RADIUS
                reason = "READY TO CHECK DEPTH" if charted_area else "OUTSIDE CHARTED SOUNDINGS"
            labels.append("%s: %s" % (label, reason))
        return labels

    def _attempt_navigation_fix(self, kind):
        """Attempt one condition-gated fix; failures never expose the true error vector."""
        if kind not in self.navigation_fix_cooldowns:
            return False
        w = self.world
        now = w.time
        remaining = self.navigation_fix_cooldowns[kind] - (now - self.navigation_fix_last_attempt[kind])
        if remaining > 0:
            self.chart_status = "%s FIX COOLING — %.0f SIM-SECONDS" % (kind.upper(), remaining)
            return False

        observer = self._best_navigation_observer()
        true_design = V(w.ship_pos) / w.scale
        estimate = V(w.ship_pos)
        accuracy_units = 0.0
        method_label = kind.upper()

        if kind == "landmark":
            visible = self._visible_navigation_landmarks()
            if not visible:
                self.chart_status = "LANDMARK FIX UNAVAILABLE — NO NAMED LANDMARK IN SIGHT"
                return False
            if observer is None:
                self.chart_status = "LANDMARK FIX UNAVAILABLE — NEED A SAILOR ON THE MAIN DECK"
                return False
            distance, landmark_name, _landmark_pos = visible[0]
            check = assess_landmark_bearing(distance, self.weather.visibility_km(),
                                            float(observer.skill), w.sea_state, True)
            if not check.available:
                self.chart_status = "LANDMARK FIX UNAVAILABLE — " + check.reason
                return False
            accuracy_units = check.accuracy_units
            dx, dy = sample_position_error(accuracy_units)
            estimate += V(dx, dy) * w.scale
            method_label = "LANDMARK / " + landmark_name
            self.navigation_fix_last_attempt[kind] = now
            w.apply_approximate_position_fix(estimate, method_label, accuracy_units * w.scale)
            self.chart_status = "LANDMARK FIX: %s — ESTIMATED ACCURACY ±%.0f UNITS" % (landmark_name, accuracy_units)

        elif kind == "sextant":
            check = assess_sextant(w.hour(), self.weather.cloud,
                                   float(observer.skill) if observer else 0.0, observer is not None)
            if not check.available:
                self.chart_status = "SEXTANT FIX UNAVAILABLE — " + check.reason
                return False
            accuracy_units = check.accuracy_units
            dx, dy = sample_position_error(accuracy_units)
            estimate += V(dx, dy) * w.scale
            method_label = "SEXTANT"
            self.navigation_fix_last_attempt[kind] = now
            w.apply_approximate_position_fix(estimate, method_label, accuracy_units * w.scale)
            self.chart_status = "SEXTANT FIX: SUN SIGHT TAKEN — ESTIMATED ACCURACY ±%.0f UNITS" % accuracy_units

        elif kind == "rdf":
            operator = self.radio_operator
            distance = w.ship_pos.distance_to(HARBOUR) / w.scale
            check = assess_rdf(distance, self.radio_station_ok(),
                               float(operator.skill) if operator is not None else 0.0)
            if not check.available:
                self.chart_status = "RDF FIX UNAVAILABLE — " + check.reason
                return False
            bearing_to_station = math.atan2(-true_design.y, -true_design.x)
            dx, dy, along_accuracy = sample_rdf_error(check.accuracy_units, bearing_to_station)
            estimate += V(dx, dy) * w.scale
            accuracy_units = along_accuracy
            method_label = "RDF"
            self.navigation_fix_last_attempt[kind] = now
            w.apply_approximate_position_fix(estimate, method_label, accuracy_units * w.scale)
            self.chart_status = "RDF FIX: COAST BEARING PLOTTED — ALONG-LINE DOUBT ±%.0f UNITS" % accuracy_units

        elif kind == "sounder":
            believed_design = V(w.believed_pos) / w.scale
            if math.hypot(believed_design.x, believed_design.y) > KNOWN_AREA_RADIUS:
                self.chart_status = "SOUNDER UNAVAILABLE — OUTSIDE CHARTED SOUNDINGS"
                return False
            sounded = w.bottom_m(w.ship_pos.distance_to(HARBOUR) / w.scale)
            charted = charted_depth_at(believed_design.x, believed_design.y, w.bottom_m)
            check = assess_echo_sounder(sounded, charted, True)
            self.navigation_fix_last_attempt[kind] = now
            if check.available:
                w.reset_position_fix("ECHO SOUNDER")
                self.chart_status = "SOUNDER MATCH: %.0f M / CHART %.0f M — POSITION CONFIRMED" % (sounded, charted)
                self.record_log_entry("Navigation: echo-sounder depth matched the chart; position estimate confirmed.")
                self.crew.say("Navigator: Sounding agrees with the chart. Position confirmed.")
                return True
            self.chart_status = "SOUNDER MISMATCH: %.0f M / CHART %.0f M — POSITION STILL UNCERTAIN" % (sounded, charted)
            self.record_log_entry("Navigation: echo-sounder mismatch (%.0f m sounded, %.0f m charted); no correction applied." % (sounded, charted))
            self.crew.say("Navigator: Sounding doesn't agree with the chart. We need another fix.")
            return False

        self.record_log_entry("Navigation fix: %s accepted; nominal accuracy about ±%.0f chart units." % (method_label, accuracy_units))
        self.crew.say("Navigator: %s fix plotted. Estimated accuracy about %d units." % (method_label, round(accuracy_units)))
        return True

    def _chart_design_point(self, screen_pos):
        rect, transform = self._chart_map_rect, self._chart_transform
        if rect is None or transform is None or not rect.collidepoint(screen_pos):
            return None
        x, y = pixel_to_chart(screen_pos[0] - rect.x, screen_pos[1] - rect.y, transform)
        if getattr(self, "campaign_phase", "A") == "B":
            # Phase B chart Y increases downward on screen, while projected world Y
            # increases north. Invert it before checking NM bounds or inverse projection.
            phase_b_y_nm = -float(y)
            min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
            if not (min_x <= x <= max_x and min_y <= phase_b_y_nm <= max_y):
                return None
            # The editor stores legacy local design coordinates; only the view is wide-area.
            return tuple(float(v) for v in phase_b_nm_to_legacy_design((float(x), phase_b_y_nm)))
        if not within_chart_bounds(x, y):
            return None
        return (float(x), float(y))

    def _chart_start_design(self):
        w = self.world
        return (float(w.believed_pos.x / w.scale), float(w.believed_pos.y / w.scale))

    def _handle_chart_left_click(self, screen_pos, shift=False):
        editor = self.chart_route_editor
        point = self._chart_design_point(screen_pos)
        if editor is None or point is None:
            self.chart_status = "CLICK OPEN WATER INSIDE THE CHART SHEET"
            return
        start = self._chart_start_design()
        k = self._chart_transform[0] if self._chart_transform else 0.0
        unit_scale = 185.2 if self.campaign_phase == "B" else 1.0
        point_tolerance = 16.0 / max(k, 1e-6) * unit_scale
        leg_tolerance = 12.0 / max(k, 1e-6) * unit_scale

        # A selected point is carried to the next left-click location. The route is
        # still staged until Enter, so closing the chart cancels these edits.
        if self.chart_move_index is not None:
            index = self.chart_move_index
            if editor.move(index, point, start=start):
                self.chart_status = "WAYPOINT %d MOVED — ENTER TO COMMIT" % (index + 1)
                self.chart_move_index = None
            else:
                self.chart_status = "MOVE REJECTED — KEEP LEGS DISTINCT AND INSIDE THE SHEET"
            return

        hit = editor.nearest_waypoint(point, point_tolerance)
        if hit is not None:
            self.chart_move_index = hit
            self.chart_status = "WAYPOINT %d SELECTED — CLICK ITS NEW POSITION" % (hit + 1)
            return

        if shift:
            leg = editor.nearest_leg(point, start, leg_tolerance)
            if leg is None:
                self.chart_status = "SHIFT-CLICK CLOSER TO A ROUTE LEG TO INSERT"
                return
            index, _distance, projected = leg
            if editor.insert(index, projected, start=start):
                self.chart_status = "WAYPOINT INSERTED AS %d — ENTER TO COMMIT" % (index + 1)
            else:
                self.chart_status = "INSERT REJECTED — ROUTE TOO CLOSE TO AN EXISTING POINT"
            return

        if editor.add(point, start=start):
            self.chart_status = "WAYPOINT %d ADDED — ENTER TO COMMIT" % len(editor.points)
        elif len(editor.points) >= MAX_CHART_WAYPOINTS:
            self.chart_status = "ROUTE LIMIT: EIGHT WAYPOINTS"
        else:
            self.chart_status = "POINT REJECTED — TOO CLOSE TO SHIP / ANOTHER WAYPOINT"

    def _handle_chart_right_click(self, screen_pos):
        editor = self.chart_route_editor
        point = self._chart_design_point(screen_pos)
        if editor is not None and point is not None:
            k = self._chart_transform[0] if self._chart_transform else 0.0
            unit_scale = 185.2 if self.campaign_phase == "B" else 1.0
            hit = editor.nearest_waypoint(point, 16.0 / max(k, 1e-6) * unit_scale)
            if hit is not None:
                editor.delete(hit)
                self.chart_move_index = None
                self.chart_status = "WAYPOINT %d DELETED — ENTER TO COMMIT" % (hit + 1)
                return
        # Preserve the established right-click close affordance when not over a point.
        self._close_navigation_chart()

    def _commit_chart_route(self):
        editor, w = self.chart_route_editor, self.world
        if editor is None:
            self._close_navigation_chart()
            return
        if self.line.auto or self.line.stage != "off":
            self.chart_status = "AUTO-FISHING HAS PRIORITY — STAND IT DOWN BEFORE COMMITTING A ROUTE"
            self.crew.say("Captain: Auto-fishing has priority. Stand it down before committing a manual chart route.")
            return
        if w.dock_state is not None or w.rescue_to is not None or self.crew.alarm_target is not None:
            self.chart_status = "ROUTE HELD — DOCKING / RESCUE HAS NAVIGATION PRIORITY"
            self.crew.say("Captain: Route not committed. Docking or rescue has navigation priority.")
            return

        design_points = list(editor.points)
        had_existing_course = bool(w.route_waypoints) or w.destination is not None
        w.route_waypoints = [V(x * w.scale, y * w.scale) for x, y in design_points]
        w.route_origin = V(w.believed_pos)
        w.route_arrival_hold = False
        w.ocean_quick_target = None
        if w.route_waypoints:
            w.set_destination(w.route_waypoints[0], preserve_route=True)
            self.record_log_entry("Manual chart course committed with %d waypoint(s)." % len(w.route_waypoints))
            self.crew.say("Captain: Chart course committed. %d waypoint(s); steer for the first leg." % len(w.route_waypoints))
        else:
            w.route_waypoints.clear()
            w.destination = None
            w.ap_t = 0.0
            if had_existing_course:
                self.record_log_entry("Manual chart course cleared.")
                self.crew.say("Captain: Manual chart course cleared. Holding present heading.")
        self._close_navigation_chart()

    def _clear_chart_route(self):
        """Escape clears the entire course immediately, as specified by the chart plan."""
        w = self.world
        had_course = bool(w.route_waypoints) or (w.destination is not None and not self.line.auto and self.line.stage == "off")
        w.route_waypoints.clear()
        w.route_origin = None
        w.route_arrival_hold = False
        w.ocean_quick_target = None
        if not self.line.auto and self.line.stage == "off" and w.dock_state is None and w.rescue_to is None:
            w.destination = None
            w.ap_t = 0.0
        if self.chart_route_editor is not None:
            self.chart_route_editor.clear()
        self.chart_move_index = None
        self.world.route_origin = None
        self.world.route_arrival_hold = False
        self.world.ocean_quick_target = None
        self.chart_status = "COURSE CLEARED — ENTER TO COMMIT THE EMPTY ROUTE / C TO CLOSE"
        if had_course:
            self.record_log_entry("Manual chart course cleared with Escape.")
            self.crew.say("Captain: Chart course cleared.")

    def _build_phase_b_navigation_chart_base(self, size):
        """Rasterize the static Phase B ocean sheet once per viewport size.

        Coastlines and the fleet box are deliberately marked approximate. This is
        a campaign overview, not a substitute for a surveyed navigation chart.
        """
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        surface = pygame.Surface((width, height))
        pal = CHART_PALETTE
        surface.fill(pal["water"])
        chart_bounds = phase_b_chart_bounds()
        transform = chart_transform(width, height, bounds=chart_bounds, margin=28)
        self._phase_b_chart_transform = transform

        def point_nm(position):
            return chart_to_pixel(float(position[0]), -float(position[1]), transform)

        def point_geo(lon, lat):
            return point_nm(HIGH_SEAS_PROJECTION.to_nm(float(lon), float(lat)))

        min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
        # Latitude/longitude graticule, labelled in geographic coordinates.
        for latitude in (41, 45, 50, 55, 60, 62):
            y_nm = HIGH_SEAS_PROJECTION.to_nm(160.0, float(latitude))[1]
            y_chart = -y_nm
            pygame.draw.line(surface, pal["grid"],
                             chart_to_pixel(chart_bounds[0], y_chart, transform),
                             chart_to_pixel(chart_bounds[2], y_chart, transform), 1)
            label = self.chart_small_font.render("%d°N" % latitude, True, pal["ink"])
            lx, ly = point_geo(160.0, latitude)
            surface.blit(label, (4, int(clamp(ly - label.get_height() // 2, 2, height - label.get_height() - 2))))
        for longitude in range(140, 186, 5):
            x_nm = HIGH_SEAS_PROJECTION.to_nm(float(longitude), 45.0)[0]
            pygame.draw.line(surface, pal["grid"],
                             chart_to_pixel(x_nm, chart_bounds[1], transform),
                             chart_to_pixel(x_nm, chart_bounds[3], transform), 1)
            if longitude < 180:
                label_text = "%d°E" % longitude
            elif longitude == 180:
                label_text = "180°"
            else:
                label_text = "%d°W" % (360 - longitude)
            label = self.chart_small_font.render(label_text, True, pal["ink"])
            lx, _ly = point_geo(longitude, 62.0)
            surface.blit(label, (int(clamp(lx - label.get_width() // 2, 2, width - label.get_width() - 2)), 4))

        # Schematic coastline polygons, intentionally soft/labelled approximate.
        land_shapes = [
            # Hokkaido / north Honshu edge.
            [(138.0, 39.4), (142.0, 39.8), (146.2, 41.5), (146.1, 44.8),
             (144.1, 46.2), (141.3, 45.5), (139.6, 43.5), (138.0, 42.2)],
            # Sakhalin.
            [(140.4, 45.6), (142.5, 46.5), (144.3, 49.3), (144.1, 52.0),
             (142.5, 54.5), (140.7, 52.5), (141.0, 49.0)],
            # Northern mainland / Sea of Okhotsk edge.
            [(134.0, 56.5), (145.0, 55.0), (151.5, 54.0), (158.5, 56.2),
             (163.0, 60.0), (165.0, 63.0), (134.0, 63.0)],
            # Kamchatka peninsula.
            [(158.5, 51.0), (161.2, 51.0), (164.1, 53.0), (167.3, 57.0),
             (171.0, 61.0), (172.0, 63.0), (166.0, 63.0), (162.3, 59.0), (160.1, 55.0)],
        ]
        for coordinates in land_shapes:
            polygon = [point_geo(lon, lat) for lon, lat in coordinates]
            if len(polygon) >= 3:
                pygame.draw.polygon(surface, pal["land"], polygon)
                pygame.draw.lines(surface, pal["coast"], True, polygon, 2)

        # Kuril chain as simple small islands, not detailed coast geometry.
        for index, (lon, lat) in enumerate((
            (145.6, 44.4), (147.0, 45.0), (148.3, 45.7), (149.6, 46.8),
            (151.0, 47.5), (152.0, 48.6), (153.4, 49.2), (155.0, 50.0),
        )):
            ix, iy = point_geo(lon, lat)
            pygame.draw.ellipse(surface, pal["land"], (ix - 2, iy - 3, 5, 7))
            pygame.draw.ellipse(surface, pal["coast"], (ix - 2, iy - 3, 5, 7), 1)

        # Historical salmon fleet box (160E through 175W, 46N–62N).
        fleet_box = [point_geo(160.0, 46.0), point_geo(185.0, 46.0),
                     point_geo(185.0, 62.0), point_geo(160.0, 62.0)]
        pygame.draw.lines(surface, (151, 117, 48), True, fleet_box, 2)
        box_label = self.chart_header_font.render("1962 SALMON FLEET BOX", True, (121, 86, 38))
        label_anchor = point_geo(172.5, 61.2)
        surface.blit(box_label, (int(clamp(label_anchor[0] - box_label.get_width() // 2,
                                          2, width - box_label.get_width() - 2)),
                                 int(clamp(label_anchor[1], 2, height - box_label.get_height() - 2))))

        # Schematic mothership areas show clustering policy without revealing any
        # vessel's live or exact schedule position.
        for number, centre in enumerate(MOTHERSHIP_CLUSTER_CENTERS_NM, 1):
            cx, cy = point_nm(centre)
            radius = max(4, int(36.0 * transform[0]))
            pygame.draw.circle(surface, (163, 145, 102), (cx, cy), radius, 1)
            tag = self.chart_small_font.render("AREA %02d" % number, True, (118, 101, 72))
            surface.blit(tag, (cx + 4, cy + 3))

        # Hakodate is the Phase A / Phase B transition reference.
        hakodate_nm = legacy_design_to_phase_b_nm((0.0, 0.0))
        hx, hy = point_nm(hakodate_nm)
        pygame.draw.circle(surface, pal["landmark"], (hx, hy), 4, 2)
        pygame.draw.line(surface, pal["landmark"], (hx - 7, hy), (hx + 7, hy), 1)
        pygame.draw.line(surface, pal["landmark"], (hx, hy - 7), (hx, hy + 7), 1)
        hakodate_label = self.chart_small_font.render("HAKODATE / DEPARTURE", True, pal["landmark"])
        surface.blit(hakodate_label, (int(clamp(hx + 8, 2, width - hakodate_label.get_width() - 2)),
                                      int(clamp(hy - 14, 2, height - hakodate_label.get_height() - 2))))

        scale_px = min(max(1, int(200.0 * transform[0])), max(1, width // 3))
        scale_x, scale_y = 14, height - 20
        pygame.draw.line(surface, pal["ink"], (scale_x, scale_y), (scale_x + scale_px, scale_y), 2)
        for xx in (scale_x, scale_x + scale_px // 2, scale_x + scale_px):
            pygame.draw.line(surface, pal["ink"], (xx, scale_y - 4), (xx, scale_y + 4), 1)
        scale_label = self.chart_small_font.render("0                         100                         200 NM APPROX.", True, pal["ink"])
        surface.blit(scale_label, (scale_x, scale_y - 14))
        disclaimer = self.chart_small_font.render("APPROXIMATE COASTLINE / NOT FOR NAVIGATIONAL FIXES", True, pal["landmark"])
        surface.blit(disclaimer, (max(4, width - disclaimer.get_width() - 8), height - disclaimer.get_height() - 4))
        return surface

    def _select_phase_b_contact_at(self, screen_pos):
        """Select only a reported/highlighted Phase B contact hitbox."""
        for rect, vessel_id in reversed(getattr(self, "_phase_b_contact_hitboxes", [])):
            if rect.collidepoint(screen_pos):
                ship = self.traffic_world.by_id(vessel_id)
                if ship is None:
                    continue
                self.phase_b_chart_selected_contact_id = ship.id
                report = ship.last_reported_position_nm
                if report is None:
                    self.chart_status = "%s — NO POSITION REPORT" % ship.callsign
                else:
                    self.chart_status = "%s SELECTED — PRESS R TO HAIL IF WITHIN RANGE" % ship.callsign
                return True
        return False

    def _open_phase_b_selected_radio_contact(self):
        """Open the normal radio panel for the selected contact, if its plot is in range."""
        vessel_id = getattr(self, "phase_b_chart_selected_contact_id", None)
        ship = self.traffic_world.by_id(vessel_id) if vessel_id else None
        if ship is None:
            self.chart_status = "SELECT A REPORTED VESSEL FIRST"
            return False
        report = ship.last_reported_position_nm
        if report is None:
            self.chart_status = "%s HAS NO REPORTED POSITION" % ship.callsign
            return False
        player_nm = self._traffic_player_believed_position_nm()
        range_nm = math.dist(player_nm, report)
        if range_nm > float(ship.radio_range_nm):
            self.chart_status = "%s PLOT IS %.1f NM AWAY — OUTSIDE STATED RADIO RANGE" % (ship.callsign, range_nm)
            return False
        if not self.open_radio_ui():
            self.chart_status = "RADIO PANEL IS UNAVAILABLE"
            return False
        # Since radio range is at most 49 NM and refresh includes 55 NM, this ID
        # should be present. Keep a defensive fallback for unusual custom radio fits.
        ids = [contact.id for contact in self.radio_ui_contacts]
        if ship.id not in ids:
            self.chart_open = True
            self.radio_ui_open = False
            self.chart_status = "%s PLOT IS NOT IN THE CURRENT RADIO CONTACT SET" % ship.callsign
            return False
        self.radio_ui_selected_ship_id = ship.id
        self.radio_ui_scroll = max(0, ids.index(ship.id) - 2)
        self.radio_ui_status = "Selected %s from the high-seas chart." % ship.callsign
        return True

    def _draw_phase_b_navigation_chart(self, map_rect, side_rect, outer):
        """Draw the wide-area Phase B chart, routes, player DR and known reports."""
        width, height = map_rect.size
        if (self._phase_b_chart_base_surface is None
                or self._phase_b_chart_base_size != map_rect.size):
            self._phase_b_chart_base_surface = self._build_phase_b_navigation_chart_base(map_rect.size)
            self._phase_b_chart_base_size = map_rect.size
        chart_surface = self._phase_b_chart_base_surface.copy()
        transform = self._phase_b_chart_transform
        self._chart_transform = transform
        self._chart_map_rect = map_rect.copy()
        self._chart_outer_rect = outer.copy()
        pal = CHART_PALETTE
        chart_bounds = phase_b_chart_bounds()
        self._phase_b_contact_hitboxes = []
        now = float(self.world.time)
        w = self.world

        def point_chart(x, y_chart):
            return chart_to_pixel(float(x), float(y_chart), transform)

        def point_nm(position_nm):
            return point_chart(float(position_nm[0]), -float(position_nm[1]))

        def point_design(position_design):
            return point_nm(legacy_design_to_phase_b_nm((float(position_design[0]), float(position_design[1]))))

        def clamp_chart(x, y):
            return (min(chart_bounds[2] - 25.0, max(chart_bounds[0] + 25.0, float(x))),
                    min(chart_bounds[3] - 25.0, max(chart_bounds[1] + 25.0, float(y))))

        player_nm = self._traffic_player_believed_position_nm()
        player_chart = (player_nm[0], -player_nm[1])
        player_on_sheet = within_chart_bounds(player_chart[0], player_chart[1], bounds=chart_bounds)
        player_draw_chart = player_chart if player_on_sheet else clamp_chart(*player_chart)
        sx, sy = point_chart(*player_draw_chart)

        # Route editing remains in the legacy physical chart coordinate store, but
        # each point is projected on this wider sheet. Lines are clipped at chart edge.
        editor = self.chart_route_editor
        route_points_design = list(editor.points) if editor is not None else []
        route_points_nm = [legacy_design_to_phase_b_nm(p) for p in route_points_design]
        path_nm = [player_nm] + route_points_nm
        for leg_index, (a, b) in enumerate(zip(path_nm, path_nm[1:])):
            a_chart, b_chart = (a[0], -a[1]), (b[0], -b[1])
            clipped = clip_segment_to_bounds(a_chart, b_chart, chart_bounds)
            if clipped is None:
                continue
            pa, pb = point_chart(*clipped[0]), point_chart(*clipped[1])
            pygame.draw.line(chart_surface, pal["course"], pa, pb, 2)
            leg_nm = math.dist(a, b)
            mid = ((clipped[0][0] + clipped[1][0]) * 0.5,
                   (clipped[0][1] + clipped[1][1]) * 0.5)
            label = self.chart_small_font.render("%.0f NM" % leg_nm, True, pal["ink"])
            mx, my = point_chart(*mid)
            chart_surface.blit(label, (int(clamp(mx + 4, 2, width - label.get_width() - 2)),
                                        int(clamp(my + 2, 2, height - label.get_height() - 2))))
        for index, position_nm in enumerate(route_points_nm):
            cx, cy = position_nm[0], -position_nm[1]
            if not within_chart_bounds(cx, cy, bounds=chart_bounds):
                continue
            px, py = point_chart(cx, cy)
            selected = editor is not None and self.chart_move_index == index
            radius = 9 if selected else 7
            fill = pal["gold"] if selected else pal["paper"]
            pygame.draw.circle(chart_surface, pal["course"], (px, py), radius + 2, 1)
            pygame.draw.circle(chart_surface, fill, (px, py), radius)
            pygame.draw.circle(chart_surface, pal["ink"], (px, py), radius, 1)
            label = self.chart_header_font.render(str(index + 1), True, pal["ink"])
            chart_surface.blit(label, (px - label.get_width() // 2, py - label.get_height() // 2))

        # Towline joins the crew's believed player fix to the Coast Guard's last
        # reported plot. It does not substitute the escort's live position.
        escort = getattr(self, "tow_escort", None)
        if escort is not None and escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW", "ARRIVED"):
            tow_entity = self.traffic_world.by_id(getattr(escort, "vessel_id", ""))
            tow_report = getattr(tow_entity, "last_reported_position_nm", None) if tow_entity else None
            if tow_report is None:
                tow_report = self._legacy_nm_to_active_nm(escort.world_reported_position_nm)
            tow_chart = (float(tow_report[0]), -float(tow_report[1]))
            clip = clip_segment_to_bounds(player_chart, tow_chart, chart_bounds)
            if clip is not None and escort.state == "UNDER_TOW":
                pa, pb = point_chart(*clip[0]), point_chart(*clip[1])
                if escort.line_at_risk:
                    for a, b in dashed_segments(pa, pb, dash=8, gap=5):
                        pygame.draw.line(chart_surface, pal["tow"], a, b, 2)
                else:
                    pygame.draw.line(chart_surface, pal["tow"], pa, pb, 2)

        color_for = {
            TrafficArchetype.INDEPENDENT_LONGLINE: (66, 108, 105),
            TrafficArchetype.INDEPENDENT_GILLNET: (71, 116, 134),
            TrafficArchetype.CORPORATE_CATCHER: (100, 91, 65),
            TrafficArchetype.CORPORATE_LONGLINER: (126, 91, 52),
            TrafficArchetype.MOTHERSHIP: (81, 67, 119),
            TrafficArchetype.COAST_GUARD: pal["tow"],
            TrafficArchetype.SOVIET_TRAWLER: (93, 105, 70),
        }
        contacts = [ship for ship in self.traffic_world.known_contacts()
                    if ship.known_to_player and ship.last_reported_position_nm is not None]
        # The sparse known-contact collection keeps render work independent of the
        # 461-ship schedule catalogue. Put nearest reports first so the 24 visible
        # labels are useful around the player instead of depending on catalogue order.
        contacts.sort(key=lambda ship: (math.dist(player_nm, ship.last_reported_position_nm), ship.id))
        selected_id = getattr(self, "phase_b_chart_selected_contact_id", None)
        selected_ship = self.traffic_world.by_id(selected_id) if selected_id else None
        for contact_index, ship in enumerate(contacts):
            report = ship.last_reported_position_nm
            x, y = float(report[0]), float(report[1])
            chart_x, chart_y = x, -y
            if not within_chart_bounds(chart_x, chart_y, bounds=chart_bounds):
                continue
            px, py = point_chart(chart_x, chart_y)
            stale = ship.report_stale_at(now)
            color = (128, 125, 108) if stale else color_for.get(ship.archetype, pal["ink"])
            angle = -float(ship.last_reported_heading_rad)  # north-positive world Y -> screen-down
            triangle = [
                (px + int(9 * math.cos(angle)), py + int(9 * math.sin(angle))),
                (px + int(-6 * math.cos(angle) - 4 * math.sin(angle)),
                 py + int(-6 * math.sin(angle) + 4 * math.cos(angle))),
                (px + int(-6 * math.cos(angle) + 4 * math.sin(angle)),
                 py + int(-6 * math.sin(angle) - 4 * math.cos(angle))),
            ]
            pygame.draw.polygon(chart_surface, color, triangle)
            pygame.draw.polygon(chart_surface, pal["paper"], triangle, 1)
            if ship.id == selected_id:
                pygame.draw.circle(chart_surface, pal["gold"], (px, py), 12, 2)
            global_rect = pygame.Rect(map_rect.x + px - 10, map_rect.y + py - 10, 20, 20)
            self._phase_b_contact_hitboxes.append((global_rect, ship.id))
            # Name at most the 24 nearest sorted IDs / always the selected contact.
            if contact_index < 24 or ship.id == selected_id:
                age_s = ship.report_age_s(now)
                suffix = "?" if stale else ""
                label_text = "%s%s" % (ship.callsign, suffix)
                label = self.chart_small_font.render(label_text, True, color)
                lx = int(clamp(px + 9, 2, width - label.get_width() - 2))
                ly = int(clamp(py - label.get_height() - 3, 2, height - label.get_height() - 2))
                chart_surface.blit(label, (lx, ly))

        # Player's marker is crew-estimated, not physical truth. It appears at the
        # nearest chart edge if local physics carries the hull off the current sheet.
        angle = float(w.believed_heading)
        ship_poly = [
            (sx + int(12 * math.cos(angle)), sy + int(12 * math.sin(angle))),
            (sx + int(-8 * math.cos(angle) - 6 * math.sin(angle)), sy + int(-8 * math.sin(angle) + 6 * math.cos(angle))),
            (sx + int(-8 * math.cos(angle) + 6 * math.sin(angle)), sy + int(-8 * math.sin(angle) - 6 * math.cos(angle))),
        ]
        if w.dr_uncertainty > 0.5:
            radius = int(clamp((w.dr_uncertainty / max(0.001, w.scale * 185.2)) * transform[0], 3, min(width, height) * 0.2))
            pygame.draw.circle(chart_surface, pal["gold"], (sx, sy), radius, 1)
        pygame.draw.polygon(chart_surface, pal["ship"], ship_poly)
        pygame.draw.polygon(chart_surface, pal["ink"], ship_poly, 1)
        player_label_text = "KŌEI MARU / CREW PLOT" if player_on_sheet else "KŌEI MARU / OFF SHEET"
        player_label = self.chart_small_font.render(player_label_text, True, pal["ink"])
        chart_surface.blit(player_label, (int(clamp(sx + 11, 2, width - player_label.get_width() - 2)),
                                          int(clamp(sy + 7, 2, height - player_label.get_height() - 2))))

        self.screen.blit(chart_surface, map_rect.topleft)
        pygame.draw.rect(self.screen, pal["ink"], map_rect, 2)
        pygame.draw.rect(self.screen, (231, 220, 193), side_rect)
        pygame.draw.rect(self.screen, pal["ink"], side_rect, 1)
        inner_x, yy = side_rect.x + 9, side_rect.y + 7

        def section(header, lines):
            nonlocal yy
            needed = 17 + 14 * len(lines) + 4
            if yy + needed > side_rect.bottom - 22:
                return False
            self.screen.blit(self.chart_header_font.render(header, True, pal["landmark"]), (inner_x, yy))
            yy += 16
            for line_text in lines:
                text = str(line_text)
                max_width = side_rect.w - 18
                while text and self.chart_font.size(text)[0] > max_width:
                    text = text[:-1]
                if text != line_text:
                    text = text.rstrip() + "…"
                self.screen.blit(self.chart_font.render(text, True, pal["ink"]), (inner_x, yy))
                yy += 14
            yy += 4
            return True

        lon, lat = HIGH_SEAS_PROJECTION.to_lonlat(player_nm[0], player_nm[1])
        lon_label = "%0.2f°%s" % (abs(lon), "E" if lon >= 0 else "W")
        lat_label = "%0.2f°%s" % (abs(lat), "N" if lat >= 0 else "S")
        speed_kt = 10.0 * w.believed_speed / max(1.0, w.max_speed)
        section("HIGH-SEAS POSITION", [lat_label + " / " + lon_label,
                "Plot: crew estimate" + (" / off sheet" if not player_on_sheet else ""),
                "Heading: %03d deg" % int(round(math.degrees(w.believed_heading) % 360)),
                "Speed: %.1f kt" % speed_kt])
        date = w.calendar_date()
        section("CAMPAIGN / TRAFFIC", ["Phase B / %02d-%02d / %02d h" % (date.month, date.day, int(w.hour())),
                "Fleet catalogue: %d" % len(self.traffic_world.ships),
                "Active vessels: %d / %d" % (len(self.traffic_world.lod.active_ids), self.traffic_world.lod.active_cap),
                "Known plots: %d" % len(contacts)])
        try:
            cell = self.world_weather_grid.sample(player_nm, sim_time_s=self.world.time)
            weather_lines = ["Wind: %.1f kt / %03.0f deg" % (cell.wind_speed_kt, cell.wind_direction_deg),
                             "Sea state: %.2f" % cell.sea_state,
                             "Cloud/rain/fog: %.2f / %.2f / %.2f" % (cell.cloud, cell.precipitation, cell.fog),
                             cell.phrase]
        except Exception:
            weather_lines = ["Regional weather unavailable", "Shipboard weather remains active"]
        section("REGIONAL WEATHER GRID", weather_lines)
        if selected_ship is not None:
            report = selected_ship.last_reported_position_nm
            if report is None:
                selected_lines = [selected_ship.callsign, "No position report", "Radio: unavailable"]
            else:
                age = selected_ship.report_age_s(now)
                distance = math.dist(player_nm, report)
                can_hail = distance <= float(selected_ship.radio_range_nm) and self.radio_station_ok()
                selected_lines = [selected_ship.callsign,
                                  "Plot range: %.1f nm" % distance,
                                  "Report: %s" % ("STALE" if selected_ship.report_stale_at(now) else "current-ish"),
                                  "Radio: %s" % ("in range" if distance <= selected_ship.radio_range_nm else "out of range"),
                                  "Report age: %s" % ("unknown" if not math.isfinite(age) else "%d game min" % int(age * 2.4))]
                if not self.radio_station_ok():
                    selected_lines.append("No radio operator at set")
            section("SELECTED CONTACT", selected_lines)
        section("ROUTE PLANNING", ["Click open water: add waypoint", "Shift-click: insert on leg",
                "Click waypoint: move / right-click: delete", "Waypoint coordinates convert back to ship plane",
                "Enter commits / Esc clears staged route"])
        section("CHART KEY", ["Triangle: last reported vessel plot", "? = stale / uncertain report",
                "Gold ring: selected contact", "Amber box: 1962 salmon fleet area",
                "Chart coastlines are schematic"])
        if self.chart_status and yy + 30 < side_rect.bottom - 10:
            self.screen.blit(self.chart_small_font.render(self.chart_status[:62], True, pal["landmark"]),
                             (inner_x, yy + 1))
        footer = self.chart_small_font.render(
            "A REGIONAL  ·  B HIGH SEAS  ·  R RADIO SELECTED  ·  ENTER COMMIT  ·  ESC CLEAR  ·  C CLOSE",
            True, pal["ink"])
        self.screen.blit(footer, (outer.x + 12, outer.bottom - 17))

    def draw_navigation_chart(self):
        """Draw the static 1962 chart and the live vessel/course markers."""
        if not self.chart_open:
            return
        if self._chart_dim_surface is None or self._chart_dim_surface.get_size() != (W, H):
            self._chart_dim_surface = pygame.Surface((W, H), pygame.SRCALPHA)
            self._chart_dim_surface.fill((5, 13, 16, 215))
        self.screen.blit(self._chart_dim_surface, (0, 0))
        pal = CHART_PALETTE
        outer = pygame.Rect(14, 10, W - 28, H - 20)
        pygame.draw.rect(self.screen, pal["paper"], outer)
        pygame.draw.rect(self.screen, pal["ink"], outer, 2)
        phase = getattr(self, "campaign_phase", "A")
        title_text = ("NORTH PACIFIC HIGH-SEAS CHART — 1962" if phase == "B"
                      else "NORTH PACIFIC — APPROACHES TO THE HARBOUR — 1962")
        title = self.chart_title_font.render(title_text, True, pal["ink"])
        self.screen.blit(title, (outer.x + 14, outer.y + 8))
        subtitle_text = ("PHASE B / WIDE-AREA PLOTS / APPROXIMATE COASTLINE — NOT A SURVEYED FIX" if phase == "B"
                         else "PHASE A / HAND-CORRECTED COASTAL SHEET / SOUNDINGS IN FATHOMS")
        subtitle = self.chart_small_font.render(subtitle_text, True, pal["ink"])
        self.screen.blit(subtitle, (outer.x + 16, outer.y + 34))
        # Phase tabs are shared by both chart sheets and are rebuilt at the current
        # viewport size so mouse input remains aligned after a resize.
        self._chart_phase_button_rects = {}
        tab_y = outer.y + 7
        b_rect = pygame.Rect(outer.right - 101, tab_y, 88, 25)
        a_rect = pygame.Rect(b_rect.x - 91, tab_y, 87, 25)
        for code, rect, label_text in (("A", a_rect, "A / REGIONAL"), ("B", b_rect, "B / HIGH SEAS")):
            fill = (168, 190, 177) if phase == code else (235, 224, 197)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            pygame.draw.rect(self.screen, pal["ink"], rect, 1, border_radius=3)
            label_surf = self.chart_small_font.render(label_text, True, pal["ink"])
            self.screen.blit(label_surf, (rect.centerx - label_surf.get_width() // 2,
                                          rect.centery - label_surf.get_height() // 2))
            self._chart_phase_button_rects[code] = rect

        map_x, map_y = outer.x + 10, outer.y + 54
        side_w = int(clamp(W * 0.185, 165, 250))
        gap = 9
        map_w = max(250, outer.w - 20 - side_w - gap)
        map_h = max(220, outer.h - 86)
        map_rect = pygame.Rect(map_x, map_y, map_w, map_h)
        side_rect = pygame.Rect(map_rect.right + gap, map_y, side_w, map_h)
        self._chart_map_rect = map_rect.copy()
        self._chart_outer_rect = outer.copy()
        if phase == "B":
            self._draw_phase_b_navigation_chart(map_rect, side_rect, outer)
            return
        if self._chart_base_surface is None or self._chart_cache_size != map_rect.size:
            self._chart_base_surface = self._build_navigation_chart_base(map_rect.size)
            self._chart_cache_size = map_rect.size
        chart_surface = self._chart_base_surface.copy()
        transform = self._chart_transform
        w = self.world

        def point(x, y):
            return chart_to_pixel(float(x), float(y), transform)

        ship_design = V(w.believed_pos) / w.scale
        ship_on_sheet = within_chart_bounds(ship_design.x, ship_design.y)
        ship_draw = clamp_to_chart_bounds(ship_design.x, ship_design.y, inset=250.0)

        # Show the staged course with numbered, editable marks and leg lengths. Route
        # points are drawn in chart coordinates, never from the screen click history.
        editor = self.chart_route_editor
        route_points = list(editor.points) if editor is not None else []
        if route_points:
            path = [(float(ship_design.x), float(ship_design.y))] + route_points
            for leg_i, (a, b) in enumerate(zip(path, path[1:])):
                clipped = clip_segment_to_bounds(a, b)
                if clipped is not None:
                    pygame.draw.line(chart_surface, pal["course"], point(*clipped[0]), point(*clipped[1]), 2)
                    mid = ((clipped[0][0] + clipped[1][0]) * 0.5, (clipped[0][1] + clipped[1][1]) * 0.5)
                    mx, my = point(*mid)
                    leg_nm = math.dist(a, b) / 185.2
                    leg_label = self.chart_small_font.render("%.1f nm" % leg_nm, True, pal["ink"])
                    chart_surface.blit(leg_label, (mx + 3, my + 3))
            for i, waypoint in enumerate(route_points):
                wxp, wyp = point(*waypoint)
                selected = self.chart_move_index == i
                radius = 9 if selected else 7
                color = pal["gold"] if selected else pal["paper"]
                pygame.draw.circle(chart_surface, pal["course"], (wxp, wyp), radius + 2, 1)
                pygame.draw.circle(chart_surface, color, (wxp, wyp), radius)
                pygame.draw.circle(chart_surface, pal["ink"], (wxp, wyp), radius, 1)
                label = self.chart_header_font.render(str(i + 1), True, pal["ink"])
                chart_surface.blit(label, (wxp - label.get_width() // 2, wyp - label.get_height() // 2))
        elif editor is not None:
            # Do not reveal an old manual destination after its staged route was
            # deleted. Auto-fishing may still display its own current steering target.
            if self.line.auto and w.destination is not None:
                destination = V(w.destination) / w.scale
                clipped = clip_segment_to_bounds((ship_design.x, ship_design.y), (destination.x, destination.y))
                if clipped is not None:
                    pygame.draw.line(chart_surface, pal["course"], point(*clipped[0]), point(*clipped[1]), 2)
                dx, dy = point(*clamp_to_chart_bounds(destination.x, destination.y, inset=250.0))
                pygame.draw.circle(chart_surface, pal["course"], (dx, dy), 7, 1)
                pygame.draw.line(chart_surface, pal["course"], (dx - 6, dy), (dx + 6, dy), 2)
                pygame.draw.line(chart_surface, pal["course"], (dx, dy - 6), (dx, dy + 6), 2)
        elif w.destination is not None:
            destination = V(w.destination) / w.scale
            clipped = clip_segment_to_bounds((ship_design.x, ship_design.y), (destination.x, destination.y))
            if clipped is not None:
                pygame.draw.line(chart_surface, pal["course"], point(*clipped[0]), point(*clipped[1]), 2)
            destination_draw = clamp_to_chart_bounds(destination.x, destination.y, inset=250.0)
            dx, dy = point(*destination_draw)
            pygame.draw.circle(chart_surface, pal["course"], (dx, dy), 7, 1)
            pygame.draw.line(chart_surface, pal["course"], (dx - 6, dy), (dx + 6, dy), 2)
            pygame.draw.line(chart_surface, pal["course"], (dx, dy - 6), (dx, dy + 6), 2)

        # Crew-estimated vessel marker; true ship position remains internal to physics.
        sx, sy = point(*ship_draw)
        angle = w.believed_heading
        ship_poly = [
            (sx + int(12 * math.cos(angle)), sy + int(12 * math.sin(angle))),
            (sx + int(-8 * math.cos(angle) - 6 * math.sin(angle)), sy + int(-8 * math.sin(angle) + 6 * math.cos(angle))),
            (sx + int(-8 * math.cos(angle) + 6 * math.sin(angle)), sy + int(-8 * math.sin(angle) - 6 * math.cos(angle))),
        ]
        # Show navigational doubt as a crew-estimated circle, not the hidden
        # true error vector or an exact true ship coordinate.
        if w.dr_uncertainty > 0.5:
            uncertainty_px = int(clamp((w.dr_uncertainty / w.scale) * transform[0],
                                       3.0, min(map_w, map_h) * 0.32))
            pygame.draw.circle(chart_surface, pal["gold"], (sx, sy), uncertainty_px, 1)
        pygame.draw.polygon(chart_surface, pal["ship"], ship_poly)
        pygame.draw.polygon(chart_surface, pal["ink"], ship_poly, 1)
        label_text = "VESSEL / DR" if ship_on_sheet else "VESSEL OFF SHEET"
        label = self.chart_small_font.render(label_text, True, pal["landmark"] if not ship_on_sheet else pal["ink"])
        chart_surface.blit(label, (max(3, min(map_w - label.get_width() - 3, sx + 12)),
                                   max(3, min(map_h - label.get_height() - 3, sy + 8))))

        # M8: the shared traffic entity supplies the Coast Guard marker; this
        # specialised layer draws only its reported towline and an off-sheet fallback.
        escort = getattr(self, "tow_escort", None)
        if escort is not None and escort.state in ("EN_ROUTE", "ALONGSIDE", "UNDER_TOW", "ARRIVED"):
            tow_report = tuple(float(v) for v in escort.reported_position)
            tow_on_sheet = within_chart_bounds(*tow_report)
            tow_color = pal.get("tow", (211, 105, 51))
            towline = clip_segment_to_bounds(ship_design, tow_report)
            if towline is not None and escort.state == "UNDER_TOW":
                a_px, b_px = point(*towline[0]), point(*towline[1])
                if escort.line_at_risk:
                    for seg_start, seg_end in dashed_segments(a_px, b_px, dash=8, gap=5):
                        pygame.draw.line(chart_surface, tow_color, seg_start, seg_end, 2)
                else:
                    pygame.draw.line(chart_surface, tow_color, a_px, b_px, 2)
            # Shared chart renderer clips regular reports at sheet edges; retain a
            # clearly labelled edge contact when the Coast Guard's report is outside.
            if not tow_on_sheet:
                tow_draw = clamp_to_chart_bounds(*tow_report, inset=250.0)
                tx, ty = point(*tow_draw)
                tow_angle = float(escort.heading)
                tow_tip = (tx + int(12 * math.cos(tow_angle)), ty + int(12 * math.sin(tow_angle)))
                tow_poly = [tow_tip,
                    (tx + int(-8 * math.cos(tow_angle) - 6 * math.sin(tow_angle)), ty + int(-8 * math.sin(tow_angle) + 6 * math.cos(tow_angle))),
                    (tx + int(-8 * math.cos(tow_angle) + 6 * math.sin(tow_angle)), ty + int(-8 * math.sin(tow_angle) - 6 * math.cos(tow_angle)))]
                pygame.draw.polygon(chart_surface, tow_color, tow_poly)
                pygame.draw.polygon(chart_surface, (245, 229, 188), tow_poly, 2)
                suffix = "?" if escort.marker_stale else ""
                tow_label = self.chart_small_font.render("CG %s%s OFF SHEET" % (escort.callsign, suffix), True, tow_color)
                chart_surface.blit(tow_label, (int(clamp(tx + 12, 2, map_w - tow_label.get_width() - 2)),
                                                int(clamp(ty - tow_label.get_height() - 5, 2, map_h - tow_label.get_height() - 2))))
        # Render one reported contact for every known identity, including the escort.
        self.draw_traffic_chart_contacts(chart_surface, point, map_w, map_h, pal)

        # V13V1-14: current crew gut plots are separate from unconfirmed radio/fleet
        # reports. Their location is transformed through the current DR error; never
        # draw the hidden physical hotspot coordinate directly.
        live_spots = {id(spot): spot for spot in w.hotspots}
        gut_contacts = {}
        for lookout in self.sailors:
            spot = getattr(lookout, "gut_spot", None)
            confidence = float(getattr(lookout, "gut_confidence", 0.0))
            if (spot is None or id(spot) not in live_spots or confidence < GUT_BOOK_CONFIDENCE_THRESHOLD
                    or lookout.mode != Sailor.ABOARD or lookout.level != Level.MAIN):
                continue
            old = gut_contacts.get(id(spot))
            if old is None or confidence > old[0]:
                gut_contacts[id(spot)] = (confidence, lookout)
        for spot_id, (confidence, lookout) in gut_contacts.items():
            spot = live_spots[spot_id]
            gx, gy = estimated_hotspot_destination(spot.pos, w.position_error)
            gx, gy = gx / max(0.001, w.scale), gy / max(0.001, w.scale)
            if not within_chart_bounds(gx, gy):
                continue
            cx, cy = point(gx, gy)
            radius = int(clamp(5 + 4 * confidence, 6, 10))
            diamond = [(cx, cy - radius), (cx + radius, cy),
                       (cx, cy + radius), (cx - radius, cy)]
            gut_ink = (245, 224, 130)
            pygame.draw.polygon(chart_surface, gut_ink, diamond, 2)
            pygame.draw.circle(chart_surface, gut_ink, (cx, cy), max(2, radius // 3), 1)
            gut_id = int(getattr(spot, "gut_book_entry_id", 0) or 0)
            marker_label = self.chart_small_font.render("G%02d" % (gut_id % 100), True, gut_ink)
            label_x = int(clamp(cx + radius + 3, 2, map_w - marker_label.get_width() - 2))
            label_y = int(clamp(cy - marker_label.get_height() - 3, 2, map_h - marker_label.get_height() - 2))
            chart_surface.blit(marker_label, (label_x, label_y))

        # V13V1-12: report markers are leads, not true hotspot markers. Their
        # appearance encodes reported source confidence/age only, never truth.
        chart_reports = sorted(w.fishing_reports, key=lambda item: item.age)[:MAX_CHART_REPORTS]
        for report in chart_reports:
            if not within_chart_bounds(report.x, report.y):
                continue
            rx, ry = point(report.x, report.y)
            age_fraction = report.age / max(1.0, report.lifetime)
            ink = report_map_color(report.confidence, age_fraction)
            uncertainty_r = int(clamp(report.accuracy_radius * transform[0], 4, 18))
            pygame.draw.circle(chart_surface, ink, (rx, ry), uncertainty_r, 1)
            pygame.draw.circle(chart_surface, pal["paper"], (rx, ry), 6)
            pygame.draw.circle(chart_surface, ink, (rx, ry), 6, 2)
            question = self.chart_small_font.render("?", True, ink)
            chart_surface.blit(question, (rx - question.get_width() // 2, ry - question.get_height() // 2))
            marker_label = self.chart_small_font.render("R%d" % (report.report_id % 100), True, ink)
            label_x = int(clamp(rx + 8, 2, map_w - marker_label.get_width() - 2))
            label_y = int(clamp(ry - marker_label.get_height() - 4, 2, map_h - marker_label.get_height() - 2))
            chart_surface.blit(marker_label, (label_x, label_y))
        self.screen.blit(chart_surface, map_rect.topleft)
        pygame.draw.rect(self.screen, pal["ink"], map_rect, 2)

        pygame.draw.rect(self.screen, (231, 220, 193), side_rect)
        pygame.draw.rect(self.screen, pal["ink"], side_rect, 1)
        inner_x, yy = side_rect.x + 10, side_rect.y + 8
        def section(header, lines):
            nonlocal yy
            needed = 17 + 15 * len(lines) + 5
            # On short windows, keep every visible line inside the card instead of
            # letting the final section spill over the chart/footer.
            if yy + needed > side_rect.bottom - 24:
                return False
            self.screen.blit(self.chart_header_font.render(header, True, pal["landmark"]), (inner_x, yy))
            yy += 17
            for content in lines:
                fitted = content
                max_width = side_rect.w - 20
                while fitted and self.chart_font.size(fitted)[0] > max_width:
                    fitted = fitted[:-1]
                if fitted != content:
                    fitted = fitted.rstrip() + "…"
                self.screen.blit(self.chart_font.render(fitted, True, pal["ink"]), (inner_x, yy))
                yy += 15
            yy += 5
            return True

        speed_kt = 10.0 * w.believed_speed / max(1.0, w.max_speed)
        heading_deg = int(round(math.degrees(w.believed_heading) % 360))
        if self.chart_route_editor is not None and self.chart_route_editor.points:
            first = self.chart_route_editor.points[0]
            distance_nm = math.dist((ship_design.x, ship_design.y), first) / 185.2
            destination_lines = ["Course: %d WAYPOINT(S)" % len(self.chart_route_editor.points),
                                 "First leg: %.1f nm" % distance_nm]
        elif self.line.auto and w.destination is not None:
            distance_nm = (w.believed_pos.distance_to(w.destination) / max(0.001, w.scale)) / 185.2
            destination_lines = ["Course: AUTO-FISHING", "Range: %.1f nm" % distance_nm]
        else:
            destination_lines = ["Course: NO MANUAL ROUTE", "Steering: current heading"]
        section("POSITION / COURSE", ["Position: crew estimate", "Heading: %03d deg" % heading_deg,
                                        "Speed: %.1f kt" % speed_kt,
                                        "Doubt: +/- %d units" % round(w.dr_uncertainty),
                                        "Last fix: %s (%s)" % (w.fix_age_text(), w.last_fix_method)] + destination_lines)
        section("CONDITIONS", ["Visibility: %.1f km" % self.weather.visibility_km(),
                               "Sea state: %.2f" % w.sea_state,
                               "Wind: %s %d kt" % (self.weather.wind_from(), self.weather.wind_kt())])
        escort = getattr(self, "tow_escort", None)
        if escort is not None:
            age = escort.report_age_game_minutes
            section("COAST GUARD ESCORT", [
                "%s / %s" % (escort.callsign, escort.captain_name),
                "State: %s" % escort.state.replace("_", " "),
                "Plot age: %d game min%s" % (age, " (STALE)" if escort.marker_stale else ""),
                "Crew: %s" % ", ".join(member.name.rsplit(" ", 1)[-1] for member in escort.crew),
                "F4: position check / G: ask captain",
            ])
        report_lines = []
        for report in sorted(w.fishing_reports, key=lambda item: item.age)[:3]:
            report_lines.append("R%d %s %s %d%% %s" % (
                report.report_id % 100, report.species_tag, report.short_age,
                round(report.confidence * 100), report.source_tag,
            ))
        if not report_lines:
            report_lines = ["No reports received yet", "Check again after more time at sea"]
        report_lines.append("Leads may be false or stale")
        section("FISHING SPOT REPORTS (?)", report_lines)
        section("POSITION FIXES (PRESS 1–4)", self._navigation_fix_status_lines())
        section("CHART KEY", ["Cream: land / coastline", "Numbers: charted fathoms",
                              "G# diamond: crew gut plot (DR)", "R# ring: unconfirmed report",
                              "Orange triangle: Coast Guard", "? = stale Coast Guard report",
                              "Orange line: towline; dashed = strain", "Red line: plotted course"])
        route_lines = ["Waypoints: %d / %d" % (len(route_points), MAX_CHART_WAYPOINTS),
                       "Left-click: add / select move", "Shift-click: insert on a leg",
                       "Right-click point: delete", "Enter: commit / Esc: clear"]
        section("ROUTE PLAN", route_lines)
        section("SURVEY STATUS", ["Known radius: 6,000 units (32 nm)", "Beyond edge: UNCHARTED",
                                  "Magnetic variation: 6 deg E", "Reports are leads, not facts"])
        if self.chart_status and yy + 32 < side_rect.bottom - 20:
            status = self.chart_small_font.render(self.chart_status[:62], True, pal["landmark"])
            self.screen.blit(status, (inner_x, yy + 1))
        help_surf = self.chart_small_font.render(
            "FIX 1 LANDMARK  2 SEXTANT  3 RDF  4 SOUNDER  •  ENTER COMMIT  •  ESC CLEAR  •  C CLOSE",
            True, pal["ink"])
        self.screen.blit(help_surf, (outer.x + 12, outer.bottom - 17))

    def draw_auction_modal(self):
        if not self.auction_active:
            return
        shade = self._cached_panel_surface((W, H), (0, 0, 0, 215))
        self.screen.blit(shade, (0, 0))
        width, height = min(W - 40, 900), min(H - 40, 620)
        x, y = (W - width) // 2, (H - height) // 2
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (18, 29, 34), rect, border_radius=12)
        pygame.draw.rect(self.screen, (211, 180, 112), rect, width=2, border_radius=12)
        def line(txt, yy, color=(240, 234, 213), bold=False):
            font = self.auction_title_font if bold else self.auction_font
            self.screen.blit(font.render(txt, True, color), (x + 24, yy))
        if not self.hold or self.auction_index >= len(self.hold):
            line("AUCTION COMPLETE", y + 35, (255, 225, 154), True)
            line("Press any key to return to the harbour.", y + 80)
            return
        fish = self.hold[self.auction_index]
        line("HARBOUR FISH AUCTION  —  FISH %d / %d" % (self.auction_index + 1, len(self.hold)), y + 24, (255, 225, 154), True)
        line("%s  |  Grade %s  |  Quality %.2f  |  Base %d yen" % (fish.name.title(), fish.grade(), fish.quality, fish.sale_value()), y + 60)
        line("Market x%.2f  |  Sold %d  |  Session proceeds %d yen" % (self.market, self.auction_session_sold, self.auction_session_total), y + 88)
        line("OFFERS  (press 1–4 to sell to that buyer)", y + 132, (188, 222, 211), True)
        for i, (buyer, price, note) in enumerate(self.auction_offers[:4]):
            line("%d. %-20s %8d yen   — %s" % (i + 1, buyer, price, note), y + 168 + i * 34,
                 (255, 230, 165) if i == 0 else (230, 231, 220))
        line("K / ESC: keep this fish   A: accept best offers for all remaining fish", y + height - 76, (180, 216, 195))
        line("LEFT / RIGHT: browse fish     World simulation paused during auction", y + height - 46, (170, 188, 193))

    # --- weather: cloud shadow and gloom, fog, rain and lightning
    def _cloud_tex(self):
        """A seamless 1024px map of cloud shadow, built once."""
        if self._cloud is None:
            n, per = 80, 64
            small = pygame.Surface((n, n), pygame.SRCALPHA)
            rnd = random.Random(7)
            waves = [(rnd.randint(1, 3), rnd.randint(0, 3), rnd.uniform(0, TAU), 1.0), (rnd.randint(0, 3), rnd.randint(1, 3), rnd.uniform(0, TAU), 0.8),
                     (rnd.randint(2, 5), rnd.randint(2, 5), rnd.uniform(0, TAU), 0.5), (rnd.randint(3, 7), rnd.randint(1, 6), rnd.uniform(0, TAU), 0.3)]
            for y in range(n):
                for x in range(n):
                    v = sum(a * math.sin(TAU * (kx * x + ky * y) / per + ph) for kx, ky, ph, a in waves) / 2.6
                    small.set_at((x, y), (18, 28, 42, int(255 * smoothstep(0.05, 0.75, v))))
            big = pygame.transform.smoothscale(small, (n * 16, n * 16))
            self._cloud = big.subsurface((128, 128, 1024, 1024)).copy()
        return self._cloud

    def _fog_surf(self, b):
        key = (W, H, b)
        sf = self._fog_cache.get(key)
        if sf is None:
            sw, sh, steps = 96, 60, 40
            small = pygame.Surface((sw, sh), pygame.SRCALPHA)
            r0 = lerp(0.50, 0.08, b / 5.0)
            for i in range(steps):                            # outermost ring first, clear towards the middle
                rho = 1.45 * (1.0 - i / steps)
                a = int(255 * smoothstep(r0, 1.0, rho))
                pygame.draw.ellipse(small, (205, 212, 216, a), (sw / 2 - rho * sw / 2, sh / 2 - rho * sh / 2, rho * sw, rho * sh))
            if len(self._fog_cache) > 24:
                self._fog_cache.clear()
            sf = self._fog_cache[key] = pygame.transform.smoothscale(small, (W, H))
        return sf

    def draw_weather(self):
        wx, w, s = self.weather, self.world, self.screen
        dt = min(self.clock.get_time() / 1000.0, 0.05)
        day = w.daylight()
        gloom = 80 * wx.cloud * (0.35 + 0.65 * day) + 50 * wx.rain
        if gloom > 2:
            self.wx_tint.fill((34, 44, 58))
            self.wx_tint.set_alpha(int(gloom))
            s.blit(self.wx_tint, (0, 0))
        if wx.cloud > 0.2:                                    # shadows of clouds drifting past, higher up than the ship
            tex = self._cloud_tex()
            tex.set_alpha(int(120 * wx.cloud ** 1.3))
            drift = V(1, 0).rotate_rad(wx.wind_dir - w.heading) * (w.time * 22.0 * (0.4 + wx.wind))
            off = w.deck_of(V(0, 0)) * 0.12 * self.zoom + drift
            ox, oy = int(off.x % 1024) - 1024, int(off.y % 1024) - 1024
            for x in range(ox, W, 1024):
                for y in range(oy, H, 1024):
                    s.blit(tex, (x, y))
        if wx.fog > 0.03:
            self.wx_tint.fill((205, 212, 216))
            self.wx_tint.set_alpha(int(150 * wx.fog))
            s.blit(self.wx_tint, (0, 0))
            fs = self._fog_surf(int(clamp(wx.fog, 0.0, 1.0) * 5))
            fs.set_alpha(int(255 * clamp(wx.fog * 1.15, 0.0, 1.0)))
            s.blit(fs, (0, 0))
        if wx.rain > 0.03:
            wind = V(1, 0).rotate_rad(wx.wind_dir - w.heading)
            d = (wind * 0.45 + V(0.1, 0.9)).normalize()
            n, sp, ln = int(380 * wx.rain), 1000.0 * (0.8 + 0.4 * wx.wind), 12 + 16 * wx.rain
            drops = self._drops
            while len(drops) < n:
                drops.append([random.uniform(0, W), random.uniform(0, H), random.uniform(0.7, 1.3)])
            del drops[n:]
            col = mix((150, 170, 192), (205, 220, 235), wx.rain)
            for p in drops:
                p[0] = (p[0] + d.x * sp * p[2] * dt) % W
                p[1] = (p[1] + d.y * sp * p[2] * dt) % H
                pygame.draw.line(s, col, (p[0], p[1]), (p[0] - d.x * ln * p[2], p[1] - d.y * ln * p[2]), 1)
            if random.random() < wx.rain * dt * 60 * 0.6:       # ripples where the drops land
                for _ in range(max(1, int(wx.rain * 3))):
                    self._ripples.append([random.uniform(0, W), random.uniform(0, H), 0.0])
            for r in self._ripples:
                r[2] += dt
                if r[2] < 0.55:
                    pygame.draw.circle(s, mix((235, 242, 248), (120, 156, 176), r[2] / 0.55), (int(r[0]), int(r[1])), int(2 + r[2] * 22 * self.zoom ** 0.5), 1)
            self._ripples = [r for r in self._ripples if r[2] < 0.55][-160:]
        else:
            self._drops, self._ripples = [], []

    def draw_lightning(self):
        wx, s = self.weather, self.screen
        if wx.bolt_t > 0 and wx.bolt:
            pts = [(x * W, y * H) for x, y in wx.bolt]
            pygame.draw.lines(s, (150, 170, 255), False, pts, 7)
            pygame.draw.lines(s, (255, 255, 255), False, pts, 3)
        if wx.flash > 0.02:
            self.wx_flash.set_alpha(int(150 * wx.flash))
            s.blit(self.wx_flash, (0, 0))

    def weather_text(self):
        return self.weather.text()

    # --- day and night: a dark blue veil over everything, with the lamps punched through it
    def _glow(self, r):
        r = int(clamp(r, 8, 480) // 8 * 8 + 8)
        sf = self._glows.get(r)
        if sf is None:
            if len(self._glows) > 48:
                self._glows.clear()
            sf = pygame.Surface((2 * r, 2 * r), pygame.SRCALPHA)
            steps = 26
            for i in range(steps):                  # concentric discs, clearer towards the middle
                k = i / (steps - 1)
                pygame.draw.circle(sf, (0, 0, 0, int(250 * k ** 1.5)), (r, r), max(1, int(r * (1.0 - 0.98 * k))))
            self._glows[r] = sf
        return sf

    def _lights(self):
        """(screen position, radius in px) for every lamp."""
        z, w, m = self.zoom, self.world, self.ship.markers
        out = [(self.SS(m["haul_station"]), 330 * z), (self.SS(m["stern_set"] + V(60, 0)), 330 * z),
               (self.SS(m["table_stand"]), 300 * z), (self.SS(m["hatch_1"]), 280 * z),
               (self.SS(m["captain_post"]), 330 * z), (self.SS(m["bow_lookout"]), 260 * z)]
        out.append((self.S(w.deck_of(w.bw_b)), 700 * z))                    # the lighthouse
        for x in (-150, 0, 150, 300, 450):                                  # lamps along the quay
            out.append((w.dsp((x, -372)), 110 * w.scale * z))
        out += w.town_lights(self)
        for wp in self.line.end_buoys():                                    # the marker buoys carry lamps
            out.append((self.S(w.deck_of(wp)), 160 * z))
        return out

    def draw_night(self):
        w = self.world
        d = w.daylight()
        dark = 1.0 - d
        twi = 4.0 * d * (1.0 - d)                                           # peaks at dusk and dawn
        lay = self.night_layer
        if twi > 0.03:
            lay.fill((255, 130, 60, int(46 * twi)))
            self.screen.blit(lay, (0, 0))
        if dark < 0.03:
            return
        lay.fill((6, 12, 34, int(195 * dark)))
        for pos, r in self._lights():
            if -r < pos[0] < W + r and -r < pos[1] < H + r:
                g = self._glow(r)
                gr = g.get_width() // 2
                lay.blit(g, (pos[0] - gr, pos[1] - gr), special_flags=pygame.BLEND_RGBA_SUB)
        self.screen.blit(lay, (0, 0))
        if dark < 0.3:
            return
        ov, z, t = self.ov_d, self.zoom, w.time
        ov.fill((0, 0, 0, 0))
        lh = V(self.S(w.deck_of(w.bw_b)))                                   # the lighthouse beam sweeps round
        a = t * 0.9
        for spread, al in ((0.10, 40), (0.04, 70)):                          # a wide faint beam and a narrow bright one
            pts = [lh, lh + V(2600 * z, 0).rotate_rad(a - spread), lh + V(2600 * z, 0).rotate_rad(a + spread)]
            pygame.draw.polygon(ov, (255, 244, 190, int(al * dark)), pts)
        L, B = self.ship.length, self.ship.beam                             # navigation lights: red port, green starboard, white masthead
        for p, col in ((V(L * 0.42, -B * 0.28), (230, 40, 40)), (V(L * 0.42, B * 0.28), (50, 220, 90)), (V(L * 0.10, 0), (255, 255, 235))):
            c = self.SS(p)
            pygame.draw.circle(ov, col + (int(70 * dark),), c, max(6, int(34 * z)))
            pygame.draw.circle(ov, col + (255,), c, max(2, int(9 * z)))
        for wp in self.line.end_buoys():
            if int(t * 2) % 2 == 0:
                pygame.draw.circle(ov, (255, 230, 150, 230), self.S(w.deck_of(wp)), max(3, int(12 * z)))
        self.screen.blit(ov, (0, 0))
        ov.fill((0, 0, 0, 0))

    def _bar_y(self):
        """Keep the fishing minigame higher in the play area, with extra room on short windows."""
        # Reserve a compact strip at the very top; never let controls push it down.
        target = min(58, int(H * 0.52))
        # The former lower placement used clamp(target, 72, max(72, H - 96));
        # 12v13 intentionally lowers that minimum to 42 to pin the UI at the top.
        return int(clamp(target, 42, max(42, H - 96)))

    def _fishing_bar_geometry(self, requested_width):
        """Fit the fishing controls between the left telemetry card and the screen edges."""
        y = self._bar_y()
        bw = min(420, max(300, int(W * 0.70) - 40), max(140, W - 20),
                 max(140, int(requested_width) if requested_width else 420))
        x = (W - bw) // 2
        if self.telemetry_visible and self.telemetry_panel_rect.bottom > y - 24:
            left = self.telemetry_panel_rect.right + 8
            right = W - 10
            safe_width = right - left
            if safe_width >= 260:
                bw = min(bw, safe_width)
                x = left + (safe_width - bw) // 2
            else:
                x = left
                bw = min(bw, max(140, W - x - 10))
        else:
            x = max(10, min(x, W - bw - 10))
        return int(bw), int(x), int(y)

    def draw_tension(self):
        f = self.line.fight
        if f is None or not self.show_fishing_minigame:
            return
        bw, x, y = self._fishing_bar_geometry(min(420, max(300, int(W * 0.70) - 40)))
        bh = 20
        s = self.screen
        pygame.draw.rect(s, (20, 24, 28), (x - 4, y - 24, bw + 8, 82))
        k = bw / 1.3
        pygame.draw.rect(s, (70, 40, 38), (x, y, bw, bh))
        pygame.draw.rect(s, (60, 130, 70), (x + f.LO * k, y, (f.HI - f.LO) * k, bh))
        pygame.draw.rect(s, (150, 120, 40), (x + f.HI * k, y, (0.92 - f.HI) * k, bh))
        pygame.draw.rect(s, (235, 235, 235), (x, y, bw, bh), 2)
        nx = x + clamp(f.tension, 0.0, 1.3) * k
        pygame.draw.line(s, (255, 255, 255), (nx, y - 5), (nx, y + bh + 5), 4)
        self.text("%s  tension %.2f  (%s)" % (f.name.upper(), f.tension, "YOU on the brake" if f.manual else "crew on the brake"), (x, y - 22))
        pygame.draw.rect(s, (40, 44, 48), (x, y + bh + 8, bw, 8))
        pygame.draw.rect(s, (200, 170, 90), (x, y + bh + 8, bw * clamp(f.stamina, 0.0, 1.0), 8))
        self.text("fish stamina    Z ease off    X tighten", (x, y + bh + 20))
        if f.slack_t > 0.4:
            self.text("SLACK - he'll throw the hook!", (x + bw // 2 - 120, y - 46), (255, 200, 90))
        elif f.strain_t > 0.3:
            self.text("TOO TIGHT - the line will part!", (x + bw // 2 - 130, y - 46), (255, 90, 80))

    def draw_gaff(self):
        ln = self.line
        gf = ln.gaff
        if not self.show_fishing_minigame:
            return
        if ln.phase != Longline.HAULING or gf is None or not ln.pts or ln.pts[0] is not gf["hook"]:
            return
        bw, x, y = self._fishing_bar_geometry(min(420, max(300, int(W * 0.70) - 40)))
        bh = 18
        s = self.screen
        pygame.draw.rect(s, (20, 24, 28), (x - 4, y - 24, bw + 8, 62))
        pygame.draw.rect(s, (40, 44, 48), (x, y, bw, bh))
        pygame.draw.rect(s, (205, 90, 70) if gf["thrash"] > 0 else (110, 170, 120), (x, y, bw * clamp(gf["prog"], 0.0, 1.0), bh))
        pygame.draw.rect(s, (235, 235, 235), (x, y, bw, bh), 2)
        self.text("GAFFING %s%s   SPACE: heave" % (gf["hook"]["name"].upper(), "" if self.gaffs > 0 else " (no gaff!)"), (x, y - 22))
        if gf["thrash"] > 0:
            self.text("IT'S THRASHING - mind your hands!", (x, y + bh + 4), (255, 150, 110))

    def draw_longline_debug_minimap(self):
        """Developer-only line overview; never drawn in the normal immersive view."""
        rect = pygame.Rect(12, 96, 210, 130)
        pygame.draw.rect(self.screen, (18, 27, 31), rect)
        pygame.draw.rect(self.screen, (180, 130, 70), rect, 1)
        self.screen.blit(self.hud_compact_font.render("DEBUG: LONGLINE MAP", True, (235, 205, 130)), (rect.x + 6, rect.y + 5))
        pts = self.line.pts
        if len(pts) > 1:
            coords = []
            for point in pts:
                pos = point.get("pos") if isinstance(point, dict) else None
                if pos is not None:
                    coords.append((rect.x + rect.w / 2 + pos.x * 0.025, rect.y + rect.h / 2 + pos.y * 0.025))
            if len(coords) > 1:
                pygame.draw.lines(self.screen, (225, 185, 90), False, coords, 1)

    def draw_profile(self):
        """Compact side view of the water column, repositioned after removal of the minimap."""
        self.profile_rect = pygame.Rect(0, 0, 0, 0)
        if H < 500:
            return
        if W < 900 and self.show_fishing_minigame and (self.line.fight is not None or self.line.gaff is not None):
            return
        ln, w, s = self.line, self.world, self.screen
        profile_w = min(240, max(180, W // 3))
        rect = pygame.Rect(W - profile_w - 10, 82, profile_w, 110)  # moved down 20 px in v13v1-04
        self.profile_rect = rect
        if rect.bottom > H - 12:
            return
        dmax = 500.0
        d0 = ln.pts[len(ln.pts) // 2]["pos"].distance_to(HARBOUR) / w.scale if ln.pts else w.dist()
        surface_temp = w.surface_temp(d0)
        thermocline = w.thermocline(d0)
        profile_key = (profile_w, rect.h, int(d0 // 50.0), int(surface_temp), int(thermocline // 5.0))
        profile_bg = self._profile_background_cache.get(profile_key)
        if profile_bg is None:
            profile_bg = pygame.Surface((profile_w, rect.h)).convert()
            for yy in range(0, rect.h, 4):
                t = w.temp_at(yy / rect.h * dmax, d0)
                pygame.draw.rect(profile_bg,
                                 mix((14, 40, 72), (70, 150, 150), clamp((t - 5.0) / 18.0, 0.0, 1.0)),
                                 (0, yy, profile_w, min(4, rect.h - yy)))
            self._profile_background_cache[profile_key] = profile_bg
            if len(self._profile_background_cache) > 48:
                self._profile_background_cache.popitem(last=False)
        else:
            self._profile_background_cache.move_to_end(profile_key)
        s.blit(profile_bg, rect.topleft)
        bot = w.bottom_m(d0)
        if bot < dmax:
            by = rect.y + int(bot / dmax * rect.h)
            pygame.draw.rect(s, (84, 70, 50), (rect.x, by, rect.w, rect.bottom - by))
        ty = rect.y + int(clamp(thermocline / dmax, 0.0, 1.0) * rect.h)
        pygame.draw.line(s, (240, 220, 140), (rect.x, ty), (rect.right, ty), 1)
        n = len(ln.pts)
        if n >= 2:
            def pt(i, p):
                return (rect.x + 8 + (rect.w - 16) * i / (n - 1), rect.y + clamp(p["z"] * DEPTH_M / dmax, 0.0, 1.0) * rect.h)
            pygame.draw.lines(s, (235, 230, 210), False, [pt(i, p) for i, p in enumerate(ln.pts)], 2)
            for i, p in enumerate(ln.pts):
                c = pt(i, p)
                if p["float"]:
                    pygame.draw.circle(s, (217, 83, 30), c, 4)
                elif p["fish"]:
                    pygame.draw.circle(s, FISH_DOT.get(p.get("name"), (200, 220, 235)), c, 4)
                else:
                    pygame.draw.circle(s, GOLD, c, 2)
        pygame.draw.rect(s, (235, 235, 235), rect, 2)
        self.text(self._fit("DEPTH 0-%dm  x%.2f" % (dmax, ln.slack), rect.w), (rect.x, rect.y - 20))
        self.text("%dm" % bot if bot < dmax else "", (rect.x + 4, rect.bottom - 18), (255, 235, 170))

    def draw_lifelines(self):
        """A rope from the rescuer to the swimmer, with an orange ring on the end."""
        s, z = self.screen, self.zoom
        for r in self.sailors:
            sw = r.rescue_target
            if r.mode != Sailor.ABOARD or sw is None or sw.mode != Sailor.SWIMMING or r.line_state not in ("throw", "haul"):
                continue
            a, b = V(self.SS(r.pos)), V(self.S(sw.pos))
            t = clamp(r.rescue_t / max(r.throw_time(), 0.01), 0.0, 1.0) if r.line_state == "throw" else 1.0
            end = a.lerp(b, t)
            pygame.draw.line(s, (235, 230, 210), a, end, max(1, int(3 * z * 2)))
            rr = max(4, int(11 * r.scale * z))
            pygame.draw.circle(s, (217, 83, 30), end, rr, max(2, rr // 2))
            pygame.draw.circle(s, (240, 240, 240), end, rr, 1)

    def _column_w(self):
        """Width of each side HUD column. The centre play area is at least 600px or 70% of the window."""
        centre = max(600, int(W * 0.70))
        return int(clamp((W - centre - 24) / 2, 250, 300))

    def _panel_lines(self, rect, header, lines, head_color=GOLD):
        self.panel(rect, lines, header=header, header_color=head_color)

    def _dr_telemetry_line(self):
        w = self.world
        return "DR DOUBT +/- %du | FIX %s" % (round(w.dr_uncertainty), w.fix_age_text())

    def _compact_hud_lines(self):
        """Three compact lines: operation/navigation, conditions, and DR doubt."""
        w = self.world
        if self.hud_mode == "operations":
            phase = {Longline.IDLE: "LINE IDLE", Longline.SETTING: "LINE SET",
                     Longline.SOAKING: "LINE SOAK", Longline.HAULING: "LINE HAUL"}.get(self.line.phase, "LINE ?")
            alerts = []
            if self.crew.alarm_target is not None:
                alerts.append("MAN OVERBOARD")
            if self.muster_active:
                alerts.append("MUSTER %d/%d" % (len(self.muster_reports), len(self.muster_expected)))
            if self.ship.flood_state in ("FLOODED", "CRITICAL"):
                alerts.append("FLOODING")
            if abs(self.ship.list_trim) >= 0.22:
                alerts.append("LIST %d%s" % (round(abs(self.ship.list_trim) * FloodingModel.DEGREES_PER_LIST),
                                             "S" if self.ship.list_trim > 0 else "P"))
            if self.ship.engine_flood >= 0.40:
                alerts.append("BILGE HIGH")
            if self.ship.wet >= 0.80 or self.ship.flood >= 0.40:
                alerts.append("DECK FLOOD")
            if self.engine_ok is False or self.fuel <= 0:
                alerts.append("ENGINE FAULT")
            trip = self.line.trip_hud()
            second = " / ".join(alerts[:2]) if alerts else "%sHOLD %d FISH | FUEL %d%%" % (
                (trip + " | ") if trip else "", len(self.hold), round(100 * self.fuel / max(1, FUEL_CAP)))
            depth = int(self.world.bottom_m(self.world.dist()))
            return [phase + " | ENG " + ("OK" if self.engine_ok and self.fuel > 0 else "CHECK"),
                    second, self._dr_telemetry_line(), "DEPTH %dm" % depth]

        weather_flag = "STORM" if w.sea_state >= 0.75 else ("ROUGH" if w.sea_state >= 0.55 else self.weather.label().upper())
        speed_kt = 10.0 * w.believed_speed / max(1.0, w.max_speed)
        heading = int(round(math.degrees(w.believed_heading) % 360))
        depth = int(w.bottom_m(w.dist()))
        return ["SPD %.1f kt  HDG %03d deg" % (speed_kt, heading),
                "SEA %.2f  %s" % (w.sea_state, weather_flag),
                self._dr_telemetry_line(), "DEPTH %dm" % depth]

    def draw_telemetry_panel(self):
        """Small essential-only HUD; F7 switches content and F8 hides it without losing controls."""
        margin = 10
        if not self.telemetry_visible:
            rect = pygame.Rect(margin, margin, 62, 22)
            self.telemetry_panel_rect = rect
            self.telemetry_tab_hitboxes = {}
            tab = self._cached_panel_surface((rect.w, rect.h), self.PANEL_BG[:3],
                                             border=self.PANEL_BORDER, border_width=1, radius=4)
            self.screen.blit(tab, rect.topleft)
            self.screen.blit(self.hud_compact_font.render("HUD F8", True, (235, 235, 220)), (rect.x + 6, rect.y + 3))
            return

        lines = self._compact_hud_lines()
        panel_w = min(230, max(194, W - 20))
        line_h = 17
        panel_h = 8 + len(lines) * line_h + 8
        rect = pygame.Rect(margin, margin, panel_w, min(panel_h, max(42, H - 20)))
        self.telemetry_panel_rect = rect
        self.telemetry_tab_hitboxes = {}
        card = self._cached_panel_surface((rect.w, rect.h), (8, 12, 18, 205),
                                          border=self.PANEL_BORDER, border_width=1, radius=5)
        self.screen.blit(card, rect.topleft)
        clip = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-4, -4))
        for i, line in enumerate(lines):
            if self.hud_compact_font.size(line)[0] > rect.w - 14:
                while line and self.hud_compact_font.size(line + "…")[0] > rect.w - 14:
                    line = line[:-1]
                line = line.rstrip() + "…"
            colour = (255, 220, 120) if (("MAN OVERBOARD" in line) or ("BILGE HIGH" in line) or ("FLOODING" in line)
                    or ("DECK FLOOD" in line) or ("ENGINE FAULT" in line) or ("STORM" in line)) else (238, 242, 235)
            self.screen.blit(self.hud_compact_font.render(line, True, colour), (rect.x + 7, rect.y + 5 + i * line_h))
        self.screen.set_clip(clip)

    def draw_money_counter(self):
        """Persistent balance card; unlike telemetry it remains visible when F8 hides the compact HUD."""
        width = min(220, max(172, W // 3))
        rect = pygame.Rect(W - width - 10, 10, width, 44)
        self.money_hud_rect = rect
        card = self._cached_panel_surface((rect.w, rect.h), self.PANEL_BG[:3],
                                          border=(218, 185, 105), border_width=1, radius=5)
        self.screen.blit(card, rect.topleft)
        balance = self.hud_compact_font.render("CASH  ¥%s" % f"{self.cash:,}", True, (255, 226, 130))
        earned = self.chart_small_font.render("TOTAL EARNED  ¥%s" % f"{self.earned:,}", True, (218, 226, 218))
        self.screen.blit(balance, (rect.x + 8, rect.y + 5))
        self.screen.blit(earned, (rect.x + 8, rect.y + 25))
        # Separate compact anchor button immediately beside the cash HUD.
        ax = max(8, rect.x - 82)
        self.anchor_hud_rect = pygame.Rect(ax, rect.y, min(72, max(52, rect.x - 10)), rect.h)
        anchor_bg = (91, 70, 39) if self.anchor_deployed else self.PANEL_BG[:3]
        anchor_border = (255, 202, 100) if self.anchor_deployed else (125, 145, 139)
        anchor_card = self._cached_panel_surface((self.anchor_hud_rect.w, self.anchor_hud_rect.h), anchor_bg,
                                                 border=anchor_border, border_width=2 if self.anchor_deployed else 1, radius=5)
        self.screen.blit(anchor_card, self.anchor_hud_rect.topleft)
        label = "ANCHOR" if self.anchor_deployed else "ANCHOR"
        state = "DOWN" if self.anchor_deployed else "UP"
        self.screen.blit(self.hud_compact_font.render(label, True, (245, 231, 192)),
                         (self.anchor_hud_rect.x + 5, self.anchor_hud_rect.y + 5))
        self.screen.blit(self.chart_small_font.render(state, True, (255, 205, 110) if self.anchor_deployed else (205, 220, 215)),
                         (self.anchor_hud_rect.x + 5, self.anchor_hud_rect.y + 25))
        rx = max(8, self.anchor_hud_rect.x - 82)
        self.radio_hud_rect = pygame.Rect(rx, rect.y, min(72, max(52, self.anchor_hud_rect.x - 10)), rect.h)
        radio_bg = (37, 76, 66) if self.radio_ui_open else self.PANEL_BG[:3]
        radio_border = (135, 205, 158) if self.radio_ui_open else (125, 145, 139)
        radio_card = self._cached_panel_surface((self.radio_hud_rect.w, self.radio_hud_rect.h), radio_bg,
                                                border=radio_border, border_width=2 if self.radio_ui_open else 1, radius=5)
        self.screen.blit(radio_card, self.radio_hud_rect.topleft)
        self.screen.blit(self.hud_compact_font.render("RADIO", True, (235, 231, 203)),
                         (self.radio_hud_rect.x + 5, self.radio_hud_rect.y + 5))
        radio_state = "OPEN" if self.radio_ui_open else ("READY" if self.radio_station_ok() else "WATCH")
        self.screen.blit(self.chart_small_font.render(radio_state, True, (161, 222, 177) if self.radio_station_ok() else (204, 195, 157)),
                         (self.radio_hud_rect.x + 5, self.radio_hud_rect.y + 25))

    def draw_hud(self):
        w = self.world
        col = self._column_w()
        pad = 12
        # The compact telemetry and ship/catch tabs share one reserved edge card.
        # Keeping both datasets in one tabbed panel prevents the old tall left-side
        # blocks from covering the deck and fishing view.
        self.draw_telemetry_panel()
        self.draw_money_counter()
        # Physical compass and wind pennant: heading and wind direction are deliberately separate.
        # On narrow windows the RADIO/ANCHOR/CASH controls occupy the right top;
        # move the compass to the second row instead of letting cards overlap.
        compass_y = 10 if W >= 1000 else 80
        compass_rect = pygame.Rect(W // 2 - 88, compass_y, 176, 40)
        pygame.draw.rect(self.screen, (22, 30, 34), compass_rect, border_radius=5)
        pygame.draw.rect(self.screen, (125, 145, 139), compass_rect, 1, border_radius=5)
        hdg = int(round(math.degrees(w.believed_heading) % 360))
        self.screen.blit(self.hud_compact_font.render("COMPASS  %03d°" % hdg, True, (237, 229, 194)), (compass_rect.x + 9, compass_rect.y + 5))
        wind_deg = int(round(math.degrees(self.weather.wind_dir) % 360))
        # Flag points downwind, with a readable bearing label.
        fx, fy = compass_rect.x + 18, compass_rect.y + 29
        wind_vec = V(1, 0).rotate_rad(self.weather.wind_dir) * 12
        pygame.draw.line(self.screen, (218, 214, 184), (fx, fy - 7), (fx, fy + 7), 2)
        pygame.draw.polygon(self.screen, (220, 85, 55), [(fx, fy - 5), (fx + wind_vec.x, fy - 5 + wind_vec.y), (fx + wind_vec.x * 0.7, fy + wind_vec.y + 1)])
        self.screen.blit(self.hud_compact_font.render("WIND %03d°" % wind_deg, True, (225, 190, 164)), (fx + 22, fy - 6))
        date_rect = pygame.Rect(W - 220 - 10, 58, 220, 18)
        date_card = self._cached_panel_surface((date_rect.w, date_rect.h), self.PANEL_BG[:3],
                                               border=(150, 150, 140), border_width=1, radius=3)
        self.screen.blit(date_card, date_rect.topleft)
        date_text = self.hud_compact_font.render(self.world.calendar_date_text(), True, (226, 220, 194))
        self.screen.blit(date_text, (date_rect.x + 7, date_rect.y + 1))
        self.calendar_hud_rect = date_rect

        # ---- bottom-right: selected sailor card
        sel = self.selected()
        if sel:
            info = [
                "Task: %s%s" % (sel.task, " (%s)" % sel.duty if sel.duty else ""),
                "Where: %s" % {1: "wheelhouse", 0: "main deck", -1: "below"}[int(sel.level)],
                "Morale %.2f  Tired %.2f" % (sel.morale, sel.fatigue),
                "Health %d%%  Owed %d" % (round(100 * sel.health), int(sel.owed)),
                "Caution %.2f Skill %.2f" % (sel.caution, sel.skill),
            ]
            if sel.carry:
                info.append("Carrying %d fish" % len(sel.carry))
            if sel.mode == Sailor.SWIMMING:
                info.append("IN THE WATER  stamina %.2f%s" % (sel.breath, "  ON THE LINE" if sel.lifeline is not None else ""))
            h_sel = self._block_h(len(info))
            self._draw_block(W - col - pad, H - h_sel - pad, col, sel.name.upper(), info, head_color=(242, 208, 75))

        # ---- bottom-centre: controls and radio ticker, sized to fit between the side columns
        strip_w = min(W - 2 * col - 4 * pad - 24, 860)
        if self.show_controls and strip_w >= 420:
            keys = ["F1 info / crew sheet   C chart   F9 notebook   SPACE hold   T speed   B auction",
                    "L auto-fish   P manual set (one set)   J haul now   H muster   R rescue   W weather   K bait",
                    "M engage/bypass stern roller; clear jam with a deckhand aft   Y harness protects rail crew",
                    "U open/dog nearby hatch   F sluice table with hose   V trim ice (below deck)",
                    "I bearing/range report   O speed report   click another deckhand within 5s for a second opinion",
                    "SPACE brake / gaff   Z/X fine brake   [ ] line depth   , . sea state   Q/E climb",
                    "Duty: 1 set 2 haul 3 clean 4 rest 5 cut 6 engine 7 helm 0 free",
                    "At assigned helm: arrows steer/telegraph. Captain 4 = veteran relief.",
                    "Ocean: right-click water = steer-to; Shift + right-drag A→B = plot leg (day/clear only); Esc clears.",
                    "Course is a reference, not a rail: rudder lag, current, wind and helm skill cause drift.",
                    "A anchor  click RADIO / Ctrl+F11 fleet contacts  F2 weather  F3 market  F4 tow  G escort questions",
                    "F5 controls  F6 fishing UI  F7 HUD mode  F8 HUD show/hide  F10 debug line map  F12 tow debug",
                    "B auction at quay (1-4 sell, K keep, A all)"]
            if self.tow_escort is not None and self.tow_escort_status_t > 0 and self.tow_escort_status_message:
                radio = "Radio: " + self.tow_escort_status_message
            elif self.tow_transit_active and self.tow_escort is not None:
                radio = "Radio: %s — escort active; last report %dm ago%s" % (
                    self.tow_escort.callsign, self.tow_escort.report_age_game_minutes,
                    " (CHECK-IN STALE)" if self.tow_escort.marker_stale else "")
            elif self.tow_escort is not None and self.tow_escort.state in ("EN_ROUTE", "ALONGSIDE"):
                radio = "Radio: COAST GUARD %s EN ROUTE / MAKING FAST — F4 position / G questions" % self.tow_escort.callsign
            elif self.tow_transit_active:
                radio = "Radio: TOW ACCEPTED — tug towing us back to berth"
            elif self.tow_request_active:
                radio = "Radio: TOW REQUEST ACTIVE — retransmitting until answered"
            elif self.radio_message:
                radio = "Radio: " + self.radio_message
            elif not self.radio_station_ok():
                radio = "Radio: AM/SSB 2182 kHz — unattended (send crew to wireless)"
            else:
                radio = "Radio: AM/SSB 2182 kHz — standby  signal %d%%" % round(100.0 * self.radio.signal_quality)
            lines = keys + [radio]
            h_strip = self._block_h(len(lines))
            x = W // 2 - strip_w // 2
            self._draw_block(x, H - h_strip - pad, strip_w, "CONTROLS", lines, head_color=(255, 235, 170))
            self._strip_top = H - h_strip - pad
        elif not self.show_controls:
            self.text("F5: SHOW CONTROLS", (W // 2 - 88, H - 27), (175, 198, 190))

        # ---- off-screen buoy pointers
        for wp in self.line.end_buoys():
            c = self.S(self.world.deck_of(wp))
            m = 50
            if m < c[0] < W - m and m < c[1] < H - m:
                continue
            d = V(c) - CENTER
            half = CENTER - V(m, m)
            k = min(half.x / max(abs(d.x), 1e-3), half.y / max(abs(d.y), 1e-3))
            pos = CENTER + d * k
            a = math.atan2(d.y, d.x)
            pygame.draw.polygon(self.screen, (217, 83, 30), [pos + V(18, 0).rotate_rad(a), pos + V(14, 0).rotate_rad(a + 2.5), pos + V(14, 0).rotate_rad(a - 2.5)])

    def _block_h(self, n):
        return 2 * self.PAD + self.HEAD_H + n * self.LINE_H

    def _draw_block(self, x, y, w, header, lines, head_color=GOLD):
        """A HUD card sized to its contents: fixed line pitch, clipped to the card, header on top."""
        rect = pygame.Rect(int(x), int(y), int(w), self._block_h(len(lines)))
        self.panel(rect, lines, header=header, header_color=head_color)

    def run(self):
        """Run the Pygame loop with persistent crash diagnostics.

        Exceptions raised during input, update, physics or rendering are written to
        ``cache/errors`` with a traceback and compact simulation snapshot so a blank
        exit is diagnosable even when the terminal is hidden.
        """
        install_diagnostics()
        logger = get_logger()
        running = True
        frame_no = 0
        last_event = "startup"
        logger.info("Game session started; version=%s", "v13.2.13")
        try:
            while running:
                frame_no += 1
                set_active_context({"frame": frame_no, "event": last_event, "loop_stage": "frame_start"})
                try:
                    dt = min(self.clock.tick(60) / 1000.0, 0.05)
                    for ev in pygame.event.get():
                        if ev.type == pygame.KEYDOWN:
                            try:
                                last_event = "KEYDOWN:" + pygame.key.name(ev.key)
                            except Exception:
                                last_event = "KEYDOWN"
                        else:
                            last_event = "EVENT:%s" % getattr(ev, "type", "unknown")
                        set_active_context({"frame": frame_no, "event": last_event, "loop_stage": "input"})
                        if ev.type == pygame.VIDEORESIZE and pygame.version.vernum[0] < 2:
                            self.screen = pygame.display.set_mode(ev.size, pygame.RESIZABLE)
                        if ev.type == pygame.QUIT or not self.handle(ev):
                            running = False
                            break
                    if not running:
                        break
                    surf = pygame.display.get_surface()        # window resized / fullscreen toggled
                    if surf is not None and surf.get_size() != self._win:
                        self.screen = surf
                        self.resize(*surf.get_size())
                    keys = pygame.key.get_pressed()
                    set_active_context({"frame": frame_no, "event": last_event, "loop_stage": "simulation_update"})
                    for _ in range(self.timescale):
                        self.update(dt, keys)
                    set_active_context({"frame": frame_no, "event": last_event, "loop_stage": "draw"})
                    self.draw()
                    pygame.display.flip()
                except Exception:
                    exc_info = sys.exc_info()
                    context = game_context_snapshot(self, frame_no=frame_no, last_event=last_event)
                    path = write_exception_report(
                        "Unhandled exception in the game loop", exc_info=exc_info, context=context
                    )
                    message = "Fishing Simulator stopped after an error."
                    if path:
                        message += " Diagnostic report: %s" % path
                    print(message, file=sys.stderr, flush=True)
                    logger.error("Game loop stopped on frame %d after %s", frame_no, last_event)
                    running = False
        finally:
            logger.info("Game session ended; frames=%d", frame_no)
            try:
                pygame.quit()
            except Exception:
                write_exception_report("Pygame shutdown failed", exc_info=sys.exc_info(),
                                       context={"frame": frame_no, "last_event": last_event})



if __name__ == "__main__":
    Game().run()