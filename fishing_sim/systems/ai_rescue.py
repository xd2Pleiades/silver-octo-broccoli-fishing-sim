"""Autonomous response to distress calls from the coarse AI fleet (M9).

The manager commandeers one existing scheduled vessel at a time. It does not spawn
another Coast Guard hull, and it advances the responder by steering toward a desired
track with finite turning rate; the vessel follows its heading, not an invisible rail.
All mission state is JSON-safe and its responder's temporary route is stored on the
shared AIShip contact so career saves can reconstruct the same vessel identity.
"""
from __future__ import annotations

import math
from typing import Any

from fishing_sim.world.traffic import Activity, Archetype, AIShip, TrafficWorld, SIM_NM_PER_KNOT_SECOND

AI_RESCUE_SCHEMA_VERSION = 1
AI_RESCUE_DISPATCH_DELAY_S = 42.0
AI_RESCUE_STORM_DISPATCH_DELAY_S = 12.0
AI_RESCUE_RETRY_INTERVAL_S = 4.0
AI_RESCUE_ON_SCENE_RADIUS_NM = 1.25
AI_RESCUE_WORK_DURATION_S = 6.0
AI_RESCUE_TURN_RATE_RAD_S = 0.34
AI_RESCUE_MAX_UPDATE_STEP_S = 12.0
COAST_GUARD_RESPONSE_RANGE_NM = 49.0
NEARBY_RESPONSE_RANGE_NM = 8.0
STORM_NEARBY_RESPONSE_RANGE_NM = 15.0
_REPORT_INTERVAL_S = 4.0
_ACTIVE_STATES = {"en_route", "on_scene", "returning"}
_TERMINAL_STATES = {"completed", "failed"}
_RESPONSE_ARCHETYPES = {
    Archetype.INDEPENDENT_LONGLINE,
    Archetype.INDEPENDENT_GILLNET,
    Archetype.CORPORATE_CATCHER,
    Archetype.CORPORATE_LONGLINER,
    Archetype.COAST_GUARD,
}
_OUTCOMES = {
    "taking_water": "water ingress controlled; vessel secured alongside",
    "engine_failure": "engine failure assessed; vessel secured for repair",
    "injury": "injured hand stabilized; vessel standing by for further help",
    "gear_entanglement": "propeller fouling cleared; vessel able to proceed when ready",
}


