# TOW REQUEST AND DISTRESS RADIO: DESIGN AND IMPLEMENTATION GUIDE

Status: PROPOSED
Depends on: V13.1.31 tow constants, V13.1.23 ocean plotting (radio via ship
station), `Broadcast Conversations - Catalogue.md`, Plan 13.2.xx (ship_radio)
Feeds into: SINKING_AND_ABANDONMENT.md (MAYDAY on foundering), 13.2 AI traffic

## PURPOSE

Replace the silent, automatic tow with a *conversation shouted into the
dark*. The player keys the radio, says what they think their situation is,
and waits. Someone answers — or does not. The tow is the outcome of that
exchange, not a menu item.

The design principle from Plan 13.2.xx applies unchanged: **every reply is a
claim, not a guarantee.** An acknowledgement is not a rescue. A vessel that
says it is four hours out may be eight hours out, may be lying about its
position to protect a hotspot, or may be a passing ship that heard the call
and chose to say nothing at all.

The player is not calling a dispatcher. In 1962 nobody knew who was
listening. The radio is a microphone and an ocean, and most of the time the
ocean does not answer.

---

## 1. DISTRESS TAXONOMY — AND WHY IT MATTERS

1962 procedure, still standard:

| Signal | Meaning | Use for |
|---|---|---|
| MAYDAY | Grave and imminent danger; vessel or life at risk | Foundering, fire, man overboard, abandoning ship |
| PAN-PAN | Urgency; no immediate danger to life | Engine failure, out of fuel, adrift, unable to make way |
| SECURITE | Safety | Navigational warnings, weather, gear in the water |

**A tow request is PAN-PAN, not MAYDAY.** This distinction is the doc's first
teaching moment, and the game should not hide it behind a tooltip.

### 1.1 The "Mayday mayday, is anyone there?" case

A panicked player will key the mic and say exactly that. It is **not a valid
distress call**: no station identification, no position, no nature of
distress. The game should let them send it, and then let the ocean respond
honestly.

**The naive call goes out into the dark and is more likely to be ignored
than answered.** A listener who hears a mis-keyed call with no call sign and
no position has very little to act on. Some listeners will ignore it as
traffic noise. Some will key up and say nothing. If the coast station is on
watch and heard it, it may reply with a format correction:

```
[Hakodate Coast Radio, 2182 kc]
  COAST: Station calling Mayday, station calling Mayday.
         This is Hakodate Coast Radio. Say again your call sign
         and your position. Over.
```

This is good play. It costs the player thirty seconds, it teaches the format
by consequence, and it characterizes the coast station as a professional
operator rather than a vending machine. The well-formed call gets a faster
and more useful answer.

But the correction is **not guaranteed**. If no coast station is on watch,
or if only passing ships heard it, the naive call may get nothing at all —
just a carrier, or silence, or a voice that says "vessel calling, we hear
you" and then never speaks again.

### 1.2 Consequence of a false MAYDAY

Sending MAYDAY when PAN-PAN was correct is not fatal, but it is remembered:

- The coast station logs it. A second MAYDAY within `FALSE_MAYDAY_WINDOW`
  is answered more slowly, or answered by a junior operator, or relayed
  rather than handled directly.
- Independent peers on the band lose a little respect (`reputation -= n`).
- A real MAYDAY later in the run is **not** ignored — but the
  *acknowledgement is delayed*, which in a foundering scenario is exactly
  the thing that kills you.

That is the whole moral of the system: **credibility is a resource you
spend.**

---

## 2. PLAYER FLOW

```
[Radio station, wheelhouse]
   R  -> open radio
   band:  2182 kc (distress) | 2638 kc (ship-to-ship) | WX
   call:  MAYDAY | PAN-PAN | SECURITE | ROUTINE
   fill:  nature, position (auto from believed_pos, editable),
          assistance required (tow | pumps | medical | escort | none)
   PTT -> transmit, into the dark
```

The player is **not calling a dispatcher.** They are broadcasting on a band
that anyone within range can hear. The game does not tell them who is
listening, because in 1962 nobody knew that.

- The **position transmitted is `believed_pos`, not `pos`.** A stale fix
  means you have just told the ocean the wrong place, and every responder
  will navigate to that wrong place.
- Reception depends on the operator's skill, the weather, the time of day,
  and the antenna. A low-skill hand may garble the call, omit the position,
  or fail to hear a reply that came back.
