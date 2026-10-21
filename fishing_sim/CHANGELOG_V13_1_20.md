# Fishing Simulator 13.1.20 — Phase 6: Powered Hauler and Stern Roller

## Implemented

- Phase 6 mechanics are integrated into the modular V13 project while preserving the Phase 3–5 wheelhouse, engine-room, hatch, flooding/bilge, processing, ice-hold, and runtime error-cache work.
- The upstream rewritten sailor painter was reviewed against the linked repository's `fishing_sim/core/game.py` and retained: it includes jacket highlights, collar/buttons/pocket details, carried fish, bucket/accessories, headwear, and the health bar. The entire upstream runtime was not substituted because it is a different entry-point/phase state; the mechanics were applied to the feature-complete V13 base instead. Source: https://github.com/xd2Pleiades/silver-octo-broccoli-fishing-sim
- Added pure gear helpers in `fishing_sim/systems/gear_handling.py` for friction-drum slip, line wear, roller friction, and snag risk.
- Hauling torque now depends on engine power, actual working hauler hands, line load, and drum condition. Sustained friction-drum slip lowers drum condition and reduces available hauling speed/power.
- Line load responds to deployed hook count, sea state, vessel speed during setting, and the caught fish/fight tension during hauling.
- The stern roller has three states: working, bypassed, and jammed. A working roller wears over time and can seize when worn and held above its load threshold. A bypassed or jammed roller increases line chafe and snag chance.
- Snags pause the line for a short interval and damage its condition. If line condition is severely degraded under high sustained load, the mainline can part and lose the remaining hooks. Unharnessed crew working at the stern gear may be injured by whipping line; `Y` harness protection remains relevant.
- Roller/drum condition is visible in the world and the line status readout. The roller tint is steel-grey when correctly engaged, gold when bypassed, and red when jammed; drum tint and the slip percentage show overload. Press `M` to engage/bypass the roller. If jammed, order a healthy deckhand aft near the roller, then press `M` to clear it.
- Set package version metadata to `13.1.20` and updated the Roadmap V2 Phase 6 status.

## Verification

- Python compilation passed.
- Full headless unit-test suite: **325 tests passed** (including 10 Phase 6 gear mechanics/renderer-preservation checks).
- ZIP integrity and extracted-archive test run are recorded with this release build.
- Pygame is unavailable in the build environment. Actual FPS, visual rendering, and hand-play testing of setting/hauling with jammed or bypassed gear remain to be performed on a desktop build.

## Controls

- `M`: engage/bypass the stern roller. If jammed, a healthy main-deck crew member must be near the stern roller to clear it.
- `Y`: toggle the crew safety harness; it reduces the whipping-line injury risk but slightly slows work per the existing tradeoff.
- Existing manual setting (`P`), auto-fishing (`L`), haul-now (`J`), brake/gaff (`SPACE`), and engine-room maintenance controls remain unchanged.
