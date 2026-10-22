# Changelog — Fishing Simulator v13.2.13

**Release focus:** M9 physical player-vessel assistance, plus active mission persistence.

## Added

- `PlayerRescueMissionManager`, a bounded one-at-a-time rescue mission state machine (`en_route` → `on_scene` → `completed`, with loss/cancel/failure states).
- Accepting **ASSIST** on a received MAYDAY now plots the normal navigation destination to the ship's **reported position**. The player's hull is not moved or teleported.
- A distressed AI ship remains fixed at its distress scene rather than continuing along its ordinary schedule during the incident.
- Real navigation proximity is required before the mission enters `on_scene`; the on-scene work timer must finish before an outcome is recorded.
- Situation-specific outcomes for taking water, engine failure, serious injury, and gear entanglement.
- Radio history / broadcast updates for dispatch, arrival, rendezvous loss, and completion.
- Restoration of the pre-rescue course after completion, unless the player takes control of navigation during the mission.
- Versioned career-save snapshot support for the active mission, reported plot, route target, navigation backup, on-scene timer, outcome, and counters. Older saves without the optional mission section still load as no active player-vessel rescue.
- Phase switching is refused while an active player rescue mission is in progress, preventing the target from being orphaned in the inactive world.
- New headless regression tests for mission timing, target freeze, course plotting without teleporting, report validation, active mission snapshots, and game wiring.

## Fixed / hardened

- Corrected the `on_scene_started_s == 0` timer edge case so an on-scene rescue that begins at simulation time zero can still complete.
- Kept the radio transcript read cursor stable when the radio UI is closed, allowing rescue status lines to be read later.
- Made rescue-dispatch setup roll back the decision/trust increment if course setup throws before the mission starts.
- Updated the career envelope package version to `13.2.13`.

## Not yet included

- The Coast Guard launch does not yet dispatch itself to third-party AI distress calls.
- No casualty transfer, raft rendezvous, or full raft survival/pickup loop is implemented by this slice.
- Pygame live navigation / visual / career save-load testing was not possible in this environment.

## Validation

- Focused tests: 278 run; 263 passed, 15 skipped, zero failures.
- Python compilation and the dependency-free release gate passed.
- Pygame was unavailable; graphical/live save-load checks were not run.