- The call can be **cancelled mid-transmission**. A half-sent distress call
  is worse than none.

### 2.1 The ambient traffic layer

Before the player ever needs to call, the radio should tell them **roughly
who is out there.** This is what makes the passing-ship model legible.

The 2182 and 2638 kc bands carry routine traffic as ambient broadcast
conversations:

```
[2638 kc, 19:42]
PEER: {peer_a}, {peer_a}. Hauling. Two thousand hooks, half done.
PEER_B: Roger. We're setting at first light.
CORP: [unidentified catcher-boat] {corp}, {corp}. Holding north of
      the line. Keeping clear.
```

These lines are **not directed at the player** and do not require a
response. They exist so the player learns the texture of the band: who is
nearby, who is hauling, who is transiting, whether the ocean is busy or
empty tonight. A player who has been listening for two hours **has a rough
mental model of who might hear a distress call.** A player who keyed the mic
cold does not.

This is the whole design: **listening is a skill, and the radio rewards it.**

### 2.2 The waiting state — shouting into the dark

After transmission the game enters `AWAITING_REPLY`. It must not look like a
menu waiting for a server.

- The radio log shows `TX 21:14  PAN-PAN  position given` and then
  **nothing**.
- There is no "waiting for response…" indicator. The silence is the
  gameplay.
- Replies arrive as timed, attributed, interruptible broadcasts through the
  existing `_update_broadcast()` system — **if they arrive at all.**
- The player may keep working (bail, secure gear, tend the raft) during the
  wait.
- **Most of the time, nobody answers.** That is the baseline, not the
  failure case.

The player is encouraged to do the human thing: key up again after ten
minutes, try a different band, ask a specific ship they heard earlier by
name.

---

## 3. RADIO STATE MACHINE

```
IDLE
 -> KEYED                 (PTT down, call assembling)
 -> TRANSMITTED           (full call sent)
 -> AWAITING_REPLY        (silence; the default state)
 -> CARRIER_ONLY          (someone keyed up, said nothing)
 -> ANONYMOUS_RESPONSE    (a voice, no identification)
 -> ACKNOWLEDGED          (someone answered and identified)
 -> ASSISTANCE_EN_ROUTE   (a claim; may be withdrawn or false)
 -> ASSISTANCE_ARRIVED
 -> TOW_IN_PROGRESS       (hands off to the tow state machine)
 -> NO_REPLY              (timeout)
 -> CANCELLED             (stood down, or situation resolved)
```

Notes:

- **`CARRIER_ONLY`** — the player's operator hears the squelch open and a
  carrier, but no voice. Someone was listening. They did not speak. This is
  a real and unsettling thing on HF, and it is the best single mechanic for
  making the ocean feel inhabited. The log records it:
  `RX 21:22  carrier only`. The player will wonder who it was for the rest
  of the run.
- **`ANONYMOUS_RESPONSE`** — a voice on the band, no call sign given.
  "Vessel calling, we hear you." The player cannot tell who it is, where
  they are, or whether they are coming. This is the *most interesting*
  state, because the player has to decide whether to trust an unidentified
  voice.
- **`ACKNOWLEDGED` does not imply assistance.** It means someone heard and
  said something. Nothing more.
- **`ASSISTANCE_EN_ROUTE` is a claim.** It can be withdrawn, revised, or
  never arrive. The log records what was said, not what happened.
- `TOW_IN_PROGRESS` must reconcile with the existing `UNDER_TOW` state —
  see §7.
- Any state can be interrupted by a higher-priority inbound distress. See §5.

---

## 4. DIALOGUE CATALOGUE

All lines go through the broadcast system with attribution, priority, and
interruptibility. `{ship}` = player, `{pos}` = transmitted position,
`{dist}` = claimed distance, `{eta}` = claimed time.

### 4.1 Player transmits

Well-formed PAN-PAN:

```
PAN-PAN, PAN-PAN, PAN-PAN.
This is {ship}, {ship}, {ship}.
Position {pos}.
Engine disabled, unable to make way. No immediate danger to life.
Request tow. Over.
```

Well-formed MAYDAY:

```
MAYDAY, MAYDAY, MAYDAY.
This is {ship}, {ship}, {ship}.
Position {pos}.
Taking on water, {n} persons aboard, preparing to abandon.
Request immediate assistance. Over.
```

The naive call — sendable, and corrected in-fiction only if someone hears
and chooses to correct it:

```
"Mayday mayday, is anyone there? Anyone? Over."
```

**It goes out into the dark and the ocean answers, or does not.** If the
coast station is on watch and heard it, it may reply with a format
correction (§4.2). If only a passing ship heard it, that ship may simply
ignore it as a mis-keyed call. This is a real cost: **the naive call is more
likely to be ignored than answered.**

Minimal PAN-PAN from a competent operator:

```
PAN-PAN, PAN-PAN, PAN-PAN. {ship}, {ship}. Position {pos}.
Fuel exhausted. No way on. Request tow. Over.
```

### 4.2 The coast station — one listener among many

The coast station is a **monitoring service**, not a dispatcher. It logs
you, acknowledges you, and passes your situation along. It usually does not
have a vessel to send. Its honesty is high; its usefulness is modest.

Acknowledging a well-formed call:

```
Hakodate Coast Radio, roger, {ship}. Your distress acknowledged.
We have no vessel in your area. We will keep a listening watch
and relay to traffic proceeding south. Over.
```

That is the **most common** coast-station reply, and the player should learn
to read it correctly: *acknowledged, not assisted.*

Correcting a malformed call:

```
Station calling Mayday, this is Hakodate Coast Radio.
Say again your call sign and your position. Over.
```

Refusing / deferring:

```
{ship}, Hakodate Coast Radio. No vessel available in your area at
this time. Recommend you consider anchoring if conditions permit.
We will relay. Over.
```

Out of watch hours:

```
[2182 kc] ... (carrier only; no voice)
```

A stale plot (their idea of where you are is from your last report):

```
{ship}, Hakodate Coast Radio. Our plot places you {dist2} south-west
of your stated position. Confirm. Over.
```

The player must decide whether to trust their own fix or the station's plot.
Both are claims.

### 4.3 The passing ship — the main event

This is who the player is really hoping to hear. **A voice with a rough hand
and a call sign they did not recognise.** They are out there by chance,
within range by chance, and they decide whether to help by their own lights.

**The good one:**

```
[2638 kc, rough voice, no preamble]
Vessel calling, {peer}, {peer}. We hear you. We're maybe three hours
off your light. We'll come about. Keep your lamp lit. Over.
```

Three hours becomes five. They arrive apologetic:

```
{peer}: Sorry, {ship}. Current set us south. We see you now. Stand by
to take a line.
```

This is the outcome the player is hoping for, and it should feel like a
small miracle every time.

**The one who can't:**

```
{peer}: {ship}, we hear you. We're hauling. Can't break off, not
this set. Try the coast station. {peer} out.
```

No dishonesty, just priorities. This is the most common passing-ship reply
and the player should not read it as a bug.

**The one who hears and says nothing:**

Silence, but the log shows `RX 21:31  carrier only`. Someone was there. They
did not speak. The player cannot know why: hauling, unwilling, asleep at the
set, listening to see who else answers first. **This is the single most
important case in the whole document.** It is what makes the ocean feel
populated and indifferent at the same time.

**The anonymous one:**

```
[No call sign]
Vessel calling {ship}, vessel calling {ship}. We hear you.
Stand by.
```

Then nothing for an hour. Then a different voice, perhaps:

```
Vessel calling {ship}. We're close. Can you see our lights?
```

Or nothing at all. The player has been given hope by someone who did not
identify themselves. This is the most interesting state the system can
produce, and it costs nothing but two lines of dialogue.

**The one who lies:**

```
{peer}: {ship}, {peer}. We're two hours out. Hold on. Over.
```

They are not two hours out. They may be eight hours out, or they may never
come. The game does not tell the player this. They find out by waiting.

**The corporate catcher-boat:**

```
[Catcher-boat {corp}, clipped and formal]
{ship}, {corp}. We can assist. Understand our schedule is committed.
Towing will be at commercial rate, {fee} yen, payable on arrival.
Confirm you accept. Over.
```

**The mothership:**

```
[Mothership {name}, calm operator]
{ship}, {name}. We have you on our plot. We can divert, but we are
{eta} out. If you can hold, hold. If you cannot hold, say so now.
```

Note the honesty. The mothership does not overpromise — which makes its
arrival meaningful.

**The relay:**

```
[Third party]
Hakodate Coast Radio, Hakodate Coast Radio. This is {relay}.
Relaying distress from {ship}, position {pos}, requires tow. Over.
```