def _finite_pair(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("%s must be a coordinate pair" % field)
    pair = (float(value[0]), float(value[1]))
    if not all(math.isfinite(v) for v in pair):
        raise ValueError("%s must contain finite coordinates" % field)
    return pair


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _turn_toward(current: float, desired: float, max_step: float) -> float:
    delta = (float(desired) - float(current) + math.pi) % math.tau - math.pi
    return float(current) + max(-max_step, min(max_step, delta))


class AIDistressResponseManager:
    """Dispatch and steer one existing AI vessel to help another vessel in distress."""

    def __init__(self) -> None:
        self.mission: dict[str, Any] | None = None
        self.completed_count = 0
        self.failed_count = 0
        self.last_scan_s = -AI_RESCUE_RETRY_INTERVAL_S

    @property
    def has_active_mission(self) -> bool:
        return bool(self.mission and self.mission.get("state") in _ACTIVE_STATES)

    @property
    def mission_target_id(self) -> str | None:
        if self.has_active_mission:
            return str(self.mission.get("target_vessel_id", "")) or None
        return None

    def is_responding_to(self, vessel_id: str) -> bool:
        return bool(self.has_active_mission and self.mission.get("target_vessel_id") == str(vessel_id))

    @staticmethod
    def _candidate_responder(target: AIShip, traffic: TrafficWorld, sea_state: float) -> AIShip | None:
        storm = max(0.0, min(1.5, float(sea_state)))
        local_radius = (NEARBY_RESPONSE_RANGE_NM
                        + max(0.0, storm - 0.45) * (STORM_NEARBY_RESPONSE_RANGE_NM - NEARBY_RESPONSE_RANGE_NM) / 1.05)
        candidates = []
        for ship in traffic.ships.values():
            if ship.id == target.id or ship.runtime_kind != "scheduled":
                continue
            if ship.archetype not in _RESPONSE_ARCHETYPES:
                continue
            if ship.mayday_sent or ship.activity_override is not None or ship.position_override_nm is not None:
                continue
            if ship.activity in (Activity.ANCHORED, Activity.DISTRESSED):
                continue
            if ship.speed_kn <= 0.1:
                continue
            distance = _distance(ship.position_nm, target.position_nm)
            if ship.archetype == Archetype.COAST_GUARD:
                max_range = COAST_GUARD_RESPONSE_RANGE_NM
            else:
                max_range = local_radius
            if distance > max_range:
                continue
            eta = distance / max(1.0, ship.speed_kn) / SIM_NM_PER_KNOT_SECOND
            # ETA is primary: a fishing captain already close to the incident may beat
            # a distant patrol, while Coast Guard wins exact ETA ties by role priority.
            priority = 0 if ship.archetype == Archetype.COAST_GUARD else 1
            candidates.append((eta, priority, ship.id, ship))
        candidates.sort(key=lambda item: (round(item[0], 6), item[1], item[2]))
        return candidates[0][3] if candidates else None

    def _dispatch(self, target: AIShip, responder: AIShip, now: float, traffic: TrafficWorld) -> dict:
        start = _finite_pair(responder.position_nm, "responder position")
        scene = _finite_pair(target.distress_position_nm or target.position_nm, "distress scene")
        # Distress locations are held by the traffic schedule layer. Keep them frozen
        # throughout the response even if they were not visible to the player.
        target.distress_position_nm = scene
        target.position_override_nm = scene
        target.activity_override = Activity.DISTRESSED
        target.position_nm = scene
        target.activity = Activity.DISTRESSED
        target.distress_assistance_status = "en_route"
        target.distress_outcome = None
        target.mayday_resolved = True  # the incident has an assigned responder; no second decision

        responder.position_override_nm = start
        responder.activity_override = Activity.TRANSIT
        responder.position_nm = start
        responder.known_to_player = True
        responder.activity = Activity.TRANSIT
        traffic.index.upsert(responder.id, start)
        traffic.index.upsert(target.id, scene)
        traffic.mark_known(responder.id)
        # Expose a plotted contact, not a perfect omniscient position jump.
        self._set_report(responder, now, traffic)
        traffic.mark_known(target.id)
        traffic.promote_rescue_contact(target.id)
        traffic.promote_rescue_contact(responder.id)

        mission_id = "ai-rescue:%s:%s:%d" % (responder.id, target.id, round(now * 1000.0))
        self.mission = {
            "schema_version": AI_RESCUE_SCHEMA_VERSION,
            "mission_id": mission_id,
            "target_vessel_id": target.id,
            "target_callsign": target.callsign,
            "responder_vessel_id": responder.id,
            "responder_callsign": responder.callsign,
            "state": "en_route",
            "started_s": float(now),
            "last_update_s": float(now),
            "last_report_s": float(now),
            "on_scene_elapsed_s": 0.0,
            "returning_started_s": None,
            "return_target_nm": None,
            "distress_kind": str(target.distress_kind or "taking_water"),
        }
        return {"type": "dispatched", "mission_id": mission_id,
                "target_vessel_id": target.id, "target_callsign": target.callsign,
                "responder_vessel_id": responder.id, "responder_callsign": responder.callsign,
                "distance_nm": _distance(start, scene)}

    @staticmethod
    def _set_report(ship: AIShip, now: float, traffic: TrafficWorld) -> None:
        # Report error is deterministic within a four-second update bucket and does
        # not consume the global gameplay RNG stream.
        import random
        from fishing_sim.world.seeding import stable_seed
        rng = random.Random(stable_seed(traffic.world_seed, "ai-rescue-plot", ship.id,
                                        int(max(0.0, now) // _REPORT_INTERVAL_S)))
        ship.report_position(now, error_nm=0.18, rng=rng)
        traffic.mark_known(ship.id)

    @staticmethod
    def _move_toward(ship: AIShip, target_nm: tuple[float, float], dt: float,
                     sea_state: float, *, speed_multiplier: float = 1.0) -> float:
        current = _finite_pair(ship.position_nm, "vessel position")
        goal = _finite_pair(target_nm, "route target")
        dx, dy = goal[0] - current[0], goal[1] - current[1]
        distance = math.hypot(dx, dy)
        if distance <= 1e-6 or dt <= 0.0:
            return distance
        desired_heading = math.atan2(-dy, dx)  # traffic heading convention: y points north
        turn = AI_RESCUE_TURN_RATE_RAD_S * dt
        ship.heading_rad = _turn_toward(ship.heading_rad, desired_heading, turn)
        sea = max(0.0, min(1.5, float(sea_state)))
        speed_scale = max(0.58, 1.0 - max(0.0, sea - 0.55) * 0.25)
        travel = min(distance, max(0.0, ship.speed_kn) * SIM_NM_PER_KNOT_SECOND
                     * dt * speed_scale * max(0.5, float(speed_multiplier)))
        # The vessel follows its current heading with finite turn rate; the desired
        # track sets the heading target but is not a teleporting path/rail.
        x = current[0] + math.cos(ship.heading_rad) * travel
        y = current[1] - math.sin(ship.heading_rad) * travel
        ship.position_nm = (x, y)
        ship.position_override_nm = ship.position_nm
        return _distance(ship.position_nm, goal)

    def _end_failed(self, traffic: TrafficWorld, target: AIShip | None, responder: AIShip | None,
                    reason: str, now: float) -> dict:
        mission = self.mission or {}
        if target is not None and target.distress_assistance_status in ("en_route", "on_scene"):
            target.distress_assistance_status = "awaiting_dispatch"
            target.distress_outcome = None
            if target.distress_decision is None:
                target.mayday_resolved = False
        if responder is not None:
            responder.position_override_nm = None
            responder.activity_override = None
            responder.activity = responder.position_at(now)[2]
            traffic.index.upsert(responder.id, responder.position_nm)
            traffic.release_rescue_contact(responder.id)
        if target is not None:
            traffic.release_rescue_contact(target.id)
        self.failed_count += 1
        if self.mission is not None:
            self.mission["state"] = "failed"
            self.mission["failure_reason"] = str(reason)[:240]
            self.mission["ended_s"] = float(now)
        return {"type": "failed", "mission_id": mission.get("mission_id", ""),
                "target_vessel_id": mission.get("target_vessel_id", ""),
                "target_callsign": mission.get("target_callsign", "distressed vessel"),
                "responder_vessel_id": mission.get("responder_vessel_id", ""),
                "responder_callsign": mission.get("responder_callsign", "responder"),
                "reason": str(reason)}

    def update(self, sim_time_s: float, traffic: TrafficWorld, *, sea_state: float,
               player_rescue_target_id: str | None = None, sea_state_at=None) -> list[dict]:
        """Dispatch when help is overdue, and steer the chosen hull on fixed simulation time.

        In ordinary conditions the dispatcher allows a short response window for the
        player. In heavy weather it shortens that window and widens the nearby-vessel
        range, so another captain is more likely to turn around if no response arrives.
        """
        now = max(0.0, float(sim_time_s))
        sea = max(0.0, min(1.5, float(sea_state)))
        events: list[dict] = []
        if self.has_active_mission:
            mission = self.mission
            target = traffic.by_id(mission["target_vessel_id"])
            responder = traffic.by_id(mission["responder_vessel_id"])
            if target is None or responder is None:
                events.append(self._end_failed(traffic, target, responder, "target or responder contact is missing", now))
                return events
            raw_dt = max(0.0, now - float(mission.get("last_update_s", now)))
            dt = min(AI_RESCUE_MAX_UPDATE_STEP_S, raw_dt)
            mission["last_update_s"] = now
            state = str(mission.get("state", ""))
            if state == "en_route":
                distance = self._move_toward(responder, target.position_nm, dt, sea)
                traffic.index.upsert(responder.id, responder.position_nm)
                if now - float(mission.get("last_report_s", 0.0)) >= _REPORT_INTERVAL_S:
                    self._set_report(responder, now, traffic)
                    mission["last_report_s"] = now
                if distance <= AI_RESCUE_ON_SCENE_RADIUS_NM:
                    mission["state"] = "on_scene"
                    mission["on_scene_elapsed_s"] = 0.0
                    target.distress_assistance_status = "on_scene"
                    responder.activity_override = Activity.ANCHORED
                    events.append({"type": "on_scene", "mission_id": mission["mission_id"],
                                   "target_vessel_id": target.id, "target_callsign": target.callsign,
                                   "responder_vessel_id": responder.id, "responder_callsign": responder.callsign,
                                   "distance_nm": float(distance)})
            elif state == "on_scene":
                # Hold at working distance; if waves/schedules displace the contact, the
                # responder re-approaches instead of declaring success from stale range.
                distance = _distance(responder.position_nm, target.position_nm)
                if distance > AI_RESCUE_ON_SCENE_RADIUS_NM * 1.6:
                    mission["state"] = "en_route"
                    mission["on_scene_elapsed_s"] = 0.0
                    target.distress_assistance_status = "en_route"
                    responder.activity_override = Activity.TRANSIT
                    events.append({"type": "rendezvous_lost", "mission_id": mission["mission_id"],
                                   "target_vessel_id": target.id, "target_callsign": target.callsign,
                                   "responder_vessel_id": responder.id, "responder_callsign": responder.callsign,
                                   "distance_nm": float(distance)})
                else:
                    mission["on_scene_elapsed_s"] = float(mission.get("on_scene_elapsed_s", 0.0)) + dt
                    if mission["on_scene_elapsed_s"] >= AI_RESCUE_WORK_DURATION_S:
                        outcome = _OUTCOMES.get(mission.get("distress_kind"), _OUTCOMES["taking_water"])
                        target.distress_assistance_status = "completed"
                        target.distress_outcome = outcome
                        target.activity_override = Activity.ANCHORED
                        target.position_override_nm = target.distress_position_nm or target.position_nm
                        target.position_nm = target.position_override_nm
                        responder.activity_override = Activity.RETURNING
                        mission["state"] = "returning"
                        mission["returning_started_s"] = now
                        # Rejoin the schedule at its current physical point, then release
                        # the temporary override only when the hull reaches that track.
                        mission["return_target_nm"] = list(responder.position_at(now)[0])
                        traffic.index.upsert(target.id, target.position_nm)
                        events.append({"type": "completed", "mission_id": mission["mission_id"],
                                       "target_vessel_id": target.id, "target_callsign": target.callsign,
                                       "responder_vessel_id": responder.id, "responder_callsign": responder.callsign,
                                       "outcome": outcome})
            elif state == "returning":
                schedule_position = _finite_pair(responder.position_at(now)[0], "schedule position")
                distance = self._move_toward(responder, schedule_position, dt, sea, speed_multiplier=1.35)
                traffic.index.upsert(responder.id, responder.position_nm)
                if now - float(mission.get("last_report_s", 0.0)) >= _REPORT_INTERVAL_S:
                    self._set_report(responder, now, traffic)
                    mission["last_report_s"] = now
                if distance <= 0.85:
                    responder.position_override_nm = None
                    responder.activity_override = None
                    responder.position_nm = schedule_position
                    responder.heading_rad = float(responder.position_at(now)[1])
                    traffic.index.upsert(responder.id, responder.position_nm)
                    traffic.release_rescue_contact(responder.id)
                    traffic.release_rescue_contact(target.id)
                    self.completed_count += 1
                    mission["state"] = "completed"
                    mission["ended_s"] = now
                    events.append({"type": "returned", "mission_id": mission["mission_id"],
                                   "target_vessel_id": target.id, "target_callsign": target.callsign,
                                   "responder_vessel_id": responder.id, "responder_callsign": responder.callsign})
            return events

        if now - self.last_scan_s < AI_RESCUE_RETRY_INTERVAL_S:
            return events
        self.last_scan_s = now
        if player_rescue_target_id:
            player_rescue_target_id = str(player_rescue_target_id)
        distressed = [ship for ship in traffic.ships.values()
                      if ship.mayday_sent
                      and ship.distress_assistance_status in ("none", "ignored", "awaiting_dispatch", "cancelled")
                      and ship.activity_override == Activity.DISTRESSED
                      and ship.id != player_rescue_target_id]
        distressed.sort(key=lambda s: (float(s.distress_started_s if s.distress_started_s is not None else now), s.id))
        for target in distressed:
            # Dispatch urgency and local-support radius use weather at the incident,
            # not only the player's current sea state. Fall back safely if no sampler
            # is supplied or a spatial weather sample is unavailable.
            target_sea = sea
            if callable(sea_state_at):
                try:
                    sampled_sea = float(sea_state_at(target))
                    if math.isfinite(sampled_sea):
                        target_sea = max(0.0, min(1.5, sampled_sea))
                except (TypeError, ValueError, ArithmeticError):
                    target_sea = sea
            if target.distress_decision == "assist" and target.distress_assistance_status in ("awaiting_dispatch", "cancelled"):
                # Let the player's committed route own this incident unless that mission
                # has explicitly ended. A cancelled mission can receive a second responder.
                if target.distress_assistance_status == "awaiting_dispatch":
                    continue
            started = max(0.0, float(target.distress_started_s if target.distress_started_s is not None else now))
            delay = AI_RESCUE_STORM_DISPATCH_DELAY_S if target_sea >= 0.75 else AI_RESCUE_DISPATCH_DELAY_S
            if target.distress_assistance_status == "ignored":
                delay = 0.0
            if now - started < delay:
                continue
            responder = self._candidate_responder(target, traffic, target_sea)
            if responder is None:
                target.distress_assistance_status = "awaiting_dispatch"
                continue
            events.append(self._dispatch(target, responder, now, traffic))
            break  # one autonomous response at a time; don't commandeer the entire fleet
        return events

    def snapshot(self) -> dict:
        return {
            "schema_version": AI_RESCUE_SCHEMA_VERSION,
            "mission": dict(self.mission) if self.mission is not None else None,
            "completed_count": int(self.completed_count),
            "failed_count": int(self.failed_count),
            "last_scan_s": float(self.last_scan_s),
        }

    @staticmethod
    def validate_snapshot(payload: Any) -> dict:
        if payload is None:
            return {"schema_version": AI_RESCUE_SCHEMA_VERSION, "mission": None,
                    "completed_count": 0, "failed_count": 0,
                    "last_scan_s": -AI_RESCUE_RETRY_INTERVAL_S}
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != AI_RESCUE_SCHEMA_VERSION:
            raise ValueError("unsupported AI rescue mission snapshot schema")
        try:
            completed = int(payload.get("completed_count", 0))
            failed = int(payload.get("failed_count", 0))
            last_scan = float(payload.get("last_scan_s", -AI_RESCUE_RETRY_INTERVAL_S))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid AI rescue manager counters") from exc
        if completed < 0 or failed < 0 or not math.isfinite(last_scan):
            raise ValueError("invalid AI rescue manager counters")
        raw_mission = payload.get("mission")
        mission = None
        if raw_mission is not None:
            if not isinstance(raw_mission, dict):
                raise ValueError("invalid AI rescue mission")
            mission = dict(raw_mission)
            if int(mission.get("schema_version", 0)) != AI_RESCUE_SCHEMA_VERSION:
                raise ValueError("unsupported AI rescue mission schema")
            state = str(mission.get("state", ""))
            if state not in _ACTIVE_STATES | _TERMINAL_STATES:
                raise ValueError("invalid AI rescue mission state")
            target_id = str(mission.get("target_vessel_id", "")).strip()
            responder_id = str(mission.get("responder_vessel_id", "")).strip()
            if not target_id or not responder_id or target_id == responder_id:
                raise ValueError("invalid AI rescue vessel identity")
            for name in ("mission_id", "target_callsign", "responder_callsign"):
                if not isinstance(mission.get(name), str) or not mission[name].strip():
                    raise ValueError("invalid AI rescue mission field: %s" % name)
            for field in ("started_s", "last_update_s", "last_report_s", "on_scene_elapsed_s"):
                try:
                    number = float(mission.get(field, 0.0))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("invalid AI rescue clock: %s" % field) from exc
                if not math.isfinite(number) or number < 0:
                    raise ValueError("invalid AI rescue clock: %s" % field)
                mission[field] = number
            if state == "returning":
                try:
                    mission["returning_started_s"] = float(mission.get("returning_started_s"))
                    if not math.isfinite(mission["returning_started_s"]) or mission["returning_started_s"] < 0:
                        raise ValueError("invalid AI rescue return clock")
                    mission["return_target_nm"] = list(_finite_pair(mission.get("return_target_nm"), "return target"))
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid AI rescue return state") from exc
            mission["state"] = state
            mission["target_vessel_id"] = target_id
            mission["responder_vessel_id"] = responder_id
        return {"schema_version": AI_RESCUE_SCHEMA_VERSION, "mission": mission,
                "completed_count": completed, "failed_count": failed, "last_scan_s": last_scan}

    def restore(self, payload: Any) -> None:
        clean = self.validate_snapshot(payload)
        self.mission = clean["mission"]
        self.completed_count = clean["completed_count"]
        self.failed_count = clean["failed_count"]
        self.last_scan_s = clean["last_scan_s"]

    @classmethod
    def from_snapshot(cls, payload: Any) -> "AIDistressResponseManager":
        manager = cls()
        manager.restore(payload)
        return manager
