"""Sea-to-ship interaction for Fishing Simulator (v13.2.05).

Three small, display-free models live here so they can be tested headlessly:

* ``HullWaveInteraction`` compares the *actual* sea surface at the hull's rail
  points with where the hull sits (heave + pitch + roll) and the freeboard it
  has left.  A crest that reaches the rail produces a ``HullStrike`` — either a
  ``slap`` (spray, foam, ripples) or an ``overtop`` (green water on deck).
* ``RippleSystem`` keeps a bounded set of expanding rings in absolute water
  coordinates, like ``SeaFoamSystem`` does for foam.
* ``FloodingModel`` advances deck / engine-room / ice-hold water with real
  feedback: water lowers freeboard, freeboard governs scupper drainage and
  ingress, deck water free-surface-lolls the ship to one side, and the engine
  powers the bilge pump that keeps the lower spaces in hand.

Conventions match the game: deck coordinates have the origin at the ship's
centre, +x toward the bow and +y toward starboard; world coordinates are
absolute water coordinates.
"""
from dataclasses import dataclass, field
import math
import random
from typing import Callable, Dict, List, Optional, Tuple

Vec2 = Tuple[float, float]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def deck_to_world(ship_x: float, ship_y: float, heading: float, lx: float, ly: float) -> Vec2:
    c, s = math.cos(heading), math.sin(heading)
    return (ship_x + lx * c - ly * s, ship_y + lx * s + ly * c)


# ---------------------------------------------------------------- hull strikes

@dataclass(slots=True)
class HullStrike:
    zone: str              # "bow" / "stern" / "port" / "stbd"
    kind: str              # "slap" (spray only) or "overtop" (green water aboard)
    energy: float          # 0..1
    local_x: float         # deck coordinates of the struck rail point
    local_y: float
    nx: float              # outward hull normal in deck coordinates
    ny: float


