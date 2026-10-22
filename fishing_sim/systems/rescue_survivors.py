"""Persistent casualty-transfer and liferaft-survival state for M9 rescue missions.

Survivors use the stable traffic vessel ID as their incident parent.  A liferaft is
an independent, drifting survivor target rather than a duplicate ship/contact.  This
keeps map/radio/Coast Guard identity ownership in TrafficWorld and lets the player
and autonomous responder share one idempotent survivor ledger.
"""
from __future__ import annotations

import copy
import math
import random
from types import SimpleNamespace
from typing import Any

from fishing_sim.world.seeding import stable_seed

RESCUE_SURVIVOR_SCHEMA_VERSION = 1
CASUALTY_SURVIVAL_S = 360.0
LIFERAFT_SURVIVAL_S = 270.0
LIFERAFT_PICKUP_RADIUS_NM = 2.0
LIFERAFT_OCCUPANTS = 2
LIFERAFT_BEACON_RANGE_NM = 55.0
LIFERAFT_BEACON_INTERVAL_S = 90.0
LIFERAFT_REPORT_ERROR_MIN_NM = 0.25
LIFERAFT_REPORT_ERROR_MAX_NM = 0.95
MAX_RESCUE_INCIDENTS = 512
RESCUE_SURVIVOR_UPDATE_INTERVAL_S = 1.0


