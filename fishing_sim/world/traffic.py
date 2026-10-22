"""Deterministic, schedule-driven regional AI traffic for v13.2.01.

Coarse vessels are immutable-ish schedule records. Position is sampled on a low
frequency tick; the index/LOD layer controls nearby queries and the renderer never
owns movement. Local x/y are NM east/north of Hakodate. Screen/chart conversion
belongs to an integration adapter, not these entities.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
import random
from typing import Iterable

from .chunk_manager import LODManager, SpatialIndex, DEFAULT_CELL_SIZE_NM
from .coordinates import PHASE_B_BOUNDS_NM
from .seeding import SEED_ALGORITHM_VERSION, stable_seed, stable_vessel_id

DAY_LEN_SIM_SECONDS = 600.0
SIM_NM_PER_KNOT_SECOND = 0.04  # 24 h in-game / 600 simulation seconds
TRAFFIC_TICK_INTERVAL_S = 3.0
VISUAL_SIGHTING_RADIUS_NM = 2.2
REPORT_STALE_AFTER_SIM_SECONDS = DAY_LEN_SIM_SECONDS * 45.0 / (24.0 * 60.0)
MAX_ACTIVE_RESCUE_CONTACTS = 3


class Activity(str, Enum):
    TRANSIT = "transit"
    FISHING = "fishing"
    HAULING = "hauling"
    ANCHORED = "anchored"
    DISTRESSED = "distressed"
    RETURNING = "returning"


class Archetype(str, Enum):
    PLAYER = "player"
    INDEPENDENT_LONGLINE = "ind_longline"
    INDEPENDENT_GILLNET = "ind_gillnet"
    CORPORATE_CATCHER = "corp_catcher"
    CORPORATE_LONGLINER = "corp_longline"
    MOTHERSHIP = "mothership"
    COAST_GUARD = "coast_guard"
    SOVIET_TRAWLER = "soviet"


# The source Plan 13.2.xx total is 461, not the prose estimate of ~450.
SOURCE_FLEET_COUNTS = {
    Archetype.CORPORATE_CATCHER: 300,
    Archetype.MOTHERSHIP: 11,
    Archetype.INDEPENDENT_GILLNET: 80,
    Archetype.INDEPENDENT_LONGLINE: 40,
    Archetype.CORPORATE_LONGLINER: 15,
    Archetype.COAST_GUARD: 5,
    Archetype.SOVIET_TRAWLER: 10,
}
SOURCE_FLEET_TOTAL = sum(SOURCE_FLEET_COUNTS.values())

# Phase A deliberately starts with a small, named pool; full source populations
# are a later content milestone after profiling and seasonal-density tuning.
PHASE_A_COUNTS = {
    # M11: denser but still regional fleet. The full 461-vessel source population
    # stays deferred until Phase B and performance profiling.
    Archetype.INDEPENDENT_LONGLINE: 14,
    Archetype.INDEPENDENT_GILLNET: 8,
    Archetype.CORPORATE_CATCHER: 8,
    Archetype.CORPORATE_LONGLINER: 3,
    Archetype.MOTHERSHIP: 2,
    Archetype.COAST_GUARD: 2,
    Archetype.SOVIET_TRAWLER: 3,
}
PHASE_A_FLEET_TOTAL = sum(PHASE_A_COUNTS.values())
PHASE_B_COUNTS = dict(SOURCE_FLEET_COUNTS)
PHASE_B_FLEET_TOTAL = sum(PHASE_B_COUNTS.values())

NAMES_BY_ARCHETYPE = {
    Archetype.INDEPENDENT_LONGLINE: (
        "Kita Maru", "Daiichi Maru", "Sakura Maru", "Shiranui Maru",
        "Hokusei Maru", "Kozu Maru", "Shinwa Maru", "Kuroshio Maru",
    ),
    Archetype.INDEPENDENT_GILLNET: (
        "Tenyo Maru", "Koyo Maru", "Taisei Maru", "Hachiman Maru", "Aoba Maru",
    ),
    Archetype.CORPORATE_CATCHER: (
        "Taiyo Maru No. 18", "Taiyo Maru No. 21", "Nichiro Maru No. 7", "Nichiro Maru No. 12",
    ),
    Archetype.CORPORATE_LONGLINER: ("Hokoku Maru No. 3", "Nisshin Maru No. 4"),
    Archetype.MOTHERSHIP: ("Taiyo Mothership",),
    Archetype.COAST_GUARD: ("Tsugaru",),
    Archetype.SOVIET_TRAWLER: ("SRT-204", "SRT-118"),
}

PERSONALITIES_BY_ARCHETYPE = {
    Archetype.INDEPENDENT_LONGLINE: ("cooperative", "cagey", "competitive", "gossip"),
    Archetype.INDEPENDENT_GILLNET: ("cooperative", "cagey", "gossip"),
    Archetype.CORPORATE_CATCHER: ("corporate",),
    Archetype.CORPORATE_LONGLINER: ("corporate", "cagey"),
    Archetype.MOTHERSHIP: ("official",),
    Archetype.COAST_GUARD: ("official",),
    Archetype.SOVIET_TRAWLER: ("hostile",),
}

RADIO_RANGE_NM = {
    "DSB": 27.0,
    "SSB": 49.0,
}


@dataclass(frozen=True)
class SchedulePoint:
    time_s: float
    x_nm: float
    y_nm: float
    activity: Activity


@dataclass
class AIShip:
    id: str
    name: str
    callsign: str
    archetype: Archetype
    home_port: str
    personality: str
    schedule: tuple[SchedulePoint, ...]
    period_s: float
    speed_kn: float
    radio_fit: str = "DSB"
    radio_range_nm: float = 27.0
    trust: float = 0.0
    last_contact_sim_time: float = -1e9
    contact_count: int = 0
    contact_attempts: int = 0
    mayday_sent: bool = False
    mayday_resolved: bool = False
    mayday_player_heard: bool = False
    distress_started_s: float | None = None
    distress_kind: str | None = None
    distress_origin_activity: Activity | None = None
    distress_decision: str | None = None
    distress_position_nm: tuple[float, float] | None = None
    distress_assistance_status: str = "none"
    distress_outcome: str | None = None
    # A physical position override freezes a vessel at a distress/assistance scene;
    # scheduled routes resume only when a future behavior explicitly releases it.
    position_override_nm: tuple[float, float] | None = None
    is_rival: bool = False
    activity_override: Activity | None = None
    position_nm: tuple[float, float] = (0.0, 0.0)
    heading_rad: float = 0.0
    activity: Activity = Activity.TRANSIT
    lod: str = "coarse"
    known_to_player: bool = False
    last_reported_position_nm: tuple[float, float] | None = None
    last_reported_heading_rad: float = 0.0
    last_report_time_s: float | None = None
    last_visual_report_s: float = -1e9
    report_count: int = 0
    # Runtime contacts (e.g. the active Coast Guard tow launch) share this same
    # identity with specialised state/rendering, and are not schedule-driven.
    runtime_kind: str = "scheduled"
    # For Phase B catcher boats, stable mothership identity ties the schedule to
    # the corporate collection/command cluster. Regeneration derives this field.
    mothership_id: str | None = None

    @property
    def marker_stale(self) -> bool:
        return self.last_report_time_s is None

    def report_age_s(self, sim_time_s: float) -> float:
        if self.last_report_time_s is None:
            return math.inf
        return max(0.0, float(sim_time_s) - self.last_report_time_s)

    def report_stale_at(self, sim_time_s: float) -> bool:
        return self.report_age_s(sim_time_s) >= REPORT_STALE_AFTER_SIM_SECONDS

    def report_position(self, sim_time_s: float, *, error_nm: float = 0.0,
                        rng: random.Random | None = None) -> None:
        """Refresh the player-facing plot, keeping it separate from physical truth."""
        error_nm = max(0.0, float(error_nm))
        rng = rng or random.Random(stable_seed("report", self.id, self.report_count))
        angle = rng.random() * math.tau
        ex, ey = math.cos(angle) * error_nm, math.sin(angle) * error_nm
        self.last_reported_position_nm = (self.position_nm[0] + ex, self.position_nm[1] + ey)
        self.last_reported_heading_rad = self.heading_rad
        self.last_report_time_s = float(sim_time_s)
        self.known_to_player = True
        self.report_count += 1

    def position_at(self, sim_time_s: float) -> tuple[tuple[float, float], float, Activity]:
        """Interpolate a closed route directly from simulation time (fast-forward safe)."""
        if not self.schedule or self.period_s <= 0.0:
            return self.position_nm, self.heading_rad, self.activity
        t = float(sim_time_s) % self.period_s
        points = self.schedule
        idx = 0
        for i in range(len(points) - 1):
            if points[i].time_s <= t < points[i + 1].time_s:
                idx = i
                break
        else:
            idx = len(points) - 1
        a = points[idx]
        b = points[idx + 1] if idx + 1 < len(points) else points[0]
        start_t = a.time_s
        end_t = b.time_s if idx + 1 < len(points) else self.period_s
        duration = max(1e-9, end_t - start_t)
        f = max(0.0, min(1.0, (t - start_t) / duration))
        dx, dy = b.x_nm - a.x_nm, b.y_nm - a.y_nm
        # Circular routes are bounded to the harbour chart, so seam interpolation is continuous.
        pos = (a.x_nm + dx * f, a.y_nm + dy * f)
        heading = math.atan2(-dy, dx) if abs(dx) + abs(dy) > 1e-9 else self.heading_rad
        activity = self.activity_override or a.activity
        return pos, heading, activity


ACTIVITY_CYCLE = {
    Archetype.INDEPENDENT_LONGLINE: (Activity.TRANSIT, Activity.FISHING, Activity.HAULING,
                                    Activity.FISHING, Activity.TRANSIT, Activity.HAULING,
                                    Activity.FISHING, Activity.TRANSIT),
    Archetype.INDEPENDENT_GILLNET: (Activity.TRANSIT, Activity.FISHING, Activity.HAULING,
                                    Activity.HAULING, Activity.FISHING, Activity.TRANSIT,
                                    Activity.FISHING, Activity.TRANSIT),
    Archetype.CORPORATE_CATCHER: (Activity.TRANSIT, Activity.FISHING, Activity.HAULING,
                                  Activity.HAULING, Activity.FISHING, Activity.TRANSIT,
                                  Activity.FISHING, Activity.HAULING),
    Archetype.CORPORATE_LONGLINER: (Activity.TRANSIT, Activity.FISHING, Activity.HAULING,
                                    Activity.FISHING, Activity.TRANSIT, Activity.HAULING,
                                    Activity.FISHING, Activity.TRANSIT),
    Archetype.MOTHERSHIP: (Activity.ANCHORED, Activity.ANCHORED, Activity.TRANSIT,
                           Activity.ANCHORED, Activity.ANCHORED, Activity.TRANSIT,
                           Activity.ANCHORED, Activity.ANCHORED),
    Archetype.COAST_GUARD: (Activity.TRANSIT, Activity.TRANSIT, Activity.RETURNING,
                            Activity.TRANSIT, Activity.TRANSIT, Activity.RETURNING,
                            Activity.TRANSIT, Activity.TRANSIT),
    Archetype.SOVIET_TRAWLER: (Activity.TRANSIT, Activity.FISHING, Activity.TRANSIT,
                               Activity.HAULING, Activity.TRANSIT, Activity.FISHING,
                               Activity.TRANSIT, Activity.HAULING),
}


def _radius_band(archetype: Archetype) -> tuple[float, float, float, float, float, float]:
    # center radius min/max, route radius min/max, speed min/max. Keep all tracks on
    # the legacy harbour-centered sheet while architecture is ready for Phase B.
    return {
        Archetype.INDEPENDENT_LONGLINE: (3.0, 24.0, 2.5, 7.5, 3.8, 8.2),
        Archetype.INDEPENDENT_GILLNET: (7.0, 31.0, 3.5, 8.0, 3.5, 7.8),
        Archetype.CORPORATE_CATCHER: (22.0, 43.0, 4.5, 8.0, 4.5, 8.5),
        Archetype.CORPORATE_LONGLINER: (16.0, 37.0, 4.0, 8.0, 4.0, 8.0),
        Archetype.MOTHERSHIP: (43.0, 48.0, 1.5, 3.5, 2.0, 4.5),
        Archetype.COAST_GUARD: (14.0, 35.0, 5.0, 11.0, 7.0, 12.0),
        Archetype.SOVIET_TRAWLER: (43.0, 50.0, 4.0, 8.0, 5.0, 10.0),
    }[archetype]


def _make_schedule(archetype: Archetype, rng: random.Random, speed_kn: float) -> tuple[tuple[SchedulePoint, ...], float]:
    """Phase A loop schedules, intentionally bounded to the legacy harbour sheet."""
    rmin, rmax = _radius_band(archetype)[2:4]
    crmin, crmax = _radius_band(archetype)[:2]
    center_radius = rng.uniform(crmin, crmax)
    center_angle = rng.random() * math.tau
    cx, cy = math.cos(center_angle) * center_radius, math.sin(center_angle) * center_radius
    route_radius = rng.uniform(rmin, rmax)
    ellipse = rng.uniform(0.68, 1.22)
    phase = rng.random() * math.tau
    jitter = rng.uniform(-0.08, 0.08)
    coords = []
    for i in range(8):
        theta = phase + math.tau * i / 8.0
        radial = route_radius * (1.0 + jitter * math.sin(3.0 * theta))
        coords.append((cx + math.cos(theta) * radial,
                       cy + math.sin(theta) * radial * ellipse))
    # Legacy chart sheet: +/- 59 NM east/west and +/- 53 NM north/south.
    coords = [(max(-59.0, min(59.0, x)), max(-53.0, min(53.0, y))) for x, y in coords]
    return _schedule_from_coords(coords, archetype, speed_kn)


# Eleven deterministic mothership stations inside the high-seas operating box.
# Catcher boats are distributed around these fixed cluster anchors, making the
# corporate hierarchy spatially visible without giving each vessel expensive AI.
MOTHERSHIP_CLUSTER_CENTERS_NM = (
    (75.0, 105.0), (300.0, 115.0), (525.0, 125.0), (750.0, 135.0), (970.0, 145.0),
    (180.0, 330.0), (405.0, 345.0), (630.0, 360.0), (855.0, 375.0),
    (300.0, 640.0), (730.0, 820.0),
)


def _schedule_from_coords(coords: list[tuple[float, float]], archetype: Archetype,
                           speed_kn: float) -> tuple[tuple[SchedulePoint, ...], float]:
    acts = ACTIVITY_CYCLE[archetype]
    points: list[SchedulePoint] = []
    elapsed = 0.0
    for i, (x, y) in enumerate(coords):
        points.append(SchedulePoint(elapsed, x, y, acts[i % len(acts)]))
        nx, ny = coords[(i + 1) % len(coords)]
        leg = math.hypot(nx - x, ny - y)
        elapsed += max(5.0, leg / max(0.06, speed_kn * SIM_NM_PER_KNOT_SECOND))
    return tuple(points), max(1.0, elapsed)


def _make_phase_b_schedule(archetype: Archetype, index: int, rng: random.Random,
                            speed_kn: float) -> tuple[tuple[SchedulePoint, ...], float]:
    """Generate a bounded Phase B route in high-seas projection coordinates (NM)."""
    min_x, max_x, min_y, max_y = PHASE_B_BOUNDS_NM
    if archetype == Archetype.MOTHERSHIP:
        cx, cy = MOTHERSHIP_CLUSTER_CENTERS_NM[index % len(MOTHERSHIP_CLUSTER_CENTERS_NM)]
        route_radius = rng.uniform(1.5, 7.5)
        ellipse = rng.uniform(0.7, 1.1)
    elif archetype == Archetype.CORPORATE_CATCHER:
        cx, cy = MOTHERSHIP_CLUSTER_CENTERS_NM[index % len(MOTHERSHIP_CLUSTER_CENTERS_NM)]
        cx += rng.uniform(-24.0, 24.0)
        cy += rng.uniform(-24.0, 24.0)
        route_radius = rng.uniform(12.0, 35.0)
        ellipse = rng.uniform(0.65, 1.25)
    elif archetype == Archetype.SOVIET_TRAWLER:
        # Patrols and fishing runs loosely parallel to the 45N treaty boundary.
        cx = rng.uniform(80.0, max_x - 90.0)
        cy = rng.uniform(-32.0, 155.0)
        route_radius = rng.uniform(18.0, 58.0)
        ellipse = rng.uniform(0.45, 0.95)
    elif archetype in (Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET):
        # Independent land-based boats spread along the Hakodate transit corridor
        # and the southern edge of the high-seas grounds.
        cx = rng.uniform(min_x + 55.0, 220.0)
        cy = rng.uniform(min_y + 35.0, 255.0)
        route_radius = rng.uniform(15.0, 62.0)
        ellipse = rng.uniform(0.55, 1.35)
    elif archetype == Archetype.CORPORATE_LONGLINER:
        cx = rng.uniform(50.0, max_x - 80.0)
        cy = rng.uniform(75.0, max_y - 80.0)
        route_radius = rng.uniform(20.0, 58.0)
        ellipse = rng.uniform(0.6, 1.3)
    else:  # Coast Guard patrols the transit corridor and approaches to the fleet box.
        cx = rng.uniform(min_x + 60.0, max_x - 90.0)
        cy = rng.uniform(min_y + 45.0, 520.0)
        route_radius = rng.uniform(25.0, 70.0)
        ellipse = rng.uniform(0.55, 1.25)
    phase = rng.random() * math.tau
    jitter = rng.uniform(-0.07, 0.07)
    coords = []
    for i in range(8):
        theta = phase + math.tau * i / 8.0
        radial = route_radius * (1.0 + jitter * math.sin(3.0 * theta))
        x = cx + math.cos(theta) * radial
        y = cy + math.sin(theta) * radial * ellipse
        coords.append((max(min_x + 2.0, min(max_x - 2.0, x)),
                       max(min_y + 2.0, min(max_y - 2.0, y))))
    return _schedule_from_coords(coords, archetype, speed_kn)


class TrafficWorld:
    """Seeded Phase A or Phase B fleet with a shared index and bounded active LOD."""
    def __init__(self, world_seed: int = 1962, *, active_cap: int = 30,
                 cell_size_nm: float = DEFAULT_CELL_SIZE_NM, phase: str = "A"):
        self.world_seed = int(world_seed)
        self.phase = str(phase).upper()
        if self.phase not in ("A", "B", "C"):
            raise ValueError("traffic phase must be A, B, or C")
        # Phase C currently uses the Phase B fleet/extent until modular east tiles land.
        self.seed_algorithm_version = SEED_ALGORITHM_VERSION
        self.ships: dict[str, AIShip] = {}
        # Contacts are a sparse set, so chart rendering scales with vessels the player
        # knows about rather than scanning the whole coarse fleet every frame.
        self.known_contact_ids: set[str] = set()
        # Runtime ships are authoritative elsewhere (TowEscort, future distress
        # responses) but indexed here so chart/radio queries resolve one identity.
        self.runtime_ship_ids: set[str] = set()
        # A very small bounded set of active rescue contacts; a MAYDAY can be
        # dispatched even before promotion, but nearby rescue vessels get live LOD.
        self.rescue_contact_ids: set[str] = set()
        self.index = SpatialIndex(cell_size_nm=cell_size_nm)
        self.lod = LODManager(active_cap=active_cap)
        self.sim_time_s = 0.0
        self._next_tick_s = 0.0
        self.tick_count = 0
        self.cell_crossings = 0
        if self.phase == "A":
            self.generate_phase_a_fleet()
        else:
            self.generate_phase_b_fleet()
        self.advance(0.0, focus_nm=(0.0, 0.0), force=True)

    def _generate_fleet(self, counts: dict[Archetype, int], *, high_seas: bool) -> None:
        ships: dict[str, AIShip] = {}
        for archetype, count in counts.items():
            names = NAMES_BY_ARCHETYPE[archetype]
            band = _radius_band(archetype)
            for index in range(count):
                vessel_id = stable_vessel_id(self.world_seed, archetype.value, index)
                rng = random.Random(stable_seed(self.world_seed, "traffic", vessel_id))
                name = names[index % len(names)]
                if index >= len(names):
                    name = f"{name} {index + 1}"
                speed_kn = rng.uniform(band[4], band[5])
                schedule, period = (_make_phase_b_schedule(archetype, index, rng, speed_kn)
                                    if high_seas else _make_schedule(archetype, rng, speed_kn))
                personalities = PERSONALITIES_BY_ARCHETYPE[archetype]
                personality = personalities[rng.randrange(len(personalities))]
                radio_fit = "SSB" if archetype in (Archetype.MOTHERSHIP, Archetype.COAST_GUARD) else "DSB"
                ship = AIShip(
                    id=vessel_id, name=name, callsign=name.upper(), archetype=archetype,
                    home_port=("Hakodate" if archetype in (
                        Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET,
                        Archetype.CORPORATE_LONGLINER, Archetype.COAST_GUARD) else
                        ("North Pacific fleet" if archetype in (Archetype.CORPORATE_CATCHER, Archetype.MOTHERSHIP)
                         else "Soviet Far East")),
                    personality=personality, schedule=schedule, period_s=period, speed_kn=speed_kn,
                    radio_fit=radio_fit, radio_range_nm=RADIO_RANGE_NM[radio_fit],
                )
                if high_seas:
                    if archetype == Archetype.MOTHERSHIP:
                        ship.mothership_id = ship.id
                    elif archetype == Archetype.CORPORATE_CATCHER:
                        ship.mothership_id = stable_vessel_id(
                            self.world_seed, Archetype.MOTHERSHIP.value,
                            index % len(MOTHERSHIP_CLUSTER_CENTERS_NM))
                ships[ship.id] = ship
        self.ships = dict(sorted(ships.items()))

    def generate_phase_a_fleet(self) -> None:
        self._generate_fleet(PHASE_A_COUNTS, high_seas=False)

    def generate_phase_b_fleet(self) -> None:
        self._generate_fleet(PHASE_B_COUNTS, high_seas=True)

    @staticmethod
    def _in_salmon_season(month: int, day: int) -> bool:
        return ((int(month) > 5 or (int(month) == 5 and int(day) >= 20))
                and (int(month) < 8 or (int(month) == 8 and int(day) <= 10)))

    def _phase_b_entity_available(self, ship: AIShip, *, in_season: bool, now: float) -> bool:
        if self.phase == "A" or in_season:
            return True
        if (ship.id in self.runtime_ship_ids or ship.activity_override is not None
                or ship.known_to_player or (ship.mayday_sent and not ship.mayday_resolved)):
            return True
        # Corporate fleet lays up off-season; a small deterministic subset remains
        # underway. The full catalogue and route IDs stay resident for save stability.
        slot = stable_seed(self.world_seed, "off-season", ship.id)
        if ship.archetype == Archetype.CORPORATE_CATCHER:
            return slot % 12 == 0
        if ship.archetype == Archetype.MOTHERSHIP:
            return slot % 11 == 0
        if ship.archetype == Archetype.SOVIET_TRAWLER:
            return slot % 2 == 0
        return True

    def advance(self, sim_time_s: float, *, focus_nm: tuple[float, float] = (0.0, 0.0),
                month: int | None = None, day: int | None = None,
                hour: float | None = None, force: bool = False) -> bool:
        """Sample schedules on a fixed interval; handles time skips without catch-up loops."""
        now = max(0.0, float(sim_time_s))
        if not force and now >= self.sim_time_s and now < self._next_tick_s:
            return False
        self.sim_time_s = now
        positions = {}
        for ship_id, ship in self.ships.items():
            if ship_id in self.runtime_ship_ids:
                # Do not overwrite a rescue/tow contact from its schedule. Its
                # specialised controller updates its position, heading and state.
                pos = (float(ship.position_nm[0]), float(ship.position_nm[1]))
                ship.activity = ship.activity_override or ship.activity
                heading = float(ship.heading_rad)
            elif ship.position_override_nm is not None:
                pos = (float(ship.position_override_nm[0]), float(ship.position_override_nm[1]))
                heading = float(ship.heading_rad)
                activity = ship.activity_override or ship.activity
                ship.position_nm = pos
                ship.activity = activity
            elif (ship.activity_override == Activity.DISTRESSED
                  and ship.distress_position_nm is not None):
                # A distressed vessel no longer advances along its ordinary fishing
                # schedule. It remains at the incident position until assisted or abandoned.
                pos = (float(ship.distress_position_nm[0]), float(ship.distress_position_nm[1]))
                heading = float(ship.heading_rad)
                activity = Activity.DISTRESSED
                ship.position_nm = pos
                ship.activity = activity
            else:
                pos, heading, activity = ship.position_at(now)
                ship.position_nm = pos
                ship.heading_rad = heading
                ship.activity = ship.activity_override or activity
            in_salmon_season = (True if month is None or day is None
                                else self._in_salmon_season(month, day))
            # In Phase B, corporate vessels are sparse outside the salmon season.
            # Their stable entities remain in the catalogue, but most are removed
            # from the live spatial/radio index until the fleet deploys again.
            if self.phase != "A" and not self._phase_b_entity_available(
                    ship, in_season=in_salmon_season, now=now):
                self.index.remove(ship.id)
                continue
            if month is not None and day is not None and not in_salmon_season and ship.activity_override is None:
                if ship.archetype == Archetype.CORPORATE_CATCHER:
                    ship.activity = Activity.TRANSIT
                elif ship.archetype == Archetype.MOTHERSHIP:
                    ship.activity = Activity.ANCHORED
            positions[ship.id] = pos
            if self.index.upsert(ship.id, pos):
                self.cell_crossings += 1
        self.lod.assign(positions, (float(focus_nm[0]), float(focus_nm[1])))
        # Time-critical rescue contacts get an explicit LOD promotion override.
        # This may exceed active_cap by the number of concurrent rescue contacts,
        # which is intentional and bounded by the small runtime contact set.
        active_ids = list(self.lod.active_ids)
        active_ids.extend(v for v in sorted(self.runtime_ship_ids)
                          if v in positions and v not in active_ids)
        rescue_ids = [v for v in sorted(self.rescue_contact_ids)
                      if v in positions and v not in active_ids][:MAX_ACTIVE_RESCUE_CONTACTS]
        active_ids.extend(rescue_ids)
        self.lod.active_ids = tuple(active_ids)
        active = set(self.lod.active_ids)
        warm = set(self.lod.warm_ids)
        for ship in self.ships.values():
            ship.lod = "active" if ship.id in active else ("warm" if ship.id in warm else "coarse")
        self._next_tick_s = now + TRAFFIC_TICK_INTERVAL_S
        self.tick_count += 1
        return True

    def observe_nearby(self, focus_nm: tuple[float, float], sim_time_s: float,
                       *, radius_nm: float = VISUAL_SIGHTING_RADIUS_NM) -> list[AIShip]:
        """Update reports for close visual sightings; does not reveal distant true positions."""
        observed = []
        now = float(sim_time_s)
        for hit in self.index.query(focus_nm, radius_nm):
            ship = self.ships[hit.vessel_id]
            # Runtime rescue contacts own their radio-reported plot; a generic
            # visual sighting must not silently replace that captain's report.
            if hit.vessel_id in self.runtime_ship_ids:
                observed.append(ship)
                continue
            if now - ship.last_visual_report_s < REPORT_STALE_AFTER_SIM_SECONDS:
                observed.append(ship)
                continue
            # Small bounded visual plotting error, independent per ship and report window.
            rng = random.Random(stable_seed(self.world_seed, "visual-report", ship.id,
                                            int(now // REPORT_STALE_AFTER_SIM_SECONDS)))
            ship.report_position(now, error_nm=rng.uniform(0.03, 0.18), rng=rng)
            ship.last_visual_report_s = now
            self.known_contact_ids.add(ship.id)
            observed.append(ship)
        return observed

    def nearby(self, focus_nm: tuple[float, float], radius_nm: float) -> list[AIShip]:
        return [self.ships[hit.vessel_id] for hit in self.index.query(focus_nm, radius_nm)
                if hit.vessel_id in self.ships]

    def radio_candidates(self, focus_nm: tuple[float, float]) -> list[AIShip]:
        max_range = max((s.radio_range_nm for s in self.ships.values()), default=0.0)
        return [ship for ship in self.nearby(focus_nm, max_range)
                if math.hypot(ship.position_nm[0] - focus_nm[0], ship.position_nm[1] - focus_nm[1]) <= ship.radio_range_nm]

    def by_id(self, vessel_id: str) -> AIShip | None:
        return self.ships.get(str(vessel_id))

    def register_runtime_ship(self, ship: AIShip) -> AIShip:
        """Register a live rescue/contact entity in the shared world identity map.

        Its owning gameplay system remains authoritative; this world owns the
        common ID, spatial query visibility, LOD override, and chart contact.
        """
        vessel_id = str(ship.id)
        if not vessel_id:
            raise ValueError("runtime vessel requires a stable non-empty ID")
        existing = self.ships.get(vessel_id)
        if existing is not None and vessel_id not in self.runtime_ship_ids:
            raise ValueError("runtime vessel ID collides with scheduled fleet: %s" % vessel_id)
        ship.runtime_kind = ship.runtime_kind if ship.runtime_kind != "scheduled" else "runtime"
        self.ships[vessel_id] = ship
        self.runtime_ship_ids.add(vessel_id)
        self.index.upsert(vessel_id, ship.position_nm)
        if ship.known_to_player or ship.last_reported_position_nm is not None:
            self.known_contact_ids.add(vessel_id)
        if vessel_id not in self.lod.active_ids:
            self.lod.active_ids = tuple(self.lod.active_ids) + (vessel_id,)
        ship.lod = "active"
        return ship

    def sync_runtime_ship(self, vessel_id: str, *, position_nm: tuple[float, float],
                          heading_rad: float, activity: Activity = Activity.TRANSIT,
                          reported_position_nm: tuple[float, float] | None = None,
                          reported_heading_rad: float | None = None,
                          report_time_s: float | None = None,
                          known_to_player: bool = True) -> AIShip | None:
        """Synchronise one externally-controlled entity into the shared index."""
        vessel_id = str(vessel_id)
        if vessel_id not in self.runtime_ship_ids:
            return None
        ship = self.ships.get(vessel_id)
        if ship is None:
            return None
        pos = (float(position_nm[0]), float(position_nm[1]))
        heading = float(heading_rad)
        if not all(math.isfinite(v) for v in (*pos, heading)):
            raise ValueError("runtime vessel position/heading must be finite")
        ship.position_nm = pos
        ship.heading_rad = heading
        ship.activity = Activity(activity)
        ship.known_to_player = bool(known_to_player)
        if reported_position_nm is not None:
            report = (float(reported_position_nm[0]), float(reported_position_nm[1]))
            if not all(math.isfinite(v) for v in report):
                raise ValueError("runtime vessel reported position must be finite")
            ship.last_reported_position_nm = report
            ship.last_reported_heading_rad = heading if reported_heading_rad is None else float(reported_heading_rad)
            ship.last_report_time_s = None if report_time_s is None else float(report_time_s)
        self.index.upsert(vessel_id, pos)
        if ship.known_to_player or ship.last_reported_position_nm is not None:
            self.known_contact_ids.add(vessel_id)
        ship.lod = "active"
        if vessel_id not in self.lod.active_ids:
            self.lod.active_ids = tuple(self.lod.active_ids) + (vessel_id,)
        return ship

    def unregister_runtime_ship(self, vessel_id: str) -> None:
        """Remove an ended runtime contact from queries and current chart contacts."""
        vessel_id = str(vessel_id)
        if vessel_id not in self.runtime_ship_ids:
            return
        self.runtime_ship_ids.discard(vessel_id)
        self.ships.pop(vessel_id, None)
        self.known_contact_ids.discard(vessel_id)
        self.index.remove(vessel_id)
        self.lod.active_ids = tuple(v for v in self.lod.active_ids if v != vessel_id)
        self.lod.warm_ids = tuple(v for v in self.lod.warm_ids if v != vessel_id)
        self.lod.coarse_ids = tuple(v for v in self.lod.coarse_ids if v != vessel_id)

    def promote_rescue_contact(self, vessel_id: str) -> bool:
        """Promote one distress vessel to live LOD without activating the whole fleet.

        Radio delivery does not depend on this method: coarse vessels are still indexed
        and can transmit a MAYDAY. Promotion only grants a bounded active update/render.
        """
        vessel_id = str(vessel_id)
        if vessel_id not in self.ships or vessel_id in self.runtime_ship_ids:
            return False
        if vessel_id not in self.rescue_contact_ids:
            if len(self.rescue_contact_ids) >= MAX_ACTIVE_RESCUE_CONTACTS:
                return False
            self.rescue_contact_ids.add(vessel_id)
        active = list(self.lod.active_ids)
        if vessel_id not in active:
            active.append(vessel_id)
        self.lod.active_ids = tuple(active)
        self.ships[vessel_id].lod = "active"
        return True

    def release_rescue_contact(self, vessel_id: str) -> None:
        """Release a rescue-only LOD override; normal range-based LOD resumes next tick."""
        self.rescue_contact_ids.discard(str(vessel_id))

    def mark_known(self, vessel_id: str) -> None:
        """Mark a stable vessel identity as chart-visible after sighting/radio contact."""
        ship = self.ships.get(str(vessel_id))
        if ship is not None and (ship.known_to_player or ship.last_reported_position_nm is not None):
            self.known_contact_ids.add(ship.id)

    def known_contacts(self) -> tuple[AIShip, ...]:
        """Return sorted known contacts for chart rendering without scanning all fleet ships."""
        return tuple(self.ships[vessel_id] for vessel_id in sorted(self.known_contact_ids)
                     if vessel_id in self.ships)

    def snapshot_contacts(self) -> dict:
        """Versioned compact contact delta; full game save integration lands in M10."""
        contacts = {}
        for ship in self.ships.values():
            if (not ship.known_to_player and ship.contact_count == 0 and ship.contact_attempts == 0
                    and not ship.mayday_sent and ship.activity_override is None):
                continue
            contacts[ship.id] = {
                "trust": float(ship.trust),
                "contact_count": int(ship.contact_count),
                "contact_attempts": int(ship.contact_attempts),
                "last_contact_sim_time": float(ship.last_contact_sim_time),
                "known_to_player": bool(ship.known_to_player),
                "last_reported_position_nm": list(ship.last_reported_position_nm) if ship.last_reported_position_nm is not None else None,
                "last_reported_heading_rad": float(ship.last_reported_heading_rad),
                "heading_rad": float(ship.heading_rad),
                "last_report_time_s": ship.last_report_time_s,
                "mayday_sent": bool(ship.mayday_sent),
                "mayday_resolved": bool(ship.mayday_resolved),
                "mayday_player_heard": bool(ship.mayday_player_heard),
                "distress_started_s": ship.distress_started_s,
                "distress_kind": ship.distress_kind,
                "distress_origin_activity": ship.distress_origin_activity.value if ship.distress_origin_activity else None,
                "distress_decision": ship.distress_decision,
                "distress_position_nm": list(ship.distress_position_nm) if ship.distress_position_nm is not None else None,
                "distress_assistance_status": str(ship.distress_assistance_status),
                "distress_outcome": ship.distress_outcome,
                "position_override_nm": list(ship.position_override_nm) if ship.position_override_nm is not None else None,
                "is_rival": bool(ship.is_rival),
                "activity_override": ship.activity_override.value if ship.activity_override else None,
            }
        return {"schema_version": 1, "world_seed": self.world_seed, "phase": self.phase,
                "seed_algorithm_version": self.seed_algorithm_version, "contacts": contacts}

    def restore_contacts(self, snapshot: dict) -> None:
        """Restore contact deltas onto regenerated stable identities, ignoring unknown IDs safely."""
        if not isinstance(snapshot, dict) or int(snapshot.get("schema_version", 0)) != 1:
            raise ValueError("unsupported traffic contact snapshot schema")
        if int(snapshot.get("world_seed", self.world_seed)) != self.world_seed:
            raise ValueError("traffic snapshot world seed does not match")
        snapshot_phase = str(snapshot.get("phase", "A")).upper()
        if snapshot_phase != self.phase:
            raise ValueError("traffic snapshot phase does not match")
        contacts = snapshot.get("contacts", {})
        if not isinstance(contacts, dict):
            raise ValueError("traffic contacts must be a mapping")
        for vessel_id, state in contacts.items():
            ship = self.ships.get(str(vessel_id))
            if ship is None or not isinstance(state, dict):
                continue
            ship.trust = max(-1.0, min(1.0, float(state.get("trust", ship.trust))))
            ship.contact_count = max(0, int(state.get("contact_count", ship.contact_count)))
            ship.contact_attempts = max(0, int(state.get("contact_attempts", ship.contact_attempts)))
            ship.last_contact_sim_time = float(state.get("last_contact_sim_time", ship.last_contact_sim_time))
            ship.known_to_player = bool(state.get("known_to_player", ship.known_to_player))
            pos = state.get("last_reported_position_nm")
            if pos is not None and isinstance(pos, (tuple, list)) and len(pos) == 2 and all(math.isfinite(float(v)) for v in pos):
                ship.last_reported_position_nm = (float(pos[0]), float(pos[1]))
            if ship.known_to_player or ship.last_reported_position_nm is not None:
                self.known_contact_ids.add(ship.id)
            ship.last_reported_heading_rad = float(state.get("last_reported_heading_rad", ship.last_reported_heading_rad))
            # Older contact snapshots omit physical heading; accept them, while newly
            # saved autonomous/tow responses preserve their current helm orientation.
            saved_heading = float(state.get("heading_rad", ship.heading_rad))
            if not math.isfinite(saved_heading):
                raise ValueError("invalid vessel heading in traffic snapshot")
            ship.heading_rad = saved_heading
            report_time = state.get("last_report_time_s")
            ship.last_report_time_s = None if report_time is None else float(report_time)
            ship.mayday_sent = bool(state.get("mayday_sent", ship.mayday_sent))
            ship.mayday_resolved = bool(state.get("mayday_resolved", ship.mayday_resolved))
            ship.mayday_player_heard = bool(state.get("mayday_player_heard", ship.mayday_player_heard))
            started = state.get("distress_started_s", ship.distress_started_s)
            ship.distress_started_s = None if started is None else max(0.0, float(started))
            kind = state.get("distress_kind", ship.distress_kind)
            ship.distress_kind = None if kind is None else str(kind)
            origin = state.get("distress_origin_activity")
            ship.distress_origin_activity = Activity(origin) if origin else ship.distress_origin_activity
            decision = state.get("distress_decision", ship.distress_decision)
            ship.distress_decision = None if decision is None else str(decision)
            distress_position = state.get("distress_position_nm")
            if distress_position is not None:
                if (not isinstance(distress_position, (tuple, list)) or len(distress_position) != 2
                        or not all(math.isfinite(float(v)) for v in distress_position)):
                    raise ValueError("invalid distress position in traffic snapshot")
                ship.distress_position_nm = (float(distress_position[0]), float(distress_position[1]))
            ship.distress_assistance_status = str(state.get("distress_assistance_status", ship.distress_assistance_status))
            if ship.distress_assistance_status not in ("none", "ignored", "awaiting_dispatch", "en_route", "on_scene", "completed", "cancelled"):
                raise ValueError("invalid distress assistance status")
            outcome = state.get("distress_outcome", ship.distress_outcome)
            ship.distress_outcome = None if outcome is None else str(outcome)
            position_override = state.get("position_override_nm")
            if position_override is not None:
                if (not isinstance(position_override, (tuple, list)) or len(position_override) != 2
                        or not all(math.isfinite(float(v)) for v in position_override)):
                    raise ValueError("invalid position override in traffic snapshot")
                ship.position_override_nm = (float(position_override[0]), float(position_override[1]))
            ship.is_rival = bool(state.get("is_rival", ship.is_rival))
            override = state.get("activity_override")
            ship.activity_override = Activity(override) if override else None
            if ship.position_override_nm is not None:
                ship.position_nm = ship.position_override_nm
                self.index.upsert(ship.id, ship.position_nm)
            elif ship.activity_override == Activity.DISTRESSED and ship.distress_position_nm is not None:
                ship.position_nm = ship.distress_position_nm
                self.index.upsert(ship.id, ship.position_nm)
            if ship.mayday_player_heard:
                self.known_contact_ids.add(ship.id)
                if ship.mayday_sent and not ship.mayday_resolved:
                    self.promote_rescue_contact(ship.id)

    def diagnostics(self, focus_nm: tuple[float, float] = (0.0, 0.0)) -> dict:
        return {
            "world_seed": self.world_seed,
            "seed_algorithm_version": self.seed_algorithm_version,
            "phase": self.phase,
            "ship_count": len(self.ships),
            "phase_a_ship_count": len(self.ships) if self.phase == "A" else 0,
            "phase_b_ship_count": len(self.ships) if self.phase == "B" else 0,
            "phase_a_reference_fleet_count": PHASE_A_FLEET_TOTAL,
            "source_plan_full_fleet_count": SOURCE_FLEET_TOTAL,
            "index_cells": len(self.index.cells),
            "active_count": len(self.lod.active_ids),
            "warm_count": len(self.lod.warm_ids),
            "coarse_count": len(self.lod.coarse_ids),
            "tick_count": self.tick_count,
            "cell_crossings": self.cell_crossings,
        }
