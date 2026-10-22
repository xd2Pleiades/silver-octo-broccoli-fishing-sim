"""Physical player-vessel assistance missions for received AI MAYDAY calls.

The player navigates to the distress vessel's *reported* position. The manager
uses the frozen target's physical position only to validate a close rendezvous;
that true position is never returned in status text or mission snapshots. One
mission is active at a time, and all mission state is JSON-safe for career saves.
"""
from __future__ import annotations

import math
from typing import Any

RESCUE_MISSION_SCHEMA_VERSION = 1
RESCUE_ON_SCENE_RADIUS_NM = 4.4
RESCUE_WORK_DURATION_S = 12.0
MAX_MISSION_ID_LENGTH = 220

_OUTCOMES = {
    "taking_water": ("water ingress contained; vessel holding station", "PUMPS AND PATCHING"),
    "engine_failure": ("engine inspection underway; vessel secured", "ENGINE ASSISTANCE"),
    "injury": ("casualty stabilized; vessel holding station", "MEDICAL ASSISTANCE"),
    "gear_entanglement": ("propeller fouling cleared; vessel holding station", "GEAR CLEARANCE"),
}
_ACTIVE_STATES = {"en_route", "on_scene"}
_TERMINAL_STATES = {"completed", "cancelled", "failed"}


