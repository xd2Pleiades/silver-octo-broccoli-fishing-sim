# V13V1-17 — Roadmap V2 Phase 3 and Phase 4

## Phase 3 — Forward wheelhouse cutaway

- Changed wheelhouse viewing from a whole-hull veil to a localized roof cutaway. The wheelhouse still remains `Level.WHEELHOUSE` for multi-level navigation and station ownership, but the visual shows the cabin interior over the same top-down vessel rather than treating it as a separate full-screen height.
- Kept the surrounding main deck visible, including deck crew. Main-deck crew can still be selected while viewing the cutaway, and right-click orders outside the cabin continue to target the main deck.
- Preserved the helm, magnetic compass, mechanical throttle quadrant, AM/SSB radio, station ownership, and `helm_ok` propulsion interlock.

## Phase 4 — Engine room and crew quarters

- Added six bunk fixtures to the engine-room perimeter and six reserved rest-stand positions. Bunks are below-deck navigation/collision solids, so crew path around them.
- Changed rest duty to route sailors to a reserved bunk stand on `Level.BELOW`; fatigue and morale recovery now happen in the below-deck quarters rather than at the main-deck standby point.
- Preserved the existing oil, cooling-water intake, and shaft-seal wear/fault checks. Neglected maintenance can reduce engine output or trip the diesel; an engineer at the engine station restores service points, and engine output still gates propulsion and hauler power.
- Kept the engine-room and ice-hold compartments separate. Hatch opening/closing remains a later Phase 5 task.

## Verification

- Python compilation passed.
- 298 headless source/model tests pass.
- Pygame is not installed in the build environment, so the roof cutaway, bunk readability, and live multi-level walking still need a graphical playtest.

## Documentation

- `Roadmap_V2.md` is updated with Phase 3 and Phase 4 complete.
- The previous `Roadmap V2 (4).md` upload is retained in `docs/` as the older reference copy.
