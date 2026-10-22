"""Deterministic, bounded trust decay and local gossip propagation for v13.2.

The system observes trust changes made by radio/distress systems, propagates small
rumours once through nearby independent gossip contacts, and slowly returns stale
relationships toward neutral. It never consumes global RNG and its baseline is saved
so loading a career cannot replay an old rumour.
"""
from __future__ import annotations

import math
import random
from typing import Any

from fishing_sim.world.seeding import stable_seed
from fishing_sim.world.traffic import AIShip, Archetype, TrafficWorld

RELATIONSHIP_SCHEMA_VERSION = 1
SIM_SECONDS_PER_GAME_DAY = 600.0
INDEPENDENT_ARCHETYPES = frozenset((Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET))
CORPORATE_ARCHETYPES = frozenset((Archetype.CORPORATE_CATCHER, Archetype.CORPORATE_LONGLINER, Archetype.MOTHERSHIP))
TRUST_DECAY_PER_DAY_INDEPENDENT = 0.01
TRUST_DECAY_PER_DAY_CORPORATE = 0.02
GOSSIP_RANGE_NM = 30.0
GOSSIP_MAX_RECIPIENTS = 2
GOSSIP_DELTA_RATIO = 0.20
GOSSIP_PROPAGATION_CHANCE = 0.45
MAX_TRACKED_VESSELS = 5000


