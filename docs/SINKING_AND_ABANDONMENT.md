# Sinking and Abandonment: Design and Implementation Guide

**Status:** Proposed design; not yet implemented as a complete playable system  
**Depends on:** Phase 5 processing / ice hold / manual hatches; Phase 6 hauler and stern roller; v13.1.29 anchor and tow  
**Feeds into:** Plan 13.2.xx AI traffic, ship radio, persistence

## Purpose

Flooding, foundering, and abandonment should have real consequences. The emergency boat should be a playable survival state rather than a cutscene. A sunk ship does not immediately end the run: the player continues with the surviving raft crew, and the outcome depends on weather, fatigue, equipment, and whether a distress call is heard.

## Core principle

Water is the antagonist. It enters through things the player already controls (hatches, sluicing, and storm exposure) and leaves through things the crew can do (bailing and pumps). New survival mechanics should reuse existing crew movement, radio, weather, and rescue systems wherever possible.

## 1. Flooding model

### 1.1 Compartments

Reuse the physical layout. Each compartment should track the following state:

| Field | Type | Meaning |
|---|---|---|
| `water` | float, m³ | Water currently inside |
| `capacity` | float, m³ | Volume before the compartment is full |
| `free_surface` | float, 0–1 | Baffling factor: 0 is baffled, 1 is open |
| `open_hatch` | bool | Synchronized with the existing hatch state |
| `breach` | float, m² | Effective hull-hole area; 0 means intact |
| `pump_rate` | float, m³/s | Installed pump rate; 0 if none |

Compartments should match the five relevant ship areas:

- `WHEELHOUSE`
- `MAIN_DECK` (working deck and cutting-table area)
- `ENGINE_ROOM`
- `ICE_HOLD`
- `FISH_HOLD`

The current game's engine-room, hold, and deck-water values can be adapted into this fuller volume model incrementally. Do not pretend that a single normalized flood value is already a compartment-volume simulation.

### 1.2 Water ingress

| Source | Condition | Suggested rate model |
|---|---|---|
| Open hatch / boarding sea | Hatch open and wave height > 1.5 m | `k_hatch * breach_equiv * wave_height` |
| Hull breach | `breach > 0` | `k_breach * breach * sqrt(depth_below_waterline)` |
| Deck water | Storm and scuppers blocked | `k_deck * wave_height * (1 - scupper_flow)` |
| Sluicing left on | Hose/sluicing switch remains on | Small continuous ingress |
| Tow or collision | Future extension | Explicit event source |

`depth_below_waterline` should use the compartment's vertical offset. The engine room therefore floods faster than the wheelhouse, creating a meaningful lower-deck risk.

### 1.3 Water egress

- **Bailing:** Existing crew behavior should remove water only from the compartment in which the sailor is physically working. Rate should scale with skill and health.
- **Bilge pump:** A pump station in the engine room requires an assigned crew member and a running engine, unless a manually operated pump is added. It should fail if water submerges its intake or the engine room is critically flooded.
- **Net rate:** `egress - ingress`. Warn when positive ingress is sustained for `T_WARN` seconds.
- **Readability:** Show the water level and whether bailing/pumping is currently reducing it. A warning must distinguish ongoing ingress from an active but insufficient pump.

### 1.4 List, trim, and the death spiral

- `list` is port/starboard heel from asymmetric water, measured in degrees.
- `trim` is bow/stern pitch from fore/aft water distribution.
- Unbaffled free-surface water reduces effective stability, proportionally to `free_surface * water`.
- Above `LIST_CRITICAL` (initial target: 18°), the deck edge starts shipping water at an increased rate and a capsize timer begins.
- List should degrade rudder authority and crew movement speed. At a more severe threshold, the hauler should be prevented from operating safely.

A wet compartment should be recoverable early. The same compartment left unattended can become terminal. The player should see the progression and have an opportunity to act before the critical threshold.

## 2. Flooding state machine

```text
NORMAL
  -> TAKING_ON_WATER   (net ingress > 0 for T_WARN)
  -> FLOODED           (any compartment > 60%, or list > 8°)
  -> CRITICAL          (any compartment > 90%, or list > LIST_CRITICAL)
  -> ABANDON_SHIP      (player order before capsize, or explicitly defined last-chance rule)
  -> ADRIFT             (raft in water)
  -> RESCUED | LOST
```

`TAKING_ON_WATER -> NORMAL` is allowed if net egress remains positive for `T_RECOVER` seconds. Later stages should ratchet forward rather than oscillate rapidly as waves slosh around.

**Abandonment timing:** The preferred design is that the player deliberately orders abandonment while there is still time to board. Capsize without a timely abandonment order can go directly to `LOST`, because the raft may no longer be launchable. Do not automatically launch a raft only after the ship has already become unrecoverable.