class HullWaveInteraction:
    """Detect waves reaching the rails of a hull riding a procedural sea.

    The sea surface is supplied as ``wave_height(x, y)`` in world coordinates.
    The hull answers the sea through three critically damped second-order
    responses (heave, pitch, roll), so it rises over a long swell but cannot
    keep up with steep, short seas or with a quick encounter at speed — the bow
    plunges into the crest.  The difference between the sea at a rail point and
    the hull's own height there is how far water stands above the rail datum;
    once that exceeds the remaining freeboard, the sea comes aboard.
    """

    HEAVE_WN, PITCH_WN, ROLL_WN = 1.55, 1.25, 1.05    # rad/s natural responses
    FOLLOW = 0.92          # fraction of the wave slope the hull is trying to take
    SLAP_FRACTION = 0.52   # fraction of freeboard where a crest starts to slap the side
    # (zone, local x as a fraction of length, local y as a fraction of half-beam, base freeboard px)
    POINTS = (
        ("bow", 0.47, 0.0, 129.0),
        ("stern", -0.485, 0.0, 84.0),
        ("port", 0.22, -1.0, 126.0),
        ("port", -0.22, -1.0, 99.0),
        ("stbd", 0.22, 1.0, 126.0),
        ("stbd", -0.22, 1.0, 99.0),
    )
    NORMALS = {"bow": (1.0, 0.0), "stern": (-1.0, 0.0), "port": (0.0, -1.0), "stbd": (0.0, 1.0)}

    def __init__(self, length: float = 1100.0, beam: float = 280.0):
        self.length, self.beam = float(length), float(beam)
        # response states: [value, rate] for heave (px), pitch (px/px), roll (px/px)
        self._h = [0.0, 0.0]
        self._p = [0.0, 0.0]
        self._r = [0.0, 0.0]
        self._primed = False
        self._rel_prev: Dict[int, float] = {}
        self._cooldown: Dict[Tuple[str, str], float] = {}
        self.rel: Dict[int, float] = {}
        self.immersion: Dict[str, float] = {"bow": 0.0, "stern": 0.0, "port": 0.0, "stbd": 0.0}
        self.strikes_total = 0
        self.overtops_total = 0

    @property
    def heave(self) -> float:
        return self._h[0]

    @property
    def heave_rate(self) -> float:
        return self._h[1]

    def reset(self) -> None:
        self._primed = False
        self._rel_prev.clear()
        self._cooldown.clear()
        self._h, self._p, self._r = [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]

    @staticmethod
    def _respond(state, target: float, wn: float, dt: float) -> None:
        # Sub-step so a long frame cannot destabilise the integrator.
        steps = max(1, int(math.ceil(dt * wn / 0.12)))
        h = dt / steps
        for _ in range(steps):
            acc = wn * wn * (target - state[0]) - 2.0 * wn * state[1]
            state[1] += acc * h
            state[0] += state[1] * h

    def update(self, dt: float, *, ship_position: Vec2, heading: float,
               wave_height: Callable[[float, float], float],
               freeboard_factor: float = 1.0, list_bias: float = 0.0) -> List[HullStrike]:
        """Advance one step and return the strikes that began during it.

        ``list_bias`` is the normalized static list (+ starboard down): it
        drops the low rail's freeboard and lifts the high one.
        """
        dt = float(dt)
        if dt < 1e-4:
            return []
        sx, sy = float(ship_position[0]), float(ship_position[1])
        L, half_b = self.length, self.beam * 0.5
        c, s_ = math.cos(heading), math.sin(heading)
        # Sea under the hull and its local slopes (same stencil the deck-slope uses).
        sa = L * 0.28
        h_c = wave_height(sx, sy)
        h_bow = wave_height(sx + c * sa, sy + s_ * sa)
        h_stern = wave_height(sx - c * sa, sy - s_ * sa)
        h_stbd = wave_height(sx - s_ * half_b, sy + c * half_b)
        h_port = wave_height(sx + s_ * half_b, sy - c * half_b)
        mean = (h_c + 0.25 * (h_bow + h_stern + h_stbd + h_port)) / 2.0
        grad_x = (h_bow - h_stern) / (2.0 * sa) * self.FOLLOW
        grad_y = (h_stbd - h_port) / (2.0 * half_b) * self.FOLLOW
        if not self._primed:
            self._h[0], self._p[0], self._r[0] = mean, grad_x, grad_y
            self._primed = True
        self._respond(self._h, mean, self.HEAVE_WN, dt)
        self._respond(self._p, grad_x, self.PITCH_WN, dt)
        self._respond(self._r, grad_y, self.ROLL_WN, dt)

        for k in self._cooldown:
            self._cooldown[k] = max(0.0, self._cooldown[k] - dt)

        strikes: List[HullStrike] = []
        worst: Dict[str, float] = {z: 0.0 for z in self.immersion}
        for idx, (zone, fx, fy, base_fb) in enumerate(self.POINTS):
            lx, ly = fx * L, fy * half_b
            nx, ny = self.NORMALS[zone]
            # Sample just outside the rail so the water we compare is the water touching the hull.
            wx, wy = deck_to_world(sx, sy, heading, lx + nx * 8.0, ly + ny * 8.0)
            sea = wave_height(wx, wy)
            rel = sea - (self._h[0] + self._p[0] * lx + self._r[0] * ly)
            fb = base_fb * clamp(freeboard_factor, 0.25, 1.0)
            if zone == "stbd":
                fb *= clamp(1.0 - 0.85 * list_bias, 0.35, 1.25)
            elif zone == "port":
                fb *= clamp(1.0 + 0.85 * list_bias, 0.35, 1.25)
            prev = self._rel_prev.get(idx, rel)
            vel = (rel - prev) / dt
            self._rel_prev[idx] = rel
            self.rel[idx] = rel
            worst[zone] = max(worst[zone], clamp((rel - fb) / max(1.0, fb), 0.0, 1.0))
            ratio = rel / max(1.0, fb)
            # Edge-triggered overtopping: the crest has to *arrive* at the rail.
            if (rel > fb and prev <= fb and self._cooldown.get((zone, "overtop"), 0.0) <= 0.0
                    and self._cooldown.get(("any", "overtop"), 0.0) <= 0.0):
                energy = clamp(0.35 + (rel - fb) / (0.7 * fb) + max(0.0, vel) / (2.4 * fb), 0.35, 1.0)
                strikes.append(HullStrike(zone, "overtop", energy, lx, ly, nx, ny))
                self._cooldown[(zone, "overtop")] = 3.5
                self._cooldown[("any", "overtop")] = 1.1     # one sea does not board four rails at once
                self._cooldown[(zone, "slap")] = 0.9
                self.overtops_total += 1
            elif (ratio > self.SLAP_FRACTION and vel > 0.0 and rel <= fb
                  and self._cooldown.get((zone, "slap"), 0.0) <= 0.0):
                energy = clamp(0.18 + 0.55 * (ratio - self.SLAP_FRACTION) / (1.0 - self.SLAP_FRACTION)
                               + vel / (3.0 * fb), 0.12, 0.85)
                strikes.append(HullStrike(zone, "slap", energy, lx, ly, nx, ny))
                self._cooldown[(zone, "slap")] = 0.8 + 0.5 * (1.0 - energy)
        self.immersion = worst
        self.strikes_total += len(strikes)
        return strikes