The relay's idea of your position is *its* hearing of *your* transmitted
position. Error compounds. If your fix was stale when you called, and the
relay misheard your position, help will arrive somewhere else.

### 4.4 Later discovery — who heard

The player may learn, days later, that someone heard and did not answer:

```
{peer}: Heard your call last Tuesday. We were hauling, couldn't
break off. Figured the coast station had you.
```

Or that someone was closer than they knew:

```
{peer}: We were two miles off your light that night. Never heard
you. Must have been off watch.
```

These are ambient broadcasts, not targeted at the player, and they are how
the game quietly tells the player: **the ocean heard you, or didn't, and you
will never fully know which.**

### 4.5 Withdrawal and revision

```
{peer}: {ship}, we have a problem with our engine. We cannot reach
you. Contacting coast station on your behalf. Sorry.
```

```
COAST: {ship}, Hakodate Coast Radio. Correction to previous.
{vessel} is not available. No assistance at this time. Over.
```

### 4.6 Real distress interrupting a routine call

If a genuine MAYDAY comes in while the player is mid-PAN-PAN, the coast
station drops the player's traffic:

```
COAST: All stations, all stations. Cease transmissions. MAYDAY in
progress. {ship}, stand by, we will return to you. Out.
```

The player's tow request is now queued behind a life-and-death call. That is
correct, and it should sting a little.

---

## 5. PRIORITY AND INTERRUPTION

| Priority | Source | Behaviour |
|---|---|---|
| 0 | Inbound MAYDAY | Stops all lower-priority traffic, including the player's |
| 1 | Player MAYDAY | Highest the player can send |
| 2 | Player PAN-PAN | Queued behind any MAYDAY |
| 3 | Coast station routine | Weather, market, time signals |
| 4 | Peer chatter | Ambient; interruptible |

The broadcast system already supports interruptible conversations; this doc
just assigns the priority ladder. Inbound MAYDAY must be able to pre-empt a
routine weather broadcast and a player PAN-PAN alike.

---

## 6. WHO IS IN RANGE RIGHT NOW

This is the model that makes the whole system work.

At any moment, the ocean within radio range of the player contains a
**population of vessels.** The player does not know this population
directly. They infer it from:

