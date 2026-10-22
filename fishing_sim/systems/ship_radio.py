"""Radio intent and information-policy foundation for AI vessels (v13.2.01).

This system compiles one routine broadcast exchange; the existing BroadcastDirector
continues to own timing, interruption, display, and Notebook logging.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import random
from typing import Iterable

from fishing_sim.world.seeding import stable_seed
from fishing_sim.world.traffic import AIShip, Activity, Archetype

RADIO_PRIORITY_ROUTINE = 2
RADIO_PRIORITY_SAFETY = 4
RADIO_TOPIC_COOLDOWN_SECONDS = 18.75  # 45 in-game minutes at 600 sim seconds per game day
RADIO_SERVICE_SCHEMA_VERSION = 1

@dataclass(frozen=True)
class RadioExchange:
    delivered: bool
    intent: str
    transmit_text: str
    turns: tuple[tuple[float, str, str, str], ...] = ()
    reason: str = ""
    reported_position_nm: tuple[float, float] | None = None


class ShipRadioService:
    def __init__(self, world_seed: int = 1962):
        self.world_seed = int(world_seed)
        # Keyed by stable vessel ID + topic. This throttles repetitive transmissions
        # without changing any fishing/crew RNG stream, and is included in career saves.
        self.last_topic_at: dict[str, float] = {}

    @staticmethod
    def _clock_modifier(ship: AIShip, sim_time_s: float, month: int | None = None,
                        day: int | None = None) -> float:
        hour = ((max(0.0, float(sim_time_s)) % 600.0) / 600.0) * 24.0
        night = hour >= 22.0 or hour < 6.0
        if ship.archetype == Archetype.COAST_GUARD:
            modifier = 0.055 if not night else -0.22
        elif ship.archetype in (Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET):
            modifier = 0.07 if night else -0.015
        elif ship.archetype in (Archetype.CORPORATE_CATCHER, Archetype.CORPORATE_LONGLINER):
            modifier = 0.025 if not night else -0.035
        elif ship.archetype == Archetype.MOTHERSHIP:
            modifier = 0.025 if not night else -0.06
        else:
            modifier = 0.0
        if month is not None and day is not None:
            in_season = ((int(month) > 5 or (int(month) == 5 and int(day) >= 20))
                         and (int(month) < 8 or (int(month) == 8 and int(day) <= 10)))
            if in_season and ship.archetype in (Archetype.CORPORATE_CATCHER, Archetype.MOTHERSHIP):
                modifier += 0.025
        return modifier

    def _cooldown_reason(self, ship: AIShip, topic: str, sim_time_s: float) -> str | None:
        now = max(0.0, float(sim_time_s))
        key = "%s|%s" % (ship.id, topic)
        previous = self.last_topic_at.get(key)
        if previous is not None and now - previous < RADIO_TOPIC_COOLDOWN_SECONDS:
            return "No fresh report yet; give the vessel another watch before repeating that query."
        self.last_topic_at[key] = now
        # Bound the map so a long career cannot accumulate unbounded topic keys.
        if len(self.last_topic_at) > 2000:
            cutoff = now - RADIO_TOPIC_COOLDOWN_SECONDS * 4.0
            self.last_topic_at = {k: v for k, v in self.last_topic_at.items() if v >= cutoff}
        return None

    def snapshot(self) -> dict:
        return {"schema_version": RADIO_SERVICE_SCHEMA_VERSION, "world_seed": self.world_seed,
                "last_topic_at": dict(sorted(self.last_topic_at.items()))}

    def restore(self, snapshot: dict) -> None:
        if not isinstance(snapshot, dict) or int(snapshot.get("schema_version", 0)) != RADIO_SERVICE_SCHEMA_VERSION:
            raise ValueError("unsupported ship-radio service snapshot schema")
        if int(snapshot.get("world_seed", self.world_seed)) != self.world_seed:
            raise ValueError("ship-radio snapshot world seed mismatch")
        raw = snapshot.get("last_topic_at", {})
        if not isinstance(raw, dict) or len(raw) > 2000:
            raise ValueError("ship-radio cooldown state must be a bounded mapping")
        clean = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not key or "|" not in key:
                raise ValueError("invalid ship-radio cooldown key")
            try:
                timestamp = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid ship-radio cooldown timestamp") from exc
            if not math.isfinite(timestamp) or timestamp < 0:
                raise ValueError("invalid ship-radio cooldown timestamp")
            clean[key] = timestamp
        self.last_topic_at = clean

    @staticmethod
    def can_hail(ship: AIShip, player_position_nm: tuple[float, float]) -> bool:
        return math.hypot(ship.position_nm[0] - player_position_nm[0],
                          ship.position_nm[1] - player_position_nm[1]) <= ship.radio_range_nm + 1e-9

    @staticmethod
    def eligible_intents(ship: AIShip) -> tuple[str, ...]:
        """Keep corporate decline, rival deception, and official safety distinct."""
        if ship.activity == Activity.HAULING:
            return ("short_ack", "weather_warning")
        if ship.archetype == Archetype.COAST_GUARD:
            return ("official_safety", "weather_warning")
        if ship.archetype == Archetype.SOVIET_TRAWLER:
            return ("refuse_contact", "weather_warning")
        if ship.archetype in (Archetype.CORPORATE_CATCHER, Archetype.CORPORATE_LONGLINER):
            return ("grounds_declined", "weather_warning", "hail_familiar")
        if ship.archetype == Archetype.MOTHERSHIP:
            return ("grounds_declined", "weather_warning", "official_safety")
        intents = ["hail_stranger" if ship.contact_count == 0 else "hail_familiar", "peer_exchange"]
        if ship.personality in ("cooperative", "gossip") and ship.trust >= 0.4:
            intents.append("grounds_report_honest")
        if ship.personality == "competitive" and ship.trust < 0.3 and not ship.is_rival:
            # Low-trust rivals can misdirect, but this first routine call only selects it
            # as one possible response; it never changes physical fish ecology.
            intents.append("grounds_misdirect")
        if ship.is_rival:
            intents.append("refuse_contact")
        intents.append("weather_warning")
        return tuple(intents)

    @staticmethod
    def _weather_phrase(sea_state: float, weather_phrase: str | None) -> str:
        if weather_phrase:
            return str(weather_phrase).strip().lower()
        if sea_state >= 0.76:
            return "heavy swell and poor working conditions"
        if sea_state >= 0.58:
            return "a building sea"
        if sea_state >= 0.38:
            return "a moderate sea"
        return "fair conditions"

    def hail_any(self, ships: Iterable[AIShip], **kwargs) -> tuple[AIShip | None, RadioExchange]:
        """Try the broadcast against listeners in deterministic distance order.

        A silent/occupied listener does not block another vessel from answering.
        Return the first successful responder; if nobody replies, preserve the final
        listener outcome so the caller can distinguish range loss from silence.
        """
        last: RadioExchange | None = None
        for ship in ships:
            last = self.hail(ship, **kwargs)
            if last.delivered:
                return ship, last
        if last is not None:
            return None, last
        player_name = str(kwargs.get("player_name", "VESSEL"))
        player_port = str(kwargs.get("player_port", "unknown port"))
        tx = ("All stations, all stations. This is %s, independent longline out of %s. "
              "Any traffic in the vicinity, report general conditions and fishing activity. Over." %
              (player_name, player_port))
        return None, RadioExchange(False, "no_listeners", tx,
                                   reason="No vessel is within the set's radio range.")

    def hail(self, ship: AIShip, *, player_name: str, player_port: str,
             player_position_nm: tuple[float, float], sim_time_s: float,
             sea_state: float = 0.35, weather_phrase: str | None = None,
             responder_sea_state: float | None = None,
             responder_weather_phrase: str | None = None,
             radio_clarity: float = 0.75,
             month: int | None = None, day: int | None = None) -> RadioExchange:
        """Attempt a local ship-to-ship hail and return timed radio turns.

        Distance is checked against the vessel's physical position and configured
        radio fit. Replies remain uncertain, and the player only receives reported
        position data after a successful response.
        """
        distance = math.hypot(ship.position_nm[0] - player_position_nm[0],
                              ship.position_nm[1] - player_position_nm[1])
        tx = ("All stations, all stations. This is %s, independent longline out of %s. "
              "Any traffic in the vicinity, report general conditions and fishing activity. Over." %
              (player_name, player_port))
        if distance > ship.radio_range_nm:
            return RadioExchange(False, "out_of_range", tx, reason="No vessel within the set's radio range.")
        cooldown_reason = self._cooldown_reason(ship, "hail", sim_time_s)
        if cooldown_reason:
            return RadioExchange(False, "cooldown", tx, reason=cooldown_reason)
        ship.contact_attempts += 1
        # Per-attempt stream is deterministic and independent of weather/hotspot/fleet streams.
        rng = random.Random(stable_seed(self.world_seed, "radio-hail", ship.id,
                                        ship.contact_attempts, int(max(0.0, sim_time_s) // 15.0)))
        clarity = max(0.0, min(1.0, float(radio_clarity)))
        sea = max(0.0, min(1.0, float(sea_state)))
        range_factor = distance / max(1e-6, ship.radio_range_nm)
        response_chance = max(0.10, min(0.94, 0.88 - 0.28 * range_factor - 0.28 * sea
                                        - 0.22 * (1.0 - clarity)
                                        + self._clock_modifier(ship, sim_time_s, month, day)))
        if not rng.random() < response_chance:
            return RadioExchange(False, "no_reply", tx, reason="Carrier fades; nobody answers the hail.")

        remote_sea = sea if responder_sea_state is None else max(0.0, min(1.0, float(responder_sea_state)))
        weather = self._weather_phrase(remote_sea, responder_weather_phrase or weather_phrase)
        eligible = self.eligible_intents(ship)
        # Weather/safety information is universally shareable and gets priority when either
        # end of the link reports hazardous seas. Radio reception still uses player-side sea.
        if max(sea, remote_sea) >= 0.68 and "weather_warning" in eligible:
            intent = "weather_warning"
        else:
            # Stable weighted choice without a global random draw.
            intent = eligible[rng.randrange(len(eligible))]
        if ship.activity == Activity.HAULING and intent != "weather_warning":
            intent = "short_ack"

        if intent == "hail_stranger":
            reply = ("%s, %s. New voice on the band. We're an independent longliner working out of %s. "
                     "What have you got for conditions? Over." % (player_name, ship.callsign, ship.home_port))
            player = ("%s, %s. Light catch so far. We're checking traffic and weather. Any birds or signs worth noting? Over." %
                      (ship.callsign, player_name))
            closer = ("Copy, %s. Birds moving with the set; don't make a long run on one report. "
                      "%s out." % (player_name, ship.callsign))
        elif intent == "hail_familiar":
            reply = ("%s, %s. Back on the band, then. We're %s at present. Over." %
                     (player_name, ship.callsign, ship.activity.value.replace("_", " ")))
            player = ("%s, %s. Acknowledged. How are conditions in your quarter? Over." % (ship.callsign, player_name))
            closer = ("Sea's %s. Check again before you set gear. %s out." % (weather, ship.callsign))
        elif intent == "peer_exchange":
            reply = ("%s, %s. Independent boat. We're %s and watching the birds. Over." %
                     (player_name, ship.callsign, ship.activity.value.replace("_", " ")))
            player = ("%s, %s. Any fish sign or weather change? Over." % (ship.callsign, player_name))
            closer = ("Nothing certain. Current's the thing to watch; the report is only a report. Out." )
        elif intent == "grounds_report_honest":
            reply = ("%s, %s. We've seen scattered birds working west of our last line. "
                     "Could be worth a look, but no promise of fish. Over." % (player_name, ship.callsign))
            player = ("%s, %s. Roger. We'll treat that as a lead, not a fix. Out." % (ship.callsign, player_name))
            closer = None
        elif intent == "grounds_misdirect":
            reply = ("%s, %s. Try the eastern bank; we heard there was a load there this morning. Over." %
                     (player_name, ship.callsign))
            player = ("%s, %s. Copy. We'll make our own observation before setting. Out." % (ship.callsign, player_name))
            closer = None
        elif intent == "grounds_declined":
            reply = ("%s, %s. We're operating under company schedule. Grounds information is company business; "
                     "can't say. The %s is %s here. Over." % (player_name, ship.callsign, "weather", weather))
            player = ("%s, %s. Understood. Thank you for the weather report. Out." % (ship.callsign, player_name))
            closer = None
        elif intent == "weather_warning":
            reply = ("%s, %s. Warning to traffic nearby: %s. We're reducing speed and securing loose gear. "
                     "Recommend you do the same. Over." % (player_name, ship.callsign, weather.capitalize()))
            player = ("%s, %s. Roger the warning. We'll secure the deck and keep clear of the rail. Out." %
                      (ship.callsign, player_name))
            closer = None
        elif intent == "official_safety":
            reply = ("%s, Coast Guard %s. We copy. Keep a listening watch and report any danger to life or vessel. "
                     "Conditions are %s. Over." % (player_name, ship.callsign, weather))
            player = ("Coast Guard %s, %s. Received and understood. Out." % (ship.callsign, player_name))
            closer = None
        elif intent == "refuse_contact":
            reply = ("%s, %s. State your business or clear the frequency. We have no grounds report for you. Over." %
                     (player_name, ship.callsign))
            player = ("%s, %s. Routine call only. We will clear the frequency. Out." % (ship.callsign, player_name))
            closer = None
        else:  # hauling's short response
            reply = ("%s, %s. We're hauling and can't talk long. Sea is %s. Acknowledge and clear. Out." %
                     (player_name, ship.callsign, weather))
            player = ("%s, %s. Roger. Clear of the frequency. Out." % (ship.callsign, player_name))
            closer = None

        # Acknowledge successful contact exactly once. Corporate does not gain access to
        # the rival misdirection path, and official safety remains truthful by policy.
        ship.contact_count += 1
        ship.last_contact_sim_time = max(0.0, float(sim_time_s))
        ship.trust = max(-1.0, min(1.0, ship.trust + (0.02 if ship.personality == "corporate" else 0.05)))
        if ship.archetype in (Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET):
            ship.is_rival = ship.trust < -0.2
        report_rng = random.Random(stable_seed(self.world_seed, "radio-report", ship.id,
                                               ship.contact_count, int(sim_time_s // 15.0)))
        error = report_rng.uniform(0.7, 2.0) * (1.0 - min(0.9, max(0.0, ship.trust)) * 0.35)
        ship.report_position(sim_time_s, error_nm=error, rng=report_rng)
        turns: list[tuple[float, str, str, str]] = [
            (0.0, ship.callsign, reply, "radio"),
            (3.0, player_name.upper(), player, "radio"),
        ]
        if closer:
            turns.append((2.4, ship.callsign, closer, "radio"))
        return RadioExchange(True, intent, tx, tuple(turns), reported_position_nm=ship.last_reported_position_nm)

    def interact(self, ship: AIShip, topic: str, *, player_name: str,
                 player_port: str, player_position_nm: tuple[float, float],
                 sim_time_s: float, sea_state: float = 0.35,
                 weather_phrase: str | None = None,
                 responder_sea_state: float | None = None,
                 responder_weather_phrase: str | None = None,
                 radio_clarity: float = 0.75,
                 month: int | None = None, day: int | None = None) -> RadioExchange:
        """Ask one selected vessel a specific question through the radio UI.

        Replies are deliberately claims: position reports use a separate reported
        plot, corporate vessels decline grounds questions, and no reply is a valid
        outcome. The deterministic per-contact stream doesn't perturb fishing RNG.
        """
        topic = str(topic or "hail").lower().strip()
        if topic == "hail":
            return self.hail(ship, player_name=player_name, player_port=player_port,
                             player_position_nm=player_position_nm, sim_time_s=sim_time_s,
                             sea_state=sea_state, weather_phrase=weather_phrase,
                             responder_sea_state=responder_sea_state,
                             responder_weather_phrase=responder_weather_phrase,
                             radio_clarity=radio_clarity, month=month, day=day)
        allowed = {"position", "weather", "activity", "grounds", "crew", "name"}
        if topic not in allowed:
            topic = "hail"
            return self.hail(ship, player_name=player_name, player_port=player_port,
                             player_position_nm=player_position_nm, sim_time_s=sim_time_s,
                             sea_state=sea_state, weather_phrase=weather_phrase,
                             responder_sea_state=responder_sea_state,
                             responder_weather_phrase=responder_weather_phrase,
                             radio_clarity=radio_clarity, month=month, day=day)

        distance = math.hypot(ship.position_nm[0] - player_position_nm[0],
                              ship.position_nm[1] - player_position_nm[1])
        tx_prompts = {
            "position": "Request your position, over.",
            "weather": "How are conditions in your quarter? Over.",
            "activity": "Report your present activity, over.",
            "grounds": "Any fishing sign or grounds worth a look? Over.",
            "crew": "How is your crew holding up? Over.",
            "name": "Confirm your vessel name and callsign, over.",
        }
        tx = "%s, %s. This is %s out of %s. %s" % (
            ship.callsign, ship.callsign, player_name, player_port, tx_prompts[topic])
        if distance > ship.radio_range_nm:
            return RadioExchange(False, "out_of_range", tx,
                                 reason="No answer; selected vessel is beyond the radio set's range.")
        cooldown_reason = self._cooldown_reason(ship, topic, sim_time_s)
        if cooldown_reason:
            return RadioExchange(False, "cooldown", tx, reason=cooldown_reason)
        ship.contact_attempts += 1
        rng = random.Random(stable_seed(self.world_seed, "radio-topic", ship.id, topic,
                                        ship.contact_attempts, int(max(0.0, sim_time_s) // 15.0)))
        clarity = max(0.0, min(1.0, float(radio_clarity)))
        sea = max(0.0, min(1.0, float(sea_state)))
        range_factor = distance / max(1e-6, ship.radio_range_nm)
        response_chance = max(0.18, min(0.96, 0.88 - 0.30 * range_factor
                                        - 0.25 * sea - 0.20 * (1.0 - clarity)
                                        + (0.05 if ship.contact_count else 0.0)
                                        + self._clock_modifier(ship, sim_time_s, month, day)))
        if rng.random() >= response_chance:
            return RadioExchange(False, "no_reply", tx,
                                 reason="Only a carrier and static answer the call.")

        remote_sea = sea if responder_sea_state is None else max(0.0, min(1.0, float(responder_sea_state)))
        weather = self._weather_phrase(remote_sea, responder_weather_phrase or weather_phrase)
        activity = ship.activity.value.replace("_", " ")
        if topic == "position":
            personality_error = 0.25 if ship.personality in ("official", "cooperative") else 1.2
            report_rng = random.Random(stable_seed(self.world_seed, "radio-ui-position", ship.id,
                                                   ship.contact_attempts, int(sim_time_s // 15.0)))
            ship.report_position(sim_time_s, error_nm=report_rng.uniform(0.03, personality_error), rng=report_rng)
            rx, ry = ship.last_reported_position_nm or ship.position_nm
            reply = ("Our plot has us %.1f nautical miles east and %.1f north of Hakodate. "
                     "That is our reported fix, not a fresh survey. Over." % (rx, ry))
            player = "Roger. We will mark that as your reported position. Out."
        elif topic == "weather":
            reply = "We have %s here. Conditions may differ where you are; keep watch on the sea. Over." % weather
            player = "Copy the weather report. We will use our own observations as well. Out."
        elif topic == "activity":
            reply = "At present we are %s. Our ability to talk may change when work comes up. Over." % activity
            player = "Roger. We will keep the frequency clear if you are working. Out."
        elif topic == "grounds":
            if ship.archetype in (Archetype.CORPORATE_CATCHER, Archetype.CORPORATE_LONGLINER,
                                  Archetype.MOTHERSHIP):
                reply = "Fishing grounds are company business. Can't give you a position. Weather is %s here. Over." % weather
            elif ship.personality == "competitive" and ship.trust < 0.4:
                reply = "Heard talk of fish to the east, maybe. Could be yesterday's news. Make your own observations. Over."
            elif ship.personality in ("cooperative", "gossip") and ship.trust >= 0.0:
                reply = "Birds have been working west of our last line. Patchy sign, no guarantee there are fish below. Over."
            else:
                reply = "Nothing I would stake a set on. The sign is too uncertain today. Over."
            player = "Understood. A report is a lead, not a promise. Out."
        elif topic == "crew":
            if ship.personality == "gossip":
                reply = "Crew are tired but in good spirits. We have had worse weather and poorer catches. Over."
            elif ship.personality == "hostile":
                reply = "Crew are fit for duty. That is all you need to know. Over."
            elif ship.personality == "corporate":
                reply = "Crew is on schedule and accounted for. We have our orders to keep. Over."
            else:
                reply = "All hands are well enough. We rotate the tired ones when the work allows. Over."
            player = "Good to hear. Keep them safe. Out."
        else:  # name / callsign
            reply = "This is %s, home port %s. You can call us %s on this frequency. Over." % (
                ship.name, ship.home_port, ship.callsign)
            player = "Copy, %s. We have your vessel noted. Out." % ship.callsign

        ship.contact_count += 1
        ship.last_contact_sim_time = max(0.0, float(sim_time_s))
        trust_step = 0.025 if ship.personality == "corporate" else 0.04
        ship.trust = max(-1.0, min(1.0, ship.trust + trust_step))
        if ship.archetype in (Archetype.INDEPENDENT_LONGLINE, Archetype.INDEPENDENT_GILLNET):
            ship.is_rival = ship.trust < -0.2
        if ship.last_reported_position_nm is None:
            report_rng = random.Random(stable_seed(self.world_seed, "radio-ui-report", ship.id,
                                                   ship.contact_count, int(sim_time_s // 15.0)))
            ship.report_position(sim_time_s, error_nm=report_rng.uniform(0.1, 1.0), rng=report_rng)
        turns = ((0.0, ship.callsign, reply, "radio"),
                 (2.0, player_name.upper(), player, "radio"))
        return RadioExchange(True, topic, tx, turns,
                             reported_position_nm=ship.last_reported_position_nm)

