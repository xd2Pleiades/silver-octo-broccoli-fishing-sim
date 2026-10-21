# Broadcast Conversations — Catalogue

A reference for every kind of voice that can be heard in the world: radio broadcasts, ship-to-ship transmissions, intercom calls, crew chatter on deck, harbour gossip, and distress traffic. Includes what exists today, what could be added, and concrete sample scripts.

Reference: `fishing_sim_11.py`. `Crew.say()`, `Game.radio_call()`, `Game._update_radio()`, `Weather.SAYS`, `Longline` stage messages.

---

## 1. What exists today

The game already has four broadcast channels, all one-way:

| Channel | Where | Example |
|---|---|---|
| **Crew speech bubbles** | `Crew.say()` | "Captain: Storm! Keep off the rails!" |
| **Radio coast-station** | `radio_call("weather" / "auction" / "tow")` | "Coast station reports overcast; wind NE 22 kt" |
| **Weather changes** | `Weather.SAYS` | "Fog's coming down. Keep an eye out for the buoys." |
| **Longline stage messages** | `Longline` internal | "A yellowfin on the line! Mind the brake." |

These are all **single lines** — no back-and-forth, no reply. They fire once and vanish into the speech bubble. That works, but the world is very quiet and every voice is a solo.

## 2. What a conversation needs

A "broadcast conversation" is different from a single line:

- **Multi-message** — two or three lines back-and-forth
- **Timed** — each line arrives 1.5–6 seconds after the previous, creating a rhythm
- **Attributed** — speaker changes on each line ("Coast Station: ...", "Captain: ...")
- **Interruptible** — a higher-priority call cuts off a lower one (a Mayday beats a weather forecast)
- **Reply-capable** (optional) — the player can pick a canned response

That's a new system — call it `Game._update_broadcast()` — managing a queue of `(delay, speaker, text)` entries and a "current conversation" state.

## 3. The channels, in detail

### 3.1 Coast station — one-way broadcasts

The coast station is the ship's link to shore. Range-limited (already modelled in `radio_call`), fog-faded, atmospheric. Currently three kinds exist; below is the full catalogue for the extended system.

| Type | Trigger | Priority | Sample |
|---|---|---|---|
| **Time signal** | Every game hour, on the hour | Low | "This is JJY. The time is fourteen hours, zero minutes, zero seconds." |
| **Weather report** | `F2` or auto on hour | Medium | "Coast station: overcast, wind northeast twenty-two knots, visibility six kilometres, sea moderate." |
| **Weather warning** | Event fires (typhoon, front) | High | "Typhoon warning. Typhoon 'Betty' expected to pass through the eastern grounds tonight. All vessels advised to seek shelter." |
| **Market report** | `F3` | Medium | "Harbour market report: yellowfin at twenty-two thousand, bigeye at thirty-eight. Sashimi-grade fetching a premium." |
| **Tow acknowledgement** | `F4` | High | "This is coast station. Vessel in tow request acknowledged. Launch departing in twenty minutes. Stand by on two-one-eight-two." |
| **Navigation warning** | Random | Medium | "Navigational warning: fishing vessel *Kōei Maru* reports a submerged object eight miles east of Kabura Island. Mariners exercise caution." |
| **Fleet position** | Random | Low | "Fleet positions at noon: *Tenyo Maru* off Cape Erimo. *Kōzu Maru* at the grounds. *Shinwa Maru* returning." |
| **News bulletin** | Event fires | Low | "News: the Diet has approved the fiscal budget. Emperor's health reported stable. The baseball season opens next week." |
| **Quarantine notice** | Docking | Low | "Port notice: all incoming vessels report to quarantine on arrival." |
| **CQ CQ (general call)** | Random | Low | "CQ CQ CQ, this is coast station. Any vessel monitoring, report your position." |

**Etiquette:** coast station broadcasts often begin with "CQ" (general) or the ship's name (specific). They always sign off with "out" or "standing by." The player's ship should have a name for two-way exchanges; recommend **Kōei Maru** (光栄丸, "ship of honour") or something similar 1960s-style.

### 3.2 Ship-to-ship — two-way radio (extended system)

Other boats in range. Range: 15–30 km of line-of-sight. Both vessels alternate in a conversation.