- the ambient traffic they have heard over the last few hours,
- the time of day (haulers are on watch at night, coast stations are not),
- the weather (storm static shrinks everyone's range),
- their own drifted position (which may be nowhere near where they planned
  to be).

### 6.1 The response pipeline

When the player transmits:

1. **Compile the listener set.** Which vessels are within range of the call,
   given their positions and the current propagation conditions? This
   includes the coast station and every AI ship within range.
2. **Hearing check, per listener.** Distance, band, weather, their watch
   status, their radio operator's skill. Some fraction hears the call; the
   rest do not.
3. **Response decision, per listener that heard.** Based on their situation,
   their character, their relationship to the player, and their own
   priorities. Most listeners that hear will **not** respond. Some will
   respond honestly, some will respond dishonestly, some will key up and say
   nothing.
4. **Player's reception check, per response.** The player's radio operator
   must also *hear* the reply. A low-skill operator may miss a response
   entirely, or mishear a position, or fail to catch a call sign.
5. **Log what was heard, not what happened.** The Ship's Notebook records
   `RX 21:31  carrier only` even if the listener was a peer who chose to say
   nothing. It records `RX 21:44  unidentified, "we hear you", stand by`
   even if that voice was lying. The player reads the log and makes their own
   decisions.

### 6.2 Responder types

| Responder | Typical range | Usually hears you? | Usually responds? | Can it actually help? | Honesty |
|---|---|---|---|---|---|
| Hakodate Coast Radio | ~40 nm | Yes, on watch | Yes | Rarely (no vessel) | High |
| Independent peer | ~25 nm | Yes | Sometimes | Yes, if not hauling | Medium |
| Corporate catcher | ~60 nm | Yes | If paid | Yes, at commercial rate | Medium |
| Mothership | ~80 nm | Yes | If diverting | Yes, slowly | High |
| Anonymous vessel | ~25 nm | Unknown | Unknown | Unknown | Unknown |
| Silent listener | ~25 nm | Yes | **No** | n/a | n/a |
| Nobody in range | — | No | — | — | — |

The **silent listener** is the row that matters most. In a sparsely fished
ocean, most of the time there is a ship within range, and most of the time
that ship hears the call and says nothing. The player hears a carrier, or
hears nothing at all, and cannot tell the difference between *"nobody's out
there"* and *"somebody's out there and doesn't care."*

### 6.3 Availability by role

- **Coast station** — on watch 06:00–22:00 local. Outside those hours, no
  reply. At night the band is quieter, and the player is more alone.
- **Independent peers** — more likely to be listening at night, because they
  haul at night. More likely to hear you, less likely to help, because
  breaking off a haul costs them money.
- **Corporate catcher-boats** — will help if paid. Their rate scales with
  distance and with how much schedule they lose.
- **Motherships** — rare, slow, honest. The best outcome, and the least
  likely.
- **Anonymous vessels** — may be anyone. A peer who doesn't want to give
  their position away. A corporate boat fishing your grounds. A coast
  station relay on a bad antenna. A hallucination of the player's exhausted
  radio operator. **The game does not resolve which.**

### 6.4 Watch clock

The time of day shapes the whole listener set:

- **Day (06:00–22:00)** — coast station on watch, peers mostly hauling,
  corporate boats transiting. Busy band.
- **Night (22:00–06:00)** — coast station off watch, peers hauling and
  listening, corporate boats running dark. Quieter band. The people who
  answer at night are the people who were awake and chose to answer.
- **Dawn / dusk** — the band opens up (skip). Distant stations may be
  audible and near ones may be lost. A call at 05:00 may reach a ship 100 nm
  away and miss the one 10 nm away.

This is the first time in the game that **time of day has a real mechanical
consequence** for the player's decisions, and it should be legible in the
crew log: *"Band quiet. Coast station off watch until 06:00."*

### 6.5 Selection weights

Responder selection is weighted by: distance, availability, responder type,
whether the player's transmitted position is plausible, and (rarely) whether
the responder has a reason to help or not. Do not make it always-succeed.
Target roughly:

- ~25%: a passing ship or coast station responds within an hour.
- ~25%: someone responds, but late, or with a correction.
- ~20%: coast station acknowledges, no vessel available.
- ~15%: carrier only — someone heard, nobody spoke.
- ~15%: silence.

Tune against playtest; the point is that silence and lateness are common,
not exceptional.

---

## 7. INTEGRATION WITH TOW AND ABANDONMENT

The V13.1.31 tow currently starts a simplified, persistent radio tow call
when the low-fuel threshold or the six-in-game-hour adrift timer trips, then
uses the existing `TOW_REQUESTED -> UNDER_TOW` state. This proposal changes
the normal player interaction to an explicit PAN-PAN conversation, but
**keeps the automatic trigger and retry loop as a fallback** for players who
never key the mic.

```
adrift detected  ->  TOW_ADVISED    (crew log entry, no state change)
                 ->  [player keys the radio, sends PAN-PAN, into the dark]
                 ->  AWAITING_REPLY / CARRIER_ONLY / ANONYMOUS_RESPONSE /
                     ACKNOWLEDGED / ASSISTANCE_EN_ROUTE / NO_REPLY
                 ->  UNDER_TOW      (existing state; helm locks; per-frame
                                     advance of pos AND believed_pos)
```

### 7.1 Automatic fallback

After `TOW_TRIGGER_DRIFT_SECONDS` with no radio contact and no way on, the
coast station — *if on watch* — notices an overdue vessel and initiates
contact:

```
COAST: {ship}, {ship}, Hakodate Coast Radio. We have you overdue
on your reported passage. Do you require assistance? Over.
```

This is the station doing its monitoring job, not dispatching help. It
still has to find a vessel to send. It may not find one. The player may
still end up drifting.

If the coast station is **off watch** when the drift timer expires, there is
no automatic call. The player drifts until daylight, or until they key the
mic themselves, or until a passing ship notices them.

### 7.2 Execution path (from the tow diagnosis)

The existing `UNDER_TOW` update must:

- advance **both** `pos` and `believed_pos` by the same step, in **design
  units** (`DESIGN_UNITS_PER_NAUTICAL_MILE = 185.2`, **not** 1852),
- lock the helm on entry and unlock on arrival,
- raise the anchor rather than refusing to tow,
- cast off and unlock the helm if flooding reaches `CRITICAL`, so
  `ABANDON_SHIP` remains available.

### 7.3 Non-tow assistance

The same listener model applies:

- **Pumps** — a passing ship may have a portable pump; may reach you in
  time.
- **Medical** — for an injured crew member; may arrive too late.
- **Escort** — for a damaged but seaworthy vessel.
- **Abandonment** — a MAYDAY from a foundering ship. The responder may be
  the one who picks up the raft. Ties into
  `SINKING_AND_ABANDONMENT.md` §4.5.

### 7.4 If the ship sinks during the conversation

The MAYDAY goes out on the same radio, from the same station, with the
raft's position (which is the ship's last `believed_pos`). `AWAITING_REPLY`
transfers to the raft if a handheld radio was carried. If not, the crew is
alone and the radio log shows the ship's last transmission and nothing after
it.