# --------------------------------------------------------------------- ripples

@dataclass(slots=True)
class Ripple:
    x: float
    y: float
    radius: float
    growth: float          # px/s
    age: float
    life: float
    strength: float        # 0..1
    seed: int
    stretch_angle: float = 0.0   # world angle the ring is elongated along (0 stretch = circle)
    stretch: float = 0.0

    @property
    def opacity(self) -> float:
        t = clamp(self.age / max(0.001, self.life), 0.0, 1.0)
        return clamp(self.strength * (1.0 - t) ** 1.3 * clamp(self.age / 0.12, 0.0, 1.0), 0.0, 1.0)


class RippleSystem:
    """Bounded expanding rings anchored to water coordinates."""

    DEFAULT_CAP = 110

    def __init__(self, max_ripples: int = DEFAULT_CAP, seed: int = 2604):
        self.max_ripples = max(1, min(400, int(max_ripples)))
        self.ripples: List[Ripple] = []
        self.rng = random.Random(seed)
        self.emitted_total = 0
        self.recycled_total = 0
        self._bow_accum = 0.0
        self._prop_accum = 0.0
        self._roll_accum = 0.0

    @property
    def active_count(self) -> int:
        return len(self.ripples)

    def clear(self) -> None:
        self.ripples.clear()
        self._bow_accum = self._prop_accum = self._roll_accum = 0.0

    def emit(self, x: float, y: float, strength: float, *, radius: float = 6.0, growth: float = 38.0,
             life: float = 2.8, stretch_angle: float = 0.0, stretch: float = 0.0) -> None:
        r = self.rng
        if len(self.ripples) >= self.max_ripples:
            idx = min(range(len(self.ripples)), key=lambda i: self.ripples[i].opacity)
            self.ripples.pop(idx)
            self.recycled_total += 1
        self.ripples.append(Ripple(float(x), float(y), radius, growth * r.uniform(0.85, 1.15), 0.0,
                                   life * r.uniform(0.85, 1.2), clamp(strength, 0.05, 1.0),
                                   r.randrange(1, 2 ** 30), stretch_angle, stretch))
        self.emitted_total += 1

    def emit_impact(self, ship_x: float, ship_y: float, heading: float, strike: HullStrike,
                    current: Vec2 = (0.0, 0.0)) -> None:
        """A wave hitting the hull throws out a couple of fast rings plus a slower trailing pair."""
        base = deck_to_world(ship_x, ship_y, heading, strike.local_x + strike.nx * 14.0,
                             strike.local_y + strike.ny * 14.0)
        n_world = math.atan2(strike.nx * math.sin(heading) + strike.ny * math.cos(heading),
                             strike.nx * math.cos(heading) - strike.ny * math.sin(heading))
        e = strike.energy
        count = 2 + int(2 * e) + (1 if strike.kind == "overtop" else 0)
        for i in range(count):
            off = i * (10.0 + 10.0 * e)
            self.emit(base[0] + math.cos(n_world) * off, base[1] + math.sin(n_world) * off,
                      0.38 + 0.55 * e - 0.08 * i, radius=8.0 + 6.0 * i,
                      growth=(52.0 + 70.0 * e) * (1.0 - 0.12 * i), life=2.2 + 2.4 * e,
                      stretch_angle=n_world + math.pi * 0.5, stretch=0.35)

    def update(self, dt: float, *, ship_position: Vec2, heading: float, speed_fraction: float,
               throttle: float, sea_state: float, roll_rate: float = 0.0, ship_length: float = 1100.0,
               ship_beam: float = 280.0, current_velocity: Vec2 = (0.0, 0.0),
               keep_radius: float = 1800.0) -> None:
        dt = max(0.0, float(dt))
        if dt <= 0.0:
            return
        sx, sy = float(ship_position[0]), float(ship_position[1])
        speed = clamp(speed_fraction, 0.0, 1.0)
        sea = clamp(sea_state, 0.0, 1.0)
        r = self.rng
        # Bow and quarter ripples spread from the moving hull; a stopped hull makes none.
        self._bow_accum += dt * speed * (2.4 + 4.0 * speed)
        # Propeller wash keeps stirring the surface at the stern, even at low speed.
        self._prop_accum += dt * clamp(throttle, 0.0, 1.0) * 3.2
        # A rolling hull slops water against its own sides, even when stationary.
        self._roll_accum += dt * clamp(abs(roll_rate) * 1.4, 0.0, 1.6) * (0.35 + 0.65 * sea)
        for attr, kind in (("_bow_accum", "bow"), ("_prop_accum", "prop"), ("_roll_accum", "roll")):
            accum = getattr(self, attr)
            due = min(int(accum), 6)
            setattr(self, attr, accum - int(accum))
            for _ in range(due):
                side = -1.0 if r.random() < 0.5 else 1.0
                if kind == "bow":
                    lx, ly = ship_length * r.uniform(0.30, 0.46), side * ship_beam * r.uniform(0.50, 0.66)
                    self.emit(*deck_to_world(sx, sy, heading, lx, ly), 0.30 + 0.35 * speed,
                              radius=5.0, growth=34.0 + 30.0 * speed, life=2.6 + 1.4 * speed,
                              stretch_angle=heading, stretch=0.45)
                elif kind == "prop":
                    lx, ly = -ship_length * 0.5 - r.uniform(8, 28), r.uniform(-0.18, 0.18) * ship_beam
                    self.emit(*deck_to_world(sx, sy, heading, lx, ly), 0.28 + 0.30 * clamp(throttle, 0, 1),
                              radius=6.0, growth=28.0, life=2.6)
                else:
                    lx = ship_length * r.uniform(-0.30, 0.34)
                    ly = side * (ship_beam * 0.5 + 10.0)
                    self.emit(*deck_to_world(sx, sy, heading, lx, ly), 0.22 + 0.30 * sea,
                              radius=5.0, growth=24.0 + 12.0 * sea, life=2.2,
                              stretch_angle=heading, stretch=0.30)
        cx, cy = float(current_velocity[0]) * 0.5, float(current_velocity[1]) * 0.5
        for rp in self.ripples:
            rp.age += dt
            rp.radius += rp.growth * dt
            rp.growth *= math.exp(-0.55 * dt)      # rings slow as they spread and thin out
            rp.x += cx * dt
            rp.y += cy * dt
        limit = max(700.0, keep_radius)
        self.ripples = [p for p in self.ripples if p.age < p.life and math.hypot(p.x - sx, p.y - sy) < limit]