**Existing input conflict:** The supplied design draft proposes `A` at the liferaft station. In v13.1.29, `A` already raises/lowers the anchor. Do not assign two unrelated actions to the same global key; use a liferaft interaction/context-menu option or a distinct, documented key with confirmation.

## 3. Abandonment and emergency boat

### 3.1 Deployment

- One inflatable liferaft is stowed at the stern.
- Deployment begins only after a deliberate abandonment order, while deployment is still possible.
- Crew board over `BOARD_TIME` seconds, faster with more healthy hands available.
- Crew who fail to board before the ship goes under are marked `LOST`; do not silently teleport them into the raft.
- Reuse the existing rescue-boat movement/state machinery where possible, rather than making a second, incompatible boat controller.

### 3.2 Art reuse

Reuse the cached ship surface for the emergency-boat sprite, scaled once to `RAFT_SPRITE_SCALE` (initial target: 0.18) and given a small tint/rotation distinction. Cache the derived sprite; do not rescale and rotate a large surface from scratch every frame. This keeps art cost low and follows the project's static-art caching rule.

### 3.3 Provisions

Determine raft equipment at the moment of deployment from what is aboard:

| Item | Effect |
|---|---|
| Paddle | Normal paddling efficiency |
| Spare paddle | Replaces one lost paddle |
| Flares | Improves the chance of being spotted |
| Drinking water / rations | Extends stamina before exhaustion |
| Handheld radio | Enables a MAYDAY call |

Missing gear is part of the survival challenge. The UI/log should state what was carried aboard so the player understands the consequences.

## 4. Raft survival state

### 4.1 Movement and navigation

- Initial paddle speed: `RAFT_SPEED = 0.4 kn`, around 1/20 of ship speed.
- The player can right-click a point on the ocean to set a desired direction. Crew execute the order; it is not an instantaneous teleport or a rail path.
- Paddling effectiveness degrades with fatigue and sea state. Wind/current still affect the raft, with leeway becoming dominant when crew stop paddling.

### 4.2 Fatigue and stopping

Each raft crew member has `stamina` from 0 to 1, starting at 1.

- Paddling drains `STAM_DRAIN` per second, increased by rough seas.
- Below 0.2 stamina, efficiency falls linearly.
- At zero stamina, exhausted crew stop paddling and drift. Do not kill them solely for being exhausted.
- Recovery is slow (`STAM_REGEN`) and only occurs when the raft is relatively dry and the sea is calmer than the drain threshold.

The player cannot force exhausted crew to paddle. Waiting and drifting are valid failure states.

### 4.3 Paddle loss

A paddle may be lost in a raft capsize, an extreme wave, or when a crew member goes over the side while holding it.

- Without a paddle, efficiency falls to `HAND_PADDLE_EFF` (initial target: 0.15) and stamina drains faster.
- A spare paddle can replace one lost paddle.
- With no paddle, no spare, no radio, and exhausted crew, the raft stops making meaningful progress after `GIVE_UP_GRACE` (initial target: 600 seconds). The crew should drift and remain eligible for later rescue rather than immediately fading to black.

### 4.4 Storm ejection and clinging

While `sea_state > STORM_THRESHOLD`, check each wave for each crew member:

```text
p_eject = EJECT_BASE * sea_state * (1 - grip_factor) * (1 - stamina)
```

The grip factor improves when crew hold the painter, spare hands are available, and the raft is not swamped.

An ejected crew member enters `CLINGING`, remains visibly near the raft, and loses stamina at `CLING_DRAIN` (initial target: 0.010/s). Another raft member must haul them aboard, taking time and stamina. A clinging crew member who reaches zero stamina before recovery is `LOST`. Several ejections in one storm can empty a raft, but should be rare.

### 4.5 Rescue

Rescue sources, in priority order:

1. **Responding vessel:** A MAYDAY was sent and acknowledged; the acknowledgement is not itself a rescue.
2. **Passing AI traffic:** Future 13.2 vessels may spot the raft, more readily if flares are present.
3. **Coast station / shore:** The raft reaches a safe landing area.

A rescue acknowledgement is a claim, not a guarantee. A responding vessel may be delayed, unable to reach the casualty, or misreport its position. Radio logs should distinguish *acknowledged*, *dispatched*, *sighted*, and *rescued*.

Suggested detection model per hour:

```text
p_detect = base
           * (has_flares ? FLARE_MULT : 1)
           * (has_radio ? RADIO_MULT : 1)
           * proximity_factor(distance_to_nearest_traffic_or_shore)
```

## 5. Loss and persistence