| Type | Trigger | Priority | Sample |
|---|---|---|---|
| **Position exchange** | Random (another boat on freq) | Low | "Kōei Maru, this is Tenyo Maru. Position twenty-five by eight. We're on the yellowfin. Over." / "Tenyo Maru, Kōei Maru, roger, thanks. Kōei standing by." |
| **Catch report** | After successful haul | Low | "Kōei Maru, what's your catch? We've only got four albacore all day." / "Kōei Maru: seven yellowfin, two bigeye. Must be luck. Over." |
| **Weather query** | In heavy weather | Medium | "Tenyo Maru, we've lost our weather forecast. What's it doing to the south?" / "Kōei Maru: fog bank rolling in from the west. Wind dropping. Stand by." |
| **Tow request (short range)** | Fishing boat in trouble | **High** | "Any vessel within twelve miles, this is Shinwa Maru. Our engine has gone. Request assistance. Over." / "Shinwa Maru, this is Kōei Maru, copy. We'll come alongside. Stand by." |
| **Race to port** | Both vessels heading same way | Low | "Kōei Maru, first one to the breakwater buys the sake." / "Tenyo Maru, you're on. Not with that engine you won't." |
| **Trade offer** | Rare | Low | "Kōei Maru, this is Tenyo Maru. I'll swap you two hundred metres of line for a tin of squid bait." |
| **Warnings** | After seeing something | Medium | "Vessel west of Kabura, this is Tenyo Maru. Submerged object two hundred metres to your starboard. Stand off." |

**Etiquette:** "over" means "I'm done speaking, please respond." "Out" means "end of transmission, no reply needed." "Roger" = acknowledged. "Wilco" = will comply. "Say again" = repeat. Saying the other ship's name at the start of each transmission is standard.

### 3.3 Intercom — internal ship calls

Not radio. The wheelhouse-to-engine-room voice pipe, the deck-to-bridge hand signals, and the shouting down the hatch. These are short, functional, and period-accurate.

| Type | Trigger | Priority | Sample |
|---|---|---|---|
| **Engine room report** | Every hour | Low | "Bridge, engine room. Temperature steady. Oil pressure holding at forty." |
| **Engine room query** | Bridge wants power | Medium | "Bridge to engine room. Give me a half ahead." / "Engine room: half ahead, aye." |
| **Engine room alert** | Warning condition | **High** | "Bridge, engine room! Cooling water pressure dropping. We need to slow." |
| **Deck report** | During hauling | Low | "Bridge, deck. Fish alongside. Do you want the boat held?" / "Bridge: hold her head to the swell. Over." |
| **Deck query** | Captain asks | Low | "Bridge to deck. How many this set?" / "Deck: eleven, four good size." |
| **Fishing report** | After each haul | Low | "Captain, deck. Twelve fish landed. Three sashimi-grade." |
| **Off-watch report** | Rest completion | Low | "Bridge, cabin. I'm awake. Where do you want me?" |
| **Alarm** | Any critical event | **Critical** | "Bridge! Fire in the galley! Bridge!" |

**Etiquette:** very short. Whoever calls states their station ("Bridge to engine room"), then the message. Responder repeats the action to confirm.

### 3.4 Crew chatter — deck voices

Small talk on watch. Not task-related. Gives texture to the deck between operations.

| Type | Trigger | Sample |
|---|---|---|
| **Veteran wisdom** | Random idle | "Takeda: The sea tells you where the fish are. You just have to look." |
| **Green hand anxiety** | Slip, storm, first haul | "Sato: The deck's moving under me." / "Takeda: Of course it's moving. You've got legs. Use them." |
| **Complaint** | After a long watch | "Yamamoto: Six hours in a swell and my hands won't close. Where's the cook?" |
| **Market interest** | After a sale | "Yamamoto: The chef at the Ginza — he said my yellowfin was the best he'd seen. Wouldn't stop talking about it." |
| **Superstition** | Random, near fishing | "Sato: Have you seen the captain's face? Yellowfin are thick today. Something's bound to go wrong." / "Kondo: Don't talk like that on a fishing boat. The sea's listening." |
| **Homelife** | Random, calm | "Mori: My daughter starts school next month. My wife says I should be home." / "Takeda: Then be home in a week. The fish will be here." |
| **Rival boats** | After a fleet event | "Kondo: The Tenyo Maru got twelve hundred yesterday. Twelve hundred! What are we doing wrong?" |
| **Weather complaint** | In storm | "Sato: I can't feel my fingers." / "Takeda: My fingers went in 1958. You'll get used to it." |
| **Rest compliment** | After a good rest | "Yamamoto: Slept like a stone. Didn't even hear the engine." / "Mori: You snored through the exhaust. Congratulate yourself." |
| **Terse professional** | Any working moment | "Takeda: On the brake. Set your feet. Now." |

