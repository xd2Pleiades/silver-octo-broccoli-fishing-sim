"""Vacuum-tube AM/SSB radio model for the 1962 fishing vessel."""
from __future__ import annotations

import random

RADIO_MAX_RANGE_NM = 120.0
RADIO_NOISE_FLOOR = 0.15


class RadioSystem:
    """Distance-attenuated radio facade integrated with the game's existing call queue.

    The game retains its asynchronous reply/tow simulation; this object centralizes
    instrument state and provides a small, testable API for signal-dependent actions.
    """

    def __init__(self, game):
        self.game = game
        self.frequency_khz = 2182
        self.signal_quality = 1.0
        self.last_bulletin = ""
        self.tow_called = False
        # Legacy single-line poll remains for compatibility/tests. The game uses the
        # sparse timed-conversation poll below, where silence is the default.
        self.broadcast_timer = random.uniform(24.0, 48.0)
        self.conversation_timer = random.uniform(95.0, 165.0)
        self.distress_checked = False  # at most one 5% Mayday roll per offshore session
        self.panpan_checked = False    # at most one 10% Pan-pan roll per offshore session
        self.broadcasts_received = 0
        self.broadcasts_missed = 0

    def update(self, dt=0.0):
        # The map's design units are calibrated to the legacy radio ranges (~43.3
        # design units per nautical mile), rather than pretending pixels are miles.
        distance_units = float(self.game.world.dist())
        distance_nm = distance_units / (5200.0 / 120.0)
        self.signal_quality = max(RADIO_NOISE_FLOOR, 1.0 - distance_nm / RADIO_MAX_RANGE_NM)
        return self.signal_quality


    def poll_random_broadcast(self, dt, *, staffed, busy=False):
        """Return an incoming broadcast when due, or None if it should be skipped.

        Ambient transmissions are intentionally independent from F2/F3/F4 calls:
        they never assign a station owner, start a tow, change navigation, or join
        the outgoing radio-call queue. An unattended set misses the transmission.
        """
        self.broadcast_timer -= max(0.0, float(dt))
        if self.broadcast_timer > 0.0:
            return None

        if not staffed:
            self.broadcasts_missed += 1
            self.broadcast_timer = random.uniform(12.0, 25.0)
            return None
        if busy:
            # Don't overwrite a requested reply or an unread radio bubble.
            self.broadcast_timer = random.uniform(6.0, 13.0)
            return None

        message = self._compose_random_broadcast()
        self.last_bulletin = message
        self.broadcasts_received += 1
        self.broadcast_timer = random.uniform(28.0, 62.0)
        return message

    def _compose_random_broadcast(self):
        """Create plausible 1962 fishing-fleet/coast-station traffic for 2182 kHz."""
        self.update()
        g = self.game
        wx = g.weather
        world = g.world
        sea = float(getattr(world, "sea_state", 0.0))
        wind = int(wx.wind_kt())
        wind_dir = wx.wind_from()
        visibility = float(wx.visibility_km())
        market = float(getattr(g, "market", 1.0))
        hour_fn = getattr(world, "hour", None)
        hour = float(hour_fn()) if callable(hour_fn) else 12.0
        vessel = random.choice(("Kita Maru", "Shiranui Maru", "Hokusei Maru", "Taisei Maru",
                                "No. 8 Kuroshio", "Nisshin Maru"))
        fish = random.choice(("yellowfin", "albacore", "bigeye", "skipjack", "swordfish"))

        # Very weak reception is still represented as atmospheric radio traffic,
        # but should not pretend every distant call can be copied clearly.
        if self.signal_quality < 0.18 and random.random() < 0.72:
            return "Radio: [bursts of carrier, then static; distant transmission unreadable]"

        if wx.storm > 0.55 or wx.wind > 0.78:
            options = [
                "Radio: Coastal station weather warning — %s, wind %s at %d knots, sea state %.1f. Secure loose gear and keep clear of the rails." %
                (wx.label().lower(), wind_dir, wind, sea),
                "Radio: All fishing vessels, squall line reported in the outer grounds. Reduce speed if visibility or deck conditions deteriorate.",
                "Radio: %s to fleet traffic — heavy motion here; we are suspending work at the rail until the worst passes." % vessel,
            ]
        elif wx.fog > 0.45 or visibility < 2.0:
            options = [
                "Radio: Harbour control advises fog in the approaches, visibility about %.1f kilometres. Make sound signals and proceed with caution." % visibility,
                "Radio: %s calling any vessel in the grounds. Fog is thickening to the west; we have reduced speed and posted a lookout." % vessel,
                "Radio: Coastal station — patchy fog reported around the outer buoy line. Bearings may be unreliable in the haze.",
            ]
        else:
            options = [
                "Radio: %s reports a fair sign of %s in the eastern grounds; current setting south by southeast. No guarantee the fish will stay." %
                (vessel, fish),
                "Radio: Harbour market bulletin — buyer index now x%.2f. Handle and chill the catch promptly; quality still decides the price." % market,
                "Radio: %s to fleet traffic, radio check. We are heading back with a modest load; anyone working the northern grounds, answer if copied." % vessel,
                "Radio: Coastal station routine notice — keep a listening watch, check running lights after dusk, and report hazards to navigation.",
                "Radio: %s reports gear trouble and is making repairs at low speed. Traffic in the area is asked to give her room." % vessel,
                "Radio: Harbour control to outbound vessels — traffic is moving through the approaches. Keep clear of the channel and acknowledge if called.",
                "Radio: Fleet weather note — %s, wind %s at %d knots, visibility %.1f kilometres. Conditions can change quickly offshore." %
                (wx.label().lower(), wind_dir, wind, visibility),
                "Radio: Time signal — approximately %02d hundred hours. This is the coastal station maintaining the 2182-kilohertz watch." % int(hour),
                "Radio: %s to any fishing vessel nearby: we have seen birds working over a patch of water, but the shoal is moving." % vessel,
            ]
            # A rare, non-actionable snippet adds texture without taking control of
            # the ship or creating an automatic rescue/navigation event.
            if random.random() < 0.025:
                options.append("Radio: ...Mayday, Mayday... engine trouble... position follows... [static swallows the rest of the transmission]")
        return random.choice(options)


    def poll_random_conversation(self, dt, *, staffed, busy=False, docked=False, line_phase="off"):
        """Return a sparse, timed and attributed conversation dictionary, or None.

        Routine fleet traffic is deliberately infrequent. A distress roll is made only
        once per offshore session; Mayday traffic is critical priority and never starts
        an automatic rescue or changes navigation.
        """
        self.conversation_timer -= max(0.0, float(dt))
        if self.conversation_timer > 0.0:
            return None
        if busy:
            # Defer, rather than drop, routine traffic while a call or conversation is read.
            self.conversation_timer = random.uniform(24.0, 48.0)
            return None

        self.update()
        g = self.game
        wx = g.weather
        world = g.world
        sea = float(getattr(world, "sea_state", 0.0))
        wind = int(wx.wind_kt())
        wind_dir = wx.wind_from()
        visibility = float(wx.visibility_km())
        vessel = random.choice(("Tenyo Maru", "Kōzu Maru", "Shinwa Maru", "Hokusei Maru"))
        player_vessel = "Kōei Maru"

        # Quay voices do not require a wireless operator. Keep gossip to a few lines,
        # and only allow it during a docked visit.
        if docked and int(getattr(g, "broadcast_harbour_gossip_count", 0)) < 3 and random.random() < 0.62:
            gossip = random.choice((
                [
                    (0.0, "Quay hand", "Ahoy, Kōei Maru! Catch looking good?", "harbour"),
                    (3.0, "Deck", "Good enough. Is the ice house still open?", "harbour"),
                    (3.5, "Quay hand", "Till six. The Ginza buyer is asking after good yellowfin today.", "harbour"),
                ],
                [
                    (0.0, "Tenyo crew", "We got the bigeye first. Twenty kilos. Beat that.", "harbour"),
                    (3.0, "Takeda", "There's more bigeye in the sea than on your deck. Give us a week.", "harbour"),
                ],
                [
                    (0.0, "Quay hand", "Careful out there. The Mizuho Maru lost a man last month.", "harbour"),
                    (3.5, "Deck", "We'll keep a sharp lookout. Thank you.", "harbour"),
                ],
                [
                    (0.0, "Quay hand", "The Ginza chef, Kuroda-san, wants to know what you're bringing tomorrow.", "harbour"),
                    (3.0, "Deck", "Tell him to come to the auction house after first light.", "harbour"),
                ],
                [
                    (0.0, "Harbour master", "Port notice. All incoming boats report for the usual inspection before unloading.", "harbour"),
                    (3.0, "Captain Ishida", "Understood. We will report before the catch goes ashore.", "harbour"),
                ],
            ))
            self.conversation_timer = random.uniform(105.0, 185.0)
            self.broadcasts_received += 1
            g.broadcast_harbour_gossip_count = int(getattr(g, "broadcast_harbour_gossip_count", 0)) + 1
            return {"lines": gossip, "priority": 1, "source": "harbour_gossip"}

        if not staffed:
            self.broadcasts_missed += 1
            self.conversation_timer = random.uniform(95.0, 170.0)
            return None

        # A Mayday is a rare one-time roll per offshore session, not an ambient regular.
        offshore = int(getattr(world, "zone", 0)) > 0
        if offshore and not self.distress_checked:
            self.distress_checked = True
            if random.random() < 0.05:
                lines = [
                    (0.0, "SHINWA MARU", "Mayday, Mayday, Mayday. This is Shinwa Maru. We are sinking. Position two-six by zero-nine. Six men aboard. Over.", "radio"),
                    (4.5, "COAST STATION", "Shinwa Maru, this is coast station. Received your Mayday. Rescue vessels are being alerted. What is your condition? Over.", "radio"),
                    (5.0, "SHINWA MARU", "Coast station, Shinwa Maru. Taking water fast. Engine swamped. We are abandoning. Over.", "radio"),
                    (4.5, "COAST STATION", "Shinwa Maru, coast station. Understood. Keep transmitting for as long as you can. Out.", "radio"),
                    (6.0, "COAST STATION", "All vessels, all vessels. Distress traffic on two-one-eight-two. Shinwa Maru sinking, position two-six by zero-nine. Any vessel able to assist, acknowledge. Out.", "radio"),
                ]
                self.conversation_timer = random.uniform(150.0, 240.0)
                self.broadcasts_received += 1
                return {"lines": lines, "priority": 4, "source": "mayday"}

        if offshore and not self.panpan_checked:
            self.panpan_checked = True
            if random.random() < 0.10:
                lines = [
                    (0.0, "TENYO MARU", "Pan-pan, Pan-pan, Pan-pan. This is Tenyo Maru. Engine failure; we are drifting in the outer grounds. Request tow. No immediate danger. Over.", "radio"),
                    (4.0, "COAST STATION", "Tenyo Maru, coast station. Pan-pan received. State your position and number of persons aboard. Over.", "radio"),
                    (4.0, "TENYO MARU", "Position two-five by zero-eight. Six men aboard. We are keeping clear of the rail. Over.", "radio"),
                ]
                self.conversation_timer = random.uniform(150.0, 240.0)
                self.broadcasts_received += 1
                return {"lines": lines, "priority": 3, "source": "panpan"}

        # Very poor signal yields broken carrier rather than perfectly intelligible traffic.
        if self.signal_quality < 0.20 and random.random() < 0.65:
            lines = [
                (0.0, "RADIO STATIC", "...carrier... vessel calling...", "radio"),
                (3.0, "RADIO STATIC", "...say again... [static swallows the rest of the transmission]", "radio"),
            ]
            self.conversation_timer = random.uniform(100.0, 190.0)
            self.broadcasts_received += 1
            return {"lines": lines, "priority": 1, "source": "faded_traffic"}

        if wx.storm > 0.55 or wx.wind > 0.78:
            options = [
                (3, "COAST STATION", "Weather warning. Wind %s at %d knots; sea state %.1f. Secure loose gear and keep clear of the rails. Over." % (wind_dir, wind, sea)),
                (4, "TENYO MARU", "Coast station, Tenyo Maru. Heavy motion here. We are suspending work at the rail until the worst passes. Over."),
                (3, "COAST STATION", "Tenyo Maru, roger. All vessels are advised to reduce speed if visibility or deck conditions deteriorate. Out."),
            ]
            priority = 3
            source = "weather_warning"
        elif wx.fog > 0.45 or visibility < 2.0:
            options = [
                (3, "COAST STATION", "Harbour control advises fog in the approaches, visibility about %.1f kilometres. Make sound signals and proceed with caution. Over." % visibility),
                (4, vessel.upper(), "%s calling any vessel in the grounds. Fog is thickening to the west. We have reduced speed and posted a lookout. Over." % vessel),
                (3, "COAST STATION", "Received. Keep a listening watch and report any hazard to navigation. Out."),
            ]
            priority = 2
            source = "fog_report"
        else:
            kind = random.choice(("position", "catch", "market", "navigation", "fleet", "cq", "time", "news", "weather_query", "race", "trade"))
            priority = 1
            source = kind
            if kind == "position":
                options = [
                    (0, vessel.upper(), "%s, this is %s. Position twenty-five by eight. We're on the yellowfin. Over." % (player_vessel, vessel)),
                    (3.5, "VESSEL", "%s, %s. Roger, thanks. Fishing has been fair to the east. Over." % (vessel, player_vessel)),
                    (4.0, vessel.upper(), "Understood. Keep a sharp lookout for the fleet. %s standing by." % vessel),
                ]
            elif kind == "catch":
                fish = random.choice(("yellowfin", "albacore", "bigeye"))
                other_fish = random.choice(("albacore", "skipjack", "yellowfin"))
                options = [
                    (0, vessel.upper(), "%s, how's the catch? We've only got four %s all morning. Over." % (player_vessel, other_fish)),
                    (3.5, "VESSEL", "%s: seven %s, two bigeye. Must be luck. Over." % (player_vessel, fish)),
                    (3.0, vessel.upper(), "Good work. We shall try farther east. %s out." % vessel),
                ]
            elif kind == "market":
                options = [
                    (0, "COAST STATION", "Harbour market report. Buyer index x%.2f. Handle and chill the catch promptly; grade still decides the price. Over." % float(getattr(g, "market", 1.0))),
                    (3.5, "VESSEL", "Roger, coast station. We will keep the fish properly iced. Out."),
                ]
            elif kind == "navigation":
                options = [
                    (0, vessel.upper(), "Navigational warning. Submerged object reported eight miles east of Kabura Island. Mariners exercise caution. Over."),
                    (3.5, "COAST STATION", "Warning received and entered. Keep clear of the reported position. Out."),
                ]
                priority = 2
            elif kind == "fleet":
                options = [
                    (0, "COAST STATION", "Fleet positions at noon: Tenyo Maru off Cape Erimo; Kōzu Maru on the grounds; Shinwa Maru returning. Out."),
                ]
            elif kind == "cq":
                options = [
                    (0, "COAST STATION", "CQ CQ CQ. This is coast station. Any vessel monitoring, report your position. Over."),
                    (3.0, vessel.upper(), "Coast station, this is %s. Position twenty-four by zero-seven. Standing by. Out." % vessel),
                ]
            elif kind == "time":
                hour_fn = getattr(world, "hour", None)
                hour = int(float(hour_fn()) if callable(hour_fn) else 14) % 24
                options = [
                    (0, "JJY TIME SIGNAL", "This is JJY. The time is %02d hundred hours. Out." % hour),
                ]
            elif kind == "news":
                options = [
                    (0, "COAST STATION", "Coastal bulletin. The Diet's budget sitting continues in Tokyo. Fishing vessels are reminded to keep the channel clear. Out."),
                ]
            else:
                options = [
                    (0, vessel.upper(), "Tenyo Maru, this is %s. We have lost the weather report. What is it doing to the south? Over." % player_vessel),
                    (3.5, "VESSEL", "Fog bank rolling in from the west. Wind dropping. Stand by for another report. Over."),
                    (3.5, vessel.upper(), "Roger. Thank you. %s out." % vessel),
                ]

        lines = [(float(delay), str(speaker), str(text), "radio") for delay, speaker, text in options]
        self.conversation_timer = random.uniform(105.0, 200.0)
        self.broadcasts_received += 1
        return {"lines": lines, "priority": priority, "source": source}

    def request_tow(self):
        self.update()
        if self.signal_quality < 0.2:
            return False, "Radio static... No response from coast station."
        accepted = self.game.radio_call("tow")
        if not accepted:
            return False, "Tow call was not accepted; check the radio message for details."
        self.tow_called = True
        return True, "Coast Guard call queued; awaiting acknowledgement."

    def fetch_weather_report(self):
        self.update()
        if self.signal_quality < 0.35:
            return "Crackling static... [Unable to decode marine forecast]"
        weather = self.game.weather
        if hasattr(weather, "forecast"):
            outlook = weather.forecast(4)[1:4]
            return "Three-day marine forecast: " + " ".join(item.radio_line() for item in outlook)
        return f"Forecast: {weather.label()}, sea state {self.game.world.sea_state:.2f}; winds variable."

    def fetch_market_report(self):
        self.update()
        if self.signal_quality < 0.35:
            return "Crackling static... [Unable to decode market report]"
        return f"Harbour market buyer index: x{self.game.market:.2f}."
