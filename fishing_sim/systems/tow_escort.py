"""State for the Coast Guard vessel escorting a disabled fishing boat.

The escort is intentionally a separate entity from the player's vessel.  It
stores its own crew and position reports; the chart draws the last reported
position rather than exposing its live position directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import random

CHART_UNITS_PER_NAUTICAL_MILE = 185.2
SIM_SECONDS_PER_GAME_DAY = 600.0
CHECKIN_INTERVAL = SIM_SECONDS_PER_GAME_DAY * 30.0 / (24.0 * 60.0)  # 12.5 sim sec
STALE_TOW_REPORT = SIM_SECONDS_PER_GAME_DAY * 45.0 / (24.0 * 60.0)  # 18.75 sim sec
DEPART_DELAY = SIM_SECONDS_PER_GAME_DAY * 30.0 / (24.0 * 60.0)
LINE_RISK_SEA_STATE = 0.72  # game's sea_state is normalized 0..1
TOW_ESCORT_SEPARATION_NM = 2.0  # tug centre ahead of disabled vessel while towing
TOW_ESCORT_HANDOVER_SECONDS = 3.2  # time to come alongside and turn for the homeward tow

COAST_GUARD_CAPTAINS = ("Captain Sato", "Captain Mori", "Captain Tanabe", "Captain Kuroda")
COAST_GUARD_CALLSIGNS = ("KIKU MARU", "SHIRASE", "HAKUTO", "KAIYO MARU")
COAST_GUARD_CAPTAIN_BY_CALLSIGN = {
    "KIKU MARU": "Captain Sato",
    "SHIRASE": "Captain Mori",
    "HAKUTO": "Captain Tanabe",
    "KAIYO MARU": "Captain Kuroda",
}
TOW_ESCORT_SCHEMA_VERSION = 1
COAST_GUARD_CREWS = {
    "KIKU MARU": (
        ("Petty Officer Nakamura", "radio operator"),
        ("Chief Engineer Fujita", "engineer"),
        ("Able Seaman Arai", "deck hand"),
        ("Able Seaman Kobayashi", "line handler"),
    ),
    "SHIRASE": (
        ("Petty Officer Endo", "radio operator"),
        ("Chief Engineer Watanabe", "engineer"),
        ("Able Seaman Okada", "deck hand"),
        ("Able Seaman Hasegawa", "line handler"),
    ),
    "HAKUTO": (
        ("Petty Officer Ishikawa", "radio operator"),
        ("Chief Engineer Matsuda", "engineer"),
        ("Able Seaman Ono", "deck hand"),
        ("Able Seaman Hayashi", "line handler"),
    ),
    "KAIYO MARU": (
        ("Petty Officer Shimizu", "radio operator"),
        ("Chief Engineer Kondo", "engineer"),
        ("Able Seaman Ueda", "deck hand"),
        ("Able Seaman Ito", "line handler"),
    ),
}


@dataclass
class TowCrewMember:
    name: str
    duty: str


@dataclass
class TowEscort:
    callsign: str
    captain_name: str
    personality: str
    skill: float
    crew: list[TowCrewMember]
    true_position: tuple[float, float]
    reported_position: tuple[float, float]
    heading: float = 0.0
    state: str = "EN_ROUTE"
    elapsed: float = 0.0
    since_checkin: float = 0.0
    unscheduled_elapsed: float = 0.0
    unscheduled_next: float = 65.0
    last_report_elapsed: float = 0.0
    enroute_duration: float = 20.0
    enroute_elapsed: float = 0.0
    handover_elapsed: float = 0.0
    missed_checkins: int = 0
    player_silent_intervals: int = 0
    fee_owed: int = 0
    fuel: float = 1.0
    patience: float = 1.0
    line_at_risk: bool = False
    warned_line_risk: bool = False
    departed: bool = False
    depart_elapsed: float = 0.0
    question_index: int = 0
    pending_topics: list[str] = field(default_factory=list)
    # Shared identity used by the world traffic index, chart and ship-radio UI.
    vessel_id: str = ""

    @classmethod
    def coast_guard(cls, position: tuple[float, float], *, enroute_duration: float = 20.0,
                    rng=None) -> "TowEscort":
        rng = rng or random
        callsign = rng.choice(COAST_GUARD_CALLSIGNS)
        # Callsign and captain identify a specific launch consistently between
        # tow events; personality remains an encounter-level variation.
        captain = COAST_GUARD_CAPTAIN_BY_CALLSIGN[callsign]
        personality = rng.choices(("professional", "terse", "chatty", "worried"),
                                  weights=(0.55, 0.20, 0.15, 0.10), k=1)[0]
        crew = [TowCrewMember(name, duty) for name, duty in COAST_GUARD_CREWS[callsign]]
        point = (float(position[0]), float(position[1]))
        vessel_id = "coast_guard_launch:" + callsign.lower().replace(" ", "_")
        escort = cls(callsign, captain, personality, rng.uniform(0.62, 0.96), crew,
                     point, point, enroute_duration=max(0.1, float(enroute_duration)),
                     vessel_id=vessel_id)
        escort.refresh_report(point, rng=rng, initial=True)
        return escort

    @property
    def world_position_nm(self) -> tuple[float, float]:
        """Physical position in the shared world's east/north nautical-mile frame."""
        return (float(self.true_position[0]) / CHART_UNITS_PER_NAUTICAL_MILE,
                -float(self.true_position[1]) / CHART_UNITS_PER_NAUTICAL_MILE)

    @property
    def world_reported_position_nm(self) -> tuple[float, float]:
        """Last radio plot transformed to the shared traffic coordinate frame."""
        return (float(self.reported_position[0]) / CHART_UNITS_PER_NAUTICAL_MILE,
                -float(self.reported_position[1]) / CHART_UNITS_PER_NAUTICAL_MILE)

    @property
    def world_heading_rad(self) -> float:
        # Heading is already in the renderer's screen-angle convention (y down).
        return float(self.heading)

    @property
    def marker_stale(self) -> bool:
        return max(0.0, self.elapsed - self.last_report_elapsed) >= STALE_TOW_REPORT

    @property
    def report_age_game_minutes(self) -> int:
        return int(max(0.0, self.elapsed - self.last_report_elapsed) * 2.4)


    def snapshot(self) -> dict:
        """Return a versioned JSON-safe mid-en-route/mid-tow state snapshot."""
        state = {
            "schema_version": TOW_ESCORT_SCHEMA_VERSION,
            "vessel_id": self.vessel_id or ("coast_guard_launch:" + self.callsign.lower().replace(" ", "_")),
            "callsign": str(self.callsign),
            "captain_name": str(self.captain_name),
            "personality": str(self.personality),
            "skill": float(self.skill),
            "crew": [{"name": member.name, "duty": member.duty} for member in self.crew],
            "true_position": [float(v) for v in self.true_position],
            "reported_position": [float(v) for v in self.reported_position],
            "heading": float(self.heading), "state": str(self.state),
        }
        for name in (
            "elapsed", "since_checkin", "unscheduled_elapsed", "unscheduled_next",
            "last_report_elapsed", "enroute_duration", "enroute_elapsed", "handover_elapsed",
            "missed_checkins", "player_silent_intervals", "fee_owed", "fuel", "patience",
            "line_at_risk", "warned_line_risk", "departed", "depart_elapsed", "question_index",
            "pending_topics",
        ):
            value = getattr(self, name)
            if name == "pending_topics":
                state[name] = [str(v) for v in value]
            elif name in ("line_at_risk", "warned_line_risk", "departed"):
                state[name] = bool(value)
            elif name in ("missed_checkins", "player_silent_intervals", "fee_owed", "question_index"):
                state[name] = int(value)
            else:
                state[name] = float(value)
        return state

    @classmethod
    def from_snapshot(cls, payload: dict) -> "TowEscort":
        """Restore and validate a saved escort without relying on Python pickle."""
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != TOW_ESCORT_SCHEMA_VERSION:
            raise ValueError("unsupported tow escort snapshot schema")
        state = str(payload.get("state", ""))
        if state not in {"EN_ROUTE", "ALONGSIDE", "UNDER_TOW", "ARRIVED"}:
            raise ValueError("invalid tow escort state")
        def point(name):
            raw = payload.get(name)
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise ValueError("tow escort %s must have two coordinates" % name)
            values = (float(raw[0]), float(raw[1]))
            if not all(math.isfinite(v) for v in values):
                raise ValueError("tow escort %s must be finite" % name)
            return values
        crew_raw = payload.get("crew", [])
        if not isinstance(crew_raw, list) or len(crew_raw) > 32:
            raise ValueError("invalid tow escort crew roster")
        crew = []
        for item in crew_raw:
            if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                raise ValueError("invalid tow escort crew member")
            crew.append(TowCrewMember(str(item["name"]), str(item.get("duty", "crew"))))
        callsign = str(payload.get("callsign", "")).strip()
        captain = str(payload.get("captain_name", "")).strip()
        personality = str(payload.get("personality", "professional"))
        if not callsign or not captain or personality not in ("professional", "terse", "chatty", "worried"):
            raise ValueError("invalid tow escort identity")
        expected_vessel_id = "coast_guard_launch:" + callsign.lower().replace(" ", "_")
        payload_vessel_id = str(payload.get("vessel_id", "")).strip()
        if payload_vessel_id and payload_vessel_id != expected_vessel_id:
            raise ValueError("tow escort vessel_id does not match its callsign")
        obj = cls(
            callsign=callsign, captain_name=captain, personality=personality,
            skill=float(payload.get("skill", 0.7)), crew=crew,
            true_position=point("true_position"), reported_position=point("reported_position"),
            heading=float(payload.get("heading", 0.0)), state=state,
            elapsed=float(payload.get("elapsed", 0.0)),
            since_checkin=float(payload.get("since_checkin", 0.0)),
            unscheduled_elapsed=float(payload.get("unscheduled_elapsed", 0.0)),
            unscheduled_next=float(payload.get("unscheduled_next", 65.0)),
            last_report_elapsed=float(payload.get("last_report_elapsed", 0.0)),
            enroute_duration=float(payload.get("enroute_duration", 20.0)),
            enroute_elapsed=float(payload.get("enroute_elapsed", 0.0)),
            handover_elapsed=float(payload.get("handover_elapsed", 0.0)),
            missed_checkins=max(0, int(payload.get("missed_checkins", 0))),
            player_silent_intervals=max(0, int(payload.get("player_silent_intervals", 0))),
            fee_owed=max(0, int(payload.get("fee_owed", 0))),
            fuel=max(0.0, min(1.0, float(payload.get("fuel", 1.0)))),
            patience=max(0.0, min(1.0, float(payload.get("patience", 1.0)))),
            line_at_risk=bool(payload.get("line_at_risk", False)),
            warned_line_risk=bool(payload.get("warned_line_risk", False)),
            departed=bool(payload.get("departed", False)),
            depart_elapsed=max(0.0, float(payload.get("depart_elapsed", 0.0))),
            question_index=max(0, int(payload.get("question_index", 0))),
            pending_topics=[str(v) for v in payload.get("pending_topics", [])],
            vessel_id=payload_vessel_id or expected_vessel_id,
        )
        numeric = (obj.skill, obj.heading, obj.elapsed, obj.since_checkin, obj.unscheduled_elapsed,
                   obj.unscheduled_next, obj.last_report_elapsed, obj.enroute_duration,
                   obj.enroute_elapsed, obj.handover_elapsed, obj.depart_elapsed)
        if not all(math.isfinite(v) for v in numeric) or not (0.0 <= obj.skill <= 1.0) or obj.enroute_duration <= 0:
            raise ValueError("invalid tow escort timing or skill value")
        return obj

    def dumps(self) -> str:
        return json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def loads(cls, payload: str | bytes) -> "TowEscort":
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("invalid tow escort snapshot encoding") from exc
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("invalid tow escort snapshot JSON") from exc
        return cls.from_snapshot(data)

    def refresh_report(self, true_chart_position: tuple[float, float], *, rng=None,
                       initial: bool = False) -> None:
        """Store a chart report with skill-scaled 1–3 nm plot error (initial can be exact)."""
        rng = rng or random
        tx, ty = float(true_chart_position[0]), float(true_chart_position[1])
        if initial:
            self.reported_position = (tx, ty)
        else:
            error_nm = rng.uniform(1.0, 3.0) * (1.0 - self.skill * 0.65)
            angle = rng.uniform(0.0, math.tau)
            self.reported_position = (tx + math.cos(angle) * error_nm * CHART_UNITS_PER_NAUTICAL_MILE,
                                      ty + math.sin(angle) * error_nm * CHART_UNITS_PER_NAUTICAL_MILE)
        self.last_report_elapsed = self.elapsed
        self.missed_checkins = 0