**Etiquette:** casual, period-appropriate. The 1962 Japanese longliner crew is working class; grammar and vocabulary are direct. Avoid modern slang. Avoid deliberate rudeness — these are men who live together and don't want to fight.

### 3.5 Harbour gossip — dockside voices

Only when docked or approaching the quay. Voices from the pier, other crews, and the harbour master.

| Type | Trigger | Sample |
|---|---|---|
| **Quay greeting** | Arrival | "Quay hand: Ahoy, Kōei Maru! Catch looking good?" / "Deck: Good enough. The ice house still open?" |
| **Market rumour** | Docked | "Quay hand: The Ginza's sending a man this afternoon. Wants the best yellowfin. You'll want to talk to him." |
| **Rival boast** | Rival docked | "Tenyo crew: We got the bigeye first. Twenty kilos. Beat that." / "Takeda: There's more bigeye in the sea than on your deck. Give us a week." |
| **Local news** | Docked, random | "Quay hand: Have you heard? The wife of the harbour master is pregnant again. Fourth child." |
| **Weather gossip** | Docked, stormy | "Quay hand: It's coming on to blow. Every boat's coming in. You'll be wanting to get in too." |
| **Warning** | Departing | "Quay hand: Careful out there. The Mizuho Maru lost a man last month." |
| **Chef query** | Docked | "Quay hand: The chef from the Ginza wants to know what you're bringing tomorrow. Wants to plan." |

**Etiquette:** pragmatic, gossipy, respectful of the sea. The harbour is where reputations are made.

### 3.6 Distress traffic — rare, high-priority

The most powerful broadcasts. Rare — should feel special — but the game is set in 1962, when a fishing boat lost at sea was a real and common occurrence.

| Type | Trigger | Priority | Sample |
|---|---|---|---|
| **Mayday** | Rare (5% per session at sea) | **Critical** | "Mayday, Mayday, Mayday. This is Shinwa Maru. We are sinking. Position twenty-six by nine. Six men aboard. Over." |
| **Pan-pan** | Rare (10% per session) | High | "Pan-pan, Pan-pan, Pan-pan. This is Tenyo Maru. We are drifting with engine failure. Request tow. No immediate danger. Over." |
| **Silence** | After Mayday | — | (The line goes quiet. Nobody answers. The player can break silence with a reply.) |
| **Coast station response** | After Mayday | High | "Shinwa Maru, Shinwa Maru, this is coast station. Received your Mayday. Rescue vessels en route. Stand by on two-one-eight-two." |
| **Survivor** | After Mayday + 6 hours | — | "Coast station to all vessels: Shinwa Maru has been lost with all hands. All vessels render assistance if sighted. Out." |

**Etiquette:** Mayday is repeated three times. "Pan-pan" for urgency, "Mayday" for distress. Ship name, nature of emergency, position, persons aboard. Coast station acknowledges. Silence follows unless a responding ship breaks it.

The player **can respond** to a distress call — with a menu of canned replies:

- "Kōei Maru: received Mayday. We are twelve miles east. Standing by to assist. Over."
- "Kōei Maru: received. Our engine is running. We will make best speed. Over."
- *(no reply — the player leaves it to someone closer)*

Responding takes time, fuel, and possibly risks the crew. But refusing a distress is a mark on the captain's character that the crew will note.

### 3.7 Overheard — other boats' traffic

Not directed at the player, but audible. Adds ambient realism.

