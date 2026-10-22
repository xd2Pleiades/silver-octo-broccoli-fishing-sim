# Changelog — v13.2.05

Date: 2026-10-22

## Merge of uploaded v13.2.04 WIP

- Three-way merged the WIP `fishing_sim/core/game.py` against the common v13.2.03 base and the newer v13.2.04 tree, retaining the v13.2.04 shared Coast Guard identity and all intervening fixes. The merge produced no conflict markers and compiles.
- Added `fishing_sim/systems/sea_interaction.py`: hull heave/pitch/roll response, rail strike/overtopping detection, bounded ripple rings and the compartment flooding/buoyancy/list model.
- Merged `sea_foam.py` impact emission, hull-strike integration, deck-water boarding/scupper drain, bilge pump, physically staffed bucket-bailing, flooding alerts/telemetry and severe-foundering trigger into `core/game.py`.

## M9 — Distress and MAYDAY first slice

- Added `DistressDispatcher`, using deterministic seed-derived outcomes and 30-second simulation-time dispatch cadence. Distress candidates are evaluated from the shared radio candidate index, not only active/rendered traffic.
- Added one-shot MAYDAY state, uncertain reported position and incident kinds (taking water, engine failure, injury, gear entanglement). Distress candidates are bounded to one new event per dispatch cadence.
- MAYDAY uses critical-priority broadcast traffic and interrupts routine radio UI exchanges.
- Added player ASSIST/IGNORE actions in the radio UI, keyboard shortcuts `A`/`I` when an active MAYDAY is selected, Notebook entries, bounded rescue-contact promotion (maximum three), and idempotent trust effects (+0.40 assist / -0.50 ignore).
- Included distress fields in traffic contact snapshot/restore paths; this is not yet global career-save migration.

## Deferred / limitations

- ASSIST records an acknowledgement and relationship effect but does not yet simulate a physical intercept or rescue tow.
- The full raft survival and responder-pickup design remains unfinished.
- M10 global career-save wiring remains outstanding; snapshot helpers do not alone guarantee the legacy save file persists these states.
- Weather-grid mean tick previously measured ~2.86 ms, above the 2 ms budget; optimization remains before Phase B.

## Validation

- `python -m compileall -q fishing_sim run_fishing_sim.py`: passed.
- Focused regressions: 133 tests passed (see `TEST_RESULTS_V13_2_05.txt`).
- No live Pygame visual playtest was possible in the build environment.
