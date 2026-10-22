"""Player-directed Coast Guard dispatch to a reported MAYDAY or liferaft plot (M9).

The controller commandeers one existing scheduled Coast Guard contact, keeps its
stable vessel ID, follows a desired track with finite turning, performs a short
on-scene search/assistance, and returns the hull to its scheduled route. The target
is always a radio-reported coordinate, never a hidden physical raft fix.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from fishing_sim.systems.ai_rescue import AIDistressResponseManager, _distance, _finite_pair
from fishing_sim.world.traffic import Activity, Archetype, AIShip, TrafficWorld, SIM_NM_PER_KNOT_SECOND

COAST_GUARD_ROUTE_SCHEMA_VERSION = 1
COAST_GUARD_ROUTE_MAX_RANGE_NM = 49.0
COAST_GUARD_ROUTE_ON_SCENE_RADIUS_NM = 1.25
COAST_GUARD_ROUTE_TURN_RATE_RAD_S = 0.34
COAST_GUARD_ROUTE_WORK_DURATION_S = 6.0
COAST_GUARD_ROUTE_RAFT_SEARCH_S = 2.0
COAST_GUARD_ROUTE_MAX_UPDATE_STEP_S = 12.0
COAST_GUARD_ROUTE_REPORT_INTERVAL_S = 4.0
_ACTIVE_STATES = {"en_route", "on_scene", "returning"}
_TERMINAL_STATES = {"completed", "failed"}
_TARGET_KINDS = {"distress", "liferaft"}


def _finite_time(value: Any, field: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError("%s must be finite and non-negative" % field)
    return number


class PlayerCoastGuardRoutingManager:
    """Route one existing Coast Guard patrol to a player-selected reported target."""

    def __init__(self) -> None:
        self.mission: dict[str, Any] | None = None
        self.completed_count = 0
        self.failed_count = 0
        self.next_sequence = 1

    @property
    def has_active_mission(self) -> bool:
        return bool(self.mission and self.mission.get("state") in _ACTIVE_STATES)

    @property
    def target_vessel_id(self) -> str | None:
        if not self.has_active_mission:
            return None
        return str(self.mission.get("target_vessel_id", "")) or None

    @staticmethod
    def _candidate(traffic: TrafficWorld, target_nm: tuple[float, float]) -> AIShip | None:
        candidates = []
        for ship in traffic.ships.values():
            if ship.archetype != Archetype.COAST_GUARD or ship.runtime_kind != "scheduled":
                continue
            # Do not steal a patrol already commandeered by towing, autonomous rescue,
            # player-directed rescue, or another higher-priority runtime controller.
            if ship.position_override_nm is not None or ship.activity_override is not None:
                continue
            if ship.mayday_sent or ship.activity in (Activity.ANCHORED, Activity.DISTRESSED):
                continue
            if float(ship.speed_kn) <= 0.1:
                continue
            distance = _distance(ship.position_nm, target_nm)
            if distance > COAST_GUARD_ROUTE_MAX_RANGE_NM:
                continue
            eta = distance / max(1.0, float(ship.speed_kn)) / SIM_NM_PER_KNOT_SECOND
            candidates.append((eta, distance, ship.id, ship))
        candidates.sort(key=lambda item: (round(item[0], 6), round(item[1], 6), item[2]))
        return candidates[0][3] if candidates else None

    def dispatch(self, traffic: TrafficWorld, *, target_kind: str, target_id: str,
                 target_vessel_id: str, target_callsign: str, target_position_nm,
                 sim_time_s: float, target_reported_at_s: float | None = None,
                 target_report_sequence: int = 0) -> dict:
        """Assign the nearest/fastest eligible existing patrol to an uncertain report."""
        if self.has_active_mission:
            return {"type": "unavailable", "reason": "a player-directed Coast Guard route is already active"}
        kind = str(target_kind)
        if kind not in _TARGET_KINDS:
            raise ValueError("unsupported Coast Guard route target kind")
        target_id = str(target_id).strip()
        parent_id = str(target_vessel_id).strip()
        if not target_id or not parent_id:
            raise ValueError("Coast Guard route target IDs must not be empty")
        target_nm = _finite_pair(target_position_nm, "reported target position")
        now = _finite_time(sim_time_s, "simulation time")
        parent = traffic.by_id(parent_id)
        if parent is None:
            return {"type": "unavailable", "reason": "reported target contact is no longer available"}
        if kind == "distress":
            if not parent.mayday_sent or parent.distress_assistance_status in ("completed", "failed", "en_route", "on_scene"):
                return {"type": "unavailable", "reason": "there is no unassigned active distress target to route to"}
            if parent.last_reported_position_nm is None:
                return {"type": "unavailable", "reason": "distress has no reported position fix"}
            # The caller passes the contact's actual last report; refuse hidden/truth fixes.
            if _distance(target_nm, parent.last_reported_position_nm) > 1e-6:
                return {"type": "unavailable", "reason": "distress route must use the saved reported fix"}
        elif kind == "liferaft":
            if (parent.mayday_sent and parent.distress_assistance_status in ("en_route", "on_scene")):
                return {"type": "unavailable", "reason": "the incident already has an active responder"}
            if not target_id.endswith(":liferaft:01"):
                return {"type": "unavailable", "reason": "invalid liferaft identity"}
            if target_reported_at_s is None:
                return {"type": "unavailable", "reason": "liferaft has no received beacon fix"}
            _finite_time(target_reported_at_s, "liferaft report time")

        responder = self._candidate(traffic, target_nm)
        if responder is None:
            return {"type": "unavailable", "reason": "no uncommitted Coast Guard patrol is within 49 NM"}
        start = _finite_pair(responder.position_nm, "Coast Guard position")
        responder.position_override_nm = start
        responder.activity_override = Activity.TRANSIT
        responder.position_nm = start
        responder.activity = Activity.TRANSIT
        responder.known_to_player = True
        traffic.index.upsert(responder.id, start)
        traffic.mark_known(responder.id)
        traffic.promote_rescue_contact(responder.id)
        traffic.promote_rescue_contact(parent.id)
        AIDistressResponseManager._set_report(responder, now, traffic)

        # A distress contact is reserved so the autonomous dispatcher cannot assign a
        # second patrol while this player-directed route is working the same incident.
        if parent.mayday_sent and parent.distress_assistance_status not in ("completed", "failed"):
            parent.distress_assistance_status = "en_route"
            parent.mayday_resolved = True
        mission_id = "coast-guard-route:%s:%s:%d:%d" % (
            responder.id, target_id, round(now * 1000.0), self.next_sequence)
        self.next_sequence += 1
        mission = {
            "schema_version": COAST_GUARD_ROUTE_SCHEMA_VERSION,
            "mission_id": mission_id,
            "state": "en_route",
            "target_kind": kind,
            "target_id": target_id,
            "target_vessel_id": parent.id,
            "target_callsign": str(target_callsign or parent.callsign)[:100],
            "target_position_nm": [target_nm[0], target_nm[1]],
            "target_reported_at_s": None if target_reported_at_s is None else float(target_reported_at_s),
            "target_report_sequence": max(0, int(target_report_sequence)),
            "responder_vessel_id": responder.id,
            "responder_callsign": responder.callsign,
            "started_s": now,
            "last_update_s": now,
            "last_report_s": now,
            "on_scene_elapsed_s": 0.0,
            "return_target_nm": None,
            "survivor_result": None,
        }
        self.mission = mission
        return {"type": "dispatched", "mission_id": mission_id,
                "target_kind": kind, "target_id": target_id,
                "target_vessel_id": parent.id, "target_callsign": mission["target_callsign"],
                "responder_vessel_id": responder.id, "responder_callsign": responder.callsign,
                "distance_nm": _distance(start, target_nm),
                "reported_position_nm": list(target_nm),
                "report_stale": bool(kind == "liferaft" and now - float(target_reported_at_s) >= 180.0)
                if kind == "liferaft" else False}

    def _release_failed(self, traffic: TrafficWorld, now: float, reason: str) -> dict:
        mission = self.mission or {}
        responder = traffic.by_id(str(mission.get("responder_vessel_id", "")))
        parent = traffic.by_id(str(mission.get("target_vessel_id", "")))
        if responder is not None:
            responder.position_override_nm = None
            responder.activity_override = None
            schedule_pos, schedule_heading, schedule_activity = responder.position_at(now)
            responder.position_nm = schedule_pos
            responder.heading_rad = schedule_heading
            responder.activity = schedule_activity
            traffic.index.upsert(responder.id, responder.position_nm)
            traffic.release_rescue_contact(responder.id)
        if parent is not None:
            if parent.distress_assistance_status in ("en_route", "on_scene"):
                parent.distress_assistance_status = "awaiting_dispatch"
                parent.distress_outcome = None
                if parent.distress_decision is None:
                    parent.mayday_resolved = False
            traffic.release_rescue_contact(parent.id)
        self.failed_count += 1
        if self.mission is not None:
            self.mission["state"] = "failed"
            self.mission["failure_reason"] = str(reason)[:240]
            self.mission["ended_s"] = now
        return {"type": "failed", "mission_id": mission.get("mission_id", ""),
                "target_vessel_id": mission.get("target_vessel_id", ""),
                "target_callsign": mission.get("target_callsign", "distressed vessel"),
                "responder_vessel_id": mission.get("responder_vessel_id", ""),
                "responder_callsign": mission.get("responder_callsign", "Coast Guard"),
                "reason": str(reason)}

    def update(self, sim_time_s: float, traffic: TrafficWorld, survivor_registry, *, sea_state: float = 0.0) -> list[dict]:
        """Steer an active patrol, replot fresh received raft reports, and resolve on-scene work."""
        if not self.has_active_mission:
            return []
        mission = self.mission
        now = _finite_time(sim_time_s, "simulation time")
        target = traffic.by_id(str(mission["target_vessel_id"]))
        responder = traffic.by_id(str(mission["responder_vessel_id"]))
        if target is None or responder is None:
            return [self._release_failed(traffic, now, "target or Coast Guard contact is missing")]
        raw_dt = max(0.0, now - float(mission.get("last_update_s", now)))
        dt = min(COAST_GUARD_ROUTE_MAX_UPDATE_STEP_S, raw_dt)
        mission["last_update_s"] = now
        events: list[dict] = []

        if mission["target_kind"] == "liferaft":
            old_goal = _finite_pair(mission["target_position_nm"], "previous liferaft plot")
            for report in survivor_registry.reported_liferaft_targets(now):
                if report["raft_id"] != mission["target_id"]:
                    continue
                if int(report["sequence"]) > int(mission.get("target_report_sequence", 0)):
                    new_goal = _finite_pair(report["position_nm"], "refreshed liferaft plot")
                    mission["target_position_nm"] = [float(v) for v in new_goal]
                    mission["target_reported_at_s"] = float(report["reported_at_s"])
                    mission["target_report_sequence"] = int(report["sequence"])
                    # A new beacon received after reaching the old plot should pull the
                    # search back onto the newly reported fix, not leave the patrol loitering.
                    if mission.get("state") == "on_scene" and _distance(old_goal, new_goal) > 0.15:
                        mission["state"] = "en_route"
                        mission["on_scene_elapsed_s"] = 0.0
                        responder.activity_override = Activity.TRANSIT
                break

        state = mission["state"]
        if state == "en_route":
            goal = _finite_pair(mission["target_position_nm"], "route target")
            distance = AIDistressResponseManager._move_toward(responder, goal, dt, sea_state)
            traffic.index.upsert(responder.id, responder.position_nm)
            if now - float(mission.get("last_report_s", 0.0)) >= COAST_GUARD_ROUTE_REPORT_INTERVAL_S:
                AIDistressResponseManager._set_report(responder, now, traffic)
                mission["last_report_s"] = now
            if distance <= COAST_GUARD_ROUTE_ON_SCENE_RADIUS_NM:
                mission["state"] = "on_scene"
                mission["on_scene_elapsed_s"] = 0.0
                responder.activity_override = Activity.TRANSIT if mission["target_kind"] == "distress" else Activity.ANCHORED
                if target.distress_assistance_status == "en_route":
                    target.distress_assistance_status = "on_scene"
                events.append({"type": "on_scene", "mission_id": mission["mission_id"],
                               "target_kind": mission["target_kind"], "target_vessel_id": target.id,
                               "target_callsign": target.callsign, "responder_vessel_id": responder.id,
                               "responder_callsign": responder.callsign, "distance_nm": float(distance)})

        elif state == "on_scene":
            if mission["target_kind"] == "distress":
                # At the reported scene the patrol may sight the distressed vessel and
                # close on its physical position; before arrival only the radio fix is used.
                true_goal = _finite_pair(target.position_nm, "distressed vessel position")
                # The patrol is already at the reported scene, so use a low-speed
                # approach while closing on the physical casualty. Keeping its full
                # transit speed here can create a large turning radius and carry the
                # hull past the target before the assistance radius is reached.
                cruise_speed_kn = float(responder.speed_kn)
                try:
                    responder.speed_kn = min(cruise_speed_kn, 2.0)
                    distance = AIDistressResponseManager._move_toward(
                        responder, true_goal, dt, sea_state)
                finally:
                    responder.speed_kn = cruise_speed_kn
                traffic.index.upsert(responder.id, responder.position_nm)
                if distance <= COAST_GUARD_ROUTE_ON_SCENE_RADIUS_NM:
                    responder.activity_override = Activity.ANCHORED
                    mission["on_scene_elapsed_s"] = float(mission.get("on_scene_elapsed_s", 0.0)) + dt
                    if mission["on_scene_elapsed_s"] >= COAST_GUARD_ROUTE_WORK_DURATION_S:
                        survivor_result = survivor_registry.complete_assistance(
                            target.id, str(mission["mission_id"]), responder.position_nm, now)
                        mission["survivor_result"] = copy.deepcopy(survivor_result)
                        target.distress_assistance_status = "completed"
                        target.distress_outcome = "Coast Guard reached the reported distress position and completed assistance"
                        target.activity_override = Activity.ANCHORED
                        target.position_override_nm = target.distress_position_nm or target.position_nm
                        target.position_nm = target.position_override_nm
                        responder.activity_override = Activity.RETURNING
                        mission["state"] = "returning"
                        mission["return_target_nm"] = list(responder.position_at(now)[0])
                        events.append({"type": "completed", "mission_id": mission["mission_id"],
                                       "target_kind": "distress", "target_vessel_id": target.id,
                                       "target_callsign": target.callsign, "responder_vessel_id": responder.id,
                                       "responder_callsign": responder.callsign, "survivor_result": survivor_result})
                else:
                    responder.activity_override = Activity.TRANSIT
                    mission["on_scene_elapsed_s"] = 0.0
            else:
                # Raft targets use only the most recent received beacon plot. The
                # survivor ledger applies the real 2-NM pickup rule at completion.
                mission["on_scene_elapsed_s"] = float(mission.get("on_scene_elapsed_s", 0.0)) + dt
                if mission["on_scene_elapsed_s"] >= COAST_GUARD_ROUTE_RAFT_SEARCH_S:
                    result = survivor_registry.complete_assistance(
                        str(mission["target_vessel_id"]), str(mission["mission_id"]), responder.position_nm, now)
                    mission["survivor_result"] = copy.deepcopy(result)
                    target.distress_assistance_status = "completed"
                    if result.get("liferafts_recovered", 0):
                        target.distress_outcome = "Coast Guard recovered the reported liferaft and its survivors"
                    else:
                        target.distress_outcome = "Coast Guard searched the reported liferaft plot; raft not recovered on this pass"
                    responder.activity_override = Activity.RETURNING
                    mission["state"] = "returning"
                    mission["return_target_nm"] = list(responder.position_at(now)[0])
                    events.append({"type": "completed", "mission_id": mission["mission_id"],
                                   "target_kind": "liferaft", "target_vessel_id": target.id,
                                   "target_callsign": target.callsign, "responder_vessel_id": responder.id,
                                   "responder_callsign": responder.callsign, "survivor_result": result})

        elif state == "returning":
            schedule_pos = _finite_pair(responder.position_at(now)[0], "Coast Guard schedule position")
            distance = AIDistressResponseManager._move_toward(
                responder, schedule_pos, dt, sea_state, speed_multiplier=1.35)
            traffic.index.upsert(responder.id, responder.position_nm)
            if now - float(mission.get("last_report_s", 0.0)) >= COAST_GUARD_ROUTE_REPORT_INTERVAL_S:
                AIDistressResponseManager._set_report(responder, now, traffic)
                mission["last_report_s"] = now
            if distance <= 0.85:
                responder.position_override_nm = None
                responder.activity_override = None
                responder.position_nm = schedule_pos
                responder.heading_rad = float(responder.position_at(now)[1])
                responder.activity = responder.position_at(now)[2]
                traffic.index.upsert(responder.id, responder.position_nm)
                traffic.release_rescue_contact(responder.id)
                traffic.release_rescue_contact(target.id)
                self.completed_count += 1
                mission["state"] = "completed"
                mission["ended_s"] = now
                events.append({"type": "returned", "mission_id": mission["mission_id"],
                               "target_kind": mission["target_kind"], "target_vessel_id": target.id,
                               "target_callsign": target.callsign, "responder_vessel_id": responder.id,
                               "responder_callsign": responder.callsign})
        return events

    def snapshot(self) -> dict:
        return {"schema_version": COAST_GUARD_ROUTE_SCHEMA_VERSION,
                "mission": copy.deepcopy(self.mission),
                "completed_count": int(self.completed_count),
                "failed_count": int(self.failed_count),
                "next_sequence": int(self.next_sequence)}

    @staticmethod
    def validate_snapshot(payload: Any) -> dict:
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != COAST_GUARD_ROUTE_SCHEMA_VERSION:
            raise ValueError("unsupported player-directed Coast Guard route snapshot schema")
        try:
            completed = int(payload.get("completed_count", 0))
            failed = int(payload.get("failed_count", 0))
            sequence = int(payload.get("next_sequence", 1))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid Coast Guard routing counters") from exc
        if min(completed, failed) < 0 or sequence < 1:
            raise ValueError("invalid Coast Guard routing counters")
        mission = payload.get("mission")
        clean_mission = None
        if mission is not None:
            if not isinstance(mission, dict) or int(mission.get("schema_version", 0)) != COAST_GUARD_ROUTE_SCHEMA_VERSION:
                raise ValueError("invalid Coast Guard route mission")
            state = str(mission.get("state", ""))
            kind = str(mission.get("target_kind", ""))
            if state not in _ACTIVE_STATES | _TERMINAL_STATES or kind not in _TARGET_KINDS:
                raise ValueError("invalid Coast Guard route state or target kind")
            for key in ("mission_id", "target_id", "target_vessel_id", "target_callsign",
                        "responder_vessel_id", "responder_callsign"):
                if not isinstance(mission.get(key), str) or not mission[key].strip():
                    raise ValueError("invalid Coast Guard route mission field: %s" % key)
            _finite_pair(mission.get("target_position_nm"), "saved Coast Guard target position")
            for field in ("started_s", "last_update_s", "last_report_s", "on_scene_elapsed_s"):
                _finite_time(mission.get(field, 0.0), "saved Coast Guard " + field)
            for field in ("started_s", "last_update_s", "last_report_s"):
                if float(mission.get(field, 0.0)) + 1e-6 < 0.0:
                    raise ValueError("invalid Coast Guard route clock")
            report_time = mission.get("target_reported_at_s")
            if report_time is not None:
                _finite_time(report_time, "saved Coast Guard target report time")
            if int(mission.get("target_report_sequence", 0)) < 0:
                raise ValueError("invalid Coast Guard beacon sequence")
            if state == "returning":
                _finite_pair(mission.get("return_target_nm"), "saved Coast Guard return target")
            if mission.get("survivor_result") is not None and not isinstance(mission.get("survivor_result"), dict):
                raise ValueError("invalid Coast Guard survivor result")
            clean_mission = copy.deepcopy(mission)
        return {"schema_version": COAST_GUARD_ROUTE_SCHEMA_VERSION,
                "mission": clean_mission, "completed_count": completed,
                "failed_count": failed, "next_sequence": sequence}

    def restore(self, payload: Any) -> None:
        clean = self.validate_snapshot(payload)
        self.mission = clean["mission"]
        self.completed_count = clean["completed_count"]
        self.failed_count = clean["failed_count"]
        self.next_sequence = clean["next_sequence"]

    @classmethod
    def from_snapshot(cls, payload: Any = None) -> "PlayerCoastGuardRoutingManager":
        manager = cls()
        if payload is not None:
            manager.restore(payload)
        return manager