| Type | Trigger | Sample |
|---|---|---|
| **Other boat's catch report** | Random, if in range | "Coast station, this is Tenyo Maru. Noon position twenty-four by eight. Catch today nine yellowfin. Over." |
| **Other boat asking weather** | Random, if in range | "Coast station, Kōzu Maru. Request weather for the eastern grounds. Over." |
| **Other boat's routine** | Random, if in range | "Coast station, Shinwa Maru. Arriving harbour tomorrow morning. Request berth allocation. Over." |
| **Rival boast** | Rare | "…and the bigeye came up so big the whole deck went silent. Twenty-two kilos. Beautiful fish." |
| **Rival complaint** | After a poor season | "…nothing but albacore all week. Albacore and one broken hook. I'm telling you, the fleet has emptied the grounds." |

These are the "atmospheric radio" of the game. They fill the world with other people. Range-faded like coast station traffic.

## 4. Priority and interruption

If two broadcasts arrive close together, the higher priority takes over:

| Priority | Types |
|---|---|
| **Critical** | Mayday, fire alarm, man overboard |
| **High** | Pan-pan, coast station urgent warning, distress response |
| **Medium** | Tow request, weather warning, engine alert |
| **Low** | Routine traffic, time signal, gossip |

If a low-priority broadcast is playing when a high-priority one arrives, the low one is cut off. A player tuning to a market report might be interrupted by a Mayday — and should be — that's the point.

## 5. Frequency and pacing

The most dangerous failure mode is **too much chatter**. The current game is quiet; silence is a feature. If a broadcast fires every 15 seconds, the world feels chatty and the player stops reading.

Suggested rates:

| Channel | Frequency |
|---|---|
| Coast station time signal | Every game hour |
| Coast station weather | Every 2–3 game hours, or on `F2` |
| Coast station market | Every 2–3 game hours, or on `F3` |
| Coast station news | 1–2 per game day |
| Coast station navigational warning | 1 per game day |
| Ship-to-ship | 1–2 per game hour, if other ships are in range |
| Intercom | 2–4 per game hour (during working operations) |
| Crew chatter | 1 per 60–120 s idle crew |
| Harbour gossip | 2–3 per docking visit |
| Distress traffic | 5% chance per session |
| Overheard | 1 per 30 min of gameplay offshore |

That's roughly one broadcast every 2–5 minutes on a quiet watch, more during operations. Enough to feel alive; not so much that it becomes background noise.

## 6. Broadcast authenticity — 1962 vocabulary

Period-accurate language, since the game is set in 1962:

**Radio phrases (universal):**
- "Over" — turn over to you, expecting reply
- "Out" — end of conversation, no reply needed
- "Roger" — received
- "Wilco" — will comply
- "Say again" — repeat
- "Standby" — wait
- "Copy" — I understand
- "Affirmative" / "Negative"
- "This is [ship name]" — standard opening
- "CQ" — general call, any station may reply

**Addressed:**
- "Coast station" — the shore operator
- Ship names followed by "Maru" — the "-Maru" suffix is universal for Japanese merchant vessels
- "Kōei Maru" — the player's ship (if named)

**Numbers:** Read digit by digit for clarity: "Twenty-two" = "two-two." "Twenty-five by eight" = 2-5 by 0-8.

**Time:** "Fourteen hundred hours" (2400 = midnight). Not "2 PM."

**Position:** lat/long in degrees/minutes, or "by the eastern grounds" / "off Cape Erimo."

**1962-specific slang:**
- "Maru" — ship suffix
- "San" — honorific for persons on voice traffic
- "Boat" — not "vessel" in casual speech (though "vessel" is correct on formal traffic)
- "The grounds" — the fishing grounds
- "The quay" — the harbour dock
- "The harbour" — the port

