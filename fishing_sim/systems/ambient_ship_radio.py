"""Throttled, deterministic overheard ship-to-ship radio traffic for M11.

Ambient transmissions are background traffic, not direct hails. The director is
slot-based, preserves its cooldown state in career saves, and never consumes the
global random stream used by fishing or crew simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random

from fishing_sim.world.seeding import stable_seed
from fishing_sim.world.traffic import Activity, Archetype, TrafficWorld

AMBIENT_SLOT_SECONDS = 42.0          # ~1.68 in-game hours (600 sim sec/game day)
AMBIENT_MIN_GAP_SECONDS = 55.0      # no more than about one extra exchange / 2.2 game hours
AMBIENT_SOURCE_COOLDOWN_SECONDS = 150.0  # ~6 in-game hours per transmitting vessel
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AmbientTransmission:
    kind: str
    source_id: str
    contact_ids: tuple[str, ...]
    turns: tuple[tuple[float, str, str, str], ...]

    @property
    def source(self) -> str:
        return "ambient_ship_radio:%s:%s" % (self.kind, self.source_id)


class AmbientShipRadioDirector:
    """Generate occasional nearby radio chatter with bounded work and no spam."""

    def __init__(self, world_seed: int = 1962):
        self.world_seed = int(world_seed)
        self.last_slot: int | None = None
        self.last_emitted_at_s = -1e12
        self.last_by_vessel: dict[str, float] = {}
        self.emitted_count = 0
        self.skipped_busy_count = 0

    @staticmethod
    def _peer(ship) -> bool:
        return ship.archetype in (Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET)

    @staticmethod
    def _corporate(ship) -> bool:
        return ship.archetype in (Archetype.CORPORATE_CATCHER, Archetype.CORPORATE_LONGLINER)

    @staticmethod
    def _in_season(month: int | None, day: int | None) -> bool:
        if month is None or day is None:
            return False
        return ((int(month) > 5 or (int(month) == 5 and int(day) >= 20))
                and (int(month) < 8 or (int(month) == 8 and int(day) <= 10)))

    def _pick_pair(self, candidates, rng, sea_state: float = 0.35):
        peers = [s for s in candidates if self._peer(s) and s.activity != Activity.ANCHORED]
        corp = [s for s in candidates if self._corporate(s)]
        mothers = [s for s in candidates if s.archetype == Archetype.MOTHERSHIP]
        soviets = [s for s in candidates if s.archetype == Archetype.SOVIET_TRAWLER]
        coast = [s for s in candidates if s.archetype == Archetype.COAST_GUARD]

        def close_pairs(left, right=None, *, exclude_same=True):
            result = []
            right = left if right is None else right
            for a in left:
                for b in right:
                    if exclude_same and a.id == b.id:
                        continue
                    distance = math.hypot(a.position_nm[0] - b.position_nm[0],
                                          a.position_nm[1] - b.position_nm[1])
                    if distance <= min(float(a.radio_range_nm), float(b.radio_range_nm)):
                        result.append((a, b))
            return result

        # Treaty-edge traffic is selected only if a Soviet contact is genuinely
        # near the 45N boundary and a second vessel is within both radios' range.
        # This is dormant in the current Phase A geometry, but ready for Phase B.
        treaty_y_nm = (45.0 - 41.8) * 60.0
        treaty_soviets = [s for s in soviets
                          if abs(float(s.position_nm[1]) - treaty_y_nm) <= 12.0]
        if treaty_soviets:
            others = [s for s in candidates if s.archetype != Archetype.SOVIET_TRAWLER]
            treaty_options = close_pairs(treaty_soviets, others)
            if treaty_options:
                return "treaty_edge", treaty_options[rng.randrange(len(treaty_options))]

        # A weather safety warning outranks flavor chatter only in genuinely poor seas.
        if float(sea_state) >= 0.66 and close_pairs(coast, peers):
            options = close_pairs(coast, peers)
            return "weather_warning", options[rng.randrange(len(options))]
        # Corporate coordination is overheard only when the catcher and mothership
        # are plausibly close enough to exchange a signal.
        options = close_pairs(corp, mothers)
        if options and rng.random() < 0.55:
            return "corporate_coordination", options[rng.randrange(len(options))]
        options = close_pairs(peers)
        if options:
            return "peer_exchange", options[rng.randrange(len(options))]
        # Fall back to a single nearby voice if two vessels are not mutually in range.
        if peers:
            return "peer_solo", (peers[rng.randrange(len(peers))],)
        if soviets:
            return "distant_traffic", (soviets[rng.randrange(len(soviets))],)
        if corp:
            return "corporate_routine", (corp[rng.randrange(len(corp))],)
        if coast:
            return "safety_broadcast", (coast[rng.randrange(len(coast))],)
        return None, ()

    def update(self, traffic: TrafficWorld, sim_time_s: float,
               player_position_nm: tuple[float, float], *, radio_staffed: bool,
               channel_busy: bool, radio_clarity: float = 0.75,
               sea_state: float = 0.35, hour: float | None = None,
               month: int | None = None, day: int | None = None,
               docked: bool = False) -> AmbientTransmission | None:
        now = max(0.0, float(sim_time_s))
        slot = int(now // AMBIENT_SLOT_SECONDS)
        if self.last_slot is None:
            self.last_slot = slot
            return None
        if slot <= self.last_slot:
            return None
        self.last_slot = slot  # failed/busy windows are consumed; never create a later backlog burst.
        if not radio_staffed:
            return None
        if channel_busy:
            self.skipped_busy_count += 1
            return None
        if now - self.last_emitted_at_s < AMBIENT_MIN_GAP_SECONDS:
            return None
        clarity = max(0.0, min(1.0, float(radio_clarity)))
        sea = max(0.0, min(1.0, float(sea_state)))
        if clarity < 0.22:
            return None

        game_hour = float(hour) % 24.0 if hour is not None else ((now % 600.0) / 600.0) * 24.0
        night = game_hour >= 22.0 or game_hour < 6.0
        in_season = self._in_season(month, day)
        # Lower chatter in bad static, but make weather/safety calls more likely.
        chance = 0.34 + (0.12 if night else 0.0) + (0.08 if in_season else -0.06)
        if sea >= 0.78:
            chance += 0.08
        elif sea >= 0.62:
            chance -= 0.03
        chance *= 0.55 + 0.45 * clarity
        chance = max(0.08, min(0.68, chance))
        rng = random.Random(stable_seed(self.world_seed, "ambient-radio-slot", slot))
        if rng.random() >= chance:
            return None

        # Port gossip is an explicit dockside-only traffic flavor; it can be heard
        # even if no fishing vessel happens to be within ship-to-ship range.
        if docked and rng.random() < 0.45:
            lines = (
                (0.0, "HAKODATE HARBOUR RADIO", "General traffic. Auction floor reports a cautious market this morning; quality and timing still decide the price. Over.", "radio"),
                (3.0, "KITA MARU", "Harbour Radio, KITA MARU. Copy. We'll get the catch iced and hear the clerk's figure before making plans. Out.", "radio"),
            )
            transmission = AmbientTransmission("port_gossip", "harbour-station", (), lines)
            self.last_by_vessel["harbour-station"] = now
            self.last_emitted_at_s = now
            self.emitted_count += 1
            return transmission

        candidates = [s for s in traffic.radio_candidates(player_position_nm)
                      if getattr(s, "runtime_kind", "scheduled") == "scheduled"
                      and now - self.last_by_vessel.get(s.id, -1e12) >= AMBIENT_SOURCE_COOLDOWN_SECONDS]
        if not candidates:
            return None
        kind, pair = self._pick_pair(candidates, rng, sea_state=sea)
        if not pair:
            return None
        a = pair[0]
        b = pair[1] if len(pair) > 1 else None
        if kind == "treaty_edge" and b is not None:
            turns = (
                (0.0, a.callsign, "%s, %s. We are working near the northern fishing boundary. Confirm your own fix before proceeding; our plot is approximate. Over." % (b.callsign, a.callsign), "radio"),
                (3.0, b.callsign, "%s, %s. Copy. We will check the chart and our own position. No intent to cross a line on a stale report. Out." % (a.callsign, b.callsign), "radio"),
            )
        elif kind == "weather_warning" and b is not None:
            # Weather lines are observational and cautious, not exact forecasts.
            turns = (
                (0.0, a.callsign, "%s, %s. Safety traffic. Sea building in our quarter; visibility is worsening. Secure loose gear and keep a listening watch. Over." % (b.callsign, a.callsign), "radio"),
                (3.0, b.callsign, "%s, %s. Roger. We'll watch the rail and take another look before setting. Out." % (a.callsign, b.callsign), "radio"),
            )
        elif kind == "corporate_coordination" and b is not None:
            catcher = a if self._corporate(a) else b
            mothership = b if catcher is a else a
            turns = (
                (0.0, catcher.callsign, "%s Control, %s. Working our assigned line; haul is delayed by the set. Request next report window. Over." % (mothership.callsign, catcher.callsign), "radio"),
                (3.0, mothership.callsign, "%s, Control. Acknowledged. Keep to the schedule and report at the next haul. Out." % catcher.callsign, "radio"),
            )
        elif kind == "peer_exchange" and b is not None:
            phrases = (
                ("Birds moving with the set, but no sure sign of a school. Over.", "Copy. We'll watch the water before laying gear. Out."),
                ("Current's turned since the last watch. Your old bearing may be no good now. Over.", "Roger. We'll take another fix and not chase a stale report. Out."),
                ("Saw a few birds westward. Could mean bait, could mean nothing. Over.", "Understood. A lead, not a promise. We'll keep our own eyes open. Out."),
                ("We've been hauling since afternoon. Not much time for a long call. Over.", "Copy. Finish your work; we'll clear the band. Out."),
            )
            first, second = phrases[rng.randrange(len(phrases))]
            turns = (
                (0.0, a.callsign, "%s, %s. %s" % (b.callsign, a.callsign, first), "radio"),
                (3.0, b.callsign, "%s, %s. %s" % (a.callsign, b.callsign, second), "radio"),
            )
        elif kind == "peer_solo":
            turns = ((0.0, a.callsign, "General traffic, general traffic. %s here. Working slowly tonight; birds are scattered, and this report is no promise of fish. Over." % a.callsign, "radio"),)
        elif kind == "distant_traffic":
            turns = ((0.0, a.callsign, "%s to traffic. We are holding our course and request other vessels keep clear of our working gear. Over." % a.callsign, "radio"),)
        elif kind == "safety_broadcast":
            turns = ((0.0, a.callsign, "Safety traffic from Coast Guard %s. Report danger to life or vessel immediately. Conditions can vary sharply across this area. Out." % a.callsign, "radio"),)
        else:
            turns = ((0.0, a.callsign, "%s, routine traffic. We are proceeding on schedule. Weather and grounds reports are local observations only. Out." % a.callsign, "radio"),)

        contact_ids = tuple(s.id for s in pair)
        for ship in pair:
            self.last_by_vessel[ship.id] = now
            # Hearing a callsign can establish identity but does not magically reveal
            # exact position. The plot is deliberately noisy and reported separately.
            plot_rng = random.Random(stable_seed(self.world_seed, "ambient-plot", ship.id, slot))
            ship.report_position(now, error_nm=plot_rng.uniform(1.2, 4.0), rng=plot_rng)
            traffic.mark_known(ship.id)
        self.last_emitted_at_s = now
        self.emitted_count += 1
        return AmbientTransmission(kind, a.id, contact_ids, turns)

    def snapshot(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "world_seed": self.world_seed,
                "last_slot": self.last_slot, "last_emitted_at_s": self.last_emitted_at_s,
                "last_by_vessel": dict(sorted(self.last_by_vessel.items())),
                "emitted_count": self.emitted_count, "skipped_busy_count": self.skipped_busy_count}

    def restore(self, snapshot: dict) -> None:
        if not isinstance(snapshot, dict) or int(snapshot.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError("unsupported ambient radio snapshot schema")
        if int(snapshot.get("world_seed", self.world_seed)) != self.world_seed:
            raise ValueError("ambient radio snapshot world seed mismatch")
        last_slot = snapshot.get("last_slot")
        if last_slot is not None and (isinstance(last_slot, bool) or not isinstance(last_slot, int)):
            raise ValueError("ambient radio last_slot must be an integer or null")
        emitted_at = float(snapshot.get("last_emitted_at_s", -1e12))
        if not math.isfinite(emitted_at):
            raise ValueError("ambient radio timestamp must be finite")
        by_vessel = snapshot.get("last_by_vessel", {})
        if not isinstance(by_vessel, dict) or len(by_vessel) > 5000:
            raise ValueError("ambient radio cooldowns must be a bounded mapping")
        clean = {}
        for vessel_id, timestamp in by_vessel.items():
            if not isinstance(vessel_id, str) or not vessel_id:
                raise ValueError("invalid ambient radio cooldown entry")
            value = float(timestamp)
            if not math.isfinite(value) or value < 0:
                raise ValueError("invalid ambient radio cooldown entry")
            clean[vessel_id] = value
        self.last_slot = last_slot
        self.last_emitted_at_s = emitted_at
        self.last_by_vessel = clean
        self.emitted_count = max(0, int(snapshot.get("emitted_count", 0)))
        self.skipped_busy_count = max(0, int(snapshot.get("skipped_busy_count", 0)))
