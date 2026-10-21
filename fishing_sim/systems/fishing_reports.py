"""Unconfirmed fishing-spot reports for the chart (V13V1-12).

Reports are deliberately not live-hotspot markers. Some are grounded in a real
concentration but have noisy positions/species calls; others are false leads.
The internal ``grounded`` bit exists for simulation/testing only and must never
be exposed by the chart UI or crew log.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from fishing_sim.systems.hotspots import HOTSPOT_SPECIES
from fishing_sim.systems.navigation_chart import CHART_BOUNDS

MAX_CHART_REPORTS = 5
DEFAULT_GROUNDED_CHANCE = 0.64
REPORT_LIFETIME_RANGE = (1200.0, 2700.0)
SOURCE_CONFIDENCE = {
    "TENYO MARU": (0.58, 0.90),
    "AOBA MARU": (0.52, 0.86),
    "COAST STATION": (0.55, 0.82),
    "HARBOUR TALK": (0.30, 0.76),
}
SOURCE_TAGS = {
    "TENYO MARU": "TENYO",
    "AOBA MARU": "AOBA",
    "COAST STATION": "COAST",
    "HARBOUR TALK": "TALK",
}
SPECIES_TAGS = {
    "albacore": "ALB?",
    "yellowfin": "YEL?",
    "bigeye": "BIG?",
    "swordfish": "SWD?",
    "mixed": "MIX?",
}


def _xy(point):
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def _inside_chart(x, y):
    xmin, ymin, xmax, ymax = CHART_BOUNDS
    return xmin <= x <= xmax and ymin <= y <= ymax


@dataclass
class FishingSpotReport:
    """A charted lead, not confirmation that fish occupy the location."""
    report_id: int
    x: float                 # chart design units, with harbour at (0, 0)
    y: float
    species: str             # reported species, which may itself be wrong
    source: str
    confidence: float        # source credibility, not ground truth probability
    accuracy_radius: float   # reported search-area radius in chart design units
    lifetime: float
    grounded: bool = False   # private simulation/testing only; never display it
    age: float = 0.0

    def update(self, dt):
        self.age += max(0.0, float(dt))
        return self.age < self.lifetime

    @property
    def expired(self):
        return self.age >= self.lifetime

    @property
    def age_minutes(self):
        return max(0, int(self.age // 60.0))

    @property
    def source_tag(self):
        return SOURCE_TAGS.get(self.source, "RADIO")

    @property
    def species_tag(self):
        return SPECIES_TAGS.get(self.species, "FISH?")

    @property
    def age_band(self):
        fraction = self.age / max(1.0, self.lifetime)
        if fraction < 0.30:
            return "FRESH"
        if fraction < 0.70:
            return "AGING"
        return "STALE"

    @property
    def short_age(self):
        if self.age < 60:
            return "NOW"
        minutes = self.age_minutes
        if minutes < 60:
            return "%02dm" % minutes
        return "%dh" % min(99, minutes // 60)


def create_fishing_report(rng, hotspots, scale, is_water, report_id,
                          grounded_chance=DEFAULT_GROUNDED_CHANCE):
    """Create one unconfirmed lead, mixing noisy real contacts and false rumours.

    ``is_water`` accepts *world* coordinates, while report coordinates are stored
    in chart design units. It is used to avoid plotting reports on land. The
    grounded chance is exposed for deterministic headless tests.
    """
    scale = max(0.001, float(scale))
    chance = max(0.0, min(1.0, float(grounded_chance)))
    chartable = []
    for spot in hotspots:
        if float(getattr(spot, "strength_now", 0.0)) <= 0.05:
            continue
        sx, sy = _xy(spot.pos)
        sx, sy = sx / scale, sy / scale
        if _inside_chart(sx, sy):
            chartable.append((spot, sx, sy))

    source = rng.choice(tuple(SOURCE_CONFIDENCE))
    confidence = rng.uniform(*SOURCE_CONFIDENCE[source])
    accuracy_radius = rng.uniform(250.0, 850.0)
    lifetime = rng.uniform(*REPORT_LIFETIME_RANGE)

    grounded = bool(chartable) and rng.random() < chance
    if grounded:
        # Bias toward stronger reports but preserve uncertainty in the position.
        spot, sx, sy = rng.choice(chartable)
        for _ in range(16):
            x = sx + rng.gauss(0.0, accuracy_radius * 0.42)
            y = sy + rng.gauss(0.0, accuracy_radius * 0.42)
            if _inside_chart(x, y) and (is_water is None or is_water(x * scale, y * scale)):
                break
        else:
            grounded = False

    if grounded:
        # Vessel species calls are useful but not infallible, even when the area is real.
        actual_species = str(getattr(spot, "species", "mixed"))
        species = actual_species if rng.random() < 0.78 else rng.choice(HOTSPOT_SPECIES)
    else:
        # A false lead should be recognisably somewhere at sea, and usually away
        # from current schools, without labelling it as false to the player.
        candidate = None
        for _ in range(60):
            angle = rng.uniform(0.0, math.tau)
            distance = rng.uniform(2200.0, 6200.0)
            x, y = math.cos(angle) * distance, math.sin(angle) * distance
            if not _inside_chart(x, y):
                continue
            if is_water is not None and not is_water(x * scale, y * scale):
                continue
            near_live_school = False
            for hot, hx, hy in chartable:
                if math.hypot(x - hx, y - hy) < max(1100.0, float(getattr(hot, "radius", 1600.0)) / scale * 0.75):
                    near_live_school = True
                    break
            if not near_live_school:
                candidate = (x, y)
                break
        if candidate is None:
            # Safe fallback: still a rumour rather than pointing at a known school.
            for _ in range(30):
                angle = rng.uniform(0.0, math.tau)
                distance = rng.uniform(2600.0, 6000.0)
                x, y = math.cos(angle) * distance, math.sin(angle) * distance
                if _inside_chart(x, y) and (is_water is None or is_water(x * scale, y * scale)):
                    candidate = (x, y)
                    break
        if candidate is None:
            return None
        x, y = candidate
        species = rng.choice(HOTSPOT_SPECIES)

    return FishingSpotReport(
        report_id=int(report_id), x=float(x), y=float(y), species=species,
        source=source, confidence=max(0.0, min(1.0, confidence)),
        accuracy_radius=accuracy_radius, lifetime=lifetime, grounded=grounded,
    )


def report_map_color(confidence, age_fraction=0.0):
    """Neutral chart ink by source credibility/freshness, never by truth status."""
    confidence = max(0.0, min(1.0, float(confidence)))
    if confidence >= 0.75:
        color = (65, 104, 84)
    elif confidence >= 0.50:
        color = (150, 111, 42)
    else:
        color = (142, 75, 59)
    fade = max(0.48, min(1.0, 1.0 - max(0.0, min(1.0, float(age_fraction))) * 0.52))
    return tuple(int(channel * fade) for channel in color)