def _finite_pair(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("%s must be a coordinate pair" % field)
    pair = (float(value[0]), float(value[1]))
    if not all(math.isfinite(v) for v in pair):
        raise ValueError("%s must contain finite coordinates" % field)
    return pair


def _distance_nm(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


class PlayerRescueMissionManager:
    """Single-mission rescue controller with strict snapshot validation."""

    def __init__(self) -> None:
        self.mission: dict[str, Any] | None = None
        self.completed_count = 0
        self.failed_count = 0

    @property
    def has_active_mission(self) -> bool:
        return bool(self.mission and self.mission.get("state") in _ACTIVE_STATES)

    def dispatch(self, ship, sim_time_s: float, *, reported_position_nm=None,
                 navigation_backup: dict | None = None,
                 route_target_world: tuple[float, float] | None = None) -> dict:
        """Accept one already-radio-acknowledged MAYDAY and create an en-route mission."""
        if self.has_active_mission:
            raise ValueError("another physical rescue mission is already active")
        now = float(sim_time_s)
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("rescue mission time must be finite and nonnegative")
        if not bool(getattr(ship, "mayday_sent", False)) or not bool(getattr(ship, "mayday_player_heard", False)):
            raise ValueError("rescue mission requires a MAYDAY heard by the player")
        if getattr(ship, "distress_decision", None) != "assist":
            raise ValueError("rescue mission requires an ASSIST decision")
        report = reported_position_nm if reported_position_nm is not None else getattr(ship, "last_reported_position_nm", None)
        report = _finite_pair(report, "reported distress position")
        if navigation_backup is not None and not isinstance(navigation_backup, dict):
            raise ValueError("navigation backup must be a mapping")
        route_target = _finite_pair(route_target_world, "route target") if route_target_world is not None else None
        mission_id = "player-rescue:%s:%d" % (str(ship.id), round(now * 1000.0))
        if len(mission_id) > MAX_MISSION_ID_LENGTH:
            raise ValueError("rescue mission identity is too long")
        self.mission = {
            "schema_version": RESCUE_MISSION_SCHEMA_VERSION,
            "mission_id": mission_id,
            "target_vessel_id": str(ship.id),
            "target_callsign": str(ship.callsign),
            "distress_kind": str(getattr(ship, "distress_kind", None) or "taking_water"),
            "reported_position_nm": list(report),
            "started_s": now,
            "state": "en_route",
            "on_scene_started_s": None,
            "completed_s": None,
            "last_distance_nm": None,
            "navigation_backup": dict(navigation_backup or {}),
            "route_target_world": list(route_target) if route_target is not None else None,
            "course_overridden": False,
            "outcome": None,
        }
        ship.distress_assistance_status = "en_route"
        ship.distress_outcome = None
        return dict(self.mission)

    def mark_course_overridden(self) -> None:
        if self.mission and self.mission.get("state") == "en_route":
            self.mission["course_overridden"] = True

    def cancel(self, traffic, sim_time_s: float, reason: str = "player_cancelled") -> dict | None:
        if not self.has_active_mission or self.mission is None:
            return None
        mission = self.mission
        ship = traffic.by_id(mission["target_vessel_id"])
        mission["state"] = "cancelled"
        mission["completed_s"] = max(0.0, float(sim_time_s))
        mission["outcome"] = str(reason)
        if ship is not None:
            ship.distress_assistance_status = "cancelled"
        self.failed_count += 1
        return {"type": "cancelled", "mission_id": mission["mission_id"],
                "target_vessel_id": mission["target_vessel_id"], "callsign": mission["target_callsign"],
                "reason": str(reason)}

    def update(self, sim_time_s: float, player_position_nm: tuple[float, float], traffic) -> dict | None:
        """Advance en-route/on-scene logic; return at most one transition event."""
        if not self.has_active_mission or self.mission is None:
            return None
        now = float(sim_time_s)
        player = _finite_pair(player_position_nm, "player position")
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("rescue mission update time must be finite and nonnegative")
        mission = self.mission
        ship = traffic.by_id(mission["target_vessel_id"])
        if ship is None:
            mission["state"] = "failed"
            mission["completed_s"] = now
            mission["outcome"] = "target_contact_lost"
            self.failed_count += 1
            return {"type": "failed", "mission_id": mission["mission_id"],
                    "target_vessel_id": mission["target_vessel_id"],
                    "callsign": mission["target_callsign"], "reason": "target_contact_lost"}
        physical_pos = (float(ship.position_nm[0]), float(ship.position_nm[1]))
        distance = _distance_nm(player, physical_pos)
        mission["last_distance_nm"] = distance
        if mission["state"] == "en_route":
            if distance <= RESCUE_ON_SCENE_RADIUS_NM:
                mission["state"] = "on_scene"
                mission["on_scene_started_s"] = now
                ship.distress_assistance_status = "on_scene"
                return {"type": "on_scene", "mission_id": mission["mission_id"],
                        "target_vessel_id": ship.id, "callsign": ship.callsign,
                        "distance_nm": distance, "distress_kind": mission["distress_kind"]}
            return None
        if mission["state"] == "on_scene":
            # Strong drift or a player-moved ship breaks the close rendezvous; return to
            # en-route rather than completing an operation from over four miles away.
            if distance > RESCUE_ON_SCENE_RADIUS_NM * 1.55:
                mission["state"] = "en_route"
                mission["on_scene_started_s"] = None
                ship.distress_assistance_status = "en_route"
                return {"type": "rendezvous_lost", "mission_id": mission["mission_id"],
                        "target_vessel_id": ship.id, "callsign": ship.callsign,
                        "distance_nm": distance}
            scene_start = now if mission["on_scene_started_s"] is None else float(mission["on_scene_started_s"])
            if now - scene_start < RESCUE_WORK_DURATION_S:
                return None
            outcome, activity_text = _OUTCOMES.get(
                mission["distress_kind"], _OUTCOMES["taking_water"])
            # Leave the assisted vessel at the scene, safely holding station. Its stable
            # position override prevents the schedule from snapping it across the chart.
            ship.position_override_nm = physical_pos
            ship.activity_override = getattr(type(ship.activity), "ANCHORED", ship.activity)
            ship.activity = ship.activity_override
            ship.distress_assistance_status = "completed"
            ship.distress_outcome = outcome
            ship.mayday_resolved = True
            ship.distress_origin_activity = ship.distress_origin_activity or ship.activity
            ship.report_position(now, error_nm=0.15)
            mission["state"] = "completed"
            mission["completed_s"] = now
            mission["outcome"] = outcome
            self.completed_count += 1
            if hasattr(traffic, "release_rescue_contact"):
                traffic.release_rescue_contact(ship.id)
            return {"type": "completed", "mission_id": mission["mission_id"],
                    "target_vessel_id": ship.id, "callsign": ship.callsign,
                    "distress_kind": mission["distress_kind"], "outcome": outcome,
                    "activity_text": activity_text, "distance_nm": distance}
        return None

    def snapshot(self) -> dict:
        return {
            "schema_version": RESCUE_MISSION_SCHEMA_VERSION,
            "mission": dict(self.mission) if self.mission is not None else None,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
        }

    def restore(self, payload: dict) -> None:
        clean = self.validate_snapshot(payload)
        self.mission = clean["mission"]
        self.completed_count = clean["completed_count"]
        self.failed_count = clean["failed_count"]

    @classmethod
    def validate_snapshot(cls, payload: dict) -> dict:
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != RESCUE_MISSION_SCHEMA_VERSION:
            raise ValueError("unsupported player rescue mission snapshot schema")
        counts = []
        for key in ("completed_count", "failed_count"):
            value = int(payload.get(key, 0))
            if value < 0:
                raise ValueError("invalid rescue mission counter")
            counts.append(value)
        raw = payload.get("mission")
        if raw is None:
            mission = None
        else:
            if not isinstance(raw, dict) or int(raw.get("schema_version", 0)) != RESCUE_MISSION_SCHEMA_VERSION:
                raise ValueError("invalid rescue mission payload")
            required = ("mission_id", "target_vessel_id", "target_callsign", "distress_kind", "state")
            if any(not isinstance(raw.get(k), str) or not raw.get(k) for k in required):
                raise ValueError("rescue mission identity/state fields are invalid")
            state = str(raw["state"])
            if state not in _ACTIVE_STATES | _TERMINAL_STATES:
                raise ValueError("invalid rescue mission state")
            started = float(raw.get("started_s", 0.0))
            scene_start = raw.get("on_scene_started_s")
            completed = raw.get("completed_s")
            distance = raw.get("last_distance_nm")
            if not math.isfinite(started) or started < 0:
                raise ValueError("invalid rescue mission start time")
            if scene_start is not None and (not math.isfinite(float(scene_start)) or float(scene_start) < started):
                raise ValueError("invalid rescue scene start time")
            if completed is not None and (not math.isfinite(float(completed)) or float(completed) < started):
                raise ValueError("invalid rescue mission completion time")
            if distance is not None and (not math.isfinite(float(distance)) or float(distance) < 0):
                raise ValueError("invalid rescue mission distance")
            report = _finite_pair(raw.get("reported_position_nm"), "saved reported distress position")
            route = raw.get("route_target_world")
            route = None if route is None else list(_finite_pair(route, "saved rescue route target"))
            backup = raw.get("navigation_backup", {})
            if not isinstance(backup, dict) or len(backup) > 32:
                raise ValueError("invalid navigation backup in rescue mission")
            mission = dict(raw)
            mission.update({
                "reported_position_nm": list(report), "route_target_world": route,
                "started_s": started,
                "on_scene_started_s": None if scene_start is None else float(scene_start),
                "completed_s": None if completed is None else float(completed),
                "last_distance_nm": None if distance is None else float(distance),
                "course_overridden": bool(raw.get("course_overridden", False)),
                "navigation_backup": dict(backup),
            })
            if not isinstance(mission.get("outcome"), (str, type(None))):
                raise ValueError("invalid rescue mission outcome")
        return {"schema_version": RESCUE_MISSION_SCHEMA_VERSION, "mission": mission,
                "completed_count": counts[0], "failed_count": counts[1]}

    @classmethod
    def from_snapshot(cls, payload: dict | None) -> "PlayerRescueMissionManager":
        manager = cls()
        if payload is not None:
            manager.restore(payload)
        return manager