| Thing | On abandonment | On rescue | On `LOST` |
|---|---|---|---|
| Ship | Lost | Lost | Lost |
| Fish in hold | Lost | Lost | Lost |
| Longline gear | Lost | Lost | Lost |
| Crew already aboard raft | Carried | Carried | Lost if unrecovered |
| Crew left aboard | Lost | Lost | Lost |
| Money / reputation | Kept, subject to penalties | Kept, subject to penalties | Kept |
| Radio contacts | Kept | Kept | Kept |

If all crew are lost, end the run with a clear loss summary and offer a fresh-vessel path rather than pretending that the wreck never happened. A future extension may leave a charted hazard or salvage site.

The save system must preserve `ADRIFT` state, raft position/heading, stamina, provisions, paddle state, clinging crew, and pending rescue calls.

## 6. Initial tuning values

Keep tunable values together so balancing does not require changes throughout gameplay code.

| Constant | Initial value | Meaning |
|---|---:|---|
| `T_WARN` | 4 s | Sustained ingress before a warning |
| `T_RECOVER` | 10 s | Sustained egress before clearing the early warning |
| `LIST_CRITICAL` | 18° | Deck edge starts submerging |
| `DECK_EDGE_MULT` | 3.0 | Ingress multiplier past critical list |
| `CAPSIZE_TIME` | 45 s | Time in critical condition before foundering |
| `RAFT_SPRITE_SCALE` | 0.18 | Cached ship-art scale for raft |
| `BOARD_TIME` | 6 s | Full-crew boarding target |
| `RAFT_SPEED` | 0.4 kn | Raft paddling speed |
| `HAND_PADDLE_EFF` | 0.15 | Efficiency without a paddle |
| `STAM_DRAIN` | 0.004/s | Normal paddling drain |
| `STAM_REGEN` | 0.001/s | Slow recovery while resting |
| `CLING_DRAIN` | 0.010/s | Stamina loss while in water holding on |
| `EJECT_BASE` | 0.02/wave | Base storm-ejection probability |
| `PADDLE_LOSS_WAVE` | 4.5 m | Wave height that can take the paddle |
| `GIVE_UP_GRACE` | 600 s | Grace before abandoned paddling attempt becomes idle drift |

## 7. Existing-system interaction

- **Hatches (`U`):** Leaving a hold hatch open in bad weather should be a major sinking risk. Teach this through the crew log, not a recurring popup.
- **Bailing:** Keep the existing physical crew-task requirement. Display compartment level and removal rate.
- **Tow (v13.1.29):** A tow must cast off if the ship reaches critical flooding; towing does not save a sinking vessel. The abandonment option must remain available while a tow is active.
- **Anchor (v13.1.29):** Anchoring in a storm with an open hatch remains a legitimate way to sink. Do not silently protect the player from the consequences.
- **Radio:** MAYDAY should use the same broadcast-conversation system and the same clarity, attribution, delay, and uncertainty rules as other calls.
- **Sinking in harbour:** The ship can be salvaged with severe fines and reputation consequences; it need not erase the entire run.

## 8. Required headless tests

1. `test_ingress_open_hatch_storm` — hatch open plus storm raises compartment water.
2. `test_bail_reduces_water` — a skilled crew member in the compartment reduces water.
3. `test_bail_wrong_compartment` — bailing does not affect water elsewhere.
4. `test_list_from_asymmetric_flooding` — port/starboard imbalance creates list.
5. `test_capsize_at_critical_list` — unchecked critical list reaches foundering.
6. `test_recovery_from_early_flood` — close hatch and bail; state returns to `NORMAL`.
7. `test_abandon_requires_order` — capsize without timely abandonment gives no free raft.
8. `test_raft_sprite_uses_ship_surface` — raft sprite comes from cached ship art and uses the configured scale.
9. `test_fatigue_stops_paddling` — zero stamina stops progress without automatically killing crew.
10. `test_paddle_loss_falls_back_to_hand_paddle` — efficiency equals `HAND_PADDLE_EFF`.
11. `test_give_up_after_grace` — no gear and no stamina eventually results in idle drift.
12. `test_storm_ejection_and_recovery` — ejection enters `CLINGING`; haul-in can recover the crew member.
13. `test_clinging_without_recovery_is_lost` — unrecovered clinging crew are lost at zero stamina.
14. `test_mayday_acknowledged_is_not_rescue` — acknowledgement alone does not set `RESCUED`.
15. `test_rescue_by_traffic_with_flares` — flares improve vessel/traffic detection.
16. `test_sink_under_tow_casts_off` — critical flooding terminates tow and preserves the abandonment option.
17. `test_save_load_mid_adrift_preserves_state` — raft status, crew stamina, and provisions survive a save/load cycle.

## 9. Open design questions

- Should the player choose who boards, or should boarding follow proximity and health?
- Is `LOST` a permanent run end or a score screen with a fresh vessel?
- Should the wreck remain as a charted hazard / salvage site?
- Should flares be finite (initial leaning: three), making them a valuable raft resource?
