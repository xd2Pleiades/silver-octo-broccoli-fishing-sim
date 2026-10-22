# Player-Vessel Assistance Mission — v13.2.13

## Player flow

1. The wireless receives an AI vessel's one-shot MAYDAY. The distress vessel is promoted as a known rescue contact and its reported plot remains separate from its physical position.
2. The player opens the radio UI and selects **ASSIST** (the existing `A` action while the MAYDAY is selected).
3. If the wireless is staffed, no other physical player-rescue mission is active, and a finite reported position exists, the game applies the existing one-time trust increase and commits a physical mission.
4. The radio UI closes so it cannot suppress movement controls. The player's ship takes a normal navigation destination aimed at the reported plot. The player vessel's physical and believed position vectors are not teleported.
5. When physical distance closes to the working radius, the mission enters `on_scene`, stops the rescue autopilot if the player hasn't overridden it, and reports that assistance is underway.
6. The ship must remain close enough for the timed work interval. If it moves far away, the rendezvous is lost and the mission returns to `en_route`.
7. At completion, the distressed ship gets a stable assisted outcome and anchored position override. The original course is restored only if the player did not intentionally change navigation during the mission.

## State machine

```text
ASSIST decision
      |
      v
  EN_ROUTE ---- target missing ----> FAILED
      |
      | physical range reached
      v
  ON_SCENE ---- range lost --------> EN_ROUTE
      |
      | assistance timer completed
      v
  COMPLETED
```

A mission is limited to one active player-vessel response at a time. A campaign phase switch is refused while the mission is active, because the target and mission are tied to the active phase's traffic world.

## Coordinates and information policy

- The route is based on `last_reported_position_nm`, not the target's hidden live position.
- The active Phase B report is converted through the existing phase adapter into the legacy hull/navigation coordinate plane.
- The mission controller uses the distressed vessel's frozen physical position internally to decide whether the player's vessel has come on scene; that true position is not disclosed in the radio report or mission status.
- Reaching the reported point does not guarantee a perfect fix. The on-scene radius accounts for the designed plot error.

## Current simulated outcomes

| Distress type | Recorded outcome | Meaning in this slice |
|---|---|---|
| Taking water | Water ingress contained; vessel holding station | Incident is closed and target remains on scene |
| Engine failure | Engine inspection underway; vessel secured | Incident is closed; no actual propulsion repair animation yet |
| Injury | Casualty stabilized; vessel holding station | Text/state resolution only; no casualty transfer aboard |
| Gear entanglement | Propeller fouling cleared; vessel holding station | Incident is closed; gear animation is not yet implemented |

These outcomes are meaningful mission state and radio/log feedback, but are not claims that bespoke repair simulations or casualty transfers already exist.

## Navigation ownership

At dispatch the mission snapshots the player's current destination, route waypoints, route origin, quick target, arrival-hold flag, manual-helm state, throttle, and cruise setting. When a mission completes, the snapshot is restored only if the player did not alter the rescue course. Manual steering, a different destination, or docking indicates a player override. An override is never silently overwritten by completion.

## Save data

The optional `player_rescue_mission` career-save section contains:

- `schema_version`, `mission_id`, target vessel ID and callsign;
- distress kind, reported plot and start timestamp;
- state, on-scene start, completion timestamp and last measured range;
- the prior navigation snapshot and rescue route target;
- course-override flag, final outcome and mission counters.

The traffic-contact snapshot independently carries the target's distress flags, reported plot, assistance status/outcome, frozen distress position and any position override. The loader validates both sections and requires active mission/target identity to agree. Saves written before this optional section is introduced default to no active player rescue mission.

## Test and QA boundary

The headless tests cover dispatch, single-mission limits, report validation, schedule freeze, proximity gating, on-scene duration, rendezvous loss, output state, navigation no-teleport contract, snapshot round-trip, and save/load source wiring. Pygame live controls, helm physics, on-scene visual treatment, and a real in-game career save/load round trip have not been run in this environment; they still need manual verification in a Pygame-enabled build.
