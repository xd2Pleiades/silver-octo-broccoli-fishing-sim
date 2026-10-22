"""Bounded, persistent 2D sea-foam simulation for Fishing Simulator.

The model is independent of Pygame drawing so particle lifecycle, emission,
coordinate transforms, and caps can be tested in a headless Python process.
Coordinates are absolute water/world coordinates; the renderer projects them
relative to the current ship camera.
"""
from dataclasses import dataclass
import math
import random
from typing import Callable, Dict, List, Optional, Tuple


Vec2 = Tuple[float, float]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def world_to_view(x: float, y: float, ship_x: float, ship_y: float, heading: float) -> Vec2:
    """Convert an absolute water coordinate into the ship-centred camera frame."""
    dx, dy = x - ship_x, y - ship_y
    c, s = math.cos(heading), math.sin(heading)
    return (dx * c + dy * s, -dx * s + dy * c)


@dataclass(slots=True)
class FoamPatch:
    """One short-lived foam mark, anchored to water rather than to the vessel."""
    x: float
    y: float
    vx: float
    vy: float
    age: float
    lifetime: float
    length: float
    width: float
    angle: float
    intensity: float
    kind: str                 # wake / bow / side / crest / spray
    seed: int

    @property
    def remaining(self) -> float:
        return max(0.0, self.lifetime - self.age)

    @property
    def normalized_age(self) -> float:
        return clamp(self.age / max(0.001, self.lifetime), 0.0, 1.0)

    @property
    def opacity(self) -> float:
        """Fade gently through most of the life, then disappear near expiry."""
        life_fade = (1.0 - self.normalized_age) ** 0.7
        end_fade = clamp(self.remaining / 0.75, 0.0, 1.0)
        return clamp(self.intensity * life_fade * end_fade, 0.0, 1.0)


