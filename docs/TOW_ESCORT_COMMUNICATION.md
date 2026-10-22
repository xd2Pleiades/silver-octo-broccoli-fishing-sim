# TOW ESCORT: CONSTANT COMMUNICATION AND CHART PRESENCE

Status: **Partially implemented in v13.1.33; remaining items are design targets.**

Depends on: `TOW_REQUEST_AND_DISTRESS_RADIO.md`, v13.1.30 tow state and constants, v13.1.23 ocean plotting, `Broadcast Conversations - Catalogue.md`.
Feeds into: `SINKING_AND_ABANDONMENT.md` and future 13.2 AI traffic.

## Implementation status in v13.1.33

Implemented now:

- A successful tow response creates an independent Coast Guard escort entity with its own callsign, captain, personality, skill, fuel/patience state, and four-person crew roster. The launch starts at the harbour, visibly approaches a calculated intercept point near the player, spends a brief handover turning period, and then leads the homeward tow; the ETA no longer teleports it from the harbour to a position in front of the player.
- The escort is visible on the navigation chart as the same triangle/ship-marker language as the player's ship, recolored Coast Guard orange with a light outline. It has a `CG <CALLSIGN>` label and last-report age.
- The chart marker uses the escort's **last reported position**, not its live position. Reports include skill-scaled plotting error; after 45 in-game minutes without a successful report, the label gains `?` and the HUD/chart panel identifies it as stale.
- A visible Coast Guard placeholder hull is drawn in the gameplay water view using the player ship hull outline as its reference, with a navy hull, pale deck, orange safety stripe, bridge/windows, and wake. A code comment `PLACE HOLDER SHIP` flags it for replacement by a dedicated art asset. A solid physical towline is drawn from the player bow to the launch stern while the tow is healthy; it becomes dashed with a radio warning when sea state rises to the line-risk threshold.
- The Coast Guard sends scheduled radio check-ins every 30 in-game minutes while en route/under tow, plus occasional personality-flavoured unsolicited messages. Check-ins include its plot, its estimate of the player's position, and an ETA claim.
- `F4` hails the Coast Guard for a position check after the launch has answered. `G` cycles through questions about ETA, weather, traffic, fishing, fuel, crew, the captain's name, fees, and whether the escort will stay.
- The chart side panel shows the captain, callsign, escort state, age of the last report, and crew surnames. The active HUD strip shows who is escorting the player and whether the report is stale.
- On arrival, the Coast Guard exchanges a final radio message and remains charted for 30 in-game minutes before its marker is removed.

Not yet implemented as full playable mechanics: a line can genuinely part and then be re-secured; the Coast Guard can abandon/depart because its own fuel is low; radio corrections directly update the captain's plot; recovery-raft rescue; a save/load system (the project currently has no save-game serialization); and bespoke Coast Guard art. The current hull is intentionally a 2D placeholder derived from the player hull, not a separate detailed 3D model or a second navigable deck/cutaway.

## Purpose and principles

Once the tow is agreed, the tug is a character rather than a progress bar: a voice on the radio, a chart contact, and a captain with their own crew and situation. The Coast Guard is the default responder in this release; the data model keeps vessel type/personality extensible for future peers, corporate catchers, and motherships.

- **Every position is a claim.** The captain's plotted position is noisy and can be stale. The chart shows the most recent reported location rather than revealing ground truth.
- **Silence is a valid reply.** The player need not answer a check-in; the escort does not stop towing merely because the player is silent.
- **The captain has their own problems.** Weather, radio reception, fuel, crew, and schedule can affect later outcomes as this system expands.
- **The tow is a conversation, not an alert feed.** Scheduled check-ins establish a baseline; extra messages are emitted only when there is room on the radio and the captain has something to say.

## 1. The captain as a persistent entity

### 1.1 Creation at handover

When the coast station accepts the tow, the game creates a `TowEscort` object. It stores:

```python
class TowEscort:
    callsign: str
    captain_name: str
    personality: str       # professional | terse | chatty | worried
    skill: float           # affects plot error
    crew: list[TowCrewMember]
    fuel: float
    patience: float
    true_position: tuple[float, float]
    reported_position: tuple[float, float]
    state: str             # EN_ROUTE | UNDER_TOW | ARRIVED
    missed_checkins: int
    fee_owed: int
```

A callsign is chosen from Coast Guard launches such as **Kiku Maru**, **Shirase**, **Hakuto**, and **Kaiyo Maru**. The captain's name is revealed if the player asks. Each launch has its own roster, currently four named Coast Guard hands: radio operator, engineer, deck hand, and line handler. They are separate from the fishing vessel's sailors.

### 1.2 Handover exchange

The response now identifies the launch by callsign instead of leaving the tug as an anonymous state change. The launch says it has copied the player's call, is coming to the reported position, and asks the player to keep the wireless open. At handover, it takes the towline and changes to `UNDER_TOW`.

