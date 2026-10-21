# V13V1-18 — Phase 5 Processing, Dogged Hatches, Bilge and Ice Hold

Built on v13v1-17 and the Roadmap V2 Phase 3/4 work.

## What changed

- Added three independent, visible hatch-cover states: engine-room access, forward hold hatch, and aft hold hatch. Covers start dogged shut.
- Added a timed `U` action to open or dog the nearest reachable hatch. Manual `Q`/`E` climbing is blocked by a shut cover; AI cross-level orders open the required cover at the landing and dog it again after crossing when clear.
- Open hatches admit more water into the engine bilge/ice hold. Engine bilge water reduces available power; severe bilge can trip the engine. Hold water raises storage temperature and accelerates ice melt.
- Added compartment-aware bucket bailing for engine-room bilge and ice-hold water. Crew must be physically in the room to reduce its water level.
- Completed the cutting-table pipeline: bleed, gut/de-gill, slice, then carry fish to an open hold hatch. Crew cannot stow catch through a shut hold cover and will wait with a spoken warning.
- Added a timed seawater-hose wash at the cutting-table station (`F`) to reduce table blood and clean nearby blood/slime patches.
- Added a timed ice-trimming/packing task (`V`) inside the ice hold; when conditions are safe it temporarily reduces ice melt. Flooding defeats cooling and wastes ice faster.
- Updated the Roadmap V2 status to mark Phase 5 complete and identify Phase 6 hauler/roller mechanics plus open-hatch fall hazard as remaining work.

## Controls

- `U`: open / dog shut nearby engine or hold hatch.
- `F`: sluice cutting table/deck with hose (stand by the hose station).
- `V`: trim and pack ice (inside the below-deck ice hold).
- `Q` / `E`: climb only after the appropriate hatch is open; otherwise climb is refused with a spoken instruction.

## Verification

- Python compilation: passed.
- Phase 5/Phase 3/Phase 4/manual-setting regression tests: passed.
- Full suite: use `python -m unittest discover -s fishing_sim/tests -v` from the project directory.
- Pygame graphical playtest has not been performed in this environment; confirm hatch visibility, crew crossing, bailing cadence and ice-hold layout in the running game.

## Known follow-up

An unattended open deck hatch currently increases flooding and blocks/permits level access correctly, but the planned chance of a sailor stepping/falling through an open hatch has not yet been implemented. It is recorded as a Phase 7 polish item rather than silently counted as complete.