def _finite_pair(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("%s must be a coordinate pair" % field)
    pair = (float(value[0]), float(value[1]))
    if not all(math.isfinite(v) for v in pair):
        raise ValueError("%s must contain finite coordinates" % field)
    return pair


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


class RescueSurvivorRegistry:
    """Durable survivor state keyed by the distress vessel's stable identity.

    First-slice content is deterministic and intentionally narrow: a taking-water
    MAYDAY deploys one two-person liferaft; an injury MAYDAY creates one casualty
    aboard the distressed vessel. Other incidents do not invent extra people.
    Timers use simulation seconds, and all pickup operations are mission-idempotent.
    """

    def __init__(self) -> None:
        self.incidents: dict[str, dict[str, Any]] = {}
        self.casualties_transferred = 0
        self.liferaft_occupants_recovered = 0
        self.survivors_lost = 0
        self.last_update_s: float | None = None

    def ensure_incident(self, ship, sim_time_s: float) -> list[dict]:
        """Register survivor state once for a MAYDAY vessel; return deployment events."""
        vessel_id = str(getattr(ship, "id", "")).strip()
        if not vessel_id or not bool(getattr(ship, "mayday_sent", False)):
            return []
        if vessel_id in self.incidents:
            return []
        try:
            now = float(sim_time_s)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid survivor incident clock") from exc
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("invalid survivor incident clock")
        kind = str(getattr(ship, "distress_kind", None) or "taking_water")
        started = getattr(ship, "distress_started_s", None)
        try:
            started_s = now if started is None else max(0.0, float(started))
        except (TypeError, ValueError, OverflowError):
            started_s = now
        scene = _finite_pair(getattr(ship, "distress_position_nm", None) or ship.position_nm,
                             "distress scene")
        incident: dict[str, Any] = {
            "vessel_id": vessel_id,
            "callsign": str(getattr(ship, "callsign", vessel_id))[:100],
            "distress_kind": kind,
            "started_s": started_s,
            "casualty": None,
            "liferaft": None,
            "completed_mission_ids": [],
        }
        events: list[dict] = []
        if kind == "injury":
            incident["casualty"] = {
                "survivor_id": vessel_id + ":casualty:01",
                "status": "aboard",
                "remaining_s": CASUALTY_SURVIVAL_S,
                "last_update_s": now,
                "recovered_by": None,
            }
        elif kind == "taking_water":
            rng = random.Random(stable_seed("rescue-liferaft", vessel_id))
            offset_angle = rng.random() * math.tau
            offset_nm = rng.uniform(0.18, 0.38)
            drift_angle = rng.random() * math.tau
            raft_pos = (scene[0] + math.cos(offset_angle) * offset_nm,
                        scene[1] + math.sin(offset_angle) * offset_nm)
            incident["liferaft"] = {
                "raft_id": vessel_id + ":liferaft:01",
                "position_nm": list(raft_pos),
                "occupants": LIFERAFT_OCCUPANTS,
                "status": "afloat",
                "remaining_s": LIFERAFT_SURVIVAL_S,
                "last_update_s": now,
                "drift_heading_rad": drift_angle,
                "recovered_by": None,
                # Radio/chart state contains a noisy report, never the physical raft fix.
                "beacon_heard_by_player": False,
                "reported_position_nm": None,
                "reported_error_nm": None,
                "reported_at_s": None,
                "next_beacon_s": 0.0,
                "beacon_sequence": 0,
            }
            events.append({"type": "liferaft_deployed", "raft_id": incident["liferaft"]["raft_id"],
                           "target_vessel_id": vessel_id,
                           "callsign": incident["callsign"], "occupants": LIFERAFT_OCCUPANTS,
                           "position_nm": list(raft_pos)})
        self.incidents[vessel_id] = incident
        # Bound career payload growth without deleting active or recent incidents.
        if len(self.incidents) > MAX_RESCUE_INCIDENTS:
            terminal = [key for key, value in self.incidents.items()
                        if not self._has_active_survivors(value)]
            for key in terminal[:len(self.incidents) - MAX_RESCUE_INCIDENTS]:
                self.incidents.pop(key, None)
        return events

    @staticmethod
    def _has_active_survivors(incident: dict) -> bool:
        casualty = incident.get("casualty")
        raft = incident.get("liferaft")
        return bool((casualty and casualty.get("status") == "aboard")
                    or (raft and raft.get("status") == "afloat"))

    @property
    def has_active_survivors(self) -> bool:
        """Whether a casualty or liferaft remains tied to the current phase's scene."""
        return any(self._has_active_survivors(incident) for incident in self.incidents.values())

    def update(self, traffic, sim_time_s: float, *, sea_state: float = 0.0,
               sea_state_at=None, player_position_nm=None, radio_staffed: bool = False) -> list[dict]:
        """Register/age survivors and transmit uncertain raft beacon plots when heard.

        Beacon reception is gated by the staffed wireless and actual radio range. The
        player only receives a deterministic noisy fix; chart callers must use
        :meth:`reported_liferaft_targets`, never the raft's physical position.
        """
        try:
            now = float(sim_time_s)
            default_sea = max(0.0, min(1.5, float(sea_state)))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid survivor update time/weather") from exc
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("invalid survivor update time")
        player_pos = None if player_position_nm is None else _finite_pair(player_position_nm, "player radio position")
        # Game calls this service from its frame update; only scan the fleet and
        # age survivor targets once per simulation second, not once per rendered frame.
        if self.last_update_s is not None and now >= self.last_update_s and now - self.last_update_s < RESCUE_SURVIVOR_UPDATE_INTERVAL_S:
            return []
        self.last_update_s = now
        events: list[dict] = []
        for ship in traffic.ships.values():
            if bool(getattr(ship, "mayday_sent", False)):
                # Older saves without a survivor section should not retroactively
                # invent a new rescue asset for an already completed incident.
                status = str(getattr(ship, "distress_assistance_status", "none"))
                if status not in ("completed", "failed"):
                    events.extend(self.ensure_incident(ship, now))
        for vessel_id, incident in list(self.incidents.items()):
            casualty = incident.get("casualty")
            if casualty and casualty.get("status") == "aboard":
                dt = max(0.0, now - float(casualty.get("last_update_s", now)))
                if dt > 0.0:
                    target = traffic.by_id(vessel_id) if hasattr(traffic, "by_id") else None
                    local_sea = self._sample_sea(target, default_sea, sea_state_at)
                    casualty["remaining_s"] = max(0.0, float(casualty["remaining_s"]) - dt * (1.0 + max(0.0, local_sea - 0.45) * 0.35))
                    casualty["last_update_s"] = now
                    if casualty["remaining_s"] <= 0.0:
                        casualty["status"] = "lost"
                        self.survivors_lost += 1
                        events.append({"type": "casualty_lost", "survivor_id": casualty["survivor_id"],
                                       "target_vessel_id": vessel_id, "callsign": incident["callsign"]})
            raft = incident.get("liferaft")
            if raft and raft.get("status") == "afloat":
                dt = max(0.0, now - float(raft.get("last_update_s", now)))
                if dt > 0.0:
                    raft_pos = _finite_pair(raft["position_nm"], "liferaft position")
                    local_sea = self._sample_sea(SimpleNamespace(position_nm=raft_pos), default_sea, sea_state_at)
                    drift_speed = 0.0008 + 0.0026 * local_sea
                    heading = float(raft.get("drift_heading_rad", 0.0))
                    raft_pos = (raft_pos[0] + math.cos(heading) * drift_speed * dt,
                                raft_pos[1] + math.sin(heading) * drift_speed * dt)
                    raft["position_nm"] = list(raft_pos)
                    raft["remaining_s"] = max(0.0, float(raft["remaining_s"]) - dt * (1.0 + local_sea * 0.45))
                    raft["last_update_s"] = now
                    if raft["remaining_s"] <= 0.0:
                        raft["status"] = "lost"
                        lost = max(0, int(raft.get("occupants", 0)))
                        self.survivors_lost += lost
                        events.append({"type": "liferaft_survivors_lost", "raft_id": raft["raft_id"],
                                       "target_vessel_id": vessel_id, "callsign": incident["callsign"],
                                       "occupants": lost})
                # A raft locator only becomes a chart contact after this vessel's
                # radio watch actually receives it. Position error is persisted and
                # visible to the player as an uncertainty ring, not a hidden exact fix.
                if (raft.get("status") == "afloat" and bool(radio_staffed)
                        and player_pos is not None and now >= float(raft.get("next_beacon_s", 0.0))):
                    physical_pos = _finite_pair(raft["position_nm"], "liferaft position")
                    if _distance(player_pos, physical_pos) <= LIFERAFT_BEACON_RANGE_NM:
                        sequence = int(raft.get("beacon_sequence", 0)) + 1
                        rng = random.Random(stable_seed("liferaft-radio-plot", raft["raft_id"], sequence))
                        error_nm = rng.uniform(LIFERAFT_REPORT_ERROR_MIN_NM, LIFERAFT_REPORT_ERROR_MAX_NM)
                        error_angle = rng.random() * math.tau
                        report = (physical_pos[0] + math.cos(error_angle) * error_nm,
                                  physical_pos[1] + math.sin(error_angle) * error_nm)
                        first_report = not bool(raft.get("beacon_heard_by_player", False))
                        raft["beacon_heard_by_player"] = True
                        raft["reported_position_nm"] = list(report)
                        raft["reported_error_nm"] = error_nm
                        raft["reported_at_s"] = now
                        raft["next_beacon_s"] = now + LIFERAFT_BEACON_INTERVAL_S
                        raft["beacon_sequence"] = sequence
                        events.append({
                            "type": "liferaft_beacon_received" if first_report else "liferaft_beacon_updated",
                            "raft_id": raft["raft_id"], "target_vessel_id": vessel_id,
                            "callsign": incident["callsign"], "occupants": int(raft.get("occupants", 0)),
                            "sequence": sequence, "reported_position_nm": list(report),
                            "report_error_nm": error_nm, "reported_at_s": now,
                        })
        return events

    def reported_liferaft_targets(self, sim_time_s: float) -> list[dict]:
        """Return chart-safe reports for active rafts; never expose their physical fix."""
        now = float(sim_time_s)
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("invalid liferaft report clock")
        reports: list[dict] = []
        for vessel_id, incident in self.incidents.items():
            raft = incident.get("liferaft")
            if not raft or raft.get("status") != "afloat" or not raft.get("beacon_heard_by_player"):
                continue
            reported = raft.get("reported_position_nm")
            if reported is None:
                continue
            report_pos = _finite_pair(reported, "reported liferaft position")
            reported_at = raft.get("reported_at_s")
            if reported_at is None:
                continue
            age = max(0.0, now - float(reported_at))
            reports.append({
                "raft_id": str(raft["raft_id"]), "target_vessel_id": vessel_id,
                "callsign": str(incident.get("callsign", vessel_id)),
                "position_nm": report_pos, "report_error_nm": float(raft.get("reported_error_nm") or 0.0),
                "reported_at_s": float(reported_at), "age_s": age,
                "stale": age >= 180.0, "occupants": max(0, int(raft.get("occupants", 0))),
                "remaining_s": max(0.0, float(raft.get("remaining_s", 0.0))),
                "sequence": max(0, int(raft.get("beacon_sequence", 0))),
            })
        reports.sort(key=lambda item: (item["age_s"], item["raft_id"]))
        return reports

    @staticmethod
    def _sample_sea(subject, fallback: float, sea_state_at) -> float:
        if callable(sea_state_at):
            try:
                sample = float(sea_state_at(subject))
                if math.isfinite(sample):
                    return max(0.0, min(1.5, sample))
            except (TypeError, ValueError, AttributeError, ArithmeticError):
                pass
        return max(0.0, min(1.5, float(fallback)))

    def complete_assistance(self, vessel_id: str, mission_id: str,
                            responder_position_nm, sim_time_s: float) -> dict:
        """Transfer a living casualty and recover any liferaft physically within pickup range.

        Repeating the same mission completion is safe; the stable mission identity is
        stored on the incident so duplicate UI/controller transitions cannot double-count.
        """
        vessel_id = str(vessel_id)
        mission_id = str(mission_id)
        if not mission_id:
            raise ValueError("rescue mission ID is required for survivor transfer")
        now = float(sim_time_s)
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("invalid survivor transfer time")
        responder_pos = _finite_pair(responder_position_nm, "responder position")
        incident = self.incidents.get(vessel_id)
        result = {"casualties_transferred": 0, "liferafts_recovered": 0,
                  "liferaft_occupants_recovered": 0, "liferafts_left_adrift": 0,
                  "survivors_lost": 0}
        if incident is None:
            return result
        completed_ids = incident.setdefault("completed_mission_ids", [])
        if mission_id in completed_ids:
            return result
        completed_ids.append(mission_id)
        if len(completed_ids) > 32:
            del completed_ids[:-32]
        casualty = incident.get("casualty")
        if casualty and casualty.get("status") == "aboard":
            # Catch up this casualty's clock if completion happens before the next
            # scheduled registry update (e.g. immediately after loading a save).
            elapsed = max(0.0, now - float(casualty.get("last_update_s", now)))
            casualty["remaining_s"] = max(0.0, float(casualty["remaining_s"]) - elapsed)
            casualty["last_update_s"] = now
            if casualty["remaining_s"] > 0.0:
                casualty["status"] = "recovered"
                casualty["recovered_by"] = mission_id
                result["casualties_transferred"] += 1
                self.casualties_transferred += 1
            else:
                casualty["status"] = "lost"
                self.survivors_lost += 1
                result["survivors_lost"] += 1
        raft = incident.get("liferaft")
        if raft and raft.get("status") == "afloat":
            # Catch up a raft if completion follows loading a save before the next
            # registry tick. Game normally advances this each traffic update; this
            # guard prevents a stale raft from being rescued after its clock expired.
            raft_elapsed = max(0.0, now - float(raft.get("last_update_s", now)))
            if raft_elapsed > 0.0:
                raft_pos = _finite_pair(raft["position_nm"], "liferaft position")
                heading = float(raft.get("drift_heading_rad", 0.0))
                raft["position_nm"] = [raft_pos[0] + math.cos(heading) * 0.0008 * raft_elapsed,
                                       raft_pos[1] + math.sin(heading) * 0.0008 * raft_elapsed]
                raft["remaining_s"] = max(0.0, float(raft.get("remaining_s", 0.0)) - raft_elapsed)
                raft["last_update_s"] = now
            raft_pos = _finite_pair(raft["position_nm"], "liferaft position")
            distance = _distance(responder_pos, raft_pos)
            if distance <= LIFERAFT_PICKUP_RADIUS_NM and float(raft.get("remaining_s", 0.0)) > 0.0:
                raft["status"] = "recovered"
                raft["recovered_by"] = mission_id
                raft["recovered_s"] = now
                result["liferafts_recovered"] = 1
                result["liferaft_occupants_recovered"] = max(0, int(raft.get("occupants", 0)))
                self.liferaft_occupants_recovered += result["liferaft_occupants_recovered"]
            elif float(raft.get("remaining_s", 0.0)) <= 0.0:
                raft["status"] = "lost"
                lost = max(0, int(raft.get("occupants", 0)))
                self.survivors_lost += lost
                result["survivors_lost"] += lost
            else:
                result["liferafts_left_adrift"] = 1
        return result

    def snapshot(self) -> dict:
        return {"schema_version": RESCUE_SURVIVOR_SCHEMA_VERSION,
                "incidents": copy.deepcopy(self.incidents),
                "casualties_transferred": int(self.casualties_transferred),
                "liferaft_occupants_recovered": int(self.liferaft_occupants_recovered),
                "survivors_lost": int(self.survivors_lost),
                "last_update_s": self.last_update_s}

    @classmethod
    def validate_snapshot(cls, payload: Any) -> dict:
        if payload is None:
            return {"schema_version": RESCUE_SURVIVOR_SCHEMA_VERSION, "incidents": {},
                    "casualties_transferred": 0, "liferaft_occupants_recovered": 0,
                    "survivors_lost": 0, "last_update_s": None}
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != RESCUE_SURVIVOR_SCHEMA_VERSION:
            raise ValueError("unsupported rescue-survivor snapshot schema")
        incidents = payload.get("incidents")
        if not isinstance(incidents, dict) or len(incidents) > MAX_RESCUE_INCIDENTS:
            raise ValueError("invalid rescue-survivor incident map")
        clean_incidents: dict[str, dict[str, Any]] = {}
        casualty_statuses = {"aboard", "recovered", "lost"}
        raft_statuses = {"afloat", "recovered", "lost"}
        for key, raw in incidents.items():
            vessel_id = str(key).strip()
            if not vessel_id or len(vessel_id) > 220 or not isinstance(raw, dict):
                raise ValueError("invalid rescue-survivor incident identity")
            incident = copy.deepcopy(raw)
            if str(incident.get("vessel_id", "")) != vessel_id:
                raise ValueError("rescue-survivor parent identity mismatch")
            if not isinstance(incident.get("callsign"), str) or not incident["callsign"].strip():
                raise ValueError("invalid rescue-survivor callsign")
            try:
                started = float(incident.get("started_s", 0.0))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("invalid rescue-survivor start time") from exc
            if not math.isfinite(started) or started < 0.0:
                raise ValueError("invalid rescue-survivor start time")
            incident["started_s"] = started
            completed_ids = incident.get("completed_mission_ids", [])
            if not isinstance(completed_ids, list) or len(completed_ids) > 32 or any(not isinstance(v, str) or not v for v in completed_ids):
                raise ValueError("invalid rescue-survivor completion identities")
            casualty = incident.get("casualty")
            if casualty is not None:
                if not isinstance(casualty, dict) or not isinstance(casualty.get("survivor_id"), str):
                    raise ValueError("invalid casualty record")
                if casualty.get("status") not in casualty_statuses:
                    raise ValueError("invalid casualty status")
                try:
                    remaining = float(casualty.get("remaining_s"))
                    last_update = float(casualty.get("last_update_s"))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("invalid casualty clock") from exc
                if not math.isfinite(remaining) or remaining < 0.0 or not math.isfinite(last_update) or last_update < 0.0:
                    raise ValueError("invalid casualty clock")
                casualty["remaining_s"] = remaining
                casualty["last_update_s"] = last_update
            raft = incident.get("liferaft")
            if raft is not None:
                if not isinstance(raft, dict) or not isinstance(raft.get("raft_id"), str):
                    raise ValueError("invalid liferaft record")
                if raft.get("status") not in raft_statuses:
                    raise ValueError("invalid liferaft status")
                try:
                    raft["position_nm"] = list(_finite_pair(raft.get("position_nm"), "saved liferaft position"))
                    remaining = float(raft.get("remaining_s"))
                    last_update = float(raft.get("last_update_s"))
                    heading = float(raft.get("drift_heading_rad"))
                    occupants = int(raft.get("occupants"))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("invalid liferaft fields") from exc
                if (not math.isfinite(remaining) or remaining < 0.0 or not math.isfinite(last_update)
                        or last_update < 0.0 or not math.isfinite(heading) or occupants < 0 or occupants > 12):
                    raise ValueError("invalid liferaft fields")
                raft["remaining_s"] = remaining
                raft["last_update_s"] = last_update
                raft["drift_heading_rad"] = heading
                raft["occupants"] = occupants
                heard = bool(raft.get("beacon_heard_by_player", False))
                raw_report = raft.get("reported_position_nm")
                report_pos = None if raw_report is None else list(_finite_pair(raw_report, "saved liferaft report"))
                raw_error = raft.get("reported_error_nm")
                raw_reported_at = raft.get("reported_at_s")
                try:
                    report_error = None if raw_error is None else float(raw_error)
                    reported_at = None if raw_reported_at is None else float(raw_reported_at)
                    next_beacon = float(raft.get("next_beacon_s", last_update))
                    sequence = int(raft.get("beacon_sequence", 0))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("invalid liferaft beacon snapshot") from exc
                if (report_error is not None and (not math.isfinite(report_error) or report_error < 0.0)
                        or reported_at is not None and (not math.isfinite(reported_at) or reported_at < 0.0)
                        or not math.isfinite(next_beacon) or next_beacon < 0.0
                        or sequence < 0 or sequence > 1_000_000):
                    raise ValueError("invalid liferaft beacon snapshot")
                if heard and (report_pos is None or report_error is None or reported_at is None or sequence < 1):
                    raise ValueError("heard liferaft beacon is missing its reported fix")
                if not heard and report_pos is not None:
                    raise ValueError("unheard liferaft beacon must not expose a chart report")
                raft["beacon_heard_by_player"] = heard
                raft["reported_position_nm"] = report_pos
                raft["reported_error_nm"] = report_error
                raft["reported_at_s"] = reported_at
                raft["next_beacon_s"] = next_beacon
                raft["beacon_sequence"] = sequence
            clean_incidents[vessel_id] = incident
        raw_last_update = payload.get("last_update_s")
        if raw_last_update is None:
            last_update = None
        else:
            try:
                last_update = float(raw_last_update)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("invalid rescue-survivor update clock") from exc
            if not math.isfinite(last_update) or last_update < 0.0:
                raise ValueError("invalid rescue-survivor update clock")
        counts = {}
        for key in ("casualties_transferred", "liferaft_occupants_recovered", "survivors_lost"):
            try:
                value = int(payload.get(key, 0))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("invalid rescue-survivor counter") from exc
            if value < 0:
                raise ValueError("invalid rescue-survivor counter")
            counts[key] = value
        return {"schema_version": RESCUE_SURVIVOR_SCHEMA_VERSION, "incidents": clean_incidents,
                "last_update_s": last_update, **counts}

    def restore(self, payload: Any) -> None:
        clean = self.validate_snapshot(payload)
        self.incidents = clean["incidents"]
        self.casualties_transferred = clean["casualties_transferred"]
        self.liferaft_occupants_recovered = clean["liferaft_occupants_recovered"]
        self.survivors_lost = clean["survivors_lost"]
        self.last_update_s = clean["last_update_s"]

    @classmethod
    def from_snapshot(cls, payload: Any) -> "RescueSurvivorRegistry":
        registry = cls()
        registry.restore(payload)
        return registry