class SeaFoamSystem:
    """Time-step based sea foam with a fixed particle budget and deterministic scan.

    ``wave_height`` is a callable accepting absolute world x/y coordinates. It is
    supplied by the existing WaveField, keeping sea-foam code independent from
    the Pygame game module.
    """

    DEFAULT_CAP = 240
    CREST_SCAN_INTERVAL = 0.72
    MAX_EVENTS_PER_UPDATE = 36

    def __init__(self, max_particles: int = DEFAULT_CAP, seed: int = 1962):
        self.max_particles = max(1, min(1000, int(max_particles)))
        self.patches: List[FoamPatch] = []
        self.rng = random.Random(seed)
        self.elapsed = 0.0
        self._wake_accum = 0.0
        self._bow_accum = 0.0
        self._side_accum = 0.0
        self._spray_accum = 0.0
        self._crest_accum = 0.0
        self._crest_cooldowns: Dict[Tuple[int, int], float] = {}
        self.emitted_total = 0
        self.recycled_total = 0
        self.peak_active = 0

    @property
    def active_count(self) -> int:
        return len(self.patches)

    def clear(self) -> None:
        self.patches.clear()
        self._crest_cooldowns.clear()
        self._wake_accum = self._bow_accum = self._side_accum = self._spray_accum = 0.0
        self._crest_accum = 0.0

    def _world_point(self, ship_x: float, ship_y: float, heading: float,
                     local_x: float, local_y: float) -> Vec2:
        c, s = math.cos(heading), math.sin(heading)
        return (ship_x + local_x * c - local_y * s,
                ship_y + local_x * s + local_y * c)

    def _insert(self, patch: FoamPatch) -> None:
        if len(self.patches) >= self.max_particles:
            # Recycle the least visible patch, not a random one, so heavy weather
            # doesn't cause sudden arbitrary disappearance across the whole sea.
            idx = min(range(len(self.patches)),
                      key=lambda i: self.patches[i].opacity * self.patches[i].width)
            self.patches.pop(idx)
            self.recycled_total += 1
        self.patches.append(patch)
        self.emitted_total += 1
        self.peak_active = max(self.peak_active, len(self.patches))

    def _make_patch(self, kind: str, x: float, y: float, angle: float,
                    current: Vec2, wind: Vec2, sea: float) -> FoamPatch:
        r = self.rng
        turbulence = (1.8 + sea * 8.0) if kind in ("crest", "spray") else (1.0 + sea * 4.0)
        vx = current[0] * 0.58 + wind[0] * (0.10 + sea * 0.12) + r.uniform(-turbulence, turbulence)
        vy = current[1] * 0.58 + wind[1] * (0.10 + sea * 0.12) + r.uniform(-turbulence, turbulence)
        if kind == "wake":
            length, width = r.uniform(22, 52), r.uniform(8, 17)
            life, strength = r.uniform(6.0, 14.0), r.uniform(0.50, 0.98)
        elif kind == "bow":
            length, width = r.uniform(20, 42), r.uniform(8, 17)
            life, strength = r.uniform(2.0, 4.2), r.uniform(0.50, 0.95)
        elif kind == "side":
            length, width = r.uniform(18, 46), r.uniform(7, 15)
            life, strength = r.uniform(3.0, 7.5), r.uniform(0.42, 0.92)
        elif kind == "crest":
            length, width = r.uniform(24, 66), r.uniform(8, 22)
            life, strength = r.uniform(3.5, 9.5), r.uniform(0.38, 0.88)
        else:  # airborne-looking spindrift/spray: thin, small, and quickly gone
            length, width = r.uniform(9, 24), r.uniform(3, 8)
            life, strength = r.uniform(0.45, 1.35), r.uniform(0.28, 0.72)
            vx += wind[0] * 0.5
            vy += wind[1] * 0.5
        return FoamPatch(float(x), float(y), vx, vy, 0.0, life, length, width,
                         angle + r.uniform(-0.38, 0.38), strength, kind,
                         r.randrange(1, 2**30))

    def _emit_at(self, kind: str, ship_x: float, ship_y: float, heading: float,
                 local_x: float, local_y: float, angle: float, current: Vec2,
                 wind: Vec2, sea: float) -> None:
        x, y = self._world_point(ship_x, ship_y, heading, local_x, local_y)
        self._insert(self._make_patch(kind, x, y, angle, current, wind, sea))

    def _emit_wake(self, kind: str, ship_x: float, ship_y: float, heading: float,
                   ship_length: float, ship_beam: float, current: Vec2,
                   wind: Vec2, sea: float) -> None:
        r = self.rng
        half_l, half_b = ship_length * 0.5, ship_beam * 0.5
        if kind == "wake":
            # Emit just abaft the stern. Later patches appear farther along the
            # route, so earlier patches remain in world space as the ship moves.
            local_x = -half_l * r.uniform(0.88, 1.08)
            local_y = r.uniform(-half_b * 0.40, half_b * 0.40)
            angle = heading + r.uniform(-0.27, 0.27)
        elif kind == "bow":
            side = -1.0 if r.random() < 0.5 else 1.0
            local_x = half_l * r.uniform(0.60, 0.92)
            local_y = side * half_b * r.uniform(0.58, 0.97)
            angle = heading + side * r.uniform(0.22, 0.78)
        elif kind == "side":
            side = -1.0 if r.random() < 0.5 else 1.0
            local_x = r.uniform(-half_l * 0.42, half_l * 0.52)
            local_y = side * (half_b + r.uniform(5.0, 24.0 + sea * 24.0))
            angle = heading + r.uniform(-0.50, 0.50)
        else:  # spray from bow/shoulders, not a giant continuous white ribbon
            side = -1.0 if r.random() < 0.5 else 1.0
            local_x = half_l * r.uniform(0.58, 0.90)
            local_y = side * half_b * r.uniform(0.25, 1.05)
            angle = heading + side * r.uniform(0.35, 1.0)
        self._emit_at(kind, ship_x, ship_y, heading, local_x, local_y,
                      angle, current, wind, sea)

    def emit_strike(self, ship_x: float, ship_y: float, heading: float, *, zone: str, kind: str,
                    energy: float, local_x: float, local_y: float, nx: float, ny: float,
                    current: Vec2 = (0.0, 0.0), wind: Vec2 = (0.0, 0.0), sea: float = 0.5) -> int:
        """A wave breaking against the hull: foam lumps at the rail plus short-lived spray.

        Reuses the existing ``side`` / ``crest`` / ``spray`` patch kinds, so the
        renderer, caps and lifecycle rules apply unchanged.  Returns the number
        of patches requested.
        """
        e = clamp(float(energy), 0.0, 1.0)
        sea = clamp(float(sea), 0.0, 1.0)
        # Outward normal in world coordinates.
        c, s = math.cos(heading), math.sin(heading)
        wn = (nx * c - ny * s, nx * s + ny * c)
        n_angle = math.atan2(wn[1], wn[0])
        along = n_angle + math.pi * 0.5
        n = 2 + int(round(3.0 * e)) + (3 if kind == "overtop" else 0)
        r = self.rng
        for i in range(n):
            off = r.uniform(4.0, 16.0 + 40.0 * e)
            slide = r.uniform(-1.0, 1.0) * (30.0 + 80.0 * e)
            # Out from the rail along the normal, and spread along the rail tangent (-ny, nx).
            lx = local_x + nx * off - ny * slide
            ly = local_y + ny * off + nx * slide
            patch_kind = "side" if i % 3 == 0 else ("crest" if (kind == "overtop" and i % 3 == 1) else "spray")
            self._emit_at(patch_kind, ship_x, ship_y, heading, lx, ly,
                          along + r.uniform(-0.5, 0.5), current, wind, sea)
            patch = self.patches[-1]
            # Hull strikes start brighter and push the foam away from the rail.
            patch.intensity = clamp(patch.intensity * (0.75 + 0.5 * e), 0.2, 1.0)
            patch.vx += wn[0] * (18.0 + 70.0 * e) * r.uniform(0.4, 1.0)
            patch.vy += wn[1] * (18.0 + 70.0 * e) * r.uniform(0.4, 1.0)
        return n

    @staticmethod
    def _stable_jitter(cx: int, cy: int, salt: int) -> float:
        n = (cx * 374761393 + cy * 668265263 + salt * 2147483647) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
        n ^= n >> 16
        return (n & 0xFFFFFF) / 0xFFFFFF

    def _scan_whitecaps(self, ship_x: float, ship_y: float, sea: float,
                        wave_strength: float, wave_direction: float,
                        wave_height: Callable[[float, float], float],
                        visible_radius: float, current: Vec2, wind: Vec2) -> None:
        # Whitecaps are weather-driven and remain possible at zero vessel speed.
        if sea < 0.32 or wave_strength < 0.16:
            return
        radius = max(500.0, visible_radius * 1.02)
        cell = max(300.0, radius / 5.0)
        cx0, cx1 = math.floor((ship_x - radius) / cell), math.floor((ship_x + radius) / cell)
        cy0, cy1 = math.floor((ship_y - radius) / cell), math.floor((ship_y + radius) / cell)
        crest_axis_x, crest_axis_y = math.cos(wave_direction), math.sin(wave_direction)
        sample = max(42.0, min(95.0, cell * 0.23))
        chance = clamp(0.035 + sea * 0.18 + wave_strength * 0.035, 0.0, 0.27)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                key = (cx, cy)
                if self._crest_cooldowns.get(key, -1.0) > self.elapsed:
                    continue
                x = (cx + self._stable_jitter(cx, cy, 1)) * cell
                y = (cy + self._stable_jitter(cx, cy, 2)) * cell
                if math.hypot(x - ship_x, y - ship_y) > radius:
                    continue
                h0 = wave_height(x, y)
                ha = wave_height(x + crest_axis_x * sample, y + crest_axis_y * sample)
                hb = wave_height(x - crest_axis_x * sample, y - crest_axis_y * sample)
                crest_energy = h0 - 0.5 * (ha + hb)
                if crest_energy <= max(0.45, wave_strength * 0.75):
                    continue
                self._crest_cooldowns[key] = self.elapsed + self.rng.uniform(5.0, 11.0)
                if self._stable_jitter(cx, cy, int(self.elapsed / self.CREST_SCAN_INTERVAL) + 3) > chance:
                    continue
                angle = wave_direction + math.pi * 0.5
                self._insert(self._make_patch("crest", x, y, angle, current, wind, sea))
        # Prevent the deterministic cell history from growing through endless voyages.
        if len(self._crest_cooldowns) > 900:
            self._crest_cooldowns = {k: t for k, t in self._crest_cooldowns.items()
                                     if t > self.elapsed and
                                     abs(k[0] * cell - ship_x) < radius * 2.0 and
                                     abs(k[1] * cell - ship_y) < radius * 2.0}

    def update(self, dt: float, *, ship_position: Vec2, heading: float,
               ship_speed_fraction: float, sea_state: float, wave_strength: float,
               wave_direction: float, ship_length: float, ship_beam: float,
               current_velocity: Vec2 = (0.0, 0.0), visible_radius: float = 1500.0,
               wave_height: Optional[Callable[[float, float], float]] = None,
               wind_strength: float = 0.45,
               wind_direction: Optional[float] = None) -> None:
        dt = max(0.0, float(dt))
        if dt <= 0.0:
            return
        self.elapsed += dt
        sx, sy = float(ship_position[0]), float(ship_position[1])
        sea = clamp(float(sea_state), 0.0, 1.0)
        speed = clamp(float(ship_speed_fraction), 0.0, 1.0)
        wave_strength = clamp(float(wave_strength), 0.0, 1.5)
        wind_strength = clamp(float(wind_strength), 0.0, 1.0)
        # Wind direction comes from the existing weather/wave field; its magnitude
        # comes from Weather.wind. This keeps foam drift subtle in a calm breeze
        # and visibly stronger in a storm without introducing another weather model.
        wind_angle = wave_direction if wind_direction is None else float(wind_direction)
        wind = (math.cos(wind_angle) * wind_strength,
                math.sin(wind_angle) * wind_strength)
        current = (float(current_velocity[0]), float(current_velocity[1]))

        self._wake_accum += dt * speed * (3.0 + 10.0 * speed)
        self._bow_accum += dt * speed * (1.2 + 2.8 * sea)
        self._side_accum += dt * speed * (1.8 + 3.0 * sea)
        self._spray_accum += dt * (max(0.0, speed - 0.35) * (0.5 + 4.0 * sea)
                                  + max(0.0, sea - 0.68) * 1.6)
        emissions = (("wake", "_wake_accum"), ("bow", "_bow_accum"),
                     ("side", "_side_accum"), ("spray", "_spray_accum"))
        for kind, attr in emissions:
            accum = getattr(self, attr)
            due = max(0, int(accum))
            count = min(due, self.MAX_EVENTS_PER_UPDATE)
            # Retain only the fractional remainder. A debugger pause or slow frame
            # must not queue hundreds of stale emissions and then dump them into
            # one wake burst over the next few rendered frames.
            setattr(self, attr, accum - due)
            for _ in range(count):
                self._emit_wake(kind, sx, sy, heading, ship_length, ship_beam,
                                current, wind, sea)

        self._crest_accum += dt
        while self._crest_accum >= self.CREST_SCAN_INTERVAL:
            self._crest_accum -= self.CREST_SCAN_INTERVAL
            if wave_height is not None:
                self._scan_whitecaps(sx, sy, sea, wave_strength, wave_direction,
                                     wave_height, max(350.0, visible_radius), current, wind)

        # Advance persistent world-space patches and let the local water/current
        # carry them. The ship's heading is never applied to old patch positions.
        for p in self.patches:
            p.age += dt
            p.vx += (current[0] * 0.12 + wind[0] * sea * 1.8 - p.vx * 0.12) * dt
            p.vy += (current[1] * 0.12 + wind[1] * sea * 1.8 - p.vy * 0.12) * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            # A gentle transverse wobble makes patches break up without per-frame
            # random noise, which otherwise looks like flickering snow.
            wobble = math.sin(self.elapsed * 0.8 + p.seed * 0.000013) * (0.5 + sea * 1.4)
            p.x += -wind[1] * wobble * dt
            p.y += wind[0] * wobble * dt
        self.patches = [p for p in self.patches
                        if p.age < p.lifetime and
                        math.hypot(p.x - sx, p.y - sy) < max(700.0, visible_radius * 1.55)]
        self.peak_active = max(self.peak_active, len(self.patches))
        if len(self.patches) > self.max_particles:  # defensive invariant
            del self.patches[:len(self.patches) - self.max_particles]
