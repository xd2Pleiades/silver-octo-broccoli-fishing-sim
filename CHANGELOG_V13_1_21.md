# Changelog — v13.1.21

## Lower deck refit

- Reworked lower-deck zones to cover almost the full inboard hull length: aft stores, ice hold, engine room, forward crew cabin, and a tapered forepeak chain locker.
- Moved the cabin farther forward and kept the engine-room landing under the existing main-deck engine hatch.
- Added a continuous centreline aisle with room dividers drawn around, rather than across, the travel corridor.
- Repositioned the engine casing away from the walking lane to maintain navigation-grid clearance.

## Sailor-sized bunks and sleeping

- Increased berths to approximately 88 × 32 world units at the standard ship scale, enough for the horizontal sleeping sprite.
- Arranged six bunks in paired port/starboard rows in the bow cabin, with six unique approach points in the central aisle.
- Expanded the horizontal sleeping pose to fill the mattress more naturally.
- A sailor lying in a bunk is excluded from hull/bed collision response and crew separation; urgent task changes wake the sailor and put them back at the aisle stand before moving.

## Engine-room path recovery

- Lower-deck A* uses the complete inboard hull and visual-only compartment regions; cabin/ice/engine boundaries no longer split the walk graph into islands.
- A* now returns an empty route when the target is genuinely unreachable instead of returning the target as a fake straight-line route.
- Sailors brake and re-plan when no route is available instead of pushing into casing/bunk collision geometry and remaining stuck.
- Moved the lower wheelhouse companionway landing to the central cabin aisle.

## Verification

- Python compilation passes.
- **335 automated tests pass** in the test runner output, including 10 new lower-deck layout/path/sleep contracts.
- Pygame is unavailable in this environment; verify corridor traffic, bed occupancy, and crew access visually on desktop.
