"""Coarse MAYDAY events and player assistance decisions (v13.2.05 / M9).

This service deliberately does not require a vessel to be LOD-active or rendered.
The traffic spatial index can hear a scheduled ship at radio range even if the
sea renderer never drew it. It emits each vessel's MAYDAY once; the choice to
assist or ignore is applied idempotently and recorded on the shared AIShip.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Optional

from fishing_sim.world.seeding import stable_seed
from fishing_sim.world.traffic import AIShip, Activity, Archetype, TrafficWorld

DISTRESS_CHECK_INTERVAL_S = 30.0
MAX_ACTIVE_RESCUE_CONTACTS = 3
ASSIST_TRUST_DELTA = 0.40
IGNORE_TRUST_DELTA = -0.50

_DISTRESS_KINDS = (
    ("taking_water", "taking water over the rail"),
    ("engine_failure", "engine failure; no way on"),
    ("injury", "a serious crew injury"),
    ("gear_entanglement", "gear fouled around the propeller"),
)


@dataclass(frozen=True)
class DistressEvent:
    vessel_id: str
    callsign: str
    kind: str
    issue_text: str
    sim_time_s: float
    heard_by_player: bool
    reported_position_nm: tuple[float, float] | None

    @property
    def source(self) -> str:
        return "mayday:" + self.vessel_id

    def radio_turns(self) -> tuple[tuple[float, str, str, str], ...]:
        pos = self.reported_position_nm
        if pos is None:
            position_text = "position uncertain"
        else:
            position_text = "reported position %.1f nautical miles east and %.1f north of Hakodate" % pos
        return (
            (0.0, self.callsign,
             "Mayday, mayday, mayday. This is %s. We are reporting %s. Position is %s. Request assistance. Over." %
             (self.callsign, self.issue_text, position_text), "radio"),
            (3.4, "RADIO SET",
             "The carrier fades into static. No other station answers immediately.", "radio"),
        )


class DistressDispatcher:
    """Low-frequency, deterministic distress generation and one-shot responses."""

    def __init__(self, world_seed: int = 1962, interval_s: float = DISTRESS_CHECK_INTERVAL_S):
        self.world_seed = int(world_seed)
        self.interval_s = max(1.0, float(interval_s))
        self._last_slot: int | None = None
        self.events_emitted = 0
        self.decisions_applied = 0

    @staticmethod
    def _eligible_random_candidate(ship: AIShip) -> bool:
        if ship.runtime_kind != "scheduled" or ship.mayday_sent or ship.mayday_resolved:
            return False
        if ship.archetype == Archetype.COAST_GUARD:
            return False
        return ship.activity not in (Activity.ANCHORED, Activity.DISTRESSED)

    def _make_event(self, ship: AIShip, sim_time_s: float, *, kind: str,
                    radio_staffed: bool) -> DistressEvent:
        if ship.mayday_sent:
            raise ValueError("a vessel may transmit only one MAYDAY per distress incident")
        try:
            origin_activity = ship.activity_override or ship.activity
            ship.distress_origin_activity = Activity(origin_activity)
        except (ValueError, TypeError):
            ship.distress_origin_activity = Activity.TRANSIT
        ship.activity_override = Activity.DISTRESSED
        ship.distress_position_nm = (float(ship.position_nm[0]), float(ship.position_nm[1]))
        ship.position_override_nm = None
        ship.distress_assistance_status = "none"
        ship.distress_outcome = None
        ship.mayday_sent = True
        ship.mayday_resolved = False
        ship.distress_started_s = max(0.0, float(sim_time_s))
        ship.distress_kind = kind
        ship.distress_decision = None
        # A MAYDAY is only presented to the player if their wireless is manned at
        # the time it is transmitted. The source event remains one-shot either way.
        heard = bool(radio_staffed)
        report = None
        if heard:
            rng = random.Random(stable_seed(self.world_seed, "mayday-plot", ship.id,
                                            int(max(0.0, sim_time_s) // self.interval_s)))
            error_nm = rng.uniform(0.25, 1.5)
            ship.report_position(sim_time_s, error_nm=error_nm, rng=rng)
            ship.mayday_player_heard = True
            ship.contact_count = max(0, int(ship.contact_count)) + 1
            ship.last_contact_sim_time = max(0.0, float(sim_time_s))
            report = ship.last_reported_position_nm
        else:
            ship.mayday_player_heard = False
        issue_text = next((text for code, text in _DISTRESS_KINDS if code == kind), _DISTRESS_KINDS[0][1])
        self.events_emitted += 1
        return DistressEvent(ship.id, ship.callsign, kind, issue_text,
                             max(0.0, float(sim_time_s)), heard, report)

    def trigger(self, ship: AIShip, sim_time_s: float, *, radio_staffed: bool = True,
                kind: str | None = None) -> DistressEvent | None:
        """Start a deterministic test/scenario distress; repeated calls are harmless."""
        if ship.mayday_sent or ship.mayday_resolved:
            return None
        rng = random.Random(stable_seed(self.world_seed, "mayday-kind", ship.id,
                                        int(max(0.0, sim_time_s) // self.interval_s)))
        selected_kind = kind or _DISTRESS_KINDS[rng.randrange(len(_DISTRESS_KINDS))][0]
        if selected_kind not in {item[0] for item in _DISTRESS_KINDS}:
            raise ValueError("unsupported distress kind")
        return self._make_event(ship, sim_time_s, kind=selected_kind, radio_staffed=radio_staffed)

    def update(self, traffic: TrafficWorld, sim_time_s: float, player_position_nm: tuple[float, float],
               *, sea_state: float, radio_staffed: bool, sea_state_at=None) -> list[DistressEvent]:
        """Evaluate nearby radio listeners on fixed time slots; never scans on every frame.

        The spatial query includes coarse/non-rendered vessels. At most one new event
        is generated per check interval to keep emergency traffic important and sparse.
        """
        now = max(0.0, float(sim_time_s))
        slot = int(now // self.interval_s)
        if self._last_slot is None:
            self._last_slot = slot - 1
        if slot <= self._last_slot:
            return []
        # Bound catch-up work if the simulation clock jumps far forward.
        start_slot = max(self._last_slot + 1, slot - 119)
        self._last_slot = slot
        candidates = traffic.radio_candidates(player_position_nm)
        candidates.sort(key=lambda s: (math.hypot(s.position_nm[0] - player_position_nm[0],
                                                  s.position_nm[1] - player_position_nm[1]), s.id))
        sea = max(0.0, min(1.5, float(sea_state)))
        # Sample each remote cell at most once per dispatch tick. Weather lookup is
        # spatial, but never repeated per rendered frame and never consumes live RNG.
        remote_sea = {}
        if sea_state_at is not None:
            for ship in candidates:
                try:
                    remote_sea[ship.id] = max(0.0, min(1.5, float(sea_state_at(ship))))
                except (TypeError, ValueError, AttributeError):
                    remote_sea[ship.id] = sea
        else:
            remote_sea = {ship.id: sea for ship in candidates}
        for check_slot in range(start_slot, slot + 1):
            for ship in candidates:
                if ship.runtime_kind != "scheduled" or ship.mayday_sent or ship.mayday_resolved:
                    continue
                # Authored distress overrides (e.g. a scenario or future schedule) are
                # dispatched once they enter radio range. Otherwise generate a rare
                # incident; storms and hauling increase, but never guarantee, the risk.
                authored = ship.activity_override == Activity.DISTRESSED or ship.activity == Activity.DISTRESSED
                if not authored and not self._eligible_random_candidate(ship):
                    continue
                rng = random.Random(stable_seed(self.world_seed, "mayday-event", ship.id, check_slot))
                ship_sea = remote_sea.get(ship.id, sea)
                chance = min(0.02, 0.00012 + 0.0012 * min(1.0, ship_sea)
                             + (0.00035 if ship.activity == Activity.HAULING else 0.0))
                if not authored and rng.random() >= chance:
                    continue
                # Make kind selection independent of the probability draw.
                kind_rng = random.Random(stable_seed(self.world_seed, "mayday-kind", ship.id, check_slot))
                kind = _DISTRESS_KINDS[kind_rng.randrange(len(_DISTRESS_KINDS))][0]
                event = self._make_event(ship, now, kind=kind, radio_staffed=radio_staffed)
                if event.heard_by_player:
                    traffic.mark_known(ship.id)
                    traffic.promote_rescue_contact(ship.id)
                return [event]
        return []

    def decide(self, ship: AIShip, decision: str, sim_time_s: float) -> tuple[bool, str]:
        """Apply assist/ignore relationship effect once. Returns (applied, status)."""
        decision = str(decision).strip().lower()
        if decision not in ("assist", "ignore"):
            raise ValueError("decision must be 'assist' or 'ignore'")
        if not ship.mayday_sent or not ship.mayday_player_heard:
            return False, "No received MAYDAY is available for this vessel."
        if ship.mayday_resolved or ship.distress_decision is not None:
            return False, "This MAYDAY already has a recorded player decision."
        delta = ASSIST_TRUST_DELTA if decision == "assist" else IGNORE_TRUST_DELTA
        ship.trust = max(-1.0, min(1.0, float(ship.trust) + delta))
        ship.distress_decision = decision
        ship.mayday_resolved = True  # decision is resolved; the physical mission has its own state.
        ship.distress_assistance_status = "awaiting_dispatch" if decision == "assist" else "ignored"
        ship.last_contact_sim_time = max(0.0, float(sim_time_s))
        ship.is_rival = (ship.archetype in (Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET)
                         and ship.trust < -0.2)
        self.decisions_applied += 1
        if decision == "assist":
            return True, "%s: assistance acknowledged. A rescue course can now be plotted to the reported position." % ship.callsign
        return True, "%s: you cleared the frequency without answering. The relationship consequence has been recorded." % ship.callsign