def _clamp_trust(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


class RelationshipDynamics:
    """Apply passive relationship decay and one-hop independent-fleet gossip."""

    def __init__(self, world_seed: int = 1962):
        self.world_seed = int(world_seed)
        self.last_update_sim_s = 0.0
        self.last_seen_trust: dict[str, float] = {}
        self.gossip_events = 0
        self.gossip_relays = 0
        self.decayed_relationships = 0

    def seed_baseline(self, traffic: TrafficWorld, sim_time_s: float = 0.0) -> None:
        """Initialize tracking without interpreting existing state as new gossip."""
        self.last_seen_trust = {ship.id: _clamp_trust(ship.trust)
                                for ship in sorted(traffic.ships.values(), key=lambda item: item.id)}
        self.last_update_sim_s = max(0.0, float(sim_time_s))

    @staticmethod
    def _update_rival_flag(ship: AIShip) -> None:
        ship.is_rival = (ship.archetype in INDEPENDENT_ARCHETYPES and ship.trust < -0.2)

    def _apply_gossip(self, traffic: TrafficWorld, source: AIShip, delta: float,
                      now: float) -> list[dict[str, str]]:
        if (source.personality != "gossip" or source.archetype not in INDEPENDENT_ARCHETYPES
                or abs(delta) < 1e-8):
            return []
        # Query the shared spatial index, never scan or activate the full fleet.
        candidates = []
        for ship in traffic.nearby(source.position_nm, GOSSIP_RANGE_NM):
            if (ship.id == source.id or ship.runtime_kind != "scheduled"
                    or ship.archetype not in INDEPENDENT_ARCHETYPES):
                continue
            distance = math.hypot(ship.position_nm[0] - source.position_nm[0],
                                  ship.position_nm[1] - source.position_nm[1])
            candidates.append((distance, ship.id, ship))
        candidates.sort(key=lambda row: (row[0], row[1]))
        event_stamp = "%s|%.3f|%.5f|%d|%d" % (
            source.id, now, delta, source.contact_count, source.mayday_resolved)
        relayed: list[dict[str, str]] = []
        for _distance, _vessel_id, recipient in candidates:
            if len(relayed) >= GOSSIP_MAX_RECIPIENTS:
                break
            # Stable per event + recipient; no global PRNG perturbation and no save/load replay.
            roll = random.Random(stable_seed(self.world_seed, "fleet-gossip", event_stamp, recipient.id)).random()
            if roll >= GOSSIP_PROPAGATION_CHANCE:
                continue
            effect = delta * GOSSIP_DELTA_RATIO
            before = recipient.trust
            recipient.trust = _clamp_trust(recipient.trust + effect)
            if abs(recipient.trust - before) < 1e-12:
                continue
            self._update_rival_flag(recipient)
            relayed.append({"source_id": source.id, "source_callsign": source.callsign,
                            "target_id": recipient.id, "target_callsign": recipient.callsign,
                            "direction": "favorable" if effect > 0 else "unfavorable"})
        if relayed:
            self.gossip_events += 1
            self.gossip_relays += len(relayed)
        return relayed

    def advance(self, traffic: TrafficWorld, sim_time_s: float) -> tuple[dict[str, str], ...]:
        """Observe external trust changes, propagate gossip, decay stale links once.

        Trust decay is measured in game days (600 simulation seconds per day) and
        always moves toward neutral. Calling this repeatedly at the same timestamp
        is idempotent. Rewinding time reseeds the baseline instead of reverse-decaying.
        """
        now = float(sim_time_s)
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("relationship simulation time must be finite and nonnegative")
        if now < self.last_update_sim_s:
            self.seed_baseline(traffic, now)
            return ()
        if len(traffic.ships) > MAX_TRACKED_VESSELS:
            raise ValueError("relationship vessel set exceeds safety limit")
        ships = sorted(traffic.ships.values(), key=lambda item: item.id)
        changes: list[tuple[AIShip, float]] = []
        for ship in ships:
            current = _clamp_trust(ship.trust)
            ship.trust = current
            previous = self.last_seen_trust.get(ship.id)
            if previous is not None:
                delta = current - previous
                if abs(delta) > 1e-7:
                    changes.append((ship, delta))
            else:
                self.last_seen_trust[ship.id] = current

        rumours: list[dict[str, str]] = []
        for source, delta in changes:
            rumours.extend(self._apply_gossip(traffic, source, delta, now))

        elapsed = max(0.0, now - self.last_update_sim_s)
        if elapsed > 0.0:
            for ship in ships:
                trust = ship.trust
                if abs(trust) <= 1e-12:
                    continue
                rate = (TRUST_DECAY_PER_DAY_CORPORATE if ship.archetype in CORPORATE_ARCHETYPES
                        else TRUST_DECAY_PER_DAY_INDEPENDENT)
                contact_t = float(ship.last_contact_sim_time)
                decay_start = max(self.last_update_sim_s, contact_t) if contact_t >= 0.0 else self.last_update_sim_s
                decay_seconds = max(0.0, now - decay_start)
                amount = rate * decay_seconds / SIM_SECONDS_PER_GAME_DAY
                if amount <= 0.0:
                    continue
                if trust > 0.0:
                    ship.trust = max(0.0, trust - amount)
                else:
                    ship.trust = min(0.0, trust + amount)
                if abs(ship.trust - trust) > 1e-12:
                    self.decayed_relationships += 1
                    self._update_rival_flag(ship)

        self.last_update_sim_s = now
        # Record final values after both gossip and decay so effects cannot replay.
        self.last_seen_trust = {ship.id: _clamp_trust(ship.trust) for ship in ships}
        return tuple(rumours)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": RELATIONSHIP_SCHEMA_VERSION,
            "world_seed": self.world_seed,
            "last_update_sim_s": self.last_update_sim_s,
            "last_seen_trust": dict(sorted(self.last_seen_trust.items())),
            "gossip_events": self.gossip_events,
            "gossip_relays": self.gossip_relays,
            "decayed_relationships": self.decayed_relationships,
        }

    def restore(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != RELATIONSHIP_SCHEMA_VERSION:
            raise ValueError("unsupported relationship dynamics snapshot schema")
        if int(payload.get("world_seed", self.world_seed)) != self.world_seed:
            raise ValueError("relationship snapshot world seed mismatch")
        last_time = float(payload.get("last_update_sim_s", 0.0))
        raw_trust = payload.get("last_seen_trust", {})
        if not math.isfinite(last_time) or last_time < 0.0:
            raise ValueError("invalid relationship update time")
        if not isinstance(raw_trust, dict) or len(raw_trust) > MAX_TRACKED_VESSELS:
            raise ValueError("relationship baseline must be a bounded mapping")
        clean: dict[str, float] = {}
        for vessel_id, value in raw_trust.items():
            if not isinstance(vessel_id, str) or not vessel_id:
                raise ValueError("invalid relationship vessel ID")
            trust = float(value)
            if not math.isfinite(trust) or not -1.0 <= trust <= 1.0:
                raise ValueError("invalid relationship trust value")
            clean[vessel_id] = trust
        counters = []
        for key in ("gossip_events", "gossip_relays", "decayed_relationships"):
            value = int(payload.get(key, 0))
            if value < 0:
                raise ValueError("invalid relationship counter")
            counters.append(value)
        self.last_update_sim_s = last_time
        self.last_seen_trust = clean
        self.gossip_events, self.gossip_relays, self.decayed_relationships = counters

    @classmethod
    def from_snapshot(cls, payload: dict[str, Any]) -> "RelationshipDynamics":
        instance = cls(world_seed=int(payload.get("world_seed", 1962)))
        instance.restore(payload)
        return instance