---

## 8. CREW, SKILL, AND RECEPTION

- The radio set is a **physical station**. A crew member must be at it.
- **Skill** affects: clarity of transmission (garble chance), whether a
  reply is correctly *heard*, and speed of call assembly.
- **The player's operator may not hear the reply.** A low-skill hand
  sitting the radio through a storm can miss a response entirely, and will
  report "no answer" with confidence. The player does not get to see the
  transcript the operator didn't hear. They get the operator's judgement.
- **A high-skill operator may hear more than the reply.** Trained 1962
  radio operators can identify a station by the rhythm of its fist, by the
  hum of its carrier, by the background noise. A skilled operator may
  volunteer: *"That's a catcher-boat, not a peer. Listen to the
  generator."* This is what skill looks like on the radio, and it should
  feel earned.
- **The radio set can be damaged.** A storm can take the antenna. Range
  halves. The player is more alone than they were an hour ago, and they
  find out when they key the mic and nobody answers.
- **Reception** depends on: distance, storm static, time of day, band
  chosen, and antenna condition.
- A low-skill operator transmitting a MAYDAY may omit the position. If a
  coast station is on watch it asks again. If not, the call is simply not
  actionable, and the silence is the cost of an unskilled crew.

---

## 9. TUNING

Initial values, one table, config-ready:

| Constant | Start value | Notes |
|---|---|---|
| `NO_REPLY_TIMEOUT` | 45 min in-game | before `NO_REPLY` |
| `SILENCE_HINT` | 20 min | operator volunteers a judgement |
| `ACK_DELAY_MEAN` | 6 min | coast station response latency |
| `ACK_DELAY_STORM_MULT` | 2.5 | storm static |
| `CARRIER_ONLY_CHANCE` | 0.15 | of all calls sent, chance someone keyed up and said nothing |
| `SILENT_LISTENER_CHANCE` | 0.35 | of calls with a listener in range, chance that listener says nothing |
| `ANONYMOUS_RESPONSE_CHANCE` | 0.10 | of calls with any listener, chance of a voice with no call sign |
| `R_COAST` / `R_PEER` / `R_CORP` / `R_MOTH` | 40 / 25 / 60 / 80 nm | base ranges |
| `COAST_WATCH` | 06:00–22:00 | local; outside = no reply |
| `BAND_OPEN_DAWN_DUSK` | true | skip conditions at dawn/dusk |
| `STORM_RANGE_MULT` | 0.5 | storm halves everyone's range |
| `TOW_FEE_BASE` | 6000 yen | replaces the flat V13.1.31 fee |
| `TOW_FEE_PER_NM` | 400 yen | distance-scaled |
| `FALSE_MAYDAY_WINDOW` | 24 h in-game | credibility recovery time |
| `REPUTATION_MAYDAY_PENALTY` | -2 | per false MAYDAY |
| `GARBLE_UNSKILLED` | 0.25 | chance a low-skill TX is misheard |
| `MISSED_REPLY_UNSKILLED` | 0.35 | chance a reply is not heard at all |
| `MISSED_CALLSIGN_SKILLED` | 0.05 | high-skill operators rarely miss a call sign |

**The single most important number is `SILENT_LISTENER_CHANCE`.** It should
be higher than the chance of an actual response. The ocean should, most of
the time, hear you and say nothing. That is the emotional core of the
system.

The `6000` yen base preserves the existing economy while making the fee
scale with how far you drifted — which is a real decision, because drifting
further before calling costs more.

---

## 10. TESTS

Headless, matching the existing suite:

1. `test_panpan_transmit_well_formed` — call assembles with `{ship}`,
   `{pos}`, nature, request.
2. `test_mayday_naive_call_gets_format_correction` — "is anyone there"
   produces the coast station's `say again your call sign` **when a coast
   station is on watch**.
3. `test_position_transmitted_is_believed_not_true` — with a stale fix, the
   transmitted position differs from `pos`.