## 2. Chart presence

The tow vessel appears on the chart for the duration of the escort and briefly after arrival.

| Element | Player vessel | Coast Guard escort |
|---|---|---|
| Icon | Ship triangle | Same triangle/marker language |
| Color | Yellow | Orange with pale outline |
| Label | `VESSEL / DR` | `CG - <CALLSIGN>` |
| Sub-label | — | `(minutes ago)`; `?` when stale |
| Heading | Crew-estimated heading | Escort's reported heading |
| Towline | — | Solid when healthy; dashed when sea state threatens the line |

The ship markers and towline are drawn on the same chart surface and use the same chart transform as the player marker. The tow line is clipped to the chart sheet if either position is off the visible sheet. The right-hand **COAST GUARD ESCORT** section lists callsign, captain, state, report age, and crew.

### 2.1 Staleness and reporting error

The escort's `reported_position` is not its live `true_position`. At each successful report the marker is offset by a skill-scaled error of 1–3 nautical miles. The report's age is measured in in-game minutes. A report older than 45 in-game minutes gets a `?`; no popup is used. This preserves the uncertainty principle while giving the player a useful chart contact.

Before the tow is accepted, the Coast Guard is not labelled as an active escort. After arrival, it remains on the chart for 30 in-game minutes to represent line-handling and harbour handover, then signs off and disappears.

## 3. Check-in loop

### 3.1 Scheduled reports

Every 30 in-game minutes, the captain reports the launch's plotted position, their estimate of the fishing vessel's position, the tow's condition, and an ETA claim. Thirty in-game minutes is 12.5 simulation seconds using the game's 600-simulation-seconds-per-day clock.

Example:

```text
KIKU MARU: Fishing vessel, Kiku Maru. Position report: our plot
           032° / 18.4 nm from harbour. We have you at 028° /
           20.1 nm from harbour. Estimated time to harbour 1.8 hours.
           Line is holding. Report any change in your vessel's condition. Over.
VESSEL:    Kiku Maru, received. Towline holding; we'll report if the
           situation changes. Over.
```

All plotted locations and ETA values are reports, not omniscient facts. The radio conversation uses the existing interruptible broadcast director, so higher-priority traffic can take precedence.

### 3.2 Player response and silence

The player can press `F4` to request a position check or press `G` to cycle through a set of radio topics. No reply is required for towing to continue. The automatic check-in exchange acts as the maintenance loop; the player's questions allow the captain to feel like a person rather than a scripted announcement.

### 3.3 Loss of contact

A very poor signal can cause the player to miss check-ins. Two missed reports are counted. If a capable radio operator is aboard and available, the operator volunteers a log/crew line suggesting that the player try to raise the launch. The chart marker's report age continues to grow; at 45 in-game minutes it turns into an explicitly stale `?` marker.

The current version does not yet model arbitrary antenna damage or a complete player choice menu for loss of contact. This is a target for the fuller radio state machine, not a feature to assume is already playable.

### 3.4 Unscheduled transmissions

Personality-flavoured messages can occur while under tow: professional captains discuss line safety and crew readiness; terse captains give short operational reports; chatty captains volunteer small personal or traffic details; worried captains ask after flooding and crew safety. They do not interrupt an already busy radio exchange unless they use the higher-priority line-warning path.

## 4. Player conversation topics

`G` advances through this sequence; `F4` asks for position directly.

| Topic | Response behaviour |
|---|---|
| Position | Gives the launch's reported position and the captain's plot of the player's vessel. The two may differ. |
| ETA | Estimates remaining time at tow speed and warns that weather may change it. |
| Weather | Reports the sea and what the launch can see ahead. |
| Traffic | Shares a modest summary of traffic heard on the band. |
| Fishing | The Coast Guard declines to offer fishing-ground intelligence. |
| Fuel | Reports that its engineer is monitoring fuel for the escort. |
| Crew | Names its radio operator, engineer, deck hand, and line handler. |
| Name | Reveals captain and launch identity. |
| Fee | Explains the harbour handling account; the existing tow fee is retained by this version. |
| Stay | Promises to remain to the berth unless conditions force a change, and says it will warn the player. |

Example exchanges:

```text
VESSEL:   Kiku Maru, this is the fishing vessel. Request position check.
KIKU MARU: Fishing vessel, Kiku Maru. Our plot has us at 031° /
           17.2 nm from harbour. We have you at 028° / 20.1 nm.
           Your fix may be the better one; report any discrepancy. Over.
```

```text
VESSEL:   Kiku Maru, how is the weather ahead?
KIKU MARU: Fishing vessel, Kiku Maru. Visibility is fair from here.
           There's a little weather to the north-east, but nothing severe yet. Over.
```

