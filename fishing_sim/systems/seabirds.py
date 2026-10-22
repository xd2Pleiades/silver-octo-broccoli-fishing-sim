"""Headless seabird flight model for working-bird fishing cues (no Pygame).

A flock belongs to one hotspot.  Birds do not sit on a rigid ellipse: each one
flies with a heading, a speed and a turn-rate limit, wheels around a slowly
wandering point above the school, banks into its turns, glides between bursts
of flapping, and every so often folds its wings and plunge-dives onto the
boil.  A dive ends in a splash (recorded in ``flock.splashes`` for the
renderer), a brief sit on the surface, and a climb back up into the circle.
Birds arrive from the open sea when a school strengthens and fly away when it
fades.  All positions are absolute world coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random

TAU = math.tau
MAX_TURN_RATE = 2.4          # rad/s while circling (gentle wheeling)
DIVE_TURN_RATE = 4.2         # rad/s while stooping on a target
MAX_FLOCK_BIRDS = 34
MAX_SPLASHES = 24
SPLASH_LIFE = 1.6
FLAP_FRAMES = 8
FRAME_GLIDE = FLAP_FRAMES        # wings held out, soaring
FRAME_FOLD = FLAP_FRAMES + 1     # wings swept back for the plunge

CIRCLE, ARRIVE, DIVE, SURFACE, CLIMB, LEAVE = "circle", "arrive", "dive", "surface", "climb", "leave"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def wrap_angle(a):
    return (a + math.pi) % TAU - math.pi


def turn_toward(heading, desired, max_step):
    """Rotate ``heading`` toward ``desired`` by at most ``max_step``; return (heading, applied_step)."""
    step = _clamp(wrap_angle(desired - heading), -max_step, max_step)
    return heading + step, step


@dataclass(slots=True)
class Seabird:
    x: float
    y: float
    heading: float
    speed: float
    base_speed: float
    orbit_r: float
    orbit_dir: float
    alt: float = 0.7              # 0 = on the water, 1 = high; drives shadow offset only
    state: str = CIRCLE
    timer: float = 0.0
    cooldown: float = 0.0         # time before this bird may dive again
    flap: float = 0.0             # flap cycle, in whole cycles
    flap_hz: float = 4.0
    glide: bool = False
    glide_timer: float = 1.0
    bank: float = 0.0             # -1..1, positive = turning clockwise on screen (y down)
    wander: float = 0.0
    tx: float = 0.0
    ty: float = 0.0


@dataclass(slots=True)
class Splash:
    x: float
    y: float
    age: float
    life: float
    size: float
    seed: int

    @property
    def progress(self):
        return _clamp(self.age / max(0.001, self.life), 0.0, 1.0)


def sprite_frame(bird):
    """Which pre-rendered pose to draw: 0..7 flap cycle, 8 soaring glide, 9 folded plunge."""
    if bird.state == DIVE:
        return FRAME_FOLD
    if bird.glide and bird.state in (CIRCLE, CLIMB, ARRIVE, LEAVE):
        return FRAME_GLIDE
    return int((bird.flap % 1.0) * FLAP_FRAMES) % FLAP_FRAMES


class SeabirdFlock:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.spin = 1.0 if self.rng.random() < 0.5 else -1.0     # the flock mostly wheels one way
        self.birds = []
        self.splashes = []
        self.elapsed = 0.0
        self.spot = None              # set by the owner: the Hotspot this flock works
        self._seeded = False

    # ------------------------------------------------------------------ spawning
    def _make_bird(self, cx, cy, cue_r, strength, arriving):
        r = self.rng
        tight = 0.55 + 0.45 * (1.0 - _clamp(strength, 0.0, 1.0))      # weak schools: looser, wider flocks
        orbit_r = max(60.0, cue_r * (0.30 + 0.70 * r.random()) * tight)
        speed = _clamp(orbit_r * r.uniform(0.55, 0.95), 95.0, 320.0)
        orbit_dir = self.spin if r.random() < 0.88 else -self.spin
        if arriving:
            ang = r.uniform(0.0, TAU)
            dist = cue_r * 3.2 + r.uniform(200.0, 900.0)
            x, y = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist
            heading = math.atan2(cy - y, cx - x) + r.uniform(-0.25, 0.25)
            state, alt = ARRIVE, 0.85
        else:
            ang = r.uniform(0.0, TAU)
            rr = orbit_r * r.uniform(0.85, 1.15)
            x, y = cx + math.cos(ang) * rr, cy + math.sin(ang) * rr
            heading = ang + orbit_dir * math.pi * 0.5
            state, alt = CIRCLE, r.uniform(0.5, 0.95)
        return Seabird(x, y, heading, speed, speed, orbit_r, orbit_dir, alt=alt, state=state,
                       cooldown=r.uniform(0.5, 5.0), flap=r.random(), flap_hz=r.uniform(3.4, 5.2),
                       glide=r.random() < 0.4, glide_timer=r.uniform(0.5, 3.0),
                       wander=r.uniform(0.0, TAU))

    # ------------------------------------------------------------------ steering
    def _circle_heading(self, b, ax, ay, orbit_r):
        dx, dy = b.x - ax, b.y - ay
        rr = math.hypot(dx, dy) or 1e-6
        ux, uy = dx / rr, dy / rr
        tx, ty = -uy * b.orbit_dir, ux * b.orbit_dir            # tangent for the bird's wheeling sense
        k = _clamp((rr - orbit_r) / max(orbit_r, 1.0) * 1.3, -0.9, 0.9)
        return math.atan2(ty - uy * k, tx - ux * k)             # outside the orbit: lean inward

    def update(self, dt, cx, cy, cue_r, strength, target_count, wind=(0.0, 0.0)):
        """Advance the flock by ``dt`` seconds around a school at (cx, cy)."""
        dt = _clamp(float(dt), 0.0, 0.1)
        if dt <= 0.0:
            return
        self.elapsed += dt
        r = self.rng
        cue_r = max(120.0, float(cue_r))
        strength = _clamp(float(strength), 0.0, 1.0)
        target = int(_clamp(target_count, 0, MAX_FLOCK_BIRDS))

        working = [b for b in self.birds if b.state != LEAVE]
        if not self._seeded:                                    # first sighting: the birds are already there
            self._seeded = True
            for _ in range(target):
                self.birds.append(self._make_bird(cx, cy, cue_r, strength, arriving=False))
        else:
            if len(working) < target and r.random() < dt * 0.9:   # reinforcements trickle in from the open sea
                self.birds.append(self._make_bird(cx, cy, cue_r, strength, arriving=True))
            elif len(working) > target and working and r.random() < dt * 0.8:   # the flock thins out gradually
                idle = [b for b in working if b.state in (CIRCLE, CLIMB, ARRIVE)] or working
                idle[r.randrange(len(idle))].state = LEAVE
        busy = sum(1 for b in self.birds if b.state in (DIVE, SURFACE))
        max_diving = max(1, target // 4)
        dive_rate = 0.004 + 0.035 * strength ** 1.5            # strong boils: a plunge every second or two

        keep = []
        for b in self.birds:
            ax = cx + math.cos(self.elapsed * 0.21 + b.wander) * cue_r * 0.12
            ay = cy + math.sin(self.elapsed * 0.17 + b.wander * 1.7) * cue_r * 0.12
            max_turn = MAX_TURN_RATE
            want_speed = b.base_speed * (1.0 + 0.08 * math.sin(self.elapsed * 0.9 + b.wander))
            desired = b.heading
            want_alt = 0.65 + 0.28 * math.sin(self.elapsed * 0.3 + b.wander)

            if b.state == CIRCLE:
                desired = self._circle_heading(b, ax, ay, b.orbit_r)
                b.cooldown -= dt
                if (b.cooldown <= 0.0 and b.alt > 0.45 and busy < max_diving
                        and r.random() < dive_rate * dt):
                    s = math.sqrt(r.random()) * cue_r * 0.35
                    a = r.uniform(0.0, TAU)
                    b.tx, b.ty = cx + math.cos(a) * s, cy + math.sin(a) * s
                    b.state, b.timer = DIVE, 3.2
                    busy += 1
            elif b.state == ARRIVE:
                desired = math.atan2(ay - b.y, ax - b.x)
                want_speed, want_alt = b.base_speed * 1.25, 0.85
                if math.hypot(b.x - ax, b.y - ay) < b.orbit_r * 1.6:
                    b.state, b.cooldown = CIRCLE, r.uniform(1.0, 4.0)
            elif b.state == DIVE:
                desired = math.atan2(b.ty - b.y, b.tx - b.x)
                max_turn = DIVE_TURN_RATE
                want_speed = b.base_speed * 1.6
                b.alt = max(0.04, b.alt - dt * 1.1)
                b.timer -= dt
                hit = max(45.0, b.speed / DIVE_TURN_RATE * 0.9)
                if math.hypot(b.tx - b.x, b.ty - b.y) < hit or b.alt <= 0.06:
                    if len(self.splashes) < MAX_SPLASHES:
                        self.splashes.append(Splash(b.x, b.y, 0.0, SPLASH_LIFE,
                                                    r.uniform(0.8, 1.3), r.randrange(1, 1 << 20)))
                    b.state, b.timer, b.alt = SURFACE, r.uniform(0.45, 1.0), 0.04
                elif b.timer <= 0.0:                            # missed the line; give it up and climb away
                    b.state = CLIMB
            elif b.state == SURFACE:
                want_speed, want_alt = b.base_speed * 0.35, 0.04
                b.timer -= dt
                if b.timer <= 0.0:
                    b.state = CLIMB
            elif b.state == CLIMB:
                desired = self._circle_heading(b, ax, ay, b.orbit_r * 1.1)
                b.alt = min(1.0, b.alt + dt * 0.9)
                if b.alt >= 0.6:
                    b.state, b.cooldown = CIRCLE, r.uniform(3.0, 8.0)
            else:                                               # LEAVE: head straight out to sea
                desired = math.atan2(b.y - cy, b.x - cx)
                want_speed, want_alt = b.base_speed * 1.3, 0.9
                if math.hypot(b.x - cx, b.y - cy) > cue_r * 5.0 + 800.0:
                    continue

            if b.state in (CIRCLE, ARRIVE, CLIMB, LEAVE):       # drift toward the wanted height
                b.alt += _clamp(want_alt - b.alt, -0.4 * dt, 0.4 * dt)
            b.alt = _clamp(b.alt, 0.0, 1.0)
            b.speed += (want_speed - b.speed) * min(1.0, 2.0 * dt)
            b.heading, step = turn_toward(b.heading, desired, max_turn * dt)
            b.bank += (_clamp(step / dt / MAX_TURN_RATE, -1.0, 1.0) - b.bank) * min(1.0, 6.0 * dt)
            b.x += math.cos(b.heading) * b.speed * dt + wind[0] * dt * 0.25
            b.y += math.sin(b.heading) * b.speed * dt + wind[1] * dt * 0.25

            b.glide_timer -= dt                                 # alternate flapping bursts and soaring glides
            if b.glide_timer <= 0.0:
                b.glide = not b.glide
                b.glide_timer = r.uniform(1.2, 3.5) if b.glide else r.uniform(0.8, 2.0)
            hz = b.flap_hz * (1.6 if b.state == SURFACE else 1.0)
            b.flap = (b.flap + dt * hz) % 1.0
            keep.append(b)
        self.birds = keep

        for s in self.splashes:
            s.age += dt
        self.splashes = [s for s in self.splashes if s.age < s.life]