def tow_intercept_position(harbour: tuple[float, float], ship: tuple[float, float],
                           separation_nm: float = TOW_ESCORT_SEPARATION_NM) -> tuple[float, float]:
    """Return an intercept between harbour and ship, leaving room for the tug ahead."""
    hx, hy = float(harbour[0]), float(harbour[1])
    sx, sy = float(ship[0]), float(ship[1])
    dx, dy = sx - hx, sy - hy
    distance = math.hypot(dx, dy)
    if distance <= 1e-6:
        return sx, sy
    separation = min(max(0.0, float(separation_nm)) * CHART_UNITS_PER_NAUTICAL_MILE,
                     distance * 0.82)
    return (sx - dx / distance * separation,
            sy - dy / distance * separation)


def lerp_chart_position(start: tuple[float, float], target: tuple[float, float],
                         progress: float) -> tuple[float, float]:
    """Interpolate a visible vessel position along the harbour-to-intercept leg."""
    t = max(0.0, min(1.0, float(progress)))
    return (float(start[0]) + (float(target[0]) - float(start[0])) * t,
            float(start[1]) + (float(target[1]) - float(start[1])) * t)


def format_chart_position(position: tuple[float, float], *, origin=(0.0, 0.0)) -> str:
    """Format a chart coordinate as a simple bearing and range from harbour."""
    dx = float(position[0]) - float(origin[0])
    dy = float(position[1]) - float(origin[1])
    bearing = int(round(math.degrees(math.atan2(dx, dy)) % 360))
    distance_nm = math.hypot(dx, dy) / CHART_UNITS_PER_NAUTICAL_MILE
    return "%03d° / %.1f nm from harbour" % (bearing, distance_nm)


def dashed_segments(start: tuple[int, int], end: tuple[int, int], dash: int = 8,
                    gap: int = 5) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Return pixel segments for a dashed chart towline, independent of Pygame."""
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length <= 0.5:
        return []
    ux, uy = dx / length, dy / length
    chunks = []
    cursor = 0.0
    while cursor < length:
        end_cursor = min(length, cursor + max(1.0, dash))
        chunks.append(((int(round(x0 + ux * cursor)), int(round(y0 + uy * cursor))),
                       (int(round(x0 + ux * end_cursor)), int(round(y0 + uy * end_cursor)))))
        cursor = end_cursor + max(1.0, gap)
    return chunks
