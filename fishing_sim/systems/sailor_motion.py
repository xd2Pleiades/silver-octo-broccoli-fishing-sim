"""Chapter B - sailor locomotion, bracing, separation, path following, gather.

Pure, Pygame-free and deterministic.  Positions are ship-local metres (+x bow,
+y starboard); the Game adapter converts from deck pixels.  Every per-tick
update is frame-rate independent: velocities change by rate * dt, caps apply to
*desired* velocity (never multiplied into current velocity), and separation is
gain * dt.

Design reference: Sailor Systems Design Guide v3.2, Part B (B2-B9, tests B11).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Callable, Optional, Sequence

Vec = tuple[float, float]

# Tunables live here until the repo has a balance-profile loader (guide 0.5).
BALANCE = {
    "max_speed": 1.4, "accel": 3.0, "decel": 4.5, "turn_rate": 5.0, "radius": 0.35,
    "arrive_radius": 0.8, "brace_speed_cut": 0.6,
    "brace_walk_roll_deg": 6.0, "grab_rail_roll_deg": 10.0, "grab_rail_flooding": 0.4,
    "brace_walk_target": 0.5, "brace_rise_per_s": 3.0, "brace_fall_per_s": 2.0,
    "separation_gain": 10.0,
    "push_damping": 6.0,
    "waypoint_radius": 0.4, "block_repath_s": 1.5, "repath_min_interval_s": 0.5,
    "stagger_roll_rate_deg_s": 8.0, "stagger_gain": 0.02, "stagger_cap": 0.6,
    "anim_blend_s": 0.2, "conversation_radius": 3.0, "gather_stop_m": 1.2,
    "queue_spacing": 0.15,
}

# Animation states (B5)
IDLE_SWAY, WALK, BRACE_WALK, BRACE_HOLD, WORK_CROUCH, STAND_WATCH = (
    "idle_sway", "walk", "brace_walk", "brace_hold", "work_crouch", "stand_watch")
ANIM_STATES = (IDLE_SWAY, WALK, BRACE_WALK, BRACE_HOLD, WORK_CROUCH, STAND_WATCH)
CROUCH_TASKS = frozenset({"bail", "stow", "clear_gear", "clear-gear"})
WATCH_TASKS = frozenset({"helm", "lookout", "radio", "post"})

# Brace modes (B4)
BRACE_NONE, BRACE_WALK_MODE, BRACE_GRAB = "none", "brace_walk", "grab_rail"


def _len(v: Vec) -> float:
    return math.hypot(v[0], v[1])


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def approach(cur: float, target: float, rate: float, dt: float) -> float:
    """Move cur toward target by at most rate*dt (linear, frame-rate independent)."""
    step = rate * dt
    if abs(target - cur) <= step:
        return target
    return cur + step if target > cur else cur - step


@dataclass
class MotionState:
    """B2 motion record for one sailor (metres, ship-local)."""
    name: str
    pos: Vec = (0.0, 0.0)
    vel: Vec = (0.0, 0.0)
    facing: float = 0.0
    target: Optional[Vec] = None
    max_speed: float = BALANCE["max_speed"]
    accel: float = BALANCE["accel"]
    decel: float = BALANCE["decel"]
    turn_rate: float = BALANCE["turn_rate"]
    radius: float = BALANCE["radius"]
    brace: float = 0.0
    brace_mode: str = BRACE_NONE
    task: str = "idle"
    anim: str = IDLE_SWAY
    anim_prev: str = IDLE_SWAY
    anim_t: float = 1.0                 # blend progress 0..1 from anim_prev to anim
    path: list = field(default_factory=list)
    stagger_v: Vec = (0.0, 0.0)
    station_target: Optional[Vec] = None   # what the task layer wants; re-supplied each tick


# --------------------------------------------------------------------------
# B2 - steering
# --------------------------------------------------------------------------
def desired_velocity(s: MotionState, bal: dict = BALANCE) -> Vec:
    """Seek with arrival; brace caps the *desired* speed (never current velocity)."""
    if s.target is None:
        return (0.0, 0.0)
    dx, dy = s.target[0] - s.pos[0], s.target[1] - s.pos[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return (0.0, 0.0)
    speed = s.max_speed
    if dist < bal["arrive_radius"]:
        speed *= dist / bal["arrive_radius"]                 # linear fall-off
    speed *= 1.0 - bal["brace_speed_cut"] * _clamp(s.brace, 0.0, 1.0)
    return (dx / dist * speed, dy / dist * speed)


def step_velocity(s: MotionState, desired: Vec, dt: float) -> Vec:
    """Accelerate toward desired (decelerate if slower than the current speed)."""
    dvx, dvy = desired[0] - s.vel[0], desired[1] - s.vel[1]
    dv = math.hypot(dvx, dvy)
    if dv < 1e-12:
        return desired
    rate = s.decel if _len(desired) < _len(s.vel) else s.accel
    step = rate * dt
    if dv <= step:
        return desired
    return (s.vel[0] + dvx / dv * step, s.vel[1] + dvy / dv * step)


def step_facing(s: MotionState, dt: float, face_toward: Optional[Vec] = None) -> float:
    """Turn toward velocity direction (when moving) or toward an explicit point."""
    if face_toward is not None:
        want = math.atan2(face_toward[1] - s.pos[1], face_toward[0] - s.pos[0])
    elif _len(s.vel) > 0.05:
        want = math.atan2(s.vel[1], s.vel[0])
    else:
        return s.facing
    diff = wrap_angle(want - s.facing)
    step = s.turn_rate * dt
    return wrap_angle(s.facing + _clamp(diff, -step, step))


# --------------------------------------------------------------------------
# B3 - separation and bottleneck reservation
# --------------------------------------------------------------------------
def separation_push(states: Sequence[MotionState], gain: float = None) -> dict:
    """Per-sailor velocity *rate* (m/s per s) pushing overlapping bodies apart.

    Multiply by dt before adding to velocity.  Coincident bodies get a
    deterministic index-based direction so they always separate.
    """
    gain = BALANCE["separation_gain"] if gain is None else gain
    out = {s.name: [0.0, 0.0] for s in states}
    for i in range(len(states)):
        for j in range(i + 1, len(states)):
            a, b = states[i], states[j]
            dx, dy = a.pos[0] - b.pos[0], a.pos[1] - b.pos[1]
            d = math.hypot(dx, dy)
            overlap = a.radius + b.radius - d
            if overlap <= 0.0:
                continue
            if d < 1e-9:
                ang = (i * 2.399963 + j * 1.618) % (2 * math.pi)   # golden-angle spread
                ux, uy = math.cos(ang), math.sin(ang)
            else:
                ux, uy = dx / d, dy / d
            k = gain * overlap
            out[a.name][0] += ux * k
            out[a.name][1] += uy * k
            out[b.name][0] -= ux * k
            out[b.name][1] -= uy * k
    return {n: (v[0], v[1]) for n, v in out.items()}


class Bottleneck:
    """B3 station reservation: capacity-limited slot with a FIFO queue."""

    def __init__(self, key: str, pos: Vec, capacity: int = 1, facing: float = 0.0):
        self.key, self.pos, self.capacity, self.facing = key, pos, capacity, facing
        self.holders: list[str] = []
        self.queue: list[str] = []

    def request(self, name: str) -> bool:
        """True if `name` holds a slot now; otherwise it is queued (once)."""
        if name in self.holders:
            return True
        if name not in self.queue:
            self.queue.append(name)
        self._promote()
        return name in self.holders

    def release(self, name: str) -> None:
        if name in self.holders:
            self.holders.remove(name)
        if name in self.queue:
            self.queue.remove(name)
        self._promote()

    def _promote(self) -> None:
        while self.queue and len(self.holders) < self.capacity:
            self.holders.append(self.queue.pop(0))

    def queue_spot(self, name: str, spacing: float = None) -> Optional[Vec]:
        """Idle-wait position: stacked a few centimetres apart, behind the bottleneck."""
        spacing = BALANCE["queue_spacing"] if spacing is None else spacing
        if name not in self.queue:
            return None
        idx = self.queue.index(name) + 1
        back = self.facing + math.pi
        off = idx * (BALANCE["radius"] * 2.0 + spacing)
        return (self.pos[0] + math.cos(back) * off, self.pos[1] + math.sin(back) * off)


# --------------------------------------------------------------------------
# B4 - bracing against the sea
# --------------------------------------------------------------------------
def classify_brace(abs_roll_deg: float, flooding: float, moving: bool,
                   bal: dict = BALANCE) -> str:
    if abs_roll_deg >= bal["grab_rail_roll_deg"] or flooding > bal["grab_rail_flooding"]:
        return BRACE_GRAB
    if abs_roll_deg >= bal["brace_walk_roll_deg"] and moving:
        return BRACE_WALK_MODE
    return BRACE_NONE


def update_brace(s: MotionState, abs_roll_deg: float, flooding: float, dt: float,
                 nearest_rail: Optional[Vec], bal: dict = BALANCE) -> None:
    """B4 per-tick brace update.

    Releasing clears the target (load-bearing): otherwise a sailor released from a
    rail grab keeps walking to the stale rail point.
    """
    moving = _len(s.vel) >= 0.05 or s.target is not None
    mode = classify_brace(abs_roll_deg, flooding, moving, bal)
    if mode == BRACE_GRAB:
        s.brace = approach(s.brace, 1.0, bal["brace_rise_per_s"], dt)
        if nearest_rail is not None:
            s.target = nearest_rail
    elif mode == BRACE_WALK_MODE:
        s.brace = approach(s.brace, bal["brace_walk_target"], bal["brace_rise_per_s"], dt)
        s.target = None                      # task layer re-supplies the station target next tick
    else:
        s.brace = approach(s.brace, 0.0, bal["brace_fall_per_s"], dt)
        if s.brace_mode != BRACE_NONE:
            s.target = None
    s.brace_mode = mode


# --------------------------------------------------------------------------
# B5 - animation state
# --------------------------------------------------------------------------
def select_anim(speed: float, brace: float, task: str) -> str:
    if brace >= 0.7:
        return BRACE_HOLD
    if speed >= 0.05:
        return BRACE_WALK if brace >= 0.3 else WALK
    if task in CROUCH_TASKS:
        return WORK_CROUCH
    if task in WATCH_TASKS:
        return STAND_WATCH
    return IDLE_SWAY


def update_anim(s: MotionState, dt: float, bal: dict = BALANCE) -> None:
    """Pick the state and blend over ~0.2 s; never hard-cut between states."""
    new = select_anim(_len(s.vel), s.brace, s.task)
    if new != s.anim:
        s.anim_prev, s.anim, s.anim_t = s.anim, new, 0.0
    s.anim_t = min(1.0, s.anim_t + dt / max(bal["anim_blend_s"], 1e-6))


def lean_angle_deg(brace: float, roll_deg: float) -> float:
    """B4 render lean: about -0.7 x roll at full brace."""
    return -0.7 * _clamp(brace, 0.0, 1.0) * roll_deg


# --------------------------------------------------------------------------
# B6 - staggering
# --------------------------------------------------------------------------
def stagger_impulse(roll_rate_deg_s: float, brace: float, bal: dict = BALANCE) -> float:
    """Signed lateral (+y) velocity impulse opposing the roll rate, capped."""
    if brace >= 0.5 or abs(roll_rate_deg_s) < bal["stagger_roll_rate_deg_s"]:
        return 0.0
    mag = _clamp(abs(roll_rate_deg_s) * bal["stagger_gain"] * (1.0 - brace), 0.0, bal["stagger_cap"])
    return -math.copysign(mag, roll_rate_deg_s)


def clamp_to_deck(pos: Vec, bounds: tuple[float, float, float, float]) -> Vec:
    """bounds = (xmin, ymin, xmax, ymax). Stagger must never push anyone overboard."""
    return (_clamp(pos[0], bounds[0], bounds[2]), _clamp(pos[1], bounds[1], bounds[3]))


# --------------------------------------------------------------------------
# B7 - path following and smoothing
# --------------------------------------------------------------------------
def smooth_path(points: Sequence[Vec], line_clear: Callable[[Vec, Vec], bool]) -> list:
    """String-pull: keep a corner only if the straight line to a later one is blocked.

    `line_clear(a, b)` must test against obstacles already inflated by the
    sailor radius.
    """
    pts = [tuple(p) for p in points]
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    anchor = 0
    i = 2
    while i < len(pts):
        if not line_clear(pts[anchor], pts[i]):
            out.append(pts[i - 1])
            anchor = i - 1
        i += 1
    out.append(pts[-1])
    return out


class PathFollower:
    """Waypoint advance (0.4 m), blocked detection (1.5 s), 0.5 s repath throttle."""

    def __init__(self, bal: dict = BALANCE):
        self.bal = bal
        self.path: list = []
        self.blocked_t = 0.0
        self.last_repath = -1e9
        self.repath_count = 0

    def set_path(self, path: Sequence[Vec]) -> None:
        self.path = [tuple(p) for p in path]
        self.blocked_t = 0.0

    def current_target(self) -> Optional[Vec]:
        return self.path[0] if self.path else None

    def advance(self, pos: Vec) -> Optional[Vec]:
        while self.path and math.hypot(self.path[0][0] - pos[0], self.path[0][1] - pos[1]) <= self.bal["waypoint_radius"]:
            if len(self.path) == 1:
                self.path.pop(0)
                break
            self.path.pop(0)
        return self.current_target()

    def note_progress(self, blocked: bool, dt: float) -> None:
        self.blocked_t = self.blocked_t + dt if blocked else 0.0

    def should_repath(self, now: float, deck_state_changed: bool = False) -> bool:
        """Obstruction > 1.5 s or a deck-state change; never more than once per 0.5 s."""
        if now - self.last_repath < self.bal["repath_min_interval_s"]:
            return False
        return deck_state_changed or self.blocked_t > self.bal["block_repath_s"]

    def mark_repathed(self, now: float) -> None:
        self.last_repath, self.blocked_t = now, 0.0
        self.repath_count += 1


# --------------------------------------------------------------------------
# B8 - gather
# --------------------------------------------------------------------------
def pick_meeting_spot(a: Vec, b: Vec, spots: Sequence[Vec]) -> Optional[Vec]:
    """Spot (rail point, hatch coaming, task station) that minimises the longer walk."""
    best, best_cost = None, 1e18
    for p in spots:
        cost = max(math.hypot(p[0] - a[0], p[1] - a[1]), math.hypot(p[0] - b[0], p[1] - b[1]))
        if cost < best_cost:
            best, best_cost = tuple(p), cost
    return best


def gather_offsets(spot: Vec, n: int, radius: float = None) -> list:
    """Stand-points around a meeting spot, inside the 3 m conversation radius."""
    radius = BALANCE["gather_stop_m"] * 0.5 if radius is None else radius
    if n <= 1:
        return [tuple(spot)]
    return [(spot[0] + math.cos(2 * math.pi * i / n) * radius,
             spot[1] + math.sin(2 * math.pi * i / n) * radius) for i in range(n)]


class GatherPlanner:
    """Chooses idle pairs to walk together so conversations can start (B8)."""

    def __init__(self, seed: int = 1962, interval_s: float = 45.0, cooldown_s: float = 90.0):
        self.rng = random.Random(seed ^ 0x6A7E)
        self.interval_s, self.cooldown_s = interval_s, cooldown_s
        self.next_check = interval_s
        self.cooldowns: dict = {}
        self.active: dict = {}             # frozenset(names) -> {"spots": {name: Vec}, "since": t}

    def plan(self, now: float, idle: Sequence[tuple], spots: Sequence[Vec],
             busy_allowed: bool = True) -> Optional[dict]:
        """idle: [(name, pos)].  Returns {name: stand_point} for a chosen pair, or None."""
        if now < self.next_check or not busy_allowed or len(idle) < 2 or not spots:
            return None
        self.next_check = now + self.interval_s
        pairs = [(a, b) for i, a in enumerate(idle) for b in idle[i + 1:]
                 if self.cooldowns.get(frozenset((a[0], b[0])), -1e9) <= now
                 and math.hypot(a[1][0] - b[1][0], a[1][1] - b[1][1]) > BALANCE["conversation_radius"]]
        if not pairs:
            return None
        a, b = pairs[self.rng.randrange(len(pairs))]
        spot = pick_meeting_spot(a[1], b[1], spots)
        if spot is None:
            return None
        key = frozenset((a[0], b[0]))
        self.cooldowns[key] = now + self.cooldown_s
        stand = gather_offsets(spot, 2)
        result = {a[0]: stand[0], b[0]: stand[1]}
        self.active[key] = {"spots": result, "since": now}
        return result

    def finish(self, names: Sequence[str]) -> None:
        self.active.pop(frozenset(names), None)


# --------------------------------------------------------------------------
# Whole-crew tick (used by tests/benchmark; Game uses the pieces directly)
# --------------------------------------------------------------------------
def step_crew(states: Sequence[MotionState], dt: float, abs_roll_deg: float = 0.0,
              roll_rate_deg_s: float = 0.0, flooding: float = 0.0,
              rail_points: Sequence[Vec] = (),
              bounds: Optional[tuple] = None, bal: dict = BALANCE) -> None:
    push = separation_push(states, bal["separation_gain"])
    for s in states:
        rail = None
        if rail_points:
            rail = min(rail_points, key=lambda p: math.hypot(p[0] - s.pos[0], p[1] - s.pos[1]))
        if s.brace_mode != BRACE_GRAB and s.target is None:
            s.target = s.station_target          # task layer re-supplies the station target
        update_brace(s, abs_roll_deg, flooding, dt, rail, bal)
        if s.target is None and s.brace_mode == BRACE_WALK_MODE:
            s.target = s.station_target          # brace-walk slows, it does not stop the walk
        vel = step_velocity(s, desired_velocity(s, bal), dt)
        px, py = push[s.name]
        imp = stagger_impulse(roll_rate_deg_s, s.brace, bal)
        s.vel = vel
        # Separation and stagger live in their own damped velocity so the walk
        # integrator's deceleration cannot swallow them at coarse time steps.
        damp = math.exp(-bal["push_damping"] * dt)
        s.stagger_v = ((s.stagger_v[0] + px * dt) * damp, (s.stagger_v[1] + (py + imp) * dt) * damp)
        s.pos = (s.pos[0] + (s.vel[0] + s.stagger_v[0]) * dt,
                 s.pos[1] + (s.vel[1] + s.stagger_v[1]) * dt)
        if bounds is not None:
            s.pos = clamp_to_deck(s.pos, bounds)
        s.facing = step_facing(s, dt)
        update_anim(s, dt, bal)
