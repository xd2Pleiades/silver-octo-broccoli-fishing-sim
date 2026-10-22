# v13.2.05 Implementation Status — M9 first slice + WIP sea/flood merge

**Release:** v13.2.05  
**Base:** v13.2.04 plus uploaded `fishing_sim_v13_2_04_wip.zip` three-way merge  
**Roadmap focus:** M9 — Distress, MAYDAY and player assistance. The WIP's sea/hull interaction was also merged as requested.

## Merged from the WIP

- `fishing_sim/systems/sea_interaction.py` provides `HullWaveInteraction`, heading-relative deck/world coordinate transforms, `RippleSystem` with a strict cap, and `FloodingModel` for boarding water, scupper drainage, bilge pumping, reserve buoyancy, free-surface/list and progressive flood-state transitions.
- `fishing_sim/systems/sea_foam.py` supports impact emission.
- `fishing_sim/core/game.py` integrates wave motion, rail slaps/overtopping, ripple and deck-foam effects, water accumulation, scuppers, engine/hold flooding, bilge pump flow, compartment bailing, flooding alerts and telemetry. A severe-foundering threshold starts the existing abandon-ship/rescue-boat/swimmer flow.
- The merge used v13.2.03 as the common ancestor so that WIP changes could be combined with v13.2.04's newer shared tow identity. Compile and test checks show no unresolved merge markers.

## M9 implemented

1. Deterministic `DistressDispatcher` with 30-second simulation-time checks, authored and low-frequency stochastic incidents, stable incident seeds, and at most one fresh event per dispatch cadence.
2. Incident types: taking water, engine failure/no way on, serious injury, and gear fouled around the propeller. A vessel's MAYDAY is one-shot for the incident.
3. Distress is considered from in-range radio candidates, even when the source vessel is coarse/non-rendered. Received calls store a reported/believed position with deterministic error; the UI does not need true position to render the contact.
4. MAYDAY interrupts routine radio and closes an open modal radio exchange. The radio UI offers ASSIST and IGNORE for the selected active call, with `A`/`I` shortcuts.
5. A decision applies trust effect once (+0.40 assist, -0.50 ignore), logs the decision, and stores flags on the common AIShip contact. Ignored distress releases the rescue-contact promotion; the world allows up to three rescue contacts at once.
6. Traffic snapshots include one-shot MAYDAY state, decision, activity override and rescue-contact state to support later persistence integration.

## M9 intentionally not complete yet

- **No physical rescue dispatch on ASSIST yet.** The current interaction acknowledges the MAYDAY and applies trust, but does not create a vessel route/intercept or a tow/rescue outcome.
- No full escalation tree for Coast Guard relays, other responders, withdrawal or delayed arrivals.
- The complete sinking/raft survival and survivor pickup flow remains separate follow-up work. The WIP gives the ship a progressive foundering/abandon trigger using existing rescue-boat/swimmer mechanics; it is not a complete liferaft sim.
- **Global save/load migration (M10) is outstanding.** The traffic snapshot API includes distress fields, but the legacy campaign save path has not yet been fully wired to serialize the new dispatcher/traffic/escort/weather state together.
- The entire historical fleet and Phase B map remain deferred.

## Validation

- `compileall`: passed.
- Focused regression suite: **133 tests passed** across the distress dispatcher, hull-wave/flooding model, tow identity, weather grid, radio UI, traffic foundation, tow persistence and prior merge/tow regressions.
- Archive integrity and Markdown placement/link audits are performed for the release archive.
- Pygame is unavailable in the build environment; no live visual playtest has been performed.