# --------------------------------------------------------------------- flooding

@dataclass(slots=True)
class FloodReport:
    state: str
    changed: bool
    net_rate: float           # reserve-weighted water change, per second (smoothed)
    pump_flow: float          # bilge volume removed this step, per second
    reserve: float
    list_degrees: float


class FloodingModel:
    """Compartment water with feedback.  Operates on any object exposing:

    ``flood`` (deck standing water), ``engine_flood``, ``hold_flood`` in 0..1 and
    the model-owned ``list_lat``, ``list_trim``, ``freeboard_factor``,
    ``pump_flow``, ``flood_net``, ``flood_state``, ``flood_taking_t``, ``flood_calm_t``.
    ``attach`` creates the owned attributes with defaults.
    """

    DECK_W, ENGINE_W, HOLD_W = 0.30, 0.40, 0.30     # contribution of each space to lost buoyancy
    FOUNDER_RESERVE = 0.22
    LIST_CRITICAL = 0.40                            # normalized; about 18 degrees
    DEGREES_PER_LIST = 45.0
    PUMP_ENGINE_RATE = 0.0050                       # engine-room bilge per second at full power
    PUMP_HOLD_RATE = 0.0022                         # leftover suction spills to the ice hold
    STATES = ("NORMAL", "TAKING_ON_WATER", "FLOODED", "CRITICAL")
    CALM_STEP = 5.0

    @classmethod
    def attach(cls, s) -> None:
        defaults = dict(flood=0.0, engine_flood=0.0, hold_flood=0.0, list_lat=0.0, list_trim=0.0,
                        freeboard_factor=1.0, pump_flow=0.0, flood_net=0.0,
                        flood_state="NORMAL", flood_taking_t=0.0, flood_calm_t=0.0)
        for name, value in defaults.items():
            if not hasattr(s, name):
                setattr(s, name, value)

    # -- derived quantities -------------------------------------------------
    @classmethod
    def water_load(cls, s) -> float:
        return cls.DECK_W * s.flood + cls.ENGINE_W * s.engine_flood + cls.HOLD_W * s.hold_flood

    @classmethod
    def reserve_buoyancy(cls, s) -> float:
        return clamp(1.0 - cls.water_load(s), 0.0, 1.0)

    @classmethod
    def freeboard_factor_for(cls, s) -> float:
        return clamp(1.0 - 0.55 * cls.water_load(s), 0.35, 1.0)

    @classmethod
    def stability(cls, s) -> float:
        """Righting stiffness 1 -> 0.3: loose deck water costs most, baffled hold water least."""
        fsm = 0.62 * s.flood + 0.24 * s.engine_flood + 0.08 * s.hold_flood
        return clamp(1.0 - fsm, 0.30, 1.0)

    @classmethod
    def list_for(cls, s) -> float:
        return clamp(s.list_lat * (0.50 * s.flood + 0.10 * s.engine_flood), -0.60, 0.60)

    # -- events -----------------------------------------------------------------
    @classmethod
    def boarded(cls, s, side: str, intensity: float) -> float:
        """Green water arrives; returns the volume added to the deck."""
        cls.attach(s)
        intensity = clamp(intensity, 0.0, 1.0)
        added = (0.15 + 0.11 * intensity) * intensity * (1.0 + 0.7 * (1.0 - s.freeboard_factor))
        s.flood = min(1.0, s.flood + added)
        sign = {"stbd": 1.0, "port": -1.0}.get(side, 0.0)
        s.list_lat = clamp(s.list_lat + sign * 0.55 * intensity, -1.0, 1.0)
        return added

    # -- step -------------------------------------------------------------------
    @classmethod
    def step(cls, s, dt: float, *, sea: float, slope_y: float, engine_hatch_open: bool,
             open_hold_hatches: int, pump_power: float, immersion: float = 0.0) -> FloodReport:
        cls.attach(s)
        dt = max(0.0, float(dt))
        if dt <= 0.0:
            return FloodReport(s.flood_state, False, s.flood_net, s.pump_flow,
                               cls.reserve_buoyancy(s), s.list_trim * cls.DEGREES_PER_LIST)
        sea = clamp(sea, 0.0, 1.5)
        before = cls.water_load(s)
        ff = cls.freeboard_factor_for(s)
        s.freeboard_factor = ff

        # Free surface: deck water runs to the low side, and a list makes the low side lower still.
        pull = clamp(5.0 * (slope_y + 1.0 * s.list_trim), -1.0, 1.0)
        s.list_lat += (pull - s.list_lat) * (1.0 - math.exp(-dt / 5.0))
        s.list_lat = clamp(s.list_lat, -1.0, 1.0)
        s.list_trim = cls.list_for(s)

        # Scuppers: head-driven drainage, choked as the hull settles; a rail awash lets the sea back in.
        drain = (0.010 + 0.016 * math.sqrt(max(s.flood, 0.0)) + 0.020 * abs(slope_y)) * ff * ff
        backflow = 0.0
        if ff < 0.72:
            backflow += 0.006 * sea * (0.72 - ff) / 0.72
        backflow += 0.004 * sea * clamp(abs(s.list_trim) - 0.15, 0.0, 1.0)
        backflow += 0.010 * clamp(immersion, 0.0, 1.0)
        s.flood = clamp(s.flood - drain * dt + backflow * dt, 0.0, 1.0)

        # Closed covers still weep when they lie under deep deck water.
        weep = 0.0012 * max(0.0, s.flood - 0.45)
        s.engine_flood = clamp(s.engine_flood + weep * dt * (1.0 if not engine_hatch_open else 0.0), 0.0, 1.0)
        s.hold_flood = clamp(s.hold_flood + weep * 0.6 * dt * (1.0 if open_hold_hatches == 0 else 0.0), 0.0, 1.0)

        # Bilge pump: engine-powered; it clears the engine bilge first and spills any spare suction to the hold.
        pump_power = clamp(pump_power, 0.0, 1.0)
        cap = pump_power * cls.PUMP_ENGINE_RATE * dt
        take = min(s.engine_flood, cap)
        s.engine_flood -= take
        spare = cap - take
        hold_take = min(s.hold_flood, spare * (cls.PUMP_HOLD_RATE / cls.PUMP_ENGINE_RATE))
        s.hold_flood -= hold_take
        s.pump_flow = (take + hold_take) / dt

        # Smoothed net trend for readouts and the state machine (positive = gaining water).
        raw = (cls.water_load(s) - before) / dt
        s.flood_net += (raw - s.flood_net) * (1.0 - math.exp(-dt / 3.0))

        worst_low = max(s.engine_flood, s.hold_flood)
        reserve = cls.reserve_buoyancy(s)
        if s.flood_net > 0.0004 or worst_low > 0.12 or s.flood > 0.35:
            s.flood_taking_t += dt
        else:
            s.flood_taking_t = max(0.0, s.flood_taking_t - 2.0 * dt)
        if reserve <= cls.FOUNDER_RESERVE + 0.12 or worst_low > 0.90 or abs(s.list_trim) > cls.LIST_CRITICAL:
            new_state = "CRITICAL"
        elif worst_low > 0.55 or s.flood > 0.60 or abs(s.list_trim) > 0.22:
            new_state = "FLOODED"
        elif s.flood_taking_t > 6.0:
            new_state = "TAKING_ON_WATER"
        else:
            new_state = "NORMAL"
        # Warnings escalate at once but clear one level per CALM_STEP seconds of improvement.
        old_i, new_i = cls.STATES.index(s.flood_state), cls.STATES.index(new_state)
        if new_i < old_i:
            s.flood_calm_t += dt
            if s.flood_calm_t >= cls.CALM_STEP:
                s.flood_calm_t = 0.0
                new_state = cls.STATES[old_i - 1]
            else:
                new_state = s.flood_state
        else:
            s.flood_calm_t = 0.0
        changed = new_state != s.flood_state
        s.flood_state = new_state
        return FloodReport(new_state, changed, s.flood_net, s.pump_flow, reserve,
                           s.list_trim * cls.DEGREES_PER_LIST)
