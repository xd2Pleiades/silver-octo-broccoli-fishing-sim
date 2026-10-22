# M9 Survivor Transfer, Liferaft Recovery and Beacon Discovery

## Scope

This implementation adds a small, deterministic survivor layer to the physical player and autonomous AI assistance already present in v13.2.13. Survivor records use the original distress vessel's stable `vessel_id` as their parent. Liferafts are survivor targets, not new `AIShip` objects, and do not create a second Coast Guard/tow identity.

## Incident rules

- `injury`: creates one casualty aboard the distressed vessel with a 360 simulation-second survival clock.
- `taking_water`: creates one liferaft with two occupants and a 270 simulation-second survival clock.
- Other distress kinds do not create extra survivors in this first slice; they continue using their existing ship-assistance outcomes.
- The registry is initialized once per distress vessel, keyed by stable vessel ID, and updated on simulation time rather than render frames. Game invokes the service from its frame update, but the registry throttles fleet scanning and survivor movement/clock updates to once per simulated second. A campaign-phase switch is refused while a casualty or liferaft remains active, preventing the survivor coordinates from being interpreted in another phase's map plane.

## Liferaft simulation

- Each raft receives a stable ID of the form `<vessel_id>:liferaft:01`.
- Initial position offset and drift direction are derived from a stable seed, without consuming the game's gameplay RNG stream.
- Rafts drift with a small speed that rises with local sea state. Their survival clock drains faster in rougher seas.
- A raft remains a separate target and is not teleported aboard merely because a responder completes ship assistance.
- Pickup requires the responder to be within 2 nautical miles and the raft to still have survival time remaining.
- An afloat nearby raft is drawn as a small `RAFT / 2` sea-view marker.
- A radio beacon is received only while the player's wireless operator is on watch and the raft is within 55 NM. The first reception creates a chart/radio report; repeat bursts are attempted every 90 simulation seconds while the raft remains in range.
- Each radio report stores a deterministic 0.25–0.95 NM position error, report timestamp and sequence. The chart displays the *reported* fix with an amber uncertainty ring; it never follows the raft's exact physical drift coordinate. A plot becomes stale after 180 simulation seconds without a new burst and is refreshed when another burst is received.
- Beacon discovery state and the last uncertain chart fix are part of the career snapshot. Losing radio watch or moving out of range prevents fresh reports but does not erase the last report.

## Casualty transfer and mission idempotency

- A casualty can be transferred only while the casualty record remains `aboard` and its survival clock is positive.
- Successful transfer records the stable rescue `mission_id` on the incident and changes the casualty to `recovered`.
- A repeated completion transition for the same mission ID returns zero new recoveries.
- If survival reaches zero before transfer, the casualty becomes `lost` and cannot later be counted as rescued.
- The shared registry is used by both player-rescue and autonomous AI-rescue completion handlers. There is still one active autonomous response mission at a time.

## Persistence and migration

`rescue_survivors` is an optional versioned career-save section. It contains stable parent/survivor IDs, casualty status/timer, raft status/position/remaining lifetime/drift heading, recovery mission IDs, aggregate recovery/loss counters, and liferaft beacon sequence/report state. Validation rejects unsupported schemas, mismatched parent identities, negative counters/timers, non-finite physical or reported positions and invalid beacon state. The additional beacon fields have defaults so earlier v13.2.13 survivor snapshots can still be loaded. Career saves without this optional section remain loadable; a completed historical distress is not retroactively assigned new survivors. Survivor update cadence is persisted so repeated rendered frames do not trigger a full fleet scan.

## Validation

`fishing_sim/tests/test_v13_2_13_rescue_survivors.py` covers deterministic raft deployment, no duplicate ship creation, one-time casualty transfer, physical pickup radius, raft drift, faster storm survival drain, expiration/loss, staffed-radio and range gating, uncertain report-vs-physical position, stale chart plots, periodic beacon refresh, snapshot round-trip, and invalid snapshot rejection. Static game-wiring checks cover initialization, update, radio announcement, both chart variants, completion and career persistence.

Pygame is unavailable in the build environment. The marker draw code compiles and headless report-state tests pass, but marker visibility/legibility, a real radio transcript, route clicking at chart scale, and a graphical career save/load round-trip remain on `VISUAL_QA_CHECKLIST_V13_2_12.md`.

## Known next steps

1. Add player-directed Coast Guard routing, starting with a route-to-reported-raft / distress plot order that keeps TowEscort identity and ownership intact.
2. Add bounded multi-responder dispatch only after response/contact limits are measured.
3. Test storm conditions, radio watch changes, stale plot recovery, raft visibility, and save/load in a Pygame-enabled runtime.


## Current merge note

The behavior described here is merged into the supplied v13.2.15 input archive. Newer Chapter A conversation and Chapter B sailor-motion behavior from that archive is preserved. The internal package/save version remains `13.2.13`, matching the source archive's embedded metadata; see `RAFT_BEACON_MERGE_V13_2_15.md` for the merge record.