4. `test_no_reply_is_valid_outcome` — silence does not raise, does not
   block, and the state machine reaches `NO_REPLY`.
5. `test_silence_hint_requires_competent_operator` — low-skill radio op
   does not volunteer a judgement.
6. `test_coast_watch_hours` — call at 03:00 gets static; 10:00 gets a reply.
7. `test_acknowledgement_is_not_rescue` — `ACKNOWLEDGED` does not set
   `ASSISTANCE_EN_ROUTE`.
8. `test_assistance_can_be_withdrawn` — en-route → withdrawn → no tow.
9. `test_inbound_mayday_preempts_panpan` — priority 0 interrupts priority 2.
10. `test_false_mayday_delays_next_ack` — second MAYDAY within window gets
    a delayed acknowledgement.
11. `test_storm_reduces_ack_probability` — storm static lowers reply rate.
12. `test_relay_compounds_position_error`.
13. `test_under_tow_advances_pos_and_believed_pos` — the reconciliation
    guard from the tow diagnosis.
14. `test_sinking_during_awaiting_reply_transfers_to_raft` — handheld radio
    present → raft keeps radio; absent → no radio.
15. `test_tow_fee_scales_with_distance`.
16. `test_radio_station_requires_crew` — no operator → no transmission.
17. `test_save_load_mid_awaiting_reply` — state, elapsed timer, and log
    persist.
18. `test_carrier_only_is_valid_outcome` — log records `carrier only`, no
    state change to acknowledged.
19. `test_anonymous_response_has_no_callsign` — response parses as
    unidentified; player cannot resolve responder.
20. `test_silent_listener_does_not_block` — a listener who hears and says
    nothing does not prevent a later listener from answering.
21. `test_listener_set_depends_on_position_and_weather` — storm halves the
    compiled listener set.
22. `test_coast_watch_hours_no_auto_reply` — call at 03:00 does not produce
    a coast-station reply.
23. `test_dawn_skip_reaches_distant_station_not_near_one` — with skip
    active, range is inverted for distant stations.
24. `test_ambient_traffic_does_not_require_response` — routine peer
    broadcasts do not enter `AWAITING_REPLY`.
25. `test_low_skill_operator_misses_reply` — response sent, operator
    reports "no answer," log does not contain the reply.
26. `test_high_skill_operator_identifies_responder_by_fist` — skilled
    operator volunteers a responder-type judgement.
27. `test_radio_antenna_damage_halves_range`.
28. `test_later_discovery_broadcast` — a peer broadcast days later reveals
    a missed call, does not retroactively alter the log.
29. `test_naive_mayday_is_more_likely_ignored` — a call without position or
    call sign has a lower response probability than a well-formed PAN-PAN.
30. `test_tow_fallback_fires_when_drift_timer_expires_and_coast_on_watch`.
31. `test_tow_fallback_does_not_fire_when_coast_off_watch`.

---

## 11. OPEN QUESTIONS

- Should the player hear **other vessels'** distress traffic as ambient
  broadcasts, even when not involved? (Leaning yes — it makes the ocean feel
  populated and makes the moral weight of ignoring a MAYDAY real.)
- Should the player be able to hear other ships' routine traffic **before**
  they need it, and use it to guess who is nearby? (Leaning strongly yes —
  this is the whole point of the ambient layer, and it makes listening a
  skill.)
- Should the player ever be *sure* who answered? (Leaning no. The
  uncertainty is the mechanic. Even an identified peer may not be where they
  say they are.)
- Should the silent listener ever be revealed? (Leaning only by inference,
  never by the game telling the player. A peer who mentions it a week later
  is as explicit as it should get.)
- Should a false MAYDAY make the coast station *less* likely to respond, or
  just slower? (Leaning slower, not less likely — a professional station
  still answers; it just takes its time and trusts the player less.)
- Does refusing to assist another vessel carry a penalty? (Historically and
  in law, yes. Implementing it is a design choice, not a simulation one.)
- Can the player be the one who **answers** a distress call from an AI ship?
  That is the 13.2 version of this entire doc, and it is the natural sequel.
- Should the player ever be the anonymous voice in someone else's
  transcript? (Yes, in 13.2, when AI ships are the ones calling.)
- Is the flat `6000` fee kept for the automatic-fallback path, with distance
  scaling only for player-initiated calls? (Probably yes — the coast
  station's rate card is the rate card.)