**Things to avoid:**
- "10-4" (CB slang, not 1962 maritime)
- "Copy that" (later
- Modern idioms ("no worries," "doing great," "sounds good")
- Radar, sonar, GPS — all later or not fitted to this class
- "Over and out" — an error; use one or the other

## 7. Implementation notes

### 7.1 The conversation queue

Add to `Game`:

```python
self.broadcast_queue = []       # list of (delay, speaker, text, kind)
self.broadcast_t = 0.0
self.broadcast_current = None   # (speaker, text) or None
```

Every tick:

```python
def _update_broadcast(self, dt):
    if self.broadcast_current:
        # Already displaying a line; wait for its dwell time
        return
    if not self.broadcast_queue:
        return
    self.broadcast_t += dt
    if self.broadcast_t < self.broadcast_queue[0][0]:
        return
    delay, speaker, text, kind = self.broadcast_queue.pop(0)
    self.broadcast_t = 0.0
    if kind == "crew":
        # Speech bubble via Crew.say
        self.crew.say("%s: %s" % (speaker, text))
    elif kind == "radio":
        # Radio line + speech bubble from whoever's on the radio
        self.radio_message = text
        self.radio_message_t = 8.0
    elif kind == "intercom":
        # Speech bubble from the calling sailor
        self.crew.say("%s: %s" % (speaker, text))
    self.broadcast_current = (speaker, text)
```

### 7.2 Triggers

A few entry points for the new system:

- `_roll_ambient_broadcast(dt)` — fires crew chatter and overheard traffic every X seconds
- `_trigger_radio_broadcast(kind)` — scheduled coast station broadcasts (time signal, weather, market)
- `_trigger_event_broadcast(event_id)` — fires when a market/event milestone lands
- `_trigger_distress()` — rare, from the event pool
- `_trigger_harbour_gossip()` — docked

### 7.3 Conversation sequencing

For multi-line exchanges (ship-to-ship, distress, market exchange):

```python
def _say_conversation(self, lines):
    """lines: [(delay_sec, speaker, text, kind), ...]"""
    self.broadcast_queue.extend(lines)
```

Example:

```python
self._say_conversation([
    (0.0, "Tenyo Maru", "Kōei Maru, this is Tenyo Maru. Position twenty-five by eight. Over.", "radio"),
    (3.5, "Captain", "Tenyo Maru, Kōei Maru. Roger. Thanks. Standing by.", "radio"),
    (7.0, "Tenyo Maru", "Good luck. Tenyo out.", "radio"),
])
```

### 7.4 Interruption

When a higher-priority broadcast arrives:

```python
def _interrupt_with(self, lines, priority=3):
    if priority < self.broadcast_current_priority:
        return
    self.broadcast_queue.clear()
    self.broadcast_current = None
    self.broadcast_t = 0.0
    self._say_conversation(lines)
    self.broadcast_current_priority = priority
```

### 7.5 Where to hook

- **`Game.update()`** — call `self._update_broadcast(dt)` and `self._roll_ambient_broadcast(dt)`
- **`Longline` stage transitions** — hook for crew chatter during setting/hauling
- **`Weather.set()`** — hook for weather broadcast
- **`AuctionSession`** — hook for market news and buyer gossip
- **`Game.settle_supplies_and_wages()`** — hook for harbour gossip
- **`Game.radio_call()`** — already exists, extend to also fire conversations

## 8. Sample conversation scripts

Five full scripts you could paste in, one per category.

### 8.1 Coast station — hourly time signal

```
[HH:00:00] Coast station: "This is JJY. The time is fourteen hours, zero minutes."
[HH:00:04] Coast station: "Zero seconds. Out."
```

### 8.2 Ship-to-ship — a friendly exchange

```
[0.0] Tenyo Maru: "Kōei Maru, this is Tenyo Maru. How's the fishing where you are? Over."
[4.0] Captain: "Tenyo Maru, Kōei Maru. Slow. Four albacore all morning. What about you? Over."
[9.0] Tenyo Maru: "Twelve yellowfin. Come east. We're twenty-two by seven. Over."
[13.0] Captain: "Kōei Maru: copy. We'll make our way. Thanks. Out."
[15.5] Tenyo Maru: "Good luck. Tenyo out."
```

### 8.3 Distress — a Mayday call

```
[0.0] Unknown: "Mayday, Mayday, Mayday. This is Shinwa Maru. We are sinking. Position twenty-six by nine. Six men aboard. Over."
[5.0] Coast station: "Shinwa Maru, this is coast station. Received your Mayday. Rescue vessels en route. What is your condition? Over."
[10.0] Unknown: "Coast station, Shinwa Maru. Taking water fast. Engine swamped. We are abandoning. Over."
[15.0] Coast station: "Shinwa Maru, coast station. Understood. Abandon ship. Rescue vessels ETA forty minutes. Over."
[20.0] (silence — the line goes quiet)
[22.0] Coast station: "All vessels, all vessels. This is coast station. Distress traffic on two-one-eight-two. Vessel Shinwa Maru sinking, position two-six by zero-nine. Any vessel able to assist, acknowledge. Out."
[27.0] (no reply — the player can break silence here)
```

If the player responds with "Kōei Maru: received. We are twelve miles east. Standing by to assist. Over.":

```
[30.0] Coast station: "Kōei Maru, coast station. Received. Make best speed. Report when on scene. Out."
```

If the player does not respond within 20 seconds:

```
[42.0] Coast station: "Coast station to all vessels. No vessels responding. Rescue launch departed. Out."
```

The crew may comment afterward:

```
[45.0] Takeda: "God keep them. The sea takes who she takes."
```

### 8.4 Intercom — a working exchange

```
[0.0] Takeda: "Bridge, deck. Fish alongside. Do you want the boat held?"
[3.0] Captain: "Bridge: hold her head to the swell. Two minutes."
[6.5] Takeda: "Aye. Holding."
[9.0] Takeda: "Bridge, deck. Fish aboard. Twelve this set, four good size."
[13.0] Captain: "Copy. Bring them to the table."
```

### 8.5 Harbour gossip — a docking exchange

```
[0.0] Quay hand: "Ahoy, Kōei Maru! Catch looking good?"
[3.0] Takeda: "Good enough. Is the ice house still open?"
[6.0] Quay hand: "Open till six. There's a chef from the Ginza at the auction house, wants to talk to whoever brought the best yellowfin. You'll want to see him."
[12.0] Takeda: "Chef from the Ginza. What's his name?"
[15.0] Quay hand: "Kuroda-san. Old man. Very particular."
[18.0] Takeda: "We've dealt with particular before."
```

## 9. The silence rule

The catalogue above is a menu, not a script. If everything fires, the game becomes a wall of text and voices. The design rule:

- **Silence is the baseline.** The default state of the game is quiet — wind, engine, waves.
- **A broadcast should interrupt.** If the player is doing something and a voice cuts in, they should *notice*.
- **Crew chatter should be sparse.** One or two voices per working hour, not a background hum.
- **Distress traffic should be rare enough to feel dangerous.** If it fires every session, it loses weight.
- **The most common broadcast should be silence.** Time signal, weather, occasional overheard — the daily bread. Everything else is a moment.

The game's atmosphere is heavy with silence — the sound of the engine, the sea, the wind. The voices are punctuation.

## 10. Extension — replies and branching

A future extension (Phase 7+, not needed now): the player can *reply* to distress calls and ship-to-ship offers with a small choice menu.

- "Kōei Maru: received. We are on our way." → crew morale +0.1, fuel cost, delay to the trip
- "Kōei Maru: received. Cannot assist. Sorry." → crew morale -0.2, no cost, guilt
- *(no reply — silence)* → crew morale -0.05, harbour reputation -0.1

The player's choices shape their reputation in the harbour and among the crew. A captain who never answers a distress call is a captain whose crew questions him.

That's the long arc: from "a fisherman" to "a captain people would sail with." The broadcasts are the visible part of that arc.

## Summary

The world already has four broadcast channels — speech bubbles, coast-station radio, weather changes, and longline stage messages — but they're all one-way single-line calls. A proper broadcast system adds three things:

1. **Multi-message conversations** — two or three lines back-and-forth with believable timing
2. **Attribution** — each line has a speaker ("Coast station", "Tenyo Maru", "Captain", "Takeda")
3. **Priority** — a Mayday interrupts a weather report; a distress interrupts crew chatter

Six channels of voice, all period-appropriate for 1962: coast station broadcasts (weather, market, news, navigational warnings, time signal, fleet positions, distress acknowledgements); ship-to-ship two-way traffic; ship-internal intercom; deck-level crew chatter; harbour gossip; and distress traffic. Rare distress calls carry the most weight — a Mayday should feel like a shock, not ambient sound.

The silence rule is the design constraint. The game's atmosphere is heavy with silence — wind, engine, waves. Broadcasts punctuate that silence; they don't fill it. If a player stops noticing the voices, the voices have failed.