```text
VESSEL:   Kiku Maru, will you stay with us all the way in?
KIKU MARU: Fishing vessel, Kiku Maru. We'll stay with you to the berth.
           If conditions force us to break off, I'll tell you before we cast off. Over.
```

## 5. When the tow is strained or fails

### 5.1 Line at risk

The game's sea state is normalized from 0 to 1. At 0.72 and above, the line is marked at risk on the chart with a dashed line, and the captain transmits that the sea is building, is reducing speed, and is watching the fairlead. When conditions ease, the launch reports that line strain is back within limits and returns to a solid towline.

### 5.2 Line parts / Coast Guard departs

The intended design includes a real `LINE_PARTED` event, a message reporting the part, removal of the towline, unlocked helm, two ships drifting separately, and a new-line-or-departure decision. It also includes an emergency departure if the Coast Guard itself becomes unable to continue. **These consequences are not implemented in v13.1.33**; line strain currently warns and changes chart styling, but does not yet snap the line.

### 5.3 Sinking during tow

The intended integration with `SINKING_AND_ABANDONMENT.md` aborts the tow at critical flooding, unlocks the helm for abandonment, and lets the Coast Guard choose whether it can approach the raft. That full branch remains a design target and is not introduced by this tow-communication pass.

## 6. State and transitions

The desired full state machine is:

```text
EN_ROUTE -> ALONGSIDE -> UNDER_TOW
UNDER_TOW -> LINE_AT_RISK -> UNDER_TOW
LINE_AT_RISK -> LINE_PARTED -> UNDER_TOW (if a new line is secured)
LINE_PARTED -> DEPARTING (captain withdraws)
UNDER_TOW -> DEPARTING (captain's emergency)
UNDER_TOW -> ARRIVED -> escort marker remains 30 in-game minutes -> removed
```

The currently playable states are `EN_ROUTE`, `ALONGSIDE`, `UNDER_TOW`, and `ARRIVED`. Position reports, radio conversations, the harbour-to-intercept route, visible placeholder hull, line-passing/turning phase, physical/chart towline, line-risk visual, and marker fade are implemented. Actual line parting/reconnection, independent departure/fuel failure, and raft recovery remain planned.

## 7. Initial tuning values

| Constant | Value | Use |
|---|---:|---|
| `CHECKIN_INTERVAL` | 30 in-game minutes | Scheduled position check-in |
| `CHECKIN_MISSES` | 2 | Missed reports before operator comment |
| `STALE_TOW_REPORT` | 45 in-game minutes | Marker receives `?` |
| `DEPART_DELAY` | 30 in-game minutes | Marker remains after arrival |
| `UNSCHEDULED_CHANCE` | approximately 10% per 10-minute check window | Personality chatter target; current cadence uses a longer randomized timer to prevent radio spam |
| `CAPTAIN_PLOT_ERROR_NM` | skill-scaled, 1–3 nm | Error in reported position |
| `LINE_RISK_SEA_STATE` | 0.72 (normalized) | Dashed towline and warning |
| `DEPART_FUEL_FRACTION` | 0.15 | Planned independent departure threshold; not yet active |

## 8. Test plan

The v13.1.33 suite includes checks for:

1. Named captain/callsign and an independent four-person Coast Guard crew.
2. Reported positions being distinct from live position.
3. Chart report age and the 45-minute stale threshold.
4. Skill-scaled nautical-mile plot error.
5. Bearing/range report formatting.
6. Dashed towline geometry.
7. 30-minute check-in and 45-minute staleness time conversion.
8. Game state owning/updating a separate escort entity.
9. Coast Guard marker/towline and chart status section.
10. Periodic and unscheduled radio conversations.
11. `F4` position check and `G` conversation topics.
12. Arrival fade and escort removal.
13. The physical placeholder hull and water-view towline are drawn.
14. The route begins at harbour and ends at a calculated intercept point.
15. Tow start is gated on arrival and the short alongside/turning handover.

These are headless state/source regression tests. A graphical Pygame playtest is still needed to validate chart layout and the feel/pacing of radio conversations in a live run.

## 9. Future design questions

- Should captain personality be inferred from dialogue or shown explicitly?
- Can a familiar peer captain answer later calls at a lower fee? The Coast Guard should remain the default for this version.
- Should a captain ever lie about their position? The current Coast Guard reports are noisy, but not intentionally deceptive.
- Should the chart show the escort's true position after arrival? No; the chart is a record of the crew's belief, not a reveal of hidden truth.
- Should AI traffic and tow escorts share a common chart-marker renderer in 13.2? Yes. They should use the same transform, colour/identity metadata, report age, and stale-contact treatment.
- Should players be able to answer AI distress calls later? Yes; that belongs to the broader 13.2 ship-radio and AI traffic system.
